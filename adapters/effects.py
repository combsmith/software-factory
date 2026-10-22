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
import urllib.parse

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


# A Role's writes, `apply`'s: each on one item, through the Role App's own token, narrowed to them (issue 194, PR 2).
# A check run is written once the Role App is granted `checks`; until then its need waits, and no token is minted for it.
ROLE_WRITES = ("submit_review", "create_check_run", "resolve_thread", "comment")
# GitHub takes at most fifty annotations in one request: more would need a second write, which nothing sends yet.
ANNOTATIONS = 50
LEVEL = {"minor": "warning", "info": "notice"}
SHA = re.compile(r"[0-9a-f]{40}")
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
THREAD = """query AppliedThread($id: ID!) {
  node(id: $id) {
    ... on PullRequestReviewThread { id isResolved pullRequest { number repository { nameWithOwner } } }
  }
}"""
RESOLVE = """mutation AppliedResolve($id: ID!) {
  resolveReviewThread(input: {threadId: $id}) { thread { id isResolved } }
}"""
THREAD_ID = re.compile(r"PRRT_[A-Za-z0-9_-]+")
SINCE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def role_permits(item: dict, head: str, name: str, threads) -> tuple:
    """`(permits, patterns)`: what a Role App's token may send on one item, for `Allowed`. A review on it, a comment
    on it, its check run, named `name`, on its head, `head`, the resolution of one of its threads, `threads`, and the
    reads that recover and read each back; nothing else, on no other item."""
    threads = frozenset(threads)
    repo, number = item["repo"], item["number"]
    pull, issue = "/repos/%s/pulls/%d" % (repo, number), "/repos/%s/issues/%d" % (repo, number)
    owner, repo_name = repo.split("/")

    def nothing(body) -> bool:
        return body is None

    def review(body) -> bool:
        return (isinstance(body, dict) and set(body) == {"commit_id", "event", "body", "comments"}
                and body["event"] == "COMMENT" and isinstance(body["comments"], list))

    def comment(body) -> bool:
        return isinstance(body, dict) and set(body) == {"body"} and isinstance(body["body"], str)

    def graphql(body) -> bool:
        if not isinstance(body, dict) or set(body) != {"query", "variables"}:
            return False
        if body["query"] == THREADS:
            return body["variables"] == {"owner": owner, "name": repo_name, "number": number}
        return (body["query"] in (THREAD, RESOLVE) and set(body["variables"]) == {"id"}
                and isinstance(body["variables"]["id"], str) and THREAD_ID.fullmatch(body["variables"]["id"]) is not None
                and body["variables"]["id"] in threads)
    def check(body) -> bool:
        return (isinstance(body, dict) and set(body) == {"name", "head_sha", "external_id", "status", "conclusion",
                                                          "output"}
                and body["status"] == "completed" and body["name"] == name and body["head_sha"] == head
                and isinstance(body["head_sha"], str) and SHA.fullmatch(body["head_sha"]) is not None)
    permits = {("GET", pull + "/reviews?per_page=100"): nothing, ("POST", pull + "/reviews"): review,
               ("POST", issue + "/comments"): comment, ("POST", "/graphql"): graphql,
               ("POST", "/repos/%s/check-runs" % repo): check}
    patterns = [("GET", re.compile(re.escape(pull) + r"/reviews/[1-9][0-9]{0,18}"), nothing),
                ("GET", re.compile(r"/repos/%s/check-runs/[1-9][0-9]{0,18}" % re.escape(repo)), nothing),
                ("GET", re.compile(r"/repos/%s/commits/[0-9a-f]{40}/check-runs\?check_name=[A-Za-z0-9%%._-]+&per_page=100"
                                   % re.escape(repo)), nothing),
                ("GET", re.compile(r"/repos/%s/issues/comments/[1-9][0-9]{0,18}" % re.escape(repo)), nothing),
                ("GET", re.compile(re.escape(issue) + r"/comments\?since=%s&per_page=100" % SINCE.pattern), nothing)]
    return permits, patterns


def _sent(transport, req: dict):
    """GitHub's answer, or None where it gave none. Nothing is sent twice."""
    try:
        return transport.send(req)
    except Unanswered:
        return None


def _fault(answer) -> dict:
    """A write GitHub did not take: refused for a credential it would not take, which ends every later write on it, or
    failed for no answer or one it did not take."""
    if answer is not None and answer.get("status") in REFUSED:
        return _back("refused", None, reason="token_refused")
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
    if kind == "submit_review":
        return _review(transport, item, req, login)
    if kind == "create_check_run":
        return _check(transport, item, req, login)
    if kind == "resolve_thread":
        return _resolve(transport, item, req)
    if kind == "comment" and req["on"] == "item":
        return _comment(transport, item, req, login)
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
    listed = _body(_sent(transport, request("GET", "/repos/%s/commits/%s/check-runs?check_name=%s&per_page=100" % (
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


def _thread(transport, item: dict, thread: str):
    """A thread as read: True or False for whether it is resolved, `elsewhere` for one not on the item, None unread."""
    data = _data(_sent(transport, request("POST", "/graphql", body={"query": THREAD, "variables": {"id": thread}})))
    node = data.get("node") if isinstance(data, dict) else None
    if not isinstance(node, dict) or node.get("id") != thread or not isinstance(node.get("isResolved"), bool):
        return None
    pr = node.get("pullRequest") if isinstance(node.get("pullRequest"), dict) else {}
    if pr.get("number") != item["number"] or (pr.get("repository") or {}).get("nameWithOwner") != item["repo"]:
        return "elsewhere"
    return node["isResolved"]


def _resolve(transport, item: dict, req: dict) -> dict:
    """A thread's resolution: recovered by its resolved flag, else resolved, and read back resolved."""
    before = _thread(transport, item, req["thread"])
    if before is None:
        return _back("failed", None, reason="thread_unreadable")
    if before == "elsewhere":
        return _back("refused", None, reason="thread_not_on_item")
    if before is True:
        return _back("already_applied", req["thread"])
    answer = _sent(transport, request("POST", "/graphql", body={"query": RESOLVE, "variables": {"id": req["thread"]}}))
    if _data(answer) is None:
        return _fault(answer if answer is None or answer.get("status") != 200 else dict(answer, status=422))
    return _back("applied", req["thread"]) if _thread(transport, item, req["thread"]) is True else _back("sent", None)


def _comment(transport, item: dict, req: dict, login: str) -> dict:
    """A comment on the item. A comment has no key (section 3.6): the Result is its intent record, and one already
    made is recovered by listing this App's comments since the Run began, never by its text, the `index`-th of them
    this Run's `index`-th comment."""
    issue = "/repos/%s/issues/%d/comments" % (item["repo"], item["number"])
    listed = _body(_sent(transport, request("GET", issue + "?since=%s&per_page=100" % req["since"])), 200)
    if not isinstance(listed, list) or len(listed) >= 100:
        return _back("failed", None, reason="comments_unreadable")
    mine = sorted((c for c in listed if isinstance(c, dict) and isinstance(c.get("user"), dict)
                   and c["user"].get("login") == login and type(c.get("id")) is int), key=lambda c: c["id"])
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
