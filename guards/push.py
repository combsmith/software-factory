"""What a Role's push may read before it writes, and the answers it takes (issue 838; FR-14). What the push may
write, in what order, and what must be read back before it counts as landed, is still to come.

A push lands what `guards/patch.py`'s `applied` gave, `changes`, as one commit on the commit the Decision admitted,
`parent`, on the Run's work branch. This holds the sequence, not each request alone: the caller carries a state, asks
`permits` before a request leaves and gives `seen` GitHub's answer after, and stops at the first False or None.

- `began(push)`: the first state, or None for a push told wrongly. `push` is `{"repo", "branch", "parent", "head",
  "message", "changes", "blobs"}`: `head` is the branch's head the Decision admitted, None where it admitted none and
  `parent` otherwise; `message` is the commit's, `apply`'s and never a model's text; `blobs` is the base64 of each
  written file's bytes, by its path. A push of no `changes` and no `blobs` reads, and writes nothing: the port reads
  under one what `applied` needs.
- `permits(state, method, path, body)`: whether the next request may leave.
- `seen(state, method, path, body, answer)`: the state after GitHub's answer, `{"status", "body"}` with the status
  as text, or None where the request may not leave or the answer is none this takes of it.

The reads the state allows: of the admitted commit, of its tree, whole and never truncated, of the blobs that tree
names, and of the branch, which is absent where `head` is None and at `head` where it is not. No write leaves yet:
what a push writes, in what order, is the next part's.

What this rests on, and its stated limits:
- The state is the caller's and never the port's: it is `began`'s answer or `seen`'s and nothing else, and the port
  is handed copies of what `push` holds, never `push`. A state of another shape lets nothing leave; one forged in
  the right shape is not told from a true one.
- An answer is what the transport read from GitHub.
- A request is allowed again for as long as its answer has not reached `seen`: the caller stops at an answer lost.
- That `blobs` is the base64 of the bytes `changes` holds is `apply`'s to say, which may import what encodes it.
- A directory is read by the files under it: an empty one in a listing is passed over. And a repo whose listing
  GitHub truncates takes no push.

`touched(changes)` and `existing(changes, tree)` name the paths `harness/apply.py` is asked about: a push that touches
a protected path is refused there, and so is one that changes or removes a test the admitted commit holds. One matcher
reads the base's patterns (`tools/hooks/protected.py`); this names the paths, so what is asked about is what lands.

`apply` and a port give every argument; this reads nothing itself.
"""
from __future__ import annotations

from guards import patch

HEX = "0123456789abcdef"
DIGITS = "0123456789"
# A commit's, a tree's and a blob's name are each as long as this, of `HEX`.
SHA = "0000000000000000000000000000000000000000"
# The characters an owner's and a repo's name hold, as GitHub names them.
REPO_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
# The branch a Run's push lands on, `factory-work/issue-<N>-<k>` (decision 0068): never the default branch or a
# Release's tag, whatever this is told. Whose Run's branch it is, the Decision says; this cannot.
WORK = "factory-work/issue-"
HEADS = "refs/heads/"
RECURSIVE = "?recursive=1"
BLOB = "blob"
TREE = "tree"
COMMIT = "commit"
BASE64 = "base64"
# A directory's mode in a tree's listing, and a submodule's, whose entry names a commit and no blob.
FOLDER = "040000"
SUBMODULE = "160000"
# GitHub's answers, as text, as the caller gives them: a number here would be a limit, and these are a protocol's
# names.
OK = "200"
ABSENT = "404"
# What a file is written as: two things.
WRITTEN = ("mode", "bytes")
PUSH = ("repo", "branch", "parent", "head", "message", "changes", "blobs")
CHANGES = ("written", "removed", "read")
# What a state holds: the push; the admitted commit's tree and its listing, once read; whether the branch was read as
# the Decision admitted it; the blob made for each written path; the tree made, and whether it was read back as the
# admitted one with the changes in it; the commit made, and whether it was read back as made; whether the branch was
# written; and whether the push landed, the branch read again at the commit made.
STATE = ("push", "tree", "before", "branch_read", "made", "new", "checked", "commit", "commit_back", "moved", "landed")
NAMES = ("tree", "new", "commit")
FLAGS = ("branch_read", "checked", "commit_back", "moved", "landed")
# What a listing holds of a path: its mode and its name.
HELD = ("mode", "sha")
# The reads of a push, each named for what `seen` then asks of its answer.
REF_READ, COMMIT_READ, TREE_READ, BLOB_READ = "ref_read", "commit_read", "tree_read", "blob_read"


def _sha(said) -> bool:
    return type(said) is str and len(said) == len(SHA) and all(c in HEX for c in said)


def _count(said: str) -> bool:
    """A whole number from 1 as a branch's name holds one: digits, the first not 0."""
    return bool(said) and all(c in DIGITS for c in said) and not said.startswith("0")


def _work(branch) -> bool:
    if type(branch) is not str or not branch.startswith(WORK):
        return False
    issue, _, opened = branch[len(WORK):].partition("-")
    return _count(issue) and _count(opened)


def _repo(said) -> bool:
    if type(said) is not str or not all(c in REPO_CHARS or c == "/" for c in said):
        return False
    owner, slash, name = said.partition("/")
    return bool(slash) and "/" not in name and all(part and part not in (".", "..") for part in (owner, name))


def _above(path: str) -> list:
    """Each directory `path` stands under."""
    names = path.split("/")
    return ["/".join(names[:n]) for n in range(1, len(names))]


def _changes(changes) -> bool:
    """Whether `changes` is in the shape `guards/patch.py`'s `applied` gives, path by path: exactly its three keys;
    files written, each with a file's mode and its bytes; files removed; files read; every path a name `patch.named`
    reads; no path written or removed twice, or both, and none of them above another; and one at least."""
    if not isinstance(changes, dict) or set(changes) != set(CHANGES):
        return False
    written, removed, read = changes["written"], changes["removed"], changes["read"]
    if not isinstance(written, dict) or not isinstance(removed, list) or not isinstance(read, list):
        return False
    paths = list(written) + list(removed)
    if not paths or not all(patch.named(path) for path in paths + list(read)):
        return False
    if len(set(paths)) != len(paths) or len(set(read)) != len(read):
        return False
    if any(above in written or above in removed for path in paths for above in _above(path)):
        return False
    return all(isinstance(to, tuple) and len(to) == len(WRITTEN) and to[0] in patch.FILE_MODES
               and isinstance(to[1], bytes) for to in written.values())


def _told(push) -> bool:
    """Whether `push` says one push whole: a repo, a work branch, the commit it stands on, the head admitted, which is
    none or that commit, a message, and changes with the base64 of each written file, or neither."""
    if not isinstance(push, dict) or set(push) != set(PUSH):
        return False
    if not (_repo(push["repo"]) and _work(push["branch"]) and _sha(push["parent"])
            and (push["head"] is None or (_sha(push["head"]) and push["head"] == push["parent"]))
            and type(push["message"]) is str and bool(push["message"])):
        return False
    changes, blobs = push["changes"], push["blobs"]
    if changes is None or blobs is None:
        return changes is None and blobs is None
    return (_changes(changes) and isinstance(blobs, dict) and set(blobs) == set(changes["written"])
            and all(type(text) is str for text in blobs.values()))


def began(push):
    """The state of a push of which nothing was sent yet, or None for a push told in part or wrongly."""
    if not _told(push):
        return None
    return {"push": push, "tree": None, "before": None, "branch_read": False, "made": {}, "new": None,
            "checked": False, "commit": None, "commit_back": False, "moved": False, "landed": False}


def _state(state) -> bool:
    """Whether `state` is in the shape `began` and `seen` give: its keys, a push told whole, each name a name or none
    yet, each flag True or False, a listing that holds a pair with a name to each path, a blob's name for written
    paths alone, and no tree made by a push of no changes or before the admitted one was listed."""
    if type(state) is not dict or set(state) != set(STATE) or not _told(state["push"]):
        return False
    if not all(state[key] is None or _sha(state[key]) for key in NAMES):
        return False
    if not all(state[key] is True or state[key] is False for key in FLAGS):
        return False
    before, made, changes = state["before"], state["made"], state["push"]["changes"]
    if before is not None and not (isinstance(before, dict) and all(
            isinstance(held, tuple) and len(held) == len(HELD) and _sha(held[1]) for held in before.values())):
        return False
    if state["new"] is not None and (before is None or changes is None):
        return False
    written = changes["written"] if changes is not None else {}
    return isinstance(made, dict) and all(isinstance(path, str) and path in written and _sha(made[path])
                                          for path in made)


def _step(state, method, path, body):
    """Which request of the push this is, as the state stands, or None where it may not leave. A state that is none
    of `began`'s, or of a push told wrongly, lets nothing leave; nor does a path outside this repo's git data,
    whatever the method, or a method or a path that is text of another kind."""
    if not _state(state) or type(method) is not str or type(path) is not str:
        return None
    push = state["push"]
    root = "/repos/" + push["repo"] + "/git/"
    if not path.startswith(root):
        return None
    rest, branch = path[len(root):], push["branch"]
    if method == "GET":
        if body is not None:
            return None
        if rest == "ref/heads/" + branch:
            return REF_READ
        if rest == "commits/" + push["parent"]:
            return COMMIT_READ
        if state["tree"] is not None and rest == "trees/" + state["tree"] + RECURSIVE:
            return TREE_READ
        if state["before"] is not None and any(rest == "blobs/" + held[1] for held in state["before"].values()
                                               if held[0] != SUBMODULE):
            return BLOB_READ
        return None
    # What a push writes, and when, is the next part's: no write leaves yet.
    return None


def permits(state, method, path, body) -> bool:
    """Whether the next request of the push may leave, as the state stands."""
    return _step(state, method, path, body) is not None


def _listing(body, name):
    """`{path: (mode, sha)}` for everything that is no directory in a tree's listing, read whole, or None: a listing
    of another tree, a truncated one, a path twice, or an entry that is none git writes."""
    if not isinstance(body, dict) or body.get("sha") != name or body.get("truncated") is not False:
        return None
    entries = body.get("tree")
    if not isinstance(entries, list):
        return None
    out, folders = {}, {}
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        path, mode, kind = entry.get("path"), entry.get("mode"), entry.get("type")
        if not isinstance(path, str) or path in out or path in folders or not _sha(entry.get("sha")):
            return None
        if mode == FOLDER and kind == TREE:
            folders[path] = True
        elif mode in patch.TREE_MODES and kind == (COMMIT if mode == SUBMODULE else BLOB):
            out[path] = (mode, entry.get("sha"))
        else:
            return None
    # No path git cannot hold: a part that is empty or a dot's, or a file above another path.
    if any(part in ("", ".", "..") for path in list(out) + list(folders) for part in path.split("/")):
        return None
    if any(above in out for path in list(out) + list(folders) for above in _above(path)):
        return None
    return out


def _ref(got, branch):
    """The commit a branch's read or write answers with, or None where the answer names another ref or no commit."""
    if not isinstance(got, dict) or got.get("ref") != HEADS + branch or not isinstance(got.get("object"), dict):
        return None
    return got["object"].get("sha")


def seen(state, method, path, body, answer):
    """The state after GitHub's answer to a request, or None: the request may not leave as the state stands, or the
    answer is none this takes of it. An answer is `{"status": the status GitHub gave, as text, "body": what it
    said}`."""
    step = _step(state, method, path, body)
    if step is None or type(answer) is not dict or set(answer) != {"status", "body"}:
        return None
    status, got, push = answer["status"], answer["body"], state["push"]
    if step == REF_READ:
        # The branch is as the Decision admitted it: absent, or at the admitted head.
        if push["head"] is None:
            return dict(state, branch_read=True) if status == ABSENT else None
        if status != OK or _ref(got, push["branch"]) != push["head"]:
            return None
        return dict(state, branch_read=True)
    if status != OK:
        return None
    if step == COMMIT_READ:
        tree = got.get("tree") if isinstance(got, dict) and got.get("sha") == push["parent"] else None
        name = tree.get("sha") if isinstance(tree, dict) else None
        if not _sha(name) or state["tree"] not in (None, name):
            return None
        return dict(state, tree=name)
    if step == TREE_READ:
        listing = _listing(got, state["tree"])
        if listing is None or state["before"] not in (None, listing):
            return None
        return dict(state, before=listing)
    # The blob asked for, in base64: what the port reads under a push of no changes is what `applied` patches.
    if (not isinstance(got, dict) or got.get("sha") != path.split("/")[-1] or got.get("encoding") != BASE64
            or type(got.get("content")) is not str):
        return None
    return state


def touched(changes):
    """`(paths, read)` for `harness/apply.py`'s `push_refusal`: every path the push writes or removes, and every path a
    rename or a copy in it read. None for changes in no shape `applied` gives."""
    if not _changes(changes):
        return None
    return sorted(set(changes["written"]) | set(changes["removed"])), list(changes["read"])


def existing(changes, tree):
    """The files of the admitted commit, `tree`, that the push changes or removes, each once, in order: what FR-14's
    rule on a test is asked about. A file the push adds is none of them. None for changes in no shape `applied`
    gives."""
    if not _changes(changes) or not isinstance(tree, dict):
        return None
    return sorted(path for path in list(changes["written"]) + changes["removed"] if path in tree)
