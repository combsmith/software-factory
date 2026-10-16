"""A decision record states what is decided now; to change one, add a record that replaces it.

Each record in `docs/decisions/` that the base holds is compared with this working tree: its
Decision and its Why, word for word but for where the lines break. A change to either is refused
unless the same change sets that record's Status to name, as "replaced by" and a path in
backticks, a later record that exists. A new record is always allowed, and so is any change to
Boundaries: a row is added when the check for it is written, and that changes nothing decided.

The base is the merge base of HEAD and refs/remotes/origin/main, named in full, read as the Stop
hook reads it (`tools/hooks/rules_changed.py`): git's replacement refs, grafts and commit graph off.
CI checks out the whole history for it. With a `.git` here and no base to read, a shallow clone,
no origin, no git, the check fails: it never passes what it could not compare. With no `.git` at
all the tree is an export, which has no history, and the comparison is skipped; `verify` says so.
CI's checkout always writes `.git`, so CI cannot skip it.
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess

from tools.check_context import _sections

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "refs/remotes/origin/main"
NO_GRAFTS = "/dev/null/grafts"      # a path that cannot exist: below a file, not a directory
SECONDS = 30                        # for each git command
FOLDER = "docs/decisions"
HELD = ("Decision", "Why")
REPLACED = re.compile(r"replaced by `(%s/(\d{4})-[^`/]+\.md)`" % FOLDER)
NUMBER = re.compile(r"^(\d{4})-")


class Unreadable(Exception):
    """The base could not be read, so nothing could be compared."""


def _git(root: pathlib.Path, *args: str) -> str:
    exe = shutil.which("git")
    if exe is None:
        raise Unreadable("git is not on PATH")
    # Only this tree's .git is read: no GIT_DIR or the like from whatever runs this. Replacement refs,
    # grafts and the commit graph are off, since any of them could make the base read as the change.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_GRAFT_FILE"] = NO_GRAFTS
    try:
        done = subprocess.run([exe, "--no-replace-objects", "-c", "core.commitGraph=false", *args], cwd=str(root),
                              env=env, capture_output=True, timeout=SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        raise Unreadable("git %s did not finish" % args[0])
    if done.returncode != 0:
        raise Unreadable("git %s failed" % args[0])
    return done.stdout.decode("utf-8", "replace")


def base(root: pathlib.Path = ROOT):
    """The commit the records are compared with; None in an export, which has no `.git`. Raises Unreadable."""
    if not os.path.lexists(str(root / ".git")):
        return None
    if _git(root, "rev-parse", "--is-shallow-repository").strip() != "false":
        raise Unreadable("this clone is shallow")
    _git(root, "rev-parse", "--verify", "--quiet", BASE + "^{commit}")
    return _git(root, "merge-base", "HEAD", BASE).strip()


def described(root: pathlib.Path = ROOT) -> str:
    """What the records were compared with, for `verify` to print."""
    try:
        at = base(root)
    except Unreadable as err:
        return "unreadable (%s)" % err
    if at is None:
        return "skipped: no .git here, so this is an export with no history to compare with"
    return "compared with %s, the merge base with origin/main" % at[:12]


def _recorded(root: pathlib.Path, at: str) -> dict:
    """{path: text} of each record the base holds."""
    names = _git(root, "ls-tree", "-z", "--name-only", at, "--", FOLDER + "/").split("\0")
    return {name: _git(root, "cat-file", "blob", "%s:%s" % (at, name))
            for name in names if name.endswith(".md") and name.count("/") == FOLDER.count("/") + 1}


def _words(text: str) -> str:
    return " ".join(text.split())


def _status(text: str) -> str:
    """The Status paragraph: from the line that opens "Status:" to the first blank line."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("Status:")), None)
    if start is None:
        return ""
    end = next((i for i in range(start, len(lines)) if not lines[i].strip()), len(lines))
    return _words("\n".join(lines[start:end]))


def _not_replaced(rel: str, old: str, new: str, root: pathlib.Path) -> str:
    """Why this change does not replace the record at `rel`, or "" when it does."""
    if REPLACED.search(_status(old)):
        return "its Status named the record that replaces it before this change, so it is the rule as it was"
    named = REPLACED.search(_status(new))
    if named is None:
        return "its Status names no record that replaces it, as 'replaced by' and the path in backticks"
    if not (root / named.group(1)).is_file():
        return "its Status names %s, which does not exist" % named.group(1)
    own = NUMBER.match(rel.rsplit("/", 1)[-1])
    if own is None or named.group(2) <= own.group(1):
        return "its Status names %s, which is not a later record" % named.group(1)
    return ""


def run(root: pathlib.Path = ROOT) -> list:
    try:
        at = base(root)
        before = _recorded(root, at) if at else {}
    except Unreadable as err:
        return ["the decision records cannot be compared with the merge base of HEAD and %s (%s); fetch main's "
                "whole history (git fetch --unshallow origin, or git fetch origin main) and run again" % (BASE, err)]
    problems = []
    for rel, old in sorted(before.items()):
        path = root / rel
        if not path.is_file():
            problems.append("%s: is gone; a record is never removed or renamed, so restore it, and add a record "
                            "that replaces it" % rel)
            continue
        new = path.read_text(errors="replace")
        parts_old, parts_new = dict(_sections(old, "## ")), dict(_sections(new, "## "))
        changed = [name for name in HELD if _words(parts_old.get(name, "")) != _words(parts_new.get(name, ""))]
        why = _not_replaced(rel, old, new, root) if changed else ""
        if why:
            problems.append("%s: its %s changed, and %s; a record's Decision and Why are never edited, so restore "
                            "them, and add a record that replaces it and name that record in this one's Status"
                            % (rel, " and ".join(changed), why))
    return problems
