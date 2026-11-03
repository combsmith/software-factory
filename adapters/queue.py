"""The queue App's writes (issue 381, decision 0129): an enqueue bound to a head, a dequeue, and the resolution of a
Lens's thread, each through the queue App's own token, narrowed to its item by `Queuing`.

The App holds `contents: write` and `metadata: read` alone, and each request here is one a trial recorded it making:
`GET /repos/{repo}/pulls/{n}` and the three mutations (trials/P-2.queue-app.json), its review threads read and resolved
(trials/P-5.queue.json), and the enqueue's `expectedHeadOid`, which GitHub refuses once the head moved
(trials/P-57.json, asked through the Maintainer's login; the App's own token is owed). Whether the pull request is in
the merge queue is read as an installation token narrowed to `metadata: read` read it (trials/P-2.least.json, the
Controller's App; the queue App's own token is owed). Each write is sent once and read
back from GitHub's answer. Whose fault a failure was is read from its status and from the pull request read again,
never from GitHub's words."""
from __future__ import annotations

import re

from adapters.github import Unanswered, request

# The documents, as the trials sent them: the enqueue as P-57's, the dequeue as P-2.queue-app's, the threads' read and
# the resolution as P-5.queue's, the threads' comments left out, since nothing here reads text.
ENQUEUE = ("mutation($id:ID!,$h:GitObjectID!){enqueuePullRequest(input:{pullRequestId:$id,expectedHeadOid:$h})"
           "{mergeQueueEntry{state}}}")
DEQUEUE = "mutation($id: ID!) { dequeuePullRequest(input: {id: $id}) { mergeQueueEntry { id state } } }"
THREADS = ("query($owner: String!, $name: String!, $pr: Int!) { repository(owner: $owner, name: $name) { pullRequest("
           "number: $pr) { reviewThreads(first: 100) { totalCount pageInfo { hasNextPage } nodes { id isResolved "
           "resolvedBy { login databaseId __typename } } } } } }")
# The merge queue's read, as P-2.least's Controller App sent it narrowed to `metadata: read`.
MEMBERSHIP = ("query($owner: String!, $name: String!, $pr: Int!) { repository(owner: $owner, name: $name) { mergeQueue("
              "branch: \"main\") { entries(first: 20) { totalCount nodes { position state pullRequest { number } } } } "
              "pullRequest(number: $pr) { isInMergeQueue mergeQueueEntry { position state } } } }")
RESOLVE = ("mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { id isResolved resolvedBy "
           "{ login databaseId __typename } } } }")
NODE = re.compile(r"PR_[A-Za-z0-9_-]{1,100}")
THREAD = re.compile(r"PRRT_[A-Za-z0-9_-]{1,100}")
SHA = re.compile(r"[0-9a-f]{40}")
REFUSED = (401, 403)
# What an entry of the merge queue may say of itself, once an enqueue is taken.
ENTRY_STATES = ("QUEUED", "AWAITING_CHECKS", "MERGEABLE", "UNMERGEABLE", "LOCKED")


class Queuing:
    """The queue App's transport, narrowed to one pull request: read it, read its review threads and whether it is
    queued, enqueue it at one head, dequeue it, and resolve one of its threads. A write names only the node id its own
    read of the pull request answered with, and a resolution only a thread its own read of the threads listed, so no
    other pull request of the repo, which the token reaches whole, is written. Anything else is refused before it
    leaves."""

    def __init__(self, transport, item: dict):
        self._transport, self._item = transport, dict(item)
        self._pull = "/repos/%s/pulls/%d" % (item["repo"], item["number"])
        self._node, self._threads = None, set()

    def _allowed(self, body) -> bool:
        if not isinstance(body, dict) or set(body) != {"query", "variables"} or not isinstance(body["variables"], dict):
            return False
        query, given = body["query"], body["variables"]

        def node(value, form) -> bool:
            return isinstance(value, str) and form.fullmatch(value) is not None
        owner, name = self._item["repo"].split("/")
        if query == ENQUEUE:
            return set(given) == {"id", "h"} and given["id"] == self._node and node(given["h"], SHA)
        if query == DEQUEUE:
            return set(given) == {"id"} and given["id"] == self._node
        if query == RESOLVE:
            return set(given) == {"id"} and node(given["id"], THREAD) and given["id"] in self._threads
        return query in (THREADS, MEMBERSHIP) and given == {"owner": owner, "name": name, "pr": self._item["number"]}

    def send(self, req: dict) -> dict:
        method, path, body = req.get("method"), req.get("path"), req.get("body")
        if method == "GET" and path == self._pull and body is None:
            answer = self._transport.send(req)
            read = _body(answer) or {}
            if read.get("number") == self._item["number"] and isinstance(read.get("node_id"), str) \
                    and NODE.fullmatch(read["node_id"]) is not None:
                self._node = read["node_id"]
            return answer
        if method == "POST" and path == "/graphql" and self._allowed(body):
            answer = self._transport.send(req)
            if body["query"] == THREADS:
                self._threads |= set(_listed(_body(answer)) or {})
            return answer
        raise Unanswered("a request the queue App's token may not send")


def _asked(transport, req: dict):
    try:
        return transport.send(req)
    except Unanswered:
        return None


def _ended(answer, state: str):
    """The fault of an answer that is no answer at all, or None: no answer or GitHub unavailable, and a token refused."""
    status = answer.get("status") if isinstance(answer, dict) else None
    if status in REFUSED:
        return {"state": "refused", "key": None, "fault": "environment", "reason": "token_refused"}
    if status is None or status >= 500:
        return {"state": state, "key": None, "fault": "environment", "reason": "github_unavailable"}
    return None


def _body(answer):
    body = answer.get("body") if isinstance(answer, dict) and answer.get("status") == 200 else None
    return body if isinstance(body, dict) else None


def pull(transport, item: dict) -> dict:
    """`{node, head, open, fault}` of the pull request, read again; a pull request that cannot be read is the
    environment's."""
    answer = _asked(transport, request("GET", "/repos/%s/pulls/%d" % (item["repo"], item["number"])))
    ended = _ended(answer, "refused")
    if ended is not None:
        return dict(ended, node=None, head=None, open=None)
    body = _body(answer)
    head = (body or {}).get("head")
    head = head.get("sha") if isinstance(head, dict) else None
    if body is None or body.get("number") != item["number"] or not isinstance(body.get("node_id"), str) \
            or NODE.fullmatch(body["node_id"]) is None or not isinstance(head, str) or SHA.fullmatch(head) is None \
            or body.get("state") not in ("open", "closed") or type(body.get("merged")) is not bool:
        return {"state": "refused", "key": None, "fault": "environment", "reason": "pull_unreadable", "node": None,
                "head": None, "open": None}
    return {"node": body["node_id"], "head": head, "open": body["state"] == "open" and not body["merged"], "fault": None}


def _changed(transport, item: dict, head: str):
    """Why the pull request read again is no longer the one the act was decided on, or None."""
    again = pull(transport, item)
    if again["fault"] is not None:
        return {"state": "failed", "key": None, "fault": again["fault"], "reason": again["reason"]}
    if not again["open"]:
        return {"state": "failed", "key": None, "fault": "superseded", "reason": "closed_under_act"}
    if again["head"] != head:
        return {"state": "failed", "key": None, "fault": "superseded", "reason": "head_moved"}
    return None


def enqueue(transport, item: dict, node: str, head: str) -> dict:
    """The enqueue of `node` at `head`, sent once: `applied`, keyed by the pull request's node id, only with an entry of
    the queue in GitHub's answer. A refusal is read from the pull request read again: a head that moved or a close is a
    change under the act; at the head it was decided on, open, it is the item's, which its attempts bound."""
    answer = _asked(transport, request("POST", "/graphql", body={"query": ENQUEUE, "variables": {"id": node, "h": head}}))
    ended = _ended(answer, "failed")
    if ended is not None:
        return ended
    body = _body(answer)
    if body is None:
        return {"state": "failed", "key": None, "fault": "environment", "reason": "not_read_back"}
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    entry = data.get("enqueuePullRequest")
    entry = entry.get("mergeQueueEntry") if isinstance(entry, dict) else None
    if not body.get("errors") and isinstance(entry, dict) and entry.get("state") in ENTRY_STATES:
        return {"state": "applied", "key": node, "fault": None, "reason": None}
    if not body.get("errors"):
        return {"state": "failed", "key": None, "fault": "environment", "reason": "not_read_back"}
    changed = _changed(transport, item, head)
    if changed is not None:
        return changed
    return {"state": "failed", "key": None, "fault": "item", "reason": "enqueue_refused"}


def dequeue(transport, node: str) -> dict:
    """The dequeue of `node`, sent once: `applied` only with the entry GitHub says it removed. A refusal claims nothing:
    the pull request may have left the queue already, which the next pass reads, or may still be in it."""
    answer = _asked(transport, request("POST", "/graphql", body={"query": DEQUEUE, "variables": {"id": node}}))
    ended = _ended(answer, "failed")
    if ended is not None:
        return ended
    body = _body(answer)
    data = (body or {}).get("data") if isinstance((body or {}).get("data"), dict) else {}
    entry = data.get("dequeuePullRequest")
    entry = entry.get("mergeQueueEntry") if isinstance(entry, dict) else None
    if body is not None and not body.get("errors") and isinstance(entry, dict) and isinstance(entry.get("id"), str):
        return {"state": "applied", "key": node, "fault": None, "reason": None}
    return {"state": "failed", "key": None, "fault": "environment", "reason": "dequeue_refused"}


def _pulled(body):
    """The pull request a GraphQL answer about this repository names, or None for an answer with errors or of another
    shape."""
    data = body.get("data") if isinstance(body, dict) and not body.get("errors") else None
    repository = data.get("repository") if isinstance(data, dict) else None
    found = repository.get("pullRequest") if isinstance(repository, dict) else None
    return found if isinstance(found, dict) else None


def _listed(body):
    """`{thread id: resolved}` of every review thread the answer lists, read whole, or None."""
    listed = (_pulled(body) or {}).get("reviewThreads")
    nodes = listed.get("nodes") if isinstance(listed, dict) else None
    page = listed.get("pageInfo") if isinstance(listed, dict) else None
    if not isinstance(nodes, list) or listed.get("totalCount") != len(nodes) \
            or not isinstance(page, dict) or page.get("hasNextPage") is not False \
            or not all(isinstance(n, dict) and isinstance(n.get("id"), str) and type(n.get("isResolved")) is bool
                       for n in nodes):
        return None
    return {n["id"]: n["isResolved"] for n in nodes}


def threads(transport, item: dict) -> dict:
    """`{fault, threads}`: each review thread's id and whether it is resolved, read whole, or a fault."""
    owner, name = item["repo"].split("/")
    answer = _asked(transport, request("POST", "/graphql", body={
        "query": THREADS, "variables": {"owner": owner, "name": name, "pr": item["number"]}}))
    ended = _ended(answer, "refused")
    if ended is not None:
        return {"fault": ended, "threads": None}
    listed = _listed(_body(answer))
    if listed is None:
        return {"fault": {"state": "refused", "key": None, "fault": "environment", "reason": "threads_unreadable"},
                "threads": None}
    return {"fault": None, "threads": listed}


def queued(transport, item: dict) -> dict:
    """`{fault, queued}`: whether the pull request is in the merge queue, or a fault, the environment's."""
    owner, name = item["repo"].split("/")
    answer = _asked(transport, request("POST", "/graphql", body={
        "query": MEMBERSHIP, "variables": {"owner": owner, "name": name, "pr": item["number"]}}))
    ended = _ended(answer, "refused")
    if ended is not None:
        return {"fault": ended, "queued": None}
    found = (_pulled(_body(answer)) or {}).get("isInMergeQueue")
    if type(found) is not bool:
        return {"fault": {"state": "refused", "key": None, "fault": "environment", "reason": "queue_unreadable"},
                "queued": None}
    return {"fault": None, "queued": found}


def resolve(transport, thread: str, login: str) -> dict:
    """The resolution of `thread`, sent once: `applied`, keyed by the thread's id, only when GitHub's answer says that
    thread is resolved by the queue App's own account."""
    answer = _asked(transport, request("POST", "/graphql", body={"query": RESOLVE, "variables": {"id": thread}}))
    ended = _ended(answer, "failed")
    if ended is not None:
        return ended
    body = _body(answer)
    data = (body or {}).get("data") if isinstance((body or {}).get("data"), dict) else {}
    back = data.get("resolveReviewThread")
    back = back.get("thread") if isinstance(back, dict) else None
    if body is None or body.get("errors"):
        return {"state": "failed", "key": None, "fault": "environment", "reason": "resolve_refused"}
    by = back.get("resolvedBy") if isinstance(back, dict) else None
    if isinstance(back, dict) and back.get("id") == thread and back.get("isResolved") is True and isinstance(by, dict) \
            and by.get("login") == login:
        return {"state": "applied", "key": thread, "fault": None, "reason": None}
    return {"state": "failed", "key": None, "fault": "environment", "reason": "not_read_back"}
