# 0114. A Run GitHub started no job of counts toward the automatic pause, under its own name

Status: accepted. The Factory Builder's ruling of 2026-11-01 on "Many Runs with no outcome across items raise no alert: a skipped dispatch or a broken Release ends in Holds that name no cause" (issue 456).

## Decision

| What | Decided | Because |
|---|---|---|
| The fact | The records port sets `never_ran` on a run record, to GitHub's word, where it said `startup_failure`, or `skipped` on a first attempt. Nothing else has it, and `facts/1` does not change | Each already reads `cancelled`, as a person's cancel and a concurrency group's do, which is what hid them. The word is kept because the two have different remedies: a shim's `if:`, or the Release |
| The pause | `automatic_pause` counts such a Run with no outcome as a fault, by the same rule as an `environment` outcome: 3 faults on 2 items in the hour, since a Run last succeeded | An alert alone would let each open item reach its `run_ceiling` Hold within minutes, and section 3.10 says one cause must never become fifty Holds. The pause slows the dispatches to a few each hour, which gives a person hours to act. It does not stop them: see the costs below. The Kernel reads it as `model_deferred_until`, as it does today, so it needs no change |
| The name | One new alert, `runs_never_started`, and the same word in health's `by`, in place of `environment` where only such Runs hold the pause, beside it where both do. Health's `faults` lists each such Run by GitHub's word | Such a Run is not known to be an outage, and the Maintainer needs the cause: a shim's `if:` or a broken Release, not GitHub |
| How long it is named | The alert stands, by the pause's own counts and with no window, until a Run succeeds. The pause itself still lapses by time | The pause lapses hourly while the cause goes on. Tied to the pause, the tracking issue would close and reopen each hour, and the name would be gone by the time every item held |
| Attempts and the ceiling | Unchanged. Such a Run is still no attempt, and still counts toward the Run ceiling | Decisions 0049 and 0109 read it so, and only the pause is added |

## Why

Without a flag the pause could not see these Runs at all, since they write nothing. A person's cancel must not trip a pause, so counting every `cancelled` was never open.

It costs three things, all accepted. **A lasting cause still reaches every item's Hold.** The pause delays this and does not stop it: at 10 Runs per item and one try an hour, about 9 hours, measured through a pass, and each Hold still needs a writer. It spends no model, and the alert now names the cause throughout, so a person away overnight finds the Holds and the reason. Stopping the tries would leave nothing to show the cause is gone. **A person setting `FACTORY_PAUSED`** while Runs are being dispatched could skip enough of them to trip it, needing 3 Runs on 2 items in that moment, and clearing the Pause would then still defer Runs for up to an hour, under this alert until a Run succeeds. **Rows not yet proven:** no fixture holds a `startup_failure` row, and if GitHub lists one under the workflow's name and not its run-name, it reads as an unnamed Run and `runs_unnamed` is raised, which also fails safe but does not name this cause. A later trial must read one. An outsider has no route to this pause that the security read could find: a counted row needs the pass's own token on the default branch.

## Boundaries

| Boundary | Check |
|---|---|
| `startup_failure` and a first attempt `skipped` say they never ran, each in its own word; a re-run skipped, a cancel, a failure and a Run in flight do not | `tests/test_adapters.py::test_a_run_github_started_no_job_of_says_so_and_no_other_does` |
| Such Runs pause Admission by the same rule and are named `runs_never_started`, each shown by GitHub's word; too few, one item's, or a success after them hold nothing; the name outlasts the pause until a Run succeeds; a cancel with no flag trips nothing; both causes are named where both hold, and an outage a success ended is not; a word beside an outcome is the outcome's; it stops no act | `tests/test_controller.py::test_runs_that_never_ran_pause_admission_and_are_named_as_themselves` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
