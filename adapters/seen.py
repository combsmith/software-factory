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
Factory identity alarms. A thread's resolver is told by its account id alone, since GitHub types it a User whoever
resolved it (decision 0067); a thread GitHub names no resolver for is `unattributed`. A list
that cannot be read whole, or a write whose time or key cannot be read, leaves what was read `whole` false, so that
reconciliation is short, never silent; nothing is guessed. Ids and codes alone: no body or title is kept.

Whether the comments read is served by `pull_requests: read` alone is a trial of the second token window's
(`tests/test_reconcile.py::test_the_comments_on_a_pull_request_are_read_with_pull_requests_read`, pending). An edit of
a write the Factory recorded, a check run's conclusion changed among them, keeps its key, and is not seen.
"""
from __future__ import annotations

import datetime
import re

from adapters import records, threads, timeline
from adapters.github import Unanswered, request

LEFT = "left"      # what `kept` is for an item the pass before served that is no longer open: nothing kept, read here
# GitHub's periods of a repo's activity, each by its days, shortest first: the one asked covers the window.
PERIODS = (("day", 1), ("week", 7), ("month", 28), ("quarter", 89), ("year", 364))
MARGIN = 1 / 24     # a day's hour: a period is asked only if it covers the window an hour over, for clocks apart
PAGE = 100          # the activity is read once: a list as long as a page may be cut short
AT = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z")
KEY = re.compile(r"[A-Za-z0-9_=:-]{1,100}")
PARTS = ("events", "reviews", "threads", "check_runs")
# The timeline's events that are writes, and what each is: those a Factory write makes, and those that change a pull
# request's state, which none makes yet.
EVENTS = {"labeled": "label", "unlabeled": "label", "added_to_merge_queue": "enqueue",
          "removed_from_merge_queue": "dequeue", "merged": "merge", "closed": "close", "reopened": "reopen",
          "review_dismissed": "dismissal", "renamed": "rename", "ready_for_review": "ready",
          "convert_to_draft": "draft", "auto_merge_enabled": "auto_merge", "base_ref_changed": "retarget",
          "head_ref_force_pushed": "force_push", "head_ref_deleted": "branch_deleted",
          "head_ref_restored": "branch_restored", "review_requested": "review_request",
          "review_request_removed": "review_request", "assigned": "assignment", "unassigned": "assignment",
          "locked": "lock", "unlocked": "lock"}
# The timeline's events that are no write to the item by their actor, or are read elsewhere: any other a Factory
# identity made is `other`, keyed by its event's name, so that an event GitHub adds alarms rather than going unread.
NOT_WRITES = {"commented", "reviewed", "committed", "mentioned", "subscribed", "unsubscribed", "cross-referenced",
              "referenced", "line-commented", "commit-commented"}
# The states GitHub gives a submitted review.
STATES = ("APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED")
# A dismissed review's state before, as the timeline gives it, as the reviews list gives a review's state.
DISMISSED = {"approved": "APPROVED", "changes_requested": "CHANGES_REQUESTED", "commented": "COMMENTED"}
# What the repo's activity names each write to a branch.
ACTIVITY = {"push": "push", "force_push": "force_push", "branch_creation": "branch_created",
            "branch_deletion": "branch_deleted", "pr_merge": "merge", "merge_queue_merge": "merge"}


def _pages(transport, path: str) -> tuple:
    """Every item of a list GitHub gives page by page, and whether it was read whole; nothing, not whole, if not."""
    try:
        return timeline._pages(transport, path)
    except (Unanswered, KeyError, TypeError):
        return [], False


def _readable(actor) -> bool:
    """Whether an account can be told: by a positive id and a type GitHub gives an actor, a User or a Bot."""
    return isinstance(actor, dict) and isinstance(actor.get("id"), int) and not isinstance(actor.get("id"), bool) \
        and actor["id"] > 0 and actor.get("type") in ("User", "Bot")


def _who(actor, identities: dict):
    return identities.get((actor["id"], actor["type"])) if _readable(actor) else None


def _at(text, since: str):
    """The moment, if it is one and not before `since`; None if it is before; False if it cannot be read."""
    if not isinstance(text, str) or not AT.fullmatch(text):
        return False
    return text if text >= since else None


def _positive(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _key(value):
    return value if isinstance(value, str) and KEY.fullmatch(value) else None


def _object(value) -> dict:
    return value if isinstance(value, dict) else {}


def _threads(transport, item: dict) -> tuple:
    """A pull request's review threads as GitHub gives each node, and whether they were read whole: one page."""
    owner, name = item["repo"].split("/")
    try:
        answer = transport.send(request("POST", "/graphql", body={"query": threads.QUERY, "variables": {
            "owner": owner, "name": name, "number": item["number"], "after": None}}))
    except Unanswered:
        return [], False
    pr = (((_object(answer.get("body")).get("data") or {}).get("repository") or {}).get("pullRequest")) or {}
    listed = _object(_object(pr).get("reviewThreads")) if answer.get("status") == 200 else {}
    nodes = listed.get("nodes") if isinstance(listed.get("nodes"), list) else None
    if nodes is None:
        return [], False
    return nodes, listed.get("totalCount") == len(nodes) and _object(listed.get("pageInfo")).get("hasNextPage") is False


def _check_runs(transport, item: dict) -> tuple:
    """The check runs on a pull request's head as the checks read keeps each, and whether they were read whole."""
    try:
        pulled = transport.send(request("GET", "/repos/%s/pulls/%d" % (item["repo"], item["number"])))
        head = _object(_object(pulled.get("body")).get("head")).get("sha") if pulled.get("status") == 200 else None
        if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head):
            return [], False
        answer = transport.send(request("GET", "/repos/%s/commits/%s/check-runs?per_page=%d" % (item["repo"], head,
                                                                                               PAGE)))
    except Unanswered:
        return [], False
    body = _object(answer.get("body")) if answer.get("status") == 200 else {}
    runs = body.get("check_runs") if isinstance(body.get("check_runs"), list) else None
    if runs is None:
        return [], False
    kept = [{"id": _object(r).get("node_id"), "startedAt": _object(r).get("started_at"),
             "checkSuite": {"app": {"databaseId": _object(_object(r).get("app")).get("id")}}} for r in runs]
    return kept, body.get("total_count") == len(runs) < PAGE


def read(transport, item: dict, kept, identities: dict, apps: dict, since: str) -> tuple:
    """`(writes, merged, whole)` for one served item. `kept` is what the snapshot of `adapters/facts.py` kept of a
    pull request, or None where it kept nothing; an issue's is not read. For an item the pass before served that is no
    longer open, a pull request merged or closed between the passes, `kept` is `LEFT`: no snapshot reads it, so its
    timeline, reviews, threads and the check runs on its head are read here, and with them its close or its merge
    (decision 0063). One whose timeline names no close is not one that left, and what was seen of it is short."""
    repo, number = item["repo"], item["number"]
    issue = "/repos/%s/issues/%d" % (repo, number)
    writes, merged = [], []
    if item["type"] == "pull_request" and kept != LEFT:
        parts = dict(kept) if isinstance(kept, dict) else {}
    elif item["type"] == "pull_request":
        parts = {"events": _pages(transport, issue + "/timeline?per_page=%d" % PAGE),
                 "reviews": _pages(transport, "/repos/%s/pulls/%d/reviews?per_page=%d" % (repo, number, PAGE)),
                 "threads": _threads(transport, item), "check_runs": _check_runs(transport, item)}
    else:
        parts = {"events": _pages(transport, issue + "/timeline?per_page=%d" % PAGE), "reviews": ([], True),
                 "threads": ([], True), "check_runs": ([], True)}
    parts["comments"] = _pages(transport, issue + "/comments?since=%s&per_page=%d" % (since, PAGE))
    whole = True
    for name in PARTS + ("comments",):
        got = parts.get(name)
        whole &= isinstance(got, tuple) and len(got) == 2 and isinstance(got[0], list) and got[1] is True
        parts[name] = got[0] if isinstance(got, tuple) and len(got) == 2 and isinstance(got[0], list) else []
    if kept == LEFT and item["type"] == "pull_request":
        whole &= any(_object(e).get("event") in ("closed", "merged") and _at(_object(e).get("created_at"), since)
                     for e in parts["events"])

    def add(by, kind, key, at):
        writes.append({"by": by, "kind": kind, "item": dict(item), "key": key, "at": at})

    # What each dismissed review was before, from the timeline's dismissals, by the review's id.
    before = {}
    for e in map(_object, parts["events"]):
        if e.get("event") == "review_dismissed":
            dismissed = _object(e.get("dismissed_review"))
            ident, state = dismissed.get("review_id"), dismissed.get("state")
            if _positive(ident) and isinstance(state, str):
                before[ident] = state

    for r in map(_object, parts["reviews"]):
        whole &= _readable(r.get("user"))
        by, at = _who(r.get("user"), identities), _at(r.get("submitted_at"), since)
        if by is None or at is None or r.get("state") == "PENDING":
            continue
        state = r.get("state")
        whole &= state in STATES
        if state == "DISMISSED":
            # A dismissed review is what it was before it was dismissed: a Role's review is matched as one, and an
            # approval as an approval. One whose state before cannot be read leaves what was seen short.
            state = DISMISSED.get(before.get(r.get("id"))) if _positive(r.get("id")) else None
            whole &= state is not None
        whole &= at is not False and _key(r.get("node_id")) is not None
        add(by, "approval" if state in ("APPROVED", None) else "review", _key(r.get("node_id")), at or None)
    for c in map(_object, parts["comments"]):
        whole &= _readable(c.get("user"))
        by, at = _who(c.get("user"), identities), _at(c.get("created_at"), since)
        if by is None or at is None:
            continue
        whole &= at is not False and _key(c.get("node_id")) is not None
        add(by, "comment", _key(c.get("node_id")), at or None)
    for e in map(_object, parts["events"]):
        name = e.get("event")
        if not isinstance(name, str):
            whole = False
            continue
        kind = EVENTS.get(name)
        if kind is None and name in NOT_WRITES:
            continue
        at = _at(e.get("created_at"), since)
        if at is None:
            continue
        if kind is None:
            # An event no Factory write makes: a person's is left out; one by an account that cannot be read may be
            # a Factory identity's, and leaves what was seen short.
            if _readable(e.get("actor")) and _who(e.get("actor"), identities) is None:
                continue
            kind = "other"
        whole &= at is not False and _readable(e.get("actor"))
        if kind == "merge" and at:
            merged.append({"item": dict(item), "at": at})
        by = _who(e.get("actor"), identities)
        if by is not None:
            add(by, kind, _key(name) if kind == "other" else None, at or None)
    for t in map(_object, parts["threads"]):
        if t.get("isResolved") is not True:
            continue
        resolver = t.get("resolvedBy")
        ident = _object(resolver).get("databaseId")
        # A resolver GitHub names but whose account cannot be read cannot be told from a Factory identity.
        whole &= resolver is None or (isinstance(ident, int) and not isinstance(ident, bool) and ident > 0)
        # GraphQL types resolvedBy a User whoever resolved it, an App among them (trials/P-49.json): it is told by its
        # account id alone, which names one account whatever its type (decision 0067).
        by = "unattributed" if resolver is None else next(
            (code for (told, _), code in identities.items() if told == ident and _positive(ident)), None)
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


def _utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _period(since: str, now: str):
    """GitHub's shortest period of a repo's activity that covers `since` at `now`, an hour over, or None if none does,
    or `now` is before `since`, or either cannot be read."""
    try:
        days = (datetime.datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ")
                - datetime.datetime.strptime(since, "%Y-%m-%dT%H:%M:%SZ")).total_seconds() / 86400
    except (TypeError, ValueError):
        return None
    if days < 0:
        return None
    return next((name for name, most in PERIODS if days + MARGIN <= most), None)


def _dated(answer: dict):
    """The answer's own time, from GitHub's `Date`, read as the records port reads it, or None if it gives none that
    can be read."""
    try:
        return records._http_date(_object(answer.get("headers")).get("date"))
    except Unanswered:
        return None


def pushes(transport, repo: str, approver: dict, since: str, clock=_utc) -> tuple:
    """`(writes, whole)`: each write the machine user made to any branch of `repo` since `since`, from the repo's
    activity, as P-47 reads a branch's (`contents: read`), and kept from `since`, each of the kind its activity names
    it: a push, a force push, a branch made or deleted, or a merge, which a served item's timeline names too. Every one
    is a write the machine user may not make; an activity of a type not known is `other`, and leaves the read short.
    The activity is asked for by the machine user's login, as GitHub takes it, and each entry held to its account's
    id; a login renamed and not recorded reads none. The period asked is GitHub's shortest that covers `since` at
    `clock`'s time, an hour over; a window older than a year, or a clock before `since`, is read for the year, and
    short; and a period GitHub's own `Date` says falls short of the window leaves the read short too."""
    period = _period(since, clock())
    try:
        answer = transport.send(request("GET", "/repos/%s/activity?actor=%s&time_period=%s&per_page=%d" % (
            repo, approver["login"], period or PERIODS[-1][0], PAGE)))
    except Unanswered:
        answer = {}
    found = answer.get("body") if answer.get("status") == 200 else None
    whole = isinstance(found, list) and len(found) < PAGE and period is not None
    # GitHub's own time decides what its period covered, where its answer gives it: a period shorter than the one GitHub
    # would need leaves the read short.
    said = _dated(answer)
    if said is not None:
        needed = _period(since, said)
        names = [name for name, _ in PERIODS]
        whole &= needed is not None and period is not None and names.index(needed) <= names.index(period)
    writes = []
    for a in map(_object, found if isinstance(found, list) else []):
        actor = a.get("actor")
        whole &= _readable(actor)
        if not _readable(actor) or (actor["id"], actor["type"]) != (approver["id"], "User"):
            continue
        at = _at(a.get("timestamp"), since)
        if at is None:
            continue
        ident = a.get("id")
        key = str(ident) if isinstance(ident, int) and not isinstance(ident, bool) and ident > 0 else None
        kind = ACTIVITY.get(a.get("activity_type"), "other")
        whole &= at is not False and key is not None and a.get("activity_type") in ACTIVITY
        writes.append({"by": "approver", "kind": kind, "item": None, "key": key, "at": at or None})
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
    found, known, twice = {}, True, set()
    for code, account in [("approver", accounts.get("approver")), ("controller", accounts.get("controller"))] + sorted(
            (accounts.get("roles") or {}).items()):
        if isinstance(account, dict):
            # The machine user is a User, as the configuration records it by login and id alone. Two identities of one
            # account could not be told apart: neither is known.
            told = (account["id"], account.get("type", "User"))
            if told in found or told in twice:
                twice.add(told)
            found[told] = code
        else:
            known = False
    # The queue App is an identity once its account is set (issue 381); until then no write is its, and none is short.
    queue = accounts.get("queue")
    if isinstance(queue, dict):
        told = (queue["id"], "Bot")
        if told in found:
            twice.add(told)
        found[told] = "queue"
    for told in twice:
        del found[told]
    return found, known and not twice
