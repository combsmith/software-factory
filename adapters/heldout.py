"""The held-out home's cases, read for the eval job alone (design §3.13 and §4.9, issue 309): each case a manifest names,
`GET /repos/{owner}/{repo}/contents/{role}/{id}.json`, through the one transport, with the token the job minted for the
home and nothing else. A case is handed back as the bytes its manifest hashed, or not at all, with a code that says why.

The home's owner and name are the job's environment's, never this repo's, and no refusal, code or message here names
them, a case's path or a byte of a case: what the job prints is counts and codes. A case is read from GitHub's JSON
answer for a file, base64 decoded, so that its bytes are exactly the file's and its sha256 the manifest's to compare."""
from __future__ import annotations

import base64
import hashlib
import re

from adapters.github import Unanswered, request

LARGEST = 1024 * 1024       # bytes a case may be: a facts snapshot and a diff; GitHub inlines a file's content to 1 MiB
OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
NAME = re.compile(r"[A-Za-z0-9_.-]{1,100}")
PART = re.compile(r"[a-z0-9][a-z0-9-]*")      # a Role or a case id, as eval-set/1 holds them: no dot, no slash
SHA256 = re.compile(r"[0-9a-f]{64}")


def home(owner, name) -> bool:
    """Whether the coordinates the job was given can name a repo on GitHub, and no path that climbs out of one."""
    return (isinstance(owner, str) and OWNER.fullmatch(owner) is not None and isinstance(name, str)
            and NAME.fullmatch(name) is not None and name not in (".", ".."))


def case(transport, owner: str, name: str, role: str, entry) -> tuple:
    """`(bytes, None)` for one case the manifest names, read whole and hashing to its sha256; `(None, code)` otherwise:
    `not_this_set` for an entry or a Role that cannot name a file, `not_found`, `too_large`, `hash_differs`, or
    `unanswered` for anything GitHub did not answer as a file."""
    if not (isinstance(entry, dict) and isinstance(entry.get("id"), str) and PART.fullmatch(entry["id"])
            and isinstance(entry.get("sha256"), str) and SHA256.fullmatch(entry["sha256"])
            and isinstance(role, str) and PART.fullmatch(role)):
        return None, "not_this_set"
    if not home(owner, name):
        return None, "unanswered"
    path = "%s/%s.json" % (role, entry["id"])
    try:
        answer = transport.send(request("GET", "/repos/%s/%s/contents/%s" % (owner, name, path)))
    except Unanswered:
        return None, "unanswered"
    if answer["status"] == 404:
        return None, "not_found"
    body = answer["body"]
    if answer["status"] != 200 or not isinstance(body, dict):
        return None, "unanswered"
    size = body.get("size")
    if body.get("type") != "file" or body.get("path") != path or type(size) is not int or size < 0:
        return None, "not_found"
    if size > LARGEST:
        return None, "too_large"
    content = body.get("content")
    if body.get("encoding") != "base64" or not isinstance(content, str):
        return None, "unanswered"
    try:
        data = base64.b64decode(content.replace("\n", ""), validate=True)
    except ValueError:      # binascii.Error, what bad base64 raises, is one
        return None, "unanswered"
    if len(data) != size:
        return None, "unanswered"
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        return None, "hash_differs"
    return data, None

