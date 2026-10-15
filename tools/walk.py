"""The files of this working tree, and of no other nested inside it.

A session's git worktree sits inside the main checkout, a whole copy of the repo with a `.git`
file; a full clone has a `.git` directory. Either is another working tree, and nothing in it is
this repo's. Every check that walks the tree walks it here, and every copy of the repo is made
here, so that all of them skip the same things. It reads only the tree, so it needs no git and
works in an export that has no `.git` at all. A link is listed, never followed, and is never
taken for another working tree, whatever it points at.
"""
from __future__ import annotations

import os
import pathlib
import shutil

# Directories that are never part of the repo, at any depth: Python's caches. A file of that name is a file.
SKIP = {"__pycache__"}
# Directories skipped at the root only: git's own store, and the corpus `make_corpus.py` writes there.
# A `.git` below the root marks another working tree, and the whole of that tree is skipped.
ROOT_ONLY = {".git", "corpus"}


def elsewhere(path: pathlib.Path) -> bool:
    """Is `path` a directory that holds another working tree? Its `.git` may be a file or a directory."""
    return os.path.isdir(str(path)) and os.path.lexists(os.path.join(str(path), ".git"))


def _skip(root: pathlib.Path):
    """What to leave out of each folder below `root`, in the form `shutil.copytree` takes."""
    def skipped(folder: str, names: list) -> set:
        top = os.path.normpath(folder) == os.path.normpath(str(root))
        out = set()
        for name in names:
            path = os.path.join(folder, name)
            if top and name == ".git":
                out.add(name)       # this tree's own, file or directory
            elif os.path.isdir(path) and not os.path.islink(path) and (
                    name in SKIP or (top and name in ROOT_ONLY) or elsewhere(pathlib.Path(path))):
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
