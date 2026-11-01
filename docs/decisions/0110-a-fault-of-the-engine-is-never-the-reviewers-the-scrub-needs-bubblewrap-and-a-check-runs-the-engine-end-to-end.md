# 0110. A fault of the Engine is never the reviewer's, the scrub needs bubblewrap, and a check runs the Engine end to end

Status: accepted. The Builder's rulings of 2026-10-31, after the second eval, run 41256743435 on the commit 37355b0, read 42 cases as `case_failed` and 2 as `diff_not_whole` in 8 seconds, with no model having run.

## Decision

| What | Decided | Because |
|---|---|---|
| The cause | The Engine sets `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` (decision 0050), and the CLI at the pin refuses to start with it set and no bubblewrap on the runner: exit 1 in 0.1 s, saying "bubblewrap is required". `ubuntu-24.04` does not have it | Read on a real runner, the canary's run 41266395422 with it installed: `completed`, one Finding, five coverage entries, scored, 10 s, $0.07 |
| Why no trial saw it | The workflows of P-50 and P-51 installed bubblewrap, and P-13 ran on a Mac. `.github/workflows/run-jobs.yml` lacked it as well, so every live Run would have failed the same way. That is read from the workflow, and no live Run was tried | What a trial's workflow installs is part of what it measured, and nothing compared the two |
| The fix | `sudo apt-get install -y --no-install-recommends bubblewrap` is the last line of `CLI_INSTALL_RUN`, in `tools/check_workflows.py`, which holds `.github/workflows/eval.yml` and `.github/workflows/run-jobs.yml` word for word. The scrub stays on | Decision 0050 stands: turning the scrub off would pass the eval by removing what a Run is promised |
| The exception to "nothing is installed" | This is the one apt fetch here. It is unversioned, and Ubuntu's signature on its index holds what arrives. `tools/check_repo.py` is unchanged: what it holds is this repo's own dependencies. The `install` rule of `tools/check_workflows.py` is met as the CLI's is, by the block being held word for word | A pinned version disappears from the archive when a fix replaces it, and a Run would fail on Ubuntu's schedule |
| Before anything is in the job | apt runs as root, so the block comes before anything worth reading. In `.github/workflows/run-jobs.yml` it already came before the reader. In `.github/workflows/eval.yml` it moves from after the fetch to before it, in `EVAL_ORDER`, so the token has not been used and no case is on the disk | A package's own scripts run as root, and no step's `env:` would hold them away from the scratch |
| Telling the faults apart | `ENGINE_FAULTS`, in `harness/eval/__init__.py`, names six reasons a `failed` Result can carry that are no answer of the reviewer's: `credential_missing`, `engine_version`, `engine_failed`, `engine_timeout`, `task_too_large` and `rubric_unreadable`. Such a case is `unreadable` by that reason, and `verdict` reads the run as `engine_fault` ahead of `case_failed`. The gate stays closed | 42 cases read as `case_failed` said the reviewer was wrong 42 times, of a reviewer that had not run. The code says nothing of what a case expected, so the report may carry it (decisions 0078 and 0099) |
| The check | `harness/eval/canary.py`, run by a workflow of the canary repo on a checkout of `main`, weekly and before each cut, for one model call, about $0.07. `install` runs `CLI_INSTALL_RUN` itself, and `review` asks `harness.eval.assess` about the repo's example case. It is red unless the CLI answered `completed` | A copy of the block in the canary's workflow would stay green when a line was taken from `main`. The canary is reached by the organisation's model credential, and what the check does there touches nothing of this repo |
| What it prints | When the CLI fails, the last 600 characters of what it said. The eval job's steps may not, as they hold cases; this one holds the repo's example alone. A case the model answered and missed is green here | That line is what named the cause. Whether the model is any good is the eval's question, and a miss here would make the check flaky |

## Why

The eval read a broken Engine as a bad reviewer, and the first anyone could learn of the Engine's state was the eval itself. Each half hid the other: the codes said the reviewer failed, and nothing ran the Engine between a merge and a dispatch.

## Limits

- Before each cut is a step of the runbook. `release/cut.py` does not read the canary.
- A schedule in a public repo is turned off by GitHub after 60 days with no activity there, and a failed scheduled run notifies only whoever last edited the schedule.
- The canary's workflow lives in the canary repo, so no check here holds its shape.
- `apt-get install` is run with no `apt-get update`, as the probe ran it, in 4.4 s, version 0.9.0-1ubuntu0.3. An index on the image older than the archive would fail the step, and closed; the weekly run is where that would show first.
- The time a real case takes is not settled by one synthetic review: 110 minutes for 44 cases allows about 2.5 minutes each.

## Boundaries

| Boundary | Check |
|---|---|
| Each fault of the Engine or the Factory is `unreadable` by its own code and the run says `engine_fault`; the reviewer's own failure stays `case_failed` | `tests/test_evals.py::test_a_fault_of_the_engine_or_the_factory_is_not_the_reviewers` |
| The eval job's install holds bubblewrap and comes before its fetch | `tests/test_evals.py::test_the_eval_workflow_names_each_credential_in_one_step_alone` |
| The Run's jobs hold bubblewrap | `tests/test_tools.py::test_the_runs_jobs_keep_each_key_apart_and_always_leave_the_outcome` |
| The check installs the block the jobs hold, at the pin and by its checksum | `tests/test_evals.py::test_the_canary_installs_the_block_the_jobs_hold` |
| The check is red unless the CLI answered, and says the end of what a failing CLI said | `tests/test_evals.py::test_the_canary_is_red_unless_the_cli_answered` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
