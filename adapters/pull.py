"""The facts of a pull request that its own reads give: what it is, who opened it and pushed it last, what it changes,
and whether each read was whole. Each function takes the transport and returns the part of `facts/1` it reads; the one
snapshot that puts the parts together, with reviews, threads and checks, is `adapters/facts.py` (#191, ruling 4).

Nothing here decides. A read that cannot be taken whole says so in its `complete` flag, and a fact that cannot be read
is null where `facts/1` allows it, never a guess (L-53, I-13). Text from GitHub reaches no part but the title, which is
handed beside the facts and never in them (decision 0039).
"""
from __future__ import annotations

import hashlib
import re

from adapters.github import DIFF, Unanswered, request

PAGE = 100          # files on one page of a pull request's list of files
FILE_HEADER = re.compile(r"^diff --git ", re.M)


def _ok(answer: dict, what: str):
    if answer["status"] != 200:
        raise Unanswered("%s answered %d" % (what, answer["status"]))
    return answer["body"]


def read(transport, repo: str, number: int) -> dict:
    """The pull request as GitHub's REST API gives it, read once; every part below is taken from this one read."""
    body = _ok(transport.send(request("GET", "/repos/%s/pulls/%d" % (repo, number))), "the pull request")
    if not isinstance(body, dict) or body.get("number") != number:
        raise Unanswered("the pull request's read is not pull request %d" % number)
    return body


def _login(actor) -> tuple:
    if not isinstance(actor, dict) or not actor.get("login") or actor.get("type") not in ("User", "Bot"):
        return None, None
    return actor["login"], actor["type"]


def own(pull: dict, identities: dict) -> tuple:
    """`item`, `state`, `is_draft`, `author`, `class` and `mergeable`, and the title beside them.

    The class is worked out from the author and from where the head is, never from a name's spelling alone: a head in
    another repo is `outside`; an author is `agent`, `maintainer` or `dependency` only as the account the caller's
    `identities` names for it, by its login and its account type, a User or a Bot; anyone else is `outside`, which asks
    for a person's admission and so fails closed (decisions 0005, 0026)."""
    login, kind = _login(pull.get("user"))
    head, base = pull.get("head") or {}, pull.get("base") or {}
    head_repo = ((head.get("repo") or {}).get("full_name"))
    base_repo = ((base.get("repo") or {}).get("full_name"))
    if login is None or not base_repo:
        raise Unanswered("the pull request's author or base cannot be read")
    if head_repo != base_repo:
        klass = "outside"
    else:
        klass = next((name for name in ("agent", "maintainer", "dependency")
                      if (login, kind) in identities.get(name, ())), "outside")
    state = "merged" if pull.get("merged_at") else pull.get("state")
    if state not in ("open", "closed", "merged") or not isinstance(pull.get("draft"), bool):
        raise Unanswered("the pull request's state cannot be read")
    mergeable = pull.get("mergeable") if pull.get("mergeable") in (True, False) else None
    part = {"item": {"repo": base_repo, "type": "pull_request", "number": pull["number"]}, "state": state,
            "is_draft": pull["draft"], "author": login, "class": klass, "mergeable": mergeable}
    return part, pull.get("title")


def targets_protected(transport, pull: dict) -> bool:
    """Whether the base branch is a protected one, from the branch itself as the pass reads it."""
    base = pull["base"]
    path = "/repos/%s/branches/%s" % (base["repo"]["full_name"], base["ref"])
    body = _ok(transport.send(request("GET", path)), "the base branch")
    if not isinstance(body, dict) or not isinstance(body.get("protected"), bool):
        raise Unanswered("the base branch's protection cannot be read")
    return body["protected"]


def last_pusher(transport, pull: dict):
    """The account that pushed the head, as GitHub records the push: the newest entry of the head branch's activity,
    its actor when its `after` is the head commit, a person's push and an App's alike, and null otherwise, which the
    Kernel reads as unreadable (decision 0026). A head in another repo is null: no Factory App reads a fork's
    activity until a trial grounds it. Never a commit's author or committer, which whoever makes the commit writes."""
    head = pull["head"]
    if (head.get("repo") or {}).get("full_name") != pull["base"]["repo"]["full_name"]:
        return None
    path = "/repos/%s/activity?ref=refs/heads/%s&per_page=10" % (head["repo"]["full_name"], head["ref"])
    entries = _ok(transport.send(request("GET", path)), "the head branch's activity")
    if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
        return None
    newest = entries[0]
    login, _ = _login(newest.get("actor"))
    return login if newest.get("after") == head.get("sha") else None


def _counts(text: str) -> tuple:
    added = deleted = 0
    for line in text.split("\n"):
        if line.startswith("+") and not line.startswith("+++ "):
            added += 1
        elif line.startswith("-") and not line.startswith("--- "):
            deleted += 1
    return len(FILE_HEADER.findall(text)), added, deleted


def diff(transport, pull: dict) -> dict:
    """`diff`, `content_id` and `complete.diff`, from the pull request's own diff against its merge base.

    The diff is checked against the counts of the same pull request's read, its files, added and deleted lines: a
    difference is a short read, `complete.diff` false. A 406 is GitHub's whole answer that it will not serve the diff:
    `truncated`, read whole, which holds the pull request as too large; its `content_id` is the head commit's, so any
    push is new content and nothing is read as unchanged (decision 0002). No read is built from `patch`."""
    files, added, deleted = pull.get("changed_files"), pull.get("additions"), pull.get("deletions")
    if not all(isinstance(n, int) and n >= 0 for n in (files, added, deleted)):
        raise Unanswered("the pull request's counts cannot be read")
    path = "/repos/%s/pulls/%d" % (pull["base"]["repo"]["full_name"], pull["number"])
    answer = transport.send(request("GET", path, accept=DIFF))
    size = {"files": files, "lines": added + deleted}
    if answer["status"] == 406:
        head = str(pull["head"].get("sha", ""))
        return {"diff": dict(size, truncated=True), "content_id": "sha256:" + hashlib.sha256(head.encode()).hexdigest(),
                "complete": True}
    text = _ok(answer, "the diff")
    if not isinstance(text, str):
        raise Unanswered("the diff is not text")
    whole = _counts(text) == (files, added, deleted)
    return {"diff": dict(size, truncated=False), "content_id": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
            "complete": whole}


def changed_paths(transport, pull: dict) -> dict:
    """`changed_paths` and `complete.changed_paths`: every file the pull request changes, page by page, each by its path
    and, for a rename or a copy, the path it had before. Whole only when every page was read and the list holds exactly
    as many files as the pull request's count; GitHub stops listing at 3,000, and a page past the end is a 200 with
    nothing in it, so a list that ends short of the count is read as short, never as the whole (P-29, decision 0020)."""
    want = pull.get("changed_files")
    if not isinstance(want, int) or want < 0:
        raise Unanswered("the pull request's count of files cannot be read")
    base = "/repos/%s/pulls/%d/files?per_page=%d" % (pull["base"]["repo"]["full_name"], pull["number"], PAGE)
    paths, page = [], 1
    while True:
        rows = _ok(transport.send(request("GET", base if page == 1 else "%s&page=%d" % (base, page))), "the files")
        if not isinstance(rows, list):
            raise Unanswered("a page of files is not a list")
        for row in rows:
            name = row.get("filename") if isinstance(row, dict) else None
            if not isinstance(name, str) or not name:
                return {"changed_paths": paths, "complete": False}
            moved = row.get("status") in ("renamed", "copied")
            before = row.get("previous_filename") if moved else None
            if moved and not (isinstance(before, str) and before):
                return {"changed_paths": paths, "complete": False}
            paths.append({"path": name, "previous": before})
        if len(rows) < PAGE or len(paths) >= want or page > want // PAGE + 1:
            break
        page += 1
    names = [p["path"] for p in paths]
    whole = len(paths) == want and len(set(names)) == len(names)
    return {"changed_paths": paths, "complete": whole}
