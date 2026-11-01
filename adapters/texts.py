"""The texts a Run's Task holds beside its diff: for now, the body of each issue a pull request serves (decision 0116).

A review judges a change by what its issue asks (the rubric's PR-1), and a Task of the diff alone cannot. The issues are
the ones `adapters/acceptance.py` reads for the contract, by one rule: the one its branch binds it to, and else those it
closes. Each is read as GitHub gives it now, `by` naming who opened it, which is all GitHub says: `harness/task.py` holds an
issue's text `outside` whoever that is. An issue with no body has no text. What cannot be read whole raises, so that no
Task is built short of one. A thread's text waits on the story that holds it."""
from __future__ import annotations

from adapters import acceptance
from adapters.github import Unanswered, request


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
