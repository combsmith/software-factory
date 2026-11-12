# 0200. A Run's outcome says whether its Engine step started

Status: accepted. The Factory Builder's ruling of 2026-11-12 on "A Run that ended environment does not use up the item's run ceiling" (issue 757): before a Run that ended `environment` may be counted apart from the Run ceiling, the run record must say whether the Run reached the model. This record adds that fact alone. What counts toward which bound is the next record's.

## Decision

| What | Decided | Because |
|---|---|---|
| The signal | The `run` job hands on its Engine step's outcome as the output `engine`, `${{ steps.engine.outcome }}` | GitHub skips a step once a step before it has failed, so a Run whose CLI install or read failed shows the Engine step `skipped`. That was every Run of the runner DNS outage of 2026-11-11. The step's outcome is GitHub's own word, set by no Factory code, and one of four |
| What `apply` writes | `outcome/1`'s `engine_started`: false where the output is `skipped`; true where it is `success`, `failure` or `cancelled`; left out where it is anything else or missing | A Run whose Engine step ran may have spent on the model, whatever ended it. One whose output cannot be read is read as one that may have: the field is left out, never false |
| Where it is written | Every `outcome/1` `apply` writes, whatever its outcome. The fallback the last step writes, `apply_failed`, and the reader's `release_moved` carry none | Only `apply` is given the run job's outputs (`NEEDS`) |
| The run record | `engine_started`, a true or a false alone, as the failed Run's outcome said it, and absent where the outcome said nothing. The records port reads it with the outcome, and keeps it with a kept outcome from the last pass record, the one `known` keeps a fault from | An outcome is written once for its attempt, so what it said stands. Kept outcomes are not read again, so the field must be kept with them, or a later pass would lose it |
| The workflow check | A job may hand on a step's `outcome` as an output, beside a step's own output | It is one of four words, so it cannot become a command, as `tools/check_workflows.py`'s expression rule requires |
| What reads it | Nothing yet: the Kernel's counting is the next record's | One change, one rule |

## Why

`environment` covers a CLI install that failed, as in the outage, and a Run stopped at its step limit after the model read the item. Both reach `apply` as `run_failed`. A count that cannot tell them apart either gives up the cost ceiling to a slow item, or holds every item after an outage. Whether the Engine step started is the one thing that splits them, and only the `run` job knows it.

It fails closed: a Run says it did not start the Engine only where GitHub said the step was skipped. A job killed before it handed on its outputs, an output missing, or a word GitHub has not given before all leave the field out. An older outcome, written before this change, has none.

It costs one thing, accepted. `outcome/1` admits no field it does not name, so after a rollback of `next` to a Release cut before this change, that Release reads a newer Run's outcome as no `outcome/1`, and its list of Runs is not whole until those Runs leave the window. Pass records' run records already carry such a field, `began_at` (decision 0193). Not verified on GitHub: that the job output reads `skipped` for a step skipped after an earlier one failed. GitHub's documentation says so, and if it reads otherwise the field is left out.

## Boundaries

| Boundary | Check |
|---|---|
| `apply` says the Engine did not start only where the run job hands on `skipped`, that it started where it hands on any word GitHub gives a step that ran, and nothing otherwise; the live workflow hands the Engine step's outcome on, and gives `apply` every job's results and outputs | `tests/test_steps.py::test_apply_says_whether_the_engine_step_started`, `harness/apply_step.py`, `.github/workflows/run-jobs.yml`, `tools/mutants.py`, mutant: "the run job hands on nothing of its Engine step", mutant: "a skipped Engine step says it started", mutant: "an Engine step that ran says nothing", mutant: "any word but skipped says the Engine started", mutant: "an Engine step cancelled says nothing", mutant: "an Engine step that failed says nothing", mutant: "an Engine step that succeeded says nothing", mutant: "apply leaves out whether the Engine started", mutant: "apply says the Engine did not start where the job said nothing" |
| A job may hand on a step's outcome, and nothing else of a step but its own output | `tests/test_tools.py::test_a_runs_lane_is_its_item_on_the_job_and_cancels_nothing_running`, `tools/check_workflows.py`, `tools/mutants.py`, mutant: "a job's output may be any of its step's", mutant: "a job may not hand on a step's outcome" |
| An outcome's `engine_started` is handed on where the caller asks and the outcome says, and an outcome that says it otherwise is no `outcome/1` | `tests/test_adapters.py::test_a_runs_outcome_is_read_from_its_one_file_and_held_to_outcome_1`, `adapters/artifacts.py`, `tools/mutants.py`, mutant: "an outcome hands on nothing of the Engine", mutant: "a caller that does not ask is handed the Engine" |
| The run record carries it as the outcome said it, and keeps it with a kept outcome, by its own Run and attempt: the last record's word alone, a true or a false alone, and nothing for a Run the record lists twice | `tests/test_adapters.py::test_whether_the_engine_started_is_read_with_the_outcome_and_kept_by_its_run_and_attempt`, `adapters/records.py`, `tools/mutants.py`, mutant: "a Run's outcome read says nothing of its Engine", mutant: "a kept outcome keeps nothing of the Engine", mutant: "a kept outcome takes the Engine of another Run", mutant: "anything said of the Engine is kept", mutant: "what a record says of the Engine twice is kept", mutant: "the earlier record's word of the Engine is read", mutant: "a key that is no Run or no start is kept for the Engine" |
| The pass's entry hands the records port what the records before said of the Engine, from pass records alone, each from before the pass | `tests/test_controller.py::test_the_entry_gathers_what_reconciliation_reads`, `controller/__main__.py`, `tools/mutants.py`, mutant: "the entry keeps nothing of the Engine", mutant: "the entry keeps the Engine from records as they were downloaded" |
