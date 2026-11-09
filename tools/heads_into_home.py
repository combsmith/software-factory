"""Each case's head, put beside the case in the held-out home and pinned by it (issue 611). Run at the Maintainer's
terminal, in his checkout of the home, never in a session: a session never sees a case.

    GH_TOKEN="$(gh auth token)" python3 -m tools.heads_into_home <the home's checkout> <role folder>

For each case `<role folder>/<id>.json`, it reads the commit the case names as its head, `head`, of the repo its facts
name, through the one transport with the token given: the commit's tarball, through codeload as a live Run reads one
(decision 0138), and its tree, every level of it (decision 0142). It holds the one to the other, as the eval job will,
and only then writes `<id>.tar.gz` and `<id>.tree.json` beside the case, and adds to the case the sha256 of each,
`head_sha256` and `tree_sha256`, after its `head`, writing the case anew. Each file is written whole into the folder and
moved over its name, so a link there is replaced and never written through; a folder that is a link is refused. It
takes a role folder and touches nothing else: so the review Intent's set and a gate set made later are pinned alike.

It prints counts and hashes alone, never a byte of a case: how many cases it pinned and, by a code, how many it did not,
then each pinned case's id and the sha256 of its new bytes, one JSON object to a line, which is what the set's manifest
under `evals/` takes. A case it did not pin is left as it was. It exits 0 only when every case was pinned."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pathlib
import re
import sys
import tempfile

PART = re.compile(r"[a-z0-9][a-z0-9-]*")      # a Role or a case id, as eval-set/1 holds them: no dot, no slash
COMMIT = re.compile(r"[0-9a-f]{40}")
REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}")


def put(folder: pathlib.Path, name: str, data: bytes) -> None:
    """`data` written as `folder/name`, whole or not at all: into a new file beside it, then moved over it, so that a
    link already at that name is replaced, never written through, and nothing is left half written."""
    fd, temporary = tempfile.mkstemp(dir=str(folder), prefix=".heads-into-home-")
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        os.replace(temporary, str(folder / name))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def read(path: pathlib.Path):
    """The bytes of the case at `path`, or None for one that is a link or cannot be read as a file."""
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        with os.fdopen(fd, "rb") as f:
            return f.read()
    except OSError:
        return None


def pinned(data: bytes, transport, folder: pathlib.Path, ident: str):
    """`(the case's new bytes, None)` once its head's tarball and tree are written beside it in `folder`, or `(None, code)`:
    `not_a_case` for bytes that are no case with a head of a repo, and `head_unreadable` for a head not read, unpacked,
    held to its tree, or within what the eval job reads, whole. Nothing is written for a case not pinned."""
    from adapters import github, heldout
    from harness import head
    try:
        case = json.loads(data)
        repo, sha = case["facts"]["item"]["repo"], case["head"]
    except (ValueError, TypeError, KeyError, RecursionError):
        return None, "not_a_case"
    if not (isinstance(case, dict) and case.get("id") == ident and isinstance(sha, str) and COMMIT.fullmatch(sha)
            and isinstance(repo, str) and REPO.fullmatch(repo)):
        return None, "not_a_case"
    if not github.TREE.fullmatch(head.tree_path(repo, sha)):
        return None, "not_a_case"
    try:
        tar = head.fetch(transport, repo, sha)
        answer = transport.send(github.request("GET", head.tree_path(repo, sha)))
        if answer.get("status") != 200:
            raise head.Refused("the commit's tree was not answered")
        tree = head.tree_of(answer.get("body"))
        with tempfile.TemporaryDirectory() as scratch:
            into = os.path.join(os.path.realpath(scratch), ident)
            head.unpack(tar, sha, into)
            head.held(into, tree)
    except (head.Refused, github.Unanswered, OSError):
        return None, "head_unreadable"
    # The tree as GitHub's answer held it, written compact, so that a tree GitHub gave whole is within what the job reads.
    listed = (json.dumps(answer["body"], separators=(",", ":")) + "\n").encode("utf-8")
    if len(tar) > heldout.BESIDE["tar.gz"] or len(listed) > heldout.BESIDE["tree.json"]:
        return None, "head_unreadable"
    out = {}
    for key, value in case.items():
        if key not in ("head_sha256", "tree_sha256"):
            out[key] = value
        if key == "head":
            out["head_sha256"], out["tree_sha256"] = hashlib.sha256(tar).hexdigest(), hashlib.sha256(listed).hexdigest()
    new = (json.dumps(out, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    put(folder, "%s.tar.gz" % ident, tar)
    put(folder, "%s.tree.json" % ident, listed)
    return new, None


def main(argv: list, env=None, transport=None, out=None) -> int:
    from adapters import github
    env, out = os.environ if env is None else env, sys.stdout if out is None else out
    if len(argv) != 2 or not PART.fullmatch(argv[1]) or not (pathlib.Path(argv[0]) / argv[1]).is_dir() \
            or (pathlib.Path(argv[0]) / argv[1]).is_symlink():
        out.write("usage: GH_TOKEN=... python3 -m tools.heads_into_home <the home's checkout> <role folder>\n")
        return 2
    folder = pathlib.Path(argv[0]) / argv[1]
    if transport is None:
        if not env.get("GH_TOKEN"):
            out.write("no token: give one as GH_TOKEN\n")
            return 2
        from harness.eval.fetch import ReadOnly
        transport = ReadOnly(github.Live(env["GH_TOKEN"]))
    said, entries = {"pinned": 0}, []
    for path in sorted(p for p in folder.iterdir() if p.suffix == ".json" and not p.name.endswith(".tree.json")):
        ident = path.name[:-len(".json")]
        data = read(path) if PART.fullmatch(ident) else None
        try:
            new, code = pinned(data, transport, folder, ident) if data is not None else (None, "not_a_case")
            if new is not None:
                put(folder, path.name, new)
        except Exception:       # by its code alone: no message, which could quote a case
            new, code = None, "not_written"
        said[code or "pinned"] = said.get(code or "pinned", 0) + 1
        if new is not None:
            entries.append({"id": ident, "sha256": hashlib.sha256(new).hexdigest()})
    out.write("pinned %d of %d cases%s\n" % (said["pinned"], sum(said.values()), "".join(
        "; %s %d" % (code, n) for code, n in sorted(said.items()) if code != "pinned")))
    for entry in entries:
        out.write(json.dumps(entry) + "\n")
    return 0 if said["pinned"] == sum(said.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
