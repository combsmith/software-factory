"""PostToolUse on an edit: run the checks alone, `make checks`, and show a failure to the agent.

The edit has already happened; exit 2 puts the failure in front of the agent and refuses nothing. A run
that does not finish found nothing, and says that it did not finish. The tests are CI's, and a builder's
own `make verify`: they outgrew any time a hook can spend (issue 438).
Run as `python3 -I` on this file, so nothing in the working directory can stand in for the standard
library; the repo is put last on the path, after it.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))
from tools.hooks import make  # noqa: E402

TIMEOUT = 110   # seconds; the settings give the hook 120


def respond(payload: dict, env: dict) -> tuple:
    """(exit code, stdout, stderr) for this edit. An edit outside the project and its worktrees runs nothing."""
    edited = payload.get("tool_input") or {}
    where = make.tree(make.project(env), edited.get("file_path") or edited.get("notebook_path") or payload.get("cwd"))
    if where is None:
        return 0, "", ""
    passed, said = make.make("checks", where, env, TIMEOUT)
    if passed:
        return 0, "", ""
    if said.startswith(make.UNFINISHED % ("checks", TIMEOUT, where)):
        return 0, json.dumps({"systemMessage": "%s They found nothing; CI runs them." % said}) + "\n", ""
    if make.lacks("checks", where, env):
        told = "%s has no `make checks` target, so the checks did not run after this edit." % where
        return 0, json.dumps({"systemMessage": told}) + "\n", ""
    return 2, "", ("The checks fail after this edit (`make checks` in %s). The edit stands; this is what fails "
                   "now:\n%s\n" % (where, said))


def main() -> int:
    code, out, err = respond(json.loads(sys.stdin.read() or "{}"), dict(os.environ))
    sys.stdout.write(out)
    sys.stderr.write(err)
    return code


if __name__ == "__main__":
    sys.exit(main())
