# The entry shim and the poller

A workflow on `schedule`, `workflow_dispatch` or `workflow_run` runs the default branch's own file, which no Release
holds and no channel rolls back (§2.4 rule 1). So it is a shim: it calls the Release and holds nothing else. These rules
are issue 196's rulings 3 and 4, held by `tools/check_workflows.py` before any shim exists:
"Workflows: the frozen entry shim, the poller, the Run's three jobs and the nudge, each held to its shape".
Every other rule of `docs/standards/workflows.md` holds here too.

## The entry shim

```yaml
jobs:
  pass:
    permissions:
      actions: write
      contents: read
    concurrency:
      group: sf-poller
      cancel-in-progress: false
    uses: combsmith/software-factory/.github/workflows/pass.yml@factory/v0-next
```

Each job holds `uses`, `permissions` and `concurrency`, and may hold `if` and `with`: no steps, runner, env, secrets,
environment, strategy, needs or timeout, which the called job has. It calls one file of this repo at the channel,
`factory/v0-next`, never a local path, which would run main's copy; and a `with:` value is `${{ inputs.<the same
name> }}`. Above its jobs it holds `name`, `on`, `permissions`, `jobs` and, for the Run's shim alone, `run-name`. Only
a workflow on `workflow_call` alone names an environment, so no shim, push or pull request's job is handed a key. Each
shim is held word for word by its hash in `SHIMS`, as `.github/workflows/ci.yml` is in `EXEMPT`. The eval job runs main's own file on a
dispatch, since it judges main's commit, and is spared this rule for its own shape, `eval_problems` (decision 0053).

Org standard: none for a shim; the org's reusable workflows are called at their channel tags, ci-standards.md, "Centralization tiers".
Held by: `examples/workflows/invalid/shim.a-step-in-the-shim.yml`, `examples/workflows/invalid/shim.the-default-branchs-own-copy.yml`, `examples/workflows/invalid/shim.a-secret-handed-to-the-release.yml`, `examples/workflows/invalid/shim.a-key-beside-a-pull-request.yml`, `tests/test_tools.py::test_a_shim_holds_no_step_and_calls_the_release_at_its_channel`, `tests/test_tools.py::test_a_shim_is_held_word_for_word`, `tests/test_tools.py::test_every_shim_calls_one_channel`

## The poller

```yaml
on:
  workflow_dispatch:       # no inputs: what started a pass is read from its own run record
  workflow_run:
    workflows:
      - factory            # never sf-poller, its own name
      - ci
      - sf-run
    types:
      - completed          # never requested, nor every stage
```

poller.yml alone runs on `workflow_run`: it wakes when a workflow of this repo ends, on the completion alone of those
it names, never its own, and reads nothing of the run that woke it: it names the `github` context in no form, in any case, outside a whole-line comment (decision 0043). The pass it calls names it only for its own token, `github.token`. Its
dispatch takes no input. Its schedule is three lines an hour, none at minute 0. Its job, `pass`, is the one job
anywhere granted a write, `actions: write`, which starts the Runs and the successor with the job's own token (§4.9,
P-9); the id `pass` is poller.yml's and pass.yml's alone. Every shim's job holds a group of its own that waits,
never cancelling the run in progress.

Org standard: none; the org's workflows do not wake on another's end.
Held by: `examples/workflows/invalid/wake.reads-the-run-that-woke-it.yml`, `examples/workflows/invalid/wake.woken-by-its-own-end.yml`, `examples/workflows/invalid/wake.a-poller-that-takes-inputs.yml`, `examples/workflows/invalid/wake.on-every-stage-of-a-run.yml`, `examples/workflows/invalid/permissions.actions-write-beyond-the-pass.yml`, `tests/test_tools.py::test_only_the_poller_runs_on_workflow_run`, `tests/test_tools.py::test_the_pass_job_alone_is_granted_a_write`

## The Run's shim

```yaml
jobs:
  lane:
    if: github.actor_id == '41898282' && github.run_attempt == '1' && (vars.FACTORY_PAUSED == '' || vars.FACTORY_PAUSED == 'false')
    concurrency:
      group: ${{ inputs.item }}
      cancel-in-progress: false
```

run.yml is held to the Run's shim as `RUN_SHIM` in `tools/check_workflows.py` gives it, word for word: three required
inputs, `name`, `item` and `pass`, so every Role dispatch carries an item (decision 0036); its run named by `name`; and one
job, `lane`, that starts the Run's jobs only when the dispatcher is the pass's own token, by the account
`config/controller.json` names for it, on the run's first attempt alone, since a re-run keeps the dispatcher's id
though a person started it, and while the Pause is unset or exactly `false` (decision 0003). While the configuration
names no such account, no run.yml is right, and no file but run.yml calls the Run's jobs. One lane per Work item, never
a name written in, and a newer Run waits: it never cancels the one in progress. A job that calls the Run's jobs holds its item's lane on the
job, so it holds from `run` to `apply`. An expression may stand whole as the run's name, `${{ inputs.name }}`, the lane,
`${{ inputs.item }}`, or a job's output of one of its steps, and in no other new place.

Org standard: none; the org's workflows run no Run.
Held by: `examples/workflows/invalid/lane.cancels-the-run-in-progress.yml`, `examples/workflows/invalid/lane.one-lane-for-every-item.yml`, `examples/workflows/invalid/lane.a-run-with-no-group.yml`, `examples/workflows/invalid/expression.text-around-the-run-name.yml`, `tests/test_tools.py::test_a_runs_lane_is_its_item_on_the_job_and_cancels_nothing_running`, `tests/test_tools.py::test_every_run_dispatch_carries_an_item_and_the_poller_takes_none`, `tests/test_tools.py::test_a_run_starts_only_from_the_poller_and_never_under_a_pause`
