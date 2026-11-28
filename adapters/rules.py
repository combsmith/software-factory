"""The Factory's own rules as a commit holds them: `config/hooks.json` and `config/defaults.json` at the pull request's base
commit, read through the one transport with the token its caller holds, `GET /repos/{repo}/contents/{path}?ref={sha}`, in
the shape P-51 recorded a file read at a commit (issue 139).

What a Role's push may not touch is the base's list, never the head's, so that a change cannot take itself off it
(decisions 0020 and 0052). `sha` is the base commit from the trusted read of the pull request, never one the head
names: GitHub answers `?ref=` with a commit of any fork of the repo, so a sha the head chose could be a list it wrote.
The list is `tools/hooks/protected.py`'s reading of that text, the same function and syntax the Kernel's
`protected_paths` comes from: every protected path, and each input of a model Lens that `config/defaults.json` names at
that commit, the Kernel's `model_lens_inputs`, each once. A path that is only a deterministic Lens's input is not on it:
it is pushed, and converges only once every model Lens has reviewed its head (decision 0020). A list that cannot be
read, of any kind, or a commit that names no model Lens, whose review would hold such a path, is
`push_list_unreadable`, the Factory's fault, never an empty list.

`workflows_at` reads, at a commit, every workflow `.github/workflows` holds, for the push's own read of record 0239's
workflows at the base and at the commit it lands on, and of 0242's at the admitted commit and the default branch's
head. Which commits those are is its caller's: `harness/push.py`."""
from __future__ import annotations

import base64
import json
import re

from adapters.github import Unanswered, request
from tools.hooks import protected

PATH = "config/hooks.json"
DEFAULTS = "config/defaults.json"
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}")
SHA = re.compile(r"[0-9a-f]{40}")
UNREADABLE = "push_list_unreadable"
FOLDER = ".github/workflows"
WORKFLOWS_UNREADABLE = "workflows_unreadable"
ENTRIES = 1000      # GitHub lists at most this many entries of a folder: a listing of as many may have been cut
MOST = 50           # the workflows read at one commit; a folder that holds more is not read


def _file_at(transport, repo: str, path: str, sha: str):
    """The text of `path` at commit `sha` of `repo`, or None where it cannot be read as that one file."""
    try:
        answer = transport.send(request("GET", "/repos/%s/contents/%s?ref=%s" % (repo, path, sha)))
    except Unanswered:
        return None
    body = answer["body"]
    if answer["status"] != 200 or not isinstance(body, dict):
        return None
    size, content = body.get("size"), body.get("content")
    if body.get("type") != "file" or body.get("path") != path or type(size) is not int \
            or body.get("encoding") != "base64" or not isinstance(content, str):
        return None
    try:
        data = base64.b64decode(content.replace("\n", ""), validate=True)
        text = data.decode("utf-8")
    except ValueError:      # bad base64 and bytes no UTF-8 are ValueErrors
        return None
    return text if len(data) == size else None


def _unaskable(repo, sha) -> bool:
    """Whether `repo` and `sha` cannot name a commit of a repo, so are never asked."""
    return not isinstance(repo, str) or not REPO.fullmatch(repo) or repo.split("/")[1] in (".", "..") \
            or not isinstance(sha, str) or not SHA.fullmatch(sha)


def listed_at(transport, repo: str, sha: str) -> tuple:
    """`(patterns, None)`: what a push may not touch, as commit `sha` of `repo` holds it, every protected path and each
    model Lens's input, each once; or `(None, "push_list_unreadable")`."""
    if _unaskable(repo, sha):
        return None, UNREADABLE
    text = _file_at(transport, repo, PATH, sha)
    try:
        held = protected.parse(text) if text is not None else None
    except protected.Unreadable:
        held = None
    if held is None:
        return None, UNREADABLE
    # Which Lens is a model Lens is the base's word too: config/defaults.json at the same commit.
    said = _file_at(transport, repo, DEFAULTS, sha)
    try:
        models = json.loads(said)["required_lenses"]["model"] if said is not None else None
    except (ValueError, KeyError, TypeError):
        models = None
    if not isinstance(models, list) or not models or not all(isinstance(m, str) and m for m in models):
        return None, UNREADABLE
    return protected.push_of(held, models), None


def workflows_at(transport, repo: str, sha: str) -> tuple:
    """`(files, None)`: every workflow commit `sha` of `repo` holds, each file right in `.github/workflows` whose name
    ends `.yml` or `.yaml` in any case, mapped from its path to its text, for `guards/workflows.refusal_at`; or
    `(None, "workflows_unreadable")` where the folder, or any one of them, cannot be read whole. A commit with no such
    folder is one of those: GitHub answers it 404, as it answers one it cannot read, so a repo with none is refused."""
    if _unaskable(repo, sha):
        return None, WORKFLOWS_UNREADABLE
    try:
        answer = transport.send(request("GET", "/repos/%s/contents/%s?ref=%s" % (repo, FOLDER, sha)))
    except Unanswered:
        return None, WORKFLOWS_UNREADABLE
    listing = answer["body"]
    # A commit with no such folder is not told from one unread: GitHub answers both 404, so both are refused.
    if answer["status"] != 200 or not isinstance(listing, list) or len(listing) >= ENTRIES:
        return None, WORKFLOWS_UNREADABLE
    seen = []
    for entry in listing:
        name = entry.get("name") if isinstance(entry, dict) else None
        path = "%s/%s" % (FOLDER, name)
        if not isinstance(name, str) or not name or "/" in name or entry.get("path") != path or path in seen:
            return None, WORKFLOWS_UNREADABLE
        seen.append(path)
    paths = [path for path in seen if path.lower().endswith((".yml", ".yaml"))]
    if len(paths) > MOST:
        return None, WORKFLOWS_UNREADABLE
    files = {}
    for path in paths:
        # A link or a submodule listed under a workflow's name is no file of that path when read, so is refused.
        files[path] = _file_at(transport, repo, path, sha)
        if files[path] is None:
            return None, WORKFLOWS_UNREADABLE
    return files, None
