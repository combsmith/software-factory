"""The eval job's run step: each case the set names given to the review Intent as a live Run is, and scored.

What is measured is what runs (design §3.14, issue 309's ruling 5). A case's Task is built by `harness/task.admitted`,
the function a live Run's is built by, from the case's facts and its diff, with the Release's own configuration and the
Role's manifest; only the admission is the case's own, its content the case's facts give, and its Run a fresh id. It
is answered by `harness/run.answer`, as a live Run is: the same pin, the tier's limits, `--tools ""` and the scrub.
The step holds the model's credential and the CLI's path alone (`tools/check_workflows.py`), and stops starting cases
when the time it has left is less than a case's tier allows, so that the job ends before its own timeout: a case not
reached is unanswered, and the run fails.

Nothing of a case, a Task or a Result is printed or written in the workspace: the Results stay in the scratch
directory's memory, and only `eval-report.json` is written there, by `score`."""
from __future__ import annotations

import json
import os
import time

from harness import run as live, task as tasks
from harness.eval import Stop, _planned, exit_with, score

# The seconds this step may spend: the job's 120 minutes less what checkout, plan, fetch and the install take, and the
# upload and judge after it.
BUDGET = 105 * 60
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def run_id() -> str:
    """A fresh Run id, in the form a pass mints one, for one case's Task alone."""
    return "r_" + "".join(ALPHABET[b % 32] for b in os.urandom(20))


def reviewer(env: dict, release: str, call=None, clock=time.monotonic):
    """The review Intent, as `assess` asks it: a case's `result/1`, or Stop with the code that says why there is none.
    Its Task is the case's, built as a live Run's; a case whose facts do not name the content its diff is
    (`content_id`, the sha256 of the diff), or of no review, is `not_this_set`, and nothing is asked of the model. The
    configuration and the manifest are the checkout's own, the Release's, as a live Run's are."""
    config = dict(live.configuration(), release=release)
    with open(os.path.join(str(live.ROOT), "roles", "pr-review.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    deadline = clock() + BUDGET

    def review(case: dict) -> dict:
        facts = case["facts"]
        admit = {"role": case["role"], "intent": case["intent"], "content_id": facts.get("content_id")}
        try:
            the_task = tasks.admitted(admit, facts.get("item"), run_id(), facts, [], manifest, [], config,
                                      case["diff"].encode("utf-8"))
        except (tasks.Refused, AttributeError, KeyError, TypeError):
            raise Stop("not_this_set") from None
        if deadline - clock() < the_task["limits"]["seconds"]:
            raise Stop("unanswered")
        return live.answer(the_task, env, config, call, clock)
    return review


def step(env, root, workspace, call=None, clock=time.monotonic):
    kept, _, _ = _planned(env, root, workspace)
    return score(env, root, workspace, reviewer(env, kept["release"], call, clock))


if __name__ == "__main__":
    exit_with(step)
