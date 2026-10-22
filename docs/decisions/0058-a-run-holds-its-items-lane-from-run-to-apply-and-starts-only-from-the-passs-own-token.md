# 0058. A Run holds its item's lane from run to apply, and starts only from the pass's own token while nothing is Paused

Status: accepted. A working ruling of 2026-10-21 on "Workflows: the frozen entry shim, the poller, the Run's three jobs and the nudge, each held to its shape" (issue 196), its ruling 6, built as the rules before the Run's shim exists; the Maintainer may overturn it in review. It adds to `docs/decisions/0057-a-shim-calls-the-release-and-holds-nothing-else-and-the-poller-wakes-on-a-workflows-end-and-reads-nothing-of-it.md`, whose shim rule the Run's shim keeps, and to `docs/decisions/0003-one-controller-admits-every-run.md`, whose lane and Pause it holds in the workflow.

## Decision

| What | Decided | Because |
|---|---|---|
| The lane | A job that calls the Run's jobs, run-jobs.yml, holds one concurrency group for each Work item, exactly `${{ inputs.item }}`, on the job, with `cancel-in-progress: false` | It holds from `run` to `apply`, and a newer Run on the item waits rather than cancel one between its Result and its apply (§2.4 rule 4, §7.3, P-44) |
| Three expressions more | An expression may stand whole as a run's name, `${{ inputs.name }}`, as the lane, `${{ inputs.item }}`, and as a job's output of one of its steps, `${{ steps.<id>.outputs.<name> }}`; with no text around any of them | Each is the whole of a value no text from outside can become a command in |
| The Run's shim | run.yml is the Run's shim word for word: three required inputs, `name`, `item` and `pass`; its run named by `name`; one job, `lane`, calling run-jobs.yml at the channel and passing the three on | Every Role dispatch carries an item (0036), and the shim and the Release it calls agree on its inputs (L-46) |
| Who starts a Run | The job's `if:` is the dispatcher, the pass's own token by the account `config/controller.json` names for it, and no Pause of the repo or the org: `github.actor_id == '<id>' && vars.FACTORY_PAUSED != 'true'`. While the configuration names no such account, no run.yml is right | A person's dispatch runs nothing the records port would not count (I-34), and a Pause starts no Run even when the Factory's code is broken (0003). GitHub gives `vars.FACTORY_PAUSED` as one value, the repo's over the org's, so this is a second layer: the pass reads both |

## Why

The Run's shim is the last of the shims' shapes the check holds before any shim exists. The lane and the dispatcher are the two places a Run's workflow can go wrong without a step to read: a group written in serialises every item's Runs, a cancelled Run leaves a Result no `apply` writes, and a dispatch by a person starts a Run no one counts.

## Boundaries

| Boundary | Check |
|---|---|
| A Run's lane is its item's, on the job, and cancels nothing running | `tests/test_tools.py::test_a_runs_lane_is_its_item_on_the_job_and_cancels_nothing_running` |
| Every Run's dispatch carries an item, and the poller takes none | `tests/test_tools.py::test_every_run_dispatch_carries_an_item_and_the_poller_takes_none` |
| A Run starts only from the pass's own token and never under a Pause | `tests/test_tools.py::test_a_run_starts_only_from_the_poller_and_never_under_a_pause` |
| An expression stands whole as a run's name, a lane or a step's output, and with no text around it | `examples/workflows/invalid/expression.text-around-the-run-name.yml` |
| Each rule has a counter-example that breaks it and no other | `examples/workflows/invalid/lane.cancels-the-run-in-progress.yml`, `examples/workflows/invalid/lane.one-lane-for-every-item.yml`, `examples/workflows/invalid/lane.a-run-with-no-group.yml` |
