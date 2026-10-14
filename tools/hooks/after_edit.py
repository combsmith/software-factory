"""PostToolUse on an edit: run the fast checks, `make fast`, and show a failure to the agent.

The edit has already happened; exit 2 puts the failure in front of the agent and refuses nothing.
"""
from __future__ import annotations

import json
import os
import sys

from tools.hooks import make

TIMEOUT = 110   # seconds; the settings give the hook 120


def respond(payload: dict, env: dict) -> tuple:
    """(exit code, stdout, stderr) for this edit."""
    edited = payload.get("tool_input") or {}
    where = make.tree(edited.get("file_path") or edited.get("notebook_path"), payload.get("cwd"))
    passed, said = make.make("fast", where, env, TIMEOUT)
    if passed:
        return 0, "", ""
    return 2, "", ("The fast checks fail after this edit (`make fast` in %s). The edit stands; this is what fails "
                   "now:\n%s\n" % (where, said))


def main() -> int:
    code, out, err = respond(json.loads(sys.stdin.read() or "{}"), dict(os.environ))
    sys.stdout.write(out)
    sys.stderr.write(err)
    return code


if __name__ == "__main__":
    sys.exit(main())
