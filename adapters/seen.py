"""The seen port: the writes each Factory identity made on a served pull request since a moment, as GitHub records them,
for reconciliation (I-33, decision 0061, the working ruling on "Controller: reconciliation, every write by a Factory
identity matched to a recorded Effect (I-33)", issue 306).

`read(transport, item, head, identities, apps, since)` reads, with the Controller's App's token: the pull request's
reviews, its comments since `since`, its timeline's events, its review threads and the check runs on `head`.
`pushes(transport, repo, approver, since)` reads the repo's activity by the machine user. Each write is told by the
account that made it, by id and type, never a login's spelling (`identities`, `{(id, type): code}`), or for a check
run by its App's id (`apps`, `{app_id: code}`); anything by anyone else is left out, but a merge by anyone, which
reconciliation reads for an Override. A thread GitHub names no resolver for, as when an App resolved it, is
`unattributed`. A list that cannot be read whole, or may be cut short, leaves what was read `whole` false, so that
reconciliation is short, never silent; nothing is guessed. Ids and codes alone: no body or title is kept.

Whether the comments read is served by `pull_requests: read` alone is a trial of the second token window's
(`tests/test_reconcile.py::test_the_comments_on_a_pull_request_are_read_with_pull_requests_read`, pending).
"""
from __future__ import annotations

import re

from adapters import threads
from adapters.github import Unanswered, request

PAGE = 100          # a list read once: one as long as a page may be cut short
AT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
KEY = re.compile(r"[A-Za-z0-9_=:-]{1,100}")
# The timeline's events that are writes, and what each is.
EVENTS = {"labeled": "label", "unlabeled": "label", "added_to_merge_queue": "enqueue",
          "removed_from_merge_queue": "dequeue", "merged": "merge"}


def _listed(transport, path: str):
    """A list GitHub answered whole in one page, or None."""
    try:
        answer = transport.send(request("GET", path))
    except Unanswered:
        return None
    body = answer.get("body") if answer.get("status") == 200 else None
    if isinstance(body, dict) and isinstance(body.get("check_runs"), list):
        return body["check_runs"] if body.get("total_count") == len(body["check_runs"]) < PAGE else None
    return body if isinstance(body, list) and len(body) < PAGE else None


def _who(actor, identities: dict):
    if not isinstance(actor, dict) or not isinstance(actor.get("id"), int) or isinstance(actor.get("id"), bool):
        return None
    return identities.get((actor["id"], actor.get("type")))


def _at(text, since: str):
    """The moment, if it is one and not before `since`; None if it is before; False if it cannot be read."""
    if not isinstance(text, str) or not AT.fullmatch(text):
        return False
    return text if text >= since else None


def _key(value):
    return value if isinstance(value, str) and KEY.fullmatch(value) else None


def read(transport, item: dict, head: str, identities: dict, apps: dict, since: str) -> tuple:
    """`(writes, merged, whole)` for one served pull request."""
    repo, number = item["repo"], item["number"]
    pull, issue = "/repos/%s/pulls/%d" % (repo, number), "/repos/%s/issues/%d" % (repo, number)
    writes, merged, whole = [], [], True

    def add(by, kind, key, at):
        writes.append({"by": by, "kind": kind, "item": dict(item), "key": key, "at": at})

    reviews = _listed(transport, pull + "/reviews?per_page=%d" % PAGE)
    whole &= reviews is not None
    for r in reviews or []:
        by, at = _who(r.get("user") if isinstance(r, dict) else None, identities), _at((r or {}).get("submitted_at"), since)
        if by is None or at is None:
            continue
        kind = "approval" if r.get("state") == "APPROVED" else "review"
        whole &= at is not False and _key(r.get("node_id")) is not None
        add(by, kind, _key(r.get("node_id")), at or None)
    comments = _listed(transport, issue + "/comments?since=%s&per_page=%d" % (since, PAGE))
    whole &= comments is not None
    for c in comments or []:
        by, at = _who(c.get("user") if isinstance(c, dict) else None, identities), _at((c or {}).get("created_at"), since)
        if by is None or at is None:
            continue
        whole &= at is not False and _key(c.get("node_id")) is not None
        add(by, "comment", _key(c.get("node_id")), at or None)
    events = _listed(transport, issue + "/timeline?per_page=%d" % PAGE)
    whole &= events is not None
    for e in events or []:
        kind = EVENTS.get(e.get("event")) if isinstance(e, dict) else None
        at = _at(e.get("created_at"), since) if kind else None
        if kind is None or at is None:
            continue
        whole &= at is not False
        if kind == "merge" and at:
            merged.append({"item": dict(item), "at": at})
        by = _who(e.get("actor"), identities)
        if by is not None:
            add(by, kind, None, at or None)
    owner, name = repo.split("/")
    try:
        answer = transport.send(request("POST", "/graphql", body={"query": threads.QUERY, "variables": {
            "owner": owner, "name": name, "number": number, "after": None}}))
        found = (((answer.get("body") or {}).get("data") or {}).get("repository") or {}).get("pullRequest") or {}
        listed = (found.get("reviewThreads") or {}) if answer.get("status") == 200 else {}
        nodes = listed.get("nodes") if isinstance(listed.get("nodes"), list) else None
    except (Unanswered, AttributeError):
        nodes, listed = None, {}
    whole &= nodes is not None and listed.get("totalCount") == len(nodes) and not (listed.get("pageInfo") or {}).get(
        "hasNextPage")
    for t in nodes or []:
        if not isinstance(t, dict) or t.get("isResolved") is not True:
            continue
        resolver = t.get("resolvedBy")
        if resolver is None:
            by = "unattributed"
        else:
            by = _who({"id": (resolver or {}).get("databaseId"), "type": "User"}, identities)
        if by is not None:
            add(by, "resolution", _key(t.get("id")), None)
    runs = _listed(transport, "/repos/%s/commits/%s/check-runs?per_page=%d" % (repo, head, PAGE))
    whole &= runs is not None
    for r in runs or []:
        app = (r.get("app") or {}).get("id") if isinstance(r, dict) and isinstance(r.get("app"), dict) else None
        by = apps.get(app) if isinstance(app, int) and not isinstance(app, bool) else None
        at = _at(r.get("started_at"), since) if by is not None else None
        if by is None or at is None:
            continue
        whole &= at is not False and _key(r.get("node_id")) is not None
        add(by, "check_run", _key(r.get("node_id")), at or None)
    return writes, merged, bool(whole)


def pushes(transport, repo: str, approver: dict, since: str) -> tuple:
    """`(writes, whole)`: each push the machine user made to any branch of `repo` in the last day, from the repo's
    activity, as P-47 reads a branch's (`contents: read`). Every one is a write the machine user may not make."""
    found = _listed(transport, "/repos/%s/activity?actor=%s&time_period=day&per_page=%d" % (repo, approver["login"], PAGE))
    writes = []
    whole = found is not None
    for a in found or []:
        actor = a.get("actor") if isinstance(a, dict) else None
        if not isinstance(actor, dict) or (actor.get("id"), actor.get("type")) != (approver["id"], "User"):
            continue
        at = _at(a.get("timestamp"), since)
        if at is None:
            continue
        whole &= at is not False
        writes.append({"by": "approver", "kind": "push", "item": None, "key": str(a.get("id")) if isinstance(
            a.get("id"), int) else None, "at": at or None})
    return writes, bool(whole)


def seen(parts: list, since: str) -> dict:
    """`seen/1` from each `read`'s and `pushes`'s answer: whole only when every part was."""
    writes, merged, whole = [], [], True
    for part in parts:
        writes += part[0]
        merged += part[1] if len(part) == 3 else []
        whole &= part[-1] is True
    return {"schema": "seen/1", "since": since, "whole": whole, "writes": writes, "merged": merged}


def identities(accounts: dict) -> tuple:
    """`(identities, known)` from the configuration's accounts: each writing identity's `(id, type)` and its code, and
    whether every one is known."""
    found, known = {}, True
    for code, account in [("approver", accounts.get("approver")), ("controller", accounts.get("controller"))] + sorted(
            (accounts.get("roles") or {}).items()):
        if isinstance(account, dict):
            found[(account["id"], account["type"])] = code
        else:
            known = False
    return found, known
