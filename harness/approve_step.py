"""The approving act's step: one approval, or none, through the machine user's token alone (decision 0055; #196's
ruling 2). `harness/approve.py` decides; this step reads and writes for it.

    python3 -m harness.approve_step NAME ITEM PASS OUT

NAME, ITEM and PASS are the Run's three inputs, OUT a new folder. The approver's token, `APPROVER_TOKEN`, is the one
credential, and every request it sends is held by the effects port's `Approving` to the item's own repo and reads, and
to the one approval: the pass record is found by PASS among the poller's runs, and the item read again
(`harness/reread.py`), through it. No key is minted and none revoked: the token is the machine user's own. OUT holds
`applied.json` and `outcome.json`; a token that cannot be read writes nothing and ends `environment`."""
from __future__ import annotations

import os
import sys
import time

from adapters import effects, passes
from adapters.github import Live, Unanswered
from controller import configuration
from harness import approve, read as read_, reread, shared, steps
from harness.steps import Stop

TOKEN = "APPROVER_TOKEN"


def written(argv: list, environ: dict, clock, connect) -> tuple:
    name, item, pass_id, _ = argv
    release = environ.get("RELEASE")
    if not isinstance(release, str) or not configuration.RELEASE.fullmatch(release):
        raise Stop("release_unreadable")
    config = configuration.load(steps.ROOT, release, "controller")
    home = config["controller"]["home"]["repo"]
    parts = read_.asked(name, item, pass_id, home)
    utc = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(clock())))
    try:
        transport = connect(environ.get(TOKEN))
    except Unanswered:
        return approve._records(parts["run"], release, "refused", None, ("environment", "approver_unreadable"))
    approving = effects.Approving(transport, parts["item"])
    record = passes.find(approving, home, config["controller"]["home"]["branch"],
                         config["controller"]["workflows"]["poller"], pass_id)
    told = {"approver": config["kernel"]["approver"],
            "kernel": dict(config["kernel"], lifecycle=config["lifecycles"]["pull_request"]),
            "github_run": environ.get("GITHUB_RUN_ID"), "release": release}
    return approve.job(record, parts["run"],
                       lambda: reread.item(approving, config, parts["item"]["number"], utc(), utc),
                       approve.Port(transport, told["approver"]), told, utc())


def step(argv: list, environ: dict, base, clock=time.time, connect=Live) -> str:
    if len(argv) != 4:
        raise Stop("usage: python3 -m harness.approve_step NAME ITEM PASS OUT")
    folder = steps.new_folder(base, argv[3])
    done, ended = written(argv, environ, clock, connect)
    if shared.errors(done, "applied") or shared.errors(ended, "outcome"):
        raise Stop("records_unreadable")
    steps.write(folder, "applied.json", done)
    steps.write(folder, "outcome.json", ended)
    return "approval %s, outcome %s" % (done["effects"][0]["state"], ended["outcome"] or "none")


if __name__ == "__main__":
    steps.exit_with(step, sys.argv[1:], dict(os.environ), os.getcwd())
