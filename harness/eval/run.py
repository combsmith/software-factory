"""The eval job's run step: each case the set names given to the review Intent as a live Run is, and scored.

What is measured is what runs (design §3.14, issue 309's ruling 5). A case's Task is built by `harness/task.from_admission`,
the function a live Run's is built by, from the case's facts and its diff, with the Release's own configuration and the
Role's manifest; only the admission is the case's own, its content the case's facts give, and its Run a fresh id. It
is answered by `harness/run.answer`, as a live Run is: the same pin, the tier's limits, `--tools ""` and the scrub.
The step holds the model's credential and the CLI's path alone (`tools/check_workflows.py`), and stops starting cases
when the time it has left is less than a case's tier allows, so that the job ends before its own timeout: a case not
reached is unanswered, and the run fails.

Nothing of a case, a Task or a Result is printed or written: each Result is scored in this step's memory and never
kept, and only `eval-report.json`, of hashes, verdicts and codes, is written in the workspace, by `score`."""
from __future__ import annotations

import json
import os
import time

from harness import run as live, task as tasks
from harness.eval import Stop, _planned, exit_with, score

# The seconds the job may spend before the last case is started, counted from when `plan` was made: the job's 120
# minutes (tools/check_workflows.py, EVAL_RUNNER) less ten for the checkout before it, the upload and judge after the
# step, and the slack of a runner's clock. The fetch and the install spend it, as the cases do.
BUDGET = 110 * 60
# What a case may cost beyond its tier's own seconds: the Engine asks the CLI its version before the call and after it,
# each within this many seconds (harness/engine.py).
VERSION_READS = 2 * 30
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def run_id() -> str:
    """A fresh Run id, in the form a pass mints one, for one case's Task alone."""
    return "r_" + "".join(ALPHABET[b % 32] for b in os.urandom(20))


def reviewer(env: dict, release: str, began: int, call=None, clock=time.time):
    """The review Intent, as `assess` asks it: a case's `result/1`, or Stop with the code that says why there is none.
    Its Task is the case's, built as a live Run's; a case its Task is refused for is `not_this_set`, and one whose diff is
    over the bound `diff_not_whole`, and nothing is asked of the model: `harness.eval.case_fault` has told the rest apart. The
    configuration and the manifest are the checkout's own, the Release's, as a live Run's are. `began` is when `plan`
    was made, by `clock`, the runner's own: no case is started once less time is left of BUDGET than it may take."""
    config = dict(live.configuration(), release=release)
    with open(os.path.join(str(live.ROOT), "roles", "pr-review.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    deadline = began + BUDGET

    def review(case: dict) -> dict:
        facts = case["facts"]
        admit = {"role": case["role"], "intent": case["intent"], "content_id": facts.get("content_id")}
        # The issue a change serves, as a live Run reads it (adapters/texts.py), where the case holds one (decision 0116).
        texts = [{"id": "issue:%d" % case["issue"]["number"], "by": case["issue"]["by"], "body": case["issue"]["body"]}] \
            if "issue" in case else []
        try:
            the_task = tasks.from_admission(admit, facts.get("item"), run_id(), facts, texts, manifest, [], config,
                                      case["diff"].encode("utf-8"))
        except (tasks.Refused, KeyError, UnicodeEncodeError):
            raise Stop("not_this_set") from None
        # A diff over the Kernel's bound is cut in the Task, and a review is never of part of one: `live.answer` would
        # write a failed Result, and it would read as a case the reviewer failed.
        if any(o["kind"] == "diff" for o in the_task["omitted"]):
            raise Stop("diff_not_whole")
        # So is an issue over the texts' budget: asked without it, a case on PR-1 would read as the reviewer's failure.
        if any(o["kind"] == "issue" for o in the_task["omitted"]):
            raise Stop("issue_not_whole")
        if deadline - clock() < the_task["limits"]["seconds"] + VERSION_READS:
            raise Stop("unanswered")
        return live.answer(the_task, env, config, call, clock)
    return review


def step(env, root, workspace, call=None, clock=time.time):
    kept, _, _ = _planned(env, root, workspace)
    began = kept.get("planned_at")
    if not isinstance(began, int) or isinstance(began, bool):
        raise Stop("scratch_unreadable")
    return score(env, root, workspace, reviewer(env, kept["release"], began, call, clock))


if __name__ == "__main__":
    exit_with(step)
