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
    secrets: inherit
```

Each job holds `uses`, `permissions`, `concurrency` and `secrets: inherit`, in those words, and may hold `if` and
`with`: no steps, runner, env, named secret, environment, strategy, needs or timeout, which the called job has. A called
job that names an environment reads its secrets only with `secrets: inherit` on its caller (trial P-55). The called file
can then name any secret of the repo or the org, and an environment's where its job names that environment. The branch
policy is met by the caller's `main`, whatever commit the channel names, so the tag's ruleset guards every key. It calls one file of this repo at the channel,
`factory/v0-next`, never a local path, which would run main's copy; and a `with:` value is `${{ inputs.<the same
name> }}`. Above its jobs it holds `name`, `on`, `permissions`, `jobs` and, for a shim that dispatches a Run alone,
the Run's or an act's, `run-name`. Only a workflow on `workflow_call` alone names an environment, so no shim, push or
pull request's job is handed a key. Each
shim is held word for word by its hash in `SHIMS`, as `.github/workflows/ci.yml` is in `EXEMPT`. The eval job runs main's own file on a
dispatch, since it judges main's commit, and is spared this rule for its own shape, `eval_problems` (decision 0053).

No shim stands on main until the ruleset `factory channel branches` is applied and its id recorded: `uses:` resolves a
branch of the Channel's name while no tag has it, and a shim inherits every secret (decision 0124).

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
    types:
      - completed          # never requested, nor every stage
```

poller.yml alone runs on `workflow_run`: it wakes when a workflow of this repo ends, on the completion alone of those
it names, never its own nor `sf-run`, and reads nothing of the run that woke it: it names the `github` context in no form, in any case, outside a whole-line comment (decision 0043). The pass it calls names it only for its own token, `github.token`. Its
dispatch takes no input. Its schedule is three lines an hour, none at minute 0. Its job, `pass`, is granted a write,
`actions: write`, which starts the Runs and the successor with the job's own token (§4.9, P-9); the id `pass` is
poller.yml's and pass.yml's alone. Two others hold that grant and no other write: `wake`, a Run's last job in
run-jobs.yml, approve-job.yml and queue-job.yml, with no secret, environment, checkout or input, since a Run that token
started wakes nothing when it ends (trial P-55); and `lane`, the calling job in run.yml, approve.yml and queue.yml,
since a called job can be granted no more than its caller. Each id is those files' alone. Every shim's job holds a group of its own that waits,
never cancelling the run in progress.

poller.yml is held word for word as `POLLER_SHIM` in `tools/check_workflows.py` gives it, and by its hash in `SHIMS`.
It is live: a pass runs at each tick and at each end of `factory` or `ci`. Under a Pause, a pass reads, decides every item
`paused`, uploads its record, and dispatches nothing, its successor neither. It still writes an item's status, which is no act, so that a person
sees why nothing moves; the tracking issue opens for any other alert, never for a Pause a person set alone.

Org standard: none; the org's workflows do not wake on another's end.
Held by: `examples/workflows/invalid/wake.reads-the-run-that-woke-it.yml`, `examples/workflows/invalid/wake.woken-by-its-own-end.yml`, `examples/workflows/invalid/wake.a-poller-that-takes-inputs.yml`, `examples/workflows/invalid/wake.on-every-stage-of-a-run.yml`, `examples/workflows/invalid/permissions.actions-write-beyond-the-pass.yml`, `tests/test_tools.py::test_only_the_poller_runs_on_workflow_run`, `tests/test_tools.py::test_the_pass_job_alone_is_granted_a_write`, `tests/test_tools.py::test_the_pollers_shim_stands_as_its_template_and_its_hash`, `tests/test_effects.py::test_no_act_or_run_is_sent_unless_the_pause_reads_exactly_not_paused_on_every_scope`, `tests/test_effects.py::test_the_persons_own_pause_opens_no_tracking_issue`

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

approve.yml and queue.yml, the approving act's shim and the queue act's, are the Run's shim but for their names,
`sf-approve` and `sf-queue`, and the file each calls, approve-job.yml and queue-job.yml: `APPROVE_SHIM` and `QUEUE_SHIM`
hold each word for word. So each act's Run is named by the run-name the pass gave it, as the records port reads a Run,
holds its item's lane beside the Run's, and starts only on a dispatch by the account the pass's own token runs as, on a
first attempt, with no Pause set (decisions 0055 and 0128). No file but its own shim calls an act's job, and a job that
calls one holds its item's lane. That account is every workflow's own token here, not the pass's alone: a dispatch is
the pass's because no job of the Factory's files but `pass`, `wake` and `lane` is granted `actions: write`. A person
with write access can still push a workflow of their own that dispatches one, as the workflows' story accepted; the
act's step then reads the item again and acts only on what the Kernel still wants.

Org standard: none; the org's workflows run no Run.
Held by: `examples/workflows/invalid/lane.cancels-the-run-in-progress.yml`, `examples/workflows/invalid/lane.one-lane-for-every-item.yml`, `examples/workflows/invalid/lane.a-run-with-no-group.yml`, `examples/workflows/invalid/expression.text-around-the-run-name.yml`, `tests/test_tools.py::test_a_runs_lane_is_its_item_on_the_job_and_cancels_nothing_running`, `tests/test_tools.py::test_every_run_dispatch_carries_an_item_and_the_poller_takes_none`, `tests/test_tools.py::test_a_run_starts_only_from_the_poller_and_never_under_a_pause`, `examples/workflows/invalid/lane.an-act-outside-its-items-lane.yml`, `tests/test_tools.py::test_an_acts_shim_is_the_runs_but_for_its_name_and_the_file_it_calls`, `tests/test_tools.py::test_the_shims_that_dispatch_a_run_stand_as_their_templates_and_their_hashes`
