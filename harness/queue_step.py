"""The queue act's step: one enqueue, dequeue or set of resolutions, through the queue App's token alone (issue 381,
decision 0130). `harness/queue.py` decides; this step reads and writes for it.

    python3 -m harness.queue_step NAME ITEM PASS OUT

NAME, ITEM and PASS are the Run's three inputs, OUT a new folder. Two credentials, each for its own part: the job's own
`GITHUB_TOKEN` finds the pass record by PASS among the poller's runs, narrowed by the effects port's `Approving` to
the item's repo and reads, with no write; and the queue App's token, minted from `QUEUE_APP_KEY` with the grants its
three acts take and revoked when the act ends, makes the one write, narrowed to the item by `adapters.queue.Queuing`.
`FACTORY_PAUSED` is the Pause as the job's `vars` context gives it. OUT holds `applied.json` and `outcome.json`. A Run
whose outcome names a fault fails the step, by its code, after both are written, so that the run concludes as it ended
and the pass reads its outcome."""
from __future__ import annotations

import json
import os
import sys
import time

from adapters import effects, identity, passes
from adapters.github import Live, Unanswered
from controller import configuration
from controller.writes import QUEUE_INTENTS
from harness import queue, read as read_, shared, steps
from harness.steps import Stop

TOKEN = "GITHUB_TOKEN"
KEY = "QUEUE_APP_KEY"
PAUSE = "FACTORY_PAUSED"
# The needs of the queue App's three acts, which its grant must hold (config/apps.json).
NEEDS = ("effect:enqueue_merge", "effect:dequeue_merge", "effect:resolve_thread")


def written(argv: list, environ: dict, clock, connect) -> tuple:
    name, item, pass_id, _ = argv
    release = steps.release()
    config = configuration.load(steps.ROOT, release, "controller")
    controller = config["controller"]
    home = controller["home"]["repo"]
    parts = read_.asked(name, item, pass_id, home)
    kinds = {intent: action for action, intent in QUEUE_INTENTS.items()}
    if parts["intent"] not in kinds:
        raise Stop("not_a_queue_act")
    kind, run = kinds[parts["intent"]], parts["run"]
    try:
        reading = effects.Approving(connect(environ.get(TOKEN)), parts["item"])
        record = passes.find(reading, home, controller["home"]["branch"], controller["workflows"]["poller"], pass_id)
    except Unanswered:
        return queue._records(run, release, kind, [], ("environment", "record_unreadable"))
    if record is not None and record.get("release") != release:
        return queue._records(run, release, kind, [], ("environment", "release_differs"))
    found = queue.decision_of(record, run) if record is not None else None
    # With no Decision for the Run, or under a Pause, no token is minted at all.
    if found is None:
        return queue._records(run, release, kind, [], ("superseded", "no_decision"))
    if found[0]["item"] != parts["item"] or found[0]["content_id"] != parts["content_id"] \
            or QUEUE_INTENTS[found[0]["action"]] != parts["intent"] or parts["role"] != config["kernel"]["owner_role"]:
        return queue._records(run, release, kind, [], ("superseded", "not_the_decision"))
    if environ.get(PAUSE) not in queue.NOT_PAUSED:
        return queue._records(run, release, kind, [], ("superseded", "paused"))
    account = controller["accounts"]["queue"]
    if not isinstance(account, dict):
        return queue._records(run, release, kind, [], ("environment", "queue_account_unknown"))
    try:
        apps = json.loads((steps.ROOT / "config" / "apps.json").read_text())
        app = apps["apps"]["queue"]
        wanted = identity.granted(app, apps["needs"], NEEDS, "write")
        transport, revoke = identity.from_key(app, home, wanted, environ.get(KEY), int(clock()), connect)
    except identity.Refused as refused:
        return queue._records(run, release, kind, [], ("environment", str(refused)))
    try:
        done, ended = queue.job(record, run, queue.Port(transport, parts["item"], account["login"]),
                                {"release": release, "kind": kind, "paused": environ.get(PAUSE)})
    finally:
        revoked = revoke()
    if revoked is not True and ended["outcome"] is None:
        ended = dict(ended, outcome="environment", reason="token_not_revoked")
    return done, ended


def step(argv: list, environ: dict, base, clock=time.time, connect=Live) -> str:
    argv = steps.given(argv, environ, steps.INPUTS, ("applied",))
    if len(argv) != 4:
        raise Stop("usage: python3 -m harness.queue_step NAME ITEM PASS OUT")
    folder = steps.new_folder(base, argv[3])
    done, ended = written(argv, environ, clock, connect)
    if shared.errors(done, "applied") or shared.errors(ended, "outcome"):
        raise Stop("records_unreadable")
    steps.write(folder, "applied.json", done)
    steps.write(folder, "outcome.json", ended)
    # A Run that did not succeed must conclude so, or the pass never reads its outcome (section 3.10).
    if ended["outcome"] is not None:
        raise Stop(ended["reason"] or ended["outcome"])
    return "%s %s" % (done["effects"][0]["type"], ", ".join(e["state"] for e in done["effects"]))


if __name__ == "__main__":
    steps.exit_with(step, sys.argv[1:], dict(os.environ), os.getcwd())
