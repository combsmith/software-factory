"""A gate set's manifest counts its cases in the groups main has counted them in.

A gate set's report is counts alone, each of a group of ten cases at least (decisions 0164 and 0180). The groups are
the manifest's: the criteria it floors and the cases it marks natural. Two manifests of the same cases that floored
other criteria, or marked other cases natural, would publish counts whose difference is a group of fewer cases than a
report may count, one case's verdict among them (issue 695, decision 0208). So each gate set's manifest under `evals/`
is held to every gate set's manifest main has held of the same cases, each id with its sha256, under any name, and to
the others in this tree: it floors the criteria they floor and marks natural the cases they mark. A floor's fraction
may change, as no count is of it.

What main has held is read from the merge base with origin/main back: every manifest under `evals/` as each commit
of main that changed anything there left it. The base is the decision records', `tools/check_decisions.py`'s. One that cannot be read fails, and an export, which
has no history, is held to its own tree alone. A tree with no gate set reads no history. In a merge group the
entries ahead are read as main's, from the commit before this one. The check reads no
case, and stops a pull request, never a dispatch. Cases that changed are other cases: a set issued again, or with one
added or dropped, is not held to what the cases before it counted, which is a residual.
"""
from __future__ import annotations

import json
import os
import pathlib
import re

from tools.check_decisions import Unreadable, _git, base
from tools.check_examples import _once

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = re.compile(r"evals/[^/]+/cases\.json")


def _groups(found):
    """`(cases, floored, natural)` of a gate set's manifest: each case's id with its hash, the criteria it floors, and
    the ids it marks natural, which are the groups its reports count; None for what is no gate set's manifest."""
    cases = found.get("cases") if isinstance(found, dict) and found.get("gate") is True else None
    if not isinstance(cases, list) or not all(isinstance(c, dict) and isinstance(c.get("id"), str)
                                              and isinstance(c.get("sha256"), str) for c in cases):
        return None
    floors = found.get("criterion_bars", {})
    return (frozenset((c["id"], c["sha256"]) for c in cases), frozenset(floors if isinstance(floors, dict) else ()),
            frozenset(c["id"] for c in cases if c.get("natural") is True))


def _read(text: str):
    """`_groups` of a manifest's text; None for what is not JSON, or writes a key twice."""
    try:
        return _groups(json.loads(text, object_pairs_hook=_once))
    except (ValueError, RecursionError):
        return None


def _held(root: pathlib.Path, at: str) -> list:
    """`[(where, groups)]` of each gate set's manifest main held at `at` or before it, once for each way of counting:
    every manifest under `evals/` as each commit of main that changed anything there left it. Raises Unreadable."""
    seen, read, found = set(), {}, []
    for commit in _git(root, "log", "--first-parent", "--format=%H", at, "--", "evals").split():
        for entry in _git(root, "ls-tree", "-r", "-z", commit, "--", "evals/").split("\0"):
            kind, _, name = entry.partition("\t")
            # A regular file alone: a link's bytes are its target's name, and a gitlink is no file at all.
            if not MANIFEST.fullmatch(name) or kind.split()[0] not in ("100644", "100755"):
                continue
            blob = kind.split()[2]
            if blob not in read:
                read[blob] = _read(_git(root, "cat-file", "blob", blob))
            if read[blob] is not None and read[blob] not in seen:
                seen.add(read[blob])
                found.append(("%s at %s" % (name, commit[:12]), read[blob]))
    return found


def run(root: pathlib.Path = ROOT) -> list:
    here = []
    for path in sorted(p for p in (root / "evals").glob("*/cases.json") if p.is_file()):
        groups = _read(path.read_text(encoding="utf-8", errors="replace"))
        if groups is not None:
            here.append((path.relative_to(root).as_posix(), groups))
    if not here:
        return []       # nothing to hold, and no history read for it
    try:
        at = base(root)
        # In a merge group the entries ahead of this one are main's to be: the history is read from the commit before it.
        since = "HEAD^" if at and os.environ.get("GITHUB_EVENT_NAME") == "merge_group" else at
        before = _held(root, since) if since else []
    except Unreadable as err:
        return ["%s: cannot be compared with what main has held (%s); fetch main's whole history and run again"
                % (rel, err) for rel, _ in here]
    problems = []
    for rel, now in here:
        for where, was in before + here:
            if was[0] != now[0]:
                continue
            if was[1] != now[1]:
                problems.append("%s: floors other criteria than %s does of the same cases; a gate set's floored "
                                "criteria change only with its cases (decision 0208)" % (rel, where))
            if was[2] != now[2]:
                problems.append("%s: marks other cases natural than %s does of the same cases; a gate set's natural "
                                "marks change only with its cases (decision 0208)" % (rel, where))
    return problems
