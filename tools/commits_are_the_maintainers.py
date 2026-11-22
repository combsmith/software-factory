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
must be this repo, never a fork (decision 0102). A merge group's payload names no opener, so this reads the pull request
its ref names, with the job's read-only token; a merge group always runs main's tool and main's list, so a pull request
retargeted to main is caught there.

And it reads the decision records the pull request adds, between BASE_SHA and HEAD_SHA in the head's own tree: at most
one, numbered by the pull request itself, its number from the payload or, on a merge group, from the queue's ref, whose
base is the entry before it. A rename adds a record too. Until the chain numbered before this rule has merged, a record
numbered in that range stands as well (decision 1121). Run with `python3 -m tools.commits_are_the_maintainers`.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

from adapters.github import Live, Unanswered, request
from tools import pr_title

ROOT = pathlib.Path(__file__).resolve().parent.parent
SECONDS = 120       # for each git command
FORMAT = "%H%x00%an%x00%ae%x00%cn%x00%ce"
QUEUED = re.compile(r"refs/heads/gh-readonly-queue/([^/]+)/pr-([1-9][0-9]*)-[0-9a-f]{40}")
RECORDS = "docs/decisions/"
RECORD = re.compile(r"docs/decisions/([0-9]{4,})-[^/]*\.md")
# The first and the last of the records numbered in order before a record took its pull request's number, both in: a
# record numbered between them stands too, until each has merged and this is taken off. The Builder may hand out more.
CHAINED = (235, 253)


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


def added(root: pathlib.Path, base: str, head: str, run=git) -> list:
    """The decision records the head adds since its merge base with `base`, a rename among them, as each file's path.
    The head must have been fetched (commits). Raises ValueError where git cannot give them."""
    listed = run(root, "diff", "--no-renames", "--diff-filter=A", "--name-only", "-z", "%s...%s" % (base, head), "--",
                 RECORDS)
    return [path for path in listed.split("\0") if path.endswith(".md") and "/" not in path[len(RECORDS):]]


def pull_number(environ) -> int:
    """The number of the event's pull request: the payload's own, or on a merge group the one its ref names. Raises
    ValueError, KeyError, TypeError or OSError where it cannot be read."""
    payload = json.loads(pathlib.Path(environ["GITHUB_EVENT_PATH"]).read_text())
    if environ.get("EVENT") == "merge_group":
        return int(QUEUED.fullmatch(payload["merge_group"]["head_ref"]).group(2))
    told = payload["pull_request"]["number"]
    if type(told) is not int or told < 1:
        raise TypeError("the pull request's number is not a number above 0")
    return told


def record_problems(root: pathlib.Path, environ, run=git) -> list:
    """Why the decision records BASE_SHA..HEAD_SHA adds are not one record at most, numbered by its pull request: nothing
    where they are (decision 1121). A path is shown quoted, as Python writes it, so a name that holds a new line is
    printed on one line, and no line of it opening '::' is read by GitHub Actions as a command."""
    base, head = environ.get("BASE_SHA"), environ.get("HEAD_SHA")
    if not base or not head or environ.get("EVENT") not in ("pull_request", "merge_group"):
        return ["BASE_SHA, HEAD_SHA and EVENT (pull_request or merge_group) must be set from the event, so the decision "
                "records the pull request adds are read"]
    try:
        found, own = added(root, base, head, run), pull_number(environ)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as err:
        return ["the decision records the pull request adds cannot be read: %r" % err]
    allowed = {"%04d" % own} | {"%04d" % chained for chained in range(CHAINED[0], CHAINED[1] + 1)}
    why = []
    if len(found) > 1:
        why.append("the pull request adds %d decision records, %s; it adds one at most"
                   % (len(found), ", ".join(map(repr, found))))
    for path in found:
        named = RECORD.fullmatch(path)
        if named is None or named.group(1) not in allowed:
            why.append("%r is a decision record the pull request adds, and a record is numbered by the pull request that "
                       "adds it, %04d" % (path, own))
    return why


def openers(root: pathlib.Path) -> dict:
    """{(login, id): what the account is}, each account that may open a pull request here, from config/hooks.json."""
    return {(o["login"], o["id"]): o["is"] for o in json.loads((root / "config" / "hooks.json").read_text())["openers"]}


def queued(payload: dict, environ, transport=None) -> tuple:
    """(the pull request the merge group's ref names, as GitHub answers for it now, why it cannot be read). The ref must
    name exactly one pull request, on the branch the group merges to; the answer must be that one, open and based there."""
    group = payload.get("merge_group")
    if not isinstance(group, dict) or "pull_request" in payload:
        return None, "merge_group_unreadable: the event is a merge group, and its payload is not a merge group's"
    named = QUEUED.fullmatch(group["head_ref"]) if isinstance(group.get("head_ref"), str) else None
    if named is None or group.get("base_ref") != "refs/heads/" + named.group(1):
        return None, "merge_group_ref_unreadable: the merge group's ref names no one pull request on its base"
    number, token = int(named.group(2)), environ.get("WORKFLOW_TOKEN")
    if not token:
        return None, "merge_group_pull_unreadable: the job's token was not given"
    try:
        answer = (transport or Live(token)).send(request("GET", "/repos/%s/pulls/%d" % (payload["repository"]["full_name"], number)))
    except Unanswered as err:
        return None, "merge_group_pull_unreadable: pull request %d was not answered: %s" % (number, type(err).__name__)
    pull = answer["body"]
    if answer["status"] != 200 or not isinstance(pull, dict) or type(pull.get("number")) is not int or pull["number"] != number:
        return None, "merge_group_pull_unreadable: pull request %d was answered %s" % (number, answer["status"])
    base = pull.get("base")
    if pull.get("state") != "open" or not isinstance(base, dict) or base.get("ref") != named.group(1):
        return None, "merge_group_pull_unreadable: pull request %d is not open on the merge group's base" % number
    if not isinstance(base.get("repo"), dict) or base["repo"].get("full_name") != payload["repository"]["full_name"]:
        return None, "merge_group_pull_unreadable: pull request %d is answered as another repo's" % number
    return pull, None


def opener(root: pathlib.Path, environ, transport=None) -> tuple:
    """(why the event's pull request may not stand on who opened it and from where, what was read where it may): the
    first is empty where it may, and the second then says what it holds. A pull request's own event carries both values;
    a merge group's carries neither, so they are read from GitHub, by the base's tool and its list (decision 0102)."""
    event = environ.get("EVENT")
    if event not in ("pull_request", "merge_group"):
        return ["EVENT (pull_request or merge_group) must be set from the event"], ""
    try:
        payload = json.loads(pathlib.Path(environ["GITHUB_EVENT_PATH"]).read_text())
        if event == "merge_group":
            pull, why = queued(payload, environ, transport)
            if why:
                return [why], ""
        else:
            pull = payload["pull_request"]
        user, head, base = pull["user"], pull["head"]["repo"], pull["base"]["repo"]
        login, head_repo, own = user["login"], head and head["full_name"], base and base["full_name"]
        allowed = openers(root)
        what = allowed.get((login, user["id"])) if type(user["id"]) is int else None
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as err:
        return ["the pull request's opener cannot be read: %r" % err], ""
    found = []
    if what is None:
        found.append("the pull request is opened by %s (id %s), and only these may open one: %s"
                     % (login, user["id"], "; ".join("%s, %s" % (who[0], is_) for who, is_ in sorted(allowed.items()))))
    if not own or head_repo != own:
        found.append("the pull request is opened from %s, and only from this repo, %s" % (head_repo, own))
    return found, "the pull request is opened from %s by %s, %s" % (own, login, what)


def opener_problems(root: pathlib.Path, environ, transport=None) -> list:
    """Why the event's pull request may not stand on who opened it and from where: nothing where it may."""
    return opener(root, environ, transport)[0]


def main(environ=os.environ, root: pathlib.Path = ROOT, transport=None) -> int:
    opened, said = opener(root, environ, transport)
    found = problems(root, environ) + opened + record_problems(root, environ)
    found += pr_title.check(environ, transport)
    for problem in found:
        print(problem)
    if not found:
        print("every commit from %s to %s names the Maintainer as its author, and as its committer where GitHub did not "
              "commit it" % (environ["BASE_SHA"][:7], environ["HEAD_SHA"][:7]))
        print(said)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
