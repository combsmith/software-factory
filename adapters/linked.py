"""The issues port's last part: the pull requests that close an issue, `issue-facts/1`'s `linked` (design sections 3.3
and 4.1; decisions 0028, 0139, 0141 and 0186).

One GraphQL read gives the references, `closedByPullRequestsReferences(includeClosedPrs: true)` as trial P-67 read them,
and the issue's closes and links by hand, each naming its pull request as its subject, as trials/P-61.json
recorded them, which ask no repository. One referenced, linked by hand, or named the closer of a close in the
present life is listed only while its base is the default branch, as REST names both: another base carries no closing
reference (trials/P-33.json). A closer is listed whatever its references now say (trials/P-46.json), a pull request by
repository and number, as a merge commit's close (P-33) and the queue's squash (P-67) named one; its first close in the
present life is its own. References or a timeline read short, a reference of another repo or one named twice, are not
whole.

Each one's draft changes are read from its own timeline (`adapters/timeline.py`), in its order; the later ones undone
from its flag now give its flag at a time (`draft_at`, decision 0141). `keyword` is whether it is referenced.

Not read yet: an unlinking, a commit's close, a closer or a link by hand that cannot be listed, an issue that changed
while it was read, each one's other facts, and an answer that must be refused.
"""
from __future__ import annotations

from adapters import issues, pull, timeline
from adapters.github import Unanswered, request

PAGE = 25            # references read at most; more is not the whole list
EVENTS = 100         # events read at most; more is not the whole timeline
DRAFTS = {"convert_to_draft": "converted_to_draft", "ready_for_review": "ready_for_review"}
LINKS = {"ConnectedEvent": "connected"}
QUERY = """query IssueLinked($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    issue(number: $number) {
      number updatedAt
      closedByPullRequestsReferences(first: %d, includeClosedPrs: true) {
        totalCount
        nodes { number repository { nameWithOwner } }
      }
      timelineItems(itemTypes: [CLOSED_EVENT, CONNECTED_EVENT], first: %d) {
        pageInfo { hasNextPage }
        nodes {
          __typename
          ... on ClosedEvent { createdAt closer { __typename ... on PullRequest { number repository { nameWithOwner } } } }
          ... on ConnectedEvent { createdAt subject { __typename ... on PullRequest { number repository { nameWithOwner } } } }
        }
      }
    }
  }
}""" % (PAGE, EVENTS)


def _number(node, repo: str):
    """The number of the pull request `node` names, None if of another repo."""
    number = issues._field(node, "number")
    return number if issues._field(issues._field(node, "repository"), "nameWithOwner") == repo else None


def joined(transport, repo: str, number: int, updated_at: str, began: str) -> dict:
    """The issue's GraphQL read: `refs`, the numbers referenced; `links`, each link by hand, by number;
    `closers`, when each pull request closed the issue, its first close in the life begun at `began` or else its first;
    and `whole`."""
    field, (owner, name) = issues._field, repo.split("/")
    answer = transport.send(request("POST", "/graphql", body={
        "query": QUERY, "variables": {"owner": owner, "name": name, "number": number}}))
    body = answer["body"] if answer["status"] == 200 and isinstance(answer["body"], dict) else None
    if body is None:
        raise Unanswered("the pull requests that close issue %d could not be read" % number)
    found = field(field(body, "data"), "repository")
    issue = field(found, "issue")
    listed, items = field(issue, "closedByPullRequestsReferences"), field(issue, "timelineItems")
    total, nodes = field(listed, "totalCount"), field(listed, "nodes")
    more, events = field(field(items, "pageInfo"), "hasNextPage"), field(items, "nodes")
    if type(total) is not int or not isinstance(nodes, list) or not isinstance(more, bool) or not isinstance(events, list):
        raise Unanswered("the references cannot be read")
    refs = [_number(node, repo) for node in nodes]
    out, closes = {"refs": set(refs), "links": {},
           "whole": total == len(nodes) and not more and None not in refs and len(set(refs)) == len(refs)}, {}
    for node in events:
        kind = field(node, "__typename")
        at = timeline._time(field(node, "createdAt"))
        if kind in LINKS:
            subject = field(node, "subject")
            linked = _number(subject, repo)
            out["links"].setdefault(linked, []).append({"action": LINKS[kind], "at": at})
        elif kind == "ClosedEvent":
            closer = field(node, "closer")
            typed = field(closer, "__typename") if closer is not None else None
            if typed == "PullRequest":
                closed = _number(closer, repo)
                closes.setdefault(closed, []).append(at)
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


def entry(transport, read: dict, identities: dict, accounts: timeline.Accounts, join: dict) -> tuple:
    """`(the pull request's number, draft flag and changes, links, keyword and close of the issue, whether its timeline
    was whole)`, from `read` and `join`."""
    number = read["number"]
    own, _ = pull.own(read, identities)
    events, whole = timeline.events(transport, read)
    return {"number": number, "draft": own["is_draft"], "closed_issue_at": join["closers"].get(number),
            "draft_events": drafts(events), "link_events": join["links"].get(number, []),
            "keyword": number in join["refs"]}, whole


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
    """`(linked, whole)` for issue `number`: each pull request listed, by number, and whether every part was read whole.
    `began` is when its present life began, `identities` the class's accounts, `accounts` who acted."""
    join = joined(transport, repo, number, updated_at, began)
    present = {n for n, at in join["closers"].items() if at >= began}
    found, whole = [], join["whole"]
    for candidate in sorted(join["refs"] | set(join["links"]) | present):
        got = pull.read(transport, repo, candidate)
        if not on_default(got):
            continue
        made, read_whole = entry(transport, got, identities, accounts, join)
        found.append(made)
        whole = whole and read_whole
    return found, whole

