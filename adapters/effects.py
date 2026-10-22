"""The effects port: the Controller's writes, sent through the transport, each through the one credential its type
names and nothing else (design sections 3.6 and 4.9; #193's rulings for PR 2, posted 2026-10-21).

`apply` takes the pass's plan, `writes/1`, and the pass record it was planned from, and returns `written/1`: what each
write did, as read back. Before anything is sent the plan is held to the record: the same pass and Release, ids in
order, and every write but a last successor exactly the ones the record's Decisions call for, all of them, in their
order, each dispatch under the run-name its Decision gives it, an approval's under the configuration's owner Role, and
a successor exactly where the record says the pass decided one. A plan that is not the record's is refused whole, and
nothing is sent (I-22).

A dispatch is the pass job's own token's (`WORKFLOW_TOKEN`), whose account the records port counts a Run by (P-9;
#196's ruling 10). Its transport may send nothing but a dispatch of the three workflow files the configuration names,
on its home repo and branch, a Run's or an approval's with its three inputs and the successor's with none. While
the configuration names no account for that token, no Run or approval is dispatched: the records port could not
count it, and the ceilings would not see it (I-34). GitHub answers a dispatch 204 with no run,
so it is `sent`, never `applied`: the next pass's records port reads it back by its run-name. A dispatch is sent once
and never retried, whatever it answers: one GitHub did not answer may still have started a run, and a second would
start a second under the same Run id. A 401 or 403 ends every later write on that credential. An act no write serves
yet is recorded `not_built` and raises nothing.

`python3 -m adapters.effects PASS WRITES OUT` is the step: it reads the pass record and the plan, sends the writes
through a live transport, writes `written.json` to `OUT`, and exits non-zero when a write failed or was refused for
any reason but `not_built`, so that the pass's run concludes where the Maintainer sees it. A plan refused whole, or a
token the transport cannot take, still leaves `written.json`, every write in it refused.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

from adapters import acceptance, checks, threads
from adapters.github import Live, Unanswered, request
from kernel import terms as t
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = {p.name[: -len(".schema.json")]: json.loads(p.read_text())
           for p in sorted((ROOT / "schemas").glob("*.schema.json"))}
DISPATCHES = {"dispatch_run": "run", "dispatch_approval": "approval", "dispatch_successor": "poller"}
REFUSED = {401, 403}
# The facts port's own GraphQL reads, which the approver's token may ask of its item and nothing else.
QUERIES = (threads.QUERY, checks.QUERY, acceptance.QUERY)


class Refused(ValueError):
    """A plan that is not the record's: nothing is sent."""


class Allowed:
    """A transport that sends only the requests one credential may make, each by its method and path and the shape of
    its body; any other is refused before it leaves."""

    def __init__(self, transport, permits: dict):
        self._transport, self._permits = transport, dict(permits)

    def send(self, req: dict) -> dict:
        shape = self._permits.get((req.get("method"), req.get("path")))
        if shape is None or not shape(req.get("body")):
            raise Unanswered("a write this credential may not send")
        return self._transport.send(req)


def dispatch_path(config: dict, kind: str) -> str:
    return "/repos/%s/actions/workflows/%s/dispatches" % (config["home"]["repo"], config["workflows"][kind])


def workflow_permits(config: dict) -> dict:
    """The requests the pass job's own token may send: a dispatch of each of the three files, on the home branch, a
    Run's or an approval's with its three inputs, the successor's with none; and nothing else."""
    branch = config["home"]["branch"]

    def run(body) -> bool:
        return isinstance(body, dict) and set(body) == {"ref", "inputs"} and body["ref"] == branch \
            and isinstance(body["inputs"], dict) and set(body["inputs"]) == {"name", "item", "pass"} \
            and all(isinstance(v, str) for v in body["inputs"].values())

    def poller(body) -> bool:
        return body == {"ref": branch}
    return {("POST", dispatch_path(config, "run")): run, ("POST", dispatch_path(config, "approval")): run,
            ("POST", dispatch_path(config, "poller")): poller}


def run_name(item: dict, intent: str, role: str, content: str, run: str) -> str:
    """The run-name a Run is dispatched under, as `controller/pass_.py` gives it."""
    return "sf %s#%d %s %s %s %s" % (item["repo"], item["number"], intent, role, content, run)


def expected(record: dict, owner_role: str) -> list:
    """Every write but the successor that the record's Decisions call for, in the order they are sent: each act no
    write serves yet, then each Run's and approval's dispatch, in the record's item order, under the run-name its
    Decision gives it."""
    entries = record["pull_requests"] + record["issues"]
    acts, dispatches = [], []
    for e in entries:
        d = e["decision"]
        if d["outcome"] == t.ADMIT:
            a = d["admit"]
            dispatches.append(("dispatch_run", d["item"], e["run"],
                               run_name(d["item"], a["intent"], a["role"], a["content_id"], e["run"]), None))
        elif d["outcome"] == t.ACT and d.get("action") == "issue_approval":
            dispatches.append(("dispatch_approval", d["item"], e["run"],
                               run_name(d["item"], t.ISSUE_APPROVAL, owner_role, d["content_id"], e["run"]), None))
        elif d["outcome"] == t.ACT:
            acts.append(("not_built", d["item"], None, None, d["action"]))
    return acts + dispatches


def _held(writes: dict, record: dict, owner_role: str) -> None:
    """Refuse a plan that is not the record's (I-22): every write but a last successor must be one the record's
    Decisions call for, all of them, in order, under the run-names they give."""
    problems = validate(writes, SCHEMAS["writes"], schemas=SCHEMAS) + validate(record, SCHEMAS["pass"], schemas=SCHEMAS)
    if problems:
        raise Refused("the plan or its record does not validate: %s" % problems[0])
    if (writes["pass"], writes["release"]) != (record["pass"], record["release"]):
        raise Refused("the plan is of another pass or Release than its record")
    planned = writes["writes"]
    if [w["id"] for w in planned] != ["w%d" % (n + 1) for n in range(len(planned))]:
        raise Refused("the plan's ids are not w1, w2 and so on, in order")
    successor = bool(planned) and planned[-1]["type"] == "dispatch_successor"
    if successor != (record.get("successor") is True):
        raise Refused("a successor the record did not decide, or none where it did")
    if successor:
        last = planned[-1]
        if any((last["item"], last["run"], last["name"], last["action"])):
            raise Refused("a successor that names an item, a Run or an act")
        planned = planned[:-1]
    got = [(w["type"], w["item"], w["run"], w["name"], w["action"]) for w in planned]
    if got != expected(record, owner_role):
        raise Refused("the plan is not every write its record's Decisions call for, in their order")


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


def apply(writes: dict, record: dict, transports: dict, config: dict, owner_role: str) -> dict:
    """`written/1`: each write of the plan sent through its credential's transport, and what it did. `transports`
    maps a credential, `workflow`, to its transport; one that is missing sends nothing. `owner_role` is the Role an
    approval is dispatched under, the configuration's."""
    problems = validate(config, SCHEMAS["controller"], schemas=SCHEMAS)
    if problems:
        raise Refused("the Controller's configuration does not validate: %s" % problems[0])
    _held(writes, record, owner_role)
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


def refused_all(writes, record, reason: str) -> dict:
    """`written/1` for a plan nothing of which was sent: each write the plan holds refused for `reason`, or none where
    the plan cannot be read, so that the step always leaves its record."""
    readable = isinstance(writes, dict) and not validate(writes, SCHEMAS["writes"], schemas=SCHEMAS)
    rows = writes["writes"] if readable else []
    ident = record if isinstance(record, dict) else {}
    return {"schema": "written/1", "pass": ident.get("pass"), "release": ident.get("release"),
            "writes": [{"id": w["id"], "type": w["type"], "item": w["item"], "run": w["run"], "state": "refused",
                        "key": None, "reason": reason} for w in rows]}


# The machine user's approval, the approving act's one write (issue 195, ruling 4): through the approver's own token,
# whose transport may read the item's repo, who the token is and the org's Pause, ask the facts port's own GraphQL reads
# of this pull request, and write one review, the approval of the commit the act read, with nothing else in it.
UNAVAILABLE = 429      # with no answer and any 5xx, GitHub's own trouble: the environment's
GONE = 404             # with 401 and 403, a token GitHub will not take for this item: the environment's


class Approving:
    """The approver's transport, narrowed to what one step may send, and anything else refused before it leaves. With
    no item, it may ask only who the token is; with an item, also read that item's repo, the org's Pause and the facts
    port's own GraphQL reads of that pull request; with the head the act just read as well, also write one review, the
    approval of that commit and nothing else in it. No path may climb out of the item's repo."""

    def __init__(self, transport, item: dict = None, head: str = None):
        self._transport, self._item, self._head = transport, dict(item) if item else None, head
        if item:
            self._repo = "/repos/%s/" % item["repo"]
            self._pause = "/orgs/%s/actions/variables/FACTORY_PAUSED" % item["repo"].split("/")[0]
            self._reviews = "/repos/%s/pulls/%d/reviews" % (item["repo"], item["number"])

    def _read(self, path) -> bool:
        if not isinstance(path, str) or ".." in path or "%2e" in path.lower() or "//" in path:
            return False
        return path == "/user" or (self._item is not None and (path == self._pause or path.startswith(self._repo)))

    def _query(self, body) -> bool:
        """One of the facts port's own reads of this pull request, its variables this item's and a page's cursor."""
        if self._item is None or not isinstance(body, dict) or set(body) != {"query", "variables"} \
                or body["query"] not in QUERIES:
            return False
        variables = body["variables"]
        owner, name = self._item["repo"].split("/")
        return (isinstance(variables, dict) and set(variables) <= {"owner", "name", "number", "after"}
                and variables.get("owner") == owner and variables.get("name") == name
                and (variables.get("after") is None or isinstance(variables["after"], str))
                and variables.get("number") == self._item["number"])

    def send(self, req: dict) -> dict:
        method, path, body = req.get("method"), req.get("path"), req.get("body")
        if method == "GET" and self._read(path):
            return self._transport.send(req)
        if method == "POST" and path == "/graphql" and self._query(body):
            return self._transport.send(req)
        if method == "POST" and self._head is not None and path == self._reviews \
                and body == {"commit_id": self._head, "event": "APPROVE"}:
            return self._transport.send(req)
        raise Unanswered("a request the approver's token may not send")


def _asked(transport, req: dict):
    """GitHub's answer, or None where it gave none. Nothing is sent twice."""
    try:
        return transport.send(req)
    except Unanswered:
        return None


def _answered(answer, status: int):
    return answer.get("body") if isinstance(answer, dict) and answer.get("status") == status else None


def _trouble(answer, otherwise: str) -> tuple:
    """Whose fault a read GitHub did not answer as asked was: the environment's, by its status alone, never its words."""
    status = answer.get("status") if isinstance(answer, dict) else None
    if status is None or status >= 500 or status == UNAVAILABLE:
        return "environment", "github_unavailable"
    if status in REFUSED or status == GONE:
        return "environment", "token_refused"
    return "environment", otherwise


def approver_of(transport) -> dict:
    """Who the token is, `GET /user`: `{login, type, fault, reason}`, the fault None when it was read."""
    answer = _asked(transport, request("GET", "/user"))
    body = _answered(answer, 200)
    if not isinstance(body, dict):
        fault, reason = _trouble(answer, "approver_unreadable")
        return {"login": None, "type": None, "fault": fault, "reason": reason}
    return {"login": body.get("login"), "type": body.get("type"), "fault": None, "reason": None}


def _approval(review, head: str, login: str) -> bool:
    return (isinstance(review, dict) and review.get("state") == "APPROVED" and review.get("commit_id") == head
            and isinstance(review.get("user"), dict) and review["user"].get("login") == login
            and isinstance(review.get("node_id"), str) and review["node_id"] != "")


def approval_of(transport, item: dict, head: str, login: str) -> dict:
    """The approver's approval of `head` that stands, recovered as a review by this actor on this commit (section 3.6):
    `{state, key, fault, reason}`, `already_applied` with its node id, or a state of None where there is none. A list
    that cannot be read, or that may be cut short, recovers nothing."""
    answer = _asked(transport, request("GET", "/repos/%s/pulls/%d/reviews?per_page=100" % (item["repo"], item["number"])))
    listed = _answered(answer, 200)
    if not isinstance(listed, list) or len(listed) >= 100:
        fault, reason = _trouble(answer, "facts_unreadable")
        return {"state": None, "key": None, "fault": fault, "reason": reason}
    # The approver's latest review of this commit is the one that stands: a request for changes after an approval
    # supersedes it (the fresh review).
    mine = [r for r in listed if isinstance(r, dict) and r.get("commit_id") == head and isinstance(r.get("user"), dict)
            and r["user"].get("login") == login]
    if mine and _approval(mine[-1], head, login):
        return {"state": "already_applied", "key": mine[-1]["node_id"], "fault": None, "reason": None}
    return {"state": None, "key": None, "fault": None, "reason": None}


def approve(transport, item: dict, head: str, login: str) -> dict:
    """The approval of `head`, sent once and read back: `{state, key, fault, reason}`. `applied` only with the node id
    of the approver's own approval of that commit, read back by the id GitHub answered (L-41). Whose fault a failure
    was is read from its status and from the pull request read again, never from GitHub's words (ruling 6)."""
    pull = "/repos/%s/pulls/%d" % (item["repo"], item["number"])
    answer = _asked(transport, request("POST", pull + "/reviews", body={"commit_id": head, "event": "APPROVE"}))
    review = _answered(answer, 200)
    if not isinstance(review, dict):
        status = answer.get("status") if isinstance(answer, dict) else None
        if status in REFUSED or status == GONE:
            return {"state": "refused", "key": None, "fault": "environment", "reason": "token_refused"}
        if status is None or status >= 500 or status == UNAVAILABLE:
            return {"state": "failed", "key": None, "fault": "environment", "reason": "github_unavailable"}
        if 200 <= status < 300:
            # GitHub took it and the answer cannot be read: the approval may stand, and nothing is claimed for it.
            return {"state": "failed", "key": None, "fault": "environment", "reason": "not_read_back"}
        # Any other refusal is the item's, while the pull request is open at the commit; a head that moved or a close
        # is a change under the act.
        again = _asked(transport, request("GET", pull))
        now = _answered(again, 200)
        if not isinstance(now, dict) or now.get("state") not in ("open", "closed") or not isinstance(now.get("head"), dict) \
                or not isinstance(now["head"].get("sha"), str):
            # The pull request read again cannot be read: whose fault, by its status alone (Codex on PR 321).
            fault, reason = _trouble(again, "github_unavailable")
            return {"state": "failed", "key": None, "fault": fault, "reason": reason}
        if now.get("state") != "open" or now["head"].get("sha") != head:
            return {"state": "failed", "key": None, "fault": "superseded", "reason": "head_moved"}
        return {"state": "failed", "key": None, "fault": "item", "reason": "approval_refused"}
    rid = review.get("id")
    back = _answered(_asked(transport, request("GET", pull + "/reviews/%d" % rid)), 200) if type(rid) is int else None
    if not isinstance(back, dict) or back.get("id") != rid:
        return {"state": "failed", "key": None, "fault": "environment", "reason": "not_read_back"}
    if not _approval(back, head, login):
        return {"state": "failed", "key": None, "fault": "item", "reason": "read_back_differs"}
    return {"state": "applied", "key": back["node_id"], "fault": None, "reason": None}


def main(argv=None, environ=None, base=None) -> int:
    """The step. It reads and writes only inside the directory it runs in, `base`, by default the working directory:
    each path is followed to where it really is, and one outside is refused before anything is opened, naming no path."""
    argv = sys.argv[1:] if argv is None else argv
    environ = os.environ if environ is None else environ
    inside = os.path.realpath(str(pathlib.Path.cwd() if base is None else base))
    if len(argv) != 3:
        print("usage: python3 -m adapters.effects PASS WRITES OUT; nothing was sent")
        return 2
    passed, planned, out = (os.path.realpath(os.path.join(inside, p)) for p in argv)
    if not passed.startswith(inside + os.sep) or not planned.startswith(inside + os.sep) \
            or not (out == inside or out.startswith(inside + os.sep)):
        print("usage: python3 -m adapters.effects PASS WRITES OUT, each inside the directory it runs in; nothing was sent")
        return 2
    if not os.path.isdir(out) or not os.access(out, os.W_OK):
        print("usage: python3 -m adapters.effects PASS WRITES OUT, OUT a folder it can write; nothing was sent")
        return 2
    with open(passed, encoding="utf-8") as one, open(planned, encoding="utf-8") as two:
        record, writes = json.load(one), json.load(two)
    config = json.loads((ROOT / "config" / "controller.json").read_text())
    owner_role = json.loads((ROOT / "config" / "defaults.json").read_text())["owner_role"]
    token = environ.get("WORKFLOW_TOKEN")
    sent = True
    try:
        transports = {"workflow": Allowed(Live(token), workflow_permits(config)) if token else None}
        written = apply(writes, record, transports, config, owner_role)
    except Unanswered:
        written, sent = refused_all(writes, record, "token_unreadable"), False
    except Refused:
        written, sent = refused_all(writes, record, "plan_refused"), False
    with open(os.path.join(out, "written.json"), "w", encoding="utf-8") as kept:
        kept.write(json.dumps(written, indent=2) + "\n")
    return 0 if sent and not failed(written) else 1


if __name__ == "__main__":
    sys.exit(main())
