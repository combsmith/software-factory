"""Every commit a pull request carries names the Maintainer as its author and committer, checked outside the shell.

The `commits` job of the required check runs this from a checkout of the base, never the head, as `verify` runs
`needs_passed.py`: a change cannot make its own verdict pass. It fetches the head from origin, the repo itself, and
reads each commit between BASE_SHA and HEAD_SHA. Each one's author and committer must be the identity
`config/hooks.json` names as the Maintainer; no identity is written here. The commits GitHub makes are told by their
place, never by the name they carry: on a merge group (EVENT merge_group) the head, which the queue made, is read for
its author alone, since GitHub commits it. Anything else refuses: another identity, a range that holds no commit, or a
commit list the check cannot read. The session hook `tools/hooks/identity.py` guards against the same mistake before a
commit is made, and reads words; this reads what git recorded. What git recorded is what the commit's maker wrote: a
name written to forge the Maintainer's passes here, and is left to the Maintainer's review (decision 0087).

So it reads too what GitHub wrote and the committer did not: the event's payload, at GITHUB_EVENT_PATH, where the runner
leaves it. A pull request's opener must be an account `config/hooks.json` lists, by its login and its id, and its head
must be this repo, never a fork (decision 0102). A merge group's payload names no opener: the pull request's own run of
this job read it, and neither value can change after. Run with `python3 -m tools.commits_are_the_maintainers`.
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
    """Why the commits BASE_SHA..HEAD_SHA do not all name the Maintainer: nothing where every one does."""
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
            found.append("%s is authored by %s <%s>, and every commit here names the Maintainer, %s <%s>"
                         % (sha[:7], author_name, author_email, *who))
        if (committer_name, committer_email) != who and not made_by_github:
            found.append("%s is committed by %s <%s>, and every commit here names the Maintainer, %s <%s>"
                         % (sha[:7], committer_name, committer_email, *who))
    return found


def openers(root: pathlib.Path) -> dict:
    """{(login, id): what the account is}, each account that may open a pull request here, from config/hooks.json."""
    return {(o["login"], o["id"]): o["is"] for o in json.loads((root / "config" / "hooks.json").read_text())["openers"]}


def opener(root: pathlib.Path, environ) -> tuple:
    """(why the event's pull request may not stand on who opened it and from where, what was read where it may): the
    first is empty where it may, and the second then says what it holds."""
    event = environ.get("EVENT")
    if event not in ("pull_request", "merge_group"):
        return ["EVENT (pull_request or merge_group) must be set from the event"], ""
    try:
        payload = json.loads(pathlib.Path(environ["GITHUB_EVENT_PATH"]).read_text())
        if event == "merge_group":
            if not isinstance(payload.get("merge_group"), dict) or "pull_request" in payload:
                return ["the event is a merge group, and its payload is not a merge group's"], ""
            return [], "a merge group's payload names no opener: its pull request's own run of this job read it"
        pull = payload["pull_request"]
        user, head, base = pull["user"], pull["head"]["repo"], pull["base"]["repo"]
        login, head_repo, own = user["login"], head and head["full_name"], base and base["full_name"]
        allowed = openers(root)
        what = allowed.get((login, user["id"]))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as err:
        return ["the pull request's opener cannot be read: %r" % err], ""
    found = []
    if what is None:
        found.append("the pull request is opened by %s (id %s), and only these may open one: %s"
                     % (login, user["id"], "; ".join("%s, %s" % (who[0], is_) for who, is_ in sorted(allowed.items()))))
    if not own or head_repo != own:
        found.append("the pull request is opened from %s, and only from this repo, %s" % (head_repo, own))
    return found, "the pull request is opened from %s by %s, %s" % (own, login, what)


def opener_problems(root: pathlib.Path, environ) -> list:
    """Why the event's pull request may not stand on who opened it and from where: nothing where it may."""
    return opener(root, environ)[0]


def main(environ=os.environ, root: pathlib.Path = ROOT) -> int:
    opened, said = opener(root, environ)
    found = problems(root, environ) + opened
    for problem in found:
        print(problem)
    if not found:
        print("every commit from %s to %s names the Maintainer as its author, and as its committer where GitHub did not "
              "commit it" % (environ["BASE_SHA"][:7], environ["HEAD_SHA"][:7]))
        print(said)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
