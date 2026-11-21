"""What the desk runs beside the checks, for a person to read, and no check (issue 1109): about how large the Factory
will count a branch's diff. It fails no run that CI or a hook acts on.

`python3 -m tools.desk size` prints a note: about how many characters and lines the Factory will count the diff the
branch has committed against `origin/main` at, each against its limit in `config/defaults.json`, with a warning past
SHARE of either. It counts as `adapters/pull.py` counts a pull request's diff: each index line cut as `canonical` cuts
it, then numbered and escaped as JSON. GitHub heads its hunks a little differently, so the count is near the Factory's,
not equal to it. A stale local `origin/main` errs high: the base is older than main's, and what main merged since counts
as the branch's. Edits not committed are not counted; it says so of staged ones, and how many untracked files there are,
and says so of text that is no UTF-8, which the Factory holds. `make checks` prints the note after the checks, on the
desk's run alone (`tools/verify.py --checks`): CI's legs never run it, and nothing it does changes what make checks
answers. The hooks never show it: they show make checks only when a check fails.

Each read is git's own, with no program a repo's configuration names, no fetch and a timeout: `origin/main` is whatever
this clone last fetched.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

from adapters import pull
from harness import task

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "refs/remotes/origin/main"
SHARE = 0.95            # of a limit, past which `size` warns: the Factory's count runs a few hundred characters apart
SECONDS = 10
# The only verbs this runs: each reads this clone, and none fetches, pushes or reaches a remote.
READS = ("config", "diff", "diff-index", "ls-files", "merge-base")
# Each read is git's own: no program a repo's configuration names runs, no object is fetched, no lock is taken.
SAFE = ("--no-replace-objects", "--literal-pathspecs", "-c", "core.commitGraph=false", "-c", "core.fsmonitor=false",
        "-c", "diff.external=", "-c", "diff.ignoreSubmodules=none")
# A diff as GitHub writes one: no colour, no external diff, no textconv, the whole tree, renames found, a/ and b/; its
# index lines whole, for `canonical` to cut as the Factory's are cut, however long this clone abbreviates an id.
FORM = ("--no-color", "--no-ext-diff", "--no-textconv", "--no-relative", "-M")
DIFF = FORM + ("--src-prefix=a/", "--dst-prefix=b/", "-U3", "--full-index")
MOST = 10 ** 9          # a limit past this is no limit this note can compare with


def _git(root: pathlib.Path, *args: str) -> bytes:
    """What git prints for `args` in `root` alone, no GIT_ variable of whatever runs this read. Raises ValueError."""
    if args[0] not in READS:
        raise ValueError("git %s is no read" % args[0])
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    try:
        done = subprocess.run(["git", *SAFE, *args], cwd=str(root), env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("git %s did not finish" % args[0]) from None
    if done.returncode != 0:
        raise ValueError("git %s failed" % args[0])
    return done.stdout


def _text(data: bytes) -> str:
    return data.decode("utf-8", "surrogateescape")


def _rows(data: bytes) -> list:
    return [row for row in _text(data).split("\0") if row]


def limits(root: pathlib.Path) -> tuple:
    """(the most characters, the most lines) a diff may be counted at, from `config/defaults.json`. Raises ValueError."""
    try:
        said = json.loads((root / "config" / "defaults.json").read_text(encoding="utf-8"))["limits"]
        most = said["max_diff_characters"], said["max_diff_lines"]
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("config/defaults.json's limits cannot be read") from None
    if not all(type(n) is int and 0 < n < MOST for n in most):
        raise ValueError("config/defaults.json's limits cannot be read")
    return most


def counted(diff: str, numstat: str) -> tuple:
    """(about the characters the Factory counts `diff` at, the lines it adds and removes, from `numstat`)."""
    lines = sum(int(n) for row in numstat.splitlines() for n in row.split("\t")[:2] if n.isdigit())
    return task.carried(task.numbered(pull.canonical(diff))), lines


def _partial(root: pathlib.Path) -> bool:
    """Whether this clone may fetch a missing object as it reads one: a partial clone's reads can."""
    try:
        return bool(_text(_git(root, "config", "--get", "extensions.partialclone")).strip())
    except ValueError:
        return False


def size(root: pathlib.Path = ROOT) -> str:
    """The note on about the size of what the branch has committed against BASE; never a failure. A working tree's
    edits are not read: a diff of them would run whatever clean filter the repo's attributes name."""
    if not os.path.lexists(str(root / ".git")):
        return "no base to compare: this tree is no clone"
    if _partial(root):
        return "no count: this is a partial clone, whose reads may fetch"
    try:
        base = _text(_git(root, "merge-base", "HEAD", BASE)).strip()
        raw = _git(root, "diff", *DIFF, base, "HEAD")
        numstat = _text(_git(root, "diff", "--numstat", *FORM, base, "HEAD"))
        staged = bool(_rows(_git(root, "diff-index", "--cached", "--name-only", "-z", "HEAD")))
        untracked = len(_rows(_git(root, "ls-files", "--others", "--exclude-standard", "-z")))
    except ValueError:
        return "no base to compare: origin/main cannot be read here"
    try:
        most_characters, most_lines = limits(root)
    except ValueError as err:
        return "no limit to compare: %s" % err
    try:
        diff = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "the diff holds text that is no UTF-8, which the Factory holds and counts no size of; take it out"
    characters, lines = counted(diff, numstat)
    over = characters > SHARE * most_characters or lines > SHARE * most_lines
    left = (["staged edits"] if staged else []) + (
        ["%d untracked file%s" % (untracked, "" if untracked == 1 else "s")] if untracked else [])
    return "about %d of %d characters and %d of %d lines committed against origin/main as last fetched%s%s" % (
        characters, most_characters, lines, most_lines, ", %s not counted" % " and ".join(left) if left else "",
        "; split it before it opens, or the Factory holds it as too_large" if over else "")


def main(argv: list, root: pathlib.Path = ROOT) -> int:
    if argv == ["size"]:
        print(size(root))
        return 0
    print("usage: python3 -m tools.desk size")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
