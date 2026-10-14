"""Stop: a session is sent back once while `make verify` fails on work it has not pushed.

At the next stop it ends and the person is told: a hook that sent it back for ever would cycle with
no bound and no person. With nothing changed and nothing unpushed there is nothing to verify, so a
turn spent answering questions costs nothing. Run as `python3 -I` on this file; see after_edit.py.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))
from tools.hooks import make  # noqa: E402

TIMEOUT = 580       # seconds; the settings give the hook 600
TOLD = 15           # lines of the failure put in front of the person


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


def respond(payload: dict, env: dict) -> tuple:
    """(exit code, stdout, stderr) for this stop."""
    base = make.project(env)
    where = make.tree(base, payload.get("cwd")) or base
    if nothing_to_verify(where, env):
        return 0, "", ""
    passed, said = make.make("verify", where, env, TIMEOUT)
    if passed:
        return 0, "", ""
    if payload.get("stop_hook_active") is True:
        told = ("`make verify` still fails in %s. The session was sent back once to make it pass, and ends now; "
                "what happens next is yours.\n%s" % (where, make.tail(said, TOLD)))
        return 0, json.dumps({"systemMessage": told}) + "\n", ""
    return 2, "", "`make verify` fails in %s:\n%s\n" % (where, said)


def main() -> int:
    code, out, err = respond(json.loads(sys.stdin.read() or "{}"), dict(os.environ))
    sys.stdout.write(out)
    sys.stderr.write(err)
    return code


if __name__ == "__main__":
    sys.exit(main())
