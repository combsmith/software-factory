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
import re
import sys

from adapters import pause as pause_
from adapters.github import Live, Unanswered, request
from kernel import terms as t
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = {p.name[: -len(".schema.json")]: json.loads(p.read_text())
           for p in sorted((ROOT / "schemas").glob("*.schema.json"))}
DISPATCHES = {"dispatch_run": "run", "dispatch_approval": "approval", "dispatch_successor": "poller"}
REFUSED = {401, 403}
TITLE = "Factory alerts"
FIRST_LINE = "The Factory's alerts, as a pass of its own found them: codes alone, and nothing from outside the Factory."
CAUSE = re.compile(r"- `([a-z_]{1,60})`")
# What a Pause stops: every dispatch, the successor's among them (#193's ruling 11). A status and the tracking issue are
# no act, and are written under a Pause, so that a person sees why nothing moves.
STOPPED = set(DISPATCHES)
# A write refused for one of these is no fault of the pass's: an act no write serves yet, and a Pause a person set.
NO_FAULT = {"not_built", "paused"}


class Refused(ValueError):
    """A plan that is not the record's: nothing is sent."""


class Allowed:
    """A transport that sends only the requests one credential may make, each by its method and path and the shape of
    its body; any other is refused before it leaves."""

    def __init__(self, transport, permits: dict, patterns=()):
        self._transport, self._permits, self._patterns = transport, dict(permits), tuple(patterns)

    def send(self, req: dict) -> dict:
        """`patterns` are `(method, compiled path, shape)` for a path that carries an id read back, matched whole."""
        shape = self._permits.get((req.get("method"), req.get("path")))
        if shape is None:
            shape = next((s for m, pattern, s in self._patterns
                          if m == req.get("method") and isinstance(req.get("path"), str) and pattern.fullmatch(req["path"])),
                         None)
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
    Decision gives it, and then the tracking issue, the one each pass keeps (#193's ruling 8)."""
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
    return acts + dispatches + [("tracking_issue", None, None, None, None)]


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


def scopes(writes: dict, config: dict) -> tuple:
    """`(org, repos)`: the org of the home repo, and the home repo with every repo a dispatch acts in, whose Pause each
    stops the pass's dispatches."""
    home = config["home"]["repo"]
    repos = {home} | {w["item"]["repo"] for w in writes["writes"] if w["type"] in STOPPED and w["item"]}
    return home.split("/")[0], sorted(repos)


def controller_permits(config: dict, org: str, repos: list) -> tuple:
    """`(permits, patterns)`: the requests the Controller's token may send for the Pause and the tracking issue. Each
    scope's `FACTORY_PAUSED`; the open issues its App opened, one page; an issue opened with the one title, a body and
    the Maintainer assigned; and an issue of the home repo edited, its body alone, or closed as completed."""
    home = config["home"]["repo"]
    account = config["accounts"]["controller"] or {}

    def none(body) -> bool:
        return body is None

    def opened(body) -> bool:
        return isinstance(body, dict) and set(body) == {"title", "body", "assignees"} and body["title"] == TITLE \
            and isinstance(body["body"], str) and body["assignees"] == [(config["accounts"]["maintainer"] or {}).get("login")]

    def edited(body) -> bool:
        return isinstance(body, dict) and (set(body) == {"body"} and isinstance(body["body"], str)
                                           or body == {"state": "closed", "state_reason": "completed"})
    permits = {("GET", pause_.path(scope)): none for scope in [org] + list(repos)}
    if account.get("login"):
        permits[("GET", listed(home, account))] = none
    permits[("POST", "/repos/%s/issues" % home)] = opened
    return permits, (("PATCH", re.compile(re.escape("/repos/%s/issues/" % home) + r"[1-9][0-9]{0,9}"), edited),)


def listed(home: str, account: dict) -> str:
    return "/repos/%s/issues?state=open&creator=%s&per_page=100" % (home, account["login"])


def open_issues(transport, config: dict):
    """The open issues the Controller's App opened in the home repo, `[{number, causes}]`, told by their author's id and
    type, never by a title or a label anyone can set; None where they cannot all be read: a page that names another,
    or an answer that is no list of issues. The trial that records this read is still to run (#193's ruling 12)."""
    account = config["accounts"]["controller"]
    if transport is None or account is None:
        return None
    try:
        answer = transport.send(request("GET", listed(config["home"]["repo"], account)))
    except Unanswered:
        return None
    rows = answer["body"]
    if answer["status"] != 200 or not isinstance(rows, list) or 'rel="next"' in str(answer["headers"].get("link", "")):
        return None
    found = []
    for row in rows:
        user = row.get("user") if isinstance(row, dict) else None
        if not isinstance(user, dict) or type(row.get("number")) is not int:
            return None
        if "pull_request" in row or (user.get("id"), user.get("type")) != (account["id"], account["type"]):
            continue
        found.append({"number": row["number"], "causes": causes_of(row.get("body"))})
    return found


def causes_of(body):
    """The cause codes an issue's body lists, in its order; None for a body this port did not write."""
    if not isinstance(body, str):
        return None
    lines = body.split("\n")
    if not lines or lines[0] != FIRST_LINE:
        return None
    return [m.group(1) for m in (CAUSE.fullmatch(line) for line in lines[1:]) if m]


def rendered(record: dict, causes: list) -> str:
    """The tracking issue's body: a fixed first line, one line for each cause code, sorted, and the pass that wrote it,
    its time and its Release. Codes and identifiers alone: no text from outside reaches it."""
    return "\n".join([FIRST_LINE] + ["- `%s`" % c for c in causes]
                     + ["", "Written by pass %s at %s, %s." % (record["pass"], record["now"], record["release"])]) + "\n"


def tracking(transport, config: dict, record: dict, causes: list, found) -> tuple:
    """`(state, key, reason)` for the tracking issue: opened with the Maintainer assigned when a cause first stands and
    none is open, edited in place when its causes change, and closed when none stands. Two open is written to by no
    one. Each is sent once, and applied only on what GitHub's answer reads back."""
    if config["accounts"]["controller"] is None or config["accounts"]["maintainer"] is None:
        return "refused", None, "uncounted"
    if transport is None:
        return "refused", None, "no_credential"
    if found is None:
        return "failed", None, "issues_unreadable"
    if len(found) > 1:
        return "refused", None, "tracking_issue_twice"
    issue = found[0] if found else None
    home = config["home"]["repo"]
    if not causes:
        if issue is None:
            return "already_applied", None, None
        req, want = request("PATCH", "/repos/%s/issues/%d" % (home, issue["number"]),
                            body={"state": "closed", "state_reason": "completed"}), ("closed", issue["number"], None)
    elif issue is None:
        body = rendered(record, causes)
        req = request("POST", "/repos/%s/issues" % home,
                      body={"title": TITLE, "body": body, "assignees": [config["accounts"]["maintainer"]["login"]]})
        want = ("open", None, body)
    elif issue["causes"] == causes:
        return "already_applied", str(issue["number"]), None
    else:
        body = rendered(record, causes)
        req, want = request("PATCH", "/repos/%s/issues/%d" % (home, issue["number"]), body={"body": body}), \
            ("open", issue["number"], body)
    try:
        answer = transport.send(req)
    except Unanswered:
        return "failed", None, "write_unanswered"
    if answer["status"] in REFUSED:
        return "refused", None, "token_refused"
    if answer["status"] >= 500:
        return "failed", None, "write_unanswered"
    got = answer["body"] if isinstance(answer["body"], dict) else {}
    state, number, body = want
    if answer["status"] not in (200, 201) or got.get("state") != state or type(got.get("number")) is not int \
            or (number is not None and got["number"] != number) or (body is not None and got.get("body") != body):
        return "sent", None, None
    return "applied", str(got["number"]), None


def brake(pause: dict, org: str, repos: list):
    """Why no dispatch may be sent, or None: every scope's Pause must read exactly not paused, the org's and each repo's
    the pass acts in, read again here, outside the Kernel, so that it holds if the Kernel does not (decision 0003). A
    scope that pauses is `paused`; one not read, not set, or read as anything else is `pause_unreadable`."""
    pause = pause if isinstance(pause, dict) else {}
    held = pause.get("repos") if isinstance(pause.get("repos"), dict) else {}
    values = [pause.get("org", pause_.UNREADABLE)] + [held.get(repo, pause_.UNREADABLE) for repo in repos]
    if any(v == pause_.PAUSED for v in values):
        return "paused"
    if not all(v == pause_.NOT_PAUSED for v in values):
        return "pause_unreadable"
    return None


def apply(writes: dict, record: dict, transports: dict, config: dict, owner_role: str, pause=None,
          issues=None) -> dict:
    """`written/1`: each write of the plan sent through its credential's transport, and what it did. `transports`
    maps a credential, `workflow` or `controller`, to its transport; one that is missing sends nothing. `owner_role` is
    the Role an approval is dispatched under, the configuration's. `pause` is the Pause as `adapters/pause.py` read it
    for `scopes(writes, config)` just before, and `issues` the open tracking issues as `open_issues` read them."""
    problems = validate(config, SCHEMAS["controller"], schemas=SCHEMAS)
    if problems:
        raise Refused("the Controller's configuration does not validate: %s" % problems[0])
    _held(writes, record, owner_role)
    stopped = brake(pause, *scopes(writes, config))
    ended, out = set(), []
    for w in writes["writes"]:
        state, reason, key = "refused", None, None
        if w["type"] == "not_built":
            reason = "not_built"
        elif w["type"] == "tracking_issue":
            faults = any(o["state"] == "failed" or (o["state"] == "refused" and o["reason"] not in NO_FAULT)
                         for o in out)
            causes = sorted({a for a in record.get("alerts", []) if a != "paused"} | ({"write_failed"} if faults else set()))
            if "controller" in ended:
                reason = "token_refused"
            else:
                state, key, reason = tracking(transports.get("controller"), config, record, causes, issues)
                if reason == "token_refused":
                    ended.add("controller")
        elif w["type"] in DISPATCHES:
            if stopped is not None:
                reason = stopped
            elif w["type"] != "dispatch_successor" and config["accounts"]["workflow_token"] is None:
                reason = "uncounted"
            elif "workflow" in ended or transports.get("workflow") is None:
                reason = "token_refused" if "workflow" in ended else "no_credential"
            else:
                state, reason = _dispatch(transports["workflow"], w, record, config)
                if reason == "token_refused":
                    ended.add("workflow")
        out.append({"id": w["id"], "type": w["type"], "item": w["item"], "run": w["run"], "state": state,
                    "key": key, "reason": reason})
    written = {"schema": "written/1", "pass": record["pass"], "release": record["release"], "writes": out}
    problems = validate(written, SCHEMAS["written"], schemas=SCHEMAS)
    if problems:
        raise Refused("written/1: %s" % problems[0])
    return written


def failed(written: dict) -> bool:
    """Whether any write failed, or was refused for a reason but an act no write serves yet or a person's Pause."""
    return any(w["state"] == "failed" or (w["state"] == "refused" and w["reason"] not in NO_FAULT)
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
    token, own = environ.get("WORKFLOW_TOKEN"), environ.get("CONTROLLER_TOKEN")
    sent = True
    try:
        transports = {"workflow": Allowed(Live(token), workflow_permits(config)) if token else None,
                      "controller": None}
        if own and isinstance(writes, dict) and not validate(writes, SCHEMAS["writes"], schemas=SCHEMAS):
            org, repos = scopes(writes, config)
            transports["controller"] = Allowed(Live(own), *controller_permits(config, org, repos))
        org, repos = scopes(writes, config) if transports["controller"] else ("", [])
        read = pause_.read(transports["controller"], org, repos)
        written = apply(writes, record, transports, config, owner_role, pause=read,
                        issues=open_issues(transports["controller"], config))
    except Unanswered:
        written, sent = refused_all(writes, record, "token_unreadable"), False
    except Refused:
        written, sent = refused_all(writes, record, "plan_refused"), False
    with open(os.path.join(out, "written.json"), "w", encoding="utf-8") as kept:
        kept.write(json.dumps(written, indent=2) + "\n")
    return 0 if sent and not failed(written) else 1


if __name__ == "__main__":
    sys.exit(main())
