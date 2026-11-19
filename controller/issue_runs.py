"""The items whose Runs the pass asks when they began (decisions 0193 and 0196, issue 836).

The records port asks the jobs only of the Runs of the items it is handed, fifty at most in one read. The entry hands
it what the pass decides: the open pull requests, and the open issues it serves, none while `issues.served_from` is
null. An issue's Runs, an investigating, a readiness or an opening Run, are asked as a pull request's are, within that
one bound: `kernel/issue.py` reads when such a Run began. Nothing is read here, and nothing decided."""
from __future__ import annotations


def asked_of(repo: str, pull_requests: list, issues: list) -> list:
    """Each open pull request, then each served open issue, of `repo`, as the records port tells an item: by its repo,
    its type and its number. A pull request and an issue of one number are two items."""
    return [{"repo": repo, "type": "pull_request", "number": number} for number in pull_requests] \
        + [{"repo": repo, "type": "issue", "number": number} for number in issues]
