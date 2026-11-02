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

import hashlib
import json
import os
import pathlib
import re
import sys
import time
import urllib.parse

from adapters import acceptance, checks, identity, pause as pause_, threads
from adapters.github import Live, Unanswered, request
from controller import feed as feed_
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
NO_FAULT = {"not_built", "paused", "no_account", "status_bounded"}
# The status on the item (#193's ruling 6, P-12): codes and identifiers alone, and what GitHub keeps of them.
SHOWN = re.compile(r"[A-Za-z0-9_.:/#@-]{1,200}")
SHOWN_MOST = 20
SUMMARY_MOST = 4096
# A status's own forms: its key, and what `written/1` holds as the key read back. P-12: a title of 255 is taken, of 256 refused.
STATUS_ID = re.compile(r"d[0-9a-f]{32}")
STATUS_KEY = re.compile(r"[A-Za-z0-9_=:-]{1,100}")
TITLE_MOST = 255
DIGITS = re.compile(r"[1-9][0-9]{0,18}")
# The facts port's own GraphQL reads, which the approver's token may ask of its item and nothing else.
QUERIES = (threads.QUERY, checks.QUERY, acceptance.QUERY)


class Refused(ValueError):
    """A plan that is not the record's: nothing is sent."""


class Allowed:
    """A transport that sends only the requests one credential may make, each by its method and path and the shape of
    its body; any other is refused before it leaves. `patterns` are `(method, compiled path, shape)` for a path that
    carries an id read back, matched whole."""

    def __init__(self, transport, permits: dict, patterns=()):
        self._transport, self._permits, self._patterns = transport, dict(permits), list(patterns)

    def send(self, req: dict) -> dict:
        shape = self._permits.get((req.get("method"), req.get("path")))
        if shape is None:
            shape = next((s for method, path, s in self._patterns
                          if method == req.get("method") and isinstance(req.get("path"), str)
                          and path.fullmatch(req["path"])), None)
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


def status_entries(record: dict) -> list:
    """The items a status is written on, in the record's item order (#193's ruling 6): each pull request the pass carried
    a head for, as `controller.pass_.status_head` rules. An issue has no commit, and gets none."""
    return [e for e in record["pull_requests"] if e.get("head")]


def expected(record: dict, owner_role: str) -> list:
    """Every write but the successor that the record's Decisions call for, in the order they are sent: each act no
    write serves yet, then each Run's and approval's dispatch, in the record's item order, under the run-name its
    Decision gives it, then each status on an item, and then the tracking issue, the one each pass keeps (#193's ruling 8)."""
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
    statuses = [("status_on_item", e["decision"]["item"], None, None, None) for e in status_entries(record)]
    return acts + dispatches + statuses + [("tracking_issue", None, None, None, None)]


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
    repo's `FACTORY_PAUSED`, and the org's as the first repo's list of the org's variables, each page (issue 362); the
    open issues its App opened, one page; an issue opened with the one title, a body and
    the Maintainer assigned; an issue of the home repo edited, its body alone or with the Maintainer assigned
    again, or closed as completed; and on the home repo the status check run on a commit, listed, made or edited, each
    with the fields the status has and no other."""
    home = config["home"]["repo"]
    account = config["accounts"]["controller"] or {}

    def none(body) -> bool:
        return body is None

    maintainer = (config["accounts"]["maintainer"] or {}).get("login")

    def opened(body) -> bool:
        return isinstance(body, dict) and set(body) == {"title", "body", "assignees"} and body["title"] == TITLE \
            and isinstance(body["body"], str) and isinstance(maintainer, str) and body["assignees"] == [maintainer]

    def edited(body) -> bool:
        return isinstance(body, dict) and (set(body) == {"body"} and isinstance(body["body"], str)
                                           or set(body) == {"body", "assignees"} and isinstance(body["body"], str)
                                           and isinstance(maintainer, str) and body["assignees"] == [maintainer]
                                           or body == {"state": "closed", "state_reason": "completed"})
    # The org's Pause is read from the first repo's list of the org's variables, page by page (issue 362).
    permits = {("GET", pause_.path(repo)): none for repo in repos}
    via = sorted(set(repos))[0] if repos else None
    if via is not None:
        permits[("GET", pause_.listed(via))] = none
    if account.get("login"):
        permits[("GET", listed(home, account))] = none
    permits[("POST", "/repos/%s/issues" % home)] = opened

    def status_written(body, fields=("external_id", "status", "conclusion", "output")) -> bool:
        if not (isinstance(body, dict) and set(fields) <= set(body) <= set(fields) | {"details_url"}):
            return False
        output = body["output"]
        return body["status"] == "completed" and body["conclusion"] == "neutral" \
            and isinstance(body["external_id"], str) and STATUS_ID.fullmatch(body["external_id"]) is not None \
            and isinstance(output, dict) and set(output) == {"title", "summary"} \
            and isinstance(output["title"], str) and len(output["title"]) <= TITLE_MOST \
            and isinstance(output["summary"], str) and len(output["summary"]) <= SUMMARY_MOST \
            and ("details_url" not in body or (isinstance(body["details_url"], str) and run_url.fullmatch(body["details_url"]) is not None))

    def status_made(body) -> bool:
        return status_written(body, ("name", "head_sha", "external_id", "status", "conclusion", "output")) \
            and body["name"] == status_name and isinstance(body["head_sha"], str) and SHA.fullmatch(body["head_sha"]) is not None

    status_name = json.loads((ROOT / "config" / "defaults.json").read_text())["status_on_item"]
    run_url = re.compile(re.escape("https://github.com/%s/actions/runs/" % home) + r"[1-9][0-9]{0,19}")

    permits[("POST", "/repos/%s/check-runs" % home)] = status_made
    statuses = (("GET", re.compile(re.escape("/repos/%s/commits/" % home) + r"[0-9a-f]{40}/check-runs\?check_name=[^&]+&app_id=[0-9]+"
                                   r"&filter=all&per_page=100"), none),
                ("PATCH", re.compile(re.escape("/repos/%s/check-runs/" % home) + r"[1-9][0-9]{0,18}"), status_written))
    pages = (("GET", re.compile(re.escape(pause_.listed(via) + "&page=") + r"(?:[2-9]|[1-9][0-9]{1,3})"), none),) \
        if via is not None else ()
    return permits, (("PATCH", re.compile(re.escape("/repos/%s/issues/" % home) + r"[1-9][0-9]{0,9}"), edited),) + statuses + pages


def listed(home: str, account: dict) -> str:
    return "/repos/%s/issues?state=open&creator=%s&per_page=100" % (home, account["login"])


def assigned(issue: dict, config: dict) -> bool:
    """Whether GitHub's answer for an issue lists the Maintainer among its assignees, by his account id and login."""
    maintainer = config["accounts"]["maintainer"] or {}
    listed_ = issue.get("assignees") if isinstance(issue, dict) else None
    return isinstance(listed_, list) and any(
        isinstance(a, dict) and (a.get("id"), a.get("login")) == (maintainer.get("id"), maintainer.get("login"))
        for a in listed_)


def open_issues(transport, config: dict):
    """The open issues the Controller's App opened in the home repo, `[{number, causes, assigned}]`, told by their
    author's id and type, never by a title or a label anyone can set, and whether the Maintainer is assigned; None where
    they cannot all be read: a page that names another, or an answer that is no list of issues. The trial that records
    this read is still to run (#193's ruling 12)."""
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
        if not isinstance(user, dict) or type(row.get("number")) is not int or not isinstance(row.get("assignees"), list):
            return None
        causes = causes_of(row.get("body"))
        # The App's own, by its account; and of those, the one this port wrote, by its first line: an issue the App
        # opened for anything else is not the tracking issue, and is never edited or closed as one.
        if "pull_request" in row or (user.get("id"), user.get("type")) != (account["id"], account["type"]) \
                or causes is None:
            continue
        found.append({"number": row["number"], "causes": causes, "assigned": assigned(row, config)})
    return found


WRITTEN = re.compile(r"Written by pass p_[0-9A-Z]{6,26} at [0-9TZ:-]{20}, factory/v[0-9]+\.[0-9]+\.[0-9]+\.")


def causes_of(body):
    """The cause codes an issue's body lists, in its order; None for a body this port did not write, line for line as
    `rendered` writes one, so that a body anyone edited is no tracking issue's."""
    if not isinstance(body, str) or not body.endswith("\n"):
        return None
    lines = body[:-1].split("\n")
    if len(lines) < 3 or lines[0] != FIRST_LINE or lines[-2] != "" or not WRITTEN.fullmatch(lines[-1]):
        return None
    causes = [CAUSE.fullmatch(line) for line in lines[1:-2]]
    return [m.group(1) for m in causes] if all(causes) else None


def rendered(record: dict, causes: list) -> str:
    """The tracking issue's body: a fixed first line, one line for each cause code, sorted, and the pass that wrote it,
    its time and its Release. Codes and identifiers alone: no text from outside reaches it."""
    return "\n".join([FIRST_LINE] + ["- `%s`" % c for c in causes]
                     + ["", "Written by pass %s at %s, %s." % (record["pass"], record["now"], record["release"])]) + "\n"


def tracking(transport, config: dict, record: dict, causes: list, found) -> tuple:
    """`(state, key, reason)` for the tracking issue: opened with the Maintainer assigned when a cause first stands and
    none is open, edited in place when its causes change, and closed, completed, when none stands. One open that does
    not list him is edited to assign him again, so that an assignment GitHub dropped notifies him at the next pass. Two
    open is written to by no one. Each is sent once, and applied only on what GitHub's answer reads back: an issue
    written that does not list him is `failed`, `assignee_dropped`, so that the step fails where he sees it."""
    if config["accounts"]["controller"] is None or config["accounts"]["maintainer"] is None:
        # Nothing can be written while the App or the Maintainer is unnamed: a cause unreported is a fault, so that
        # the step fails where he sees it; a pass with none fails nothing.
        return "refused", None, "uncounted" if causes else "no_account"
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
    elif issue["causes"] == causes and issue["assigned"]:
        return "already_applied", str(issue["number"]), None
    else:
        body = rendered(record, causes)
        asked = {"body": body} if issue["assigned"] else {"body": body,
                                                          "assignees": [config["accounts"]["maintainer"]["login"]]}
        req, want = request("PATCH", "/repos/%s/issues/%d" % (home, issue["number"]), body=asked), \
            ("open", issue["number"], body)
    try:
        answer = transport.send(req)
    except Unanswered:
        return "failed", None, "write_unanswered"
    if answer["status"] in REFUSED:
        return "refused", None, "token_refused"
    if answer["status"] >= 500:
        return "failed", None, "write_unanswered"
    if answer["status"] not in (200, 201):
        return "failed", None, "write_refused"
    got = answer["body"] if isinstance(answer["body"], dict) else {}
    state, number, body = want
    if got.get("state") != state or type(got.get("number")) is not int \
            or (number is not None and got["number"] != number) or (body is not None and got.get("body") != body) \
            or (state == "closed" and got.get("state_reason") != "completed"):
        return "sent", None, None
    if state == "open" and not assigned(got, config):
        return "failed", str(got["number"]), "assignee_dropped"
    return "applied", str(got["number"]), None


def brake(pause: dict, org: str, repos: list):
    """Why no dispatch may be sent, or None: every scope's Pause must read exactly not paused, the org's and each repo's
    the pass acts in, read again here, outside the Kernel, so that it holds if the Kernel does not (decision 0003). A
    scope that pauses is `paused`; one not read, not set, or read as anything else is `pause_unreadable`."""
    pause = pause if isinstance(pause, dict) else {}
    held = pause.get("repos") if isinstance(pause.get("repos"), dict) else {}
    values = [pause.get("org", pause_.UNREADABLE)] + [held.get(repo, pause_.UNREADABLE) for repo in repos]
    # The org read is the home repo's; a repo of another org has an org's Pause no one read.
    values += [pause_.UNREADABLE for repo in repos if repo.split("/")[0] != org]
    if any(v == pause_.PAUSED for v in values):
        return "paused"
    if not all(v == pause_.NOT_PAUSED for v in values):
        return "pause_unreadable"
    return None


def status_id(decision: dict) -> str:
    """The status's `external_id`: `d` and the first 32 hex digits of the SHA-256 of the Decision's canonical JSON, so any
    change to the Decision, its evidence among it, changes it. P-12: GitHub keeps it whole, up to 255 characters."""
    return "d" + hashlib.sha256(json.dumps(decision, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:32]


def status_output(decision: dict, record: dict, feed: dict) -> dict:
    """What a person reads: codes and identifiers alone. No title, login, branch name or comment reaches it, and an evidence
    item that is not a code is counted, never shown. P-12: an edit with no output keeps the old, so the whole is sent."""
    def code(value) -> str:
        return "null" if value is None else str(value)
    lines = ["attention: %s" % code(decision.get("attention")), "outcome: %s" % code(decision.get("outcome")),
             "action: %s" % code(decision.get("action")), "next_actor: %s" % code(feed_.next_actor(decision, feed)),
             "content_id: %s" % code(decision.get("content_id")), "pass: %s" % record["pass"], "release: %s" % record["release"]]
    evidence = decision.get("evidence") or []
    shown = [e for e in evidence if isinstance(e, str) and SHOWN.fullmatch(e)]
    hidden, kept = len(evidence) - len(shown), 0
    for e in shown[:SHOWN_MOST]:
        line = "evidence: %s" % e
        if len("\n".join(lines + [line])) + 64 > SUMMARY_MOST:
            break
        lines.append(line)
        kept += 1
    if len(shown) > kept:
        lines.append("and %d more" % (len(shown) - kept))
    if hidden:
        lines.append("and %d not shown" % hidden)
    return {"title": "%s: %s" % (code(decision.get("state")), code(decision.get("reason"))), "summary": "\n".join(lines)}


def write_status(transport, entry: dict, record: dict, config: dict, status: dict) -> tuple:
    """`(state, key, reason, wrote)` for the status on the item: one check run by the Controller's App for each head, edited
    in place, and sent only when the Decision changed (I-17). GitHub holds the key, so a status that once failed to write is
    not stale for ever. It never passes or fails, so it can be read as no gate; GitHub would count a neutral check as met, so
    what keeps it from being one is that no ruleset names it. P-12: `filter=all`, since `latest` lists only the later of two,
    and that later one is what GitHub shows; and GitHub answers a 200 that may not hold what was sent, so it is read back.
    `wrote` says a write was sent, whatever it answered: a write GitHub limited still counts against the bound."""
    decision, head, home = entry["decision"], entry["head"], config["home"]["repo"]
    want, name, app = status_id(decision), status["name"], status["app_id"]
    listed = _body(_sent(transport, request("GET", "/repos/%s/commits/%s/check-runs?check_name=%s&app_id=%d&filter=all&per_page=100" % (
        home, head, urllib.parse.quote(name, safe=""), app))), 200)
    runs = listed.get("check_runs") if isinstance(listed, dict) else None
    if not isinstance(runs, list) or listed.get("total_count") != len(runs) or len(runs) >= 100:
        return "failed", None, "checks_unreadable", False

    def ours(run) -> bool:
        return isinstance(run, dict) and run.get("name") == name and _body_of(run.get("app")).get("id") == app \
            and type(run.get("id")) is int

    def keyed(run) -> bool:
        return isinstance(run.get("node_id"), str) and STATUS_KEY.fullmatch(run["node_id"]) is not None

    mine = [r for r in runs if ours(r)]
    target = max(mine, key=lambda r: r["id"]) if mine else None
    if target is not None and target.get("external_id") == want and target.get("status") == "completed" and target.get("conclusion") == "neutral":
        return ("already_applied", target["node_id"], None, False) if keyed(target) else ("failed", None, "not_read_back", False)
    fields = {"external_id": want, "status": "completed", "conclusion": "neutral",
              "output": status_output(decision, record, status["feed"])}
    if status.get("run_id"):
        fields["details_url"] = "https://github.com/%s/actions/runs/%s" % (home, status["run_id"])
    if target is not None:
        answer, took = _sent(transport, request("PATCH", "/repos/%s/check-runs/%d" % (home, target["id"]), body=fields)), 200
    else:
        took = 201
        answer = _sent(transport, request("POST", "/repos/%s/check-runs" % home, body=dict(fields, name=name, head_sha=head)))
    back = _body(answer, took)
    if not isinstance(back, dict):
        fault = _fault(answer)
        return fault["state"], None, fault["reason"], True
    held = ours(back) and back.get("head_sha") == head and back.get("external_id") == want \
        and back.get("status") == "completed" and back.get("conclusion") == "neutral" \
        and (target is None or back.get("id") == target["id"]) and keyed(back)
    return ("applied", back["node_id"], None, True) if held else ("failed", None, "not_read_back", True)


def _body_of(value) -> dict:
    return value if isinstance(value, dict) else {}


def apply(writes: dict, record: dict, transports: dict, config: dict, owner_role: str, pause=None,
          issues=None, status=None) -> dict:
    """`written/1`: each write of the plan sent through its credential's transport, and what it did. `transports`
    maps a credential, `workflow` or `controller`, to its transport; one that is missing sends nothing. `owner_role` is
    the Role an approval is dispatched under, the configuration's. `pause` is the Pause as `adapters/pause.py` read it
    for `scopes(writes, config)` just before, and `issues` the open tracking issues as `open_issues` read them. `status`
    names what the status on an item is written with: its check's `name`, the Controller's `app_id`, the `feed` and the
    pass's `run_id`. A pass writes at most `max_status_writes` of them, in item order: the rest wait for the next."""
    problems = validate(config, SCHEMAS["controller"], schemas=SCHEMAS)
    if problems:
        raise Refused("the Controller's configuration does not validate: %s" % problems[0])
    _held(writes, record, owner_role)
    stopped = brake(pause, *scopes(writes, config))
    ended, out, status_sent = set(), [], 0
    entries = {(e["decision"]["item"]["repo"], e["decision"]["item"]["number"]): e for e in status_entries(record)}
    for w in writes["writes"]:
        state, reason, key = "refused", None, None
        if w["type"] == "not_built":
            reason = "not_built"
        elif w["type"] == "status_on_item":
            # A status is no act: it is written under a Pause, so that a person sees why nothing moves.
            if "controller" in ended:
                reason = "token_refused"
            elif transports.get("controller") is None or status is None:
                reason = "no_credential"
            elif status_sent >= config["max_status_writes"]:
                reason = "status_bounded"
            else:
                try:
                    state, key, reason, wrote = write_status(transports["controller"], entries[(w["item"]["repo"], w["item"]["number"])],
                                                             record, config, status)
                    status_sent += 1 if wrote else 0
                except _TokenRefused:
                    state, key, reason = "refused", None, "token_refused"
                    ended.add("controller")
        elif w["type"] == "tracking_issue":
            faults = any(o["state"] == "failed" or (o["state"] == "refused" and o["reason"] not in NO_FAULT)
                         for o in out)
            causes = sorted({a for a in record.get("alerts", []) if a != "paused"} | ({"write_failed"} if faults else set()))
            # It asks for itself: a 403 on a status may be GitHub's limit and not a refused token, and an alert is not lost to one.
            state, key, reason = tracking(transports.get("controller"), config, record, causes, issues)
        elif w["type"] in DISPATCHES:
            if stopped is not None and w["type"] in STOPPED:
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


# A Role's writes, `apply`'s: each on one item, through the Role App's own token, narrowed to them (issue 194, PR 2).
# A check run is written once the Role App is granted `checks`; until then its need waits, and no token is minted for it.
# No Role resolves a thread: the queue App does, as the Kernel's act (issue 389).
ROLE_WRITES = ("submit_review", "create_check_run", "comment")
# GitHub takes at most fifty annotations in one request: more would need a second write, which nothing sends yet.
ANNOTATIONS = 50
LEVEL = {"minor": "warning", "info": "notice"}
SHA = re.compile(r"[0-9a-f]{40}")
# A check run's key: the Run's id and the Effect's.
EXTERNAL = re.compile(r"r_[0-9A-Z]{6,26}:e[0-9]{1,3}")
THREADS = """query AppliedThreads($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        totalCount
        nodes { id comments(first: 1) { nodes { databaseId pullRequestReview { databaseId } } } }
      }
    }
  }
}"""
THREAD_ID = re.compile(r"PRRT_[A-Za-z0-9_-]+")
SINCE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def role_permits(item: dict, head: str, name: str) -> tuple:
    """`(permits, patterns)`: what a Role App's token may send on one item, for `Allowed`. A review on it, a comment
    on it, its check run, named `name`, on its head, `head`, and the reads that recover and read each back; nothing
    else, on no other item. No Role resolves a thread (issue 389)."""
    repo, number = item["repo"], item["number"]
    pull, issue = "/repos/%s/pulls/%d" % (repo, number), "/repos/%s/issues/%d" % (repo, number)
    owner, repo_name = repo.split("/")

    def nothing(body) -> bool:
        return body is None

    def review(body) -> bool:
        return (isinstance(body, dict) and set(body) == {"commit_id", "event", "body", "comments"}
                and body["event"] == "COMMENT" and body["commit_id"] == head and isinstance(body["comments"], list))

    def comment(body) -> bool:
        return isinstance(body, dict) and set(body) == {"body"} and isinstance(body["body"], str)

    def graphql(body) -> bool:
        if not isinstance(body, dict) or set(body) != {"query", "variables"}:
            return False
        return body["query"] == THREADS and body["variables"] == {"owner": owner, "name": repo_name, "number": number}
    def check(body) -> bool:
        return (isinstance(body, dict) and set(body) == {"name", "head_sha", "external_id", "status", "conclusion",
                                                          "output"}
                and body["status"] == "completed" and body["name"] == name and body["head_sha"] == head
                and body["conclusion"] == "success" and isinstance(body["external_id"], str)
                and EXTERNAL.fullmatch(body["external_id"]) is not None
                and isinstance(body["head_sha"], str) and SHA.fullmatch(body["head_sha"]) is not None)
    permits = {("GET", pull + "/reviews?per_page=100"): nothing, ("POST", pull + "/reviews"): review,
               ("POST", issue + "/comments"): comment, ("POST", "/graphql"): graphql,
               ("POST", "/repos/%s/check-runs" % repo): check}
    patterns = [("GET", re.compile(re.escape(pull) + r"/reviews/[1-9][0-9]{0,18}"), nothing),
                ("GET", re.compile(r"/repos/%s/check-runs/[1-9][0-9]{0,18}" % re.escape(repo)), nothing),
                ("GET", re.compile(r"/repos/%s/commits/[0-9a-f]{40}/check-runs\?check_name=[A-Za-z0-9%%._-]+&filter=all&per_page=100"
                                   % re.escape(repo)), nothing),
                ("GET", re.compile(r"/repos/%s/issues/comments/[1-9][0-9]{0,18}" % re.escape(repo)), nothing),
                ("GET", re.compile(re.escape(issue) + r"/comments\?since=%s&per_page=100" % SINCE.pattern), nothing)]
    return permits, patterns


class _TokenRefused(Exception):
    """GitHub would not take the credential, on a read or a write: the write ends refused, and so does every later one."""


def _sent(transport, req: dict):
    """GitHub's answer, or None where it gave none. Nothing is sent twice. A 401 or 403, to a read as to a write, ends
    the write: the credential is refused."""
    try:
        answer = transport.send(req)
    except Unanswered:
        return None
    if isinstance(answer, dict) and answer.get("status") in REFUSED:
        raise _TokenRefused()
    return answer


def _fault(answer) -> dict:
    """A write GitHub did not take: failed for no answer or one it did not take. A credential it would not take never
    reaches here: `_sent` ends the write refused."""
    if answer is None or answer.get("status", 500) >= 500:
        return _back("failed", None, reason="write_unanswered")
    return _back("failed", None, reason="write_refused")


def _back(state: str, key, surfaces=None, reason=None) -> dict:
    return {"state": state, "key": key, "surfaces": dict(surfaces or {}), "reason": reason}


def _body(answer, status: int):
    return answer.get("body") if isinstance(answer, dict) and answer.get("status") == status else None


def _data(answer):
    body = _body(answer, 200)
    return body.get("data") if isinstance(body, dict) and not body.get("errors") else None


def role_write(transport, item: dict, kind: str, req: dict, login: str) -> dict:
    """What one of a Role's writes did, read back: `{state, key, surfaces, reason}`. `applied` or `already_applied`
    only with the key it was read back by, and for a review each comment's thread; `sent` for one GitHub took whose
    read-back failed, so that nothing is claimed for it."""
    try:
        if kind == "submit_review":
            return _review(transport, item, req, login)
        if kind == "create_check_run":
            return _check(transport, item, req, login)
        if kind == "comment" and req["on"] == "item":
            return _comment(transport, item, req, login)
    except _TokenRefused:
        return _back("refused", None, reason="token_refused")
    return _back("failed", None, reason="not_built")


def _place(comment: dict) -> dict:
    out = {"path": comment["path"], "line": comment["end_line"], "side": "RIGHT", "body": comment["body"]}
    if comment["start_line"] < comment["end_line"]:
        out.update(start_line=comment["start_line"], start_side="RIGHT")
    return out


def _review(transport, item: dict, req: dict, login: str) -> dict:
    """A review: recovered as one by this App on this commit (section 3.6), else submitted as a comment; read back by
    its id, on the commit, by this App, and each of its comments' threads in the order they were asked."""
    pull = "/repos/%s/pulls/%d" % (item["repo"], item["number"])
    listed = _body(_sent(transport, request("GET", pull + "/reviews?per_page=100")), 200)
    if not isinstance(listed, list) or len(listed) >= 100:
        return _back("failed", None, reason="reviews_unreadable")
    mine = [r for r in listed if isinstance(r, dict) and isinstance(r.get("user"), dict)
            and r["user"].get("login") == login and r.get("commit_id") == req["commit"]]
    if len(mine) > 1:
        return _back("failed", None, reason="reviewed_twice")
    state, review = ("already_applied", mine[0]) if mine else ("applied", None)
    if review is None:
        answer = _sent(transport, request("POST", pull + "/reviews", body={
            "commit_id": req["commit"], "event": "COMMENT", "body": req["body"],
            "comments": [_place(c) for c in req["comments"]]}))
        review = _body(answer, 200)
        if not isinstance(review, dict):
            return _fault(answer)
    rid = review.get("id")
    back = _body(_sent(transport, request("GET", pull + "/reviews/%d" % rid)), 200) if type(rid) is int else None
    if not (isinstance(back, dict) and back.get("id") == rid and back.get("commit_id") == req["commit"]
            and back.get("state") == "COMMENTED" and isinstance(back.get("user"), dict)
            and back["user"].get("login") == login and isinstance(back.get("node_id"), str) and back["node_id"]):
        return _back("sent", None)
    threads = _threads(transport, item, rid)
    if threads is None or len(threads) != len(req["comments"]):
        return _back("sent", None)
    return _back(state, back["node_id"], {c["finding"]: th for c, th in zip(req["comments"], threads)})


def _check(transport, item: dict, req: dict, login: str) -> dict:
    """A check run: recovered by its `external_id`, the Effect's own, on the commit (section 3.6), else made once,
    complete, with its annotations; read back by its id, by this App, on the commit, with as many annotations as were
    asked. Each annotation's surface is the check run's key and the Finding's ref."""
    if len(req["annotations"]) > ANNOTATIONS:
        return _back("failed", None, reason="too_many_annotations")
    repo, app = item["repo"], login[: -len("[bot]")] if login.endswith("[bot]") else login
    listed = _body(_sent(transport, request("GET", "/repos/%s/commits/%s/check-runs?check_name=%s&filter=all&per_page=100" % (
        repo, req["commit"], urllib.parse.quote(req["name"], safe="")))), 200)
    runs = listed.get("check_runs") if isinstance(listed, dict) else None
    if not isinstance(runs, list) or listed.get("total_count") != len(runs) or len(runs) >= 100:
        return _back("failed", None, reason="checks_unreadable")
    mine = [r for r in runs if isinstance(r, dict) and r.get("external_id") == req["external_id"]
            and isinstance(r.get("app"), dict) and r["app"].get("slug") == app]
    if len(mine) > 1:
        return _back("failed", None, reason="checked_twice")
    state, made = ("already_applied", mine[0]) if mine else ("applied", None)
    if made is None:
        answer = _sent(transport, request("POST", "/repos/%s/check-runs" % repo, body={
            "name": req["name"], "head_sha": req["commit"], "external_id": req["external_id"], "status": "completed",
            "conclusion": req["conclusion"], "output": {
                "title": req["name"], "summary": "%d finding(s) that do not gate" % len(req["annotations"]),
                "annotations": [{"path": a["path"], "start_line": a["start_line"], "end_line": a["end_line"],
                                 "annotation_level": LEVEL.get(a["severity"], "notice"), "message": a["body"]}
                                for a in req["annotations"]]}}))
        made = _body(answer, 201)
        if not isinstance(made, dict):
            return _fault(answer)
    cid = made.get("id")
    back = _body(_sent(transport, request("GET", "/repos/%s/check-runs/%d" % (repo, cid))), 200) \
        if type(cid) is int else None
    if not (isinstance(back, dict) and back.get("id") == cid and back.get("external_id") == req["external_id"]
            and back.get("name") == req["name"] and back.get("status") == "completed"
            and back.get("conclusion") == req["conclusion"]
            and back.get("head_sha") == req["commit"] and isinstance(back.get("app"), dict)
            and back["app"].get("slug") == app and isinstance(back.get("output"), dict)
            and back["output"].get("annotations_count") == len(req["annotations"])
            and isinstance(back.get("node_id"), str) and back["node_id"]):
        return _back("sent", None)
    key = back["node_id"]
    return _back(state, key, {a["finding"]: "%s:%s" % (key, a["finding"]) for a in req["annotations"]})


def _threads(transport, item: dict, review: int):
    """The threads review `review` opened, in the order its comments were made, or None where they cannot be read."""
    owner, name = item["repo"].split("/")
    data = _data(_sent(transport, request("POST", "/graphql", body={
        "query": THREADS, "variables": {"owner": owner, "name": name, "number": item["number"]}})))
    try:
        threads = data["repository"]["pullRequest"]["reviewThreads"]
        if threads["totalCount"] > 100 or threads["totalCount"] != len(threads["nodes"]):
            return None
        opened = []
        for node in threads["nodes"]:
            first = node["comments"]["nodes"][0]
            if (first["pullRequestReview"] or {}).get("databaseId") == review:
                if type(first["databaseId"]) is not int:
                    return None
                opened.append((first["databaseId"], node["id"]))
    except (KeyError, TypeError, IndexError):
        return None
    if any(not isinstance(th, str) or not THREAD_ID.fullmatch(th) for _, th in opened):
        return None
    return [th for _, th in sorted(opened)]


def _comment(transport, item: dict, req: dict, login: str) -> dict:
    """A comment on the item. A comment has no key (section 3.6): the Result is its intent record, and one already
    made is recovered by listing this App's comments since the Run began, never by its text, the `index`-th of them
    this Run's `index`-th comment."""
    issue = "/repos/%s/issues/%d/comments" % (item["repo"], item["number"])
    listed = _body(_sent(transport, request("GET", issue + "?since=%s&per_page=100" % req["since"])), 200)
    if not isinstance(listed, list) or len(listed) >= 100:
        return _back("failed", None, reason="comments_unreadable")
    # `since` lists comments updated since then: one made before the Run and edited since is not this Run's.
    mine = sorted((c for c in listed if isinstance(c, dict) and isinstance(c.get("user"), dict)
                   and c["user"].get("login") == login and type(c.get("id")) is int
                   and isinstance(c.get("created_at"), str) and c["created_at"] >= req["since"]), key=lambda c: c["id"])
    state = "already_applied" if len(mine) > req["index"] else "applied"
    if state == "applied":
        answer = _sent(transport, request("POST", issue, body={"body": req["body"]}))
        made = _body(answer, 201)
        if not isinstance(made, dict) or type(made.get("id")) is not int:
            return _fault(answer)
        cid = made["id"]
    else:
        cid = mine[req["index"]]["id"]
    back = _body(_sent(transport, request("GET", "/repos/%s/issues/comments/%d" % (item["repo"], cid))), 200)
    if not (isinstance(back, dict) and back.get("id") == cid and isinstance(back.get("user"), dict)
            and back["user"].get("login") == login and isinstance(back.get("node_id"), str) and back["node_id"]):
        return _back("sent", None)
    return _back(state, back["node_id"])
# The machine user's approval, the approving act's one write (issue 195, ruling 4): through the approver's own token,
# whose transport may read the item's repo, who the token is and the org's Pause, ask the facts port's own GraphQL reads
# of this pull request, and write one review, the approval of the commit the act read, with nothing else in it.
UNAVAILABLE = 429      # with no answer and any 5xx, GitHub's own trouble: the environment's
GONE = 404             # with 401 and 403, a token GitHub will not take for this item: the environment's


class Approving:
    """The approver's transport, narrowed to what one step may send, and anything else refused before it leaves. With
    no item, it may ask only who the token is; with an item, also read that item's repo, the org's Pause among it as the
    repo's list of the org's variables (issue 362), and the facts
    port's own GraphQL reads of that pull request; with the head the act just read as well, also write one review, the
    approval of that commit and nothing else in it. No path may climb out of the item's repo."""

    def __init__(self, transport, item: dict = None, head: str = None):
        self._transport, self._item, self._head = transport, dict(item) if item else None, head
        if item:
            self._repo = "/repos/%s/" % item["repo"]
            self._reviews = "/repos/%s/pulls/%d/reviews" % (item["repo"], item["number"])

    def _read(self, path) -> bool:
        if not isinstance(path, str) or ".." in path or "%2e" in path.lower() or "//" in path:
            return False
        return path == "/user" or (self._item is not None and path.startswith(self._repo))

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
    """GitHub's answer, or None where it gave none, whatever its status: the approval classes a refused token by its
    status itself (ruling 6), where `_sent` ends the Role's writes on it. Nothing is sent twice."""
    try:
        return transport.send(req)
    except Unanswered:
        return None


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
    body = _body(answer, 200)
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
    `{state, key, fault, reason}`, `already_applied` with its node id and when it was submitted, `at`, or a state of
    None where there is none. A list that cannot be read, or that may be cut short, recovers nothing."""
    answer = _asked(transport, request("GET", "/repos/%s/pulls/%d/reviews?per_page=100" % (item["repo"], item["number"])))
    listed = _body(answer, 200)
    if not isinstance(listed, list) or len(listed) >= 100:
        fault, reason = _trouble(answer, "facts_unreadable")
        return {"state": None, "key": None, "fault": fault, "reason": reason}
    # The approver's latest review of this commit is the one that stands: a request for changes after an approval
    # supersedes it (the fresh review).
    mine = [r for r in listed if isinstance(r, dict) and r.get("commit_id") == head and isinstance(r.get("user"), dict)
            and r["user"].get("login") == login]
    if mine and _approval(mine[-1], head, login):
        return {"state": "already_applied", "key": mine[-1]["node_id"], "fault": None, "reason": None,
                "at": mine[-1].get("submitted_at")}
    return {"state": None, "key": None, "fault": None, "reason": None}


def _open_at(transport, pull: str, head: str, state: str):
    """None while the pull request is open at `head`; else the act's result, in `state`: a pull request closed or
    merged is `not_open`, one at another head `head_moved`, both a change under the act; one that cannot be read is
    whose fault its status says."""
    again = _asked(transport, request("GET", pull))
    now = _body(again, 200)
    if not isinstance(now, dict) or now.get("state") not in ("open", "closed") or not isinstance(now.get("head"), dict) \
            or not isinstance(now["head"].get("sha"), str):
        # The pull request read again cannot be read: whose fault, by its status alone (Codex on PR 321).
        fault, reason = _trouble(again, "github_unavailable")
        return {"state": state, "key": None, "fault": fault, "reason": reason}
    if now.get("state") != "open" or now.get("merged") is True:
        return {"state": state, "key": None, "fault": "superseded", "reason": "not_open"}
    if now["head"].get("sha") != head:
        return {"state": state, "key": None, "fault": "superseded", "reason": "head_moved"}
    return None


def approve(transport, item: dict, head: str, login: str) -> dict:
    """The approval of `head`, sent once and read back: `{state, key, fault, reason}`. `applied` only with the node id
    of the approver's own approval of that commit, read back by the id GitHub answered (L-41). Whose fault a failure
    was is read from its status and from the pull request read again, never from GitHub's words (ruling 6).

    GitHub takes an approval of a pull request that is closed (trials/P-7.refused.json, issue 378), so the pull request
    is read open at `head` before the approval is sent, and nothing is sent to one that is not; and read again after it,
    so that one closed between the two claims nothing (`superseded`, `closed_under_act`)."""
    pull = "/repos/%s/pulls/%d" % (item["repo"], item["number"])
    closed = _open_at(transport, pull, head, "refused")
    if closed is not None:
        return closed
    answer = _asked(transport, request("POST", pull + "/reviews", body={"commit_id": head, "event": "APPROVE"}))
    review = _body(answer, 200)
    if not isinstance(review, dict):
        status = answer.get("status") if isinstance(answer, dict) else None
        if status in REFUSED or status == GONE:
            return {"state": "refused", "key": None, "fault": "environment", "reason": "token_refused"}
        if status is None or status >= 500 or status == UNAVAILABLE:
            return {"state": "failed", "key": None, "fault": "environment", "reason": "github_unavailable"}
        if 200 <= status < 300:
            # GitHub took it and the answer cannot be read: the approval may stand, and nothing is claimed for it.
            return {"state": "failed", "key": None, "fault": "environment", "reason": "not_read_back"}
        # Any other refusal is the item's, while the pull request is open at the commit; one closed or at another head
        # since it was read is a change under the act. GitHub refuses an approval of a commit a push left behind, but
        # takes one of a pull request that is closed (trials/P-7.refused.json), so a close is read here, not assumed.
        changed = _open_at(transport, pull, head, "failed")
        if changed is not None:
            return changed
        return {"state": "failed", "key": None, "fault": "item", "reason": "approval_refused"}
    rid = review.get("id")
    back = _body(_asked(transport, request("GET", pull + "/reviews/%d" % rid)), 200) if type(rid) is int else None
    if not isinstance(back, dict) or back.get("id") != rid:
        return {"state": "failed", "key": None, "fault": "environment", "reason": "not_read_back"}
    if not _approval(back, head, login):
        return {"state": "failed", "key": None, "fault": "item", "reason": "read_back_differs"}
    # A pull request closed or merged between the read and the approval took it all the same: the act claims nothing
    # for it, so reconciliation names the approval standing with no Effect, and the Kernel does not count it after a
    # reopening (issue 378). One at another head now holds an approval of a commit it no longer carries, which the
    # Kernel reads by its content; one that cannot be read claims nothing.
    after = _open_at(transport, pull, head, "failed")
    if after is not None and after["reason"] == "not_open":
        return {"state": "failed", "key": None, "fault": "superseded", "reason": "closed_under_act"}
    if after is not None and after["fault"] != "superseded":
        return {"state": "failed", "key": None, "fault": "environment", "reason": "not_read_back"}
    return {"state": "applied", "key": back["node_id"], "fault": None, "reason": None}


# The Controller's writes and reads in this step, by the needs config/apps.json names: those the App is granted
# are minted, and one that waits on its grant is not, so its write is refused for want of a credential. The Pause is
# read again before any dispatch (decision 0056), with the variables' read P-52 showed it takes.
CONTROLLER_NEEDS = ("write:status_on_item", "write:tracking_issue", "read:pass.pause")


def controller_token(environ: dict, config: dict, now: int, connect=None) -> tuple:
    """`(transport, revoke)`: the Controller App's token for the home repo, minted from `CONTROLLER_APP_KEY` with the
    needs among `CONTROLLER_NEEDS` the App is granted, or `(None, None)` when there is no key or none is granted."""
    apps = json.loads((ROOT / "config" / "apps.json").read_text())
    app = apps["apps"]["controller"]
    wanted = {}
    for name in CONTROLLER_NEEDS:
        try:
            for permission, level in identity.granted(app, apps["needs"], [name], "write").items():
                wanted[permission] = max(wanted.get(permission, "read"), level, key=identity.LEVELS.index)
        except identity.Refused:
            continue
    if not environ.get("CONTROLLER_APP_KEY") or not wanted:
        return None, None
    return identity.from_key(app, config["home"]["repo"], wanted, environ["CONTROLLER_APP_KEY"], now, connect or Live)


def main(argv=None, environ=None, base=None, mint=None, clock=None) -> int:
    """The step. It reads and writes only inside the directory it runs in, `base`, by default the working directory:
    each path is followed to where it really is, and one outside is refused before anything is opened, naming no path.
    The Controller's token is minted from its App's key, `CONTROLLER_APP_KEY`, by `mint(environ, config)`, and revoked
    when the writes end; one GitHub did not revoke fails the step."""
    argv = sys.argv[1:] if argv is None else argv
    environ = os.environ if environ is None else environ
    inside = os.path.realpath(str(pathlib.Path.cwd() if base is None else base))
    # The workflow's form: the pass's own folder, which `python3 -m controller` wrote, and written.json beside it.
    argv = argv or ["pass/pass.json", "pass/writes.json", "pass"]
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
    sent, revoke = True, None
    try:
        # The plan is held to its record before anything is read with a token: a plan that is not the record's
        # names no scope to read and asks nothing.
        if validate(config, SCHEMAS["controller"], schemas=SCHEMAS):
            raise Refused("the Controller's configuration does not validate")
        _held(writes, record, owner_role)
        transports = {"workflow": Allowed(Live(token), workflow_permits(config)) if token else None,
                      "controller": None}
        if mint is None:
            own, revoke = controller_token(environ, config, int((clock or time.time)()))
        else:
            own, revoke = mint(environ, config)
        if own is not None:
            org, repos = scopes(writes, config)
            transports["controller"] = Allowed(own, *controller_permits(config, org, repos))
        org, repos = scopes(writes, config) if transports["controller"] else ("", [])
        read = pause_.read(transports["controller"], org, repos)
        defaults = json.loads((ROOT / "config" / "defaults.json").read_text())
        run_id = environ.get("GITHUB_RUN_ID")
        status = {"name": defaults["status_on_item"], "feed": json.loads((ROOT / "config" / "feed.json").read_text()),
                  "app_id": json.loads((ROOT / "config" / "apps.json").read_text())["apps"]["controller"]["app_id"],
                  "run_id": run_id if isinstance(run_id, str) and DIGITS.fullmatch(run_id) else None}
        written = apply(writes, record, transports, config, owner_role, pause=read,
                        issues=open_issues(transports["controller"], config), status=status)
    except Unanswered:
        written, sent = refused_all(writes, record, "token_unreadable"), False
    except Refused:
        written, sent = refused_all(writes, record, "plan_refused"), False
    except identity.Refused:     # the key could not mint a token: every write refused, and the step fails
        written, sent = refused_all(writes, record, "token_unreadable"), False
    finally:
        revoked = revoke() if revoke is not None else True
    sent = sent and revoked is True
    with open(os.path.join(out, "written.json"), "w", encoding="utf-8") as kept:
        kept.write(json.dumps(written, indent=2) + "\n")
    return 0 if sent and not failed(written) else 1


if __name__ == "__main__":
    sys.exit(main())
