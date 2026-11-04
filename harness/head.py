"""The head a review reads: a pull request's tree at one commit, as data, never run (decision 0138, issue 537).

`fetch(transport, repo, sha)` reads the commit's tarball through the transport's one redirect to codeload (P-60), and
`unpack(data, sha, into)` writes it into the new folder `into` by hand, member by member, with no library's extraction:
each header is read and checked before anything is written, and the whole archive is refused at the first member that
fails. A member is written only as a regular file or a directory, each inside `into`, by a name with no `..`, no absolute
path and no byte that is not UTF-8; a link is never written, a device or a FIFO refuses the archive, and so do more than
`MEMBERS` members or more than `UNPACKED` bytes unpacked. The archive must name the commit asked for, in the pax global
header GitHub writes (P-60), and hold one folder, which is `into` once unpacked. Nothing of a file's contents is read
but its bytes, written as they are, its user's alone; no mode, owner or time of the archive's is kept.
"""
from __future__ import annotations

import os
import zlib

from adapters import github

MEMBERS = 20000                 # members an archive may hold: this repo's head holds under 1,000
UNPACKED = 64 * 1024 * 1024     # bytes it may unpack to: this repo's head is under 20 MiB
BLOCK = 512
REGULAR, DIRECTORY = (b"0", b"\0"), b"5"
LINKS = (b"1", b"2")            # a hard link and a symbolic one: never written
GLOBAL, EXTENDED = b"g", b"x"   # pax headers: the archive's own, and the next member's


class Refused(Exception):
    """A head that cannot be read whole, or an archive this unpacker will not write: the Task is not built, by the code
    `head_unreadable`, and the words say which check refused it."""


def fetch(transport, repo: str, sha: str) -> bytes:
    """The gzipped tarball of `repo` at `sha`, the bytes codeload sent; Refused unless it answered them. The transport
    asks for no commit but by its whole sha in lower case."""
    try:
        answer = transport.send(github.tarball("/repos/%s/tarball/%s" % (repo, sha)))
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
    top, named, written, extended, members = None, None, {"files": 0, "folders": 0, "bytes": 0, "links_left_out": 0}, {}, 0
    at = 0
    while True:
        header = tar[at:at + BLOCK]
        if len(header) < BLOCK:
            raise Refused("the archive ends before its end blocks")
        if header == b"\0" * BLOCK:
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
        name, extended = _name(header, extended), {}
        members += 1
        if members > MEMBERS:
            raise Refused("the archive holds more than %d members" % MEMBERS)
        if named != sha:
            raise Refused("the archive does not name the commit asked for")
        if top is None:
            top = name.rstrip("/")
            if kind != DIRECTORY or "/" in top or not top.endswith("-" + sha[:7]):
                raise Refused("the archive's first member is not its one folder, named for the commit")
            continue
        parts = _parts(name, top)
        if kind in LINKS:
            written["links_left_out"] += 1
            continue
        if kind not in REGULAR + (DIRECTORY,):
            raise Refused("a member is a device, a FIFO or a kind this unpacker does not write")
        target = _place(into, parts)
        if kind == DIRECTORY:
            os.makedirs(target, 0o700, exist_ok=True)
            written["folders"] += 1
            continue
        written["bytes"] += size        # within UNPACKED, since the whole archive is
        os.makedirs(os.path.dirname(target), 0o700, exist_ok=True)
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError:
            raise Refused("a member is named twice") from None
        with os.fdopen(fd, "wb") as out:
            out.write(body)
        written["files"] += 1
    if top is None:
        raise Refused("the archive holds no folder")
    return written
