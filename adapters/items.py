"""The items port: the open pull requests of a repo, by number, with whether the list was read whole (design section
3.3, L-53). Each is then read on its own by `adapters/facts.py`; nothing here is a fact.

They are read by GraphQL, `pullRequests(states: OPEN)`, page by page in the order they were opened, so that a pull
request updated while the pages are read moves no other across a page (the shape `trials/P-32.json` recorded, read
there newest updated first). The list is whole only when every page was read, the last naming no next one, with as
many pull requests as GitHub counted on the first page and on every page since, each once, each of this repo. A page
GitHub answered with an error, or without the repo, is refused; a list read short says so and is never the whole
(L-53), so that the pass, refusing it, never reads a pull request that was not read as one that is not open."""
from __future__ import annotations

from adapters.github import Unanswered, request

PAGE = 100            # pull requests on one page
PAGES = 10            # pages read at most: a thousand open pull requests
QUERY = ("query OpenPullRequests($owner: String!, $name: String!, $after: String) {\n"
         "  repository(owner: $owner, name: $name) {\n"
         "    nameWithOwner\n"
         "    pullRequests(states: OPEN, first: %d, after: $after, orderBy: {field: CREATED_AT, direction: ASC}) {\n"
         "      totalCount\n"
         "      pageInfo { hasNextPage endCursor }\n"
         "      nodes { number }\n"
         "    }\n"
         "  }\n"
         "}" % PAGE)


def _page(transport, repo: str, after) -> dict:
    owner, name = repo.split("/")
    answer = transport.send(request("POST", "/graphql", body={
        "query": QUERY, "variables": {"owner": owner, "name": name, "after": after}}))
    body = answer["body"] if answer["status"] == 200 and isinstance(answer["body"], dict) else None
    data = body.get("data") if isinstance(body, dict) and "errors" not in body else None
    found = data.get("repository") if isinstance(data, dict) else None
    if not isinstance(found, dict) or found.get("nameWithOwner") != repo or not isinstance(found.get("pullRequests"), dict):
        raise Unanswered("the open pull requests of %s could not be read" % repo)
    return found["pullRequests"]


def open_pull_requests(transport, repo: str) -> tuple:
    """`(numbers, whole)`: every open pull request of `repo` read, by number, in the order opened, and whether that was
    every one GitHub counts."""
    numbers, count, after, whole = [], None, None, True
    for _ in range(PAGES):
        page = _page(transport, repo, after)
        total, info, nodes = page.get("totalCount"), page.get("pageInfo"), page.get("nodes")
        if type(total) is not int or total < 0 or not isinstance(info, dict) or not isinstance(nodes, list) \
                or not isinstance(info.get("hasNextPage"), bool):
            return numbers, False
        count = total if count is None else count
        whole = whole and total == count
        for node in nodes:
            number = node.get("number") if isinstance(node, dict) else None
            if type(number) is not int or number < 1:
                return numbers, False
            numbers.append(number)
        after = info.get("endCursor")
        if not info["hasNextPage"]:
            break
        if not isinstance(after, str) or not after:
            return numbers, False
    else:
        return numbers, False
    return numbers, whole and len(numbers) == count and len(set(numbers)) == len(numbers)
