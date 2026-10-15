"""Stop: list for the person every protected path and Kernel module the branch changes.

The hook that asks before an edit (protected.py) reads a command's words, and a command can be
spelt so that it does not see the path it writes. This hook reads the state instead: what differs
from the merge base of HEAD and origin/main, in the branch's commits, the index and the working
tree, and what git does not track yet. It refuses nothing. It shows the list, since these are the
Factory's own rules and the Maintainer decides them, and says so when it cannot be made. A file git
ignores is not listed. Run as `python3 -I` on this file; see after_edit.py.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))
from tools.hooks import make, protected  # noqa: E402

TIMEOUT = 20    # seconds for each git command; the settings give the hook 60
SHOWN = 20      # paths put in front of the person
BASE = "origin/main"


def _git(where: pathlib.Path, env: dict, args: list) -> str:
    exe = shutil.which("git", path=env.get("PATH", os.defpath))
    if exe is None:
        raise protected.Unreadable("git is not on PATH")
    try:
        done = subprocess.run([exe] + args, cwd=str(where), env=env, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        raise protected.Unreadable("git %s did not finish" % args[0])
    if done.returncode != 0:
        raise protected.Unreadable("git %s failed" % args[0])
    return done.stdout


def changed(where: pathlib.Path, env: dict) -> list:
    """Every path that differs from the merge base with origin/main, committed, staged, in the working tree or new."""
    base = _git(where, env, ["merge-base", "HEAD", BASE]).strip()
    found = set()
    for args in (["diff", "--name-only", "--no-renames", "-z", base, "--"],
                 ["diff", "--cached", "--name-only", "--no-renames", "-z", base, "--"],
                 ["ls-files", "--others", "--exclude-standard", "-z"]):
        found |= set(filter(None, _git(where, env, args).split("\0")))
    return sorted(found)


def respond(payload: dict, env: dict) -> tuple:
    """(exit code, stdout, stderr) for this stop: always 0, with the list, if any, as a message to the person."""
    project = make.project(env)
    where = make.tree(project, payload.get("cwd")) or project
    try:
        found = protected.listed(protected.load(), changed(where, env))
    except protected.Unreadable as err:
        told = ("The protected paths changed on this branch could not be listed (%s). They are the Factory's own "
                "rules: compare the branch with %s before it merges." % (err, BASE))
        return 0, json.dumps({"systemMessage": told}) + "\n", ""
    if not found:
        return 0, "", ""
    lines = ["- %s: %s" % pair for pair in found[:SHOWN]]
    if len(found) > SHOWN:
        lines.append("- and %d more" % (len(found) - SHOWN))
    told = ("This branch changes the Factory's own rules, against its merge base with %s. They are the Maintainer's "
            "to decide; read each before it merges:\n%s" % (BASE, "\n".join(lines)))
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
