# 0133. The queue act's job holds the queue App's key, the job's reads and the Pause, word for word

Status: accepted. The Factory Builder's ruling of 2026-11-03 on the queue step of "A narrow queue App, combsmith-sf-queue, enqueues and dequeues with contents and pull-request write alone (P-2)" (issue 381), part of "Epic: slice 1, first approval. A Release on next reviews a pull request to this repo, and the machine user's approval stands" (issue 182): its third part, the workflow, of three. It names `workflows.queue`, which decisions 0128 and 0130 left null.

## Decision

| What | Decided | Because |
|---|---|---|
| The job | `.github/workflows/queue-job.yml`, called by the queue shim at the Release's channel, is held word for word as the approving act's is (decision 0066): one job, `queue`, on `factory-queue`, checking out the Release, never the item's code; its step `harness.queue_step`; the applied and outcome records uploaded and the Run's outcome left whatever failed; and a `wake` that holds nothing and dispatches the poller | The same path as the approving act's, so nothing new is trusted |
| Its credentials | The step holds `QUEUE_APP_KEY`, the job's own token with `actions: read` and `contents: read` alone, which finds the pass record among the poller's runs, and `FACTORY_PAUSED` from the `vars` context, which the step reads before it mints the App's token | The step needs each, and nothing else (decision 0130) |
| Its key's one file | `QUEUE_APP_KEY` and `factory-queue` are named in `.github/workflows/queue-job.yml` alone, as each key is in its one file (decision 0035); the credential table lists that file for the key | No other job holds the key |
| The grants it widens | `.github/workflows/queue-job.yml` may hold the `wake` job and the shim queue.yml the `lane` job, the two jobs granted `actions: write` beside the run's and the approving act's (decision 0115) | A Run the pass's token started wakes nothing when it ends (P-55) |
| What it names | `config/controller.json` names `workflows.queue`, queue.yml. Nothing is dispatched while `accounts.queue` is null, which waits on the users read P-39's re-read records (decision 0128) | The file is named before the account, so that naming the account is the one change that turns it on |
| What is not built | The shim queue.yml, beside run.yml and approve.yml, which go live together; naming `accounts.queue`; and reconciliation's matching of the queue App's writes to the queue job's record | The shims are held by their hashes once live, and the account by its trial |

## Why

Decision 0128 made each queue act a dispatched Run, and decision 0130 built the step that carries it out. This is the job that runs the step, held as the approving act's is so that a change to it is a change to this record.

## Boundaries

| Boundary | Check |
|---|---|
| `.github/workflows/queue-job.yml` is the queue act's one job word for word: its key, the job's reads, the Pause, its own environment, the Release checked out, the outcome left whatever failed, and its wake | `tests/test_tools.py::test_the_queue_acts_job_holds_its_key_the_jobs_reads_and_the_pause_word_for_word` |
| Its key and environment stand in no other file; its wake and the shim's lane are the only other jobs granted `actions: write` | `tests/test_tools.py::test_the_queue_acts_job_holds_its_key_the_jobs_reads_and_the_pause_word_for_word`, `tests/test_tools.py::test_the_last_job_alone_of_the_runs_wakes_the_poller_holding_nothing_else` |
| The named workflow permits no dispatch while the queue App's account is null | `tests/test_effects.py::test_a_queue_act_is_dispatched_to_the_queue_workflow_once_it_is_named` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
