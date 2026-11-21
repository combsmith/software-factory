"""What the desk runs beside the checks, and CI never needs: how large the Factory will count a branch's diff, and
whether a merge of main kept every line of main and of the branch (issues 1109 and 1110).

`python3 -m tools.desk size` prints the note `make checks` prints after the checks: the branch's diff against
`origin/main`, counted as `adapters/pull.py` counts a pull request's, numbered and escaped as JSON, and its lines, each
against its limit in `config/defaults.json`, with a warning past SHARE of either. GitHub's diff of a pull request heads
its hunks a little differently, so the count is near the Factory's, not equal to it; the margin is for that. It never
fails the run: what it cannot read, it says.

`python3 -m tools.desk merged` reads the merge of `origin/main` just made, staged and not yet committed or committed:
a file one side changed holds that side's bytes; in a file both changed, no line of either side is gone that the other
did not take out, and no line is there that a side took out or no side wrote; a file neither side changed is as both
left it. A conflict resolved by keeping one side whole fails it, and so does a line both sides changed: keeping one is
right only where that side meant to replace the other's. Lines are compared as counts, not in order, so a line moved
is not seen; a rename is named for a reader, not judged.

It runs git only to read, with what could run another program or fetch switched off, and fetches nothing:
`origin/main` is whatever this clone last fetched.
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
BASE = "refs/remotes/origin/main"
SHARE = 0.95            # of a limit, past which `size` warns: the Factory's count runs a few hundred characters apart
SHOWN = 5               # the lines told of each file, at most, each cut to WIDTH
WIDTH = 60
SECONDS = 10
# Each read is git's own: no program a repo's configuration names runs, no object is fetched, no lock is taken.
SAFE = ("--no-replace-objects", "--literal-pathspecs", "-c", "core.commitGraph=false", "-c", "core.fsmonitor=false",
        "-c", "diff.external=", "-c", "diff.ignoreSubmodules=none")
FORM = ("--no-color", "--no-ext-diff", "--no-textconv", "-M")
DIFF = FORM + ("--src-prefix=a/", "--dst-prefix=b/", "-U3")
MOST = 10 ** 9          # a limit past this is no limit this note can compare with


def _git(root: pathlib.Path, *args: str) -> bytes:
    """What git prints for `args` in `root` alone, no GIT_ variable of whatever runs this read. Raises ValueError."""
    exe = shutil.which("git")
    if exe is None:
        raise ValueError("git is not on PATH")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    try:
        done = subprocess.run([exe, *SAFE, *args], cwd=str(root), env=env, capture_output=True, timeout=SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("git %s did not finish" % args[0]) from None
    if done.returncode != 0:
        raise ValueError("git %s failed" % args[0])
    return done.stdout


def _text(data: bytes) -> str:
    return data.decode("utf-8", "surrogateescape")


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
    """(the characters the Factory counts `diff` at, the lines it adds and removes, from `numstat`)."""
    lines = sum(int(n) for row in numstat.splitlines() for n in row.split("\t")[:2] if n.isdigit())
    return task.carried(task.numbered(diff)), lines


def _partial(root: pathlib.Path) -> bool:
    """Whether this clone may fetch a missing object as it reads one: a partial clone's reads can."""
    try:
        return bool(_text(_git(root, "config", "--get", "extensions.partialclone")).strip())
    except ValueError:
        return False


def size(root: pathlib.Path = ROOT) -> str:
    """The note on the size of what the branch has committed against BASE; never a failure. A working tree's edits are
    not read: a diff of them would run whatever clean filter the repo's attributes name."""
    if not os.path.lexists(str(root / ".git")):
        return "no base to compare: this tree is no clone"
    if _partial(root):
        return "no count: this is a partial clone, whose reads may fetch"
    try:
        base = _text(_git(root, "merge-base", "HEAD", BASE)).strip()
        raw = _git(root, "diff", *DIFF, base, "HEAD")
        numstat = _text(_git(root, "diff", "--numstat", *FORM, base, "HEAD"))
        edited = bool(_text(_git(root, "diff-index", "--cached", "--name-only", "HEAD")).strip())
    except ValueError:
        return "no base to compare: origin/main cannot be read here"
    try:
        most_characters, most_lines = limits(root)
    except ValueError as err:
        return "no limit to compare: %s" % err
    try:
        diff = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "the diff holds bytes that are no UTF-8, which the Factory holds as too_large; take them out"
    characters, lines = counted(diff, numstat)
    over = characters > SHARE * most_characters or lines > SHARE * most_lines
    return "%d of %d characters and %d of %d lines committed against origin/main as last fetched%s%s" % (
        characters, most_characters, lines, most_lines, ", and staged edits not counted" if edited else "",
        "; split it before it opens, or the Factory holds it as too_large" if over else "")


def _read(root: pathlib.Path, where: str, rel: str):
    """(the mode, the bytes) of `rel` at commit `where`, or in the index for ":", or None where no entry is that exact
    path. Raises ValueError where it is listed and cannot be read, or the index holds it unmerged."""
    if where == ":":
        listed = _text(_git(root, "ls-files", "-s", "-z", "--", rel)).split("\0")
        entries = [e for e in listed if e.partition("\t")[2] == rel]
        if not entries:
            return None
        if any(e.split(" ")[2].split("\t")[0] != "0" for e in entries):
            raise ValueError("%r is not resolved: its conflict's stages are still in the index" % rel)
        return entries[0].split(" ")[0], _git(root, "show", ":%s" % rel)
    entries = [e for e in _text(_git(root, "ls-tree", "-z", where, "--", rel)).split("\0") if e.partition("\t")[2] == rel]
    if not entries:
        return None
    return entries[0].split(" ")[0], _git(root, "show", "%s:%s" % (where, rel))


def _changed(root: pathlib.Path, *between: str) -> set:
    return set(_text(_git(root, "diff", "--name-only", "--no-renames", "-z", *between)).split("\0")) - {""}


def _renamed(root: pathlib.Path, base: str, side: str) -> set:
    """The paths a rename by `side` took from and gave to."""
    rows = _text(_git(root, "diff", "--name-status", "-z", "-M", base, side)).split("\0")
    out, at = set(), 0
    while at < len(rows) - 1:
        if rows[at][:1] in ("R", "C"):
            out |= {rows[at + 1], rows[at + 2]}
            at += 3
        else:
            at += 2
    return out


def _counts(entry) -> dict:
    """Each line of an entry's bytes, split at a newline alone so a carriage return is the line's own, and how often."""
    counts = {}
    for line in _text(entry[1]).split("\n") if entry else ():
        counts[line] = counts.get(line, 0) + 1
    return counts


def _less(more: dict, fewer: dict) -> dict:
    """The lines `more` holds beyond `fewer`, each counted as often as it is beyond, as two multisets are taken apart."""
    return {line: n - fewer.get(line, 0) for line, n in more.items() if n > fewer.get(line, 0)}


def _told(rel: str, said: str, lines: dict) -> list:
    return ["%r: %s: %s" % (rel, said, line.strip()[:WIDTH]) for line in sorted(lines)[:SHOWN]]


def merged(root: pathlib.Path = ROOT) -> list:
    """What the merge in progress, staged, or the merge commit at HEAD, lost of either side: [] when it kept both."""
    if _partial(root):
        return ["this is a partial clone, whose reads may fetch; check the merge by hand"]
    heads = pathlib.Path(root, _text(_git(root, "rev-parse", "--git-path", "MERGE_HEAD")).strip())
    if heads.is_file() and len(heads.read_text(encoding="utf-8", errors="replace").split()) != 1:
        return ["a merge of more than one head is in progress, which this does not judge"]
    try:
        theirs = _text(_git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD")).strip()
        ours, result = _text(_git(root, "rev-parse", "HEAD")).strip(), ":"
        made = ("--cached", ours)
    except ValueError:
        parents = _text(_git(root, "rev-list", "--parents", "-n", "1", "HEAD")).split()
        if len(parents) != 3:
            return ["HEAD is no merge of two parents and no merge is in progress: run git merge origin/main first"]
        result, ours, theirs = parents
        made = (ours, result)
    problems = []
    try:
        tip = _text(_git(root, "rev-parse", "-q", "--verify", BASE)).strip()
    except ValueError:
        tip = None
    if theirs != tip:
        problems.append("the merge's other side is not origin/main as last fetched; fetch, then merge it")
    base = _text(_git(root, "merge-base", ours, theirs)).strip()
    mine, main = _changed(root, base, ours), _changed(root, base, theirs)
    renames = _renamed(root, base, ours) | _renamed(root, base, theirs)
    for rel in sorted(renames):
        problems.append("%r: renamed by a side, which this does not judge; read it by hand" % rel)
    for rel in sorted((mine | main | _changed(root, *made)) - renames):
        have = _read(root, result, rel)
        if rel not in mine or rel not in main:
            side, whose = (theirs, "only main") if rel not in mine else (ours, "only the branch")
            if rel not in mine and rel not in main:
                side, whose = ours, "neither side"
            if have != _read(root, side, rel):
                problems.append("%r: %s changed it, and the merge does not hold its text as it was left" % (rel, whose))
            continue
        entries = _read(root, base, rel), _read(root, ours, rel), _read(root, theirs, rel)
        if (have is None) != (entries[1] is None and entries[2] is None):
            problems.append("%r: %s" % (rel, "both sides took it out, and the merge has it" if have else
                                        "both sides kept it, and the merge took it out"))
            continue
        was, kept, wanted, held = (_counts(entry) for entry in entries + (have,))
        problems += _told(rel, "main's line is gone, and the branch did not take it out",
                          _less(_less(wanted, held), _less(was, kept)))
        problems += _told(rel, "the branch's line is gone, and main did not take it out",
                          _less(_less(kept, held), _less(was, wanted)))
        problems += _told(rel, "a line main took out, or no side wrote, is there",
                          _less(_less(held, wanted), _less(kept, was)))
        problems += _told(rel, "a line the branch took out, or no side wrote, is there",
                          _less(_less(held, kept), _less(wanted, was)))
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
              "%d problems: put each line back, or say why one side meant to replace the other's" % len(problems))
        return 1 if problems else 0
    print("usage: python3 -m tools.desk size | merged")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
