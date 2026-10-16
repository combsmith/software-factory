"""A decision record states what is decided now; to change one, add a record that replaces it.

Each record in `docs/decisions/` that the base holds is compared with this working tree, all of it
but two parts. Its Status may change once, in the change that replaces it, and only to "replaced
by" and the path, in backticks, of the record that replaces it: a record new in that change, whose
own Status says it replaces this one. After that the Status is fixed too. Its Boundaries may gain
rows, and a row's Check cell may change, since a row is added when the check for it is written and
that changes nothing decided; no row is taken away and no Boundary cell is changed. Everything
else, the title, the Decision and the Why among it, stays line for line as it was. A new record is
always allowed. In every record there is one `Status:` line, the first after the title, and no
HTML comment, which hides text from a reader; and nothing in `docs/decisions/` is a link.

The base is the merge base of HEAD and refs/remotes/origin/main, named in full, read as the Stop
hook reads it (`tools/hooks/rules_changed.py`): git's replacement refs, grafts and commit graph off.
CI checks out the whole history for it. With a `.git` here, a directory or a worktree's file, and no
base to read, a shallow clone, no origin, no git, the check fails: it never passes what it could not
compare. With no `.git` at all the tree is an export, which has no history, and the comparison is
skipped; `verify` says so. In GitHub Actions a missing `.git` fails, so CI cannot skip it.
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess

from tools.check_context import _cells

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "refs/remotes/origin/main"
NO_GRAFTS = "/dev/null/grafts"      # a path that cannot exist: below a file, not a directory
SECONDS = 30                        # for each git command
FOLDER = "docs/decisions"
PATH = r"`(%s/(\d{4})-[^`/\s]+\.md)`" % FOLDER
# How decision 0012 says it was replaced, from the start of its Status: the path, then a comma, a stop or the end.
REPLACED = re.compile(r"^Status: replaced by %s(?=[,.]|$)" % PATH)
# How decision 0015 says what it replaces: one record, or a list of them, straight after its own Status.
REPLACES = re.compile(r"^Status: accepted\. Replaces (`[^`]+`(?:(?:, and |, | and )`[^`]+`)*)")
NUMBER = re.compile(r"^(\d{4})-")
BOUNDARIES = "## Boundaries"


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
        if os.environ.get("GITHUB_ACTIONS"):
            raise Unreadable("there is no .git, and in GitHub Actions the checkout always writes one")
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


def _words(lines: list) -> str:
    return " ".join(" ".join(lines).split())


def parse(text: str):
    """(status, rest, rows) of a record, or a sentence saying why it cannot be read as one.

    `status` is the Status paragraph, its words joined by single spaces. `rows` is the Boundary
    cells, all but the Check, of each row of the first table under Boundaries. `rest` is every other
    line, as it stands but for space at its end, with the blank lines at the end of the file left out.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    if "<!--" in text:
        return "it holds an HTML comment, which hides text from a reader"
    starts = [i for i, line in enumerate(lines) if line.startswith("Status:")]
    first = next((i for i in range(1, len(lines)) if lines[i]), None)
    if len(starts) != 1 or starts[0] != first:
        return "it must have one line that opens 'Status:', the first after the title"
    end = next((i for i in range(first, len(lines)) if not lines[i]), len(lines))
    heads = [i for i, line in enumerate(lines) if line == BOUNDARIES]
    if len(heads) != 1 or heads[0] < end:
        return "it must have one line '%s', after its Status" % BOUNDARIES
    region = lines[heads[0]:]
    top = next((i for i, line in enumerate(region) if line.startswith("|")), len(region))
    bottom = next((i for i in range(top, len(region)) if not region[i].startswith("|")), len(region))
    body = range(top + 2, bottom)       # the first table's rows, below its header and the line under it
    rows = [tuple(" ".join(cell.split()) for cell in _cells(region[i])[:-1]) for i in body]
    rest = lines[:first] + lines[end:heads[0]] + [line for i, line in enumerate(region) if i not in body]
    while rest and not rest[-1]:
        rest.pop()
    return _words(lines[first:end]), rest, rows


def _status(rel: str, old: str, new: str, before: dict, root: pathlib.Path) -> str:
    """Why the Status at `rel` may not change from `old` to `new`, or "" when it may."""
    if new == old:
        return ""
    if REPLACED.match(old):
        return "its Status named the record that replaces it, and is fixed from then on"
    named = REPLACED.match(new)
    if named is None:
        return ("its Status changes only to say what replaces it: 'Status: replaced by' and the path in backticks, "
                "as decision 0012's does")
    path, number = named.group(1), named.group(2)
    own = NUMBER.match(rel.rsplit("/", 1)[-1])
    if path in before:
        return "it names %s, which is not new in this change; the record that replaces it is" % path
    target = root / path
    if target.is_symlink() or not target.is_file():
        return "it names %s, which does not exist" % path
    if own is None or number <= own.group(1):
        return "it names %s, which is not a later record" % path
    said = parse(target.read_text(encoding="utf-8", errors="replace"))
    listed = REPLACES.match(said[0]) if isinstance(said, tuple) else None
    if listed is None or rel not in re.findall(r"`([^`]+)`", listed.group(1)):
        return "%s's Status does not say it replaces this one: 'Status: accepted. Replaces' and its path" % path
    return ""


def _boundaries(old: list, new: list) -> str:
    """Why the Boundaries rows may not change from `old` to `new`, or "" when they may."""
    left = list(new)
    for row in old:
        if row not in left:
            return ("the row '%s' is gone or its Boundary changed; a row is only added, or its Check changed"
                    % " | ".join(row))
        left.remove(row)
    return ""


def _linked(root: pathlib.Path) -> list:
    folder = root / FOLDER
    if folder.is_symlink():
        return ["%s: is a link; the records are files here, which this check reads" % FOLDER]
    entries = sorted(folder.iterdir()) if folder.is_dir() else []
    return ["%s: is a link; a record is a file, which this check reads where it stands" % p.relative_to(root).as_posix()
            for p in entries if p.is_symlink()]


def run(root: pathlib.Path = ROOT) -> list:
    problems = _linked(root)
    folder = root / FOLDER
    current = {}
    for path in sorted(folder.glob("*.md")) if folder.is_dir() and not folder.is_symlink() else []:
        rel = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.is_file():
            continue
        try:
            current[rel] = parse(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            current[rel] = "it is not UTF-8"
        if isinstance(current[rel], str):
            problems.append("%s: %s" % (rel, current[rel]))
    try:
        at = base(root)
        before = _recorded(root, at) if at else {}
    except Unreadable as err:
        return problems + ["the decision records cannot be compared with the merge base of HEAD and %s (%s); fetch "
                           "main's whole history (git fetch --unshallow origin, or git fetch origin main) and run "
                           "again" % (BASE, err)]
    for rel, text in sorted(before.items()):
        old, new = parse(text), current.get(rel)
        if new is None:
            problems.append("%s: is gone; a record is never removed or renamed, so restore it, and add a record "
                            "that replaces it" % rel)
            continue
        if isinstance(new, str):
            continue        # said above
        if isinstance(old, str):
            problems.append("%s: the base's copy cannot be read as a record (%s), so it cannot be compared" % (rel, old))
            continue
        why = [w for w in (_status(rel, old[0], new[0], before, root),
                           "its title, Decision or Why changed" if old[1] != new[1] else "",
                           _boundaries(old[2], new[2])) if w]
        if why:
            problems.append("%s: %s; a record is never edited, only replaced: restore it, add a record that replaces "
                            "it, and set this one's Status to 'replaced by' and that record's path" % (rel, "; ".join(why)))
    return problems
