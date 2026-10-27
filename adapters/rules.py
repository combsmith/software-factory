"""The Factory's own rules as a commit holds them: `config/hooks.json` at the pull request's base commit, read through the one
transport with the token its caller holds, `GET /repos/{repo}/contents/config/hooks.json?ref={sha}`, in the shape P-51
recorded a file read at a commit (issue 139).

What a Role's push may not touch is the base's list, never the head's, so that a change cannot take itself off it
(decisions 0020 and 0052). `sha` is the base commit from the trusted read of the pull request, never one the head
names: GitHub answers `?ref=` with a commit of any fork of the repo, so a sha the head chose could be a list it wrote. The list is `tools/hooks/protected.py`'s reading of that text, the same function and syntax
the Kernel's `protected_paths` comes from: every protected path and every Lens's input, each once, so a model Lens's
inputs, the Kernel's `model_lens_inputs`, among them. A list that cannot be read, of any kind, is
`push_list_unreadable`, the Factory's fault, never an empty list."""
from __future__ import annotations

import base64
import re

from adapters.github import Unanswered, request
from tools.hooks import protected

PATH = "config/hooks.json"
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}")
SHA = re.compile(r"[0-9a-f]{40}")
UNREADABLE = "push_list_unreadable"


def listed_at(transport, repo: str, sha: str) -> tuple:
    """`(patterns, None)`: what a push may not touch, as config/hooks.json holds it at commit `sha` of `repo`, every
    protected path and every Lens's input, each once; or `(None, "push_list_unreadable")`."""
    if not isinstance(repo, str) or not REPO.fullmatch(repo) or repo.split("/")[1] in (".", "..") \
            or not isinstance(sha, str) or not SHA.fullmatch(sha):
        return None, UNREADABLE
    try:
        answer = transport.send(request("GET", "/repos/%s/contents/%s?ref=%s" % (repo, PATH, sha)))
    except Unanswered:
        return None, UNREADABLE
    body = answer["body"]
    if answer["status"] != 200 or not isinstance(body, dict):
        return None, UNREADABLE
    size, content = body.get("size"), body.get("content")
    if body.get("type") != "file" or body.get("path") != PATH or type(size) is not int \
            or body.get("encoding") != "base64" or not isinstance(content, str):
        return None, UNREADABLE
    try:
        data = base64.b64decode(content.replace("\n", ""), validate=True)
        held = protected.parse(data.decode("utf-8"))
    except (ValueError, protected.Unreadable):      # bad base64 and bytes no UTF-8 are ValueErrors
        return None, UNREADABLE
    if len(data) != size:
        return None, UNREADABLE
    patterns = []
    for pattern in protected.protected_of(held):
        if pattern not in patterns:
            patterns.append(pattern)
    return patterns, None
