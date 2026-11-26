"""What a Role's push is told, what it reads, what it writes up to its tree, and the paths `apply` is asked about
(issue 838; FR-14). The commit, the branch's write and what must be read back before the push counts as landed are
still to come.

A push lands what `guards/patch.py`'s `applied` gave, `changes`, as one commit on the commit the Decision admitted,
`parent`, on the Run's work branch. The guard on it holds the sequence, not each request alone: the caller carries a
state, which `began` gives first, asks `permits` before a request leaves, gives `seen` the port's answer after, and
stops at the first False or code. The state holds from the first part on each field the later parts set, so that
what the caller carries is of one shape throughout, and from this part on the blobs read.

- `began(push)`: `(state, None)`, the first state, or `(None, NOT_PERMITTED)` for a push told wrongly. `push` is
  `{"repo", "branch", "parent", "head", "message", "changes", "blobs"}`: `head` is the branch's head the Decision
  admitted, None where it admitted none and `parent` otherwise; `message` is the commit's, `apply`'s and never a
  model's text; `blobs` is the base64 of each written file's bytes, by its path. A push of no `changes` and no
  `blobs` reads, and writes nothing: the port reads under one what `applied` needs.
- `permits(state, method, path, body)`: whether the next request may leave. The reads, each once and in order: the
  work branch, absent where `head` is None and at `head` where it is not; the admitted commit; the tree it names, every
  level; and the blob of each file that tree holds, once whichever files share it. Then, for a push of changes and
  only once the branch and the listing were read, the writes: a blob of each written content, once, and one tree upon
  the admitted tree of exactly the changes, each written file by the blob made of its bytes. Nothing is read once a
  write began.
- `seen(state, method, path, body, answer)`: `(state, None)` after the port's answer, or `(None, code)`. The tree's
  answer is the port's listing, `adapters/push.py`'s `listed`, which checked it whole: this holds only that the port
  marked it `whole`, at the tree the admitted commit names (decision 1225). A write's answer is GitHub's 201 and
  the name of what it made, and a tree that is the admitted one made nothing of the changes.

What this rests on: the state is the caller's and never the port's, and the port is handed copies of what `push`
holds, never `push`. That `blobs` is the base64 of the bytes `changes` holds is `apply`'s to say, which may import
what encodes it.

`touched(changes)` and `existing(changes, tree)` give `(paths, None)`, naming the paths `harness/apply.py` is asked
about: a push that touches a protected path is refused there, and so is one that changes or removes a test the
admitted commit holds. One matcher reads the base's patterns (`tools/hooks/protected.py`); this names the paths, so
what is asked about is what lands.

Every stop gives a code, never None alone, and each code is set here, so that one table can name whose each is
(issue 838): `NOT_PERMITTED`, `BRANCH_MOVED`, `ANSWER_REFUSED` and `UNANSWERED`. Each input is held to its exact type, as the patch guard holds its own:
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
# The branch read where the Decision admitted it not: someone else wrote it, and the Run was overtaken, `superseded`.
BRANCH_MOVED = "push_branch_moved"
# GitHub answered, and not as a push may go on from: a refusal, or a read of another thing. A person's.
ANSWER_REFUSED = "push_answer_refused"
# No answer, or one read as none: the port's, an environment fault.
UNANSWERED = "push_unanswered"
# GitHub's answers, as text, as the port gives them: a number here would be a limit, and these are a protocol's names.
OK = "200"
CREATED = "201"
ABSENT = "404"
# Besides GitHub's own failure, 500 and above, what a read takes as no answer, as the port reads its listing: a rate
# limit, or a token expired or refused. The branch is read first; a 403 after it, by the same token, is GitHub refusing
# that read, which comes again on every pass: a refusal, as the port reads a blob's (decision 1222).
NO_ANSWER = ("401", "403", "429")
NO_ANSWER_AFTER = ("401", "429")
HEADS = "refs/heads/"
COMMIT = "commit"
RECURSIVE = "?recursive=1"
# What a state holds; and what the port's listing holds, which `listed` marks `whole` and names by the tree it read.
STATE = ("push", "tree", "before", "branch_read", "blobs_read", "made", "new", "checked", "commit", "commit_back",
         "moved", "landed")
LISTING = ("tree", "blobs", "sha", "whole")
# What a push writes past its tree is the next parts': until then, a state holds no commit and no flag set.
NONE_YET = ("commit",)
NOT_YET = ("checked", "commit_back", "moved", "landed")
# What the listing holds of a file's or a link's blob.
HELD = ("sha", "size")
# The reads of a push, each named for what `seen` asks of its answer.
BRANCH_READ, COMMIT_READ, TREE_READ, BLOB_READ = "branch_read", "commit_read", "tree_read", "blob_read"
# The writes, as the port's `make_blob` and `make_tree` build them.
BLOB_MADE, TREE_MADE = "blob_made", "tree_made"
BLOB_BODY = ("content", "encoding")
BASE64 = "base64"
TREE_BODY = ("base_tree", "tree")
ENTRY = ("path", "mode", "type", "sha")
BLOB = "blob"


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
    return _mapping(said) and set(said) == set(keys)


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
            "blobs_read": (), "made": {}, "new": None, "checked": False, "commit": None, "commit_back": False, "moved": False,
            "landed": False}, None


def _listing(said, tree) -> bool:
    """Whether `said` is the port's listing of the tree `tree`, as `adapters/push.py`'s `listed` gives it: marked
    `whole`, at that tree's name, a mapping of each path to its mode and of each file's and link's to its blob's
    `(sha, size)`. What the listing says of the tree the port checked; this holds only that it is the port's, whole,
    and of the tree the admitted commit names."""
    if not _keyed(said, LISTING) or said["whole"] is not True or not _said(said["sha"], tree):
        return False
    paths, blobs = said["tree"], said["blobs"]
    if not (_mapping(paths) and all(type(mode) is str and mode in patch.TREE_MODES for mode in paths.values())):
        return False
    return _mapping(blobs) and all(type(held) is tuple and len(held) == len(HELD) and _sha(held[0])
                                   and type(held[1]) is int and held[1] >= 0 for held in blobs.values())


def _files(before) -> set:
    """The blobs of the files a listing holds: what a push may read of it."""
    return {held[0] for name, held in before["blobs"].items() if before["tree"].get(name) in patch.FILE_MODES}


def _mapping(said) -> bool:
    """Whether `said` is an exact mapping whose keys are exact text, held before any key is looked up."""
    return type(said) is dict and all(type(key) is str for key in said)


def _status(said) -> bool:
    """Whether `said` is a status as `send` gives it: three digits, from 100 to 599, as text."""
    return type(said) is str and len(said) == len(OK) and all(c in DIGITS for c in said) and "1" <= said[0] <= "5"


def _said(said, text) -> bool:
    return type(said) is str and said == text


def _state(state) -> bool:
    """Whether `state` is in the shape `began` and `seen` give: its keys, a push told whole, the admitted tree's name or
    none yet, read only once the branch was, its listing or none, read only once that name was, the blobs of its files
    read, each once, and what was written: a blob's name for written files, once the listing was read, and the tree
    made, once each written file has its blob, never the admitted tree."""
    if not _keyed(state, STATE) or not _told(state["push"]):
        return False
    tree, before = state["tree"], state["before"]
    if not (tree is None or _sha(tree)) or not (before is None or (tree is not None and _listing(before, tree))):
        return False
    if tree is not None and state["branch_read"] is not True:
        return False
    read = state["blobs_read"]
    if type(read) is not tuple or not all(type(sha) is str for sha in read) or len(set(read)) != len(read):
        return False
    if read and (before is None or not set(read) <= _files(before)):
        return False
    made, new, changes, push_blobs = state["made"], state["new"], state["push"]["changes"], state["push"]["blobs"]
    if not (_mapping(made) and all(_sha(name) for name in made.values())):
        return False
    if made and (before is None or changes is None or not set(made) <= set(changes["written"])):
        return False
    # Files of one content share one blob.
    if made and any(push_blobs[path] == push_blobs[one] and made.get(path) != made[one] for one in made
                    for path in changes["written"]):
        return False
    if new is not None and not (_sha(new) and new != tree and before is not None and changes is not None
                                and set(made) == set(changes["written"])):
        return False
    return (type(state["branch_read"]) is bool and all(state[key] is None for key in NONE_YET)
            and all(state[key] is False for key in NOT_YET))


def _step(state, method, path, body):
    """Which request of the push this is, as the state stands, or None where it may not leave: each read once and in
    its order, the branch, the admitted commit, then the tree that commit names, then a file's blob that tree's
    listing names; then the writes, `_written`'s; and nothing outside this repo's git data."""
    if not _state(state) or type(method) is not str or type(path) is not str:
        return None
    push = state["push"]
    root = "/repos/" + push["repo"] + "/git/"
    if not path.startswith(root):
        return None
    rest, tree, before = path[len(root):], state["tree"], state["before"]
    if method != "GET":
        return _written(state, method, rest, body)
    if body is not None:
        return None
    if rest == "ref/heads/" + push["branch"] and not state["branch_read"]:
        return BRANCH_READ
    if rest == "commits/" + push["parent"] and tree is None and state["branch_read"]:
        return COMMIT_READ
    if tree is not None and rest == "trees/" + tree + RECURSIVE and before is None:
        return TREE_READ
    sha = rest[len("blobs/"):]
    if (before is not None and rest == "blobs/" + sha and sha in _files(before) and sha not in state["blobs_read"]
            and not state["made"] and state["new"] is None):
        return BLOB_READ
    return None


def _written(state, method, rest, body):
    """Which write this is, or None: nothing by a push of no changes, or before the branch and the admitted tree's
    listing were read; a blob of a written file's base64 that has none yet; then, once each has its blob, one tree."""
    push, made = state["push"], state["made"]
    changes = push["changes"]
    if changes is None or state["before"] is None or state["branch_read"] is not True or method != "POST":
        return None
    if rest == "blobs" and _keyed(body, BLOB_BODY) and _said(body["encoding"], BASE64) and type(body["content"]) is str:
        if any(push["blobs"][path] == body["content"] and path not in made for path in changes["written"]):
            return BLOB_MADE
    # The tree lands only changes the admitted tree can hold, as `existing` reads them.
    if (rest == "trees" and state["new"] is None and set(made) == set(changes["written"]) and _tree(body, state)
            and existing(changes, state["before"]["tree"])[1] is None):
        return TREE_MADE
    return None


def _tree(body, state) -> bool:
    """Whether `body` is the one tree upon the admitted tree of exactly the changes: each path once, a written file by
    the blob made of its bytes in the mode the changes give it, a removed file as no blob in the mode the listing
    holds."""
    if not _keyed(body, TREE_BODY) or not _said(body["base_tree"], state["tree"]) or type(body["tree"]) is not list:
        return False
    written, removed = state["push"]["changes"]["written"], state["push"]["changes"]["removed"]
    listing, entries = state["before"]["tree"], body["tree"]
    if len(entries) != len(written) + len(removed) or not all(
            _keyed(entry, ENTRY) and _said(entry["type"], BLOB) and type(entry["path"]) is str for entry in entries):
        return False
    if len({entry["path"] for entry in entries}) != len(entries):
        return False
    for entry in entries:
        path, mode, sha = entry["path"], entry["mode"], entry["sha"]
        if path in written:
            if not (_said(sha, state["made"][path]) and _said(mode, written[path][0])):
                return False
        elif not (path in removed and sha is None and path in listing and _said(mode, listing[path])):
            return False
    return True


def permits(state, method, path, body) -> bool:
    """Whether the next request of the push may leave, as the state stands."""
    return _step(state, method, path, body) is not None


def _unanswered(answer, statuses) -> bool:
    return answer is None or answer["status"] in statuses or answer["status"].startswith("5")


def seen(state, method, path, body, answer) -> tuple:
    """`(state, None)`, the state after GitHub's answer to a read, or `(None, code)`. `answer` is the port's: `send`'s,
    `{"status", "body"}` or None, and for the tree, `listed`'s listing. A request that may not leave as the state
    stands, an answer in no shape `send` gives, or a listing the port did not mark whole or read at another tree, is
    `NOT_PERMITTED`; no answer, `UNANSWERED`; the branch not as the Decision admitted it, `BRANCH_MOVED`; any other
    answer the push cannot go on from, `ANSWER_REFUSED`. A blob's bytes are the port's `read_whole`'s to judge: a
    blob given is only counted, so that it is not read again."""
    step = _step(state, method, path, body)
    if step is None:
        return None, NOT_PERMITTED
    if step == TREE_READ:
        if answer is None:
            return None, UNANSWERED
        if not _listing(answer, state["tree"]):
            return None, NOT_PERMITTED
        before = {"tree": dict(answer["tree"]), "blobs": dict(answer["blobs"]), "sha": answer["sha"], "whole": True}
        return dict(state, before=before), None
    if answer is not None and not (_keyed(answer, ("status", "body")) and _status(answer["status"])):
        return None, NOT_PERMITTED
    # A write's 4xx is GitHub refusing it; only no answer, or GitHub's own failure, is none (decision 1225).
    if _unanswered(answer, NO_ANSWER if step == BRANCH_READ else () if step in (BLOB_MADE, TREE_MADE) else NO_ANSWER_AFTER):
        return None, UNANSWERED
    status, got, push = answer["status"], answer["body"], state["push"]
    if step in (BLOB_MADE, TREE_MADE):
        name = got["sha"] if status == CREATED and _mapping(got) and "sha" in got else None
        if not _sha(name) or (step == TREE_MADE and name == state["tree"]):
            return None, ANSWER_REFUSED
        if step == TREE_MADE:
            return dict(state, new=name), None
        made = dict(state["made"])
        made.update({path: name for path in push["changes"]["written"] if push["blobs"][path] == body["content"]})
        return dict(state, made=made), None
    if step == BLOB_READ:
        # A blob refused is a refusal; its bytes, when given, are the port's to judge.
        if status != OK:
            return None, ANSWER_REFUSED
        return dict(state, blobs_read=state["blobs_read"] + (path[len(path) - len(SHA):],)), None
    if step == BRANCH_READ:
        # Absent where the Decision admitted no head, and at that head where it admitted one; any other branch is
        # someone else's write.
        at = got["object"].get("sha") if _mapping(got) and _said(got.get("ref"), HEADS + push["branch"]) \
            and _mapping(got.get("object")) and _said(got["object"].get("type"), COMMIT) else None
        if (status, push["head"]) == (ABSENT, None) or (status == OK and _sha(at) and at == push["head"]):
            return dict(state, branch_read=True), None
        return None, BRANCH_MOVED if status == ABSENT or (status == OK and _sha(at)) else ANSWER_REFUSED
    tree = got.get("tree") if status == OK and _mapping(got) and _said(got.get("sha"), push["parent"]) else None
    name = tree.get("sha") if _mapping(tree) else None
    if not _sha(name):
        return None, ANSWER_REFUSED
    return dict(state, tree=name), None


def touched(changes) -> tuple:
    """`((paths, read), None)` for `harness/apply.py`'s `push_refusal`: every path the push writes or removes, and
    every path a rename or a copy in it read. `(None, NOT_PERMITTED)` for changes in no shape `applied` gives."""
    if not _changes(changes):
        return None, NOT_PERMITTED
    return (sorted(set(changes["written"]) | set(changes["removed"])), list(changes["read"])), None


def existing(changes, tree) -> tuple:
    """`(files, None)`: the files of the admitted commit, `tree`, that the push changes or removes, each once, in
    order: what FR-14's rule on a test is asked about. A file the push adds is none of them. `(None, NOT_PERMITTED)`
    for changes in no shape `applied` gives, or that the tree cannot hold, and `(None, patch.TREE_UNREAD)` for a tree
    that is no exact mapping of text to a mode git holds, each held to its type before any is compared, or that no
    tree is: a file under a file, or deeper than any name `patch.named` reads."""
    if not _changes(changes):
        return None, NOT_PERMITTED
    if type(tree) is not dict or not all(type(path) is str and type(mode) is str and mode in patch.TREE_MODES
                                         for path, mode in tree.items()):
        return None, patch.TREE_UNREAD
    # A bound on depth, asked before a path is split, bounds what `_above` builds; no tree holds a file under a file.
    if (not all(path.count("/") < len(patch.DEEPEST) for path in tree)
            or any(above in tree for path in tree for above in _above(path))):
        return None, patch.TREE_UNREAD
    written, removed = changes["written"], set(changes["removed"])
    # Changes the tree cannot hold were never `applied`'s: a file removed or read that the tree holds as no file, a
    # file written over a link or a submodule, over a directory the tree keeps, or under a file it keeps.
    if (any(tree.get(path) not in patch.FILE_MODES for path in list(removed) + changes["read"])
            or any(path in tree and tree[path] not in patch.FILE_MODES for path in written)
            or any(above in written for path in tree if path not in removed for above in _above(path))
            or any(above in tree and above not in removed for path in written for above in _above(path))):
        return None, NOT_PERMITTED
    # Every file removed is one of the tree's, as checked above.
    return sorted([path for path in written if path in tree] + changes["removed"]), None
