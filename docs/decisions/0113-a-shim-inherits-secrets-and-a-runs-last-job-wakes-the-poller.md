# 0113. A shim inherits secrets, and a Run's last job wakes the poller

Status: accepted. Trial P-55, #196's ruling 9, run on 2026-11-01, failed its pass condition on two parts. These are their fixes, under the orchestrator's rulings of 2026-11-01. They amend #196's rulings 3, 4 and 5.

## Decision

| What | Decided | Because |
|---|---|---|
| A shim's secrets | Every shim's job holds `secrets: inherit`, in those words, directly after `uses:`. A named secret on a shim, those words quoted, and any other workflow that inherits are refused | P-55: a called job naming an environment read its secret only with `secrets: inherit` on its caller, and read nothing without it, where a job of the dispatched file read it. Under ruling 3's shim, `pass`, `run` and `apply` would each have started with an empty key |
| What that opens | The called Release file can name any secret of the repo or the org. An environment's secret stays behind that environment's branch policy, and a job naming no environment reads none of it. What holds the rest is that each called file is held word for word | Said plainly, since ruling 3 and L-37 refused this. The alternative is no reusable workflow for a job that holds a key, which gives up the channel |
| The wake-up | `wake`, a Run's last job in `run-jobs.yml`: `needs` the other three, `if: always()`, and dispatches the poller. `sf-run` leaves the poller's `workflows:`, which keeps `factory` and `ci` | P-55: a Run dispatched by the pass's token woke nothing by `workflow_run` when it ended, twice, where a person's woke the poller within seconds. `wake` brought the next pass 5 seconds after `apply` ended |
| The grant it widens | `actions: write` on `wake`, and on `lane`, run.yml's calling job, since a called job can be granted no more than its caller. §4.9 gave that to the poller's job alone. The token can also cancel or delete runs | `wake` holds no key, no checkout and no input, and its one step is one fixed line, held word for word. `run`, `verify` and `apply` each name their own grant, so the caller's gives them nothing. Each id is its file's alone |
| When it cannot | A dispatch that fails says so and exits 0, so it never fails a good Run. A force-cancelled Run, where `wake` did not run, and by the same reasoning a lost runner, not tried, leave the next pass to the backstop | The successor chain would see those too, at a pass about every 10 seconds for as long as a Run is open, up to about 180 for one Run. A wake costs one job of about 4 seconds |
| How the pass reads it | A pass `wake` started is a dispatch by the workflow's own token, so `started_by` is `successor`, as §7.3 has it | The run reads `github-actions[bot]`, event `workflow_dispatch` |
| What held | The lane: a second Run of an item started its `run` job 4 seconds after the first's `apply` ended, and another item's overlapped both. `if:`: `github.actor_id` reads 41898282 for the pass's token, true as a string and as a number; a person's dispatch, a Pause and a re-run are each skipped | As rulings 6 and 7 rest on them |
| What it answered | A run whose only job an `if:` skipped concludes `skipped`, on `workflow_dispatch` as on `schedule`, and so does the job. `job.workflow_sha` names a called workflow's own commit with no grant, as REST's `referenced_workflows` does; `github.workflow_sha` is the caller's. 8 successor dispatches ran with no stop, which is as far as it was asked | Ruling 14 and the records port's ruling 10 wait on these. Each job goes on checking out the tag, handing on the commit it got, until a change uses `job.workflow_sha` |

## Why

The trial ran the files' shape: the shims word for word but for the repo, the tag and the schedule, which would have started
passes nobody asked for; the called jobs with their needs, ifs, grants, outputs and environments, and probes for steps, since
the steps need keys. Both faults would have shown first on the live Factory, as a pass with no key and an approval that waits
for the backstop.

## Boundaries

| Boundary | Check |
|---|---|
| A shim holds `secrets: inherit` in those words, and only a shim inherits | `tests/test_tools.py::test_a_shim_holds_no_step_and_calls_the_release_at_its_channel`, `examples/workflows/invalid/shim.a-secret-handed-to-the-release.yml`, `examples/workflows/invalid/token.secrets-inherited.yml` |
| `wake` is the Run's last job, word for word, and only it and `lane` hold the pass's grant | `tests/test_tools.py::test_the_last_job_alone_of_the_runs_wakes_the_poller_holding_nothing_else` |
| What P-55 saw stands in its fixture | `tests/test_tools.py::test_what_the_runs_files_rest_on_is_as_p55_saw_it` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
