"""The texts a Run's Task holds beside its diff: the body of each issue a pull request serves (decision 0110), and
what a Lens said on each of its own review threads a caller asks for (issue 856).

A review judges a change by what its issue asks (the rubric's PR-1), and a Task of the diff alone cannot. The issues are
the ones `adapters/acceptance.py` reads for the contract, by one rule: the one its branch binds it to, and else those it
closes. Each is read as GitHub gives it now, `by` naming who opened it, which is all GitHub says: `harness/task.py` holds an
issue's text `outside` whoever that is. An issue with no body has no text. What cannot be read whole raises, so that no
Task is built short of one.

A Lens's later review can rule on a Finding only if it is shown what it said. `findings` reads the first comment of each
thread asked for, by the thread's id, and holds it: a review thread of this pull request, whose first comment replies to
none and was written by that Lens's own account, as `adapters/timeline.Accounts` types it. It is a text as any other:
data a Task carries under its writer's trust, never a fact, a decision or a code. Which threads to ask for is the
caller's, from the facts; no caller asks yet."""
from __future__ import annotations

import re

from adapters import acceptance, threads as threads_
from adapters.github import Unanswered, request

THREADS = 50      # the most threads one call reads the texts of: a longer list raises, and none of it is read
# A review thread's id as GitHub gives one, and as a text's id carries it.
THREAD_ID = re.compile(r"[A-Za-z0-9_-]{1,100}")
THREAD = """query TextsThread($id: ID!) {
  node(id: $id) {
    __typename
    ... on PullRequestReviewThread {
      id
      pullRequest { number repository { nameWithOwner } }
      comments(first: 1) {
        nodes {
          body
          replyTo { id }
          author { __typename login ... on User { databaseId } ... on Bot { databaseId } }
        }
      }
    }
  }
}"""


def issues(transport, pull: dict, accounts, opener=None, opened=None) -> list:
    """`[{id, by, body}]`, one for each issue `pull` serves that has a body, in the order of their numbers."""
    numbers, whole = acceptance.served(transport, pull, opener, opened)
    if not whole:
        raise Unanswered("the issues the pull request serves cannot be read whole")
    repo = pull["base"]["repo"]["full_name"]
    found = []
    for number in numbers:
        answer = transport.send(request("GET", "/repos/%s/issues/%d" % (repo, number)))
        issue = answer["body"]
        if answer["status"] != 200 or not isinstance(issue, dict) or issue.get("number") != number or "pull_request" in issue:
            raise Unanswered("an issue the pull request serves answered %d" % answer["status"])
        body = issue.get("body")
        if body is None or body == "":
            continue
        if not isinstance(body, str):
            raise Unanswered("an issue's body cannot be read")
        found.append({"id": "issue:%d" % number, "by": accounts.actor(issue.get("user")), "body": body})
    return found


def findings(transport, pull: dict, accounts, lens: str, threads: list) -> list:
    """`[{id, by, body}]`: what `lens` said on each of `threads`, the ids of the review threads asked for, in the order
    given; `id` is `thread:` and the thread's id. Each is the first comment of a review thread of `pull`, written by
    that Lens's own account; anything else, or a thread that cannot be read, raises, and so does a list that is none,
    names a thread twice or an id GitHub gives none like, or is longer than THREADS: nothing is asked of GitHub then."""
    if not isinstance(threads, list) or len(threads) > THREADS or len(set(map(repr, threads))) != len(threads) \
            or not all(isinstance(t, str) and THREAD_ID.fullmatch(t) for t in threads):
        raise Unanswered("the threads asked for cannot be read as a list of threads")
    repo, found = pull["base"]["repo"]["full_name"], []
    for ident in threads:
        answer = transport.send(request("POST", "/graphql", body={"query": THREAD, "variables": {"id": ident}}))
        if answer["status"] != 200 or not isinstance(answer["body"], dict) or answer["body"].get("errors"):
            raise Unanswered("a thread's read answered %d" % answer["status"])
        node = (answer["body"].get("data") or {}).get("node")
        on = node.get("pullRequest") if isinstance(node, dict) else None
        if not isinstance(on, dict) or node.get("__typename") != "PullRequestReviewThread" or node.get("id") != ident \
                or on.get("number") != pull["number"] or (on.get("repository") or {}).get("nameWithOwner") != repo:
            raise Unanswered("a thread asked for is not that review thread of this pull request")
        comments = node.get("comments") if isinstance(node.get("comments"), dict) else {}
        first = comments.get("nodes") if isinstance(comments.get("nodes"), list) else None
        if not first or not isinstance(first[0], dict) or first[0].get("replyTo") is not None:
            raise Unanswered("a thread's first comment cannot be read as its opener's")
        by, body = accounts.actor(threads_._account(first[0].get("author"))), first[0].get("body")
        if by != {"kind": "lens", "name": lens, "can_write": False}:
            raise Unanswered("a thread's first comment is not the Lens's own")
        if not isinstance(body, str) or body == "":
            raise Unanswered("a thread's first comment has no text")
        found.append({"id": "thread:%s" % ident, "by": by, "body": body})
    return found
