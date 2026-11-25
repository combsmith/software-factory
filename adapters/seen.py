"""The seen port: the writes each Factory identity made on a served item since a moment, as GitHub records them, for
reconciliation (I-33, decision 0061, the working ruling on "Controller: reconciliation, every write by a Factory
identity matched to a recorded Effect (I-33)", issue 306).

`read(transport, item, kept, identities, apps, since)` gives them for one item. A pull request's reviews, timeline,
review threads and the check runs on its head are what the facts port already read in the same pass, kept by the
snapshot of `adapters/facts.py`, so no read is made twice, but a timeline it cut at its bound, which is read here
again from its end; a pull request whose snapshot could not be read has nothing kept, and what was seen of it
is short. An issue's timeline is read here, from its end. Each item's comments since `since`
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

GitHub names `pull_requests=read` among what serves a pull request's comments (trials/P-56.json,
`tests/test_reconcile.py::test_the_comments_on_a_pull_request_are_read_with_pull_requests_read`); an issue's comments and
a private repo are unasked, and a read refused leaves what was read not whole. An edit of
a write the Factory recorded, a check run's conclusion changed among them, keeps its key, and is not seen.
"""
from __future__ import annotations

import datetime
import re
import urllib.parse

from adapters import records, threads, timeline
from adapters.github import Unanswered, request

LEFT = "left"      # what `kept` is for an item the pass before served that is no longer open: nothing kept, read here
# What `kept` is for a pull request a pass before read as left, inside the window: read as one that left, its close
# already read, so a close older than the window still stands (issue 787).
GONE = "gone"
# GitHub's periods of a repo's activity, each by its days, shortest first: the one asked covers the window.
PERIODS = (("day", 1), ("week", 7), ("month", 28), ("quarter", 89), ("year", 364))
MARGIN = 1 / 24     # a day's hour: a period is asked only if it covers the window an hour over, for clocks apart
PAGE = 100          # the activity is read once: a list as long as a page may be cut short
AT = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z")
KEY = re.compile(r"[A-Za-z0-9_=:-]{1,100}")
COMMIT = re.compile(r"[0-9a-f]{40}")
NO_COMMIT = object()    # a write that is no approval carries no commit; any value GitHub gives is an approval's
PARTS = ("events", "reviews", "threads", "check_runs")
HAND = "hand"       # who a write is by when a person resolved a thread a Role opened: no identity, and no Role's name
NOT_ROLES = ("approver", "controller", "queue")     # the identities that are no Role's App
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


# What REST answers of an issue that left once nothing more can be read there: 404, not found, or 410, deleted. Each is
# the end of the issue only where the same token read its repo in the same pass; else access may be what was lost, and
# what was seen is short. A transfer's 301 is not among them: the transport keeps no redirect's code (decision 0235).
ENDED = (404, 410)
# One entry of a list's link header, as trials/P-43.json recorded them, `<...&page=12>; rel="last"`, with any
# parameters after it, as GitHub's deprecation notice has (trials/P-1.json); the relations that page a list; and a page.
LINK = re.compile(r'<([^<>]*)>;\s*rel="([a-z]+)"(?:;\s*[a-z-]+="[^"]*")*')
PAGING = ("next", "last", "prev", "first")
PAGE_NUMBER = re.compile(r"[0-9]{1,9}")
KIND = re.compile(r"[a-z][a-z_-]*")     # an event's kind as GitHub names one


def _pages(transport, path: str) -> tuple:
    """Every item of a list GitHub gives page by page, to `timeline.BOUND` pages, and whether it was read whole. Past
    the bound it is the items read and not whole; a page not answered is nothing and not whole. Anyone can comment, so
    what was seen of a list past the bound is short, never silent (issue 1009, decision 0234). It serves the comments,
    which GitHub gives from `since` on."""
    try:
        items, whole, _ = timeline._paged(transport, path, timeline.BOUND)
        return items, whole
    except (Unanswered, KeyError, TypeError):
        return [], False


def _page(transport, path: str, page: int) -> tuple:
    """`(items, link)` of one page of a list: refused where GitHub answers anything but a list."""
    answer = transport.send(request("GET", path if page == 1 else "%s&page=%d" % (path, page)))
    if answer["status"] != 200 or not isinstance(answer["body"], list):
        raise Unanswered("%s answered %d" % (path.split("?")[0], answer["status"]))
    return answer["body"], str((answer.get("headers") or {}).get("link", ""))


def _moments(items: list) -> list:
    """The moments a page's items can be read at, by their `created_at` or `submitted_at`: only an item whose kind
    and moment can be read has one, so one that cannot never says where the read is (Astra, issue 1206)."""
    out = []
    for item in items:
        one = _object(item)
        at = one.get("submitted_at") if one.get("event") == "reviewed" else one.get("created_at")
        if isinstance(one.get("event"), str) and KIND.fullmatch(one["event"]) and isinstance(at, str) \
                and AT.fullmatch(at):
            out.append(at)
    return out


def _links(link: str) -> dict:
    """`{rel: page}` of the relations that page a list in a link header, read whole: every entry `<address>;
    rel="name"`, each paging relation once, its address naming one page in its query. One read in part raises
    ValueError, so that it never says where a list ends (Astra, Muse, Kimi, issue 1206); a relation that pages nothing
    is passed over (Claude)."""
    out = {}
    for entry in link.split(",") if link.strip() else ():
        one = LINK.fullmatch(entry.strip())
        if one is None:
            raise ValueError("a link header that cannot be read whole")
        if one.group(2) not in PAGING:
            continue
        address = urllib.parse.urlsplit(one.group(1))
        pages = [v for k, v in urllib.parse.parse_qsl(address.query, keep_blank_values=True) if k == "page"]
        if address.fragment or len(pages) != 1 or not PAGE_NUMBER.fullmatch(pages[0]) or one.group(2) in out:
            raise ValueError("a link header that cannot be read whole")
        out[one.group(2)] = int(pages[0])
    return out


def _before(items: list, since: str) -> bool:
    """Whether a page holds an item from before `since`."""
    return any(at < since for at in _moments(items))


def _mark(item):
    """What tells one item of a list from another while it is read: its kind, its ids, a commit's sha, and its time."""
    one = _object(item)
    # Each with its type, so that an id read again as a truth value is not the number it was; and who made it, and
    # its label, so that a write read again as another's is not the same (Astra, issue 1206).
    by = [_object(one.get(field)).get(key) for field in ("actor", "user") for key in ("id", "type")]
    return tuple((type(v), v) for v in [one.get("event"), one.get("id"), one.get("node_id"), one.get("sha"),
                                         one.get("created_at"), one.get("submitted_at"),
                                         _object(one.get("label")).get("name")] + by)


def _tail(transport, path: str, since: str, ends=()) -> tuple:
    """`(items, whole)`: a list GitHub gives oldest first, read from its end back to `since`, so that the writes since
    then and an item's close, which are at its end, are read however long it is (issue 1009, decision 0234). The first
    page names the last; the last pages are read back until one reaches before `since`, or the second, so the first
    is joined: `timeline.BOUND` pages at most, the last read again among them, and the first too where it is joined.
    An event that lands while it is read moves the pages, so the last page is read again at the end, and one whose
    number or items changed leaves the read not whole (the Factory Builder's ruling of 2026-11-20); an item deleted
    from the first page moves them the other way, so a joined first page must read the same again (Claude). Items are
    kept once each, by their kind and id where they carry one. It serves a list GitHub gives in the order of the time
    it reads, a timeline's; not the reviews, which it gives in the order they were started. Given `ends`, an item read
    as gone, whose close may be older than `since`, it reads on back, within the same bound, until one of them is
    found (Claude)."""
    try:
        items, link = _page(transport, path, 1)
        named = _links(link)
        if "next" not in named:
            # One page: whole, unless it names another, a last it does not lead to or one before it (Astra, Claude).
            found, joined, reached, steady = [], True, False, not named
        elif named["next"] != 2 or named.get("last", 0) < 2:
            # A next page that is not the second, or no last past the first, cannot be read from its end (Carbon,
            # issue 1206).
            return [], False
        else:
            end = named["last"]
            tail, end_link = _page(transport, path, end)
            found, page, reached, links = [tail], end, _before(tail, since), []
            while not (reached and _ended(found, ends)) and page > 2 and len(found) < timeline.BOUND - 3:
                page -= 1
                got, got_link = _page(transport, path, page)
                found.insert(0, got)
                links.append((page, _links(got_link)))
                reached = reached or _before(got, since)
            joined = page == 2
            again, again_link = _page(transport, path, end)
            # An empty page before the end is no page GitHub would give (Astra), the first among them (Muse).
            steady = (bool(items) and all(found) and [_mark(i) for i in again] == [_mark(i) for i in tail]
                      and all("next" not in got and got.get("last", end) == end
                              for got in (_links(end_link), _links(again_link))))
            # Each page read back names the one after it and the same last (Astra, issue 1206).
            steady = steady and all(got.get("next") == at + 1 and got.get("last") == end for at, got in links)
            if joined:
                first, first_link = _page(transport, path, 1)
                steady = steady and first_link == link and [_mark(i) for i in first] == [_mark(i) for i in items]
        # The moments read run in order, the skipped pages' with them, and a first page left out holds nothing that
        # could be a write and cannot be placed: else the answers contradict (Astra, Muse, issue 1206).
        order = [at for one in [items] + found for at in _moments(one)]
        steady = steady and order == sorted(order)
        steady = steady and (joined or all(_moments([i]) or _object(i).get("event") in NOT_WRITES for i in items))
    except (Unanswered, KeyError, TypeError, ValueError):
        return [], False
    kept, seen = [], {}
    for item in ([items] if joined else []) + found:
        for one in item:
            key = (_object(one).get("event"), _object(one).get("id"))
            if not all(k is None or isinstance(k, (str, int)) and not isinstance(k, bool) for k in key):
                return [], False
            if key[1] is not None and key in seen:
                if seen[key] != _mark(one):
                    # One event read twice as two: the answers contradict (Astra, issue 1206).
                    return [], False
                continue
            seen[key] = _mark(one)
            kept.append(one)
    return kept, (reached or joined) and steady


def _ended(pages: list, ends) -> bool:
    """Whether `pages` hold one of the events `ends`, or none is asked for."""
    return not ends or any(_object(e).get("event") in ends for page in pages for e in page)


def _readable(actor) -> bool:
    """Whether an account can be told: by a positive id and a type GitHub gives an actor, a User or a Bot."""
    return isinstance(actor, dict) and isinstance(actor.get("id"), int) and not isinstance(actor.get("id"), bool) \
        and actor["id"] > 0 and actor.get("type") in ("User", "Bot")


def _who(actor, identities: dict):
    return identities.get((actor["id"], actor["type"])) if _readable(actor) else None


def _opener(thread: dict, identities: dict) -> tuple:
    """`(code, told)`: the identity that opened a thread, by its first comment's author as GraphQL gives it, or None;
    and whether it could be told from one. A first comment GitHub does not say replies to none is not the opener's.
    An author GitHub no longer names, or of a type no identity has, is none; one whose type is not said cannot be told.
    A thread whose first comment was deleted reads its next as its first (trials P-49 and P-53), so its opener is
    whoever replied: that is not told here."""
    nodes = _object(thread.get("comments")).get("nodes")
    if not isinstance(nodes, list) or not nodes or not isinstance(nodes[0], dict) or nodes[0].get("replyTo", 0) is not None:
        return None, False
    author = nodes[0].get("author", 0)
    if author is None:
        return None, True
    kind = _object(author).get("__typename")
    if not isinstance(kind, str) or not kind:
        return None, False
    if kind not in ("User", "Bot"):
        return None, True
    actor = {"id": author.get("databaseId"), "type": kind}
    return _who(actor, identities), _readable(actor)


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


def _state(transport, issue: str, number: int):
    """What REST's read of an issue that left answers: `open` or `closed`, a status of `ENDED`, or None for any other
    answer, a body of another number, of a pull request, or none at all (decision 0235)."""
    try:
        answer = transport.send(request("GET", issue))
    except Unanswered:
        return None
    if answer.get("status") in ENDED:
        return answer["status"]
    body = _object(answer.get("body")) if answer.get("status") == 200 else {}
    own = type(body.get("number")) is int and body["number"] == number and "pull_request" not in body
    return body.get("state") if own and body.get("state") in ("open", "closed") else None


def repo_read(transport, repo: str) -> bool:
    """Whether REST answered the repo `repo` itself, by its full name, with its issues on, through `transport`: with
    them off, every issue answers 410, and none has ended (decision 1145)."""
    try:
        answer = transport.send(request("GET", "/repos/%s" % repo))
    except Unanswered:
        return False
    body = _object(answer.get("body")) if answer.get("status") == 200 else {}
    full = body.get("full_name")
    return isinstance(full, str) and full.lower() == repo.lower() and body.get("has_issues") is True


def read(transport, item: dict, kept, identities: dict, apps: dict, since: str, repo_read=False, told=None) -> tuple:
    """`(writes, merged, whole)` for one served item. `kept` is what the snapshot of `adapters/facts.py` kept of a
    pull request, or None where it kept nothing; an issue's is not read. For an item the pass before served that is no
    longer open, a pull request merged or closed between the passes, `kept` is `LEFT`: no snapshot reads it, so its
    timeline, reviews, threads and the check runs on its head are read here, and with them its close or its merge
    (decision 0063). One whose timeline names no close is not one that left, and what was seen of it is short. An issue
    that left is read first by its state: one still open, left out of the issues served, is read as an open one is, with
    no close; one REST answers 404 or 410 is whole, with nothing read, only where `repo_read`, the same token having read
    its repo in this pass, and is then added to `told` with its answer; any other answer is short (decision 0235)."""
    repo, number = item["repo"], item["number"]
    issue = "/repos/%s/issues/%d" % (repo, number)
    writes, merged = [], []
    ending = kept in (LEFT, GONE)
    if item["type"] == "issue" and ending:
        state = _state(transport, issue, number)
        if state in ENDED:
            # Whole only where the end can be told: with nowhere to tell it, the issue would end unseen.
            ended = repo_read is True and told is not None
            if ended:
                told.append({"item": dict(item), "answer": state})
            return [], [], ended
        if state is None:
            return [], [], False
        ending = state == "closed"
    # One read as gone is whole only with its close, of any age: its timeline is read back until the close is found.
    # One read as gone that is open again has no close to find, and is read back to `since` alone (Carbon).
    gone = ((("closed", "merged") if item["type"] == "pull_request" else ("closed",)) if kept == GONE and ending else ())
    if item["type"] == "pull_request" and kept not in (LEFT, GONE):
        parts = dict(kept) if isinstance(kept, dict) else {}
        # A timeline the snapshot cut at its bound is read again from its end, where the writes are; a reviews list
        # cut stays short, since GitHub lists reviews in the order they were started, not submitted (Claude).
        cut = kept.get("cut") if isinstance(kept, dict) and isinstance(kept.get("cut"), dict) else {}
        if cut.get("events") is True:
            parts["events"] = _tail(transport, issue + "/timeline?per_page=%d" % PAGE, since)
    elif item["type"] == "pull_request":
        parts = {"events": _tail(transport, issue + "/timeline?per_page=%d" % PAGE, since, gone),
                 "reviews": _pages(transport, "/repos/%s/pulls/%d/reviews?per_page=%d" % (repo, number, PAGE)),
                 "threads": _threads(transport, item), "check_runs": _check_runs(transport, item)}
    else:
        parts = {"events": _tail(transport, issue + "/timeline?per_page=%d" % PAGE, since, gone), "reviews": ([], True),
                 "threads": ([], True), "check_runs": ([], True)}
    parts["comments"] = _pages(transport, issue + "/comments?since=%s&per_page=%d" % (since, PAGE))
    whole = True
    for name in PARTS + ("comments",):
        got = parts.get(name)
        whole &= isinstance(got, tuple) and len(got) == 2 and isinstance(got[0], list) and got[1] is True
        parts[name] = got[0] if isinstance(got, tuple) and len(got) == 2 and isinstance(got[0], list) else []
    # One that left is read with its close: an issue's close, or a pull request's close or merge, in the window, or any
    # for one a pass before read as gone (issues 787 and 916).
    if ending:
        ends = ("closed", "merged") if item["type"] == "pull_request" else ("closed",)
        whole &= any(_object(e).get("event") in ends
                     and (kept == GONE or _at(_object(e).get("created_at"), since)) for e in parts["events"])

    def add(by, kind, key, at, commit=NO_COMMIT):
        write = {"by": by, "kind": kind, "item": dict(item), "key": key, "at": at}
        if commit is not NO_COMMIT:
            # An approval carries the commit it approved, null where GitHub gave none that can be read, so that
            # reconciliation never takes it for a hand approval by its item alone (issue 1026).
            write["commit"] = commit if isinstance(commit, str) and COMMIT.fullmatch(commit) else None
        writes.append(write)

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
        if state in ("APPROVED", None):
            # Its commit only where its state read as approved: one whose state before cannot be read has none.
            add(by, "approval", _key(r.get("node_id")), at or None, r.get("commit_id") if state == "APPROVED" else None)
        else:
            add(by, "review", _key(r.get("node_id")), at or None)
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
        if by is None and not _positive(ident):
            continue        # what was seen is short already: who resolved it cannot be told, a person least of all
        if by is None:
            # A resolver that is no Factory identity is a person's hand. The Kernel takes it as closing a Lens's Finding,
            # so its resolution of a thread a Role opened is a write to reconcile (issue 854); of any other, nobody's.
            opened, told = _opener(t, identities)
            whole &= told
            if opened is None or opened in NOT_ROLES:
                continue
            by = HAND
        whole &= _key(t.get("id")) is not None
        add(by, "resolution", _key(t.get("id")), None)
    for r in map(_object, parts["check_runs"]):
        app = _object(_object(r.get("checkSuite")).get("app")).get("databaseId")
        # A check run whose App GitHub did not show this token, or gave no id that can be read, could be any App's, a
        # Factory one's among them: what was seen is short, never silent (decision 0181).
        whole &= _positive(app)
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


def seen(parts: list, since: str, gone=()) -> dict:
    """`seen/1` from each `read`'s and `pushes`'s answer: whole only when every part was. `gone` is each issue that left
    read as whole by its 404 or 410, with that answer, carried only where there is one (decision 1145)."""
    writes, merged, whole = [], [], True
    for part in parts:
        writes += part[0]
        merged += part[1] if len(part) == 3 else []
        whole &= part[-1] is True
    found = {"schema": "seen/1", "since": since, "whole": whole, "writes": writes, "merged": merged}
    return dict(found, gone=list(gone)) if gone else found


def apps_of(accounts: dict, apps: dict) -> dict:
    """`{app_id: code}`, each Factory App whose account the configuration holds, by which a check run is told."""
    codes = ["controller", "queue"] + sorted(accounts.get("roles") or {})
    roles = accounts.get("roles") or {}
    return {apps[code]["app_id"]: code for code in codes
            if code in apps and isinstance(roles.get(code, accounts.get(code)), dict)}


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
