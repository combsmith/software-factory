"""What the desk runs beside the checks, for a person to read, and no check (issues 1109 and 1110): about how large the
Factory will count a branch's diff, and which lines a merge of main may have lost. Neither fails a run that CI or a hook
acts on.

`python3 -m tools.desk size` prints a note: about how many characters and lines the Factory will count the diff the
branch has committed against `origin/main` at, each against its limit in `config/defaults.json`, with a warning past
SHARE of either. It counts as `adapters/pull.py` counts a pull request's diff: each index line cut as `canonical` cuts
it, then numbered and escaped as JSON. GitHub heads its hunks a little differently, so the count is near the Factory's,
not equal to it; a binary file's index line counts some 33 characters high, and a file this clone's own attributes
mark as binary counts as one. A stale local `origin/main` errs high: the base is older than main's, and what main
merged since counts as the branch's. Edits not committed are not counted; it says so of staged ones, and how many
untracked files there are, and says so of text that is no UTF-8, which the Factory holds. `make checks` prints the note after the checks, on the
desk's run alone (`tools/verify.py --checks`): CI's legs never run it, and nothing it does changes what make checks
answers. The hooks show make checks only when a check fails, so they show the note only beside a failure.

`python3 -m tools.desk merged` lists lines a merge of `origin/main` may have lost of either side, or made up, for a
person to read each. While a merge is in progress (MERGE_HEAD is there) the merge is the index, and a path in it still
unmerged is refused; once committed, it is HEAD, which must have exactly two parents. A merge of more heads, or of two
sides with more than one merge base, or in a shallow clone, which may hide a base, is refused, since it cannot tell. A
file one side changed, or both alike, must hold that blob and mode, and a file neither side changed the base's; a blob
both left alike, whatever its mode, must be held. In a file both changed otherwise, lines are compared as counts, not in
order, so a line moved is not seen, nor one of two alike that both sides added or took out, nor a final newline. A
rename on either side is named, "renamed: not compared", and not judged, and so is a submodule on a side or in the merge
of a file both changed. A line it lists is not always wrong: where both sides changed one line, the right resolution may
be a line neither side wrote, combined by hand, and the person reading it says so. It is never wired into anything that
blocks.

Each read is git's own, with no program a repo's configuration names, no fetch and a timeout: `origin/main` is whatever
this clone last fetched.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

from adapters import pull
from harness import task

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "refs/remotes/origin/main"
SHARE = 0.95            # of a limit, past which `size` warns: the Factory's count runs a few hundred characters apart
SHOWN = 5               # the lines told of each file, at most, each cut to WIDTH
WIDTH = 60
SECONDS = 10
# The only verbs this runs: each reads this clone, and none fetches, pushes or reaches a remote; config only to get.
READS = ("cat-file", "config", "diff", "diff-index", "ls-files", "ls-tree", "merge-base", "rev-list", "rev-parse")
GETS = ("--get", "--get-regexp")
# Each read is git's own: no program a repo's configuration names runs, no object is fetched, no lock is taken; an
# external diff is set to none, so a diff that would run one fails rather than runs it.
SAFE = ("--no-replace-objects", "--literal-pathspecs", "-c", "core.commitGraph=false", "-c", "core.fsmonitor=false",
        "-c", "diff.external=", "-c", "diff.ignoreSubmodules=none", "-c", "core.quotePath=true",
        "-c", "diff.suppressBlankEmpty=false", "-c", "diff.submodule=short")
# A diff as GitHub writes one: no colour, no external diff, no textconv, the whole tree, renames found, a/ and b/; its
# index lines whole, for `canonical` to cut as the Factory's are cut, however long this clone abbreviates an id.
FORM = ("--no-color", "--no-ext-diff", "--no-textconv", "--no-relative", "--submodule=short", "--diff-algorithm=myers",
        "-M")
DIFF = FORM + ("--src-prefix=a/", "--dst-prefix=b/", "-U3", "--inter-hunk-context=0", "--full-index")
MOST = 10 ** 9          # a limit past this is no limit this note can compare with
# Each key that makes a clone one whose reads may fetch, and the values that say it does not: a promisor remote that
# git reads as false. A partial clone's extension names a remote, and a partial clone filter is set only on one.
PROMISORS = (("extensions.partialclone", ()), (r"^remote\..*\.partialclonefilter$", ()),
             (r"^remote\..*\.promisor$", ("false",)))


class Unset(ValueError):
    """git config found no such key: its exit of 1, apart from every other failure."""


def _git(root: pathlib.Path, *args: str) -> bytes:
    """What git prints for `args` in `root` alone, no GIT_ variable of whatever runs this read. Raises ValueError."""
    if args[0] not in READS or (args[0] == "config" and args[1:2] not in [(get,) for get in GETS]) or any(
            arg.startswith("--output") for arg in args):
        raise ValueError("git %s is no read" % args[0])
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0",
               LC_ALL="C", LANGUAGE="C")      # git's shortstat in English, whatever the desk's locale
    try:
        done = subprocess.run(["git", *SAFE, *args], cwd=str(root), env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("git %s did not finish" % args[0]) from None
    if done.returncode == 1 and args[0] == "config":
        raise Unset("git config has no %s" % args[-1])
    if done.returncode != 0:
        raise ValueError("git %s failed" % args[0])
    return done.stdout


def _text(data: bytes) -> str:
    return data.decode("utf-8", "surrogateescape")


def _rows(data: bytes) -> list:
    return [row for row in _text(data).split("\0") if row]


def limits(root: pathlib.Path) -> tuple:
    """(the most characters, the most lines) a diff may be counted at, from `config/defaults.json` as BASE holds it,
    which is what the Factory reads, not this tree's or this branch's. Raises ValueError."""
    try:
        said = json.loads(_git(root, "cat-file", "blob", BASE + ":config/defaults.json").decode("utf-8"))["limits"]
        most = said["max_diff_characters"], said["max_diff_lines"]
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("config/defaults.json's limits cannot be read") from None
    if not all(type(n) is int and 0 < n < MOST for n in most):
        raise ValueError("config/defaults.json's limits cannot be read")
    return most


def counted(diff: str, shortstat: str) -> tuple:
    """(about the characters the Factory counts `diff` at, the lines it adds and removes, from git's `shortstat`)."""
    return task.carried(task.numbered(pull.canonical(diff))), _lines(shortstat)


def _lines(shortstat: str) -> int:
    """The lines git's `shortstat` adds and removes, `N insertions(+)` and `N deletions(-)`, read by its commas and
    words, with no pattern that could backtrack (Sonar)."""
    lines = 0
    for part in shortstat.split(","):
        words = part.split()
        if len(words) == 2 and words[0].isdigit() and words[1].startswith(("insertion", "deletion")):
            lines += int(words[0])
    return lines


def _partial(root: pathlib.Path) -> bool:
    """Whether this clone may fetch a missing object as it reads one: a partial clone's reads can, and so can a promisor
    remote's on a git older than GIT_NO_LAZY_FETCH. Where git says nothing (an exit of 1) it may not; where it cannot
    say, a timeout or a value no boolean among them, it may."""
    for key, off in PROMISORS:
        try:
            said = _text(_git(root, "config", "--get-regexp", *(("--type=bool",) if off else ()), key)).splitlines()
        except Unset:
            continue
        except ValueError:
            return True
        if any(line.split(" ", 1)[1:] not in [[value] for value in off] for line in said):
            return True
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
        raw = _git(root, "diff", *DIFF, base, "HEAD", "--")
        shortstat = _text(_git(root, "diff", "--shortstat", *FORM, base, "HEAD", "--"))
        staged = bool(_rows(_git(root, "diff-index", "--cached", "--name-only", "-z", "HEAD", "--")))
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
    characters, lines = counted(diff, shortstat)
    over = characters > SHARE * most_characters or lines > SHARE * most_lines
    left = (["staged edits"] if staged else []) + (
        ["%d untracked file%s" % (untracked, "" if untracked == 1 else "s")] if untracked else [])
    return "about %d of %d characters and %d of %d lines committed against origin/main as last fetched%s%s" % (
        characters, most_characters, lines, most_lines, ", %s not counted" % " and ".join(left) if left else "",
        "; split it before it opens, or the Factory holds it as too_large" if over else "")


def _entry(root: pathlib.Path, where: str, rel: str):
    """(the mode, the blob id) of `rel` at commit `where`, or in the index for ":", or None where no entry is that
    exact path. Raises ValueError where it cannot be read."""
    if where == ":":       # mode, id, stage, then a tab and the path; a merge with any stage left is refused first
        heads = [row.partition("\t")[0].split(" ") for row in _rows(_git(root, "ls-files", "-s", "-z", "--", rel))
                 if row.partition("\t")[2] == rel]
        return (heads[0][0], heads[0][1]) if heads else None
    heads = [row.partition("\t")[0].split(" ") for row in _rows(_git(root, "ls-tree", "-z", where, "--", rel))
             if row.partition("\t")[2] == rel and " tree " not in row.partition("\t")[0]]     # mode, type, id; no folder
    return (heads[0][0], heads[0][2]) if heads else None


def _changed(root: pathlib.Path, *between: str) -> set:
    return set(_rows(_git(root, "diff", "--name-only", "--no-renames", "--ignore-submodules=none", "-z", *between)))


def _renamed(root: pathlib.Path, base: str, side: str) -> set:
    """The paths a rename by `side` took from and gave to, found as `size` finds them."""
    rows = _text(_git(root, "diff", "--name-status", "-z", "-M", base, side)).split("\0")
    out, at = set(), 0
    while at < len(rows) - 1:
        if rows[at][:1] in ("R", "C"):
            out |= {rows[at + 1], rows[at + 2]}
            at += 3
        else:
            at += 2
    return out


def _counts(root: pathlib.Path, entry) -> dict:
    """Each line of an entry's blob, split at a newline alone so a carriage return is the line's own, and how often;
    a blob that holds a NUL byte, binary, is counted as {None: 1}. A final newline ends a line, and begins none."""
    blob = _git(root, "cat-file", "blob", entry[1]) if entry else b""
    if b"\0" in blob:
        return {None: 1}
    counts, lines = {}, _text(blob).split("\n")
    for line in lines[:-1] if lines[-1] == "" else lines:
        counts[line] = counts.get(line, 0) + 1
    return counts


def _less(more: dict, fewer: dict) -> dict:
    """The lines `more` holds beyond `fewer`, each counted as often as it is beyond, as two multisets are taken apart."""
    return {line: n - fewer.get(line, 0) for line, n in more.items() if n > fewer.get(line, 0)}


def _told(rel: str, said: str, lines: dict) -> list:
    """SHOWN of `lines` at most, each escaped as a path is, with how often it is gone, and how many more there are."""
    told = ["%r: %s: %r%s" % (rel, said, line[:WIDTH], " (%d times)" % lines[line] if lines[line] > 1 else "")
            for line in sorted(lines)[:SHOWN]]
    more = sum(lines.values()) - sum(lines[line] for line in sorted(lines)[:SHOWN])
    return told + (["%r: %s: and %d more" % (rel, said, more)] if more else [])


def _sides(root: pathlib.Path):
    """(the merge's result, ":" for the index, its first side, its other side, the diff between the first and the
    result), or a list of what makes it one that cannot be told."""
    heads = pathlib.Path(root, _text(_git(root, "rev-parse", "--git-path", "MERGE_HEAD")).strip())
    if heads.is_file():
        named = heads.read_text(encoding="utf-8", errors="replace").split()
        if len(named) != 1:
            return ["cannot tell: a merge of %d heads into HEAD is in progress, not of one" % len(named)]
        if _rows(_git(root, "ls-files", "-u", "-z")):
            return ["cannot tell: the index holds paths still unmerged; resolve and stage each, then read it again"]
        ours = _text(_git(root, "rev-parse", "HEAD")).strip()
        theirs = _text(_git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD^{commit}")).strip()
        return ":", ours, theirs, ("--cached", ours)
    parents = _text(_git(root, "rev-list", "--parents", "-n", "1", "HEAD")).split()
    if len(parents) == 2:
        return ["HEAD is no merge and no merge is in progress: run git merge origin/main first"]
    if len(parents) != 3:
        return ["cannot tell: HEAD has %d parents, not two" % (len(parents) - 1)]
    result, ours, theirs = parents
    return result, ours, theirs, (ours, result)


def merged(root: pathlib.Path = ROOT) -> list:
    """The lines to read of the merge in progress, staged, or the merge commit at HEAD: what it may have lost of either
    side or made up, and what it cannot tell; [] when it kept both. Raises ValueError where git cannot read it."""
    if _partial(root):
        return ["cannot tell: this is a partial clone, whose reads may fetch; read the merge by hand"]
    if _text(_git(root, "rev-parse", "--is-shallow-repository")).strip() != "false":
        return ["cannot tell: this is a shallow clone, whose history may hide a merge base; read the merge by hand"]
    sides = _sides(root)
    if isinstance(sides, list):
        return sides
    result, ours, theirs, made = sides
    bases = _text(_git(root, "merge-base", "--all", ours, theirs)).split()
    if len(bases) != 1:
        return ["cannot tell: the two sides have %d merge bases, not one" % len(bases)]
    base, problems = bases[0], []
    try:
        tip = _text(_git(root, "rev-parse", "-q", "--verify", BASE)).strip()
    except ValueError:
        tip = None
    if theirs != tip:
        problems.append("the merge's other side is not origin/main as last fetched; fetch, then merge it")
    mine, main = _changed(root, base, ours), _changed(root, base, theirs)
    renames = _renamed(root, base, ours) | _renamed(root, base, theirs)
    problems += ["%r: renamed: not compared" % rel for rel in sorted(renames)]
    for rel in sorted((mine | main | _changed(root, *made)) - renames):
        have = _entry(root, result, rel)
        if rel not in mine or rel not in main:
            side, whose = (theirs, "only main") if rel not in mine else (ours, "only the branch")
            if rel not in mine and rel not in main:
                side, whose = base, "neither side"
            if have != _entry(root, side, rel):
                problems.append("%r: %s changed it, and the merge does not hold its blob and mode as left" % (rel, whose))
            continue
        entries = _entry(root, base, rel), _entry(root, ours, rel), _entry(root, theirs, rel)
        if entries[0] is not None and (entries[1] is None) != (entries[2] is None):
            problems.append("%r: %s took it out and the other side changed it, and the merge %s: read which was meant"
                            % (rel, "the branch" if entries[1] is None else "main", "has it" if have else "took it out"))
            continue
        if (have is None) != (entries[1] is None and entries[2] is None):
            problems.append("%r: %s" % (rel, "both sides took it out, and the merge has it" if have else
                                        "both sides kept it, and the merge took it out"))
            continue
        if entries[1] == entries[2]:
            if have != entries[1]:
                problems.append("%r: both sides left it alike, and the merge does not hold that blob and mode" % rel)
            continue
        if any(entry and entry[0] == "160000" for entry in entries + (have,)):
            problems.append("%r: a submodule, on a side or in the merge: not compared" % rel)
            continue
        problems += ["%r: %s changed its mode, and the merge does not hold it" % (rel, whose)
                     for side, whose in ((entries[1], "the branch"), (entries[2], "main"))
                     if side and have and side[0] != (entries[0] or ("",))[0] and have[0] != side[0]]
        if all(entries) and have and entries[0][0] == entries[1][0] == entries[2][0] != have[0]:
            problems.append("%r: both sides left its mode as it was, and the merge does not hold it" % rel)
        if entries[1][1] == entries[2][1]:
            if have[1] != entries[1][1]:
                problems.append("%r: both sides left its blob alike, and the merge does not hold it" % rel)
            continue
        was, kept, wanted, held = (_counts(root, entry) for entry in entries + (have,))
        if any(None in counts for counts in (was, kept, wanted, held)):
            problems.append("%r: binary: lines not compared" % rel)
            continue
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
        except (ValueError, OSError) as err:
            problems = ["cannot tell: the merge cannot be read: %s" % err]
        for problem in problems:
            print(problem)
        print("the merge keeps every line of both sides" if not problems else
              "%d to read: read each, then put a line back, or say why a side meant to replace the other's, or why a "
              "line both changed is rightly one neither wrote" % len(problems))
        return 1 if problems else 0
    print("usage: python3 -m tools.desk size | merged")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
