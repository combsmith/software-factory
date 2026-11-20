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
check run that is always `neutral` (`harness/advised.py`, decision 0224), in a child it kills at a deadline. That
changes no outcome and never fails the step: what was done for each Lens is a code on the step's one line and in
`applied.json`, which is replaced whole to hold it."""
from __future__ import annotations

import json
import os
import sys
import time

from adapters import advice, effects, identity, passes, pull
from adapters.facts import Moved
from adapters.github import Live, Unanswered
from controller import configuration
from harness import advised, apply, bundle, read as read_, reread, shared, steps, task
from harness.steps import Stop

APP = "pr-review"
KEY = "PR_REVIEW_APP_KEY"
STEP = 240      # the seconds the workflow gives this step: `Apply the Result` in run-jobs.yml, 4 minutes


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


def _replaced(folder: str, name: str, data) -> None:
    """`name` in the step's folder, replaced whole by `data`: written new beside it, through no link, and moved onto
    it, so the file is the one before or the one after and never part of either; nothing is left beside it."""
    new = os.path.join(folder, name + ".new")
    try:
        steps.write(folder, name + ".new", data)
        os.replace(new, os.path.join(folder, name))
    finally:
        if os.path.lexists(new):
            os.unlink(new)


def shown(base, argv: list, environ: dict, folder: str, done: dict, ended: dict, kept: dict, left) -> str:
    """What the step's line says of the advisory part, which runs here, last (decision 0224): a code for each Lens,
    which `applied.json` is replaced to hold too. Nothing it meets is raised: a part that cannot say what it did says
    `not_shown`, and a record that cannot be replaced stands as it was written, `not_recorded`, beside the codes."""
    try:
        said = advice.recorded(advised.run(base, argv[5] if len(argv) > 5 else None, os.path.join(argv[4], "advisory"),
                                           kept["admit"], ended, kept["held"], environ, left)) if kept else []
    except Exception:   # NOSONAR an advisory read never fails `apply`, nor changes its outcome
        return "; advisory not_shown"
    line = "".join("; %s %s" % (advice.CHECK % one["lens"], one["code"]) for one in said)
    try:
        more = dict(done, advisory=said)
        if said and shared.errors(more, "applied"):
            raise ValueError("no applied/1")
        if said:
            _replaced(folder, "applied.json", more)
    except Exception:   # NOSONAR the record stands as it was written, and the codes are said all the same
        line += "; advisory not_recorded"
    return line


def adoptable(base, folder, admit, asks: dict) -> frozenset:
    """The `(Lens, Finding id)` of each Finding a review's Result may adopt from an advisory annotation: each Finding of
    each Result of a Lens the Factory asks a reader for, read from the advise step's `folder`, bounded and never through
    a link, taken by its digest and held to `advice/1` and to the Run (`advice.held`), as the run step read it to build
    the Task. None unless the configuration hands the reads over, and none for a Run that is no review (decision 0224,
    "Adoption")."""
    if admit is None or admit["intent"] != task.REVIEWING or asks.get(task.HAND_OVER) is not True or folder is None:
        return frozenset()
    names = [lens for lens in asks["advisory"] if lens in asks.get("readers", {})]
    pairs = set()
    for lens in names:
        result, _ = advice.held(steps.bounded(base, folder, "advice.%s.json" % lens, advice.LARGEST + 1),
                                steps.bounded(base, folder, "advice.%s.sha256" % lens, 128), lens, names, admit,
                                shared.SCHEMAS)
        pairs |= {(lens, found["id"]) for found in (result or {"findings": []})["findings"]}
    return frozenset(pairs)


def written(argv: list, environ: dict, base, clock, connect, kept=None) -> tuple:
    """`(applied/1, outcome/1)` of the Run. `kept`, a dict, is given what the advisory part needs once the read token
    is revoked: the Run's admission and the item read again."""
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
            facts, head, runs, context = reread.item(reading, config, parts["item"]["number"], utc(), utc, record=record)
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
        asks = steps.read_json(steps.ROOT, os.path.join("config", "harness.json"))
        told = {"kernel": dict(config["kernel"], lifecycle=config["lifecycles"]["pull_request"]),
                "rubric": steps.read_json(steps.ROOT, os.path.join("config", "rubric-%s.json" % parts["role"])),
                "authority": steps.read_json(steps.ROOT, os.path.join("config", "authority.json")),
                "advisory": asks["advisory"],
                "adoptable": adoptable(base, argv[5] if len(argv) > 5 else None, admit, asks),
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
        kept.update(admit=admit, held=held)
    # A read token GitHub did not confirm revoked may still read: the Run is the Factory's to look at.
    if revoked is not True:
        return done[0], dict(done[1], outcome="environment", reason="token_not_revoked")
    return done


def step(argv: list, environ: dict, base, clock=time.time, connect=Live) -> str:
    began = clock()         # when the step's time began to run: before anything is read
    argv = steps.given(argv, environ, steps.INPUTS, ("result", "applied", "advice"))
    if len(argv) not in (5, 6):
        raise Stop("usage: python3 -m harness.apply_step NAME ITEM PASS RESULT OUT [ADVICE]")
    folder, kept = steps.new_folder(base, argv[4]), {}
    done, ended = written(argv, environ, base, clock, connect, kept)
    started = engine_started(environ.get("NEEDS"))
    if started is not None:
        ended = dict(ended, engine_started=started)
    if shared.errors(done, "applied") or shared.errors(ended, "outcome"):
        raise Stop("records_unreadable")
    steps.write(folder, "applied.json", done)
    steps.write(folder, "outcome.json", ended)
    # Both files stand as written, whatever follows.
    said = shown(base, argv, environ, folder, done, ended, kept, lambda: began + STEP - clock())
    return "applied, outcome %s%s" % (ended["outcome"] or "none", said)


if __name__ == "__main__":
    steps.exit_with(step, sys.argv[1:], dict(os.environ), os.getcwd())
