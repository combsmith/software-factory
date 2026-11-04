"""A pull request's description edits, as `facts/1` holds them: the time of its last, or null if it was never edited
(design section 3.3, decision 0140).

One GraphQL read, the query trials/P-58.reader.json recorded word for word, which a token narrowed to
`pull_requests: read` is answered (the reader App's grant). An edit of the description moves `lastEditedAt` and adds to
`userContentEdits`, whoever made it, a bot's or an App's among them, and a push or a title's edit moves neither
(trials/P-58.json). The time is the later of `lastEditedAt` and every edit's `editedAt`, never a `createdAt`: the opening
text's entry is made only with the first later edit, and takes that edit's `createdAt` (P-58). An edit whose revision a
writer deleted from the history still happened, and counts. No editor is read: whoever edited, the edit holds the item
(decision 0140), so no description's text and no account is kept.

The list is whole only when it says there is no next page and its count is every edit it lists; a count below the
edits it lists, or anything not in GraphQL's shape, cannot be read. Past the first hundred,
or short, `lastEditedAt` alone gives the time, since it moves on every edit and on nothing else; short with no
`lastEditedAt`, it is unread. The two must agree on whether the description was ever edited: one names an edit the other
does not, and nothing is read. Anything that cannot be read refuses the snapshot, never reads as no edit.
"""
from __future__ import annotations

import re

from adapters.github import Unanswered, request

TIME = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z")
QUERY = ("query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number)"
         "{lastEditedAt editor{__typename login} userContentEdits(first:100){totalCount pageInfo{hasNextPage endCursor} "
         "nodes{editedAt createdAt deletedAt editor{__typename login ... on User{databaseId} ... on Bot{databaseId}}}}}}}")


def _time(value) -> bool:
    return isinstance(value, str) and TIME.fullmatch(value) is not None


def last_edited_at(transport, pull: dict):
    """When the pull request's description was last edited, or None if it never was; refused where it cannot be read."""
    owner, name = pull["base"]["repo"]["full_name"].split("/")
    variables = {"owner": owner, "name": name, "number": pull["number"]}
    answer = transport.send(request("POST", "/graphql", body={"query": QUERY, "variables": variables}))
    if answer["status"] != 200 or not isinstance(answer["body"], dict) or answer["body"].get("errors"):
        raise Unanswered("the description's edits answered %d" % answer["status"])
    data = answer["body"].get("data")
    repo = data.get("repository") if isinstance(data, dict) else None
    pr = repo.get("pullRequest") if isinstance(repo, dict) else None
    if not isinstance(pr, dict) or "lastEditedAt" not in pr:
        raise Unanswered("the description's edits name no pull request")
    last = pr["lastEditedAt"]
    if last is not None and not _time(last):
        raise Unanswered("the description's last edit has no time that can be read")
    listed = pr.get("userContentEdits")
    page = listed.get("pageInfo") if isinstance(listed, dict) else None
    nodes = listed.get("nodes") if isinstance(listed, dict) else None
    total = listed.get("totalCount") if isinstance(listed, dict) else None
    if not isinstance(nodes, list) or not isinstance(page, dict) or type(page.get("hasNextPage")) is not bool \
            or type(total) is not int or total < len(nodes):
        raise Unanswered("the description's edits cannot be read")
    times = []
    for node in nodes:
        if not isinstance(node, dict) or not _time(node.get("editedAt")):
            raise Unanswered("an edit of the description has no time that can be read")
        times.append(node["editedAt"])
    if page["hasNextPage"] or total != len(nodes):
        if last is None:
            raise Unanswered("the description's edits were not read whole, and name no last edit")
        return max([last] + times)
    if (last is None) != (not times):
        raise Unanswered("the description's last edit and its edits disagree on whether it was edited")
    return max([last] + times) if times else None
