"""The `apply` job's step: one Result written, or refused, through the Role App's own token (#196's ruling 7; decision
0054). `harness/apply.py` decides; this step reads and writes for it.

    python3 -m harness.apply_step NAME ITEM PASS RESULT OUT

NAME, ITEM and PASS are the Run's three inputs, RESULT the folder its Result was downloaded into, OUT a new folder. The
job runs whether `run` and `verify` succeeded or not, so that a Run always leaves its outcome; `NEEDS` is their
results as the workflow gives them, and unless both succeeded nothing is read with a key, nothing is minted and nothing
is written, and the Run ends `environment`, `run_failed` or `verify_failed`. Otherwise, with the pr-review App's key,
`PR_REVIEW_APP_KEY`, it mints a token of reads alone for the home repo, finds the pass record by PASS, holds the Result
to the Decision of the Run the run-name names and to the digest `run` reported, `RUN_DIGEST`, and hands `apply` the
item read again through that token (`harness/reread.py`) and a mint of the write token its Effects need. Both tokens are
revoked before the step ends. OUT holds `applied.json` and `outcome.json`, which the job's last step uploads."""
from __future__ import annotations

import json
import os
import sys
import time

from adapters import effects, identity, passes
from adapters.facts import Moved
from adapters.github import Live, Unanswered
from controller import configuration
from harness import apply, read as read_, reread, shared, steps, task
from harness.steps import Stop

APP = "pr-review"
KEY = "PR_REVIEW_APP_KEY"


def _ended(run: str, release: str, why: tuple) -> tuple:
    return ({"schema": "applied/1", "run": run, "release": release, "effects": [], "findings": []},
            {"schema": "outcome/1", "run": run, "release": release, "outcome": why[0], "reason": why[1]})


def needs_met(needs) -> tuple:
    """Why nothing may be written, by what the workflow's `needs` says of `run` and `verify`, or None."""
    try:
        said = json.loads(needs) if isinstance(needs, str) else None
    except ValueError:
        said = None
    if not isinstance(said, dict):
        return "environment", "needs_unreadable"
    for job in ("run", "verify"):
        if not isinstance(said.get(job), dict) or said[job].get("result") != "success":
            return "environment", "%s_failed" % job
    return None


def written(argv: list, environ: dict, base, clock, connect) -> tuple:
    """`(applied/1, outcome/1)` of the Run."""
    name, item, pass_id, found, _ = argv
    release = steps.release()
    config = configuration.load(steps.ROOT, release, APP)
    home = config["controller"]["home"]["repo"]
    parts = read_.asked(name, item, pass_id, home)
    why = needs_met(environ.get("NEEDS"))
    if why is not None:
        return _ended(parts["run"], release, why)
    key, now = environ.get(KEY), int(clock())
    utc = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(clock())))
    try:
        reading, revoke = identity.from_key(config["app"], home,
                                            identity.granted(config["app"], config["needs"], apply.READS, "read"),
                                            key, now, connect)
    except identity.Refused as err:
        return _ended(parts["run"], release, ("environment", str(err)))
    revoked = False
    try:
        try:
            record = passes.find(reading, home, config["controller"]["home"]["branch"],
                                 config["controller"]["workflows"]["poller"], pass_id)
        except Unanswered:
            record = False
        role = steps.read_json(steps.ROOT, os.path.join("roles", "%s.json" % parts["role"]))
        admit = None
        if record is False:
            done = _ended(parts["run"], release, ("environment", "record_unreadable"))
        elif record is None:
            done = _ended(parts["run"], release, ("superseded", "no_decision"))
        elif record.get("release") != release:
            # A Run of another Release than the pass that admitted it: its files are not the ones it was decided under.
            done = _ended(parts["run"], release, ("environment", "release_differs"))
        else:
            try:
                read_.decided(record, parts, config["kernel"]["owner_role"])
                admit = apply.admitted(record, parts["run"], role, [])
            except Stop as stop:
                # A record that is no pass record is the environment's; a Decision of another item, Intent or
                # content than the run-name's is no Decision of this Run.
                why = ("environment", stop.code) if stop.code == "record_unreadable" else ("superseded", "no_decision")
                done = _ended(parts["run"], release, why)
            except task.Refused:
                done = _ended(parts["run"], release, ("superseded", "no_decision"))
        try:
            with open(steps.inside(base, os.path.join(found, "result.json")), "rb") as f:
                result = apply.taken(f.read(), environ.get("RUN_DIGEST"))
        except (OSError, Stop):
            result = None
        held = {}

        def read():
            held["item"] = reread.item(reading, config, parts["item"]["number"], utc(), utc)
            return held["item"]

        def mint(wanted):
            return identity.from_key(config["app"], home, wanted, key, int(clock()), connect)

        def write(transport, kind, req):
            facts, head = held["item"][0], held["item"][1]
            threads = [t["id"] for t in facts["threads"]]
            login = config["app"]["name"] + "[bot]"
            allowed = effects.Allowed(transport, *effects.role_permits(admit["item"], head, "factory / " + parts["role"],
                                                                      threads))
            return effects.role_write(allowed, admit["item"], kind, req, login)
        told = {"kernel": dict(config["kernel"], lifecycle=config["lifecycles"]["pull_request"]),
                "rubric": steps.read_json(steps.ROOT, os.path.join("config", "rubric-%s.json" % parts["role"])),
                "authority": steps.read_json(steps.ROOT, os.path.join("config", "authority.json")),
                "github_run": environ.get("GITHUB_RUN_ID"), "app": config["app"], "needs": config["needs"]}
        if admit is not None:
            try:
                done = apply.job(admit, result, read, write, mint, role, told, utc())
            except Moved:
                # The pull request changed while it was read again: a change under the Run, never the environment's.
                done = _ended(parts["run"], release, ("superseded", "head_moved"))
            except Unanswered:
                done = _ended(parts["run"], release, ("environment", "facts_unreadable"))
    finally:
        revoked = revoke()
    # A read token GitHub did not confirm revoked may still read: the Run is the Factory's to look at.
    if revoked is not True:
        return done[0], dict(done[1], outcome="environment", reason="token_not_revoked")
    return done


def step(argv: list, environ: dict, base, clock=time.time, connect=Live) -> str:
    argv = steps.given(argv, environ, steps.INPUTS, ("result", "applied"))
    if len(argv) != 5:
        raise Stop("usage: python3 -m harness.apply_step NAME ITEM PASS RESULT OUT")
    folder = steps.new_folder(base, argv[4])
    done, ended = written(argv, environ, base, clock, connect)
    if shared.errors(done, "applied") or shared.errors(ended, "outcome"):
        raise Stop("records_unreadable")
    steps.write(folder, "applied.json", done)
    steps.write(folder, "outcome.json", ended)
    return "applied, outcome %s" % (ended["outcome"] or "none")


if __name__ == "__main__":
    steps.exit_with(step, sys.argv[1:], dict(os.environ), os.getcwd())
