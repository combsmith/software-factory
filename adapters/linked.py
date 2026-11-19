"""The issues port's last part: the pull requests that close an issue, `issue-facts/1`'s `linked`, and
`complete.linked` (design sections 3.3 and 4.1; decisions 0028, 0139, 0141 and 0186).

One GraphQL read gives the references, `closedByPullRequestsReferences(includeClosedPrs: true)` as trial P-67 read them,
and the issue's closes, links by hand and unlinkings, each naming its pull request as its subject, as trials/P-61.json
recorded them, which ask no repository. One referenced, linked by hand, or named the closer of a close in the
present life is listed only while its base is the default branch, as REST names both: another base carries no closing
reference (trials/P-33.json), and a closer of this life to another base is not whole. A closer is listed whatever its
references now say (trials/P-46.json): a pull request by repository and number, as a merge commit's close (P-33) and the
queue's squash (P-67) named one, or a commit that is one listed pull request's merge commit; a pull request's first
close in the present life is its own. Any other commit closer of this life, one with no id, a closer of another kind, or
a pull request of another repo, is not whole.

Each one's own facts are read as a pull request's (`adapters/pull.py`, `adapters/timeline.py`): its draft changes, the
later ones undone from its flag now, give its flag at a time (`draft_at`, decision 0141); an act an App made with a
person's token is the App's. `keyword` is whether it is referenced: a link by hand, which GitHub references too (P-61),
reads as a keyword, the reading that holds.

Fail closed while `keyword_spans` are empty: they are the pass records' (decision 0186), read by
`adapters/keyword_spans.py`, not built. The Kernel reads no span as a keyword that stood at no merge (`keyword_stood`),
and a pull request whose keyword a pass saw before an edit took it out is listed for nothing here: either could read an
issue done that a rival's link held, an act on a time no read proves. So `complete.linked` is true only where no pull
request names the issue: none referenced, linked or its closer, of any base or life, and nothing but an issue, as read,
cross-referencing it, as the read also asks; the list is handed on all the same, for the pass records.
"""
from __future__ import annotations

from adapters import facts, issues, pull, timeline
from adapters.github import Unanswered, request

PAGE = 25            # references read at most; more is not the whole list
EVENTS = 100         # events read at most; more is not the whole timeline
DRAFTS = {"convert_to_draft": "converted_to_draft", "ready_for_review": "ready_for_review"}
CLOSES = ("closed", "reopened")
LINKS = {"ConnectedEvent": "connected", "DisconnectedEvent": "disconnected"}
QUERY = """query IssueLinked($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    issue(number: $number) {
      number updatedAt
      closedByPullRequestsReferences(first: %d, includeClosedPrs: true) {
        totalCount
        nodes { number repository { nameWithOwner } }
      }
      timelineItems(itemTypes: [CLOSED_EVENT, CONNECTED_EVENT, DISCONNECTED_EVENT, CROSS_REFERENCED_EVENT], first: %d) {
        pageInfo { hasNextPage }
        nodes {
          __typename
          ... on ClosedEvent { createdAt closer { __typename ... on PullRequest { number repository { nameWithOwner } } ... on Commit { oid } } }
          ... on ConnectedEvent { createdAt subject { __typename ... on PullRequest { number repository { nameWithOwner } } } }
          ... on DisconnectedEvent { createdAt subject { __typename ... on PullRequest { number repository { nameWithOwner } } } }
          ... on CrossReferencedEvent { source { __typename } }
        }
      }
    }
  }
}""" % (PAGE, EVENTS)


def _number(node, repo: str):
    """The number of the pull request `node` names, None if of another repo; refused where it names none."""
    number = issues._field(node, "number")
    if type(number) is not int or number < 1:
        raise Unanswered("a pull request with no number")
    return number if issues._field(issues._field(node, "repository"), "nameWithOwner") == repo else None


def joined(transport, repo: str, number: int, updated_at: str, began: str) -> dict:
    """The issue's GraphQL read: `refs`, the numbers referenced; `links`, each link and unlinking by hand, by number;
    `closers`, when each pull request closed the issue, its first close in the life begun at `began` or else its first;
    `commits`, when each commit did in that life; `crossed`, whether anything but an issue cross-references it; and
    `whole`. The read must name the issue's `updated_at`."""
    field, (owner, name) = issues._field, repo.split("/")
    answer = transport.send(request("POST", "/graphql", body={
        "query": QUERY, "variables": {"owner": owner, "name": name, "number": number}}))
    body = answer["body"] if answer["status"] == 200 and isinstance(answer["body"], dict) else None
    if body is None or "errors" in body:
        raise Unanswered("the pull requests that close issue %d could not be read" % number)
    found = field(field(body, "data"), "repository")
    issue = field(found, "issue")
    if field(found, "nameWithOwner") != repo or field(issue, "number") != number:
        raise Unanswered("another issue's were read")
    if timeline._time(field(issue, "updatedAt")) != updated_at:
        raise facts.Moved("the issue changed while it was read; it is read again at the next pass")
    listed, items = field(issue, "closedByPullRequestsReferences"), field(issue, "timelineItems")
    total, nodes = field(listed, "totalCount"), field(listed, "nodes")
    more, events = field(field(items, "pageInfo"), "hasNextPage"), field(items, "nodes")
    if type(total) is not int or not isinstance(nodes, list) or not isinstance(more, bool) or not isinstance(events, list):
        raise Unanswered("the references cannot be read")
    refs = [_number(node, repo) for node in nodes]
    out, closes = {"refs": set(refs), "links": {}, "commits": {}, "crossed": False,
           "whole": total == len(nodes) and not more and None not in refs and len(set(refs)) == len(refs)}, {}
    for node in events:
        kind = field(node, "__typename")
        if kind == "CrossReferencedEvent":
            source = field(node, "source")
            out["crossed"] = out["crossed"] or source is None or field(source, "__typename") != "Issue"
            continue
        at = timeline._time(field(node, "createdAt"))
        if kind in LINKS:
            subject = field(node, "subject")
            if not isinstance(subject, dict) or field(subject, "__typename") != "PullRequest":
                raise Unanswered("a link to no pull request")
            linked = _number(subject, repo)
            out["whole"] = out["whole"] and linked is not None
            out["links"].setdefault(linked, []).append({"action": LINKS[kind], "at": at})
        elif kind == "ClosedEvent":
            closer = field(node, "closer")
            typed = field(closer, "__typename") if closer is not None else None
            if typed == "PullRequest":
                closed = _number(closer, repo)
                out["whole"] = out["whole"] and closed is not None
                closes.setdefault(closed, []).append(at)
            elif typed is not None and typed != "Commit":
                out["whole"] = False
            elif typed == "Commit":
                oid = field(closer, "oid")
                if not timeline.SHA.match(str(oid)):
                    raise Unanswered("a commit closer with no id")
                if at >= began:
                    out["commits"].setdefault(oid, at)
        else:
            raise Unanswered("an event of a kind not asked")
    out["refs"].discard(None)
    out["links"].pop(None, None)
    out["closers"] = {n: min([at for at in ats if at >= began] or ats) for n, ats in closes.items() if n is not None}
    return out


def drafts(events: list) -> list:
    """Each conversion to a draft and marking ready, with its time, in the timeline's order."""
    found = []
    for event in events:
        event = timeline._object(event, "the timeline")
        if event.get("event") in DRAFTS:
            found.append({"action": DRAFTS[event["event"]], "at": timeline._time(event.get("created_at"))})
    return found


def draft_at(entry: dict, when: str) -> bool:
    """Whether a listed pull request was a draft at `when`: its flag now with every later change undone, or a draft at any
    moment of that second, so read either way in a change's own second (decision 0141)."""
    state, drafted = entry["draft"], False
    for change in reversed(entry["draft_events"]):
        if change["at"] < when:
            break
        drafted = drafted or change["at"] == when and state
        state = change["action"] == "ready_for_review"
    return drafted or state


def closes(events: list, accounts: timeline.Accounts) -> list:
    """Each close and reopening, a merge's among them (trials/P-48.json), by whom and when, as the timeline lists them."""
    found = []
    for event in events:
        event = timeline._object(event, "the timeline")
        if event.get("event") in CLOSES:
            found.append({"action": event["event"], "by": accounts.acted(event),
                          "at": timeline._time(event.get("created_at"))})
    return found


def _when(value):
    return None if value is None else timeline._time(value)


def entry(transport, read: dict, identities: dict, accounts: timeline.Accounts, join: dict) -> tuple:
    """`(the pull request as issue-facts/1 lists it, whether its timeline was whole)`, from `read` and `join`."""
    number = read["number"]
    own, _ = pull.own(read, identities)
    events, whole = timeline.events(transport, read)
    files = read.get("changed_files")
    if type(files) is not int or files < 0:
        raise Unanswered("a count of files that cannot be read")
    return {"number": number, "class": own["class"], "opener": accounts.actor(read.get("user")),
            "open": own["state"] == "open", "draft": own["is_draft"],
            "opened_at": timeline._time(read.get("created_at")), "merged_at": _when(read.get("merged_at")),
            "closed_at": _when(read.get("closed_at")), "empty": files == 0,
            "label_events": timeline.label_events(events, accounts), "closed_issue_at": join["closers"].get(number),
            "draft_events": drafts(events), "link_events": join["links"].get(number, []),
            "keyword": number in join["refs"], "keyword_spans": [], "close_events": closes(events, accounts)}, whole


def on_default(read: dict) -> bool:
    """Whether a pull request's base is the default branch, as REST names both; refused where either cannot be read."""
    base = read.get("base") if isinstance(read.get("base"), dict) else {}
    held = base.get("repo") if isinstance(base.get("repo"), dict) else {}
    ref, default = base.get("ref"), held.get("default_branch")
    if not (isinstance(ref, str) and ref and isinstance(default, str) and default):
        raise Unanswered("the base or the default branch cannot be read")
    return ref == default


def listing(transport, repo: str, number: int, updated_at: str, began: str, identities: dict,
            accounts: timeline.Accounts) -> tuple:
    """`(linked, whole, named)` for issue `number`: each pull request listed, by number; whether every part was read
    whole; and whether a pull request names the issue, before any is left out, or cross-references it.
    `began` is when its present life began, `identities` the class's accounts, `accounts` who acted."""
    join = joined(transport, repo, number, updated_at, began)
    present = {n for n, at in join["closers"].items() if at >= began}
    found, whole = [], join["whole"]
    for candidate in sorted(join["refs"] | set(join["links"]) | present):
        got = pull.read(transport, repo, candidate)
        if not on_default(got):
            # A closer of this life to another base is no link, and could be one: not whole.
            whole = whole and candidate not in present
            continue
        made, read_whole = entry(transport, got, identities, accounts, join)
        found.append((made, got.get("merge_commit_sha")))
        whole = whole and read_whole
    # A commit closer of the present life is a listed pull request's merge: its close, unless one of this life is earlier.
    for oid, at in join["commits"].items():
        merged = [made for made, sha in found if sha == oid and made["merged_at"] is not None]
        was = merged[0]["closed_issue_at"] if merged else None
        if merged and (was is None or was < began or at < was):
            merged[0]["closed_issue_at"] = at
        whole = whole and len(merged) == 1
    linked = [made for made, _ in found]
    return linked, whole, bool(join["refs"] or join["links"] or join["closers"] or join["crossed"])


def read(transport, repo: str, number: int, updated_at: str, began: str, identities: dict,
         accounts: timeline.Accounts) -> tuple:
    """`(linked, whole)`, as `listing` reads them; whole only where no pull request names the issue, while the keyword
    spans are not read (the docstring above). The spans' reader lifts this one condition."""
    linked, whole, named = listing(transport, repo, number, updated_at, began, identities, accounts)
    return linked, whole and not named

