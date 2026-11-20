"""The push port: each request of a Role's push by GitHub's git data API, and GitHub's answer to it, through the push's
own sender (issue 838; P-71). It decides nothing. Which request may leave, in what order, and what an answer must say
before the next, is `guards/push.py`'s: the Harness asks its `permits` of a request this builds, sends that request by
`send`, gives `seen` the answer, and stops at the first False or None.

One builder to a request, each giving `adapters/github.py`'s `request` as the guard reads it, or None for a part told
wrongly: a repo, a commit's, tree's or blob's name, a blob's content that is no text, or a work branch,
`factory-work/issue-<N>-<k>` (decision 0068), that is no such thing. What a body holds is the guard's to judge and the
token's to allow. `read_commit`, `read_tree` (every level), `read_blob` and `read_branch` read; `make_blob`,
`make_tree` (of a copy of its entries), `make_commit` (on one parent) and `make_branch` write; `move_branch` moves the
branch, never by force.

`transport(live, repo, branch)` is the push's sender, `adapters/effects.py`'s `Allowed` with `allowed(repo, branch)`,
what a push's token may send: the four reads; a blob in base64; a tree upon another, of files written or removed, each
by a path that names a file; a commit of one parent; the work branch made, or moved with `force` false. Never a
DELETE, a force, or another ref. `send(sender, repo, branch, req)` sends by that sender alone: a bare transport, an
`Allowed` made otherwise, or a sender bound to another repo or branch sends nothing.

`send` gives GitHub's answer as `seen` takes it, `{"status": the status as text, "body": what it said}`: GitHub gives a
number (P-71), and the guard holds none. A refusal, a 404 or a 422, is an answer, never raised: the guard reads the
work branch's 404 as the branch the Decision admitted none of, and takes no other. GitHub answers that 404 alike to a
token that cannot read the repo, so a push reads with the Role's own token, which can (P-71). A request the sender
would not send, a body that is no JSON, or an answer with no status from 100 to 599 or no body, is None, never raised.

`content` gives a blob's bytes from its read, the base64 GitHub wraps and ends with newlines (P-71), decoded here and
never in a guard, which may not import what decodes them; they are held to the name asked, never the answer's own.

`harness/push.py`, by hand, owes this port: every request sent by `transport`'s sender; its writers named in
`tools/check_writes.py`'s CALLERS; one request built and given unchanged to `permits` and `send`; `content` asked for
the name the admitted tree's listing gives, never the answer's `sha`; and P-71 replayed through `send` into `seen`.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import re

from adapters.effects import Allowed
from adapters.github import Unanswered, request

SHA = re.compile(r"[0-9a-f]{40}")
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}")
WORK = re.compile(r"factory-work/issue-[1-9][0-9]{0,18}-[1-9][0-9]{0,18}")
HEADS = "refs/heads/"
# The modes of a file a push writes or removes: a symlink or a submodule is none (`guards/patch.py`).
FILE_MODES = ("100644", "100755")


def _repo(repo) -> bool:
    return isinstance(repo, str) and REPO.fullmatch(repo) is not None and repo.split("/")[1] not in (".", "..")


def _sha(said) -> bool:
    return isinstance(said, str) and SHA.fullmatch(said) is not None


def _work(branch) -> bool:
    return isinstance(branch, str) and WORK.fullmatch(branch) is not None


def _decoded(text):
    """The bytes of base64 as GitHub reads it, its alphabet padded to fours past the newlines it wraps it with; None
    for anything else."""
    if not isinstance(text, str):
        return None
    try:
        return base64.b64decode(text.replace("\n", ""), validate=True)
    except ValueError:
        return None


def _file(path) -> bool:
    """Whether `path` names a file in a tree: text of parts each named, none of them `.` or `..`."""
    return isinstance(path, str) and all(part not in ("", ".", "..") for part in path.split("/"))


def _git(repo: str) -> str:
    return "/repos/%s/git/" % repo


def read_commit(repo, sha):
    """A commit's read, by its name."""
    if not (_repo(repo) and _sha(sha)):
        return None
    return request("GET", _git(repo) + "commits/" + sha)


def read_tree(repo, sha):
    """A tree's read, every level of it, by its name."""
    if not (_repo(repo) and _sha(sha)):
        return None
    return request("GET", _git(repo) + "trees/" + sha + "?recursive=1")


def read_blob(repo, sha):
    """A blob's read, by its name: its bytes in base64."""
    if not (_repo(repo) and _sha(sha)):
        return None
    return request("GET", _git(repo) + "blobs/" + sha)


def read_branch(repo, branch):
    """The work branch's read: the commit it is at, or GitHub's 404 where it does not stand."""
    if not (_repo(repo) and _work(branch)):
        return None
    return request("GET", _git(repo) + "ref/heads/" + branch)


def make_blob(repo, content):
    """A blob of a file's bytes, `content` their base64."""
    if not (_repo(repo) and isinstance(content, str)):
        return None
    return request("POST", _git(repo) + "blobs", body={"content": content, "encoding": "base64"})


def make_tree(repo, base, entries):
    """A tree upon the tree `base`, of `entries`, each `{"path", "mode", "type", "sha"}`, a removed file's sha None."""
    if not (_repo(repo) and _sha(base)):
        return None
    return request("POST", _git(repo) + "trees", body={"base_tree": base, "tree": copy.deepcopy(entries)})


def make_commit(repo, message, tree, parent):
    """A commit of `tree` whose one parent is `parent`."""
    if not (_repo(repo) and _sha(tree) and _sha(parent)):
        return None
    return request("POST", _git(repo) + "commits", body={"message": message, "tree": tree, "parents": [parent]})


def make_branch(repo, branch, sha):
    """The work branch, made at the commit `sha`."""
    if not (_repo(repo) and _work(branch) and _sha(sha)):
        return None
    return request("POST", _git(repo) + "refs", body={"ref": HEADS + branch, "sha": sha})


def move_branch(repo, branch, sha):
    """The work branch, moved to the commit `sha` without force: GitHub refuses a move that is no fast-forward."""
    if not (_repo(repo) and _work(branch) and _sha(sha)):
        return None
    return request("PATCH", _git(repo) + "refs/heads/" + branch, body={"sha": sha, "force": False})


class _Sender(Allowed):
    """A push's sender: `Allowed` with what a push's token may send on one repo and its one work branch, `bound`."""

    def __init__(self, live, repo, branch):
        super().__init__(live, *allowed(repo, branch))
        self.bound = (repo, branch)


def transport(live, repo, branch):
    """The push's sender on `live`, bound to `repo` and its work branch `branch`; None for either told wrongly."""
    if not (_repo(repo) and _work(branch)):
        return None
    return _Sender(live, repo, branch)


def send(sender, repo, branch, req):
    """GitHub's answer to `req`, `{"status": the status as text, "body": what it said}`, or None where `req` is none,
    `sender` is not `transport`'s for `repo` and `branch`, it would not send `req` or could not as JSON, or GitHub gave
    no answer with a status and a body."""
    if req is None or type(sender) is not _Sender or sender.bound != (repo, branch):
        return None
    try:
        answer = sender.send(req)
    except (Unanswered, TypeError, ValueError):
        return None
    status = answer.get("status") if isinstance(answer, dict) else None
    if type(status) is not int or not 100 <= status <= 599 or "body" not in answer:
        return None
    return {"status": str(status), "body": answer["body"]}


def content(answer, sha):
    """The bytes of the blob `sha`, from `send`'s answer to its read: its `content` read as base64 past the newlines
    GitHub puts in it, and nothing else let pass; None where the answer is no success, no base64, or bytes whose git
    name is not `sha`."""
    body = answer.get("body") if isinstance(answer, dict) and answer.get("status") == "200" else None
    if not isinstance(body, dict) or body.get("encoding") != "base64":
        return None
    data = _decoded(body.get("content"))
    if data is None:
        return None
    # Git names a blob by sha1 of `blob <size>\0` and its bytes: the hash is git's, compared with git's own.
    if hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest() != sha:
        return None
    return data


def allowed(repo, branch) -> tuple:
    """`(permits, patterns)` for `Allowed`: what a push's token may send on `repo`'s git data, its one work branch
    `branch` among it; nothing at all for a repo or a branch told wrongly."""
    if not (_repo(repo) and _work(branch)):
        return {}, []
    git = _git(repo)

    def nothing(body) -> bool:
        return body is None

    def blob(body) -> bool:
        return type(body) is dict and set(body) == {"content", "encoding"} and _decoded(body["content"]) is not None \
            and body["encoding"] == "base64"

    def entry(item) -> bool:
        return type(item) is dict and set(item) == {"path", "mode", "type", "sha"} and _file(item["path"]) \
            and item["mode"] in FILE_MODES and item["type"] == "blob" and (item["sha"] is None or _sha(item["sha"]))

    def tree(body) -> bool:
        return type(body) is dict and set(body) == {"base_tree", "tree"} and _sha(body["base_tree"]) \
            and type(body["tree"]) is list and all(entry(item) for item in body["tree"])

    def commit(body) -> bool:
        return type(body) is dict and set(body) == {"message", "tree", "parents"} and isinstance(body["message"], str) \
            and _sha(body["tree"]) and type(body["parents"]) is list and len(body["parents"]) == 1 \
            and _sha(body["parents"][0])

    def made(body) -> bool:
        return type(body) is dict and set(body) == {"ref", "sha"} and body["ref"] == HEADS + branch and _sha(body["sha"])

    def moved(body) -> bool:
        return type(body) is dict and set(body) == {"sha", "force"} and _sha(body["sha"]) and body["force"] is False

    permits = {("GET", git + "ref/heads/" + branch): nothing, ("POST", git + "blobs"): blob,
               ("POST", git + "trees"): tree, ("POST", git + "commits"): commit, ("POST", git + "refs"): made,
               ("PATCH", git + "refs/heads/" + branch): moved}
    patterns = [("GET", re.compile(re.escape(git + "commits/") + SHA.pattern), nothing),
                ("GET", re.compile(re.escape(git + "trees/") + SHA.pattern + re.escape("?recursive=1")), nothing),
                ("GET", re.compile(re.escape(git + "blobs/") + SHA.pattern), nothing)]
    return permits, patterns
