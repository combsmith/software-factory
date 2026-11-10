"""What a Role's push hands over, held before anything lands (issue 139): the bundle, fetched by the artifact its push
Effect names and taken only by the digest it names; every name the bundle writes or reads, read from the bundle itself,
never from what the Result says of it; and the base's list (`adapters/rules.py`), held against those names by
`harness/apply.py`'s `push_refusal`. `apply` asks `held` before it mints any token, so a push refused writes nothing.

The bundle is a patch as `git diff` writes it: one `diff --git` section to a file, its extended headers, then its hunks,
and nothing else. A binary change has no hunks a person can read, and makes the bundle unreadable: such a change is a
person's to push. Every name a section carries is read, the header's, a rename's or a
copy's two, and the `---` and `+++` sides, since any of them may be what `git apply` writes; a line this reading does not
know, or a hunk whose lines are not the count its header gives, makes the bundle unreadable, never fewer names. How
`run` hands the bundle over is "Design: a Run with tools cannot both hide the model credential and hold writes" (issue
314)'s to choose: `fetch_bundle` is the one function that choice fills, and until then it fetches nothing."""
from __future__ import annotations

import hashlib
import re

from adapters import rules
from adapters.github import Unanswered
from harness import apply

HEADER = b"diff --git "
# The extended header lines `git apply` reads after a section's header, and those of them that name a path.
EXTENDED = (b"old mode ", b"new mode ", b"deleted file mode ", b"new file mode ", b"similarity index ",
            b"dissimilarity index ", b"index ")
NAMING = (b"copy from ", b"copy to ", b"rename from ", b"rename to ", b"rename old ", b"rename new ")
HUNK = re.compile(rb"@@ -[0-9]+(?:,([0-9]+))? \+[0-9]+(?:,([0-9]+))? @@.*", re.S)
# A name git quoted: between double quotes, a character it escapes as C does, and a byte past ASCII as three octal digits.
QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')
ESCAPED = re.compile(r"\\([0-7]{3}|[abtnvfr\"\\])")
ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}


class Unfetched(Exception):
    """The bundle could not be fetched: the Factory's, never the Role's."""


def fetch_bundle(artifact: str, digest: str) -> bytes:
    """The bundle `run` handed over, by its artifact: issue 314's choice fills this. Until then no Run hands one over."""
    raise Unfetched("no Run hands over a bundle yet (issue 314)")


def _name(said: bytes):
    """A path from a name as git writes it, quoted or not, or None where it cannot be read."""
    try:
        text = said.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if text.startswith('"'):
        quoted = QUOTED.fullmatch(text)
        if not quoted:
            return None
        try:
            text = ESCAPED.sub(lambda m: chr(int(m.group(1), 8) if len(m.group(1)) == 3 else ESCAPES[m.group(1)]),
                               quoted.group(1)).encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return None
    return text if text else None


def _side(said: bytes, prefix: str):
    """A `---` or `+++` line's path, `/dev/null` as no path, as `(read, name)`."""
    if said.endswith(b"\t"):        # git ends a name that holds a space with a tab
        said = said[:-1]
    if said == b"/dev/null":
        return True, None
    name = _name(said)
    if name is None or not name.startswith(prefix) or len(name) == len(prefix):
        return False, None
    return True, name[len(prefix):]


def _header(rest: bytes):
    """The two names of a `diff --git` header, or None where they cannot be told apart: a rename's names that hold a
    space, which the section's `rename` lines name again."""
    try:
        text = rest.decode("utf-8")
    except UnicodeDecodeError:
        return None
    pairs = []
    if text.startswith('"'):
        first = QUOTED.match(text)
        if first and text[first.end():first.end() + 1] == " ":
            pairs.append((text[:first.end()], text[first.end() + 1:]))
    elif text.endswith('"'):
        at = text.rfind(' "')
        if at > 0:
            pairs.append((text[:at], text[at + 1:]))
    elif text.count(" ") == 1:
        pairs.append(tuple(text.split(" ")))
    elif (len(text) - 1) % 2 == 0 and text[(len(text) - 1) // 2] == " ":
        half = (len(text) - 1) // 2
        if text[2:half] == text[half + 3:]:         # "a/" + name + " b/" + name
            pairs.append((text[:half], text[half + 1:]))
    for old, new in pairs:
        a, b = _name(old.encode()), _name(new.encode())
        if a and b and a.startswith("a/") and b.startswith("b/") and len(a) > 2 and len(b) > 2:
            return [a[2:], b[2:]]
    return None


def names(patch) -> tuple:
    """`(written, read)`: every name the patch writes, and every name it reads that it does not write, a rename's or a
    copy's source among them, each once; or None where it cannot be read as `git diff` writes a patch of text."""
    if not isinstance(patch, bytes) or not patch.endswith(b"\n"):
        return None
    lines, i = patch[:-1].split(b"\n"), 0
    written, read = [], []
    while i < len(lines):
        if not lines[i].startswith(HEADER):
            return None
        header = _header(lines[i][len(HEADER):])
        olds, news = ([header[0]], [header[1]]) if header else ([], [])
        i += 1
        while i < len(lines) and lines[i].startswith(EXTENDED + NAMING):
            line = lines[i]
            for word in NAMING:
                if line.startswith(word):
                    name = _name(line[len(word):])
                    if name is None:
                        return None
                    (olds if word in (b"copy from ", b"rename from ", b"rename old ") else news).append(name)
            i += 1
        if i < len(lines) and lines[i].startswith(b"--- "):
            if i + 1 >= len(lines) or not lines[i + 1].startswith(b"+++ "):
                return None
            (got_old, old), (got_new, new) = _side(lines[i][4:], "a/"), _side(lines[i + 1][4:], "b/")
            if not got_old or not got_new:
                return None
            olds += [old] if old else []
            news += [new] if new else []
            i += 2
            if i >= len(lines) or not lines[i].startswith(b"@@ "):
                return None
            while i < len(lines) and lines[i].startswith(b"@@ "):
                counts = HUNK.fullmatch(lines[i])
                if not counts:
                    return None
                old_left, new_left = (int(c) if c is not None else 1 for c in counts.groups())
                i += 1
                while old_left or new_left:
                    mark = lines[i][:1] if i < len(lines) else b""
                    if mark in (b" ", b"-"):
                        old_left -= 1
                    if mark in (b" ", b"+"):
                        new_left -= 1
                    if mark not in (b" ", b"-", b"+", b"\\"):
                        return None
                    i += 1
                if i < len(lines) and lines[i].startswith(b"\\"):      # no newline at the end of the last line
                    i += 1
        if not olds and not news:
            return None
        for name in news:
            if name not in written:
                written.append(name)
        for name in olds:
            if name not in written and name not in read:
                read.append(name)
    read = [name for name in read if name not in written]
    return (written, read) if written or read else None


def held(effects: dict, base: str, transport, repo: str, fetch=fetch_bundle):
    """`(fault, reason)` why a Result's push may not land, or None for one that asks for none or that touches nothing on
    the base's list. `base` is the pull request's base commit from its trusted read, and `transport` the token `apply`
    reads with. The list is read once, before any bundle is fetched: one that cannot be read refuses every push, the
    Factory's. A bundle that cannot be fetched is the Factory's; one whose bytes are not the digest the push names, or
    that is no patch this reads, is the Role's, so that no item can pause the Factory through what its Run hands over."""
    pushes = effects.get("push_commits") or ()
    if not pushes:
        return None
    listed, why = rules.listed_at(transport, repo, base)
    if why is not None:
        return "environment", why
    for push in pushes:
        bundle = push["bundle"]
        try:
            data = fetch(bundle["artifact"], bundle["digest"])
        except (Unfetched, Unanswered, OSError, ValueError):
            return "environment", "bundle_unfetched"
        if not isinstance(data, bytes) or bundle["digest"] != "sha256:" + hashlib.sha256(data).hexdigest():
            return "item", "bundle_digest_differs"
        said = names(data)
        if said is None:
            return "item", "bundle_unreadable"
        refused = apply.push_refusal(said[0], said[1], listed)
        if refused is not None:
            return ("environment" if refused == rules.UNREADABLE else "item"), refused
    return None
