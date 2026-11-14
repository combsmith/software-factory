"""A Role's patch, applied byte for byte to the files it names (issue 838; FR-14; decision 0188's residual, "the push's
write must land exactly that patch, and no other bytes").

`applied(patch, tree, contents)` gives what a push writes: each path's new bytes and mode, and each path it removes, or
the one reason, a code, why nothing may land. Nothing is searched for and nothing is guessed: a hunk's lines are the
file's lines at the place the hunk names, or the patch is not this tree's. So what lands is what the patch says, of the
commit the Decision admitted, and of no other. It is what `git apply` lands of a hunk that stands where its header
says. `git apply --unidiff-zero`, which git wants for a hunk with no line of context, differs in one shape: removals
alone that end at a last line with no newline, which it takes a line higher where the line above reads alike or
differs only in white space at its end.

It reads a narrower patch than `harness/bundle.py` does, on purpose, and what it does not read it refuses:
- a name is read one way only: unquoted, of the characters `NAME_CHARS` holds, with no space, so the header alone
  names both files and every other line that names one must agree with it; and of no more parts than `DEEPEST` bounds;
- a file is a file: a link, a submodule, a path under a file, and a mode other than a file's two are refused;
- no file is written twice or copied twice, and none is written where the tree holds one the patch does not say it
  changes.

`tree` is every path the admitted commit holds that is not a directory, with its mode as git writes it; `contents` is
the bytes of each path `sources` names. Both are the port's reads (`adapters/push.py`); this reads nothing itself.
"""
from __future__ import annotations

HEADER = b"diff --git "
MINUS = b"--- "
PLUS = b"+++ "
HUNK = b"@@ -"
OLD_SIDE = b"a/"
NEW_SIDE = b"b/"
NULL = b"/dev/null"
NO_NEWLINE = b"\\ No newline at end of file"
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
# A file's two modes. A link's, 120000, and a submodule's, 160000, are no file's: such a change is a person's to push.
FILE_MODES = ("100644", "100755")
# The modes of what a tree holds that is no directory: a file's two, a link's and a submodule's.
TREE_MODES = ("100644", "100755", "120000", "160000")
DIGITS = b"0123456789"
HEX = b"0123456789abcdef"
MOST_DIGITS = b"999999999"      # a count of more digits than this is no count (decision 0188)
ALL_ALIKE = b"100"              # how alike two files are, in percent, is no more than this
# The characters a name may hold. git writes a name of these unquoted, and no other reading of one exists: no space,
# which would leave the header two readings; no quote and no backslash, which git escapes; nothing past ASCII, which
# git quotes.
NAME_CHARS = ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
              "!#$%&'()*+,-./:;<=>?@[]^_`{|}~")
# A name of more parts than this has characters is no name this reads. git has no such bound; no path of this repo's is
# near it, and what `applied` asks of a name it asks of each directory above it.
DEEPEST = "0123456789abcdef0123456789abcdef"
# git's own directory, and the head of the short name another file system gives it (`git~1`).
GIT_OWN = ".git"
GIT_SHORT = "git~"
# The modes git writes: a file's two, a link's and a submodule's. No other is a mode to it.
MODES = (b"100644", b"100755", b"120000", b"160000")
NUL = b"\x00"

UNREADABLE = "bundle_unreadable"        # no patch this reads: the Role's, as decision 0188 has it
NOT_APPLIED = "patch_does_not_apply"    # a patch, but not of the admitted commit's files
NOT_A_FILE = "push_not_a_file"          # it writes what is no file, or through one
TREE_UNREAD = "push_tree_unreadable"    # the port's reads are in no shape this reads: the Factory's, never the Role's


def _number(said):
    """A count or a line's number as git writes one, or None: digits, no more than `MOST_DIGITS` has, none led by 0."""
    if not said or len(said) > len(MOST_DIGITS) or not all(c in DIGITS for c in said):
        return None
    if len(said) > 1 and said.startswith(b"0"):
        return None
    return int(said)


def _gits(name: str) -> bool:
    """Whether a name is git's own directory to git on some file system (its `is_ntfs_dotgit`, read wider): `.git` under
    any case, with dots after it, or with a colon and anything after that; and its short name, `git~` and anything."""
    head = name.casefold().partition(":")[0].rstrip(".")
    return head == GIT_OWN or head.startswith(GIT_SHORT)


def named(path) -> bool:
    """Whether `path`, as text, is a name this reads: of the characters `NAME_CHARS` holds, of no more parts than
    `DEEPEST` has characters, and with no part that is empty, `.`, `..`, or git's own directory in any form git knows
    it by. What is no text is no name."""
    if not isinstance(path, str) or not path or not all(c in NAME_CHARS for c in path):
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


def _range(said):
    """`(start, count)` from one side of a hunk's header, `start` or `start,count`, or None."""
    start, comma, count = said.partition(b",")
    first = _number(start)
    many = _number(count) if comma else 1
    if first is None or many is None:
        return None
    return first, many


def _hunk(lines: list, i: int):
    """`(hunk, next line)` for the hunk whose header is line `i`, or None. Its lines are as many as its header counts,
    each a line both sides hold, one the old side holds, or one the new side holds, and one at least is not held by
    both. git's marker, on a line of its own, says the line before it has no newline at its end: so no later line of
    the hunk is on that line's side, and the line it marks is not empty, since an empty line that ends in no newline
    is no line at all."""
    old, plus, rest = lines[i][len(HUNK):].partition(b" +")
    new, end, _ = rest.partition(b" @@")
    was, now = _range(old), _range(new)
    if not plus or not end or was is None or now is None:
        return None
    old_left, new_left, body = was[1], now[1], []
    old_ended, new_ended = False, False     # a side is ended by git's marker on a line of it
    i += 1
    while old_left or new_left:
        if i == len(lines):
            return None
        line = lines[i]
        sign = line[:1]
        if line == NO_NEWLINE and body and body[-1]["text"] and not body[-1]["bare"]:
            body[-1] = dict(body[-1], bare=True)
            old_ended, new_ended = old_ended or body[-1]["sign"] != b"+", new_ended or body[-1]["sign"] != b"-"
        elif sign == b" " and old_left and new_left and not old_ended and not new_ended:
            old_left, new_left = old_left - 1, new_left - 1
            body.append({"sign": sign, "text": line[1:], "bare": False})
        elif sign == b"-" and old_left and not old_ended:
            old_left -= 1
            body.append({"sign": sign, "text": line[1:], "bare": False})
        elif sign == b"+" and new_left and not new_ended:
            new_left -= 1
            body.append({"sign": sign, "text": line[1:], "bare": False})
        else:
            return None
        i += 1
    if not any(line["sign"] != b" " for line in body):
        return None
    if i < len(lines) and lines[i] == NO_NEWLINE and body[-1]["text"]:
        body[-1] = dict(body[-1], bare=True)
        i += 1
    return {"old_start": was[0], "old_count": was[1], "new_start": now[0], "new_count": now[1], "lines": body}, i


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
    extended = (OLD_MODE, NEW_MODE, DELETED, NEW_FILE, SIMILARITY, RENAME_FROM, RENAME_TO, COPY_FROM, COPY_TO, INDEX)
    said = {}
    while i < len(lines):
        found = [p for p in extended if lines[i].startswith(p)]
        if not found:
            break
        if found[0] in said:
            return None
        said[found[0]] = lines[i][len(found[0]):]
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
    if moded and not (OLD_MODE in said and NEW_MODE in said and said[OLD_MODE] != said[NEW_MODE]):
        return None
    if SIMILARITY in said:
        alike = said[SIMILARITY][:-1]
        if not said[SIMILARITY].endswith(b"%") or _number(alike) is None:
            return None
        if len(alike) >= len(ALL_ALIKE) and alike != ALL_ALIKE:
            return None
    index_mode = None
    if INDEX in said:
        hashes, mode_follows, mode = said[INDEX].partition(b" ")
        before, dots, after = hashes.partition(b"..")
        if not dots or not before or not after or not all(c in HEX for c in before + after):
            return None
        index_mode = _mode(mode)
        # git writes a mode here only where the section has no line of its own for one: so a file is given one mode.
        if mode_follows and (index_mode is None or made or gone or moded):
            return None
    modes = {key: _mode(said[key]) for key in (OLD_MODE, NEW_MODE, DELETED, NEW_FILE) if key in said}
    if not all(mode is not None for mode in modes.values()):
        return None
    hunks = []
    if i < len(lines) and lines[i].startswith(MINUS):
        # The two sides name what the header names, the old side of a new file and the new side of a removed one nothing.
        if i + 1 == len(lines) or lines[i] != MINUS + (NULL if made else OLD_SIDE + raw_old) \
                or lines[i + 1] != PLUS + (NULL if gone else NEW_SIDE + raw_new):
            return None
        i += 1 + 1
        while i < len(lines) and lines[i].startswith(HUNK):
            # git's marker says a file ends at its line, so it stands in a section's last hunk and in no other.
            if hunks and any(line["bare"] for line in hunks[-1]["lines"]):
                return None
            read = _hunk(lines, i)
            if read is None:
                return None
            hunks.append(read[0])
            i = read[1]
        if not hunks:
            return None
    # A new file has no old line and a removed one no new line, in the one hunk git writes for either: it stands at
    # the first line of the side that has lines, and at no line of the side that has none.
    if (made or gone) and len(hunks) > 1:
        return None
    if made and any((hunk["old_start"], hunk["old_count"], hunk["new_start"]) != (0, 0, 1) for hunk in hunks):
        return None
    if gone and any((hunk["new_start"], hunk["new_count"], hunk["old_start"]) != (0, 0, 1) for hunk in hunks):
        return None
    kind = "new" if made else "deleted" if gone else "rename" if renamed else "copy" if copied else "change"
    if kind == "change" and not hunks and not moded:
        return None
    return {"kind": kind, "old": old, "new": new, "hunks": hunks, "index_mode": index_mode,
            "old_mode": modes.get(DELETED, modes.get(OLD_MODE)), "new_mode": modes.get(NEW_FILE, modes.get(NEW_MODE))}, i


def read(patch):
    """The sections of a patch as `git diff` writes it, in its order, or None where it is not one this reads: bytes that
    end a line short, a line before its first section, a line no section holds, no section at all, or a NUL, which
    makes a change a binary one written as text (decision 0188). Where a hunk stands is not asked here: a hunk at
    line 0 that holds lines, and hunks out of their order, are read; that is asked where they are applied."""
    if not isinstance(patch, bytes) or NUL in patch:
        return None
    lines = patch.split(b"\n")
    if lines.pop() != b"" or not lines:
        return None
    sections, i = [], 0
    while i < len(lines):
        found = _section(lines, i) if lines[i].startswith(HEADER) else None
        if found is None:
            return None
        sections.append(found[0])
        i = found[1]
    return sections


def sources(patch):
    """The paths whose bytes `applied` needs, each once, in the patch's order, or None for a patch this does not read:
    every file a section changes, removes, renames or copies. A new file has none."""
    sections = read(patch)
    if sections is None:
        return None
    out, named = [], {}
    for section in sections:
        if section["kind"] != "new" and section["old"] not in named:
            named[section["old"]] = True
            out.append(section["old"])
    return out


def content(old: bytes, hunks: list):
    """The bytes a file holds once `hunks`, a section's as `read` gives them, are applied to `old`, or None where they
    are not this file's. Each hunk stands where its header says, past the one before it with a line at least between
    them, as git writes two hunks; each line of its old side is the file's line there, byte for byte; and where the
    new side begins is where this puts it. git's marker stands on the file's last line exactly where that line has no
    newline at its end, and on a new line only where nothing follows it: `read` gives a marker in a section's last
    hunk alone, and here no line of the file follows that hunk's. An `old` that is no bytes is no file's content, an
    empty one's least of all: None. `hunks` are `read`'s own, and no other shape is asked for."""
    if not isinstance(old, bytes):
        return None
    held = old.split(b"\n") if old else []
    bare = bool(held) and held[-1] != b""
    if held and not bare:
        held.pop()
    last = len(held) - 1
    out, cursor, open_end, stood = [], 0, False, False
    for hunk in hunks:
        count = hunk["old_count"]
        at = hunk["old_start"] - 1 if count else hunk["old_start"]
        if at < cursor or (stood and at == cursor) or at + count > len(held):
            return None
        if at > cursor:
            out += held[cursor:at]
            open_end = bare and at > last
        if hunk["new_start"] != (len(out) + 1 if hunk["new_count"] else len(out)):
            return None
        for line in hunk["lines"]:
            if line["sign"] != b"+":
                if held[at] != line["text"] or line["bare"] != (bare and at == last):
                    return None
                at += 1
            if line["sign"] != b"-":
                if open_end:
                    return None
                out.append(line["text"])
                open_end = line["bare"]
        cursor, stood = at, True
    if cursor < len(held):
        if open_end:
            return None
        out += held[cursor:]
        open_end = bare
    if not out:
        return b""
    return b"\n".join(out) + (b"" if open_end else b"\n")


def _above(path: str) -> list:
    """Each directory `path` stands under, the nearest last."""
    names = path.split("/")
    return ["/".join(names[:n]) for n in range(1, len(names))]


def _placed(path: str, tree: dict, folders: dict) -> bool:
    """Whether `path` can be a file in `tree`, whose directories are `folders`: nothing above it is a file, and it is no
    directory there."""
    return not any(part in tree for part in _above(path)) and path not in folders


def applied(patch, tree: dict, contents: dict) -> tuple:
    """`(changes, None)`, or `(None, reason)` where nothing may land. `changes` is `{"written": {path: (mode, bytes)},
    "removed": [path], "read": [path]}`: what the push writes, what it removes, and what a rename or a copy read, which
    `harness/apply.py`'s `push_refusal` is asked about as it is about what is written. A tree or contents in no shape a
    port gives, and a file the tree holds whose bytes it did not hand over, are the Factory's fault, under its own
    code; every other reason is the Role's."""
    if not isinstance(tree, dict) or not isinstance(contents, dict):
        return None, TREE_UNREAD
    if not all(isinstance(path, str) and tree[path] in TREE_MODES for path in tree):
        return None, TREE_UNREAD
    sections = read(patch)
    if sections is None:
        return None, UNREADABLE
    folders = {}
    for path in tree:
        for part in _above(path):
            folders[part] = True
    written, removed, gone, taken, copied = {}, [], {}, [], {}
    for section in sections:
        kind, old, new = section["kind"], section["old"], section["new"]
        target = old if kind == "deleted" else new
        if target in written or target in gone or (kind == "rename" and (old in written or old in gone)):
            return None, UNREADABLE
        # A copy writes a file's bytes again: one copy of a file to a patch, so what lands is bounded by what was read.
        if kind == "copy" and old in copied:
            return None, UNREADABLE
        if kind == "new":
            before, mode = b"", section["new_mode"]
            if new in tree:
                return None, NOT_APPLIED
        else:
            before, mode = contents.get(old), tree.get(old)
            if mode is None:
                return None, NOT_APPLIED
            if mode not in FILE_MODES:
                return None, NOT_A_FILE
            if not isinstance(before, bytes):
                return None, TREE_UNREAD
            if section["old_mode"] not in (None, mode) or section["index_mode"] not in (None, mode):
                return None, NOT_APPLIED
            if kind in ("rename", "copy") and new in tree:
                return None, NOT_APPLIED
            mode = section["new_mode"] or mode
        if mode not in FILE_MODES:
            return None, NOT_A_FILE
        # A section of no hunk leaves the bytes as they are: the same bytes, not a copy of them.
        after = content(before, section["hunks"]) if section["hunks"] else before
        if after is None or (kind == "deleted" and after != b""):
            return None, NOT_APPLIED
        if kind in ("deleted", "rename"):
            removed.append(old)
            gone[old] = True
        if kind == "deleted":
            continue
        if not _placed(new, tree, folders):
            return None, NOT_A_FILE
        written[new] = (mode, after)
        if kind in ("rename", "copy"):
            taken.append(old)
        if kind == "copy":
            copied[old] = True
    if any(part in written for path in written for part in _above(path)):
        return None, NOT_A_FILE
    return {"written": written, "removed": removed, "read": taken}, None
