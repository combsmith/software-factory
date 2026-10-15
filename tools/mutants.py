"""Can the tests fail? Break the Kernel on purpose, one rule at a time, and see.

Each mutant removes or inverts one rule. A mutant that the tests do not catch
is a rule nothing is checking. Run with `python3 -m tools.mutants`.
"""
from __future__ import annotations

import concurrent.futures
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile

from tools import walk

ROOT = pathlib.Path(__file__).resolve().parent.parent
MUTANTS = [
    ("incomplete facts are trusted", "kernel/derive.py",
     "    gaps = incomplete(facts)\n", "    gaps = []\n"),
    ("a list of Runs read short is trusted", "kernel/derive.py",
     "[name for name in t.READ_IN_FULL if flags.get(name) is not True]",
     '[name for name in t.READ_IN_FULL if name != "runs" and flags.get(name) is not True]'),
    ("a flag that is not exactly true counts as whole", "kernel/derive.py",
     "if flags.get(name) is not True]", "if not flags.get(name, True)]"),
    ("incomplete facts are read before a merged or closed item", "kernel/derive.py",
     '    if facts["state"] == "merged":\n',
     "    if incomplete(facts):\n"
     '        return {"state": None, "reason": "facts_incomplete", "evidence": incomplete(facts)}\n'
     '    if facts["state"] == "merged":\n'),
    ("model review before the checks pass", "kernel/derive.py",
     "    if waiting:\n", "    if False:\n"),
    ("a failed check is ignored", "kernel/derive.py",
     "    if failed:\n", "    if False:\n"),
    ("a stranger's thread gates", "kernel/derive.py",
     'if by["kind"] == "human" and by["can_write"]:', 'if by["kind"] == "human":'),
    ("a minor finding gates", "kernel/derive.py",
     'th["severity"] in t.GATING_SEVERITIES', "True"),
    ("an empty diff converges", "kernel/derive.py",
     'if facts["diff"]["files"] == 0:', "if False:"),
    ("admission survives a push", "kernel/derive.py",
     'return facts["admitted_at"] > facts["last_push_at"]', "return True"),
    ("an approval of other content stands", "kernel/derive.py",
     'and rv["content_id"] == facts["content_id"]\n        ):', "):"),
    ("a review of other content counts", "kernel/derive.py",
     '        and r["content_id"] == facts["content_id"]\n        and r["status"] == "completed"',
     '        and r["status"] == "completed"'),
    ("the hold label is ignored", "kernel/derive.py",
     "    if t.LABEL_HOLD in labels:\n", "    if False:\n"),
    ("an unknown merge state is read as mergeable", "kernel/derive.py",
     "    if mergeable is not True:\n", "    if False:\n"),
    ("only a null merge state is unknown", "kernel/derive.py",
     "    if mergeable is not True:\n", "    if mergeable is None:\n"),
    ("a conflict is not sent back to the author", "kernel/derive.py",
     "    if mergeable is False:\n", "    if False:\n"),
    ("the merge state is read before a merged, closed, held, draft or queued item", "kernel/derive.py",
     '    if facts["state"] == "merged":\n',
     '    if facts.get("mergeable") is not True and facts.get("mergeable") is not False:\n'
     '        return {"state": None, "reason": "mergeable_unreadable", "evidence": []}\n'
     '    if facts["state"] == "merged":\n'),
    ("a dependency update waits for a model review", "kernel/derive.py",
     "    for lens in required_model_lenses(facts, config):\n",
     '    for lens in config["required_lenses"]["model"]:\n'),
    ("a model Lens's thread does not gate a dependency update", "kernel/derive.py",
     '    required = set(config["required_lenses"]["model"])\n',
     "    required = set(required_model_lenses(facts, config))\n"),
    ("a neutral deterministic check passes", "kernel/derive.py",
     '        elif check["conclusion"] != "success":\n',
     '        elif check["conclusion"] not in ("success", "neutral"):\n'),
    ("a dependency bot's pull request someone else pushed to skips the model review", "kernel/derive.py",
     ' and facts["last_pusher"] == facts["author"]:', ":"),
    ("a class the configuration does not name skips the model review", "kernel/derive.py",
     'facts["class"] in lenses["model_not_required_for"]', "True"),
    ("a dependency update converges before its checks are read", "kernel/derive.py",
     "    # Deterministic Lenses first: a model's time is not spent on content they reject.\n",
     "    if not required_model_lenses(facts, config):\n"
     '        return {"state": t.CONVERGED, "reason": "approval_due", "evidence": []}\n'),
    ("a dependency update converges before its threads are read", "kernel/derive.py",
     "    open_gates = gating_threads(facts, config)\n",
     "    open_gates = gating_threads(facts, config) if required_model_lenses(facts, config) else []\n"),
    ("two Runs on one item", "kernel/decide.py",
     "    if in_progress(mine):\n", "    if False:\n"),
    ("the approver may be the author", "kernel/decide.py",
     'if config["approver"] in (facts["author"], facts["last_pusher"]):', "if False:"),
    ("a pause admits a Run", "kernel/decide.py",
     "    pause = _pause(context)\n    if pause:\n", "    pause = _pause(context)\n    if False:\n"),
    ("a pause lets an approval or a merge through", "kernel/decide.py",
     "        pause = _pause(context)\n        if pause:\n", "        pause = _pause(context)\n        if False:\n"),
    ("a pause hides the approver Hold", "kernel/decide.py",
     '        if config["approver"] in (facts["author"], facts["last_pusher"]):\n'
     '            return _decision(facts, t.HELD, "approver_is_author_or_last_pusher", [], t.HOLD)\n'
     "        # The Hold the facts establish first, then the Pause; neither approves.\n"
     "        pause = _pause(context)\n        if pause:\n"
     "            return _decision(facts, state, pause, evidence, t.DEFER)\n",
     "        pause = _pause(context)\n        if pause:\n"
     "            return _decision(facts, state, pause, evidence, t.DEFER)\n"
     '        if config["approver"] in (facts["author"], facts["last_pusher"]):\n'
     '            return _decision(facts, t.HELD, "approver_is_author_or_last_pusher", [], t.HOLD)\n'),
    ("an unreadable pause is read as no pause", "kernel/decide.py",
     'if context.get("paused") is False:', 'if not context.get("paused"):'),
    ("attempts are unlimited", "kernel/decide.py",
     '    if len(attempts) >= limits["max_attempts"]:\n', "    if False:\n"),
    ("capacity faults count as attempts", "kernel/decide.py",
     ' and r.get("outcome") == "item"]', "]"),
    ("rounds are unlimited", "kernel/decide.py",
     '        if len(rounds) >= limits["max_rounds"]:\n', "        if False:\n"),
    ("the run ceiling is ignored", "kernel/decide.py",
     '    if len(recent) >= limits["max_runs_per_item"]:\n', "    if False:\n"),
    ("a capacity fault does not defer", "kernel/decide.py",
     "    if until is not None and until > now:\n", "    if False:\n"),
    ("an unreadable count of active Runs is trusted", "kernel/decide.py",
     "    if active is None:\n", "    if active is None and False:\n"),
    ("the org limit is ignored", "kernel/decide.py",
     '    if active >= limits["org_max_active_runs"]:\n', "    if False:\n"),
]


TIMEOUT = 600      # seconds for one run of the suite. A run that takes longer is an ERROR, never a kill
# What unittest prints last when a test failed or raised. Without it, the run broke some other way.
FAILED = re.compile(r"^FAILED \((?:failures|errors)=", re.M)
# unittest's stand-in for a test module that would not import: the copy is broken, not the rule.
UNIMPORTABLE = "unittest.loader._FailedTest"


def suite(cwd: pathlib.Path, timeout: float = TIMEOUT) -> tuple:
    """Run the tests in `cwd` to the first failure: (exit status, output), the status None if it timed out."""
    env = dict(os.environ, SIM_SEEDS="40", MUTATING="1")
    with subprocess.Popen([sys.executable, "-m", "unittest", "discover", "-q", "-f", "tests"], cwd=str(cwd),
                          env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          start_new_session=True) as run:
        try:
            out, _ = run.communicate(timeout=timeout)
            return run.returncode, out.decode(errors="replace")
        except subprocess.TimeoutExpired:
            # Its children go too, so that none is left holding the output open.
            os.killpg(run.pid, signal.SIGKILL)
            out, _ = run.communicate()
            return None, out.decode(errors="replace")


def verdict(status, output: str) -> tuple:
    """What a run of the suite says of its mutant: ("killed", "SURVIVED" or "ERROR", and why)."""
    if status is None:
        return "ERROR", "the run took longer than %d s" % TIMEOUT
    if status == 0:
        return "SURVIVED", ""
    if status == 1 and FAILED.search(output) and UNIMPORTABLE not in output:
        return "killed", ""
    last = next((line.strip() for line in reversed(output.splitlines()) if line.strip()), "no output")
    return "ERROR", "exit status %d, and no test failed: %s" % (status, last)


def attempt(mutant: tuple, root: pathlib.Path, run) -> tuple:
    """Break one rule in a fresh copy of `root` and run the tests there: (outcome, why)."""
    name, rel, old, new = mutant
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp) / "repo"
        walk.copy(root, work)
        target = work / rel
        text = target.read_text()
        if text.count(old) != 1:
            return "STALE", "the code it mutates has changed"
        target.write_text(text.replace(old, new))
        return verdict(*run(work))


def main(mutants: list = None, root: pathlib.Path = ROOT, run=suite, workers: int = None) -> int:
    mutants = MUTANTS if mutants is None else mutants
    outcome, why = verdict(*run(root))
    if outcome != "SURVIVED":
        print("the tests fail before anything is broken; a mutant cannot be told from that%s"
              % (" (%s)" % why if why else ""))
        return 1
    killed = 0
    # One run to a CPU. map() hands the results back in the order of `mutants`, however the runs finish.
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers or os.cpu_count() or 1) as pool:
        results = pool.map(lambda mutant: attempt(mutant, root, run), mutants)
        for mutant, (outcome, why) in zip(mutants, results):
            print("%-9s %s%s" % (outcome, mutant[0], " (%s)" % why if why else ""), flush=True)
            killed += outcome == "killed"
    print("%d of %d mutants killed" % (killed, len(mutants)))
    return 0 if killed == len(mutants) else 1


if __name__ == "__main__":
    sys.exit(main())
