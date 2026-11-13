"""The eval job's run step: each case the set names given to the review Intent as a live Run is, and scored.

What is measured is what runs (design §3.14, issue 309's ruling 5). A case's Task is built by `harness/task.from_admission`,
the function a live Run's is built by, from the case's facts and its diff, with the Release's own configuration and the
Role's manifest; only the admission is the case's own, its content the case's facts give, and its Run a fresh id. It
is answered by `harness/run.answer`, as a live Run is: the same pin, the tier's limits, the read tools held to the case's
head, which `fetch` unpacked in `heads_place`, apart from the cases (issue 623), and the scrub (decision 0138); each head
is removed once its case is asked.
The step holds the model's credential and the CLI's path alone (`tools/check_workflows.py`), and stops starting cases
when the time it has left is less than a case's tier allows, so that the job ends before its own timeout: a case not
reached is unanswered, and the run fails.

Nothing of a case, a Task or a Result is printed: each Result is scored in this step's memory, and only the report,
`eval-report.json`, of hashes, verdicts, codes and causes, or of counts alone for a gate set, is written in the
workspace, by `score`. A gate set's Results are kept whole in the ledger, in the scratch alone, for `seal`, which
uploads nothing of them but their ciphertext (issue 612).
The CLI's call is watched for a case's cause alone: its exit, its subtype, how it says it ended and the vendor's status, or
that it timed out (decision 0131). A case the vendor or the network failed, as `transient` reads it, is asked again, at most
RETRIES more times and RETRY_WAIT apart, while the time left allows, and marked as retried (issue 615)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

from harness import engine, passes, run as live, task as tasks
from harness.eval import Stop, _planned, exit_with, heads_place, score, transient

# The seconds the job may spend before the last case is started, counted from when `plan` was made: the job's 120
# minutes (tools/check_workflows.py, EVAL_RUNNER) less eleven for the checkout before it, the seal, the uploads and judge
# after the step, and the slack of a runner's clock. The fetch and the install spend it, as the cases do.
BUDGET = 109 * 60
# What a case may cost beyond its tier's own seconds: the Engine asks the CLI its version before the call and after it,
# each within this many seconds (harness/engine.py).
VERSION_READS = 2 * 30
# How many more times a case the vendor or the network failed is asked, and the seconds before each: the CLI has already
# retried a 5xx or a lost connection for about three minutes by then, and an overload not at all (issue 615).
RETRIES = 2
RETRY_WAIT = 30
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def run_id() -> str:
    """A fresh Run id, in the form a pass mints one, for one case's Task alone."""
    return "r_" + "".join(ALPHABET[b % 32] for b in os.urandom(20))


def reviewer(env: dict, release: str, began: int, call=None, clock=time.time, heads=None, sleep=time.sleep):
    """The review Intent, as `assess` asks it: a case's `result/1`, or Stop with the code that says why there is none.
    Its Task is the case's, built as a live Run's; a case its Task is refused for is `not_this_set`, and one whose diff is
    over the bound `diff_not_whole`, and nothing is asked of the model: `harness.eval.case_fault` has told the rest apart. The
    configuration and the manifest are the checkout's own, the Release's, as a live Run's are. `began` is when `plan`
    was made, by `clock`, the runner's own: no case is started once less time is left of BUDGET than it may take. A case's
    head is the folder `<id>` in `heads`, as `fetch` unpacked it there (decision 0138, issue 623). A case the vendor or the
    network failed is asked again, by `sleep` after RETRY_WAIT, at most RETRIES times, each only with its time left;
    `review.retried` says how many times each case was, by its id (issue 615)."""
    config = dict(live.configuration(), release=release)
    with open(os.path.join(str(live.ROOT), "roles", "pr-review.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    deadline = began + BUDGET
    asked = call or live.cli_call
    seen, retried = {}, {}

    def watched(args, env, timeout, **given):
        """The CLI's call, as the Engine makes it, in the case's head where it reads one, with what it said of the case
        kept for its cause: its exit, the subtype its answer names, how it says it ended and the vendor's status, that it
        timed out, or the class of what the call raised. Nothing of the answer itself is kept. Of a case's several calls,
        the first that did not succeed is the one kept, since that is the one whose Result `passes.union` returns: one
        that erred, or that gave no answer to hold to a schema, the Engine's `no_answer`. An answer that fails its schema
        or another model's are the Engine's to tell after the call, and the watch keeps no word of them."""
        if args[1:] == ["--version"] or seen.get("erred") is True:
            return asked(args, env=env, timeout=timeout, **given)
        try:
            done = asked(args, env=env, timeout=timeout, **given)
        except subprocess.TimeoutExpired:
            seen.update(timed_out=True, erred=True)
            raise
        except Exception as err:
            seen.update(raised=type(err).__name__, erred=True)
            raise
        seen["exit"] = done.returncode
        said = engine._answer(done.stdout) if isinstance(done.stdout, str) else None
        seen["subtype"] = said.get("subtype") if isinstance(said, dict) else None
        seen["terminal_reason"] = said.get("terminal_reason") if isinstance(said, dict) else None
        seen["api_error_status"] = said.get("api_error_status") if isinstance(said, dict) else None
        seen["erred"] = done.returncode != 0 or not (isinstance(said, dict) and said.get("is_error") is False
                                                     and isinstance(said.get("structured_output"), dict))
        return done

    def review(case: dict) -> dict:
        seen.clear()
        facts = case["facts"]
        admit = {"role": case["role"], "intent": case["intent"], "content_id": facts.get("content_id")}
        # The issue a change serves, as a live Run reads it (adapters/texts.py), where the case holds one (decision 0110).
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
        # A case may make more than one call where a private replay switches an approach on (issue 581), each with its own
        # time and its own reads of the version.
        takes = len(passes.asked(the_task, passes.settings(config["harness"]))) * (the_task["limits"]["seconds"] + VERSION_READS)
        if deadline - clock() < takes:
            raise Stop("unanswered")
        head = os.path.join(str(heads), case["id"]) if heads is not None else None
        try:
            attempts = [live.answer(the_task, env, config, watched, clock, head=head)]
            while transient(attempts[-1], seen) and retried.get(case["id"], 0) < RETRIES \
                    and deadline - clock() >= RETRY_WAIT + takes:
                sleep(RETRY_WAIT)
                # The wait may have run long: another ask starts only with its whole time still left.
                if deadline - clock() < takes:
                    break
                retried[case["id"]] = retried.get(case["id"], 0) + 1
                seen.clear()
                attempts.append(live.answer(the_task, env, config, watched, clock, head=head))
            # What every attempt used is the case's, summed as a case's several calls are, on the last attempt's Result.
            return attempts[0] if len(attempts) == 1 else dict(attempts[-1], usage=passes._usage(attempts[::-1]))
        finally:
            if head is not None:
                shutil.rmtree(head, ignore_errors=True)
    review.seen, review.retried = seen, retried
    return review


def step(env, root, workspace, call=None, clock=time.time):
    kept, _, place = _planned(env, root, workspace)
    began = kept.get("planned_at")
    if not isinstance(began, int) or isinstance(began, bool):
        raise Stop("scratch_unreadable")
    return score(env, root, workspace, reviewer(env, kept["release"], began, call, clock, heads_place(env, workspace)))


if __name__ == "__main__":
    exit_with(step)
