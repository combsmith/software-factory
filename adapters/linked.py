"""The issues port's last part: the pull requests that close an issue, `issue-facts/1`'s `linked`, and
`complete.linked` (design sections 3.3 and 4.1; decisions 0028, 0139, 0141 and 0186).

One GraphQL read gives the references, `closedByPullRequestsReferences(includeClosedPrs: true)` as trial P-67 read them,
and the issue's closes, links by hand and unlinkings, each naming its pull request as its subject, as trials/P-61.json
recorded them, which ask no repository. One referenced, linked by hand, or named the closer of a close in the
present life is listed only while its base is the default branch, as REST names both: a keyword on another base carries
no closing reference (trials/P-33.json), a closer of this life to another base is not whole, and so is one linked by
hand now, which keeps its link and its closing reference when its base moves (trials/P-69.json, decision 0236). A closer is listed whatever its
references now say (trials/P-46.json): a pull request by repository and number, as a merge commit's close (P-33) and the
queue's squash (P-67) named one, or a commit that is one listed pull request's merge commit; a pull request's first
close in the present life is its own. Any other commit closer of this life, a closer of another kind, or a pull request
of another repo, is not whole, and a commit closer of this life with no id refuses the read; each of these in a life
before is passed over, though it names the issue, and a closer of no type is refused in any life.

Each one's own facts are read as a pull request's (`adapters/pull.py`, `adapters/timeline.py`): its draft changes, the
later ones undone from its flag now, give its flag at a time (`draft_at`, decision 0141); an act an App made with a
person's token is the App's. `keyword` is whether it is referenced: a link by hand, which GitHub references too (P-61),
reads as a keyword, the reading that holds.

`keyword_spans` are the pass records' (decision 0186), read by `adapters/keyword_spans.py` from the records before this
pass, which the caller hands on. A pull request whose keyword a pass saw is listed for good, with `keyword` false once
an edit takes it out, so that no edit after a merge moves the issue; so the list is a pull request with a keyword now or
once seen, a link by hand, or a close it made in the present life, and no other. `complete.linked` is true where the
list and the spans were both read whole: records that could not be read give no time and could hide a pull request once
seen, so the issue defers. Where the records at hand break the chain of spans (`adapters/keyword_spans.py`), the list is
whole besides only where they give no pull request a span, which a broken chain may give short, and nothing names the
issue now: no pull request referenced, linked by hand or the closer of a close in any life, of any base, no closer of
any life but a person, nothing but an issue cross-referencing it and no commit referencing it, as the read also asks;
a pull request whose keyword an edit took out still cross-references it, as its trial is to show (issue 990).
"""
from __future__ import annotations

from adapters import draft_checks, facts, issues, keyword_spans, pull, timeline
from adapters.github import Unanswered, request

PAGE = 25            # references read at most; more is not the whole list
EVENTS = 100         # events read at most; more is not the whole timeline
DRAFTS = {"convert_to_draft": "converted_to_draft", "ready_for_review": "ready_for_review"}
CLOSES = ("closed", "reopened")
LINKS = {"ConnectedEvent": "connected", "DisconnectedEvent": "disconnected"}
# The pull requests an issue's linked read reads at most: past them the list is not whole and none is read, so that no
# pull request author can make one issue's read cost without bound (decision 0234).
CANDIDATES = 25
QUERY = """query IssueLinked($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    issue(number: $number) {
      number updatedAt
      closedByPullRequestsReferences(first: %d, includeClosedPrs: true) {
        totalCount
        nodes { number repository { nameWithOwner } }
      }
      timelineItems(itemTypes: [CLOSED_EVENT, CONNECTED_EVENT, DISCONNECTED_EVENT, CROSS_REFERENCED_EVENT, REFERENCED_EVENT], first: %d) {
        pageInfo { hasNextPage }
        nodes {
          __typename
          ... on ClosedEvent { createdAt closer { __typename ... on PullRequest { number repository { nameWithOwner } } ... on Commit { oid } } }
          ... on ConnectedEvent { createdAt subject { __typename ... on PullRequest { number repository { nameWithOwner } } } }
          ... on DisconnectedEvent { createdAt subject { __typename ... on PullRequest { number repository { nameWithOwner } } } }
          ... on CrossReferencedEvent { source { __typename } }
          ... on ReferencedEvent { commit { oid } }
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
    `commits`, when each commit did in that life; `closed`, whether a close of any life names a closer `closers` cannot
    hold, a commit, a pull request of another repo or a closer of another kind; `crossed`, whether anything but an issue
    cross-references it, or a commit references it, as a commit's closing keyword does; `whole`; and `cut`, whether the
    references or the timeline ran past the read's one page. The read must name the issue's `updated_at`."""
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
    out, closes = {"refs": set(refs), "links": {}, "commits": {}, "crossed": False, "closed": False,
           "whole": total == len(nodes) and not more and None not in refs and len(set(refs)) == len(refs),
           # More references, or more of the timeline, than the read's one full page holds: cut at its bound (decision
           # 0234). A page that is not full and says there is more is a read short, not a bound.
           "cut": total > len(nodes) >= PAGE or more and len(events) >= EVENTS}, {}
    for node in events:
        kind = field(node, "__typename")
        if kind == "CrossReferencedEvent":
            source = field(node, "source")
            if source is not None:
                field(source, "__typename")    # held to its type whatever was read before it
            out["crossed"] = out["crossed"] or source is None or field(source, "__typename") != "Issue"
            continue
        if kind == "ReferencedEvent":
            # A commit's closing keyword leaves this, not a cross-reference; one whose commit cannot be read names it too.
            commit = field(node, "commit")
            oid = None if commit is None else field(commit, "oid")
            if commit is not None and not (isinstance(oid, str) and timeline.SHA.match(oid)):
                raise Unanswered("a commit's reference with no id")
            out["crossed"] = True
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
            # A person's close names no closer; a closer that names no type is a read that failed.
            closer = field(node, "closer")
            typed = field(closer, "__typename") if closer is not None else None
            if closer is not None and not (isinstance(typed, str) and typed):
                raise Unanswered("a closer of no type")
            if typed == "PullRequest":
                closed = _number(closer, repo)
                closes.setdefault(closed, []).append(at)
                unlisted = closed is None
            else:
                unlisted = closer is not None
            # One that cannot be listed by its number names the issue, of any life (decision 0218), and is passed over
            # in a life before: only one of the present life makes the list not whole, or names a merge commit.
            out["closed"] = out["closed"] or unlisted
            if not unlisted or at < began:
                continue
            if typed == "Commit":
                oid = field(closer, "oid")
                if not (isinstance(oid, str) and timeline.SHA.match(oid)):
                    raise Unanswered("a commit closer with no id")
                out["commits"].setdefault(oid, at)
            else:
                out["whole"] = False    # a pull request of another repo, or a closer of another kind
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


def entry(transport, read: dict, identities: dict, accounts: timeline.Accounts, join: dict, spans: dict,
          kernel=None) -> tuple:
    """`(the pull request as issue-facts/1 lists it, whether its timeline was whole, whether it was cut at its bound)`,
    from `read`, `join` and `spans`, each pull request's keyword spans as the pass records give them. Where the issue
    rule would act on it, with the Kernel's configuration `kernel` naming an author Role, the Factory's open draft
    carries its head's `checks` too (`adapters/draft_checks.py`, decision 0217), and its own `head` (issue 1059)."""
    number = read["number"]
    own, _ = pull.own(read, identities)
    # Bounded as the issue's own is: past the bound not whole, and the issue's facts say a timeline was cut, so it
    # defers on its own code and calls a person (decision 0234).
    events, whole, cut = timeline.bounded(transport, read)
    files = read.get("changed_files")
    if type(files) is not int or files < 0:
        raise Unanswered("a count of files that cannot be read")
    made = {"number": number, "class": own["class"], "opener": accounts.actor(read.get("user")),
            "open": own["state"] == "open", "draft": own["is_draft"],
            "opened_at": timeline._time(read.get("created_at")), "merged_at": _when(read.get("merged_at")),
            "closed_at": _when(read.get("closed_at")), "empty": files == 0,
            "label_events": timeline.label_events(events, accounts), "closed_issue_at": join["closers"].get(number),
            "draft_events": drafts(events), "link_events": join["links"].get(number, []),
            "keyword": number in join["refs"], "keyword_spans": spans.get(number, []), "close_events": closes(events, accounts)}
    if draft_checks.asked(kernel, own):
        made["checks"] = draft_checks.read(transport, read, kernel)
        made["head"] = draft_checks.head(read)
    return made, whole, cut


def linked_now(events: list) -> bool:
    """Whether a pull request is linked by hand now: its last link or unlinking on the issue's timeline, in the order
    the timeline gives them, is a link (trials/P-61.json)."""
    return bool(events) and events[-1]["action"] == "connected"


def on_default(read: dict) -> bool:
    """Whether a pull request's base is the default branch, as REST names both; refused where either cannot be read."""
    base = read.get("base") if isinstance(read.get("base"), dict) else {}
    held = base.get("repo") if isinstance(base.get("repo"), dict) else {}
    ref, default = base.get("ref"), held.get("default_branch")
    if not (isinstance(ref, str) and ref and isinstance(default, str) and default):
        raise Unanswered("the base or the default branch cannot be read")
    return ref == default


def listing(transport, repo: str, number: int, updated_at: str, began: str, identities: dict,
            accounts: timeline.Accounts, spans: dict, kernel=None) -> tuple:
    """`(linked, whole, named, cut)` for issue `number`: each pull request listed, by number; whether every part was
    read whole; whether a pull request names the issue, before any is left out, or anything but an issue
    cross-references it or a commit references it; and whether the read was cut at a bound: more than `CANDIDATES` to
    read, none of which is then read, or a listed pull request's timeline cut at its own (decision 0234).
    `began` is when its present life began, `identities` the class's accounts, `accounts` who acted, and `spans` each
    pull request a pass saw with its keyword, with its spans: one of those is listed whatever the references now say."""
    join = joined(transport, repo, number, updated_at, began)
    present = {n for n, at in join["closers"].items() if at >= began}
    candidates = sorted(join["refs"] | set(join["links"]) | present | set(spans))
    # Past the bound none is read: not whole, and cut, so the issue calls a person (decision 0234). Within it every one
    # is read, whole or not, so a record not whole still opens a span for each keyword it read (decision 0186).
    past = len(candidates) > CANDIDATES
    cut = past or join["cut"]
    found, whole = [], join["whole"] and not past
    for candidate in [] if past else candidates:
        got = pull.read(transport, repo, candidate)
        if not on_default(got):
            # A closer of this life, or one a pass saw with its keyword, to another base now is no link, and could
            # have been one: not whole. So is one linked by hand now: GitHub keeps its link and its closing reference
            # when its base moves (trials/P-69.json), and it could have been linked before any pass saw it (decision 0236).
            whole = whole and candidate not in present and candidate not in spans \
                and not linked_now(join["links"].get(candidate, []))
            continue
        made, read_whole, bounded = entry(transport, got, identities, accounts, join, spans, kernel)
        found.append((made, got.get("merge_commit_sha")))
        whole, cut = whole and read_whole, cut or bounded
    # A commit closer of the present life is a listed pull request's merge: its close, unless one of this life is earlier.
    for oid, at in join["commits"].items():
        merged = [made for made, sha in found if sha == oid and made["merged_at"] is not None]
        was = merged[0]["closed_issue_at"] if merged else None
        if merged and (was is None or was < began or at < was):
            merged[0]["closed_issue_at"] = at
        whole = whole and len(merged) == 1
    linked = [made for made, _ in found]
    named = bool(join["refs"] or join["links"] or join["closers"] or join["crossed"] or join["closed"])
    return linked, whole, named, cut


def read(transport, repo: str, number: int, updated_at: str, began: str, identities: dict,
         accounts: timeline.Accounts, earlier, kernel=None) -> tuple:
    """`(linked, whole, cut, broken)`, as `listing` reads them with the spans the pass records `earlier` give: whole
    where the list was read whole and the spans were too, or, where the records break the chain of spans, where they
    give no span and nothing names the issue; whether a listed pull request's timeline was cut at its bound; and whether
    the records break the chain of spans while something names the issue, which no later pass mends (decision 0253).
    `earlier` is the pass records before this pass, oldest first, or None."""
    spans, read_whole = keyword_spans.read(earlier, {"repo": repo, "type": "issue", "number": number})
    linked, whole, named, cut = listing(transport, repo, number, updated_at, began,
                                        identities, accounts, spans, kernel)
    broken = read_whole is None and named
    return linked, whole and (read_whole is True or read_whole is None and not named and not spans), cut, broken
