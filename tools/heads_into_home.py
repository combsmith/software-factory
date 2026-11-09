"""Each case's head, put beside the case in the held-out home and pinned by it (issue 611). Run at the Maintainer's
terminal, in his checkout of the home, never in a session: a session never sees a case.

    GH_TOKEN="$(gh auth token)" python3 -m tools.heads_into_home <the home's checkout> <role folder>

For each case `<role folder>/<id>.json`, it reads the commit the case names as its head, `head`, of the repo its facts
name, through the one transport with the token given: the commit's tarball, through codeload as a live Run reads one
(decision 0138), and its tree, every level of it (decision 0142). It holds the one to the other, as the eval job will,
and only then writes `<id>.tar.gz` and `<id>.tree.json` beside the case, and adds to the case the sha256 of each,
`head_sha256` and `tree_sha256`, after its `head`. It takes a role folder and touches nothing else: so the review
Intent's set and a gate set made later are pinned alike.

It prints counts and hashes alone, never a byte of a case: how many cases it pinned and, by a code, how many it did not,
then each pinned case's id and the sha256 of its new bytes, one JSON object to a line, which is what the set's manifest
under `evals/` takes. A case it did not pin is left as it was. It exits 0 only when every case was pinned."""
from __future__ import annotations

import collections
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


def pinned(data: bytes, transport, folder: pathlib.Path, ident: str):
    """`(the case's new bytes, None)` once its head's tarball and tree are written beside it in `folder`, or `(None, code)`:
    `not_a_case` for bytes that are no case with a head of a repo, and `head_unreadable` for a head not read, unpacked or
    held to its tree whole. Nothing is written for a case not pinned."""
    from adapters import github
    from harness import head
    try:
        case = json.loads(data)
        repo, sha = case["facts"]["item"]["repo"], case["head"]
    except (ValueError, TypeError, KeyError, RecursionError):
        return None, "not_a_case"
    if not (isinstance(case, dict) and case.get("id") == ident and isinstance(sha, str) and COMMIT.fullmatch(sha)
            and isinstance(repo, str) and REPO.fullmatch(repo)):
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
    listed = (json.dumps(answer["body"], indent=2) + "\n").encode("utf-8")
    (folder / ("%s.tar.gz" % ident)).write_bytes(tar)
    (folder / ("%s.tree.json" % ident)).write_bytes(listed)
    out = {}
    for key, value in case.items():
        if key not in ("head_sha256", "tree_sha256"):
            out[key] = value
        if key == "head":
            out["head_sha256"], out["tree_sha256"] = hashlib.sha256(tar).hexdigest(), hashlib.sha256(listed).hexdigest()
    return (json.dumps(out, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), None


def main(argv: list, env=None, transport=None, out=None) -> int:
    from adapters import github
    env, out = os.environ if env is None else env, sys.stdout if out is None else out
    if len(argv) != 2 or not PART.fullmatch(argv[1]) or not (pathlib.Path(argv[0]) / argv[1]).is_dir():
        out.write("usage: GH_TOKEN=... python3 -m tools.heads_into_home <the home's checkout> <role folder>\n")
        return 2
    folder = pathlib.Path(argv[0]) / argv[1]
    if transport is None:
        if not env.get("GH_TOKEN"):
            out.write("no token: give one as GH_TOKEN\n")
            return 2
        transport = github.Live(env["GH_TOKEN"])
    said, entries = collections.Counter(), []
    for path in sorted(p for p in folder.iterdir() if p.suffix == ".json" and not p.name.endswith(".tree.json")):
        ident = path.name[:-len(".json")]
        new, code = pinned(path.read_bytes(), transport, folder, ident) if PART.fullmatch(ident) else (None, "not_a_case")
        said[code or "pinned"] += 1
        if new is not None:
            path.write_bytes(new)
            entries.append({"id": ident, "sha256": hashlib.sha256(new).hexdigest()})
    out.write("pinned %d of %d cases%s\n" % (said["pinned"], sum(said.values()), "".join(
        "; %s %d" % (code, n) for code, n in sorted(said.items()) if code != "pinned")))
    for entry in entries:
        out.write(json.dumps(entry) + "\n")
    return 0 if said["pinned"] == sum(said.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
