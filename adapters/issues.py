"""The issues port: one issue's facts, `issue-facts/1`, for `kernel/issue.py`'s `decide` (design sections 3.3 and 4.1).

The issue and its timeline are read by REST, the timeline by `adapters/timeline.py` as a pull request's is: whole only
when its last page names no next one, and an act an App made with a person's token, the opening among them, the App's
(decision 0218). One GraphQL read gives what REST does not, `lastEditedAt` and each change of the type: a key left out
refuses it, never reads as null. Both reads must name one `updatedAt`.

`content_id` hashes the title and the body, as the pull request's hashes its diff; neither text is kept.

The pull requests that close the issue are read by `adapters/linked.py`, after the rest and before the time is taken:
`linked` as it lists them, and `complete.linked` true only where it reads them whole and no pull request names the
issue, while their keyword spans are not read; so an issue any pull request names defers. The issue is read once more
after them, and refused if it moved. Not read yet, and said so: `branch_head`, which needs the count of pull requests
the Factory opened for the issue, is null. `complete.runs` is true: the pass puts the records port's answer in its place
(`controller/pass_.py`'s `asked`), and false here would leave every issue unreadable.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

from adapters import facts, linked, timeline
from adapters.github import Unanswered, raw, request
from kernel import gate
from tools.jsonschema_lite import validate

PAGE = 100            # changes of type read at most; more is not the whole timeline
STATES = ("open", "closed")
# Where each change of type names the type before and after: none, where it names neither.
TYPED = {"IssueTypeAddedEvent": (None, "issueType"), "IssueTypeChangedEvent": ("prevIssueType", "issueType"),
         "IssueTypeRemovedEvent": ("issueType", None)}
QUERY = """query IssueEdits($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    issue(number: $number) {
      number updatedAt lastEditedAt
      timelineItems(itemTypes: [ISSUE_TYPE_ADDED_EVENT, ISSUE_TYPE_CHANGED_EVENT, ISSUE_TYPE_REMOVED_EVENT], first: %d) {
        pageInfo { hasNextPage }
        nodes {
          __typename
          ... on IssueTypeAddedEvent { createdAt issueType { name } }
          ... on IssueTypeChangedEvent { createdAt prevIssueType { name } issueType { name } }
          ... on IssueTypeRemovedEvent { createdAt issueType { name } }
        }
      }
    }
  }
}""" % PAGE

SCHEMA = json.loads((pathlib.Path(__file__).resolve().parent.parent / "schemas" / "issue-facts.schema.json").read_text())


def own(transport, repo: str, number: int) -> dict:
    """The issue as REST gives it, read once; refused where it is not issue `number`, or is a pull request."""
    answer = transport.send(request("GET", "/repos/%s/issues/%d" % (repo, number)))
    body = answer["body"]
    if answer["status"] != 200 or not isinstance(body, dict) or body.get("number") != number or "pull_request" in body:
        raise Unanswered("issue %d of %s could not be read" % (number, repo))
    return body


def _field(node, key: str):
    """`node[key]`, which must be there: a key left out is never read as null (decision 0218)."""
    if not isinstance(node, dict) or key not in node:
        raise Unanswered("the answer leaves out %s" % key)
    return node[key]


def _type(found):
    """A type's name, or None for none; refused where it is neither."""
    if found is None:
        return None
    name = found.get("name") if isinstance(found, dict) else None
    if not isinstance(name, str) or not name:
        raise Unanswered("an issue type that names no type")
    return name


def edits(transport, repo: str, number: int) -> dict:
    """What REST does not give, from one GraphQL read: `updated_at`, `last_edited_at`, each change of type as
    `issue-facts/1` holds it, and whether the changes were read whole."""
    owner, name = repo.split("/")
    answer = transport.send(request("POST", "/graphql", body={
        "query": QUERY, "variables": {"owner": owner, "name": name, "number": number}}))
    body = answer["body"] if answer["status"] == 200 and isinstance(answer["body"], dict) else None
    if body is None or "errors" in body:
        raise Unanswered("the edits of issue %d of %s could not be read" % (number, repo))
    found = _field(_field(body, "data"), "repository")
    issue = _field(found, "issue")
    if _field(found, "nameWithOwner") != repo or _field(issue, "number") != number:
        raise Unanswered("the edits read are of another issue")
    listed = _field(issue, "timelineItems")
    more, nodes = _field(_field(listed, "pageInfo"), "hasNextPage"), _field(listed, "nodes")
    if not isinstance(more, bool) or not isinstance(nodes, list):
        raise Unanswered("the changes of the issue's type cannot be read")
    changes = []
    for node in nodes:
        kind = _field(node, "__typename")
        was, now = TYPED.get(kind, (0, 0)) if isinstance(kind, str) else (0, 0)
        if was == 0:
            raise Unanswered("a change of type of a kind not asked")
        changes.append({"from": _type(_field(node, was)) if was else None, "to": _type(_field(node, now)) if now else None,
                        "at": timeline._time(_field(node, "createdAt"))})
    last = _field(issue, "lastEditedAt")
    return {"updated_at": timeline._time(_field(issue, "updatedAt")),
            "last_edited_at": None if last is None else timeline._time(last), "type_events": changes, "whole": not more}


def content_changed_at(created: str, last_edited, events: list) -> str:
    """When the title or the body last changed: the newer of `lastEditedAt`, which moves for the body alone, and the
    timeline's last rename, or the creation while neither has moved (trials/P-34.json). No list of the body's edits is
    read: its first edit leaves one dated at the creation beside it."""
    times = [timeline._time(created)]
    if last_edited is not None:
        times.append(last_edited)
    times += [timeline._time(ev.get("created_at")) for ev in events if ev.get("event") == "renamed"]
    return max(times)


def life(created: str, events: list, accounts: timeline.Accounts) -> dict:
    """`life_started_at`, `reopened_last_by`, `reopened_last_at` and `closed_first_at`, from the closes and reopenings
    in the timeline's order. A reopening by a person with write access began a new life, whose first close is none
    yet; anyone else's, an App's with a person's token among them, leaves it as it was."""
    began, by, last, closed = timeline._time(created), "never", None, None
    for ev in events:
        ev = timeline._object(ev, "the timeline")
        if ev.get("event") == "reopened":
            last = timeline._time(ev.get("created_at"))
            if gate.is_person(accounts.acted(ev)):
                began, by, closed = last, "writer", None
            else:
                by = "other"
        elif ev.get("event") == "closed" and closed is None:
            closed = timeline._time(ev.get("created_at"))
    return {"life_started_at": began, "reopened_last_by": by, "reopened_last_at": last, "closed_first_at": closed}


def _names(listed, key: str) -> list:
    """Each name of a list REST gives on the issue; refused where one cannot be read."""
    names = [node.get(key) if isinstance(node, dict) else None for node in listed] if isinstance(listed, list) else [None]
    if not all(isinstance(name, str) and name for name in names):
        raise Unanswered("a name on the issue cannot be read")
    return names


def comments(events: list, accounts: timeline.Accounts) -> tuple:
    """`(role_comments, last_writer_comment_at)`: each Factory App's latest comment, by its name, the one configured for
    its id where the configuration holds it (`timeline.Accounts.named`), and a person with write access's last comment,
    or None. A comment an App made with a person's token is no person's."""
    latest, said = {}, None
    for ev in events:
        if ev.get("event") != "commented":
            continue
        who = accounts.acted(ev)
        login, ident, kind = accounts.account(ev.get("actor"))
        at = timeline._time(ev.get("created_at"))
        if (ident, kind) in accounts.factory:
            login = accounts.named(login, ident, kind)
            latest[login] = max(at, latest.get(login, at))
        elif gate.is_person(who):
            said = at if said is None or at > said else said
    return [{"by": login, "at": latest[login]} for login in sorted(latest)], said


def read(transport, repo: str, number: int, accounts: timeline.Accounts, clock=facts._utc, *, identities: dict) -> tuple:
    """`(facts, title)`: `issue-facts/1` for one issue of `repo`, held to its schema, and its title beside the facts,
    never in them, for the view alone. `accounts` tells who acted, the Factory's Apps among them, `identities` the class's
    accounts of a pull request that closes it (`adapters/pull.own`), and `clock` gives the time after the last read."""
    issue = own(transport, repo, number)
    events, whole = timeline.events(transport, {"number": number, "base": {"repo": {"full_name": repo}}})
    edited = edits(transport, repo, number)
    if edited["updated_at"] != _field(issue, "updated_at"):
        raise facts.Moved("the issue changed while it was read; it is read again at the next pass")
    title, body, state = _field(issue, "title"), _field(issue, "body"), _field(issue, "state")
    if state not in STATES or not isinstance(title, str) or not isinstance(body, (str, type(None))):
        raise Unanswered("the issue's state or content cannot be read")
    created = timeline._time(_field(issue, "created_at"))
    lived = life(created, events, accounts)
    # Who opened it is told as any act is (decision 0218).
    opened = {"actor": _field(issue, "user"), "performed_via_github_app": _field(issue, "performed_via_github_app")}
    author, labels = accounts.acted(opened), timeline.label_events(events, accounts)
    writer = timeline.since_writer(events, accounts)
    apps, said = comments(events, accounts)
    closing, closing_whole = linked.read(transport, repo, number, edited["updated_at"], lived["life_started_at"],
                                         identities, accounts)
    # A merge may have closed it since: read once more, as `adapters/pull.unchanged` does.
    if _field(own(transport, repo, number), "updated_at") != _field(issue, "updated_at"):
        raise facts.Moved("the issue changed while its pull requests were read; it is read again at the next pass")
    now = clock()
    found = dict(lived, **{
        "schema": "issue-facts/1",
        "item": {"repo": repo, "type": "issue", "number": number},
        "state": state,
        "author": author,
        "type": _type(_field(issue, "type")),
        "type_events": edited["type_events"],
        "label_names": _names(_field(issue, "labels"), "name"),
        "assignees": _names(_field(issue, "assignees"), "login"),
        "content_id": "sha256:" + hashlib.sha256(raw(json.dumps([title, body or ""], ensure_ascii=False))).hexdigest(),
        "content_changed_at": content_changed_at(created, edited["last_edited_at"], events),
        "label_events": labels,
        "linked": closing,
        "role_comments": apps,
        "last_writer_action_at": writer["last_writer_action_at"],
        "last_writer_comment_at": said,
        "acts_since_writer": writer["acts_since_writer"],
        "branch_head": None,
        "complete": {"timeline": whole and edited["whole"], "linked": closing_whole, "runs": True},
        "read_at": now,
    })
    problems = validate(found, SCHEMA)
    if problems:
        raise Unanswered("the issue's facts do not hold to issue-facts/1: %s" % problems[0])
    return found, title
