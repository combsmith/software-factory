# Workflows

Each rule shows its example first, then says what holds it. Every rule has workflows that break
it, and only it, under `examples/workflows/invalid/`. A workflow is written in a narrow form the
check can read: block style, bare keys, one key to a line. Any other spelling is refused.
An org standard is cited from petry-projects/.github at commit 9e2daad, by file and heading.

## The whole of a good workflow

```yaml
# The required check, `factory / verify`: `make verify` and the mutation check, on the commit and nothing else.
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

Org standard: ci-standards.md, "Permissions Policy", "Action Pinning Policy" and "CI Job Naming Convention". Its name, triggers and stages depart from "1. CI Pipeline (ci.yml)": `docs/decisions/0014-where-this-repo-departs-from-the-orgs-standards.md`.
Held by: `tests/test_tools.py::test_a_rule_is_not_dodged_by_writing_the_workflow_another_way`, `tests/test_tools.py::test_an_example_in_the_standard_that_has_drifted_is_caught`

## Pinned to what was looked up

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1    # yes
- uses: actions/checkout@v7                                                   # no
runs-on: ubuntu-24.04      # yes
runs-on: ubuntu-latest     # no
```

A tag can be moved; a commit hash cannot. Look the hash up from the release, and never guess one:
a made-up hash passes until the job first runs.

Org standard: ci-standards.md, "Action Pinning Policy", "Looking Up the Correct SHA" and "Exception: Internal Reusable Workflow References". Stricter here: a tag never stands in for a hash, and the runner is named by version.
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

Org standard: ci-standards.md, "Permissions Policy". Refusing a personal token and inherited secrets departs from github-settings.md, "Required secrets (all repos)": decision 0014.
Held by: `examples/workflows/invalid/permissions.none-declared.yml`, `examples/workflows/invalid/token.a-persons-token.yml`, `examples/workflows/invalid/credentials.a-token-left-on-disk.yml`

## Text from outside is never a command

```yaml
- run: echo ${{ github.head_ref }}        # no: whoever named the branch wrote this command
- run: python3 -m tools.verify            # yes: nothing from the event is in the command
```

An expression stands only as the whole of a value under env, with or secrets, or in an if. A
workflow runs on pull requests, the merge queue, a schedule or a dispatch, and on nothing else.

Org standard: none for expressions; the org's workflows pass event fields through env by hand. Refusing pull_request_target departs from dependabot-policy.md, "Auto-Merge Workflow": decision 0014.
Held by: `examples/workflows/invalid/expression.text-run-as-a-command.yml`, `examples/workflows/invalid/target.secrets-beside-a-strangers-code.yml`

## A workflow holds no logic and fetches nothing

```yaml
- run: make verify                        # yes
- run: |                                  # no: eleven lines that no test can call
    if [ "$STATE" = "held" ]; then
      ...
- run: pip install pytest                 # no: not in the commit being judged
```

A `run:` line is `make` and a target, or `python3 -m` and a module of this repo, and nothing
else: no install, download, condition or swallowed failure. One workflow is exempt, by name and
held by its hash: the org's secret scan, which downloads gitleaks.

Org standard: the org's AGENTS.md, "Decision Logic Lives in a Pure, Tested Script". Stricter here: a limit of ten lines, and nothing fetched but by push-protection.md, "Required CI job", which runs as the org wrote it.
Held by: `examples/workflows/invalid/length.logic-in-a-workflow.yml`, `examples/workflows/invalid/install.fetched-at-run-time.yml`, `examples/workflows/invalid/install.a-decision-in-shell.yml`, `tests/test_tools.py::test_an_exempt_workflow_is_held_word_for_word`

## A required check always reports

```yaml
on:
  pull_request:            # no paths: filter. A check that does not run never reports
  merge_group:             # and the merge queue waits for it too
```

A schedule never fires at minute 0, which is when the platform drops them.

Org standard: ci-standards.md, "Centralization tiers", which says a required check's workflow must run on merge_group, and "Scheduled Workflow Timing". Stricter here: every workflow on pull requests, and no path filter.
Held by: `examples/workflows/invalid/queue.a-required-check-that-never-reports.yml`, `examples/workflows/invalid/cron.the-top-of-the-hour.yml`, `examples/workflows/invalid/form.no-trigger.yml`

## A failure is seen, and a hang ends

```yaml
timeout-minutes: 15        # on every job with steps
continue-on-error: true    # never
```

Org standard: none for the time limit. Refusing continue-on-error departs from ci-standards.md, "3. SonarCloud Analysis (sonarcloud.yml)": decision 0014.
Held by: `examples/workflows/invalid/timeout.a-hung-step-runs-six-hours.yml`, `examples/workflows/invalid/soft.a-failure-nobody-sees.yml`
