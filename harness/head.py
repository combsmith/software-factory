"""The head a review reads: a pull request's tree at one commit, as data, never run (decision 0138, issue 537).

`fetch(transport, repo, sha)` reads the commit's tarball through the transport's one redirect to codeload (P-60), and
`unpack(data, sha, into)` writes it into the new folder `into` by hand, member by member, with no library's extraction:
each header is read and checked before anything is written, and the whole archive is refused at the first member that
fails. A member is written only as a regular file or a directory, each inside `into`, by a name with no `..`, no absolute
path, no `.git` and no byte that is not UTF-8, named once; a link is never written, a device or a FIFO refuses the archive, and so
do more than `MEMBERS` members, more than `UNPACKED` bytes unpacked, or an end that is not two zero blocks and padding.
The archive is the commit's as git archives it, so a file the commit's .gitattributes marks export-ignore is not in it,
and one marked export-subst is not as committed (decision 0138): so `tree(transport, repo, sha)` reads the commit's tree,
and `held(into, tree)` holds the head unpacked to it, file by file, by git's blob hash (decision 0142). The archive must name the commit asked for, in the pax global
header GitHub writes (P-60), and hold one folder, which is `into` once unpacked. Nothing of a file's contents is read
but its bytes, written as they are, its user's alone; no mode, owner or time of the archive's is kept.
"""
from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
import zlib

from adapters import github

MEMBERS = 20000                 # members an archive may hold: this repo's head holds under 1,000
UNPACKED = 64 * 1024 * 1024     # bytes it may unpack to: this repo's head is under 20 MiB
BLOCK = 512
REGULAR, DIRECTORY = (b"0", b"\0"), b"5"
LINKS = (b"1", b"2")            # a hard link and a symbolic one: never written
GLOBAL, EXTENDED = b"g", b"x"   # pax headers: the archive's own, and the next member's
BLOB = re.compile(r"[0-9a-f]{40}")   # a blob's whole sha, as git names one


class Refused(Exception):
    """A head that cannot be read whole, or an archive this unpacker will not write: the Task is not built, by the code
    `head_unreadable`, and the words say which check refused it."""


def path_of(repo: str, sha: str) -> str:
    """The API's path to `repo`'s tarball at `sha`, its owner and its name each quoted whole, so that neither is ever
    read as more than one segment of the path; for a name the transport admits, quoting changes nothing."""
    owner, _, name = repo.partition("/") if isinstance(repo, str) else ("", "", "")
    return "/repos/%s/%s/tarball/%s" % (urllib.parse.quote(owner, safe=""), urllib.parse.quote(name, safe=""), sha)


def fetch(transport, repo: str, sha: str) -> bytes:
    """The gzipped tarball of `repo` at `sha`, the bytes codeload sent; Refused unless it answered them. The transport
    asks for no commit but by its whole sha in lower case, and of no repo whose owner or name is `.` or `..`."""
    try:
        answer = transport.send(github.tarball(path_of(repo, sha)))
    except github.Unanswered:
        raise Refused("the tarball could not be read") from None
    if answer.get("status") != 200 or not isinstance(answer.get("body"), str):
        raise Refused("the tarball was not answered")
    return github.raw(answer["body"])


def _octal(field: bytes) -> int:
    text = field.rstrip(b"\0 ").lstrip(b" ")
    if not text or any(c not in b"01234567" for c in text):
        raise Refused("a header's number is not octal")
    return int(text, 8)


def _checked(header: bytes) -> None:
    """The header's checksum, as tar writes it: the sum of its bytes with the checksum field read as spaces."""
    if _octal(header[148:156]) != sum(header[:148]) + 8 * 32 + sum(header[156:]):
        raise Refused("a header's checksum is not its own")


def _pax(body: bytes) -> dict:
    """A pax header's records, `LENGTH KEY=VALUE\\n` each, as text; Refused if one cannot be read."""
    found, at = {}, 0
    while at < len(body):
        space = body.find(b" ", at)
        if space < 0:
            raise Refused("a pax record cannot be read")
        length = _decimal(body[at:space])
        record = body[at:at + length]
        if length <= space - at + 1 or len(record) != length or not record.endswith(b"\n") or b"=" not in record:
            raise Refused("a pax record cannot be read")
        key, _, value = record[space - at + 1:-1].partition(b"=")
        try:
            found[key.decode("utf-8")] = value.decode("utf-8")
        except UnicodeDecodeError:
            raise Refused("a pax record is not UTF-8") from None
        at += length
    return found


def _decimal(field: bytes) -> int:
    if not field or any(c not in b"0123456789" for c in field):
        raise Refused("a pax record's length is not a number")
    return int(field)


def _name(header: bytes, extended: dict) -> str:
    """The member's name: the pax header's path, or the ustar prefix and name; Refused unless it is UTF-8."""
    if "path" in extended:
        return extended["path"]
    name, prefix = header[:100].split(b"\0", 1)[0], header[345:500].split(b"\0", 1)[0]
    if header[257:262] == b"ustar" and prefix:
        name = prefix + b"/" + name
    try:
        return name.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused("a member's name is not UTF-8") from None


def _parts(name: str, top: str) -> list:
    """The member's path inside the archive's one folder, as its parts; Refused if it names anything else."""
    if "\0" in name or "\\" in name or name.startswith("/"):
        raise Refused("a member's name is absolute, or holds a byte a path cannot")
    parts = name.rstrip("/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise Refused("a member's name climbs, or holds an empty or a dot segment")
    # Git never archives its own folder, and a head that held one would hand the model a history, a case's answer among
    # what it could hold (issue 614). Read as a case-blind file system reads it.
    if any(part.casefold() == ".git" for part in parts):
        raise Refused("a member's name holds a .git segment")
    if parts[0] != top:
        raise Refused("a member is outside the archive's one folder")
    return parts[1:]


def _place(into: str, parts: list) -> str:
    """Where a member is written: inside `into`, as its real path says, never through a link."""
    target = os.path.join(into, *parts)
    real = os.path.realpath(target)
    if real != os.path.realpath(into) and not real.startswith(os.path.realpath(into) + os.sep):
        raise Refused("a member would be written outside the head's folder")
    return target


def unpack(data: bytes, sha: str, into: str) -> dict:
    """Write the gzipped tarball `data` of commit `sha` into the new folder `into`, and say how many files, folders and
    bytes it wrote and how many links it left out; Refused at the first check that fails, `into` then holding what was
    written before it, for the caller to remove."""
    unzip = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        tar = unzip.decompress(data, UNPACKED + 1)
    except zlib.error:
        raise Refused("the tarball is not gzip") from None
    if len(tar) > UNPACKED or unzip.unconsumed_tail:
        raise Refused("the tarball unpacks to more than %d bytes" % UNPACKED)
    if not unzip.eof or unzip.unused_data:
        raise Refused("the tarball is cut short, or has bytes after its end")
    os.mkdir(into, 0o700)
    top, named, written, members = None, None, {"files": 0, "folders": 0, "bytes": 0, "links_left_out": 0}, 0
    extended = None     # the records of a pax header that waits for its member
    seen = set()
    at = 0
    while True:
        header = tar[at:at + BLOCK]
        if len(header) < BLOCK:
            raise Refused("the archive ends before its end blocks")
        if header == b"\0" * BLOCK:
            # Two end blocks, and nothing after them but the zeros a tar pads its last record with.
            if tar[at:at + 2 * BLOCK] != b"\0" * (2 * BLOCK) or tar[at:].strip(b"\0"):
                raise Refused("the archive's end is not two zero blocks and padding alone")
            # A pax header names the member after it: an archive that ends before that member is not whole.
            if extended is not None:
                raise Refused("the archive ends before the member its last pax header names")
            break
        _checked(header)
        size, kind = _octal(header[124:136]), header[156:157]
        body = tar[at + BLOCK:at + BLOCK + size]
        if len(body) < size:
            raise Refused("a member is cut short")
        at += BLOCK + (size + BLOCK - 1) // BLOCK * BLOCK
        if kind == GLOBAL:
            named = _pax(body).get("comment")
            continue
        if kind == EXTENDED:
            extended = _pax(body)
            continue
        name, extended = _name(header, extended or {}), None
        members += 1
        if members > MEMBERS:
            raise Refused("the archive holds more than %d members" % MEMBERS)
        if named != sha:
            raise Refused("the archive does not name the commit asked for")
        if top is None:
            top = name.rstrip("/")
            if kind != DIRECTORY or "/" in top or not top.endswith("-" + sha[:7]):
                raise Refused("the archive's first member is not its one folder, named for the commit")
            seen.add(())
            continue
        parts = _parts(name, top)
        # Every member is named once, a folder, a link and the one folder among them, whatever kind each is.
        if tuple(parts) in seen:
            raise Refused("a member is named twice")
        seen.add(tuple(parts))
        if kind in LINKS:
            written["links_left_out"] += 1
            continue
        if kind not in REGULAR + (DIRECTORY,):
            raise Refused("a member is a device, a FIFO or a kind this unpacker does not write")
        target = _place(into, parts)
        try:
            if kind == DIRECTORY:
                os.makedirs(target, 0o700, exist_ok=True)
                written["folders"] += 1
                continue
            os.makedirs(os.path.dirname(target), 0o700, exist_ok=True)
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except OSError:
            # A folder where a file stands, or a file under a file: no place its name can be written.
            raise Refused("a member cannot be written where its name says") from None
        written["bytes"] += size        # within UNPACKED, since the whole archive is
        with os.fdopen(fd, "wb") as out:
            out.write(body)
        written["files"] += 1
    if top is None:
        raise Refused("the archive holds no folder")
    return written


def tree_path(repo: str, sha: str) -> str:
    """The API's path to `repo`'s git tree at commit `sha`, every level of it, its owner and its name each quoted whole,
    by `path_of` itself: a quoted owner or name holds no slash, so its last `/tarball/` is the one it adds."""
    return path_of(repo, "").rsplit("/tarball/", 1)[0] + "/git/trees/%s?recursive=1" % sha


def tree(transport, repo: str, sha: str) -> dict:
    """The commit's tree, every level of it, as GitHub lists it (trials/P-60.tree.json): `{"files": {path: (blob, size)},
    "links": {path}}`, each regular file by its path with its git blob hash and size, and each link, which the unpacker
    leaves out. Refused unless answered 200 and whole, `truncated` false, in that shape, each path once; a submodule, which
    an archive does not hold, or an entry of any other kind, refuses it too (decision 0142)."""
    path = tree_path(repo, sha) if isinstance(sha, str) else ""
    if not github.TREE.fullmatch(path):
        raise Refused("a tree is read only by its commit's whole sha, of a repo named as the API names one")
    try:
        answer = transport.send(github.request("GET", path))
    except github.Unanswered:
        raise Refused("the commit's tree could not be read") from None
    if answer.get("status") != 200:
        raise Refused("the commit's tree was not answered whole")
    return tree_of(answer.get("body"))


def tree_of(body) -> dict:
    """A commit's tree, every level of it, as `tree` reads GitHub's answer, from the answer's body: so an eval case's
    tree, kept beside it in the held-out home as GitHub answered it, is read by the same checks (issue 611)."""
    if not isinstance(body, dict) or body.get("truncated") is not False or not isinstance(body.get("tree"), list):
        raise Refused("the commit's tree was not answered whole")
    files, links, seen = {}, set(), set()
    for entry in body["tree"]:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(path, str) or path in seen:
            raise Refused("an entry of the commit's tree has no path, or one named twice")
        seen.add(path)
        # One that starts with a slash has an empty first segment, and is refused by it.
        if "\0" in path or "\\" in path or any(part in ("", ".", "..") for part in path.split("/")):
            raise Refused("an entry of the commit's tree is absolute, climbs, or holds an empty or a dot segment")
        kind, mode = entry.get("type"), entry.get("mode")
        if kind == "tree" and mode == "040000":
            continue
        if kind == "blob" and mode == "120000":
            links.add(path)
            continue
        blob, size = entry.get("sha"), entry.get("size")
        if kind == "blob" and mode in ("100644", "100755") and isinstance(blob, str) and BLOB.fullmatch(blob) \
                and type(size) is int and size >= 0:
            files[path] = (blob, size)
            continue
        raise Refused("the commit's tree holds an entry this check does not read: a submodule, or another kind")
    return {"files": files, "links": links}


def held(into: str, tree_: dict) -> None:
    """Hold the head unpacked into `into` to its commit's tree: every regular file of the tree is a file there, whose git
    blob hash, sha1 of `blob <size>\\0` and its bytes, is the tree's, and no file is there that the tree lacks. A file the
    commit's .gitattributes marked export-ignore, or one export-subst, ident, eol or working-tree-encoding rewrote, is so
    caught (decisions 0138 and 0142). A link, to a file or a folder, is refused, and so is a head that is not a folder
    or holds one that cannot be listed. Refused at the first file that differs."""
    def unreadable(err):
        raise Refused("a folder of the head cannot be listed") from None
    # The head is named by its real path, as the read step names it: absolute, through no link and none itself, with no
    # empty, `.` or `..` segment and no trailing slash, so the folder checked is the folder walked.
    if os.path.realpath(into) != into or not os.path.isdir(into):
        raise Refused("the head is not a folder")
    found = {}
    for folder, folders, names in os.walk(into, onerror=unreadable):
        if any(os.path.islink(os.path.join(folder, name)) for name in folders):
            raise Refused("the head holds a link to a folder, which os.walk would not go into")
        for name in names:
            full = os.path.join(folder, name)
            if os.path.islink(full) or not os.path.isfile(full):
                raise Refused("the head holds what is not a regular file")
            found[os.path.relpath(full, into).replace(os.sep, "/")] = full
    wanted = tree_["files"]
    if set(found) != set(wanted):
        raise Refused("the head's files are not its commit's: a committed file is missing, or another is there")
    for path, full in sorted(found.items()):
        blob, size = wanted.get(path, ("", -1))
        with open(full, "rb") as f:
            data = f.read()
        # Git names a blob by sha1, and the tree gives no other name: the hash is git's, compared with git's own.
        if len(data) != size or hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest() != blob:
            raise Refused("a file of the head is not its commit's, byte for byte")
