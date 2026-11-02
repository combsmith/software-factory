# 0111. A first attempt an `if:` skipped is no attempt, and a later attempt it skipped is one

Status: accepted. The Factory Builder's rulings of 2026-10-31 on the first reading of ruling 10 of "Workflows: the frozen entry shim, the poller, the Run's three jobs and the nudge, each held to its shape" (issue 196), once the reads found the plain reading unsafe.

## Decision

| What | Decided | Because |
|---|---|---|
| A first attempt `skipped` | Reads `cancelled`: no attempt, read as `superseded`, and the Run ceiling bounds it | It ran no Role and left no outcome, like a job that never started. The word unread would leave the list not whole for as long as GitHub serves the row, and admit nothing anywhere |
| A row `skipped` on a later attempt, or whose attempt cannot be read | Reads `failure`, an attempt, with its outcome read as any failed Run's | The shim's `if:` holds `github.run_attempt == '1'`, so a re-run is skipped, and the list shows only the latest attempt (`trials/P-27.json`). Read as no attempt, a person's re-run of a Run that failed would erase its attempt: three failures held `attempts_exhausted` were admitted again, with nothing on the timeline |
| A re-run of a Run that succeeded | Reads `failure` too, so its review is asked again and an attempt is spent | Accepted. The row cannot tell it apart, it needs write access to cause, and it fails safe. Reading attempt one from GitHub would tell them apart, but adds a read with no fixture |
| Leaving a later attempt's row not whole | Refused | One person's re-run would stop all admission for 90 days, which is what this reading ends |
| `startup_failure` | Stays `cancelled`. The same ruling 10's other reading, `environment`, is not built | Decision 0049 reads it so, by a working ruling written beside ruling 10; neither names the other, and this settles it in 0049's favour |

## Why

The gap this accepts: a cause that skips every dispatch, or a broken Release that gives every Run `startup_failure`, writes no `environment`. So no automatic pause and no alert names it, and each open item takes `max_runs_per_item` Runs and then a `run_ceiling` Hold, which a writer clears item by item. It fails safe and spends no model. Ruling 9's trial checks the shim's `github.actor_id` comparison before the shims go live, and an alert is the follow-up "Many Runs with no outcome across items raise no alert: a skipped dispatch or a broken Release ends in Holds that name no cause" (issue 456).

What waits on the trial: the word itself is read from this repo's own `.github/workflows/release.yml`: 106 `schedule` runs whose only job an `if:` skipped read `completed`, `skipped`. A canary's Run shim on `workflow_dispatch`, attempt 1, read the same for its run and its job `lane` (run 41266877465), which no fixture holds until ruling 9's canary trial lands. That a re-run the `if:` skips concludes `skipped` is unproven, and waits on that trial too. If GitHub sends another word, the row leaves the list not whole until this mapping follows the trial.

## Boundaries

| Boundary | Check |
|---|---|
| A first attempt `skipped` is no attempt; a later one, or one whose attempt cannot be read, is an attempt with its outcome read; the Run ceiling counts each | `tests/test_adapters.py::test_a_first_attempt_an_if_skipped_is_no_attempt_and_a_later_one_is_an_attempt` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
