# Workflows

How a workflow is written here. No workflow runs yet; the first will be this one. Each rule shows
its example first, then says what holds it. Every rule has a workflow that breaks it, and only it,
under `examples/workflows/invalid/`.

## The whole of a good workflow

```yaml
# The required check, `factory / verify`. It runs what `make verify` runs, on the commit and nothing else.
name: factory
on:
  pull_request:
  merge_group:
permissions: {}
jobs:
  verify:
    name: verify
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - run: make verify
      - run: python3 -m tools.mutants
```

This is `examples/workflows/verify.yml`, word for word. The check name people see is the workflow's
name and the job's name: `factory / verify`. Renaming either silently stops it being required.

Held by: `tools/check_workflows.py`, `tests/test_tools.py::test_an_example_in_the_standard_that_has_drifted_is_caught`

## Pinned to what was looked up

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1    # yes
- uses: actions/checkout@v7                                                   # no
runs-on: ubuntu-24.04      # yes
runs-on: ubuntu-latest     # no
```

A tag can be moved; a commit hash cannot. Look the hash up from the release, and never guess one:
a made-up hash passes until the job first runs.

Held by: `examples/workflows/invalid/pin.a-tag-can-move.yml`, `examples/workflows/invalid/runner.an-image-that-changes.yml`

## Nothing is granted that is not named

```yaml
permissions: {}            # at the top: nothing, for every job
jobs:
  verify:
    permissions:
      contents: read       # then only what this job needs
```

No personal access token, and no `secrets: inherit`. Every checkout sets
`persist-credentials: false`.

Held by: `examples/workflows/invalid/permissions.none-declared.yml`, `examples/workflows/invalid/token.a-persons-token.yml`, `examples/workflows/invalid/credentials.a-token-left-on-disk.yml`

## Text from outside is never a command

```yaml
- run: echo ${{ github.head_ref }}        # no: whoever named the branch wrote this command
- run: python3 -m tools.verify            # yes: nothing from the event is in the command
```

No expression is written into a `run:` block, and no workflow runs on `pull_request_target`.

Held by: `examples/workflows/invalid/expression.text-run-as-a-command.yml`, `examples/workflows/invalid/target.secrets-beside-a-strangers-code.yml`

## A workflow holds no logic and fetches nothing

```yaml
- run: make verify                        # yes
- run: |                                  # no: eleven lines that no test can call
    if [ "$STATE" = "held" ]; then
      ...
- run: pip install pytest                 # no: not in the commit being judged
```

A `run:` block is at most ten lines and calls a module. Nothing is installed or downloaded.

Held by: `examples/workflows/invalid/length.logic-in-a-workflow.yml`, `examples/workflows/invalid/install.fetched-at-run-time.yml`

## A required check always reports

```yaml
on:
  pull_request:            # no paths: filter. A check that does not run never reports
  merge_group:             # and the merge queue waits for it too
```

A schedule never fires at minute 0, which is when the platform drops them.

Held by: `examples/workflows/invalid/queue.a-required-check-that-never-reports.yml`, `examples/workflows/invalid/cron.the-top-of-the-hour.yml`, `examples/workflows/invalid/form.no-trigger.yml`

## A failure is seen, and a hang ends

```yaml
timeout-minutes: 15        # on every job with steps
continue-on-error: true    # never
```

Held by: `examples/workflows/invalid/timeout.a-hung-step-runs-six-hours.yml`, `examples/workflows/invalid/soft.a-failure-nobody-sees.yml`
