"""A Role's patch, read as `git diff` writes it, and its hunks applied to a file's bytes (issue 838; FR-14; decision
0188's residual, "the push's write must land exactly that patch, and no other bytes"). What applies a whole patch to a
tree is still to come.

`read(patch)` gives a patch's sections, or None for what it does not read. It reads a narrower patch than
`harness/bundle.py` does, on purpose, and what it does not read it refuses: a name is read one way only, unquoted, of
the characters `NAME_CHARS` holds, with no space, so the header alone names both files and every other line that names
one must agree with it; and of no more parts than `DEEPEST` bounds. `named(path)` is that reading of a name, for text.
A section's extended lines stand in the order git writes them, and a change of mode is a file's between its two modes.
No path is on the new side of two sections: git writes a change of a file's type as a removed file and a new one at one
path, and that is not read. A path a section renames or removes is named by no later section, on either side, and a
path a section makes, as a new file or a rename's or a copy's, is no later section's old side; a copy's source alone
may be named again, as `git diff -C` writes a copy and then a rename of one file, and a file changed in place is
copied after, never renamed. No file made stands where another needs a directory. A section's hunks are as git writes
them: in their order and apart, each new side where the hunks before it put it, each changing something, under an
index line; and a rename's or a copy's below 100% alike, and at it where lines only moved.

An index line's hashes and how alike a rename or a copy says its files are, are read for their form alone, the second
for whether it is 100% too, and nothing trusts them: what a patch lands is its hunks applied to the bytes it names,
and a section whose hashes differ but that has no hunk changes no bytes.

`sources(patch)` names the files whose bytes a patch needs, and `content(old, hunks)` applies one file's hunks to its
bytes. Nothing is searched for and nothing is guessed: a hunk's lines are the file's lines at the place the hunk names,
or the hunks are not this file's. `git apply` is looser, even with `--unidiff-zero`, and is no stand-in for this: where
a hunk's lines are not at the place its header names, git searches up and down the file and lands them where they
read alike; and it joins a new line with no newline at its end to the line that follows it. Here both are refused.
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
# The one change of mode git writes in place: a file made runnable, or no longer. A change of a file's type it writes as
# a removed file and a new one.
PLAIN_MODES = (b"100644", b"100755")
DIGITS = b"0123456789"
HEX = b"0123456789abcdef"
# A hash of more characters than this, a SHA-256 name in full, is no hash git writes; nor is one of fewer than this,
# git's shortest abbreviation.
FULL_HASH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
SHORT_HASH = "0123"
MOST_DIGITS = b"999999999"      # a count of more digits than this is no count (decision 0188)
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
NUL = b"\x00"



def _number(said):
    """A count or a line's number as git writes one, or None: digits, no more than `MOST_DIGITS` has, none led by 0."""
    if not said or len(said) > len(MOST_DIGITS) or not all(c in DIGITS for c in said):
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


def _range(said):
    """`(start, count)` from one side of a hunk's header, `start` or `start,count`, or None. git leaves a count of one
    out, and writes every other."""
    start, comma, count = said.partition(b",")
    first = _number(start)
    many = _number(count) if comma else 1
    if first is None or many is None or (comma and many == 1):
        return None
    return first, many


def _hunk(lines: list, i: int):
    """`(hunk, next line)` for the hunk whose header is line `i`, or None. Its lines are as many as its header counts,
    each a line both sides hold, one the old side holds, or one the new side holds; in a run of changed lines git
    writes the old side's first. git's marker, on a line of its own, says the line before it has no newline at its
    end: so no later line of the hunk is on that line's side, and the line it marks is not empty, since an empty line
    that ends in no newline is no line at all. The two sides differ, in a line or in a last line's newline: a hunk
    that changes nothing git does not write. After its header's second `@@` git writes nothing, or a space and the
    line the hunk stands under, which is not read but is never empty."""
    old, plus, rest = lines[i][len(HUNK):].partition(b" +")
    new, end, under = rest.partition(b" @@")
    was, now = _range(old), _range(new)
    if not plus or not end or was is None or now is None or (under and not under.startswith(b" ")) or under == b" ":
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
            # The line marked is the last of each side that holds it. A marker on a new line ends the new side, and
            # then no line follows, an old line coming before the new ones of its run: so it need not keep the old's.
            old_ended, new_ended = body[-1]["sign"] != b"+", body[-1]["sign"] != b"-"
        elif sign == b" " and old_left and new_left and not old_ended and not new_ended:
            old_left, new_left = old_left - 1, new_left - 1
            body.append({"sign": sign, "text": line[1:], "bare": False})
        elif sign == b"-" and old_left and not old_ended and not (body and body[-1]["sign"] == b"+"):
            old_left -= 1
            body.append({"sign": sign, "text": line[1:], "bare": False})
        elif sign == b"+" and new_left and not new_ended:
            new_left -= 1
            body.append({"sign": sign, "text": line[1:], "bare": False})
        else:
            return None
        i += 1
    if i < len(lines) and lines[i] == NO_NEWLINE and body and body[-1]["text"]:
        body[-1] = dict(body[-1], bare=True)
        i += 1
    if [(said["text"], said["bare"]) for said in body if said["sign"] != b"+"] \
            == [(said["text"], said["bare"]) for said in body if said["sign"] != b"-"]:
        return None
    return {"old_start": was[0], "old_count": was[1], "new_start": now[0], "new_count": now[1], "lines": body}, i


def _in_order(hunks: list) -> bool:
    """Whether a section's hunks stand where git writes them, as the patch alone says: each past the one before it,
    with a line at least between them, since git writes hunks that touch as one; a side's start 0 only where it counts
    no line; and each new side where the old side and the hunks before it put it. A count of 0 says the hunk stands
    after the line its start names, so `@@ -0,0 +1 @@` puts a line in at the top and `@@ -2,0 +3 @@` after line 2."""
    cursor, grown, stood = 0, 0, False
    for hunk in hunks:
        taken = hunk["old_count"]
        at = hunk["old_start"] - 1 if taken else hunk["old_start"]
        if at < cursor or (stood and at == cursor):
            return False
        if hunk["new_start"] != (at + grown + 1 if hunk["new_count"] else at + grown):
            return False
        cursor, grown, stood = at + taken, grown + hunk["new_count"] - taken, True
    return True


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
    # git writes an index line for every section whose bytes change, so for every one with hunks.
    if hunks and INDEX not in said:
        return None
    if not _in_order(hunks):
        return None
    # git writes a rename's or a copy's hunks where its two files differ, as they do below 100% alike. At 100% it may
    # still write them, where lines only moved: its score is rounded, and the bytes may differ.
    whole = said.get(SIMILARITY) == ALL_ALIKE + b"%"
    if (renamed or copied) and not whole and not hunks:
        return None
    # A new file has no old line and a removed one no new line, in the one hunk git writes for either: it stands at
    # line 0 of the side that has none, so, held to its place, at line 1 of the other; a second hunk would stand past 0.
    if made and any(hunk["old_start"] for hunk in hunks):
        return None
    if gone and any(hunk["new_start"] for hunk in hunks):
        return None
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
    no section at all, or a NUL, which makes a change a binary one written as text (decision 0188). A section is read
    with its hunks: each as its header counts it and in a form git writes (`_hunk`), all where they stand as far as
    the patch alone says (`_in_order`), under an index line, and a rename's or a copy's there where its files are
    less than wholly alike. Whether a hunk's lines are the file's is a question of the file it is applied to."""
    if type(patch) is not bytes or NUL in patch:
        return None
    lines = patch.split(b"\n")
    if lines.pop() != b"" or not lines:
        return None
    sections, written, gone, made, changed, i = [], {}, {}, {}, {}, 0
    while i < len(lines):
        found = _section(lines, i) if lines[i].startswith(HEADER) else None
        if found is None:
            return None
        kind, old, new = found[0]["kind"], found[0]["old"], found[0]["new"]
        # git names a path on the new side of one section, so a type changed, a file removed and made at its path, is
        # not read; nor is a path a section renames or removes named after it, nor one it makes read, but a copy's.
        if new in written or old in gone or new in gone or old in made:
            return None
        # Nor is a path changed in place moved away after: git writes a copy of a file after its change, no rename.
        if kind == "rename" and old in changed:
            return None
        written[new] = True
        if kind == "change":
            changed[new] = True
        if kind in ("rename", "deleted"):
            gone[old] = True
        if kind in ("new", "rename", "copy"):
            made[new] = True
        sections.append(found[0])
        i = found[1]
    return sections if _apart([s["new"] for s in sections if s["kind"] != "deleted"]) else None


def sources(patch):
    """The paths whose bytes the patch is applied to, each once, in its order, or None for a patch this does not read:
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
    are not this file's. Each hunk stands where its header says, and each line of its old side is the file's line
    there, byte for byte; `read` has held the hunks to their order and each new side to where the hunks before it put
    it. git's marker stands on the file's last line exactly where that line has no newline at its end, and on a new
    line only where nothing follows it: `read` gives a marker in a section's last hunk alone, and here no line of the
    file follows that hunk's. An `old` that is no bytes is no file's content, an empty one's least of all, and nor is
    a subclass of bytes, whose own methods would be read: None.
    `hunks` are `read`'s own, and no other shape is asked for."""
    if type(old) is not bytes:
        return None
    held = old.split(b"\n") if old else []
    bare = bool(old) and not old.endswith(b"\n")
    if held and not bare:
        held.pop()
    last = len(held) - 1
    out, cursor, open_end = [], 0, False
    for hunk in hunks:
        count = hunk["old_count"]
        at = hunk["old_start"] - 1 if count else hunk["old_start"]
        if at + count > len(held):
            return None
        if at > cursor:
            out += held[cursor:at]
            open_end = bare and at > last
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
        cursor = at
    if cursor < len(held):
        if open_end:
            return None
        out += held[cursor:]
        open_end = bare
    if not out:
        return b""
    return b"\n".join(out) + (b"" if open_end else b"\n")
