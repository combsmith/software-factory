# 0114. A Run GitHub started no job of counts toward the automatic pause, under its own name

Status: accepted. The Factory Builder's ruling of 2026-11-01 on "Many Runs with no outcome across items raise no alert: a skipped dispatch or a broken Release ends in Holds that name no cause" (issue 456).

## Decision

| What | Decided | Because |
|---|---|---|
| The fact | The records port sets `never_ran: true` on a run record where GitHub said `startup_failure`, or `skipped` on a first attempt. Nothing else has it, and `facts/1` does not change | Each already reads `cancelled`, as a person's cancel and a concurrency group's do, which is what hid them. The port is the one place that still holds GitHub's word |
| The pause | `automatic_pause` counts such a Run as a fault, by the same rule as an `environment` outcome: 3 faults on 2 items in the hour, since a Run last succeeded | An alert alone would still let each open item run to a `run_ceiling` Hold, each needing a writer, and section 3.10 says one cause must never become fifty Holds. The pause stops the dispatches. The Kernel reads it as `model_deferred_until`, as it does today, so it needs no change |
| The name | One new alert, `runs_never_started`, and the same word in health's `by`, in place of `environment` where only such Runs hold the pause, beside it where both do | Such a Run is not known to be an outage, and the Maintainer needs the cause: a shim's `if:` or a broken Release, not GitHub |
| Attempts and the ceiling | Unchanged. Such a Run is still no attempt, and still counts toward the Run ceiling | Decisions 0049 and 0109 read it so, and only the pause is added |

## Why

Without a flag the pause could not see these Runs at all, since they write nothing. A person's cancel must not trip a pause, so counting every `cancelled` was never open.

It costs two things, both accepted. A person setting `FACTORY_PAUSED` while Runs are being dispatched could skip enough of them to trip it, needing 3 Runs on 2 items in that moment, and clearing the Pause would then still defer Runs for up to an hour, under this alert. And the pause clears only by time, so a lasting broken Release pauses, tries a few Runs each hour and pauses again, as a lasting `environment` fault does. Each such hour spends a little of those items' Run ceilings. It spends no model.

## Boundaries

| Boundary | Check |
|---|---|
| `startup_failure` and a first attempt `skipped` say they never ran; a re-run skipped, a cancel, a failure and a Run in flight do not | `tests/test_adapters.py::test_a_run_github_started_no_job_of_says_so_and_no_other_does` |
| Such Runs pause Admission by the same rule and are named `runs_never_started`; too few, one item's, or a success after them hold nothing; a cancel with no flag trips nothing; both causes are named where both hold; it stops no act | `tests/test_controller.py::test_runs_that_never_ran_pause_admission_and_are_named_as_themselves` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
