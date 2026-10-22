"""The effects port: the Controller's writes, sent through the transport, each through the one credential its type
names and nothing else (design sections 3.6 and 4.9; #193's rulings for PR 2, posted 2026-10-21).

`apply` takes the pass's plan, `writes/1`, and the pass record it was planned from, and returns `written/1`: what each
write did, as read back. Before anything is sent the plan is held to the record: the same pass and Release, ids in
order, and each dispatch a Run the record minted, for an admission or an approval on the same item and content, under
the run-name the record's Decision gives it. A plan that is not the record's is refused whole, and nothing is sent
(I-22).

A dispatch is the pass job's own token's (`WORKFLOW_TOKEN`), whose account the records port counts a Run by (P-9;
#196's ruling 10). Its transport may send nothing but a dispatch of the three workflow files the configuration names,
on its home repo. While the configuration names no account for that token, no Run or approval is dispatched: the
records port could not count it, and the ceilings would not see it (I-34). GitHub answers a dispatch 204 with no run,
so it is `sent`, never `applied`: the next pass's records port reads it back by its run-name. A dispatch is sent once
and never retried, whatever it answers: one GitHub did not answer may still have started a run, and a second would
start a second under the same Run id. A 401 or 403 ends every later write on that credential. An act no write serves
yet is recorded `not_built` and raises nothing.

`python3 -m adapters.effects PASS WRITES OUT` is the step: it reads the pass record and the plan, sends the writes
through a live transport, writes `written.json` to `OUT`, and exits non-zero when a write failed or was refused for
any reason but `not_built`, so that the pass's run concludes where the Maintainer sees it.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

from adapters import records
from adapters.github import Live, Unanswered, request
from kernel import terms as t
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = {p.name[: -len(".schema.json")]: json.loads(p.read_text())
           for p in sorted((ROOT / "schemas").glob("*.schema.json"))}
DISPATCHES = {"dispatch_run": "run", "dispatch_approval": "approval", "dispatch_successor": "poller"}
REFUSED = {401, 403}


class Refused(ValueError):
    """A plan that is not the record's: nothing is sent."""


class Allowed:
    """A transport that sends only the requests one credential may make, each by its method and path; any other is
    refused before it leaves."""

    def __init__(self, transport, permits):
        self._transport, self._permits = transport, set(permits)

    def send(self, req: dict) -> dict:
        if (req.get("method"), req.get("path")) not in self._permits or req.get("follow"):
            raise Unanswered("a write this credential may not send")
        return self._transport.send(req)


def dispatch_path(config: dict, kind: str) -> str:
    return "/repos/%s/actions/workflows/%s/dispatches" % (config["home"]["repo"], config["workflows"][kind])


def workflow_permits(config: dict) -> list:
    """The requests the pass job's own token may send: a dispatch of each of the three files, and nothing else."""
    return [("POST", dispatch_path(config, kind)) for kind in ("run", "approval", "poller")]


def _held(writes: dict, record: dict) -> None:
    """Refuse a plan that is not the record's (I-22)."""
    problems = validate(writes, SCHEMAS["writes"], schemas=SCHEMAS) + validate(record, SCHEMAS["pass"], schemas=SCHEMAS)
    if problems:
        raise Refused("the plan or its record does not validate: %s" % problems[0])
    if (writes["pass"], writes["release"]) != (record["pass"], record["release"]):
        raise Refused("the plan is of another pass or Release than its record")
    if [w["id"] for w in writes["writes"]] != ["w%d" % (n + 1) for n in range(len(writes["writes"]))]:
        raise Refused("the plan's ids are not w1, w2 and so on, in order")
    minted = {e["run"]: e["decision"] for e in record["pull_requests"] + record["issues"] if e["run"] is not None}
    seen = set()
    for w in writes["writes"]:
        if w["type"] in ("dispatch_run", "dispatch_approval"):
            decision, named = minted.get(w["run"]), records.named(w["name"])
            if decision is None or named is None or w["run"] in seen:
                raise Refused("a dispatch of a Run the record did not mint, or under no run-name, or twice")
            seen.add(w["run"])
            if w["type"] == "dispatch_run":
                admitted = decision["outcome"] == t.ADMIT and decision.get("admit")
                want = admitted and (admitted["intent"], admitted["role"], admitted["content_id"])
                got = (named["intent"], named["role"], named["content_id"])
            else:
                want = decision["outcome"] == t.ACT and decision.get("action") == "issue_approval" \
                    and (t.ISSUE_APPROVAL, decision.get("content_id"))
                got = (named["intent"], named["content_id"])
            if not want or want != got or named["run"] != w["run"] or named["item"] != decision["item"] \
                    or w["item"] != decision["item"]:
                raise Refused("a dispatch whose run-name or item is not its Decision's")
        elif w["type"] == "dispatch_successor":
            if w is not writes["writes"][-1] or any((w["item"], w["run"], w["name"], w["action"])):
                raise Refused("a successor that is not the plan's last write, or names an item")
        elif w["type"] == "not_built":
            if w["action"] is None or w["run"] is not None or w["name"] is not None:
                raise Refused("an act no write serves, named without its action")
        else:
            raise Refused("a write this port does not send yet: %s" % w["type"])


def _dispatch(transport, write: dict, record: dict, config: dict) -> tuple:
    kind = DISPATCHES[write["type"]]
    body = {"ref": config["home"]["branch"]}
    if kind != "poller":
        item = write["item"]
        body["inputs"] = {"name": write["name"], "item": "%s#%d" % (item["repo"], item["number"]),
                          "pass": record["pass"]}
    try:
        answer = transport.send(request("POST", dispatch_path(config, kind), body=body))
    except Unanswered:
        return "failed", "dispatch_unanswered"
    if answer["status"] == 204:
        return "sent", None
    if answer["status"] in REFUSED:
        return "refused", "token_refused"
    if answer["status"] >= 500:
        return "failed", "dispatch_unanswered"
    return "failed", "dispatch_refused"


def apply(writes: dict, record: dict, transports: dict, config: dict) -> dict:
    """`written/1`: each write of the plan sent through its credential's transport, and what it did. `transports`
    maps a credential, `workflow`, to its transport; one that is missing sends nothing."""
    _held(writes, record)
    ended, out = set(), []
    for w in writes["writes"]:
        state, reason = "refused", None
        if w["type"] == "not_built":
            reason = "not_built"
        elif w["type"] in DISPATCHES:
            if w["type"] != "dispatch_successor" and config["accounts"]["workflow_token"] is None:
                reason = "uncounted"
            elif "workflow" in ended or transports.get("workflow") is None:
                reason = "token_refused" if "workflow" in ended else "no_credential"
            else:
                state, reason = _dispatch(transports["workflow"], w, record, config)
                if reason == "token_refused":
                    ended.add("workflow")
        out.append({"id": w["id"], "type": w["type"], "item": w["item"], "run": w["run"], "state": state,
                    "key": None, "reason": reason})
    written = {"schema": "written/1", "pass": record["pass"], "release": record["release"], "writes": out}
    problems = validate(written, SCHEMAS["written"], schemas=SCHEMAS)
    if problems:
        raise Refused("written/1: %s" % problems[0])
    return written


def failed(written: dict) -> bool:
    """Whether any write failed, or was refused for a reason but an act no write serves yet."""
    return any(w["state"] == "failed" or (w["state"] == "refused" and w["reason"] != "not_built")
               for w in written["writes"])


def main(argv=None, environ=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    environ = os.environ if environ is None else environ
    record, writes = (json.loads(pathlib.Path(p).read_text()) for p in argv[:2])
    config = json.loads((ROOT / "config" / "controller.json").read_text())
    token = environ.get("WORKFLOW_TOKEN")
    transports = {"workflow": Allowed(Live(token), workflow_permits(config)) if token else None}
    written = apply(writes, record, transports, config)
    pathlib.Path(argv[2], "written.json").write_text(json.dumps(written, indent=2) + "\n")
    return 1 if failed(written) else 0


if __name__ == "__main__":
    sys.exit(main())
