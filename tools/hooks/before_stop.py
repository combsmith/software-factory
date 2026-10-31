"""Stop: a session is sent back once while `make checks` fails on work it has not pushed.

At the next stop it ends and the person is told: a hook that sent it back for ever would cycle with
no bound and no person. With nothing changed and nothing unpushed there is nothing to verify, so a
turn spent answering questions costs nothing. Run as `python3 -I` on this file; see after_edit.py.

It runs the checks alone. The tests are CI's, and a builder's own `make verify`: they outgrew any time
a hook can spend (issue 438). A run it cannot finish is not started (issue 344): each run that ends,
or runs out of the hook's time, is written down in the tree's git directory, and while the last one
there ran out of time, within RETRY, the session is told so and ends; CI runs the checks as before.
A run that did not finish found nothing, so it sends no session back. A run the hook was told to end
is not written down. Hooks are helpers; only CI enforces.
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
from tools.hooks import make  # noqa: E402

TIMEOUT = 580       # seconds; the settings give the hook 600
TOLD = 15           # lines of the failure put in front of the person
RETRY = 3600        # seconds after a run that did not finish before one is started again
RECORD = "sf-stop-checks.json"   # in the tree's git directory: the last run's start and whether it finished in time


def _git(where: pathlib.Path, env: dict, args: list):
    exe = shutil.which("git", path=env.get("PATH", os.defpath))
    if exe is None:
        return None
    try:
        done = subprocess.run([exe] + args, cwd=str(where), env=env, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def nothing_to_verify(where: pathlib.Path, env: dict) -> bool:
    """No change in the working tree, and no commit beyond the upstream, or else origin/main. Unreadable is not nothing."""
    status = _git(where, env, ["status", "--porcelain"])
    if status is None or status.strip():
        return False
    for base in ("@{upstream}", "origin/main"):
        ahead = _git(where, env, ["rev-list", "--count", "--end-of-options", base + "..HEAD"])
        if ahead is not None:
            return ahead.strip() == "0"
    return False


def record_of(where: pathlib.Path, env: dict):
    """The file the last run in `where` is written down in, in its git directory; None where that cannot be read."""
    found = _git(where, env, ["rev-parse", "--absolute-git-dir"])
    path = pathlib.Path(found.strip()) if found and found.strip() else None
    return path / RECORD if path is not None and path.is_dir() else None


def unfinished(record, now: float):
    """How long ago a run was started that did not finish, where that is within RETRY; else None."""
    try:
        last = json.loads(record.read_text())
    except (AttributeError, OSError, ValueError):
        return None
    started = last.get("started") if isinstance(last, dict) else None
    if not isinstance(started, (int, float)) or isinstance(started, bool) or last.get("finished") is not False:
        return None
    try:
        ago = now - started
    except OverflowError:
        return None
    return ago if 0 <= ago < RETRY else None


def note(record, started: float, finished: bool) -> None:
    if record is not None:
        try:
            record.write_text(json.dumps({"started": started, "finished": finished}) + "\n")
        except OSError:
            pass


def respond(payload: dict, env: dict, clock=time.time) -> tuple:
    """(exit code, stdout, stderr) for this stop."""
    asked = time.monotonic()
    base = make.project(env)
    where = make.tree(base, payload.get("cwd")) or base
    if nothing_to_verify(where, env):
        return 0, "", ""
    record, now = record_of(where, env), clock()
    ago = unfinished(record, now)
    if ago is not None:
        told = ("`make checks` was not started in %s: the last one there, %d seconds ago, did not finish in the %d "
                "seconds the hook has. CI runs it. To have it run at the next stop, delete %s." % (where, ago, TIMEOUT,
                                                                                                record))
        return 0, json.dumps({"systemMessage": told}) + "\n", ""
    budget = max(1, int(TIMEOUT - (time.monotonic() - asked)))
    passed, said = make.make("checks", where, env, budget)
    unfinished_now = said.startswith(make.UNFINISHED % ("checks", budget, where))
    note(record, now, not unfinished_now)
    if passed:
        return 0, "", ""
    if unfinished_now:
        return 0, json.dumps({"systemMessage": "%s They found nothing; CI runs them." % said}) + "\n", ""
    if make.lacks("checks", where, env):
        told = "%s has no `make checks` target, so the checks did not run before this stop." % where
        return 0, json.dumps({"systemMessage": told}) + "\n", ""
    if payload.get("stop_hook_active") is True:
        told = ("`make checks` still fails in %s. The session was sent back once to make it pass, and ends now; "
                "what happens next is yours.\n%s" % (where, make.tail(said, TOLD)))
        return 0, json.dumps({"systemMessage": told}) + "\n", ""
    return 2, "", "`make checks` fails in %s:\n%s\n" % (where, said)


def main() -> int:
    code, out, err = respond(json.loads(sys.stdin.read() or "{}"), dict(os.environ))
    sys.stdout.write(out)
    sys.stderr.write(err)
    return code


if __name__ == "__main__":
    sys.exit(main())
