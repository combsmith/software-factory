"""Stop: a session does not end while `make verify` fails.

It is sent back once. If verify still fails when it stops again, it ends and the person is told:
a hook that sent it back for ever would cycle with no bound and no person.
"""
from __future__ import annotations

import json
import os
import sys

from tools.hooks import make

TIMEOUT = 580       # seconds; the settings give the hook 600
TOLD = 15           # lines of the failure put in front of the person


def respond(payload: dict, env: dict) -> tuple:
    """(exit code, stdout, stderr) for this stop."""
    where = make.tree(payload.get("cwd"))
    passed, said = make.make("verify", where, env, TIMEOUT)
    if passed:
        return 0, "", ""
    if payload.get("stop_hook_active") is True:
        told = ("`make verify` still fails in %s. The session was sent back once to make it pass, and ends now; "
                "what happens next is yours.\n%s" % (where, make.tail(said, TOLD)))
        return 0, json.dumps({"systemMessage": told}) + "\n", ""
    return 2, "", ("`make verify` fails in %s, so the session does not end yet. Make it pass. If it cannot pass in "
                   "this session, say why; the next stop then ends it.\n%s\n" % (where, said))


def main() -> int:
    code, out, err = respond(json.loads(sys.stdin.read() or "{}"), dict(os.environ))
    sys.stdout.write(out)
    sys.stderr.write(err)
    return code


if __name__ == "__main__":
    sys.exit(main())
