# 0057. A shim calls the Release and holds nothing else, and the poller wakes on a workflow's end and reads nothing of it

Status: accepted. A working ruling of 2026-10-21 on "Workflows: the frozen entry shim, the poller, the Run's three jobs and the nudge, each held to its shape" (issue 196), its rulings 3 to 5, built as its PR 1, the rules before any file they hold exists; the Maintainer may overturn it in review. It rewords a row of `docs/decisions/0006-one-release-one-path.md` on thin callers, and widens a row of `docs/decisions/0043-a-scheduled-tick-is-a-backstop-of-hours-the-relay-carries-w-2-and-a-pass-records-what-started-it.md` on what the poller listens to.

## Decision

| What | Decided | Because |
|---|---|---|
| What a shim is | Every workflow on `schedule`, `workflow_dispatch` or `workflow_run`, since each of those events runs the default branch's own file. A workflow on `push` alone runs the pushed commit's own file and is not one | A file on `main` is in no Release, so no Release reviews it and no channel move rolls it back (0006) |
| Its shape | Each job holds `uses`, `permissions` and `concurrency`, and may hold `if` and `with`; nothing else. It calls one file of this repo at the channel, `factory/v0-next`, never a local path. A `with:` value is `${{ inputs.<the same name> }}`. Above its jobs it holds `name`, `on`, `permissions` and `jobs`, and run.yml alone `run-name`. A job passes its inputs one to a line | Holding it to a call and an `if:` leaves nothing in it to roll back |
| Frozen | Each shim is held word for word by its hash, in `SHIMS`, as `.github/workflows/ci.yml` is in `EXEMPT`. A change fails until the same pull request records the new hash, and `.github/` is the Maintainer's to approve | A shim changes the Factory's entry for every Release at once |
| Environments | Only a workflow on `workflow_call` alone names an environment. No shim, no push's job and no pull request's job is handed a key | A pull request's job runs the head's code, and a shim runs the default branch's |
| The eval job | eval.yml runs main's own file on a dispatch, since it judges main's commit, and is spared the shim rule for its own shape check, `eval_problems` (decision 0053), which holds its one job and every step | Its code at the judged commit is what is judged |
| The poller | poller.yml alone runs on `workflow_run`. It wakes on the completion alone (`types: [completed]`) of the workflows it names, never its own; its dispatch takes no input; nothing in it, nor in the pass.yml it calls, reads the `github` context, by a dot, an index or whole, in any case | A fork can name its own run as any workflow, so what woke the poller says nothing; a pass learns what started it from its own run record (0043) |
| The nudge | The poller wakes on the ends of `factory`, `ci` and `sf-run`: every pull request, every merge and every Run's end. There is no nudge workflow on `pull_request` or `push` | Such a job would need `actions: write`, and on `pull_request` it would run the head's own code with a token that can delete run records |
| The one write | No job anywhere is granted a write but the pass job its `actions: write`, which starts the Runs and the successor with the job's own token. The job id `pass` is poller.yml's and pass.yml's alone | §4.9 gives the start of Runs to the poller job alone; the check read the top-level grant only, and a job's write passed |

## Why

The Factory's workflow files make it live, so their rules land first and can fail before any file they hold exists. This PR adds no workflow: pass.yml and the Run's jobs come in the story's second pull request, called by nothing until the third's shims, which land under a Pause.

## Boundaries

| Boundary | Check |
|---|---|
| A shim holds no step and calls the Release at its channel; only a called workflow names an environment | `tests/test_tools.py::test_a_shim_holds_no_step_and_calls_the_release_at_its_channel` |
| Every shim calls the one channel | `tests/test_tools.py::test_every_shim_calls_one_channel` |
| A shim is held word for word | `tests/test_tools.py::test_a_shim_is_held_word_for_word` |
| Only the poller runs on `workflow_run`, on a completion of what it names, never its own, with no input, reading nothing of the run | `tests/test_tools.py::test_only_the_poller_runs_on_workflow_run` |
| The pass job alone is granted a write | `tests/test_tools.py::test_the_pass_job_alone_is_granted_a_write` |
| Each rule has a counter-example that breaks it and no other | `examples/workflows/invalid/shim.a-step-in-the-shim.yml`, `examples/workflows/invalid/wake.woken-by-its-own-end.yml`, `examples/workflows/invalid/permissions.actions-write-beyond-the-pass.yml` |
| The poller's shim, as ruling 4 gives it, is held | waiting on `.github/workflows/poller.yml` |
