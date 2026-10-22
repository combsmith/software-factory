"""The seen port: the writes each Factory identity made on a served item since a moment, as GitHub records them, for
reconciliation (I-33, decision 0061, the working ruling on "Controller: reconciliation, every write by a Factory
identity matched to a recorded Effect (I-33)", issue 306).

`read(transport, item, kept, identities, apps, since)` gives them for one item. A pull request's reviews, timeline,
review threads and the check runs on its head are what the facts port already read in the same pass, kept by the
snapshot of `adapters/facts.py`, so no read is made twice; a pull request whose snapshot could not be read has
nothing kept, and what was seen of it is short. An issue's timeline is read here. Each item's comments since `since`
are read here, with the Controller's App. `pushes(transport, repo, approver, since)` reads the repo's activity by the machine user.

Each write is told by the account that made it, by id and type, never a login's spelling (`identities`,
`{(id, type): code}`), or for a check run by its App's id (`apps`, `{app_id: code}`); anything by anyone else is left
out, but a merge by anyone, which reconciliation reads for an Override. A dismissed review was an approval or a change
request, and is read as an approval: the machine user's that no Effect recorded alarms either way. The timeline's
events that change a pull request's state are read too, though no Factory write makes them yet, so that one made by a
Factory identity alarms. A thread GitHub names no resolver for, as when an App resolved it, is `unattributed`. A list
that cannot be read whole, or a write whose time or key cannot be read, leaves what was read `whole` false, so that
reconciliation is short, never silent; nothing is guessed. Ids and codes alone: no body or title is kept.

Whether the comments read is served by `pull_requests: read` alone is a trial of the second token window's
(`tests/test_reconcile.py::test_the_comments_on_a_pull_request_are_read_with_pull_requests_read`, pending). An edit of
a write the Factory recorded, a check run's conclusion changed among them, keeps its key, and is not seen.
"""
from __future__ import annotations

import re

from adapters import timeline
from adapters.github import Unanswered, request

PAGE = 100          # the activity is read once: a list as long as a page may be cut short
AT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
KEY = re.compile(r"[A-Za-z0-9_=:-]{1,100}")
PARTS = ("events", "reviews", "threads", "check_runs")
# The timeline's events that are writes, and what each is: those a Factory write makes, and those that change a pull
# request's state, which none makes yet.
EVENTS = {"labeled": "label", "unlabeled": "label", "added_to_merge_queue": "enqueue",
          "removed_from_merge_queue": "dequeue", "merged": "merge", "closed": "close", "reopened": "reopen",
          "review_dismissed": "dismissal", "renamed": "rename", "ready_for_review": "ready",
          "convert_to_draft": "draft", "auto_merge_enabled": "auto_merge", "base_ref_changed": "retarget",
          "head_ref_force_pushed": "force_push", "head_ref_deleted": "branch_deleted", "locked": "lock",
          "unlocked": "lock"}


def _pages(transport, path: str) -> tuple:
    """Every item of a list GitHub gives page by page, and whether it was read whole; nothing, not whole, if not."""
    try:
        return timeline._pages(transport, path)
    except (Unanswered, KeyError, TypeError):
        return [], False


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


def _object(value) -> dict:
    return value if isinstance(value, dict) else {}


def read(transport, item: dict, kept, identities: dict, apps: dict, since: str) -> tuple:
    """`(writes, merged, whole)` for one served item. `kept` is what the snapshot of `adapters/facts.py` kept of a
    pull request, or None where it kept nothing; an issue's is not read."""
    repo, number = item["repo"], item["number"]
    issue = "/repos/%s/issues/%d" % (repo, number)
    writes, merged = [], []
    if item["type"] == "pull_request":
        parts = dict(kept) if isinstance(kept, dict) else {}
    else:
        parts = {"events": _pages(transport, issue + "/timeline?per_page=%d" % PAGE), "reviews": ([], True),
                 "threads": ([], True), "check_runs": ([], True)}
    parts["comments"] = _pages(transport, issue + "/comments?since=%s&per_page=%d" % (since, PAGE))
    whole = True
    for name in PARTS + ("comments",):
        got = parts.get(name)
        whole &= isinstance(got, tuple) and len(got) == 2 and isinstance(got[0], list) and got[1] is True
        parts[name] = got[0] if isinstance(got, tuple) and len(got) == 2 and isinstance(got[0], list) else []

    def add(by, kind, key, at):
        writes.append({"by": by, "kind": kind, "item": dict(item), "key": key, "at": at})

    for r in map(_object, parts["reviews"]):
        by, at = _who(r.get("user"), identities), _at(r.get("submitted_at"), since)
        if by is None or at is None or r.get("state") == "PENDING":
            continue
        whole &= at is not False and _key(r.get("node_id")) is not None
        add(by, "approval" if r.get("state") in ("APPROVED", "DISMISSED") else "review", _key(r.get("node_id")),
            at or None)
    for c in map(_object, parts["comments"]):
        by, at = _who(c.get("user"), identities), _at(c.get("created_at"), since)
        if by is None or at is None:
            continue
        whole &= at is not False and _key(c.get("node_id")) is not None
        add(by, "comment", _key(c.get("node_id")), at or None)
    for e in map(_object, parts["events"]):
        kind = EVENTS.get(e.get("event"))
        at = _at(e.get("created_at"), since) if kind else None
        if kind is None or at is None:
            continue
        whole &= at is not False
        if kind == "merge" and at:
            merged.append({"item": dict(item), "at": at})
        by = _who(e.get("actor"), identities)
        if by is not None:
            add(by, kind, None, at or None)
    for t in map(_object, parts["threads"]):
        if t.get("isResolved") is not True:
            continue
        resolver = t.get("resolvedBy")
        ident = _object(resolver).get("databaseId")
        # A resolver GitHub names but whose account cannot be read cannot be told from a Factory identity.
        whole &= resolver is None or (isinstance(ident, int) and not isinstance(ident, bool))
        by = "unattributed" if resolver is None else _who({"id": ident, "type": "User"}, identities)
        if by is None:
            continue
        whole &= _key(t.get("id")) is not None
        add(by, "resolution", _key(t.get("id")), None)
    for r in map(_object, parts["check_runs"]):
        app = _object(_object(r.get("checkSuite")).get("app")).get("databaseId")
        by = apps.get(app) if isinstance(app, int) and not isinstance(app, bool) else None
        at = _at(r.get("startedAt"), since) if by is not None else None
        if by is None or at is None:
            continue
        whole &= at is not False and _key(r.get("id")) is not None
        add(by, "check_run", _key(r.get("id")), at or None)
    return writes, merged, bool(whole)


def pushes(transport, repo: str, approver: dict, since: str) -> tuple:
    """`(writes, whole)`: each push the machine user made to any branch of `repo` in the last week, from the repo's
    activity, as P-47 reads a branch's (`contents: read`), and kept from `since`. Every one is a write the machine user
    may not make. The activity is asked for by the machine user's login, as GitHub takes it, and each entry held to its
    account's id; a login renamed and not recorded reads none."""
    try:
        answer = transport.send(request("GET", "/repos/%s/activity?actor=%s&time_period=week&per_page=%d" % (
            repo, approver["login"], PAGE)))
    except Unanswered:
        answer = {}
    found = answer.get("body") if answer.get("status") == 200 else None
    whole = isinstance(found, list) and len(found) < PAGE
    writes = []
    for a in map(_object, found if isinstance(found, list) else []):
        actor = _object(a.get("actor"))
        if (actor.get("id"), actor.get("type")) != (approver["id"], "User") or isinstance(actor.get("id"), bool):
            continue
        at = _at(a.get("timestamp"), since)
        if at is None:
            continue
        ident = a.get("id")
        key = str(ident) if isinstance(ident, int) and not isinstance(ident, bool) and ident > 0 else None
        whole &= at is not False and key is not None
        writes.append({"by": "approver", "kind": "push", "item": None, "key": key, "at": at or None})
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
