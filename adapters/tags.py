"""The Factory's tags, read as GitHub holds them: every ref under `refs/tags/factory/`, read through the one transport
(decision 0044; #197's rulings 2, 4 and 7). It hands back `{name: commit}`, each name without `refs/tags/`, or None
when the refs were not answered whole: an answer not a list of refs, a next page that is not this list's next, more
than MOST_PAGES of them, a name given twice, or a tag that is not lightweight, whose sha is not its commit. GitHub may
page the list, thirty to a page; each next page is read by the link GitHub gives for it, held to this list's own: of
this repo, by its name, or by the id GitHub gives for it, read once when a link names one. It decides nothing: which
name is a Release or a Channel is `release/current.py`'s. It reads no file at any tag, so a rollback runs nothing of
what it rolls back.

`write` sends one of `release/cut.py`'s writes, through the token it is given, the release App's alone: a Release
created, never one that exists, and `next`, the one Channel a step moves, created the first time and moved with
`force` after, by the refs read before it; `stable` is never written here. It says whether GitHub answered the write
as made; whether the ref now names the commit is the read after it."""
from __future__ import annotations

import re

from adapters.github import Unanswered, request
from release import current

PREFIX = "refs/tags/factory/"
SHA = re.compile(r"[0-9a-f]{40}")
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}")
NEXT_PAGE = re.compile(r'rel="next"')
NEXT_LINK = re.compile(r'<https://api\.github\.com(/[^<>\s]*)>;\s*rel="next"')
# This list's own next page, by the repo's name or its id, as GitHub writes a link: page 2 and after, nothing else.
PAGED = re.compile(r"/(?:repos/(?P<name>[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100})|repositories/(?P<id>[1-9][0-9]{0,11}))"
                   r"/git/matching-refs/tags/factory\?(?:per_page=[1-9][0-9]{0,2}&)?page=(?P<page>[1-9][0-9]{0,3})")
MOST_PAGES = 40     # 1,200 tags at thirty to a page: a list longer than that is not read whole


def _repo(repo) -> bool:
    return isinstance(repo, str) and REPO.fullmatch(repo) is not None and repo.split("/")[1] not in (".", "..")


def path(repo: str) -> str:
    """The read of every tag whose name begins `factory`; those not under `factory/` are passed over."""
    return "/repos/%s/git/matching-refs/tags/factory" % repo


def _page(transport, asked: str, refs: dict):
    """The next page's path after reading `asked` into `refs`, "" when it was the last, or None when not read whole."""
    try:
        answer = transport.send(request("GET", asked))
    except Unanswered:
        return None
    body = answer["body"]
    headers = {str(k).lower(): str(v) for k, v in (answer.get("headers") or {}).items()}
    if answer["status"] != 200 or not isinstance(body, list):
        return None
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
    link = headers.get("link", "")
    if not NEXT_PAGE.search(link):
        return ""
    found = NEXT_LINK.search(link)
    return found.group(1) if found else None


def _ours(transport, repo: str, paged, known: dict) -> bool:
    """Whether a next page's link is of `repo`: by its name, as GitHub keeps names, without regard to case, or by the id
    GitHub gives for `repo` itself, read once."""
    if paged.group("name") is not None:
        return paged.group("name").lower() == repo.lower()
    if "id" not in known:
        try:
            answer = transport.send(request("GET", "/repos/%s" % repo))
        except Unanswered:
            return False
        body = answer["body"]
        ident = body.get("id") if answer["status"] == 200 and isinstance(body, dict) else None
        known["id"] = ident if type(ident) is int and ident > 0 else None
    return known["id"] is not None and int(paged.group("id")) == known["id"]


def read(transport, repo: str):
    """Every `factory/` tag of `repo` and the commit it names, or None when they were not all read."""
    if transport is None or not isinstance(repo, str) or not REPO.fullmatch(repo) or repo.split("/")[1] in (".", ".."):
        return None
    refs, asked, known = {}, path(repo), {}
    for number in range(2, MOST_PAGES + 2):
        asked = _page(transport, asked, refs)
        if asked == "":
            return refs
        paged = PAGED.fullmatch(asked) if asked else None
        if paged is None or int(paged.group("page")) != number or not _ours(transport, repo, paged, known):
            return None
    return None


def write(transport, repo: str, planned, refs) -> bool:
    """Send one planned write, `("create", Release, commit)` or `("move", Channel, commit)`, given the refs read before
    it. True only when GitHub answered it as made: 201 for a ref created, 200 for a Channel moved."""
    if transport is None or not _repo(repo) or not isinstance(refs, dict) or not isinstance(planned, (tuple, list)) \
            or len(planned) != 3:
        return False
    kind, name, commit = planned
    if not (isinstance(commit, str) and SHA.fullmatch(commit)):
        return False
    if kind == "create" and current.version(name) and name not in refs:
        req, wanted = request("POST", "/repos/%s/git/refs" % repo, body={"ref": "refs/tags/" + name, "sha": commit}), 201
    elif kind == "move" and current.channel(name)[1:] == ("next",) and name not in refs:
        req, wanted = request("POST", "/repos/%s/git/refs" % repo, body={"ref": "refs/tags/" + name, "sha": commit}), 201
    elif kind == "move" and current.channel(name)[1:] == ("next",):
        req, wanted = request("PATCH", "/repos/%s/git/refs/tags/%s" % (repo, name),
                              body={"sha": commit, "force": True}), 200
    else:
        return False
    try:
        answer = transport.send(req)
    except Unanswered:
        return False
    body = answer["body"]
    return answer["status"] == wanted and isinstance(body, dict) and body.get("ref") == "refs/tags/" + name \
        and isinstance(body.get("object"), dict) and body["object"].get("sha") == commit
