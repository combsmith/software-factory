"""Stop: list for the person every protected or reported path the branch changes.

The hook that asks before an edit (protected.py) reads a command's words, and a command can be
spelt so that it does not see the path it writes. This hook reads the state instead: what differs
from the merge base of HEAD and refs/remotes/origin/main, named in full so that a tag or a branch
called origin/main cannot stand in for it, in the branch's commits, the index and the working tree,
and what git does not track yet, with git's replacement refs, grafts and commit graph disabled. It
refuses nothing. It shows the list, since these are the Factory's own rules and the Maintainer
decides them, and says so when it cannot be made: whatever goes wrong, within its own deadline. A
file name is shown escaped, never raw. A file git ignores is not listed. Run as `python3 -I` on this
file; see after_edit.py.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))
from tools.hooks import make, protected  # noqa: E402

DEADLINE = 40   # seconds for every git command together; the settings give the hook 60
BASE = "refs/remotes/origin/main"
NO_GRAFTS = "/dev/null/grafts"      # a path that cannot exist: below a file, not a directory


def _git(where: pathlib.Path, env: dict, args: list, until: float) -> str:
    """git's output, its bytes read as names: what is not UTF-8 is kept, escaped, not lost."""
    exe = shutil.which("git", path=env.get("PATH", os.defpath))
    if exe is None:
        raise protected.Unreadable("git is not on PATH")
    # Replacement refs, grafts and the commit graph are off: an object under refs/replace/, a line in info/grafts or a
    # commit-graph file could make the base read as a commit that already holds the branch's change.
    env = dict(env, GIT_GRAFT_FILE=NO_GRAFTS)
    try:        # past the deadline, a timeout of zero or less ends the command at once
        done = subprocess.run([exe, "--no-replace-objects", "-c", "core.commitGraph=false"] + args, cwd=str(where),
                              env=env, capture_output=True, timeout=until - time.monotonic())
    except (OSError, subprocess.TimeoutExpired):
        raise protected.Unreadable("git %s did not finish" % args[0])
    if done.returncode != 0:
        raise protected.Unreadable("git %s failed" % args[0])
    return done.stdout.decode("utf-8", "surrogateescape")


def changed(where: pathlib.Path, env: dict, seconds: float = DEADLINE) -> list:
    """Every path that differs from the merge base with origin/main, committed, staged, in the working tree or new."""
    until = time.monotonic() + seconds
    base = _git(where, env, ["merge-base", "HEAD", BASE], until).strip()
    found = set()
    for args in (["diff", "--name-only", "--no-renames", "-z", base, "--"],
                 ["diff", "--cached", "--name-only", "--no-renames", "-z", base, "--"],
                 ["ls-files", "--others", "--exclude-standard", "-z"]):
        found |= set(filter(None, _git(where, env, args, until).split("\0")))
    return sorted(found)


def shown(name: str) -> str:
    """A file name as the person may read it: as it is when every character prints, else escaped."""
    return name if name.isprintable() else repr(name)


def respond(payload: dict, env: dict, seconds: float = DEADLINE) -> tuple:
    """(exit code, stdout, stderr) for this stop: always 0, with the list, if any, as a message to the person."""
    try:
        project = make.project(env)
        where = make.tree(project, payload.get("cwd")) or project
        found = protected.listed(protected.load(), changed(where, env, seconds))
    except protected.Unreadable as err:
        found, why = None, str(err)
    except Exception as err:    # whatever goes wrong, the person is told the list was not made
        found, why = None, "the check failed (%s)" % type(err).__name__
    if found is None:
        told = ("The protected paths changed on this branch could not be listed (%s). They are the Factory's own "
                "rules: compare the branch with origin/main before it merges." % why)
        return 0, json.dumps({"systemMessage": told}) + "\n", ""
    if not found:
        return 0, "", ""
    lines = ["- %s: %s" % (shown(path), what) for path, what in found]     # every one, so each is read
    told = ("This branch changes the Factory's own rules, against its merge base with origin/main. They are the "
            "Maintainer's to decide; read each before it merges:\n%s" % "\n".join(lines))
    return 0, json.dumps({"systemMessage": told}) + "\n", ""


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    code, out, err = respond(payload if isinstance(payload, dict) else {}, dict(os.environ))
    sys.stdout.write(out)
    sys.stderr.write(err)
    return code


if __name__ == "__main__":
    sys.exit(main())
