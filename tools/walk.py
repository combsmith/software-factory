"""The files of this working tree, and of no other nested inside it.

A session's git worktree sits inside the main checkout, a whole copy of the repo with a `.git`
file; a full clone has a `.git` directory. Either is another working tree, and nothing in it is
this repo's. Every check that walks the tree walks it here, and every copy of the repo is made
here, so that all of them skip the same things. A link is listed, never followed, and is never
taken for another working tree, whatever it points at.

Local output, Python's caches and the corpus, is skipped only while git's index does not hold it.
CI checks out the commit afresh, with its index, so there what the index does not hold was written
by the run itself. The index is read as a file, so no git is needed; an export, with no `.git`,
cannot tell local output from committed, and skips it all, as a working tree always did.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import shutil

# Local output, skipped unless git's index holds it. A file of either name is a file.
# Python's caches, at any depth:
SKIP = {"__pycache__"}
# and the corpus `make_corpus.py` writes, at the root only. A `.git` at the root is this tree's own
# and always skipped; one below the root marks another working tree, and the whole of that is skipped.
ROOT_ONLY = {"corpus"}
GITLINK = 0o160000      # the mode git's index gives a submodule


def elsewhere(path: pathlib.Path) -> bool:
    """Is `path` a directory that holds another working tree? Its `.git` may be a file or a directory."""
    return os.path.isdir(str(path)) and os.path.lexists(os.path.join(str(path), ".git"))


def _varint(data: bytes, at: int) -> tuple:
    """The number git's index writes at `at` in its own varint, and where what follows it starts."""
    byte = data[at]
    value = byte & 0x7F
    while byte & 0x80:
        at += 1
        byte = data[at]
        value = ((value + 1) << 7) | (byte & 0x7F)
    return value, at + 1


def _read(data: bytes) -> dict:
    """{path: mode} for every entry of git's index, versions 2 to 4, or ValueError."""
    if data[:4] != b"DIRC":
        raise ValueError("it is not an index")
    version, count = int.from_bytes(data[4:8], "big"), int.from_bytes(data[8:12], "big")
    if version not in (2, 3, 4):
        raise ValueError("version %d is not one this reads" % version)
    # It ends in a hash of all before it, SHA-1 or SHA-256 as the repo's objects are, or in zeros.
    if hashlib.sha256(data[:-32]).digest() == data[-32:]:
        size = 32
    elif hashlib.sha1(data[:-20], usedforsecurity=False).digest() == data[-20:] or not any(data[-20:]):
        size = 20
    else:
        raise ValueError("its checksum does not match")
    end, at, previous, held = len(data) - size, 12, b"", {}
    for _ in range(count):
        mode = int.from_bytes(data[at + 24:at + 28], "big")
        flags = int.from_bytes(data[at + 40 + size:at + 42 + size], "big")
        start, strip = at + 42 + size + (2 if version > 2 and flags & 0x4000 else 0), len(previous)
        if version == 4:        # the path is what remains of the one before, once `strip` bytes are cut
            strip, start = _varint(data, start)
            if strip > len(previous):
                raise ValueError("a path is cut by more than it holds")
        stop = data.find(b"\0", start, end)
        if stop < 0:
            raise ValueError("it ends early")
        previous = previous[:len(previous) - strip] + data[start:stop]
        held[previous.decode("utf-8", "surrogateescape")] = mode
        at = stop + 1 if version == 4 else at + (stop - at + 8) // 8 * 8      # padded with NULs to 8
    while at < end:                 # extensions: a four-letter name, a length, and that much
        if data[at:at + 4] == b"link":
            raise ValueError("it is split; `git update-index --no-split-index` joins it")
        at += 8 + int.from_bytes(data[at + 4:at + 8], "big")
    if at != end:
        raise ValueError("it ends early")
    return held


def index(root: pathlib.Path) -> dict | None:
    """{path: mode} for every path git's index holds, read from the file; None where there is no `.git`.

    Empty while nothing has been added. ValueError where it cannot be read whole, for the caller to
    fail closed on.
    """
    gitdir = root / ".git"
    if not os.path.lexists(str(gitdir)):
        return None
    if gitdir.is_file():            # a worktree's: it names the directory its index is in
        line = gitdir.read_text(errors="replace").strip()
        if not line.startswith("gitdir:"):
            raise ValueError(".git is a file that names no gitdir")
        gitdir = root / line[len("gitdir:"):].strip()
    if not gitdir.is_dir():
        raise ValueError("the gitdir .git names is not there")
    if not (gitdir / "index").is_file():
        return {}
    try:
        return _read((gitdir / "index").read_bytes())
    except IndexError:
        raise ValueError("it ends early") from None


def _local(root: pathlib.Path):
    """Whether a path, by its name from `root` and whether it is a directory, is local output to skip."""
    def output(rel: str, folder: bool) -> bool:
        dirs = rel.split("/") if folder else rel.split("/")[:-1]
        return bool(SKIP.intersection(dirs)) or (bool(dirs) and dirs[0] in ROOT_ONLY)
    try:
        held = index(root)
    except ValueError:
        return lambda rel, folder: False    # it cannot be told what is committed, so nothing is skipped
    if held is None:
        return output
    kept = set(held) | {parent.as_posix() for path in held for parent in pathlib.PurePosixPath(path).parents}
    return lambda rel, folder: output(rel, folder) and rel not in kept


def _skip(root: pathlib.Path):
    """What to leave out of each folder below `root`, in the form `shutil.copytree` takes."""
    local = _local(root)

    def skipped(folder: str, names: list) -> set:
        here = os.path.relpath(folder, str(root)).replace(os.sep, "/")
        out = set()
        for name in names:
            path = os.path.join(folder, name)
            directory = os.path.isdir(path) and not os.path.islink(path)
            if here == "." and name == ".git":
                out.add(name)       # this tree's own, file or directory
            elif (directory and elsewhere(pathlib.Path(path))) or \
                    local(name if here == "." else here + "/" + name, directory):
                out.add(name)
        return out
    return skipped


def _entries(root: pathlib.Path, under: str) -> list:
    """Every path below `root / under` that is not a directory, and every link, but none skipped."""
    skipped, out = _skip(root), []
    for folder, dirs, names in os.walk(str(root / under)):
        gone = skipped(folder, dirs + names)
        linked = {d for d in dirs if os.path.islink(os.path.join(folder, d))}
        dirs[:] = sorted(d for d in dirs if d not in gone and d not in linked)
        out += [pathlib.Path(folder, n) for n in sorted(linked) + names if n not in gone]
    return sorted(out)


def folders(root: pathlib.Path) -> list:
    """The directories at the top of `root`, sorted, but none skipped and no link."""
    names = os.listdir(str(root))
    gone = _skip(root)(str(root), names)
    return sorted(root / n for n in names if n not in gone and (root / n).is_dir() and not (root / n).is_symlink())


def files(root: pathlib.Path, under: str = "") -> list:
    """Every file below `root / under`, sorted, but none skipped and no link that points at nothing."""
    return [p for p in _entries(root, under) if p.is_file()]


def links(root: pathlib.Path) -> list:
    """Every link below `root`, sorted, whether it points at a file, a directory or nothing."""
    return [p for p in _entries(root, "") if p.is_symlink()]


def copy(root: pathlib.Path, to: pathlib.Path) -> None:
    """Copy this working tree to `to`, which must not exist, leaving out what `files` leaves out."""
    shutil.copytree(str(root), str(to), ignore=_skip(root), symlinks=True)
