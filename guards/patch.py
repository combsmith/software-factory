"""A Role's patch, applied byte for byte to the files it names (issue 838; FR-14; decision 0188's residual, "the push's
write must land exactly that patch, and no other bytes").

`applied(patch, tree, contents)` gives what a push writes: each path's new bytes and mode, and each path it removes, or
the one reason, a code, why nothing may land. Nothing is searched for and nothing is guessed: a hunk's lines are the
file's lines at the place the hunk names, or the patch is not this tree's. So what lands is what the patch says, of the
commit the Decision admitted, and of no other. `git apply` is looser, even with `--unidiff-zero`, and is no stand-in
for this: where a hunk's lines are not at the place its header names, git searches up and down the file and lands them
where they read alike; and it joins a new line with no newline at its end to the line that follows it. Here both are
refused.

It reads a narrower patch than `harness/bundle.py` does, on purpose, and what it does not read it refuses:
- a name is read one way only: unquoted, of the characters `NAME_CHARS` holds, with no space, so the header alone
  names both files and every other line that names one must agree with it; and of no more parts than `DEEPEST` bounds;
- a file is a file: a link, a submodule, a path under a file, and a mode other than a file's two are refused; where a
  file stands is asked of the tree the push leaves, so a file removed or moved away leaves its place;
- no file is written where it, or a directory above it, differs by case or canonical form alone from another path
  the push leaves, as macOS reads names (`_folded`);
- no file is written twice or copied twice, and none is written where the tree holds one the patch does not say it
  changes;
- a section's extended lines stand in the order git writes them, and a change of mode is a file's between its two
  modes;
- a section's hunks are as git writes them: in their order and apart, each new side where the hunks before it put
  it, each changing something, under an index line; and a rename's or a copy's below 100% alike, and at it where lines only moved;
- no path is on the new side of two sections: git writes a change of a file's type as a removed file and a new one at
  one path, and that is not read. A path a section renames or removes is named by no later section, on either side,
  and a path a section makes, as a new file or a rename's or a copy's, is no later section's old side; a copy's source
  alone may be named again, as `git diff -C` writes a copy and then a rename of one file, and a file changed in place
  is copied after, never renamed. No file made stands where another needs a directory.

An index line's hashes and how alike a rename or a copy says its files are, are read for their form alone, the second
for whether it is 100% too, and nothing trusts them: what a patch lands is its hunks applied to the bytes it names,
and a section whose hashes differ but that has no hunk changes no bytes.

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
# The one change of mode git writes in place: a file made runnable, or no longer. A change of a file's type it writes as
# a removed file and a new one.
PLAIN_MODES = (b"100644", b"100755")
# A file's two modes. A link's, 120000, and a submodule's, 160000, are no file's: such a change is a person's to push.
FILE_MODES = ("100644", "100755")
# The modes of what a tree holds that is no directory: a file's two, a link's and a submodule's.
TREE_MODES = ("100644", "100755", "120000", "160000")
# A submodule's mode: what it names is a commit of another repository, with no bytes here to read.
SUBMODULE = "160000"
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

UNREADABLE = "bundle_unreadable"        # no patch this reads: the Role's, as decision 0188 has it
NOT_APPLIED = "patch_does_not_apply"    # a patch, but not of the admitted commit's files
NOT_A_FILE = "push_not_a_file"          # it writes what is no file, or through one
PATH_TWIN = "push_path_collision"      # it writes a path another it leaves differs from by case or form alone
TREE_UNREAD = "push_tree_unreadable"    # the port's reads are in no shape this reads: the Factory's, never the Role's


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


# The two characters whose canonical decomposition is one of `NAME_CHARS`, though case folding leaves them as they are.
# No other character's decomposition, folded in case and decomposed again, is ASCII where its case folding is not.
CANONICAL = (("\u037e", ";"), ("\u1fef", "`"))


def _folded(name: str) -> str:
    """`name` as a file system that ignores case and canonical form reads it, as macOS's does: decomposed, folded in
    case, and decomposed again. guards/ imports nothing, so no table of decompositions is at hand. But every name a
    patch writes, and each directory above it, is of `NAME_CHARS`, which are ASCII, and two names are one only where
    both fold to it. So it is enough to fold each name exactly where its fold is ASCII: case folding, and the two
    characters `CANONICAL` holds, do that. A test reads every character against the real fold."""
    folded = name.casefold()
    for form, plain in CANONICAL:
        folded = plain.join(folded.split(form))
    return folded


def _above(path: str) -> list:
    """Each directory `path` stands under, the nearest last."""
    names = path.split("/")
    return ["/".join(names[:n]) for n in range(1, len(names))]


def _placed(path: str, tree: dict, folders: dict) -> bool:
    """Whether `path` can be a file in `tree`, whose directories are `folders`: nothing above it is a file, and it is no
    directory there."""
    return not any(part in tree for part in _above(path)) and path not in folders


def _handed(tree, contents) -> bool:
    """Whether `tree` and `contents` are in a shape a port gives. A tree is a mapping of paths, as text, to the modes
    git writes of what is no directory. No path of it has more parts than `DEEPEST` has characters, as no name this
    reads has; nor an empty part, a `.` or `..` part, git's own directory in any case, or a NUL, which git holds in no
    tree; and none is a directory to another. Contents are a mapping of paths the tree holds, none a submodule, to
    bytes. Each is of its type exactly: a subclass of
    `dict`, `str` or `bytes` would be read by its own methods. Each pair is read as it stands, and no key is looked up
    until every key is known to be plain text, since a lookup compares keys."""
    if type(tree) is not dict or type(contents) is not dict:
        return False
    if not all(type(path) is str and type(mode) is str and mode in TREE_MODES for path, mode in tree.items()):
        return False
    # A bound on depth, asked before a path is split, bounds what is built of each path here and in `_above`.
    if not all(path.count("/") < len(DEEPEST) for path in tree):
        return False
    if not all(all(part not in ("", ".", "..") and part.casefold() != GIT_OWN for part in path.split("/"))
               and str(NUL, "ascii") not in path for path in tree):
        return False
    if not all(type(path) is str and type(said) is bytes for path, said in contents.items()):
        return False
    if not all(path in tree and tree[path] != SUBMODULE for path in contents):
        return False
    return not any(part in tree for path in tree for part in _above(path))


def applied(patch, tree: dict, contents: dict) -> tuple:
    """`(changes, None)`, or `(None, reason)` where nothing may land. `changes` is `{"written": {path: (mode, bytes)},
    "removed": [path], "read": [path]}`: what the push writes, what it removes, and what a rename or a copy read, each
    path once; `harness/apply.py`'s `push_refusal` is asked about what was read as it is about what is written.
    A tree or contents in no shape a port gives, and a file the tree holds whose bytes it did not hand over, are the
    Factory's fault, under its own code; every other reason is the Role's."""
    if not _handed(tree, contents):
        return None, TREE_UNREAD
    sections = read(patch)
    if sections is None:
        return None, UNREADABLE
    # A file the patch reads, of the tree, whose bytes were not handed over is the Factory's, whatever else is wrong
    # with the patch, and in whatever order its sections stand.
    if any(tree.get(s["old"]) in FILE_MODES and s["old"] not in contents for s in sections if s["kind"] != "new"):
        return None, TREE_UNREAD
    written, removed, taken, copied = {}, [], {}, {}
    for section in sections:
        kind, old, new = section["kind"], section["old"], section["new"]
        # A copy writes a file's bytes again: one copy of a file to a patch, so what lands is bounded by what was read.
        if kind == "copy" and old in copied:
            return None, UNREADABLE
        if kind == "new":
            before, mode = b"", section["new_mode"]
            if new in tree:
                return None, NOT_APPLIED
        else:
            mode = tree.get(old)
            if mode is None:
                return None, NOT_APPLIED
            if mode not in FILE_MODES:
                return None, NOT_A_FILE
            before = contents[old]
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
        if kind == "deleted":
            continue
        written[new] = (mode, after)
        if kind in ("rename", "copy"):
            taken[old] = True
        if kind == "copy":
            copied[old] = True
    # Where a file may stand is asked of the tree the push leaves: a file removed or moved away leaves its place, as
    # git writes a file made where one was removed, and a directory whose every file left is no directory.
    gone = {path: True for path in removed}
    left = {path: mode for path, mode in tree.items() if path not in gone}
    folders = {}
    for path in left:
        for part in _above(path):
            folders[part] = True
    for path in written:
        if not _placed(path, left, folders):
            return None, NOT_A_FILE
    # Nor may a file written, or a directory above it, differ by case or canonical form alone from another path or
    # directory the push leaves: where those are not told apart, as on macOS's default file system, git checks both
    # out as one. A file renamed to its own name in another case leaves its old name, and lands.
    cases, twins = {}, {}
    for path in list(left) + list(written):
        for name in _above(path) + [path]:
            if cases.get(_folded(name), name) != name:
                twins[_folded(name)] = True
            cases[_folded(name)] = name
    for path in written:
        if any(_folded(name) in twins for name in _above(path) + [path]):
            return None, PATH_TWIN
    return {"written": written, "removed": removed, "read": list(taken)}, None
