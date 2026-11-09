"""What the release step sent through its token, and what GitHub answered, kept for its run (issue 531).

The step's exchanges become an artifact of a public repo, which anyone signed in may download, so what is kept is held
to lists, and anything not on them is left out. `Recording` wraps the step's one transport and passes every request
through unchanged; for each it keeps the call, its Accept and the headers `tools/check_trials.py`'s `HEADERS` lets a
trial's fixture keep but `location`, a redirect's address, and of a JSON body only the fields `FIELDS` names, at any
depth. The token is never among them:
`Live` adds it below the request it is given, and `authorization` is no header a fixture keeps. A body that is not JSON,
an artifact's download, whose one redirect names a signed address, and a file read at a commit, whose text may be the
eval set's own, are kept as their size and their sha256 alone. Then `tools/redact_trial.py` takes out anything shaped
like a credential, as it does from a trial's capture, and says where.

`write` puts it in the folder it is given, as NAME, a `release-exchanges/1`; nothing here prints it. Nothing kept may change what
the step does: a fault in the keeping drops that exchange, and is counted.
"""
from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import re

from tools import redact_trial
from tools.check_trials import HEADERS

AS = {"kind": "app", "name": "release"}
NAME = "release-exchanges.json"      # the one file it writes, which the workflow uploads
# The fields of a JSON body the step's reads and writes are judged by, at any depth, and none else: the refs and the
# writes (ref, object, sha, type, force), the comparison with main, the check runs and workflow runs of verify and the
# eval job, an artifact's listing, a Deployment and its status, and an error's message.
FIELDS = frozenset({
    "ref", "object", "sha", "type", "force",
    "status", "ahead_by", "behind_by", "total_commits", "merge_base_commit", "base_commit",
    "total_count", "check_runs", "check_suite", "app", "slug", "name", "conclusion", "head_sha", "started_at",
    "completed_at", "id", "workflow_runs", "path", "event", "run_attempt", "created_at", "updated_at", "check_suite_id",
    "artifacts", "size_in_bytes", "expired", "workflow_run",
    "environment", "task", "description", "state", "auto_merge", "required_contexts", "transient_environment",
    "production_environment",
    "message", "documentation_url",
})
# The headers kept: those a trial's fixture keeps, but a redirect's address, which can carry a signature.
KEPT_HEADERS = frozenset(HEADERS) - {"location"}
# A read whose body is a file's text at a commit, kept as its size and hash alone.
OPAQUE = re.compile(r"/repos/[^/]+/[^/]+/contents/")


def _measured(body) -> dict:
    """A body by its size and its sha256, never its text: a text body as the bytes the transport gave it; a file read at
    a commit, which GitHub answers as JSON holding it in base64, as the file's own bytes, so that it can be held to
    the file at that commit; any other JSON as its fields serialized in order."""
    if isinstance(body, str):
        raw = body.encode("utf-8", errors="surrogateescape")
    elif isinstance(body, dict) and body.get("encoding") == "base64" and isinstance(body.get("content"), str):
        raw = base64.b64decode(body["content"])
    else:
        raw = json.dumps(body, sort_keys=True).encode("utf-8")
    return {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


GONE = object()      # what _listed leaves out of a list


def _listed(value, dropped: list, where: str = "body", named: bool = False):
    """`value` with only the fields FIELDS names, at any depth: a text, a number or a truth is kept only under such a
    field, never alone or in a list no field names. Each place left out is added to `dropped`, by the name of the field
    left out where that name is a plain identifier, and never by a name that could be text."""
    if isinstance(value, dict):
        kept = {}
        for key, item in value.items():
            if key in FIELDS:
                kept[key] = _listed(item, dropped, "%s.%s" % (where, key), True)
            else:
                dropped.append("%s.%s" % (where, key) if key.isidentifier() else where + ".?")
        return kept
    if isinstance(value, list):
        items = [_listed(item, dropped, "%s[%d]" % (where, i), named) for i, item in enumerate(value)]
        return [item for item in items if item is not GONE]
    if value is None or named:
        return value
    dropped.append(where)
    return GONE


def _body(value, dropped: list, where: str):
    """A JSON body as _listed keeps it; a bare value it leaves out is null."""
    kept = _listed(value, dropped, where)
    return None if kept is GONE else kept


def _headers(given) -> dict:
    return {name.strip().lower(): value for name, value in (given or {}).items()
            if isinstance(name, str) and name.strip().lower() in KEPT_HEADERS and isinstance(value, str)}


def _opaque(req: dict) -> bool:
    return bool(req.get("follow")) or bool(OPAQUE.match(req.get("path", "")))


class Recording:
    """The transport `inner`, which keeps each exchange it sends as the module says."""

    def __init__(self, inner):
        self.inner, self.exchanges, self.dropped, self.unkept = inner, [], [], 0

    def send(self, req: dict) -> dict:
        try:
            answer = self.inner.send(req)
        except Exception as err:
            self._keep(req, None, type(err).__name__)
            raise
        self._keep(req, answer, None)
        return answer

    def _keep(self, req: dict, answer, raised) -> None:
        try:
            here, gone = "exchanges[%d]" % len(self.exchanges), []      # what is left out, named once it is kept
            headers = _headers(req.get("headers"))
            if isinstance(req.get("accept"), str):
                headers["accept"] = req["accept"]
            sent = {"as": AS, "via": "rest", "call": "%s %s" % (req["method"], req["path"]), "headers": headers,
                    "body": _body(req.get("body"), gone, here + ".request.body")}
            if answer is None:
                self.exchanges.append({"request": sent, "response": {"raised": raised}})
                self.dropped += gone
                return
            body = answer.get("body")
            if _opaque(req) or not isinstance(body, (dict, list, type(None))):
                kept = {"status": answer.get("status"), "headers": _headers(answer.get("headers"))}
                if body is not None:        # an answer with no body has nothing to measure
                    kept["measured"] = _measured(body)
            else:
                kept = {"status": answer.get("status"), "headers": _headers(answer.get("headers")),
                        "body": _body(body, gone, here + ".response.body")}
            self.exchanges.append({"request": sent, "response": kept})
            self.dropped += gone
        except Exception:      # what cannot be kept is left out, and counted; the step goes on as it would
            self.unkept += 1

    def kept(self) -> dict:
        """What `write` writes, each credential-shaped string in it, a dropped field's name among them, taken out by the
        trials' redaction."""
        return redact_trial.redact_json({"schema": "release-exchanges/1", "exchanges": self.exchanges, "removed": [],
                                         "dropped": list(self.dropped), "unkept": self.unkept}, [])

    def write(self, folder) -> bool:
        """Write `kept()` as NAME in `folder`, or nothing: True when written. It never raises, so it never changes the
        step's outcome or what it prints. The folder is the one the workflow names: absolute and standing; a NAME there
        already is never written over, as `open`'s "x" refuses it."""
        try:
            where = pathlib.Path(folder)
            if not where.is_absolute() or not where.is_dir():
                return False
            text = json.dumps(self.kept(), indent=1, sort_keys=True)
            with open(where / NAME, "x", encoding="utf-8") as out:
                out.write(text + "\n")
            return True
        except Exception:
            return False
