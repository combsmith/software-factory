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
it names, never its own, and reads nothing of the run that woke it, the `github` context by a dot, an index or whole, in any case (decision 0043); nor does the pass it calls. Its
dispatch takes no input. Its schedule is three lines an hour, none at minute 0. Its job, `pass`, is the one job
anywhere granted a write, `actions: write`, which starts the Runs and the successor with the job's own token (§4.9,
P-9); the id `pass` is poller.yml's and pass.yml's alone.

Org standard: none; the org's workflows do not wake on another's end.
Held by: `examples/workflows/invalid/wake.reads-the-run-that-woke-it.yml`, `examples/workflows/invalid/wake.woken-by-its-own-end.yml`, `examples/workflows/invalid/wake.a-poller-that-takes-inputs.yml`, `examples/workflows/invalid/wake.on-every-stage-of-a-run.yml`, `examples/workflows/invalid/permissions.actions-write-beyond-the-pass.yml`, `tests/test_tools.py::test_only_the_poller_runs_on_workflow_run`, `tests/test_tools.py::test_the_pass_job_alone_is_granted_a_write`
