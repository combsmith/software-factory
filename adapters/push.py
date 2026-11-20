"""The push port: each request of a Role's push by GitHub's git data API, and GitHub's answer to it, through the one
transport (issue 838; P-71). It decides nothing. Which request may leave, in what order, and what an answer must say
before the next, is `guards/push.py`'s: the Harness asks its `permits` of a request this builds, sends it by `send`,
gives `seen` the answer, and stops at the first False or None.

One builder to a request, each giving `adapters/github.py`'s `request` as the guard reads it, or None for a part told
wrongly: a repo, a commit's, tree's or blob's name, or a work branch, `factory-work/issue-<N>-<k>` (decision 0068),
that is no such thing. The parts that name where a request goes are held here; what a body holds is the guard's to
judge and the token's to allow. `read_commit`, `read_tree` (every level), `read_blob` and `read_branch` read;
`make_blob`, `make_tree`, `make_commit` (on one parent) and `make_branch` write; `move_branch` moves the branch, never
by force.

`send` gives GitHub's answer as the guard's `seen` takes it, `{"status": the status as text, "body": what it said}`:
GitHub gives the status as a number (P-71), and the guard holds no number. A refusal, a 404 or a 422, is an answer and
is handed back as one, never raised: the guard reads the work branch's 404 as the branch the Decision admitted none
of, and takes no other. GitHub answers that 404 alike to a token that cannot read the repo, so a push reads with the
Role's own token, which can (P-71). A request the transport would not send, or GitHub did not answer, is None.

`content` gives a blob's bytes from its read: the base64 GitHub sends, which it ends with a newline (P-71), decoded
here, where the Harness reads them, and never in a guard, which may not import what decodes them. The guard is given
the answer as GitHub gave it.

`allowed(repo, branch)` is what a push's token may send, for `adapters/effects.py`'s `Allowed`: the four reads; a
blob in base64; a tree upon another, of files written or removed; a commit of one parent; the work branch made, or
moved with `force` false. Never a DELETE, a force, or another ref.
"""
from __future__ import annotations

import base64
import hashlib
import re

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
    if not _repo(repo):
        return None
    return request("POST", _git(repo) + "blobs", body={"content": content, "encoding": "base64"})


def make_tree(repo, base, entries):
    """A tree upon the tree `base`, of `entries`, each `{"path", "mode", "type", "sha"}`, a removed file's sha None."""
    if not (_repo(repo) and _sha(base)):
        return None
    return request("POST", _git(repo) + "trees", body={"base_tree": base, "tree": entries})


def make_commit(repo, message, tree, parent):
    """A commit of `tree` whose one parent is `parent`."""
    if not _repo(repo):
        return None
    return request("POST", _git(repo) + "commits", body={"message": message, "tree": tree, "parents": [parent]})


def make_branch(repo, branch, sha):
    """The work branch, made at the commit `sha`."""
    if not (_repo(repo) and _work(branch)):
        return None
    return request("POST", _git(repo) + "refs", body={"ref": HEADS + branch, "sha": sha})


def move_branch(repo, branch, sha):
    """The work branch, moved to the commit `sha` without force: GitHub refuses a move that is no fast-forward."""
    if not (_repo(repo) and _work(branch)):
        return None
    return request("PATCH", _git(repo) + "refs/heads/" + branch, body={"sha": sha, "force": False})


def send(transport, req):
    """GitHub's answer to `req`, `{"status": the status as text, "body": what it said}`, or None where `req` is none,
    the transport would not send it, or GitHub gave no answer with a status."""
    if req is None:
        return None
    try:
        answer = transport.send(req)
    except Unanswered:
        return None
    status = answer.get("status") if isinstance(answer, dict) else None
    if type(status) is not int:
        return None
    return {"status": str(status), "body": answer.get("body")}


def content(answer, sha):
    """The bytes of the blob `sha`, from `send`'s answer to its read: its `content` read as base64 past the newlines
    GitHub puts in it, and nothing else let pass; None where the answer is no success, no base64, or bytes whose git
    name is not `sha`."""
    body = answer.get("body") if isinstance(answer, dict) and answer.get("status") == "200" else None
    if not isinstance(body, dict) or body.get("encoding") != "base64" or not isinstance(body.get("content"), str):
        return None
    try:
        data = base64.b64decode(body["content"].replace("\n", ""), validate=True)
    except ValueError:
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
        return type(body) is dict and set(body) == {"content", "encoding"} and isinstance(body["content"], str) \
            and body["encoding"] == "base64"

    def entry(item) -> bool:
        return type(item) is dict and set(item) == {"path", "mode", "type", "sha"} and isinstance(item["path"], str) \
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
