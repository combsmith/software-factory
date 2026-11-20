"""The push port's token: what a Role's push may send by GitHub's git data API (issue 838; P-71). It decides nothing.

`allowed(repo, branch)` is what a push's token may send, as `adapters/effects.py`'s `Allowed` takes it: a commit's,
a tree's (every level) or a blob's read by its name, and the read of the work branch, `factory-work/issue-<N>-<k>`
(decision 0068); a blob in base64; a tree upon another, of files written or removed, each by a path that names a file,
and none written where another written needs a directory; a commit of one parent; the work branch made, or moved with
`force` false. Never a DELETE, a force, or another ref; never a body that holds anything but JSON, each thing of its
exact kind; and nothing at all for a repo or a branch told wrongly, or told as text of another kind.

The builders of each request, the push's own sender on this token, and `send` and `content`, which hand GitHub's
answers on, come next (issue 838).
"""
from __future__ import annotations

import base64
import re

SHA = re.compile(r"[0-9a-f]{40}")
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}")
WORK = re.compile(r"factory-work/issue-[1-9][0-9]{0,18}-[1-9][0-9]{0,18}")
HEADS = "refs/heads/"
# The modes of a file a push writes or removes: a symlink or a submodule is none (`guards/patch.py`).
FILE_MODES = ("100644", "100755")
# The most things a body may hold: a tree's entry is five, so no push the Factory makes comes near it, and a value that
# holds itself reaches it.
MOST = 100000
# The longest base64 a blob's content may be, newlines and all, read before it is decoded. GitHub's blob API takes no
# file over 100 MB, 133,333,336 characters of base64, so a text past 2 ** 27 is no blob it takes.
MOST_BASE64 = 134217728
# Base64's alphabet, without its padding.
ALPHABET = re.compile(r"[A-Za-z0-9+/]*")
# git's own directory, and the head of the short name another file system gives it (`git~1`), as `guards/patch.py`.
GIT_OWN = ".git"
GIT_SHORT = "git~"


def _plain(value) -> bool:
    """Whether `value` holds what JSON reads and nothing else, each thing of its exact kind: a mapping of text to such
    things, a list of them, text, a whole number, true, false or null, and no more than `MOST` things. Text of another
    kind may say it equals anything, or be checked as one text and sent as another, so a body that holds one is held to
    nothing. A number with a fraction is none: no body of a push holds one. Read without recursion, so a value nested
    however deep is read, and refused, without raising."""
    left, held = [value], 1
    while left:
        value = left.pop()
        if type(value) is dict or type(value) is list:
            held += len(value)
            if held > MOST:
                return False
            if type(value) is dict and not all(type(key) is str for key in value):
                return False
            left.extend(value.values() if type(value) is dict else value)
        elif value is not None and type(value) is not str and type(value) is not int and type(value) is not bool:
            return False
    return True


def _repo(repo) -> bool:
    return type(repo) is str and REPO.fullmatch(repo) is not None and repo.split("/")[1] not in (".", "..")


def _sha(said) -> bool:
    return type(said) is str and SHA.fullmatch(said) is not None


def _work(branch) -> bool:
    return type(branch) is str and WORK.fullmatch(branch) is not None


def _decoded(text):
    """The bytes of base64 as GitHub reads it, its alphabet padded to fours past the newlines it wraps it with; None
    for anything else, or for a text longer than `MOST_BASE64`. Its `=` are at its end, at most two, so what is before
    them leaves 2 or 3 over a four: held here, not by Python's decoder, which takes `YWJj=`, and `YWJj====` on some
    versions."""
    if type(text) is not str or len(text) > MOST_BASE64:
        return None
    joined = text.replace("\n", "")
    told = joined.rstrip("=")
    if len(joined) % 4 or len(joined) - len(told) > 2 or ALPHABET.fullmatch(told) is None:
        return None
    return base64.b64decode(joined)


def _gits(name: str) -> bool:
    """Whether a name is git's own directory to git on some file system, as `guards/patch.py` reads it: `.git` under
    any case, with dots after it, or with a colon and anything after that; and its short name, `git~` and anything."""
    head = name.casefold().partition(":")[0].rstrip(".")
    return head == GIT_OWN or head.startswith(GIT_SHORT)


def _file(path) -> bool:
    """Whether `path` names a file in a tree: text of parts each named, none of them `.`, `..` or git's own directory
    (`_gits`), and no control character in it, C0, DEL or C1, nor a backslash, which another file system reads as /."""
    return type(path) is str and all(part not in ("", ".", "..") and not _gits(part) for part in path.split("/")) \
        and not any(c < " " or "\x7f" <= c <= "\x9f" or c == "\\" for c in path)


def _apart(paths: set) -> bool:
    """Whether no path among `paths` is a directory above another: `docs` and `docs/readme.md` both written put a
    file where a directory must be."""
    return not any("/".join(parts[:i]) in paths for parts in (path.split("/") for path in paths)
                   for i in range(1, len(parts)))


def _git(repo: str) -> str:
    return "/repos/%s/git/" % repo


def allowed(repo, branch) -> tuple:
    """`(permits, patterns)` for `Allowed`: what a push's token may send on `repo`'s git data, its one work branch
    `branch` among it; nothing at all for a repo or a branch told wrongly. Each body is held to `_plain` first."""
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
            and type(body["tree"]) is list and all(entry(item) for item in body["tree"]) \
            and _apart({item["path"] for item in body["tree"] if item["sha"] is not None})

    def commit(body) -> bool:
        return type(body) is dict and set(body) == {"message", "tree", "parents"} and type(body["message"]) is str \
            and _sha(body["tree"]) and type(body["parents"]) is list and len(body["parents"]) == 1 \
            and _sha(body["parents"][0])

    def made(body) -> bool:
        return type(body) is dict and set(body) == {"ref", "sha"} and body["ref"] == HEADS + branch and _sha(body["sha"])

    def moved(body) -> bool:
        return type(body) is dict and set(body) == {"sha", "force"} and _sha(body["sha"]) and body["force"] is False

    def plain(shape):
        return lambda body: _plain(body) and shape(body)

    permits = {("GET", git + "ref/heads/" + branch): nothing, ("POST", git + "blobs"): plain(blob),
               ("POST", git + "trees"): plain(tree), ("POST", git + "commits"): plain(commit),
               ("POST", git + "refs"): plain(made), ("PATCH", git + "refs/heads/" + branch): plain(moved)}
    patterns = [("GET", re.compile(re.escape(git + "commits/") + SHA.pattern), nothing),
                ("GET", re.compile(re.escape(git + "trees/") + SHA.pattern + re.escape("?recursive=1")), nothing),
                ("GET", re.compile(re.escape(git + "blobs/") + SHA.pattern), nothing)]
    return permits, patterns
