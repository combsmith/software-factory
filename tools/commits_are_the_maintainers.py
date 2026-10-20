"""Every commit a pull request carries is the Maintainer's, checked outside the shell.

The `commits` job of the required check runs this from a checkout of the base, never the head, as `verify` runs
`needs_passed.py`: a change cannot make its own verdict pass. It fetches the head from origin, the repo itself, and
reads each commit between BASE_SHA and HEAD_SHA. Each one's author and committer must be the identity
`config/hooks.json` names as the Maintainer; no identity is written here. The commits GitHub makes are told by their
place, never by the name they carry: on a merge group (EVENT merge_group) the head, which the queue made, is read for
its author alone, since GitHub commits it. Anything else refuses: another identity, a range that holds no commit, or a
commit list the check cannot read. The session hook `tools/hooks/identity.py` guards against the same mistake before a
commit is made, and reads words; this reads what git recorded. Run with `python3 -m tools.commits_are_the_maintainers`.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SECONDS = 120       # for each git command
FORMAT = "%H%x00%an%x00%ae%x00%cn%x00%ce"


def git(root: pathlib.Path, *args: str) -> str:
    """What git prints for `args` in `root`; raises ValueError where it fails or takes too long."""
    try:
        done = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=SECONDS)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise ValueError("git %s could not run: %s" % (args[0], err)) from None
    if done.returncode:
        raise ValueError("git %s failed: %s" % (args[0], done.stderr.strip() or done.stdout.strip()))
    return done.stdout


def maintainer(root: pathlib.Path) -> tuple:
    """(name, email) of the Maintainer, read from config/hooks.json."""
    who = json.loads((root / "config" / "hooks.json").read_text())["maintainer"]
    return who["name"], who["email"]


def commits(root: pathlib.Path, base: str, head: str, run=git) -> list:
    """Each commit after `base` up to `head`, oldest first, as (sha, author name, author email, committer name,
    committer email), the head fetched from origin first. Raises ValueError where git cannot give them."""
    run(root, "fetch", "--no-tags", "origin", head)
    found = []
    for line in run(root, "log", "--reverse", "--format=" + FORMAT, "%s..%s" % (base, head)).splitlines():
        parts = line.split("\0")
        if len(parts) != 5 or not all(parts):
            raise ValueError("a commit's line cannot be read: %r" % line[:80])
        found.append(tuple(parts))
    return found


def problems(root: pathlib.Path, environ, run=git) -> list:
    """Why the commits BASE_SHA..HEAD_SHA are not all the Maintainer's: nothing where every one is."""
    base, head, event = (environ.get(name) for name in ("BASE_SHA", "HEAD_SHA", "EVENT"))
    if not base or not head or event not in ("pull_request", "merge_group"):
        return ["BASE_SHA, HEAD_SHA and EVENT (pull_request or merge_group) must be set from the event"]
    try:
        who, read = maintainer(root), commits(root, base, head, run)
    except (OSError, ValueError, KeyError, TypeError) as err:
        return ["the commits cannot be read: %s" % err]
    if not read:
        return ["no commit lies between %s and %s; a pull request carries at least one" % (base[:7], head[:7])]
    found = []
    for sha, author_name, author_email, committer_name, committer_email in read:
        made_by_github = event == "merge_group" and sha == read[-1][0]     # the queue's own commit: its head
        if (author_name, author_email) != who:
            found.append("%s is authored by %s <%s>, and every commit here is the Maintainer's, %s <%s>"
                         % (sha[:7], author_name, author_email, *who))
        if (committer_name, committer_email) != who and not made_by_github:
            found.append("%s is committed by %s <%s>, and every commit here is the Maintainer's, %s <%s>"
                         % (sha[:7], committer_name, committer_email, *who))
    return found


def main(environ=os.environ, root: pathlib.Path = ROOT) -> int:
    found = problems(root, environ)
    for problem in found:
        print(problem)
    if not found:
        print("every commit from %s to %s is the Maintainer's" % (environ["BASE_SHA"][:7], environ["HEAD_SHA"][:7]))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
