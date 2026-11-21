"""The sections of a Role's patch, read as `git diff` writes them (issue 838; FR-14; decision 0188's residual, "the
push's write must land exactly that patch, and no other bytes"). A section's hunks are not read yet, and what applies
the patch is still to come.

`read(patch)` gives a patch's sections, or None for what it does not read. It reads a narrower patch than
`harness/bundle.py` does, on purpose, and what it does not read it refuses: a name is read one way only, unquoted, of
the characters `NAME_CHARS` holds, with no space, so the header alone names both files and every other line that names
one must agree with it; and of no more parts than `DEEPEST` bounds. `named(path)` is that reading of a name, for text.
A section's extended lines stand in the order git writes them, and a change of mode is a file's between its two modes.
No path is on the new side of two sections: git writes a change of a file's type as a removed file and a new one at one
path, and that is not read. A path a section renames or removes is named by no later section, on either side, and a
path a section makes, as a new file or a rename's or a copy's, is no later section's old side; a copy's source alone
may be named again, as `git diff -C` writes a copy and then a rename of one file. No file made stands where another
needs a directory.

An index line's hashes and how alike a rename or a copy says its files are, are read for their form alone, and nothing
trusts them: what a patch lands is its hunks applied to the bytes it names, and a section whose hashes differ but that
has no hunk changes no bytes.
"""
from __future__ import annotations

HEADER = b"diff --git "
OLD_SIDE = b"a/"
NEW_SIDE = b"b/"
# The extended headers git writes between a section's first line and its sides, each at most once to a section.
OLD_MODE = b"old mode "
NEW_MODE = b"new mode "
DELETED = b"deleted file mode "
NEW_FILE = b"new file mode "
SIMILARITY = b"similarity index "
RENAME_FROM = b"rename from "
RENAME_TO = b"rename to "
COPY_FROM = b"copy from "
COPY_TO = b"copy to "
INDEX = b"index "
# The one change of mode git writes in place: a file made runnable, or no longer. A change of a file's type it writes as
# a removed file and a new one.
PLAIN_MODES = (b"100644", b"100755")
DIGITS = b"0123456789"
HEX = b"0123456789abcdef"
# A hash of more characters than this, a SHA-256 name in full, is no hash git writes; nor is one of fewer than this,
# git's shortest abbreviation.
FULL_HASH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
SHORT_HASH = "0123"
ALL_ALIKE = b"100"              # how alike two files are, in percent, is no more than this
# The characters a name may hold. git writes a name of these unquoted, and no other reading of one exists: no space,
# which would leave the header two readings; no quote and no backslash, which git escapes; nothing past ASCII, which
# git quotes; and no colon, which ends a drive's name on Windows, where `C:.git/x` is in git's own directory.
NAME_CHARS = ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
              "!#$%&'()*+,-./;<=>?@[]^_`{|}~")
# A name of more parts than this has characters is no name this reads. git has no such bound, and no path of this
# repo's is near it; it bounds how many directories stand above a name.
DEEPEST = "0123456789abcdef0123456789abcdef"
# git's own directory, and the head of the short name another file system gives it (`git~1`).
GIT_OWN = ".git"
GIT_SHORT = "git~"
# The modes git writes: a file's two, a link's and a submodule's. No other is a mode to it.
MODES = (b"100644", b"100755", b"120000", b"160000")



def _number(said):
    """A count as git writes one, or None: digits, none led by 0."""
    if not said or not all(c in DIGITS for c in said):
        return None
    if len(said) > 1 and said.startswith(b"0"):
        return None
    value = 0
    for digit in said:
        value = value * len(DIGITS) + DIGITS.find(digit)
    return value


def _gits(name: str) -> bool:
    """Whether a name is git's own directory to git on some file system (its `is_ntfs_dotgit`, read wider): `.git` under
    any case or with dots after it, and its short name, `git~` and anything. A name holds no colon (`NAME_CHARS`), so
    none of the forms of `.git` that run on past one is read here."""
    head = name.casefold().rstrip(".")
    return head == GIT_OWN or head.startswith(GIT_SHORT)


def named(path) -> bool:
    """Whether `path`, as text, is a name this reads: of the characters `NAME_CHARS` holds, of no more parts than
    `DEEPEST` has characters, and with no part that is empty, `.`, `..`, or git's own directory in any form git knows
    it by. What is no text is no name, and nor is text of a subclass of `str`, whose own methods would be read."""
    if type(path) is not str or not path or not all(c in NAME_CHARS for c in path):
        return False
    names = path.split("/")
    return len(names) <= len(DEEPEST) and all(names) and not any(n in (".", "..") or _gits(n) for n in names)


def _path(said):
    """A path from a name as a patch writes it, or None where it is not one this reads (`named`). Each byte is read as
    one character, so a byte past ASCII is a character `NAME_CHARS` does not hold."""
    path = str(said, "latin-1")
    return path if named(path) else None


def _mode(said):
    """A mode git writes, one of `MODES`, or None."""
    return str(said, "ascii") if said in MODES else None


def _named(said: dict, first: bytes, second: bytes, old: bytes, new: bytes):
    """Whether a section's two lines of a rename or a copy, `first` and `second`, name what its header names: True, None
    where it has neither line, False where it has one alone or they name anything else."""
    if first not in said and second not in said:
        return None
    return said.get(first) == old and said.get(second) == new and old != new and SIMILARITY in said


def _section(lines: list, i: int):
    """`(section, next line)` for the section whose first line is line `i`, or None where it is not one this reads."""
    a, space, b = lines[i][len(HEADER):].partition(b" ")
    if not space or not a.startswith(OLD_SIDE) or not b.startswith(NEW_SIDE):
        return None
    raw_old, raw_new = a[len(OLD_SIDE):], b[len(NEW_SIDE):]
    old, new = _path(raw_old), _path(raw_new)
    if old is None or new is None:
        return None
    i += 1
    # git writes each at most once, in this order: a line out of it, or one written twice, is no line of the section.
    extended = (OLD_MODE, NEW_MODE, DELETED, NEW_FILE, SIMILARITY, RENAME_FROM, RENAME_TO, COPY_FROM, COPY_TO, INDEX)
    said, first = {}, 0
    while i < len(lines):
        found = [n for n in range(first, len(extended)) if lines[i].startswith(extended[n])]
        if not found:
            break
        said[extended[found[0]]] = lines[i][len(extended[found[0]]):]
        first = found[0] + 1
        i += 1
    renamed = _named(said, RENAME_FROM, RENAME_TO, raw_old, raw_new)
    copied = _named(said, COPY_FROM, COPY_TO, raw_old, raw_new)
    made, gone = NEW_FILE in said, DELETED in said
    moded = OLD_MODE in said or NEW_MODE in said
    if renamed is False or copied is False or (renamed and copied) or (made and gone):
        return None
    if (made or gone) and (renamed or copied or moded or SIMILARITY in said):
        return None
    if not (renamed or copied) and (old != new or SIMILARITY in said):
        return None
    if moded and not (said.get(OLD_MODE) in PLAIN_MODES and said.get(NEW_MODE) in PLAIN_MODES
                      and said[OLD_MODE] != said[NEW_MODE]):
        return None
    if SIMILARITY in said:
        # A count of more digits than a percent has is none, and its value is never built: its length is asked first.
        alike = said[SIMILARITY][:-1]
        if not said[SIMILARITY].endswith(b"%") or len(alike) > len(ALL_ALIKE) or _number(alike) is None:
            return None
        if len(alike) == len(ALL_ALIKE) and alike != ALL_ALIKE:
            return None
    index_mode = None
    # git writes an index line for every new file and every removed one, an empty one's too.
    if (made or gone) and INDEX not in said:
        return None
    if INDEX in said:
        hashes, mode_follows, mode = said[INDEX].partition(b" ")
        before, dots, after = hashes.partition(b"..")
        if not dots or not all(c in HEX for c in before + after):
            return None
        if len(before) < len(SHORT_HASH) or len(after) < len(SHORT_HASH):
            return None
        if len(before) > len(FULL_HASH) or len(after) > len(FULL_HASH):
            return None
        # A new file's first hash is all zeros and a removed one's second: the side it has not. A name git abbreviates
        # may be all zeros too, on a side a file has.
        if (made and before.rstrip(b"0")) or (gone and after.rstrip(b"0")):
            return None
        index_mode = _mode(mode)
        # git writes a mode here where the section has no line of its own for one, and only there: a file is given one.
        if mode_follows and (index_mode is None or made or gone or moded):
            return None
        if not mode_follows and not (made or gone or moded):
            return None
    modes = {key: _mode(said[key]) for key in (OLD_MODE, NEW_MODE, DELETED, NEW_FILE) if key in said}
    if not all(mode is not None for mode in modes.values()):
        return None
    hunks = []
    kind = "new" if made else "deleted" if gone else "rename" if renamed else "copy" if copied else "change"
    if kind == "change" and not hunks and not moded:
        return None
    return {"kind": kind, "old": old, "new": new, "hunks": hunks, "index_mode": index_mode,
            "old_mode": modes.get(DELETED, modes.get(OLD_MODE)), "new_mode": modes.get(NEW_FILE, modes.get(NEW_MODE))}, i


def _apart(paths: list) -> bool:
    """Whether no path among `paths` is a directory above another, as `docs/e` is above `docs/e/x`. They are read in
    order, a file before what is below it, into one tree of their parts, where a file is None: the work is as long as
    the paths."""
    files = {}
    for path in sorted(paths):
        node, names = files, path.split("/")
        for name in names[:-1]:
            if name not in node:
                node[name] = {}
            node = node[name]
            if node is None:
                return False
        node[names[-1]] = None
    return True


def read(patch):
    """The sections of a patch as `git diff` writes it, in its order, or None where it is not one this reads: what is
    not exactly bytes, since a subclass's own methods would be read; bytes that end a line short; a line before its
    first section, or a line no section holds; a path twice, or a file where a directory is, as the module says;
    or no section at all. No hunk is read
    yet: a section with sides under it is not one this reads."""
    if type(patch) is not bytes:
        return None
    lines = patch.split(b"\n")
    if lines.pop() != b"" or not lines:
        return None
    sections, written, gone, made, i = [], {}, {}, {}, 0
    while i < len(lines):
        found = _section(lines, i) if lines[i].startswith(HEADER) else None
        if found is None:
            return None
        kind, old, new = found[0]["kind"], found[0]["old"], found[0]["new"]
        # git names a path on the new side of one section, so a type changed, a file removed and made at its path, is
        # not read; nor is a path a section renames or removes named after it, nor one it makes read, but a copy's.
        if new in written or old in gone or new in gone or old in made:
            return None
        written[new] = True
        if kind in ("rename", "deleted"):
            gone[old] = True
        if kind in ("new", "rename", "copy"):
            made[new] = True
        sections.append(found[0])
        i = found[1]
    return sections if _apart([s["new"] for s in sections if s["kind"] != "deleted"]) else None
