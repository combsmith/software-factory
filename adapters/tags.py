"""The Factory's tags, read as GitHub holds them: every ref under `refs/tags/factory/`, read through the one transport
(decision 0044; #197's rulings 2, 4 and 7). It hands back `{name: commit}`, each name without `refs/tags/`, or None
when the refs were not answered whole: an answer not a list of refs, a list GitHub says has another page, a name given
twice, or a tag that is not lightweight, whose sha is not its commit. It decides nothing: which name is a Release or a
Channel is `release/current.py`'s. It reads no file at any tag, so a rollback runs nothing of what it rolls back."""
from __future__ import annotations

import re

from adapters.github import Unanswered, request

PREFIX = "refs/tags/factory/"
SHA = re.compile(r"[0-9a-f]{40}")
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}")
NEXT_PAGE = re.compile(r'rel="next"')


def path(repo: str) -> str:
    """The read of every tag whose name begins `factory`; those not under `factory/` are passed over."""
    return "/repos/%s/git/matching-refs/tags/factory" % repo


def read(transport, repo: str):
    """Every `factory/` tag of `repo` and the commit it names, or None when they were not all read."""
    if transport is None or not isinstance(repo, str) or not REPO.fullmatch(repo) or repo.split("/")[1] in (".", ".."):
        return None
    try:
        answer = transport.send(request("GET", path(repo)))
    except Unanswered:
        return None
    body = answer["body"]
    headers = {str(k).lower(): str(v) for k, v in (answer.get("headers") or {}).items()}
    if answer["status"] != 200 or not isinstance(body, list) or NEXT_PAGE.search(headers.get("link", "")):
        return None
    refs = {}
    for ref in body:
        if not isinstance(ref, dict) or not isinstance(ref.get("ref"), str) or not isinstance(ref.get("object"), dict):
            return None
        if not ref["ref"].startswith(PREFIX):
            continue
        name, target = ref["ref"][len("refs/tags/"):], ref["object"]
        if name in refs or target.get("type") != "commit" or not isinstance(target.get("sha"), str) \
                or not SHA.fullmatch(target["sha"]):
            return None
        refs[name] = target["sha"]
    return refs
