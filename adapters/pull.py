"""The facts of a pull request that its own reads give: what it is, who opened it and pushed it last, what it changes,
and whether each read was whole. Each function takes the transport and returns the part of `facts/1` it reads; the one
snapshot that puts the parts together, with reviews, threads and checks, is `adapters/facts.py` (#191, ruling 4). It
reads the pull request first and calls `same_head` last, so that every part is of the head the first read named.

Nothing here decides. A read that cannot be taken whole says so in its `complete` flag, and a fact that cannot be read
is null where `facts/1` allows it, or refused, never a guess (L-53, I-13). Text from GitHub reaches no part but the
title, which is handed beside the facts and never in them (decision 0039).
"""
from __future__ import annotations

import hashlib
import re
import urllib.parse

from adapters.github import DIFF, Unanswered, raw, request

PAGE = 100          # files on one page of a pull request's list of files
# What GitHub says of a file. A rename and a copy carry the name the file had; no other status does.
STATUSES = {"added", "removed", "modified", "renamed", "copied", "changed", "unchanged"}
MOVED = {"renamed", "copied"}
SHA = re.compile(r"^[0-9a-f]{40}$")
HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")
# The account type each class needs: the Factory's Apps and a dependency bot are Bots, the Maintainer a person.
KINDS = {"agent": "Bot", "maintainer": "User", "dependency": "Bot"}


def _ok(answer: dict, what: str):
    if answer["status"] != 200:
        raise Unanswered("%s answered %d" % (what, answer["status"]))
    return answer["body"]


def _ref(name: str) -> str:
    """A branch's name as a part of a path or a query: `#`, `%`, `&`, `+` and a space mean only themselves."""
    if not isinstance(name, str) or not name:
        raise Unanswered("a branch's name cannot be read")
    return urllib.parse.quote(name, safe="/")


def read(transport, repo: str, number: int) -> dict:
    """The pull request as GitHub's REST API gives it, read once; every part below is taken from this one read."""
    body = _ok(transport.send(request("GET", "/repos/%s/pulls/%d" % (repo, number))), "the pull request")
    if not isinstance(body, dict) or body.get("number") != number:
        raise Unanswered("the pull request's read is not pull request %d" % number)
    if not SHA.match(str((body.get("head") or {}).get("sha", ""))):
        raise Unanswered("the pull request's head commit cannot be read")
    return body


def same_head(transport, pull: dict) -> bool:
    """Whether the pull request is still at the head commit and on the base the first read named, read once more after
    every other part: a push, or a retarget that keeps the head, in between makes the parts of two pull requests, and
    the snapshot is then refused and read again."""
    again = read(transport, pull["base"]["repo"]["full_name"], pull["number"])
    base, was = again.get("base") or {}, pull["base"]
    return (again["head"]["sha"] == pull["head"]["sha"] and base.get("ref") == was.get("ref")
            and (base.get("repo") or {}).get("id") == (was.get("repo") or {}).get("id"))


def _account(actor) -> tuple:
    if not isinstance(actor, dict) or not actor.get("login") or actor.get("type") not in ("User", "Bot"):
        return None, None, None
    if not isinstance(actor.get("id"), int) or isinstance(actor.get("id"), bool):
        return None, None, None
    return actor["login"], actor["id"], actor["type"]


def own(pull: dict, identities: dict) -> tuple:
    """`item`, `state`, `is_draft`, `author`, `class` and `mergeable`, and the title beside them.

    The class is worked out from the author and from where the head is, never from a name's spelling: a head in another
    repo is `outside`; an author is `agent`, `maintainer` or `dependency` only as the account the caller's `identities`
    names for it, by its id, which a rename keeps, and its account type, a Bot for an App and a User for the
    Maintainer; anyone else is `outside`, which asks for a person's admission and so fails closed (decisions 0005,
    0026)."""
    login, ident, kind = _account(pull.get("user"))
    head, base = pull.get("head") or {}, pull.get("base") or {}
    head_repo, base_repo = (head.get("repo") or {}), (base.get("repo") or {})
    if login is None or not base_repo.get("full_name") or not isinstance(base_repo.get("id"), int):
        raise Unanswered("the pull request's author or base cannot be read")
    if head_repo.get("id") != base_repo["id"]:
        klass = "outside"
    else:
        klass = next((name for name, need in KINDS.items()
                      if kind == need and (ident, kind) in identities.get(name, ())), "outside")
    state = "merged" if pull.get("merged_at") else pull.get("state")
    if state not in ("open", "closed", "merged") or not isinstance(pull.get("draft"), bool):
        raise Unanswered("the pull request's state cannot be read")
    mergeable = pull.get("mergeable") if pull.get("mergeable") in (True, False) else None
    part = {"item": {"repo": base_repo["full_name"], "type": "pull_request", "number": pull["number"]},
            "state": state, "is_draft": pull["draft"], "author": login, "class": klass, "mergeable": mergeable}
    return part, pull.get("title")


def base(transport, pull: dict) -> dict:
    """The base branch as the pass reads it: whether it is protected, and its head commit, which a review's content is
    compared against, never the pull request's `base.sha`, which moves only when the head is pushed (P-29)."""
    branch = pull["base"]
    path = "/repos/%s/branches/%s" % (branch["repo"]["full_name"], _ref(branch.get("ref")))
    body = _ok(transport.send(request("GET", path)), "the base branch")
    if not isinstance(body, dict) or not isinstance(body.get("protected"), bool):
        raise Unanswered("the base branch's protection cannot be read")
    head = (body.get("commit") or {}).get("sha") if isinstance(body.get("commit"), dict) else None
    if not SHA.match(str(head)):
        raise Unanswered("the base branch's head commit cannot be read")
    return {"protected": body["protected"], "head": head}


def targets_protected(transport, pull: dict) -> bool:
    """Whether the base branch is a protected one, from the branch itself as the pass reads it."""
    return base(transport, pull)["protected"]


def last_pusher(transport, pull: dict):
    """The account that pushed the head, as GitHub records the push: the newest entry of the head branch's activity,
    its actor when its `after` is the head commit, a person's push and an App's alike, and null otherwise, which the
    Kernel reads as unreadable; an older entry is never read (decision 0026). A head in another repo is null: no
    Factory App reads a fork's activity until a trial grounds it. Never a commit's author or committer."""
    return last_push(transport, pull)[0]


def last_push(transport, pull: dict) -> tuple:
    """`(last pusher, when)`: the newest activity entry's actor and time when its `after` is the head, else
    `(None, None)`: one read for both, so the time is the push's own."""
    head = pull["head"]
    if (head.get("repo") or {}).get("id") != pull["base"]["repo"].get("id"):
        return None, None
    path = "/repos/%s/activity?ref=refs/heads/%s&per_page=10" % (head["repo"]["full_name"], _ref(head.get("ref")))
    entries = _ok(transport.send(request("GET", path)), "the head branch's activity")
    if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
        return None, None
    newest = entries[0]
    login, _, _ = _account(newest.get("actor"))
    if newest.get("after") != head.get("sha") or login is None:
        return None, None
    return login, _iso(newest.get("timestamp"))


def _iso(value):
    """An activity entry's timestamp, which GitHub gives with a Z, or None where it cannot be read."""
    return value if isinstance(value, str) and re.fullmatch(
        r"[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z", value) else None


def _counts(text: str):
    """Files, added and deleted lines, read from each hunk by its own header's counts, so that a line of content that
    begins `+++ ` or `--- ` is counted as the line it is. None where a hunk runs short or a line is neither."""
    files = added = deleted = 0
    old = new = 0
    for line in text.split("\n"):
        if old or new:
            if line.startswith("\\"):
                continue
            mark = line[:1]
            if mark == " ":
                old, new = old - 1, new - 1
            elif mark == "-":
                old, deleted = old - 1, deleted + 1
            elif mark == "+":
                new, added = new - 1, added + 1
            else:
                return None
            if old < 0 or new < 0:
                return None
            continue
        if line.startswith("diff --git "):
            files += 1
            continue
        hunk = HUNK.match(line)
        if hunk:
            old = int(hunk.group(1)) if hunk.group(1) is not None else 1
            new = int(hunk.group(2)) if hunk.group(2) is not None else 1
    if old or new:
        return None
    return files, added, deleted


def diff(transport, pull: dict) -> dict:
    """`diff`, `content_id` and `complete.diff`, from the pull request's own diff against its merge base.

    The diff is checked against the counts of the same pull request's read, its files, added and deleted lines: a
    difference is a short read, `complete.diff` false. The content id is the sha256 of the bytes GitHub sent. A 406
    `too_large` is GitHub's whole answer that it will not serve the diff: `truncated`, read whole, which holds the pull
    request as too large; its `content_id` is the head commit's, so any push is new content and nothing is read as
    unchanged (decision 0002). Any other 406 is refused. No read is built from `patch`."""
    files, added, deleted = pull.get("changed_files"), pull.get("additions"), pull.get("deletions")
    if not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (files, added, deleted)):
        raise Unanswered("the pull request's counts cannot be read")
    head = str(pull["head"].get("sha", ""))
    if not SHA.match(head):
        raise Unanswered("the pull request's head commit cannot be read")
    path = "/repos/%s/pulls/%d" % (pull["base"]["repo"]["full_name"], pull["number"])
    answer = transport.send(request("GET", path, accept=DIFF))
    size = {"files": files, "lines": added + deleted}
    if answer["status"] == 406:
        errors = (answer["body"] or {}).get("errors") if isinstance(answer["body"], dict) else None
        if not any(isinstance(e, dict) and e.get("code") == "too_large" for e in errors or ()):
            raise Unanswered("the diff answered 406, but not too_large")
        return {"diff": dict(size, truncated=True), "content_id": "sha256:" + hashlib.sha256(head.encode()).hexdigest(),
                "complete": True}
    text = _ok(answer, "the diff")
    if not isinstance(text, str):
        raise Unanswered("the diff is not text")
    whole = _counts(text) == (files, added, deleted)
    return {"diff": dict(size, truncated=False), "content_id": "sha256:" + hashlib.sha256(raw(text)).hexdigest(),
            "complete": whole}


def changed_paths(transport, pull: dict) -> dict:
    """`changed_paths` and `complete.changed_paths`: every file the pull request changes, page by page, each by its path
    and, for a rename or a copy, the path it had before. Whole only when every page was read and the list holds exactly
    as many files as the pull request's count, each once; GitHub stops listing at 3,000, and a page past the end is a
    200 with nothing in it, so a list that ends short of the count is read as short, never as the whole (P-29, decision
    0020)."""
    want = pull.get("changed_files")
    if not isinstance(want, int) or isinstance(want, bool) or want < 0:
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
            status = row.get("status")
            moved = status in MOVED
            before = row.get("previous_filename") if moved else None
            # A status GitHub does not give, a move without its old name, or an old name on anything but a move, is a
            # row that cannot be read: the list is short, never read as an ordinary change.
            if status not in STATUSES or (moved and not (isinstance(before, str) and before)) \
                    or (not moved and row.get("previous_filename") is not None):
                return {"changed_paths": paths, "complete": False}
            paths.append({"path": name, "previous": before})
        if len(rows) < PAGE or len(paths) >= want:
            break
        page += 1
    names = [p["path"] for p in paths]
    whole = len(paths) == want and len(set(names)) == len(names)
    return {"changed_paths": paths, "complete": whole}
