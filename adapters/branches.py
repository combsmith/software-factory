"""The work branch's head: the commit at the head of the branch the next opening Run on an issue would push to, or that
no such branch stands, or that neither can be told (decision 0242, issue 1059).

The branch is `kernel/terms.py`'s `WORK_BRANCH`, `factory-work/issue-<N>-<k>`: N the issue, k one more than the count
of pull requests the Factory has opened for it (decision 0068). That count is read from GitHub, which keeps every pull
request for ever: the pull requests of each branch `factory-work/issue-<N>-1`, `-2` and on, in every state, by REST's
`head` filter, counting a branch while the App that opens the Factory's pull requests authored one of them, and
stopping at the first that holds no pull request at all. A branch with pull requests, none the opener's, or the
opener's from another repo, cannot be told the Factory's or not, and is not told. Its account is the caller's `opener`, `adapters/facts.py`'s `opener_of`:
with no Role named to open pull requests (`None`), or one whose App cannot be told (`acceptance.UNTOLD`), the count
cannot be told and nothing is asked. So is it where a list cannot be read whole, and past `MOST` branches.

The head is then read by the branch's own ref, as `default_head` reads the default branch's: a commit, or GitHub's 404
for a branch that does not stand (`trials/P-71.json`). Any other answer, a ref of another name or an object that is no
commit, is read as neither. A count that cannot be told names no branch, and is never read as "no branch".
"""
from __future__ import annotations

import re
import urllib.parse

from adapters.acceptance import UNTOLD
from adapters.github import Unanswered, request
from kernel import terms

WORK = "factory-work/issue-%d-%d"
BRANCH = re.compile(terms.WORK_BRANCH)
MOST = 100            # branches of one issue read at most: more pull requests than any brake lets the Factory open
PAGE = 100            # pull requests of one branch on its one page
SHA = re.compile(r"[0-9a-f]{40}")
NEXT = "next"           # anywhere in the link header: a next page, quoted or not, as GitHub writes it, in lower case


def _opened(transport, repo: str, branch: str, opener):
    """Whether the opener authored a pull request of `repo` on `branch`, in any state; None where the list cannot be
    read whole: an answer that is no list of pull requests, or one that names a next page; and where it cannot be told
    whose the branch is: the opener's pull request from another repo, or, with none of the opener's, anyone else's; nor
    is a branch the opener opened two pull requests on one pull request opened."""
    owner = repo.split("/")[0]
    query = urllib.parse.urlencode({"state": "all", "head": owner + ":" + branch, "per_page": PAGE})
    answer = transport.send(request("GET", "/repos/%s/pulls?%s" % (repo, query)))
    rows = answer["body"] if answer["status"] == 200 else None
    if not isinstance(rows, list) or NEXT in str(answer["headers"].get("link", "")):
        return None
    if not all(isinstance(r, dict) and isinstance(r.get("user"), dict) and isinstance(r.get("head"), dict)
               and type(r["user"].get("id")) is int and isinstance(r["user"].get("type"), str)
               and r["head"].get("ref") == branch for r in rows):
        return None
    mine = [r for r in rows if (r["user"].get("id"), r["user"].get("type")) == tuple(opener)]
    if any(not isinstance(r["head"].get("repo"), dict) or r["head"]["repo"].get("full_name") != repo for r in mine):
        return None
    if not mine and rows or len(mine) > 1:
        return None
    return bool(mine)


def opened_count(transport, repo: str, number: int, opener):
    """The count of pull requests the Factory has opened for issue `number` of `repo`, by their branches; None where it
    cannot be told: no opener, or one untold, a list read short, or more than `MOST` branches."""
    if opener is None or opener == UNTOLD:
        return None
    for k in range(1, MOST + 1):
        found = _opened(transport, repo, WORK % (number, k), opener)
        if found is None:
            return None
        if not found:
            return k - 1
    return None


def work_head(transport, repo: str, number: int, opener) -> tuple:
    """`(head, whole)` of the branch the next opening Run on issue `number` would push to: `(sha, True)` where it stands,
    `(None, True)` where GitHub says it does not, and `(None, False)` where neither can be told."""
    try:
        count = opened_count(transport, repo, number, opener)
        if count is None:
            return None, False
        branch = WORK % (number, count + 1)
        if not BRANCH.fullmatch(branch):
            return None, False
        answer = transport.send(request("GET", "/repos/%s/git/ref/heads/%s" % (repo, branch)))
    except Unanswered:
        return None, False
    if answer["status"] == 404:
        return None, True
    ref = answer["body"] if answer["status"] == 200 and isinstance(answer["body"], dict) else {}
    head = ref.get("object") if isinstance(ref.get("object"), dict) else {}
    sha = head.get("sha")
    if ref.get("ref") != "refs/heads/" + branch or head.get("type") != "commit" \
            or not (isinstance(sha, str) and SHA.fullmatch(sha)):
        return None, False
    return sha, True
