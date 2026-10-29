"""A pull request's review threads, as `facts/1` holds them: each thread's id, whether it is resolved and by whom, and
who opened it and when, with its Finding's category and severity where the facts can give them (design section 3.3).

One GraphQL read of the threads, page by page. Who opened a thread is its first comment's author, and when, that
comment's time: a first comment that replies to another is not the opener's, and the thread is refused. Who resolved
it is GitHub's `resolvedBy`, by its account id alone: GraphQL types it a User whoever resolved it, an App among them
(trials/P-49.json), so its type is never read. The id is matched to the thread's comment author, whose type GraphQL
gives, or else to the repo's permission read of its login, which answers the account's id and type
(trials/P-53.json), once a login a pass. A resolver neither answers, or that GitHub names none for, has `resolved_by`
null, and the Kernel defers on that thread alone (`unreadable_thread`). A thread whose first comment was deleted reads
its reply as its opener, since GitHub keeps no link to the comment (trials/P-53.json); `adapters/applied.py` holds it
to the Lens's own record. Each actor is told by its account id and type,
never by a name's spelling (decision 0005, L-57), and its write access read once a login, as `adapters/timeline.py`
does. No comment's text is read. A thread whose opener GitHub no longer names, a deleted account's, is refused with the
snapshot, as an unreadable actor is anywhere: the known cost is that such a pull request is never read whole. A thread
deleted and another made between two pages leaves the count the same and one unread, as the rollup can.

A thread a person opened is `human`, with no severity (section 3.3). Any other thread, a Lens's among them, has neither:
a required Lens's category and severity come from its own Finding record, in its Run's `applied/1`, joined by
`surface.key` (decisions 0038 and 0069) in `adapters/applied.py`, never here. A thread is a Lens's only when
its author is that Lens's own App, by account id and type, as the caller names it: an outside reviewer's, CodeRabbit's
or Codex's, is no required Lens's, and gates nothing. The Kernel reads a required model Lens's own App's open thread
with neither as unreadable, and defers on it alone (`kernel/derive.py`'s `unreadable_thread`).

The list is whole only when its last page says there is no next one, every thread it counts was read, and none twice;
a cursor that repeats, or a next page past the count, ends the read short, as `adapters/checks.py` does for the rollup.
"""
from __future__ import annotations

import re

from adapters import timeline
from adapters.github import Unanswered, request

PAGE = 100
TIME = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z")
QUERY = """query FactsThreads($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: %d, after: $after) {
        totalCount
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved
          resolvedBy { login databaseId }
          comments(first: 1) {
            nodes {
              createdAt
              replyTo { id }
              author { __typename login ... on User { databaseId } ... on Bot { databaseId } }
            }
          }
        }
      }
    }
  }
}""" % PAGE


def _account(author, kind=None):
    """A GraphQL actor as the REST user object `timeline.Accounts` reads: its login, its id and its type."""
    if not isinstance(author, dict):
        raise Unanswered("a thread's actor cannot be read")
    kind = kind or author.get("__typename")
    return {"login": author.get("login"), "id": author.get("databaseId"), "type": kind}


def _resolver(by, author, accounts: timeline.Accounts):
    """Who resolved a thread, as `facts/1` holds an actor, or None where it cannot be told (decision 0067, issue 331).

    GraphQL's `resolvedBy` is typed a User whoever resolved it, an App among them (trials/P-49.json), so its type is
    never read. Its account id is matched to the thread's own comment author, whose type GraphQL gives; failing that,
    to the repo's permission read of its login, which answers the account's id and type (trials/P-53.json), held to
    the id. An id neither answers, or a read that fails, leaves the resolver unread, and the Kernel defers on the thread
    (`kernel/derive.py`'s `unreadable_thread`)."""
    if not isinstance(by, dict):
        return None
    ident = by.get("databaseId")
    if not isinstance(ident, int) or isinstance(ident, bool) or ident < 1:
        return None
    if isinstance(author, dict) and author.get("databaseId") == ident and author.get("__typename") in ("User", "Bot") \
            and not isinstance(author.get("databaseId"), bool):
        return accounts.actor(_account(author))
    kind = accounts.typed(by.get("login"), ident)
    if kind is None:
        return None
    try:
        return accounts.actor({"login": by["login"], "id": ident, "type": kind})
    except Unanswered:
        # An account typed but not read whole, its access among it: the resolver alone is unread.
        return None


def thread(node: dict, accounts: timeline.Accounts) -> dict:
    """One thread as `facts/1` holds it; refused when any part GitHub gives cannot be read."""
    ident, resolved = node.get("id"), node.get("isResolved")
    comments = node.get("comments") if isinstance(node.get("comments"), dict) else {}
    first = comments.get("nodes") if isinstance(comments.get("nodes"), list) else None
    if not isinstance(ident, str) or not ident or type(resolved) is not bool or not first \
            or not isinstance(first[0], dict):
        raise Unanswered("a review thread's id, state or first comment cannot be read")
    if first[0].get("replyTo") is not None:
        raise Unanswered("a review thread's first comment replies to another: its opener cannot be read")
    opened_at = first[0].get("createdAt")
    if not (isinstance(opened_at, str) and TIME.fullmatch(opened_at)):
        raise Unanswered("a review thread's time cannot be read")
    opened_by = accounts.actor(_account(first[0].get("author")))
    by = node.get("resolvedBy")
    if not resolved and by is not None:
        raise Unanswered("an open review thread that names who resolved it")
    resolved_by = _resolver(by, first[0].get("author"), accounts) if by is not None else None
    human = opened_by["kind"] == "human"
    # A Lens's ruling is its own record's, joined by `adapters/applied.held`; GitHub holds none (issue 389).
    return {"id": ident, "resolved": resolved, "opened_by": opened_by, "category": "human" if human else None,
            "severity": None, "resolved_by": resolved_by, "opened_at": opened_at, "ruling": None}


def read(transport, pull: dict, accounts: timeline.Accounts, kept=None) -> tuple:
    """Every review thread of the pull request, and whether they were read whole. `kept`, where given, keeps each node
    as GitHub gave it, and the same whole, for reconciliation (`adapters/seen.py`)."""
    nodes = []
    found, whole = _read(transport, pull, accounts, nodes)
    if kept is not None:
        kept["threads"] = (nodes, whole)
    return found, whole


def _read(transport, pull: dict, accounts: timeline.Accounts, nodes: list) -> tuple:
    owner, name = pull["base"]["repo"]["full_name"].split("/")
    found, after, total, ids, cursors = [], None, None, [], set()
    while True:
        variables = {"owner": owner, "name": name, "number": pull["number"], "after": after}
        answer = transport.send(request("POST", "/graphql", body={"query": QUERY, "variables": variables}))
        if answer["status"] != 200 or not isinstance(answer["body"], dict) or answer["body"].get("errors"):
            raise Unanswered("the threads' read answered %d" % answer["status"])
        pr = (((answer["body"].get("data") or {}).get("repository") or {}).get("pullRequest")) or {}
        listed = pr.get("reviewThreads")
        page = listed.get("pageInfo") if isinstance(listed, dict) else None
        if not isinstance(listed, dict) or not isinstance(listed.get("nodes"), list) or not isinstance(page, dict):
            return found, False
        counted = listed.get("totalCount")
        total = counted if total is None else total
        if not isinstance(total, int) or isinstance(total, bool) or counted != total:
            return found, False
        for node in listed["nodes"]:
            if not isinstance(node, dict):
                raise Unanswered("a review thread is not one GitHub gives")
            found.append(thread(node, accounts))
            nodes.append(node)
            ids.append(found[-1]["id"])
        if page.get("hasNextPage") is False:
            return found, len(ids) == total and len(set(ids)) == len(ids)
        cursor = page.get("endCursor")
        if page.get("hasNextPage") is not True or not isinstance(cursor, str) or not cursor or cursor in cursors \
                or len(ids) >= total:
            return found, False
        cursors.add(cursor)
        after = cursor
