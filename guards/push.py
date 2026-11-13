"""What a Role's push may send and what must be read back before it counts as landed (issue 838; FR-14).

A push lands what `guards/patch.py`'s `applied` gave, `changes`, as one commit on the commit the Decision admitted,
`parent`, on the Run's work branch. `push` says so: `{"repo", "branch", "parent", "tree", "head", "message",
"changes"}`, where `tree` is `parent`'s tree, `head` the branch's head the Decision admitted, or None where it admitted
none, and `message` the commit's message, which is `apply`'s and never a model's text.

- `permits(method, path, body, push)`: whether the push's credential may send one request. It reads the admitted
  commit, creates blobs, one tree upon `tree` that names exactly the paths of `changes`, one commit whose one parent
  is `parent`, and then creates the branch, or moves it forward and never by force. Nothing else leaves: no other
  branch, no delete, and no path outside the repo's git data.
- `landed(before, after, changes, contents)`: whether the tree read back is the admitted commit's with exactly
  `changes` in it: no path more or fewer, each file it left alone the same blob in the same mode, each file it wrote
  in the mode and of the bytes `changes` holds.
- `touched(changes)` and `existing(changes, tree)`: the paths `harness/apply.py` is asked about. A push that touches a
  protected path is refused there, and so is one that changes or removes a test the admitted commit holds: one matcher
  reads the base's patterns (`tools/hooks/protected.py`), and this names the paths, so that what is asked about is what
  lands.

A port gives every argument from its own reads and from what `apply` decided; this reads nothing itself.
"""
from __future__ import annotations

from guards import patch

HEX = "0123456789abcdef"
DIGITS = "0123456789"
# A commit's, a tree's and a blob's name are each as long as this, of `HEX`.
SHA = "0000000000000000000000000000000000000000"
# The bytes an owner's and a repo's name hold, as GitHub names them.
REPO_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
# The branch a Run's push lands on, `factory-work/issue-<N>-<k>` (decision 0068): never the default branch, a Release's
# tag or another Run's branch, whatever this is told.
WORK = "factory-work/issue-"
HEADS = "refs/heads/"
RECURSIVE = "?recursive=1"
BLOB = "blob"
BASE64 = "base64"
# What a file is written as, and what a tree holds it as: two things each.
WRITTEN = ("mode", "bytes")
ENTRY = ("mode", "sha")


def _sha(said) -> bool:
    return isinstance(said, str) and len(said) == len(SHA) and all(c in HEX for c in said)


def _count(said: str) -> bool:
    """A whole number from 1 as a branch's name holds one: digits, the first not 0."""
    return bool(said) and all(c in DIGITS for c in said) and not said.startswith("0")


def _work(branch) -> bool:
    if not isinstance(branch, str) or not branch.startswith(WORK):
        return False
    issue, dash, opened = branch[len(WORK):].partition("-")
    return bool(dash) and _count(issue) and _count(opened)


def _repo(said) -> bool:
    if not isinstance(said, str) or not all(c in REPO_CHARS or c == "/" for c in said):
        return False
    owner, slash, name = said.partition("/")
    return bool(slash) and "/" not in name and all(part and part not in (".", "..") for part in (owner, name))


def _changes(changes) -> bool:
    """Whether `changes` is in the shape `guards/patch.py`'s `applied` gives: files written, each with a file's mode and
    its bytes, and files removed, none of them both."""
    if not isinstance(changes, dict):
        return False
    written, removed = changes.get("written"), changes.get("removed")
    if not isinstance(written, dict) or not isinstance(removed, list):
        return False
    if not all(isinstance(path, str) for path in list(written) + removed) or any(path in written for path in removed):
        return False
    if len(set(removed)) != len(removed) or not (written or removed):
        return False
    return all(isinstance(to, tuple) and len(to) == len(WRITTEN) and to[0] in patch.FILE_MODES
               and isinstance(to[1], bytes) for to in written.values())


def _told(push) -> bool:
    """Whether `push` says one push whole: a repo, a work branch, the commit and tree it stands on, the head admitted or
    none, a message, and changes."""
    if not isinstance(push, dict) or set(push) != {"repo", "branch", "parent", "tree", "head", "message", "changes"}:
        return False
    return (_repo(push["repo"]) and _work(push["branch"]) and _sha(push["parent"]) and _sha(push["tree"])
            and (push["head"] is None or _sha(push["head"])) and isinstance(push["message"], str)
            and bool(push["message"]) and _changes(push["changes"]))


def _blob(body) -> bool:
    return (isinstance(body, dict) and set(body) == {"content", "encoding"} and body["encoding"] == BASE64
            and isinstance(body["content"], str))


def _tree(body, push: dict) -> bool:
    """One tree upon the admitted commit's, naming each path of `changes` once and no other: a file written as a blob
    in the mode `changes` holds, a file removed as no blob."""
    if not isinstance(body, dict) or set(body) != {"base_tree", "tree"} or body["base_tree"] != push["tree"]:
        return False
    written, removed = push["changes"]["written"], push["changes"]["removed"]
    entries = body["tree"]
    if not isinstance(entries, list) or len(entries) != len(written) + len(removed):
        return False
    seen = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "mode", "type", "sha"} or entry["type"] != BLOB:
            return False
        path = entry["path"]
        if not isinstance(path, str) or path in seen:
            return False
        seen.append(path)
        if path in removed:
            if entry["sha"] is not None or entry["mode"] not in patch.FILE_MODES:
                return False
        elif path not in written or not _sha(entry["sha"]) or entry["mode"] != written[path][0]:
            return False
    return True


def _commit(body, push: dict) -> bool:
    return (isinstance(body, dict) and set(body) == {"message", "tree", "parents"} and body["message"] == push["message"]
            and _sha(body["tree"]) and body["parents"] == [push["parent"]])


def permits(method, path, body, push) -> bool:
    """Whether the push's credential may send this request. A push told in part, or wrongly, is permitted nothing."""
    if not _told(push) or not isinstance(method, str) or not isinstance(path, str):
        return False
    root = "/repos/" + push["repo"] + "/git/"
    if not path.startswith(root):
        return False
    rest, branch = path[len(root):], push["branch"]
    if method == "GET":
        named = [rest[len(kind):] for kind in ("commits/", "blobs/") if rest.startswith(kind)]
        if rest.startswith("trees/") and rest.endswith(RECURSIVE):
            named.append(rest[len("trees/"):len(rest) - len(RECURSIVE)])
        return body is None and (rest == "ref/heads/" + branch or any(_sha(name) for name in named))
    if method == "POST" and rest == "blobs":
        return _blob(body)
    if method == "POST" and rest == "trees":
        return _tree(body, push)
    if method == "POST" and rest == "commits":
        return _commit(body, push)
    if method == "POST" and rest == "refs":
        # The branch is made only where the Decision admitted none; GitHub refuses to make one that stands.
        return (push["head"] is None and isinstance(body, dict) and set(body) == {"ref", "sha"}
                and body["ref"] == HEADS + branch and _sha(body["sha"]))
    if method == "PATCH" and rest == "refs/heads/" + branch:
        # It is moved only where the Decision admitted its head, and never by force: GitHub then refuses any move that
        # would discard a commit, so a branch that moved since lands nothing (FR-14).
        return (push["head"] is not None and isinstance(body, dict) and set(body) == {"sha", "force"}
                and body["force"] is False and _sha(body["sha"]))
    return False


def _entry(said) -> bool:
    return isinstance(said, tuple) and len(said) == len(ENTRY) and _sha(said[1])


def landed(before, after, changes, contents) -> bool:
    """Whether `after` is `before` with exactly `changes` in it. `before` and `after` are every path that is no
    directory in the admitted commit's tree and in the tree read back, each as `(mode, sha)`; `contents` is the bytes
    of each path `changes` wrote, read back by the blob `after` names."""
    if not _changes(changes) or not all(isinstance(held, dict) for held in (before, after, contents)):
        return False
    written, removed = changes["written"], changes["removed"]
    if set(after) != (set(before) - set(removed)) | set(written) or not all(path in before for path in removed):
        return False
    for path in after:
        if not _entry(after[path]):
            return False
        if path in written:
            mode, data = written[path]
            if after[path][0] != mode or contents.get(path) != data:
                return False
        elif after[path] != before[path]:
            return False
    return True


def touched(changes):
    """`(paths, read)` for `harness/apply.py`'s `push_refusal`: every path the push writes or removes, and every path a
    rename or a copy in it read. None for changes in no shape `applied` gives."""
    if not _changes(changes) or not isinstance(changes.get("read"), list):
        return None
    return sorted(set(changes["written"]) | set(changes["removed"])), list(changes["read"])


def existing(changes, tree):
    """The files of the admitted commit that the push changes or removes, each once, in order: what FR-14's rule on a
    test is asked about. A file the push adds is none of them. None for changes in no shape `applied` gives."""
    if not _changes(changes) or not isinstance(tree, dict):
        return None
    return sorted(set(path for path in changes["written"] if path in tree) | set(changes["removed"]))
