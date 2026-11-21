"""What the desk runs beside the checks, and CI never needs: how large the Factory will count a branch's diff, and
whether a merge of main kept every line of main and of the branch (issues 1109 and 1110).

`python3 -m tools.desk size` prints the note `make checks` prints after the checks: the branch's diff against
`origin/main`, counted as `adapters/pull.py` counts a pull request's, numbered and escaped as JSON, and its lines, each
against its limit in `config/defaults.json`, with a warning past SHARE of either. GitHub's diff of a pull request heads
its hunks a little differently, so the count is near the Factory's, not equal to it; the margin is for that.

`python3 -m tools.desk merged` reads the merge just made, in progress or committed: a file one side changed holds that
side's text, and in a file both changed, no line of main is gone that the branch did not take out, and no line is there
that main took out and the branch did not add. A conflict resolved by keeping one side whole fails it. A line both
sides changed is reported too: keeping the branch's is right only where the branch meant to replace main's.

It reads git and runs nothing else, and fetches nothing: `origin/main` is whatever this clone last fetched.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

from harness import task

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "origin/main"
SHARE = 0.95            # of a limit, past which `size` warns: the Factory's count runs a few hundred characters apart
SHOWN = 5               # the lines told of each file, at most
SECONDS = 60


def _git(root: pathlib.Path, *args: str) -> str:
    """What git prints for `args` in `root` alone, no GIT_ variable of whatever runs this read. Raises ValueError."""
    exe = shutil.which("git")
    if exe is None:
        raise ValueError("git is not on PATH")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        done = subprocess.run([exe, *args], cwd=str(root), env=env, capture_output=True, timeout=SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("git %s did not finish" % args[0]) from None
    if done.returncode != 0:
        raise ValueError("git %s failed" % args[0])
    return done.stdout.decode("utf-8", "replace")


def limits(root: pathlib.Path) -> tuple:
    """(the most characters, the most lines) a diff may be counted at, from `config/defaults.json`."""
    said = json.loads((root / "config" / "defaults.json").read_text(encoding="utf-8"))["limits"]
    return said["max_diff_characters"], said["max_diff_lines"]


def counted(diff: str, numstat: str) -> tuple:
    """(the characters the Factory counts `diff` at, the lines it adds and removes, from `numstat`)."""
    lines = sum(int(n) for row in numstat.splitlines() for n in row.split("\t")[:2] if n.isdigit())
    return task.carried(task.numbered(diff)), lines


def size(root: pathlib.Path = ROOT) -> str:
    """The note on the branch's size against BASE, the working tree's own edits counted; never a failure."""
    if not os.path.lexists(str(root / ".git")):
        return "no base to compare: this tree is no clone"
    try:
        base = _git(root, "merge-base", "HEAD", BASE).strip()
        diff = _git(root, "diff", "--no-color", "--no-ext-diff", base)
        numstat = _git(root, "diff", "--numstat", "--no-ext-diff", base)
        untracked = [rel for rel in _git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0") if rel]
    except ValueError:
        return "no base to compare: %s cannot be read here" % BASE
    characters, lines = counted(diff, numstat)
    most_characters, most_lines = limits(root)
    over = characters > SHARE * most_characters or lines > SHARE * most_lines
    return "%d of %d characters and %d of %d lines against %s as last fetched%s%s" % (
        characters, most_characters, lines, most_lines, BASE,
        ", and %d file%s git does not track yet, not counted" % (len(untracked), "" if len(untracked) == 1 else "s")
        if untracked else "",
        "; split it before it opens, or the Factory holds it as too_large" if over else "")


def _read(root: pathlib.Path, where, rel: str):
    """The lines of `rel` at commit `where`, or in the working tree for None; None where it is not there."""
    if where is None:
        path = root / rel
        return path.read_bytes().decode("utf-8", "replace").splitlines() if path.is_file() else None
    try:
        return _git(root, "show", "%s:%s" % (where, rel)).splitlines()
    except ValueError:
        return None


def _less(more: dict, fewer: dict) -> dict:
    """The lines `more` holds beyond `fewer`, each counted as often as it is beyond, as two multisets are taken apart."""
    return {line: n - fewer.get(line, 0) for line, n in more.items() if n > fewer.get(line, 0)}


def _counts(lines) -> dict:
    counts = {}
    for line in lines or ():
        counts[line] = counts.get(line, 0) + 1
    return counts


def _changed(root: pathlib.Path, base: str, side: str) -> set:
    return set(_git(root, "diff", "--name-only", "--no-renames", "-z", base, side).split("\0")) - {""}


def merged(root: pathlib.Path = ROOT) -> list:
    """What the merge in progress, or the merge commit at HEAD, lost of either side: [] when it kept both."""
    try:
        theirs = _git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").strip()
        ours, result = _git(root, "rev-parse", "HEAD").strip(), None
    except ValueError:
        parents = _git(root, "rev-list", "--parents", "-n", "1", "HEAD").split()
        if len(parents) != 3:
            return ["HEAD is no merge and no merge is in progress: run git merge %s first" % BASE]
        result, ours, theirs = parents
    base = _git(root, "merge-base", ours, theirs).strip()
    mine, main = _changed(root, base, ours), _changed(root, base, theirs)
    problems = []
    for rel in sorted(mine | main):
        made = _read(root, result, rel)
        if rel not in mine or rel not in main:
            side, whose = (theirs, "main") if rel not in mine else (ours, "the branch")
            if made != _read(root, side, rel):
                problems.append("%s: only %s changed it, and the merge does not hold %s's text" % (rel, whose, whose))
            continue
        was, kept, wanted = (_counts(_read(root, where, rel)) for where in (base, ours, theirs))
        have = _counts(made)
        lost = _less(_less(wanted, have), _less(was, kept))
        back = _less(_less(have, wanted), _less(kept, was))
        for line in sorted(lost)[:SHOWN]:
            problems.append("%s: main's line is gone, and the branch did not take it out: %s" % (rel, line.strip()[:120]))
        for line in sorted(back)[:SHOWN]:
            problems.append("%s: a line main took out, or no side wrote, is there: %s" % (rel, line.strip()[:120]))
    return problems


def main(argv: list, root: pathlib.Path = ROOT) -> int:
    if argv == ["size"]:
        print(size(root))
        return 0
    if argv == ["merged"]:
        try:
            problems = merged(root)
        except ValueError as err:
            problems = ["the merge cannot be read: %s" % err]
        for problem in problems:
            print(problem)
        print("the merge keeps every line of both sides" if not problems else
              "%d problems: put each line back, or say why the branch meant to replace it" % len(problems))
        return 1 if problems else 0
    print("usage: python3 -m tools.desk size | merged")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
