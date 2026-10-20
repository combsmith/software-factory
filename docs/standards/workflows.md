# Workflows

Each rule shows its example first, then says what holds it. Every rule has workflows that break
it, and only it, under `examples/workflows/invalid/`. A workflow is written in a narrow form the
check can read: block style, bare keys, one key to a line. Any other spelling is refused.
An org standard is cited from combsmith/.github at commit 9e2daad, by file and heading.

## The whole of a good workflow

```yaml
# The required check, `factory / verify`: it passes only when `make verify` and every shard of the mutation check pass on the commit, with the history tools/check_decisions.py compares it with.
# About 1,000 mutants, in eight shards of about 126, each kill confirmed by two runs of one test. With six shards of 168 the legs ran 14 to 25 minutes against a 25-minute timeout, and legs were cut at 25:00 in three pull requests, once 22 ms after the last kill had printed. Every mutant names the tests that kill it, which run first; the whole suite, its slow modules last, runs only when they pass ("Mutation run: every mutant names its tests, the slow suites run last, and a builder may break a few", issue 217). Add a shard before a leg nears its timeout.
# `verify` checks out the base, never the head, and runs the base's tools/needs_passed.py, so a change cannot make its own verdict pass: decision 0023.
# `commits` checks out the base too and runs the base's tools/commits_are_the_maintainers.py, which reads every commit the pull request carries and refuses unless each is the Maintainer's ("Identity: every commit a pull request carries is the Maintainer's, checked outside the shell", issue 204).
name: factory
on:
  pull_request:
  merge_group:
permissions: {}
jobs:
  checks:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
          fetch-depth: 0
      - run: make verify
  mutants:
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    permissions:
      contents: read
    strategy:
      fail-fast: false
      matrix:
        shard:
          - 0
          - 1
          - 2
          - 3
          - 4
          - 5
          - 6
          - 7
    env:
      MUTANTS_SHARD: ${{ strategy.job-index }}
      MUTANTS_SHARDS: ${{ strategy.job-total }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
          fetch-depth: 0
      - run: python3 -m tools.mutants
  commits:
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    permissions:
      contents: read
    env:
      BASE_SHA: ${{ github.event.pull_request.base.sha || github.event.merge_group.base_sha }}
      HEAD_SHA: ${{ github.event.pull_request.head.sha || github.event.merge_group.head_sha }}
      EVENT: ${{ github.event_name }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
          fetch-depth: 0
          ref: ${{ github.event.pull_request.base.sha || github.event.merge_group.base_sha }}
      - run: python3 -m tools.commits_are_the_maintainers
  verify:
    name: verify
    needs:
      - checks
      - commits
      - mutants
    if: always()
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    permissions:
      contents: read
    env:
      NEEDS: ${{ toJSON(needs) }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
          ref: ${{ github.event.pull_request.base.sha || github.event.merge_group.base_sha }}
      - run: python3 -m tools.needs_passed
```

This is `examples/workflows/verify.yml`, word for word. The check name people see is the workflow's
name and the job's name: `factory / verify`. Renaming either silently stops it being required.
`verify` needs every other job and has `if: always()`, the one job-level `if:` a Lens's job may have:
GitHub passes a required check that is skipped, so `tools/needs_passed.py` fails it unless each passed.
Its one checkout is of the base, never the head: the verdict is the base's `tools/needs_passed.py`, so a change
cannot make its own pass (decision 0023). It runs on no event without a base. The checks and tests in `checks` and
`mutants` are the head's. `commits` is the base's too: it fetches the head and reads who authored and committed each
commit the pull request carries, which must be the Maintainer, read from `config/hooks.json`.

Org standard: ci-standards.md, "Permissions Policy", "Action Pinning Policy" and "CI Job Naming Convention". Its name, triggers and stages depart from "1. CI Pipeline (ci.yml)": `docs/decisions/0014-where-this-repo-departs-from-the-orgs-standards.md`.
Held by: `tests/test_tools.py::test_a_rule_is_not_dodged_by_writing_the_workflow_another_way`, `tests/test_tools.py::test_an_example_in_the_standard_that_has_drifted_is_caught`, `tests/test_tools.py::test_a_lens_job_that_would_never_report_under_its_name_is_caught`, `tests/test_tools.py::test_the_required_check_fails_unless_every_job_it_needs_passed`, `tests/test_tools.py::test_a_lens_job_that_judges_its_needs_runs_from_the_base`

## Pinned to what was looked up

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1    # yes
- uses: actions/checkout@v7                                                   # no
runs-on: ubuntu-24.04      # yes
runs-on: ubuntu-latest     # no
```

A tag can be moved; a commit hash cannot. Look the hash up from the release, and never guess one:
a made-up hash passes until the job first runs. Every `actions/checkout` is the one `CHECKOUT` in
`tools/check_workflows.py` lists, hash and version: a text compared word for word takes any pin as
equal, so nothing else says which checkout reads `ref:` and `path:`. A bump of it edits that entry too:
Dependabot's bump of `actions/checkout` fails the check until a person edits `CHECKOUT` in the same pull request.

Org standard: ci-standards.md, "Action Pinning Policy", "Looking Up the Correct SHA" and "Exception: Internal Reusable Workflow References". Stricter here: a tag never stands in for a hash, the runner is named by version, and the checkout is one listed version.
Held by: `examples/workflows/invalid/pin.a-tag-can-move.yml`, `examples/workflows/invalid/pin.a-checkout-not-the-listed-one.yml`, `examples/workflows/invalid/runner.an-image-that-changes.yml`, `tests/test_tools.py::test_every_checkout_is_the_listed_one`

## Nothing is granted that is not named

```yaml
permissions: {}            # at the top: nothing, for every job
jobs:
  verify:
    permissions:
      contents: read       # then only what this job needs
```

No personal access token, no `secrets: inherit`; every checkout sets `persist-credentials: false`. No job is granted `security-events: write`: with it, an upload to code scanning could stand for CodeQL's verdict.

Org standard: ci-standards.md, "Permissions Policy". Refusing a personal token and inherited secrets departs from github-settings.md, "Required secrets (all repos)": decision 0014.
Held by: `examples/workflows/invalid/permissions.none-declared.yml`, `examples/workflows/invalid/token.a-persons-token.yml`, `examples/workflows/invalid/credentials.a-token-left-on-disk.yml`, `examples/workflows/invalid/permissions.security-events-on-a-job.yml`

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
else: no install, download, condition or swallowed failure. Two workflows are exempt, each by name
and held by its hash. One is the org's secret scan, which downloads gitleaks. It differs from the
org's text in two things: the download is held to HTTPS, and it reads its rules, `.gitleaks.toml` and
`.gitleaksignore`, from a checkout of the base, never from the head it scans, which can neither hide
a file with `.gitattributes` nor pass over one with `gitleaks:allow` (decision 0023). The other is
trial P-8's tick probe, whose one step is `exit 0`: GitHub refuses a step that runs nothing. It goes
when the trial is recorded, unless the verdict says to keep watching.

Org standard: the org's AGENTS.md, "Decision Logic Lives in a Pure, Tested Script". Stricter here: a limit of ten lines, and nothing fetched but by push-protection.md, "Required CI job", which runs as the org wrote it.
Held by: `examples/workflows/invalid/length.logic-in-a-workflow.yml`, `examples/workflows/invalid/install.fetched-at-run-time.yml`, `examples/workflows/invalid/install.a-decision-in-shell.yml`, `examples/workflows/invalid/install.a-step-that-only-exits.yml`, `tests/test_tools.py::test_an_exempt_workflow_is_held_word_for_word`, `tests/test_tools.py::test_the_secret_scan_reads_the_bases_configuration`, `tests/test_tools.py::test_the_tick_probe_is_exempt_from_install_alone`

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
