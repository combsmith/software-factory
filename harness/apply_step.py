"""The `apply` job's step: one Result written, or refused, through the Role App's own token (#196's ruling 7; decision
0054). `harness/apply.py` decides; this step reads and writes for it.

    python3 -m harness.apply_step NAME ITEM PASS RESULT OUT [ADVICE]

NAME, ITEM and PASS are the Run's three inputs, RESULT the folder its Result was downloaded into, OUT a new folder, and
ADVICE the folder the advisory Lenses' Results were downloaded into, if any was. The
job runs whether `run` and `verify` succeeded or not, so that a Run always leaves its outcome; `NEEDS` is their
results as the workflow gives them, and unless both succeeded nothing is read with a key, nothing is minted and nothing
is written, and the Run ends `environment`, `run_failed` or `verify_failed`. Otherwise, with the pr-review App's key,
`PR_REVIEW_APP_KEY`, it mints a token of reads alone for the home repo, finds the pass record by PASS, holds the Result
to the Decision of the Run the run-name names and to the digest `run` reported, `RUN_DIGEST`, and hands `apply` the
item read again through that token (`harness/reread.py`), with its diff read again at the head the facts were read at,
and a mint of the write token its Effects need. Both tokens are
revoked before the step ends. OUT holds `applied.json` and `outcome.json`, which the job's last step uploads.

Last, once both files are written and the read token revoked, a review's Run shows each advisory Lens's Result as a
check run that is always `neutral` (`advised`, decision 0224). It changes no outcome and never fails the step: what it
did for each Lens is a code on the step's one line and in `applied.json`, which is replaced whole to hold it."""
from __future__ import annotations

import json
import os
import sys
import time

from adapters import advice, effects, identity, passes, pull
from adapters.facts import Moved
from adapters.github import TIMEOUT, Live, Unanswered
from controller import configuration
from harness import apply, bundle, read as read_, reread, shared, steps, task
from harness.steps import Stop

APP = "pr-review"
KEY = "PR_REVIEW_APP_KEY"
REVIEWING = "review-change"     # the Intent whose Run the advisory Lenses read for (decision 0224)
# The seconds the workflow gives this step (`Apply the Result` in run-jobs.yml, 4 minutes), and what the advisory part
# needs of them, a request waiting at most TIMEOUT, 20 s. A Lens's check run is three requests and the revocation one,
# and ONE is those and 10 s for the record: 90 s. Minting is two: nothing is minted with less than 130 s left.
STEP, ONE, MINT = 240, 4 * TIMEOUT + 10, 2 * TIMEOUT


def _ended(run: str, release: str, why: tuple) -> tuple:
    return ({"schema": "applied/1", "run": run, "release": release, "effects": [], "findings": [], "rulings": []},
            {"schema": "outcome/1", "run": run, "release": release, "outcome": why[0], "reason": why[1]})


def change_at(transport, repo: str, number: int, head: str) -> bytes:
    """The bytes of pull request `number`'s diff, read again as the read step reads them, at `head`, the commit its facts
    were read at, or Moved: `apply` builds the Task's diff again from them, and holds a posted Finding to its lines
    (decision 0146)."""
    first = pull.read(transport, repo, number)
    if str(first["head"]["sha"]) != head:
        raise Moved("the pull request moved between its facts and its diff")
    return pull.change(transport, first, pull.base(transport, first)["head"])


def base_at(transport, repo: str, number: int, head: str) -> str:
    """The base commit of pull request `number`, from a read of it at `head`, the commit its facts were read at, or Moved:
    what a push may not touch is read at that commit, never at one the head names (issue 139)."""
    first = pull.read(transport, repo, number)
    if str(first["head"]["sha"]) != head:
        raise Moved("the pull request moved between its facts and its base")
    return str((first.get("base") or {}).get("sha"))


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


def engine_started(needs):
    """Whether the `run` job's Engine step started, by the outcome the job hands on for it (issue 757), or None.

    GitHub skips the step once a step before it failed, as the CLI's install or the read did: then the Run spent no
    model, and this is False. True for an outcome it gives a step that ran. Anything else, an output missing or not
    one of these, says nothing, and the Run is read as one that may have reached the model."""
    try:
        said = json.loads(needs) if isinstance(needs, str) else None
    except ValueError:
        said = None
    run = said.get("run") if isinstance(said, dict) else None
    outputs = run.get("outputs") if isinstance(run, dict) else None
    engine = outputs.get("engine") if isinstance(outputs, dict) else None
    if engine == "skipped":
        return False
    if engine in ("success", "failure", "cancelled"):
        return True
    return None


def _file(base, folder, name: str, most: int):
    """At most `most` bytes of a file in `folder`, a folder that really lies inside `base`; None for one that is not
    there, lies outside, or is a link, which is never followed."""
    try:
        opened = os.open(os.path.join(steps.inside(base, folder), name), os.O_RDONLY | os.O_NOFOLLOW)
        with open(opened, "rb") as f:
            return f.read(most)
    except (OSError, Stop, TypeError, ValueError):
        return None


def advised(base, folder, admit, done: tuple, held: dict, mint, config: dict, left=lambda: STEP) -> list:
    """`(lens, code)` for each advisory Lens the Factory asks: `shown` where its Result is now a check run on the
    admitted commit, else why not, one of `advice.CODES` (decision 0224, "What is shown"). Only a review's Run shows
    one, that `apply` ended with no fault or the Role's own, on an item it read again and found as admitted: a change
    under the Run is `superseded`, a Run the Factory faulted `run_not_whole`. Each Result is read from `folder`, bounded
    and through no link, and held by `advice.held`; one that fails is not shown at all. The check run is the Role
    App's, `neutral` whatever the Result says, through a token of its need alone and the advisory allowlist. `left()`
    is the seconds the step still has: nothing is begun that could not end and be revoked in them (`out_of_time`).
    Whatever a write does, the revocation is asked for, and unless confirmed every Lens asked is `token_not_revoked`."""
    if admit is None or admit["intent"] != REVIEWING:
        return []
    asks = steps.read_json(steps.ROOT, os.path.join("config", "harness.json"))
    names = [lens for lens in asks["advisory"] if lens in asks.get("readers", {})]
    facts, head = held["item"][:2] if "item" in held else (None, None)
    if facts is None:
        return [(lens, "item_not_read") for lens in names]
    if done[1]["outcome"] == "superseded" or facts["state"] != "open" or facts["content_id"] != admit["content_id"]:
        return [(lens, "superseded") for lens in names]
    if done[1]["outcome"] not in (None, "item"):
        return [(lens, "run_not_whole") for lens in names]
    said, asked = {}, []
    for lens in names:
        data = _file(base, folder, "advice.%s.json" % lens, advice.LARGEST + 1)
        digest = _file(base, folder, "advice.%s.sha256" % lens, 128)
        result, said[lens] = advice.held(data, digest, lens, names, admit, shared.SCHEMAS)
        if result is not None:
            output, ids = advice.shown(result)
            asked.append((lens, {"commit": head, "name": advice.CHECK % lens, "conclusion": "neutral",
                                 "external_id": "%s:%s" % (admit["run"], lens), "output": output,
                                 "annotations": [{"finding": ident} for ident in ids]}))
    if asked and left() < MINT + ONE:
        said.update({lens: "out_of_time" for lens, _ in asked})
    elif asked:
        try:
            transport, revoke = mint(identity.permissions(config["app"], config["needs"], ["create_check_run"]))
        except Exception:   # NOSONAR a token not minted, for whatever cause, is a code: nothing was written
            return [(lens, said[lens] or "token_not_minted") for lens in names]
        allowed = None
        for lens, req in asked:
            if left() < ONE:
                said[lens] = "out_of_time"
                continue
            try:
                allowed = allowed or effects.Allowed(transport, *effects.advisory_permits(admit["item"], head, names,
                                                                                         admit["run"]))
                state = effects.role_write(allowed, admit["item"], "create_check_run", req,
                                           config["app"]["name"] + "[bot]").get("state")
            except Exception:   # NOSONAR a write that raises, foreseen or not, is a code, and the token is still revoked
                state = "raised"
            said[lens] = "shown" if state in ("applied", "already_applied") else \
                {"sent": "not_read_back", "raised": "write_raised"}.get(state, "not_written")
        try:
            gone = revoke() is True
        except Exception:   # NOSONAR a revocation that raises is one GitHub did not confirm
            gone = False
        if not gone:
            said.update({lens: "token_not_revoked" for lens, _ in asked})
    return [(lens, said[lens]) for lens in names]


def _replaced(folder: str, name: str, data) -> None:
    """`name` in the step's folder, replaced whole by `data`: written new beside it, through no link, and moved onto
    it, so that the file is the one before or the one after and never part of either."""
    steps.write(folder, name + ".new", data)
    os.replace(os.path.join(folder, name + ".new"), os.path.join(folder, name))


def written(argv: list, environ: dict, base, clock, connect, kept=None) -> tuple:
    """`(applied/1, outcome/1)` of the Run. `kept`, a dict, is given what `advised` needs once the read token is
    revoked: the Run's admission, the item read again, the mint and the configuration."""
    name, item, pass_id, found = argv[:4]
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
            facts, head, runs, context = reread.item(reading, config, parts["item"]["number"], utc(), utc)
            # The diff is read when `apply` asks, once every check that needs no diff let the Result through (decision
            # 0146).
            diff = lambda: change_at(reading, config["controller"]["home"]["repo"], parts["item"]["number"], head)
            held["item"] = (facts, head, runs, context, diff)
            return held["item"]

        def mint(wanted):
            return identity.from_key(config["app"], home, wanted, key, int(clock()), connect)

        def holding(asked):
            # A push is held to the base's list, read through the read token, before anything is minted (issue 139).
            base = base_at(reading, home, parts["item"]["number"], held["item"][1])
            return bundle.held(asked, base, reading, home)

        def write(transport, kind, req):
            head = held["item"][1]
            login = config["app"]["name"] + "[bot]"
            allowed = effects.Allowed(transport, *effects.role_permits(admit["item"], head, "factory / " + parts["role"]))
            return effects.role_write(allowed, admit["item"], kind, req, login)
        told = {"kernel": dict(config["kernel"], lifecycle=config["lifecycles"]["pull_request"]),
                "rubric": steps.read_json(steps.ROOT, os.path.join("config", "rubric-%s.json" % parts["role"])),
                "authority": steps.read_json(steps.ROOT, os.path.join("config", "authority.json")),
                "advisory": steps.read_json(steps.ROOT, os.path.join("config", "harness.json"))["advisory"],
                "github_run": environ.get("GITHUB_RUN_ID"), "app": config["app"], "needs": config["needs"],
                # The bound the Task's diff was cut at, so that it is built again as the Run was given it (issue 327).
                "max_diff_characters": config["kernel"]["limits"]["max_diff_characters"]}
        if admit is not None:
            try:
                done = apply.job(admit, result, read, write, mint, role, told, utc(), held=holding)
            except Moved:
                # The pull request changed while it was read again: a change under the Run, never the environment's.
                done = _ended(parts["run"], release, ("superseded", "head_moved"))
            except Unanswered as err:
                done = _ended(parts["run"], release, ("environment", shared.unread(err)))
    finally:
        revoked = revoke()
    if kept is not None:
        kept.update(admit=admit, held=held, mint=mint, config=config)
    # A read token GitHub did not confirm revoked may still read: the Run is the Factory's to look at.
    if revoked is not True:
        return done[0], dict(done[1], outcome="environment", reason="token_not_revoked")
    return done


def step(argv: list, environ: dict, base, clock=time.time, connect=Live) -> str:
    argv = steps.given(argv, environ, steps.INPUTS, ("result", "applied", "advice"))
    if len(argv) not in (5, 6):
        raise Stop("usage: python3 -m harness.apply_step NAME ITEM PASS RESULT OUT [ADVICE]")
    folder, kept, began = steps.new_folder(base, argv[4]), {}, clock()
    done, ended = written(argv, environ, base, clock, connect, kept)
    started = engine_started(environ.get("NEEDS"))
    if started is not None:
        ended = dict(ended, engine_started=started)
    if shared.errors(done, "applied") or shared.errors(ended, "outcome"):
        raise Stop("records_unreadable")
    steps.write(folder, "applied.json", done)
    steps.write(folder, "outcome.json", ended)
    # Both files stand as written, whatever follows: the advisory part comes last, changes neither's outcome, and adds
    # to `applied.json` alone what it did for each Lens (decision 0224).
    shown = ""
    try:
        said = advised(base, argv[5] if len(argv) > 5 else None, kept["admit"], (done, ended), kept["held"], kept["mint"],
                       kept["config"], lambda: began + STEP - clock()) if kept else []
        more = dict(done, advisory=[{"lens": lens, "code": code} for lens, code in said])
        if said and shared.errors(more, "applied"):
            raise ValueError("what was done for a Lens is no code of applied/1's")
        if said:
            _replaced(folder, "applied.json", more)
        shown = "".join("; %s %s" % (advice.CHECK % lens, code) for lens, code in said)
    except Exception:   # NOSONAR an advisory read never fails `apply`, nor changes its outcome (decision 0224)
        shown = "; advisory not_shown"
    return "applied, outcome %s%s" % (ended["outcome"] or "none", shown)


if __name__ == "__main__":
    steps.exit_with(step, sys.argv[1:], dict(os.environ), os.getcwd())
