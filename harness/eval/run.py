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

import hashlib
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
# The reasons the Engine fails a Result for by its call alone: one that erred, timed out, or gave no answer to hold.
CALL_FAILED = ("engine_failed", "engine_timeout", "no_answer")
# What the Engine asks the CLI for one Result: its version, and where it goes on to its call, the call and its version
# again (V and C). Anything more was asked for more Results than one, whether each made its call or failed before it.
ONE_ASK = ("V", "VCV")
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def recorded(case: dict, run: str, config: dict) -> tuple:
    """`(advised, config)` for a case: where a private replay's case carries what each advisory reader said of its head,
    as recorded, each Result stamped with the case's Run and Release, with its digest, and a copy of the configuration
    that switches the hand-over on, so the case's Task is handed those reads as a live Run's would be (issue 948);
    else none, and the configuration as it is, which hands none. Nothing here asks a reader: a held-out case carries
    no reads, and a replay's come from its own set."""
    said = case.get("advisory")
    if said is None:
        return None, config
    advised = {}
    for lens, result in said.items():
        data = (json.dumps(dict(result, run=run, release=config["release"]), indent=2, sort_keys=True, allow_nan=False)
                + "\n").encode()
        advised[lens] = (data, ("sha256:%s\n" % hashlib.sha256(data).hexdigest()).encode())
    return advised, dict(config, harness=dict(config["harness"], **{tasks.HAND_OVER: True}))


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
    seen, retried, calls = {}, {}, []

    def watched(args, env, timeout, **given):
        """The CLI's call, as the Engine makes it, in the case's head where it reads one, with what it said of the case
        kept for its cause: its exit, the subtype its answer names, how it says it ended and the vendor's status, that it
        timed out, or the class of what the call raised. Nothing of the answer itself is kept. Of a case's several calls,
        the first that did not succeed is the one kept: one that erred, or that gave no answer to hold to a schema, the
        Engine's `no_answer`. An answer that fails its schema or another model's are the Engine's to tell after the
        call, and the watch cannot: `own` leaves the word out where it may be another call's."""
        calls.append("V" if args[1:] == ["--version"] else "C")
        if args[1:] == ["--version"] or seen.get("erred") is True:
            return asked(args, env=env, timeout=timeout, **given)
        try:
            done = asked(args, env=env, timeout=timeout, **given)
        except subprocess.TimeoutExpired:
            # What an earlier call that succeeded said is not this one's: the call that failed is kept alone.
            seen.clear()
            seen.update(timed_out=True, erred=True)
            raise
        except Exception as err:
            seen.clear()
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

    def own(result: dict) -> dict:
        """One ask's Result, with the watch's word left beside it only where it is the word of the call that Result came
        of. `passes.union` returns the first Result of several that did not complete. Where that one failed by its call
        alone, CALL_FAILED, every call before it succeeded, so the first that did not is its own, and its word is kept.
        Failed any other way, or completed, the Result may be of a call the watch saw succeed, or of none, and the word
        kept a later call's: it is left out, never reported as that Result's cause (issue 865). Where one Result alone
        was asked for, ONE_ASK, the word is its own."""
        if "".join(calls) not in ONE_ASK and result.get("reason") not in CALL_FAILED:
            seen.clear()
        calls.clear()
        return result

    def review(case: dict) -> dict:
        seen.clear()
        calls.clear()
        facts = case["facts"]
        admit = {"role": case["role"], "intent": case["intent"], "content_id": facts.get("content_id")}
        # The issue a change serves, as a live Run reads it (adapters/texts.py), where the case holds one (decision 0110).
        texts = [{"id": "issue:%d" % case["issue"]["number"], "by": case["issue"]["by"], "body": case["issue"]["body"]}] \
            if "issue" in case else []
        run_ = run_id()
        advised, told = recorded(case, run_, config)
        try:
            the_task = tasks.from_admission(admit, facts.get("item"), run_, facts, texts, manifest, [], told,
                                      case["diff"].encode("utf-8"), advised)
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
            own(attempts[-1])
            while transient(attempts[-1], seen) and retried.get(case["id"], 0) < RETRIES \
                    and deadline - clock() >= RETRY_WAIT + takes:
                sleep(RETRY_WAIT)
                # The wait may have run long: another ask starts only with its whole time still left.
                if deadline - clock() < takes:
                    break
                retried[case["id"]] = retried.get(case["id"], 0) + 1
                seen.clear()
                attempts.append(live.answer(the_task, env, config, watched, clock, head=head))
                own(attempts[-1])
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
