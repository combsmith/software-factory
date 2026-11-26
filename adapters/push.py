"""The push port: each request of a Role's push by GitHub's git data API, and GitHub's answer, through the push's own
sender (issue 838; P-71). It decides nothing: which request may leave, and what an answer must say before the next, is
`guards/push.py`'s. The Harness asks its `permits` of a request this builds, sends it by `send`, gives `seen` the
answer, and stops at the first False or None.

A builder to a request, each giving `adapters/github.py`'s `request`, or None for a part told wrongly or of another
kind: a repo, a name, a blob's content, or a work branch, `factory-work/issue-<N>-<k>` (decision 0068). A body is the
guard's to judge and the token's to allow. `read_commit`, `read_tree` (every level), `read_blob`, `read_branch`;
`make_blob`, `make_tree` (of a shallow copy of its entries), `make_commit` (one parent), `make_branch`, and
`move_branch`, never by force.

`transport(live, repo, branch)` is the push's sender, `adapters/effects.py`'s `Allowed` with `allowed(repo, branch)`;
none on a `live` with no `send`. `send(sender, repo, branch, req)` sends by that sender alone, by `Allowed`'s own
`send`: a bare transport, an `Allowed` made otherwise, or a sender bound elsewhere sends nothing. Its binding, permits
and transport are read-only properties of a copy made once, so an attribute set or a permit added changes nothing;
code that writes its private `_held` is not held. `send` holds no verb: `tools/check_writes.py` holds who calls the
write builders, and refuses a write request built or edited by hand. Headers or an Accept but the builders', `{}` and
GitHub's JSON, are not sent.

`send` gives the answer as `seen` takes it, `{"status": the status as text, "body": what it said}`; GitHub gives a
number (P-71). A refusal, a 404 or a 422, is an answer: the guard reads the work branch's 404 as the branch the
Decision admitted none of, and takes no other. GitHub answers that 404 alike to a token that cannot read the repo, so
a push reads with the Role's own (P-71). A limit: a token that loses its access mid-push reads the branch as absent;
its next write fails for the same lack, so nothing is written. None for a request `request` would not build or the
sender would not send, an answer with no status from 100 to 599 or no body, a rate limit's 403 (decision 1138), or a
transport's `Unanswered`, `OSError` (a timeout among them) or a body's errors. Anything else it raises is a bug in that transport, and stays raised.

`content` gives a blob's bytes from its read, the base64 GitHub wraps with newlines (P-71), decoded here, never in a
guard, and held to the name asked, never the answer's own.

`listed`, `to_read` and `read_whole` read the tree a patch lands on, as `guards/patch.py` takes it: its listing, then
the bytes of each file the patch reads, one by one, whole or not at all, within `MOST_FILES` files and `MOST_BYTES`
bytes. Each gives a code where it gives nothing, and `WHOSE` names whose each code of the guards and of this port is: the
Role's, counted as its attempt; a person's, a Hold; the port's, an environment fault, for no answer alone; or none's,
`superseded`, where someone else wrote the work branch.

`harness/push.py`, by hand, owes this port: every request sent by `transport`'s sender; its writers in
`tools/check_writes.py`'s CALLERS; one request given unchanged to `permits` and `send`; `content` asked for the name
the admitted tree's listing gives; and P-71 replayed through `send` into `seen`.
"""
from __future__ import annotations

import base64
import hashlib
import re

from adapters.effects import Allowed
from adapters.github import JSON, LARGEST, Unanswered, request
from guards import patch
from guards import push as guard

SHA = re.compile(r"[0-9a-f]{40}")
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}")
WORK = re.compile(r"factory-work/issue-[1-9][0-9]{0,18}-[1-9][0-9]{0,18}")
HEADS = "refs/heads/"
# The modes of a file a push writes or removes: a symlink or a submodule is none (`guards/patch.py`).
FILE_MODES = ("100644", "100755")
# The keys of a request `request` builds, of no download and no tarball: a push's.
REQUEST = {"method", "path", "accept", "body", "headers"}
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
# The most files a push's patch may have read, and the most bytes in all: a patch that reads more is the Role's own
# attempt, refused whole, and nothing is cut short. 64 MiB.
MOST_FILES = 1000
MOST_BYTES = 67108864
# The largest file whose blob answer the transport takes whole: base64, a newline after every 60 characters, each
# written in JSON as two, is 62 characters for every 45 bytes, and an answer past `LARGEST` is refused. 64 KiB is left
# for the rest of the answer. A file the listing says is larger is never read, by any attempt; GitHub's own limit on a
# blob, 100 MB, is higher still.
MOST_BLOB = (LARGEST - 65536) * 45 // 62
# A directory's mode in a tree's listing, and in a tree object, which writes it with no leading zero; and a link's,
# a blob that is no file. A submodule's, a commit, is `guards/patch.py`'s `SUBMODULE`.
DIRECTORY = "040000"
TREE_MODE = "40000"
LINK = "120000"
# Besides GitHub's own failure, 500 and above, a status the port reads as no answer to a listing: a rate limit, or a
# token expired or refused. A blob is read after its listing, by the same token: a 403 on it alone is GitHub refusing
# that blob, and it will refuse it again, so it is a person's. A rate limit's 403, with no request left or a time to
# wait, is no answer to either (decision 1138): `send` gives none.
UNANSWERED = ("401", "403", "429")
BLOB_UNANSWERED = ("401", "429")
# A lone surrogate, which JSON may hold and UTF-8 does not write: no name git holds.
SURROGATES = ("\ud800", "\udfff")
# The port's codes. A read cut short or of no shape is `guards/patch.py`'s `TREE_UNREAD`.
READS_TOO_LARGE = "push_reads_too_large"
TREE_UNFETCHED = "push_tree_unfetched"
ROLE, PERSON, PORT, SUPERSEDED = "role", "person", "port", "superseded"
# Whose each code of the patch guard, the push guard and this port is: the Role's, counted as its attempt; a person's, a Hold on
# the item, since the same commit reads the same way again; the port's, an environment fault; or none's, the Run
# overtaken, `superseded`, where someone else wrote the work branch. Every code is here,
# and none is read with a default: `WHOSE[code]`. A code's letters begin `push_`, `patch_` or `bundle_`: a test finds
# every code of the three modules by them.
WHOSE = {patch.UNREADABLE: ROLE, patch.NOT_APPLIED: ROLE, patch.NOT_A_FILE: ROLE, patch.PATH_TWIN: ROLE,
         patch.TREE_UNREAD: PERSON, READS_TOO_LARGE: ROLE, TREE_UNFETCHED: PORT, guard.NOT_PERMITTED: PERSON,
         guard.BRANCH_MOVED: SUPERSEDED, guard.ANSWER_REFUSED: PERSON, guard.UNANSWERED: PORT}


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
    file where a directory must be. The paths are read in order, so a file comes before anything below it, into one
    tree of their parts, where a file is None: the work is as long as the paths, however deep one is."""
    files = {}
    for path in sorted(paths):
        node, parts = files, path.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if node is None:
                return False
        node[parts[-1]] = None
    return True


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
    if not (_repo(repo) and type(content) is str):
        return None
    return request("POST", _git(repo) + "blobs", body={"content": content, "encoding": "base64"})


def make_tree(repo, base, entries):
    """A tree upon the tree `base`, of `entries`, each `{"path", "mode", "type", "sha"}`, a removed file's sha None: a
    new list of a new dict of each entry's keys, anything else as it is, for the token to refuse; None, uncopied, for
    a list longer than `MOST`."""
    if not (_repo(repo) and _sha(base)) or type(entries) is list and len(entries) > MOST:
        return None
    copied = [dict(entry) if type(entry) is dict else entry for entry in entries] if type(entries) is list else entries
    return request("POST", _git(repo) + "trees", body={"base_tree": base, "tree": copied})


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
    """A push's sender: `Allowed` with what a push's token may send on one repo and its one work branch, `bound`, read
    by properties no attribute replaces; `Allowed.__init__`, which would set them as attributes, is not called."""

    def __init__(self, live, repo, branch):
        permits, patterns = allowed(repo, branch)
        self._held = (dict(permits), tuple(patterns), (repo, branch), live)

    @property
    def _transport(self):
        return self._held[3]

    @property
    def _permits(self):
        return dict(self._held[0])

    @property
    def _patterns(self):
        return self._held[1]

    @property
    def bound(self) -> tuple:
        return self._held[2]


def transport(live, repo, branch):
    """The push's sender on `live`, bound to `repo` and its work branch `branch`; None for either told wrongly, or for
    a `live` with no `send` to call."""
    if not (_repo(repo) and _work(branch) and callable(getattr(live, "send", None))):
        return None
    return _Sender(live, repo, branch)


def send(sender, repo, branch, req):
    """GitHub's answer to `req`, `{"status": the status as text, "body": what it said}`, or None where `req` is no
    request `request` builds or holds what JSON does not, `repo` or `branch` is told wrongly, `sender` is not
    `transport`'s for them, it would not send `req`, or GitHub gave no answer with a status and a body, or a rate
    limit's 403."""
    if not (_repo(repo) and _work(branch)) or type(req) is not dict or not _plain(req) or set(req) != REQUEST \
            or req["headers"] != {} or req["accept"] != JSON:
        return None
    if type(sender) is not _Sender or sender.bound != (repo, branch):
        return None
    try:
        answer = Allowed.send(sender, req)
    except (Unanswered, OSError, TypeError, ValueError, KeyError, AttributeError):
        return None
    status = answer.get("status") if isinstance(answer, dict) else None
    if type(status) is not int or not 100 <= status <= 599 or "body" not in answer or _rate_limited(answer):
        return None
    return {"status": str(status), "body": answer["body"]}


def _rate_limited(answer: dict) -> bool:
    """Whether a 403 is a rate limit's: no request left or a time to wait, as `adapters/pause.py` tells one from a
    refusal (decision 1138)."""
    headers = answer.get("headers") if type(answer.get("headers")) is dict else {}
    return answer["status"] == 403 and (str(headers.get("x-ratelimit-remaining")) == "0" or "retry-after" in headers)


def _said(said, text: str) -> bool:
    return type(said) is str and said == text


def content(answer, sha):
    """The bytes of the blob `sha`, from `send`'s answer to its read: its `content` read as base64 past the newlines
    GitHub puts in it, and nothing else let pass; None where the answer is no success, no base64, or bytes whose git
    name is not `sha`, a name of 40 hex digits as text itself."""
    if not _sha(sha):
        return None
    body = answer.get("body") if type(answer) is dict and _said(answer.get("status"), "200") else None
    if type(body) is not dict or not _said(body.get("encoding"), "base64"):
        return None
    data = _decoded(body.get("content"))
    if data is None:
        return None
    # Git names a blob by sha1 of `blob <size>\0` and its bytes: the hash is git's, compared with git's own.
    if hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest() != sha:
        return None
    return data


def _unanswered(answer, statuses=UNANSWERED) -> bool:
    """Whether `send` gave no answer, or one the port reads as none: a status `statuses` names, or 500 and above."""
    if type(answer) is not dict or type(answer.get("status")) is not str:
        return True
    status = answer["status"]
    return status in statuses or status.startswith("5")


def _tree_name(entries: list) -> str:
    """The git name of the tree object of `entries`, each `(mode, name, sha)` as a tree object writes it: sorted by
    name, a directory's name as if a `/` followed it, each a mode, a name, a NUL and the 20 bytes of its sha."""
    def order(entry):
        return entry[1].encode() + (b"/" if entry[0] == TREE_MODE else b"")
    body = b"".join(b"%s %s\0" % (mode.encode(), name.encode()) + bytes.fromhex(sha)
                    for mode, name, sha in sorted(entries, key=order))
    # Git names a tree by sha1 of `tree <size>\0` and its entries: the hash is git's, compared with git's own.
    return hashlib.sha1(b"tree %d\0" % len(body) + body, usedforsecurity=False).hexdigest()


def listed(answer, sha):
    """`(listing, None)` from `send`'s answer to `read_tree` of `sha`, or `(None, code)`. The listing is `{"tree",
    "blobs", "sha", "whole"}`: `tree` is each path the tree holds that is no directory, to its mode, as
    `guards/patch.py`'s `applied` takes it; `blobs` is each file's and link's `(sha, size)`; `sha` is the tree it was
    read at; and `whole` is True, the mark `guards/push.py`'s `seen` asks for, given here alone. Each directory's
    entries are rebuilt into its tree object and named as git names it, the whole into `sha`: an entry left out,
    added, listed twice or under no directory listed is a listing of no tree. An answer the port reads as none is the
    port's, `TREE_UNFETCHED`; one GitHub cut short, `truncated`, of another tree, or in any shape not read here, is a
    person's, `TREE_UNREAD`: the same commit reads the same way again, and no part of a listing is taken. So is a
    `sha` that is no name of 40 hex digits as text itself, which the mark would carry."""
    if not _sha(sha):
        return None, patch.TREE_UNREAD
    if _unanswered(answer):
        return None, TREE_UNFETCHED
    body = answer.get("body") if _said(answer.get("status"), "200") else None
    if type(body) is not dict or body.get("truncated") is not False or not _said(body.get("sha"), sha) \
            or type(body.get("tree")) is not list:
        return None, patch.TREE_UNREAD
    entries = body["tree"]
    if not all(type(entry) is dict and type(entry.get("path")) is str and _sha(entry.get("sha")) for entry in entries):
        return None, patch.TREE_UNREAD
    # A path is of parts each named, with no NUL, which a tree object writes after a name, and no lone surrogate, which
    # UTF-8 does not write; and it is listed once: two entries of one path can make a tree's name and still be no tree.
    paths = [entry["path"] for entry in entries]
    if len(set(paths)) != len(paths) or any("" in path.split("/") or "\0" in path
                                             or any(SURROGATES[0] <= c <= SURROGATES[1] for c in path)
                                             for path in paths):
        return None, patch.TREE_UNREAD
    folders = {"": []}
    folders.update({entry["path"]: [] for entry in entries
                    if (entry.get("type"), entry.get("mode")) == ("tree", DIRECTORY)})
    named = {"": sha}
    tree, blobs = {}, {}
    for entry in entries:
        path, kind, mode, size = entry["path"], entry.get("type"), entry.get("mode"), entry.get("size")
        parent, _, name = path.rpartition("/")
        if not name or parent not in folders:
            return None, patch.TREE_UNREAD
        if path in folders:
            folders[parent].append((TREE_MODE, name, entry["sha"]))
            named[path] = entry["sha"]
            continue
        if kind == "commit" and mode == patch.SUBMODULE:
            tree[path] = mode
        elif kind == "blob" and mode in FILE_MODES + (LINK,) and type(size) is int and size >= 0:
            tree[path], blobs[path] = mode, (entry["sha"], size)
        else:
            return None, patch.TREE_UNREAD
        folders[parent].append((mode, name, entry["sha"]))
    if any(_tree_name(held) != named[path] for path, held in folders.items()):
        return None, patch.TREE_UNREAD
    return {"tree": tree, "blobs": blobs, "sha": sha, "whole": True}, None


def to_read(listing, sources):
    """`(paths, None)`, the files among `sources` (`guards/patch.py`'s) whose bytes a push reads, in their order, or
    `(None, code)`. A path the listing does not hold, a link or a submodule is read by no one: the guard refuses the
    patch without its bytes. A file larger than the transport takes whole, `MOST_BLOB`, is a person's, `TREE_UNREAD`.
    More files than `MOST_FILES`, or more bytes than `MOST_BYTES` in all by the listing's sizes, is the Role's,
    `READS_TOO_LARGE`: nothing is read. A patch `sources` cannot read reads nothing, and the guard names it."""
    tree, blobs = listing["tree"], listing["blobs"]
    paths = [path for path in sources or () if tree.get(path) in FILE_MODES]
    if any(blobs[path][1] > MOST_BLOB for path in paths):
        return None, patch.TREE_UNREAD
    if len(paths) > MOST_FILES or sum(blobs[path][1] for path in paths) > MOST_BYTES:
        return None, READS_TOO_LARGE
    return paths, None


def read_whole(listing, paths, read):
    """`(contents, None)`, each of `paths` to its bytes, or `(None, code)`, all or nothing. `read(path)` gives `send`'s
    answer to `read_blob` of the sha the listing gives that path; it is asked in order, and asked no more once one
    gives a code, so no more than `MOST_BYTES` and one answer are ever held. A missing answer, or one the port reads as
    none, `BLOB_UNANSWERED`, is the port's, `TREE_UNFETCHED`; any other that gives no bytes of that name, a refusal, a
    403 among them, or a blob too large, of no blob or of other bytes, a person's, `TREE_UNREAD`. Bytes past `MOST_BYTES` in all, whatever the listing
    said, are the Role's, `READS_TOO_LARGE`."""
    contents, held = {}, 0
    for path in paths:
        answer = read(path) if callable(read) else None
        data = content(answer, listing["blobs"][path][0])
        if data is None:
            return None, TREE_UNFETCHED if _unanswered(answer, BLOB_UNANSWERED) else patch.TREE_UNREAD
        held += len(data)
        if held > MOST_BYTES:
            return None, READS_TOO_LARGE
        contents[path] = data
    return contents, None


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
