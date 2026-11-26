"""What a Role's push is told, and the paths `apply` is asked about (issue 838; FR-14). What the push may send, in
what order, and what must be read back before it counts as landed, is still to come.

A push lands what `guards/patch.py`'s `applied` gave, `changes`, as one commit on the commit the Decision admitted,
`parent`, on the Run's work branch. The guard on it holds the sequence, not each request alone: the caller carries a
state, which `began` gives first. Asking whether the next request may leave, and taking GitHub's answer to it, are
the next parts'. The state holds from this part on each field those parts read and set, so that what the caller
carries is of one shape throughout.

- `began(push)`: `(state, None)`, the first state, or `(None, NOT_PERMITTED)` for a push told wrongly. `push` is
  `{"repo", "branch", "parent", "head", "message", "changes", "blobs"}`: `head` is the branch's head the Decision
  admitted, None where it admitted none and `parent` otherwise; `message` is the commit's, `apply`'s and never a
  model's text; `blobs` is the base64 of each written file's bytes, by its path. A push of no `changes` and no
  `blobs` reads, and writes nothing: the port reads under one what `applied` needs.

What this rests on: the state is the caller's and never the port's, and the port is handed copies of what `push`
holds, never `push`. That `blobs` is the base64 of the bytes `changes` holds is `apply`'s to say, which may import
what encodes it.

`touched(changes)` gives `(paths, None)`, naming the paths `harness/apply.py` is asked about: a push that touches a
protected path is refused there. Which files of the admitted commit it changes or removes, FR-14's rule on a test, is
the next part's, which reads that commit's tree. One matcher reads the base's patterns (`tools/hooks/protected.py`); this names the paths, so
what is asked about is what lands.

Every stop gives a code, never None alone, and each code is set here, so that one table can name whose each is
(issue 838). This part's is `NOT_PERMITTED`. Each input is held to its exact type, as the patch guard holds its own:
a subclass says what `in`, `set` and `[]` on it do. The state holds a copy of what it was told.

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
# What a file is written as: two things.
WRITTEN = ("mode", "bytes")
PUSH = ("repo", "branch", "parent", "head", "message", "changes", "blobs")
CHANGES = ("written", "removed", "read")
# A push told wrongly, or changes in no shape `applied` gives: the Factory's own fault in describing the push, never
# the Role's, so a person's (issue 838). A tree in no shape is the port's read, `patch.TREE_UNREAD`, a person's too.
NOT_PERMITTED = "push_not_permitted"


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


def _keyed(said, keys: tuple) -> bool:
    """Whether `said` is a mapping of exactly `keys`, each key exact text: a key's type is held before any key is
    compared, since a comparison is the key's own to say."""
    return type(said) is dict and all(type(key) is str for key in said) and set(said) == set(keys)


def _changes(changes) -> bool:
    """Whether `changes` is in the shape `guards/patch.py`'s `applied` gives, path by path: exactly its three keys;
    files written, each with a file's mode and its bytes; files removed; files read; every path a name `patch.named`
    reads; no path written or removed twice, or both; no file written above another written, nor one removed or read
    above another removed or read; and one at least. A file written where one removed stood above it, or under it, is
    a file replaced by a directory, or a directory by a file, and `applied` gives both."""
    if not _keyed(changes, CHANGES):
        return False
    written, removed, read = changes["written"], changes["removed"], changes["read"]
    if type(written) is not dict or type(removed) is not list or type(read) is not list:
        return False
    paths = list(written) + list(removed)
    if not paths or not all(patch.named(path) for path in paths + list(read)):
        return False
    if len(set(paths)) != len(paths) or len(set(read)) != len(read):
        return False
    old = set(removed) | set(read)
    if any(above in side for side in (written, old) for path in side for above in _above(path)):
        return False
    return all(type(to) is tuple and len(to) == len(WRITTEN) and type(to[0]) is str and to[0] in patch.FILE_MODES
               and type(to[1]) is bytes for to in written.values())


def _told(push) -> bool:
    """Whether `push` says one push whole: a repo, a work branch, the commit it stands on, the head admitted, which is
    none or that commit, a message, and changes with the base64 of each written file, or neither."""
    if not _keyed(push, PUSH):
        return False
    if not (_repo(push["repo"]) and _work(push["branch"]) and _sha(push["parent"])
            and (push["head"] is None or (_sha(push["head"]) and push["head"] == push["parent"]))
            and type(push["message"]) is str and bool(push["message"])):
        return False
    changes, blobs = push["changes"], push["blobs"]
    if changes is None or blobs is None:
        return changes is None and blobs is None
    return (_changes(changes) and _keyed(blobs, tuple(changes["written"]))
            and all(type(text) is str for text in blobs.values()))


def began(push) -> tuple:
    """`(state, None)`, the state of a push of which nothing was sent yet, or `(None, NOT_PERMITTED)` for a push told
    in part or wrongly."""
    if not _told(push):
        return None, NOT_PERMITTED
    # A copy, so that what the caller changes after this was checked is never what the state holds.
    changes, blobs = push["changes"], push["blobs"]
    if changes is not None:
        changes = {"written": dict(changes["written"]), "removed": list(changes["removed"]),
                   "read": list(changes["read"])}
        blobs = dict(blobs)
    return {"push": dict(push, changes=changes, blobs=blobs), "tree": None, "before": None, "branch_read": False,
            "made": {}, "new": None, "checked": False, "commit": None, "commit_back": False, "moved": False,
            "landed": False}, None


def touched(changes) -> tuple:
    """`((paths, read), None)` for `harness/apply.py`'s `push_refusal`: every path the push writes or removes, and
    every path a rename or a copy in it read. `(None, NOT_PERMITTED)` for changes in no shape `applied` gives."""
    if not _changes(changes):
        return None, NOT_PERMITTED
    return (sorted(set(changes["written"]) | set(changes["removed"])), list(changes["read"])), None

