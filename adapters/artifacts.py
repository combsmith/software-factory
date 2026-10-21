"""A Run's outcome, `outcome/1`, read from its artifact, for a Run that did not succeed and for no other (design section
3.10, decisions 0029 and 0039).

The outcome is the artifact named `outcome` the run lists, a zip of one file, `outcome.json`, a few bytes long. It is
downloaded through the transport's one redirect, to GitHub's artifact storage (decision 0045, the Maintainer's ruling on
#192), and bounded at every step: the size the listing gives, the bytes downloaded, the file's size in the zip
and the bytes read out of it. Its digest, where the listing gives one, is checked against the bytes. The file is held
to `outcome/1` and must name the Run whose artifact it is.

A Run that left no outcome, as a killed one does, is read whole with none, and so is one whose outcome is past its
retention: that is a fact, and what it means is the Kernel's (decision 0029 and design section 3.10). An outcome not yet
listed just after its Run completed reads the same, until the next pass lists it. What cannot be read, two of the name,
a zip of anything else, or a file that is not `outcome/1` of this Run, is not whole: the Kernel defers, and never reads
it as no attempt. A failed Run's file that names no fault contradicts itself, and is not whole either. The zip's file is
read only stored or deflated, the two ways whose output Python bounds as it reads.
"""
from __future__ import annotations

import hashlib
import io
import json
import pathlib
import re
import zipfile
import zlib

from adapters.github import Unanswered, download, raw, request
from tools.jsonschema_lite import validate

NAME = "outcome"           # the artifact a Run's final step uploads
MEMBER = "outcome.json"    # its one file
ZIPPED = 64 * 1024         # bytes the zip may be, as listed and as downloaded
HELD = 4 * 1024            # bytes the file may be, as the zip says and as read out of it
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
SCHEMA = json.loads((pathlib.Path(__file__).resolve().parent.parent / "schemas" / "outcome.schema.json").read_text())


def _listed(transport, repo: str, github_id: int):
    """The one artifact named `outcome` the run lists, None if it lists none, or False if the list cannot be read."""
    answer = transport.send(request("GET", "/repos/%s/actions/runs/%d/artifacts?name=%s&per_page=100"
                                    % (repo, github_id, NAME)))
    if answer["status"] != 200 or not isinstance(answer["body"], dict):
        raise Unanswered("the artifacts of run %d answered %d" % (github_id, answer["status"]))
    listed, total = answer["body"].get("artifacts"), answer["body"].get("total_count")
    if not isinstance(listed, list) or not isinstance(total, int) or isinstance(total, bool) or total != len(listed):
        return False
    named = [a for a in listed if isinstance(a, dict) and a.get("name") == NAME]
    if len(named) != len(listed) or len(named) > 1:
        return False
    return named[0] if named else None


def _member(zipped: bytes):
    """The bytes of the zip's one file, `outcome.json`, or None if the zip holds anything else or cannot be read."""
    try:
        with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
            files = archive.infolist()
            # One file, by name, stored or deflated, and no larger than the bound as the zip gives it, or it is never
            # opened. An encrypted one Python refuses to open, and a zip that under-states the file fails its check.
            if len(files) != 1 or files[0].filename != MEMBER \
                    or files[0].compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) \
                    or files[0].file_size > HELD:
                return None
            with archive.open(files[0]) as member:
                held = member.read(HELD)
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError, ValueError, NotImplementedError, RuntimeError):
        return None
    return held


def outcome(transport, repo: str, github_id: int, run: str) -> tuple:
    """`(outcome, whole)` of the Run GitHub numbers `github_id` and the Factory names `run`: the fault its outcome
    names, None for a Run that left none, and whether it was read whole."""
    found = _listed(transport, repo, github_id)
    if found is None or (found and found.get("expired") is True):
        return None, True
    ident, size, digest = (found or {}).get("id"), (found or {}).get("size_in_bytes"), (found or {}).get("digest")
    if not found or found.get("expired") is not False or not isinstance(ident, int) or isinstance(ident, bool) \
            or ident < 1 or not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= ZIPPED \
            or (digest is not None and not (isinstance(digest, str) and DIGEST.fullmatch(digest))):
        return None, False
    answer = transport.send(download("/repos/%s/actions/artifacts/%d/zip" % (repo, ident)))
    if answer["status"] != 200 or not isinstance(answer["body"], str):
        raise Unanswered("the artifact of run %d answered %d" % (github_id, answer["status"]))
    zipped = raw(answer["body"])
    if len(zipped) != size or (digest is not None and digest != "sha256:" + hashlib.sha256(zipped).hexdigest()):
        return None, False
    held = _member(zipped)
    try:
        record = json.loads(held.decode("utf-8")) if held is not None else None
    except ValueError:
        record = None
    if not isinstance(record, dict) or validate(record, SCHEMA) or record["run"] != run or record["outcome"] is None:
        return None, False
    return record["outcome"], True
