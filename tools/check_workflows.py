"""Rules every workflow obeys, read from its text.

There is no YAML parser here, so a workflow is written in a narrow form that needs none: block
style, even indents, bare keys, one key to a line. Anything outside that form is refused,
which is what stops a rule being dodged by spelling a key another way. The rules allow what is
named and refuse the rest: the events, the commands, the places an expression may stand.

Each rule has at least one counter-example under examples/workflows/invalid/, named for the rule,
that must be rejected for that rule and no other. A rule with no counter-example fails this check.

It also holds the configuration's required Lenses to the workflows that run them (lens_workflows): a Lens whose App is
GitHub Actions names its workflow file and no other Lens names one, and the file it names exists, runs on both
pull_request and merge_group, and has a job whose own `name:`, or whose id where it has none, is the Lens's check,
with no `strategy.matrix` and no `uses:`. Its one job-level `if:` is exactly `always()`, beside a `needs:` that names
every other job in its file, and then it judges them with `tools/needs_passed.py`, the base's: its one checkout is
of the base, never the head. Only `jobs.<id>.name` is read: a workflow's or a step's `name:` names no check run.

The secret scan, the exempt `ci.yml`, reads its rules from the base (scan_problems): `.gitleaks.toml` and
`.gitleaksignore` from a checkout of the base under `base/`, with the head's `.gitleaksignore` deleted first, since
gitleaks also reads the one at the top of what it scans. Its install is held word for word, its version and checksum
free only within their shapes; and every checkout in every workflow is the one CHECKOUT lists.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
RULES = {
    "form": "block style, even indents, bare keys with the colon against them; no tab, flow mapping, anchor "
            "or quoted key, and no key written twice in one mapping",
    "pin": "an action is pinned to a full commit hash with its version beside it; one of the org's own "
           "reusable workflows, to its channel tag; nothing local but a reusable workflow",
    "target": "a workflow runs only on pull_request, merge_group, push, schedule, workflow_dispatch, workflow_run "
              "or workflow_call, and never on pull_request_target",
    "permissions": "permissions are declared at the top and grant nothing that can write; never read-all or write-all; "
                   "no job is granted a write but the pass job its actions: write, and none security-events: write, "
                   "with which an upload could stand for CodeQL's verdict",
    "shim": "a workflow on schedule, workflow_dispatch or workflow_run runs the default branch's file, so it is a "
            "shim: each job calls one file of the Release at its channel, with a concurrency group and permissions, "
            "an if: and with: values that pass its inputs on, and nothing else; and only a workflow on workflow_call "
            "alone names an environment",
    "wake": "a workflow on workflow_run wakes on the completion alone of the workflows it names, never its own, takes "
            "no input and reads nothing of the run that woke it",
    "expression": "an expression stands only as the whole of a value under env:, with: or secrets:, or in if:; or as "
                  "exactly a Run's name, ${{ inputs.name }}, its lane, ${{ inputs.item }}, or a step's output",
    "model": "no step sets the CLI's environment scrub, which only the Engine sets, beside --tools \"\", and a step that "
             "holds the model's credential is handed no tool list",
    "lane": "a job that calls the Run's jobs holds its item's lane: its own concurrency group, ${{ inputs.item }}, that "
            "never cancels the Run in progress",
    "length": "a run: block is at most ten lines",
    "install": "a run: line is `make <target>` or `python3 -m <module>` and nothing else, so nothing is "
               "installed, fetched or decided in a workflow",
    "token": "a secret is named one at a time; none is a personal access token, and secrets are never inherited",
    "queue": "a workflow that runs on pull_request also runs on merge_group, and filters neither",
    "cron": "no schedule fires at minute 0, alone or among other minutes",
    "timeout": "every job that has steps sets timeout-minutes, on the job, and each of its run: steps a limit of its "
               "own, the run: steps' together leaving the job two minutes for its other steps",
    "runner": "the runner and any container image are named by version, never latest",
    "credentials": "every checkout sets persist-credentials: false",
    "soft": "no step or job continues on error",
}
EVENTS = {"pull_request", "merge_group", "push", "schedule", "workflow_dispatch", "workflow_run", "workflow_call"}
# The entry shim (issue 196's ruling 3): a workflow on these events runs the default branch's own file, which no Release
# holds and no channel rolls back, so it calls the Release and holds nothing else.
SHIM_EVENTS = {"schedule", "workflow_dispatch", "workflow_run"}
SHIM_TOP = {"name", "on", "permissions", "jobs", "run-name"}
SHIM_JOB = {"uses", "permissions", "concurrency", "if", "with"}
SHIM_NEEDS = {"uses", "permissions", "concurrency"}
# The one channel every shim calls (decision 0006), the Release's tag, never a local path, which would run main's copy.
RELEASE = re.compile(r"^combsmith/software-factory/\.github/workflows/[\w.-]+\.yml@factory/v0-next$")
# Each shim, held word for word by a hash taken with the pins left out, as EXEMPT holds ci.yml: a change to one fails
# until the same pull request records its new hash, and `.github/` is the Maintainer's to approve. None is live yet.
SHIMS = {}
# A workflow held by a shape check of its own, which it is spared these rules for: the eval job judges main's own
# commit, so it runs main's file on a dispatch, and eval_problems holds every line of it (issue 309); and the Run's
# jobs, whose CLI install run_jobs_problems holds word for word with the rest of the file (issue 196). The release job
# moves the Release every Run calls, so it cannot be one: it runs main's file, and release_problems holds every line of
# it (issue 197's ruling 4′).
SHAPED = {"eval.yml": ("shim", "install"), "run-jobs.yml": ("install",), "release.yml": ("shim",)}
# The one workflow that wakes on another's end, and the one job granted a write (issue 196's ruling 4).
WAKES = "poller.yml"
# The Run's lane (issue 196's ruling 6): one concurrency group for each Work item, on the one job that calls the Run's
# jobs, so that it holds from run to apply and never cancels what runs. And the three places an expression may stand
# whole beyond env:, with: and secrets:: the run's name, the lane, and a job's output of one of its steps.
RUN_JOBS = "run-jobs.yml"
LANE = "${{ inputs.item }}"
RUN_NAME = "${{ inputs.name }}"
OUTPUT = re.compile(r"^\$\{\{ steps\.[a-z][\w-]*\.outputs\.[a-z][\w-]* \}\}$")
# The Run's shim, as the ruling gives it in full: its dispatcher is the pass's own token, by the account controller/1
# names for it, on the run's first attempt alone, since a re-run keeps the dispatcher's id though a person started it;
# and a Pause of the repo or the org starts no Run, any value but unset or exactly false a Pause (decision 0003; I-34).
RUN_SHIM = """name: sf-run
run-name: ${{ inputs.name }}
on:
  workflow_dispatch:
    inputs:
      name:
        required: true
        type: string
      item:
        required: true
        type: string
      pass:
        required: true
        type: string
permissions: {}
jobs:
  lane:
    if: github.actor_id == '%d' && github.run_attempt == '1' && (vars.FACTORY_PAUSED == '' || vars.FACTORY_PAUSED == 'false')
    permissions:
      contents: read
    concurrency:
      group: ${{ inputs.item }}
      cancel-in-progress: false
    uses: combsmith/software-factory/.github/workflows/run-jobs.yml@factory/v0-next
    with:
      name: ${{ inputs.name }}
      item: ${{ inputs.item }}
      pass: ${{ inputs.pass }}
"""
# The github context named in any form an expression can write it, by a dot, an index, a bracket, an argument or whole,
# in any case, but its token, which is the pass job's own; outside comments. A path such as .github/workflows/ is no
# read of it. The poller and the pass it calls read nothing of the run that woke them.
EVENT_READ = re.compile(r"(?<![./\w-])github(?![\w-])(?!\.token(?![\w.\[]))", re.I)
GITHUB_ANY = re.compile(r"(?<![./\w-])github(?![\w-])", re.I)     # the poller names none of it, its token neither
PASS_JOB, PASS_FILES = "pass", ("poller.yml", "pass.yml")
# The Run's three jobs and the approving act's one, each held word for word, as run.yml is (#196's ruling 7, decisions
# 0050, 0054 and 0055; the Maintainer's answers (a) and (b) of 2026-10-21). Every job checks out the Release, never the
# item's code. `run` reads with the reader's key in a step of its own, revoked before the model's step, which holds the
# model's credential alone, the Engine setting the scrub and `--tools ""`; `verify` holds no secret and no cache; `apply`
# runs whatever failed and its last step always leaves the outcome; the act holds the machine user's token alone. The CLI
# is the second exempt install, its version the Engine's pin in config/harness.json, and its checksum CLI_CHECKSUM, the
# one the vendor's release manifest gives for linux-x64; a pull request that moves the pin moves the checksum.
APPROVE_JOB = "approve-job.yml"
PASS_WORKFLOW = "pass.yml"
# The pass, held word for word: the record uploaded before anything is dispatched, the Controller's key on its two steps
# alone, the pass's own token on the writes' step alone, and the record of each write uploaded whatever failed.
PASS_FILE = """name: sf-pass
on:
  workflow_call:
permissions: {}
jobs:
  pass:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    environment: factory-poller
    permissions:
      actions: write
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: factory/v0-next
          fetch-tags: true
          persist-credentials: false
      - name: Read and decide
        env:
          CONTROLLER_APP_KEY: ${{ secrets.CONTROLLER_APP_KEY }}
        timeout-minutes: 6
        run: python3 -m controller
      - name: Upload the pass record
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: pass
          path: pass/pass.json
          if-no-files-found: error
      - name: Write what the pass decided
        env:
          CONTROLLER_APP_KEY: ${{ secrets.CONTROLLER_APP_KEY }}
          WORKFLOW_TOKEN: ${{ github.token }}
        timeout-minutes: 6
        run: python3 -m adapters.effects
      - if: always()
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: written
          path: pass/written.json
          if-no-files-found: ignore
"""
# The CLI's sha256 for linux-x64 by version, each as the vendor's release manifest for that version gives it: a pin with
# no entry here is refused, so that a pull request that moves the pin moves the checksum.
CLI_CHECKSUMS = {"2.1.306": "520bc6c1f40af466bd03a278b5ae1af1a2938bc7de5b9e5cb15526da20d71cfe"}
RUN_JOBS_FILE = """name: sf-run-jobs
on:
  workflow_call:
    inputs:
      name:
        required: true
        type: string
      item:
        required: true
        type: string
      pass:
        required: true
        type: string
permissions: {}
jobs:
  run:
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    environment: factory-run
    permissions:
      contents: read
    outputs:
      commit: ${{ steps.commit.outputs.commit }}
      digest: ${{ steps.engine.outputs.digest }}
      artifact: ${{ steps.result.outputs.artifact-id }}
      reader: ${{ steps.reader.outputs.artifact-id }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: factory/v0-next
          persist-credentials: false
      - name: Hand on the commit it checked out, which every later job checks out
        id: commit
        timeout-minutes: 1
        run: python3 -m harness.steps
      - name: Install the CLI at the Engine's pin
        env:
          CLI_VERSION: "%(version)s"
          CLI_CHECKSUM: "%(checksum)s"
        timeout-minutes: 3
        run: |
          url="https://downloads.claude.ai/claude-code-releases/${CLI_VERSION}/linux-x64/claude"
          curl -sSfL --proto '=https' --proto-redir '=https' -o /tmp/claude "${url}"
          echo "${CLI_CHECKSUM}  /tmp/claude" | sha256sum -c
          chmod 0755 /tmp/claude
          sudo mv /tmp/claude /usr/local/bin/claude
          sudo apt-get install -y --no-install-recommends bubblewrap
      - name: Read what the Task is built from
        id: read
        env:
          NAME: ${{ inputs.name }}
          ITEM: ${{ inputs.item }}
          PASS: ${{ inputs.pass }}
          READER_APP_KEY: ${{ secrets.READER_APP_KEY }}
        timeout-minutes: 3
        run: python3 -m harness.read
      - name: Run the Engine
        id: engine
        env:
          CLAUDE_CLI: /usr/local/bin/claude
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
        timeout-minutes: 20
        run: python3 -m harness.run
      - name: Upload the Result
        id: result
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: result
          path: result/
          if-no-files-found: error
      - name: Upload the reader's outcome, which it leaves when the Run's Release is not its pass's
        id: reader
        if: failure() && steps.read.outcome == 'failure'
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: reader-outcome
          path: task/outcome.json
          if-no-files-found: ignore
  verify:
    needs: run
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: ${{ needs.run.outputs.commit }}
          fetch-tags: true
          persist-credentials: false
      - uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2
        with:
          artifact-ids: ${{ needs.run.outputs.artifact }}
          path: result
      - name: Verify the Result
        env:
          RUN_DIGEST: ${{ needs.run.outputs.digest }}
        timeout-minutes: 5
        run: python3 -m harness.verify
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: verdict
          path: verdict/
          if-no-files-found: error
  apply:
    needs:
      - run
      - verify
    if: always() && needs.run.outputs.commit != ''
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    environment: factory-apply
    permissions:
      contents: read
    env:
      NEEDS: ${{ toJSON(needs) }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: ${{ needs.run.outputs.commit }}
          fetch-tags: true
          persist-credentials: false
      - if: always() && needs.run.outputs.artifact != ''
        uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2
        with:
          artifact-ids: ${{ needs.run.outputs.artifact }}
          path: result
      - if: always() && needs.run.outputs.reader != ''
        uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2
        with:
          artifact-ids: ${{ needs.run.outputs.reader }}
          path: reader-outcome
      - name: Apply the Result
        if: always()
        env:
          NAME: ${{ inputs.name }}
          ITEM: ${{ inputs.item }}
          PASS: ${{ inputs.pass }}
          RUN_DIGEST: ${{ needs.run.outputs.digest }}
          PR_REVIEW_APP_KEY: ${{ secrets.PR_REVIEW_APP_KEY }}
        timeout-minutes: 4
        run: python3 -m harness.apply_step
      - if: always()
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: applied
          path: applied/applied.json
          if-no-files-found: ignore
      - name: Leave the Run's outcome
        if: always()
        env:
          NAME: ${{ inputs.name }}
        timeout-minutes: 2
        run: python3 -m harness.outcome
      - if: always()
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: outcome
          path: outcome/outcome.json
          if-no-files-found: error
"""
APPROVE_JOB_FILE = """name: sf-approve-job
on:
  workflow_call:
    inputs:
      name:
        required: true
        type: string
      item:
        required: true
        type: string
      pass:
        required: true
        type: string
permissions: {}
jobs:
  approve:
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    environment: factory-approve
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: factory/v0-next
          fetch-tags: true
          persist-credentials: false
      - name: Approve the commit it read, if the Kernel still wants it
        env:
          NAME: ${{ inputs.name }}
          ITEM: ${{ inputs.item }}
          PASS: ${{ inputs.pass }}
          APPROVER_TOKEN: ${{ secrets.APPROVER_TOKEN }}
        timeout-minutes: 4
        run: python3 -m harness.approve_step
      - if: always()
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: applied
          path: applied/applied.json
          if-no-files-found: ignore
      - name: Leave the Run's outcome
        if: always()
        env:
          NAME: ${{ inputs.name }}
        timeout-minutes: 2
        run: python3 -m harness.outcome
      - if: always()
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: outcome
          path: outcome/outcome.json
          if-no-files-found: error
"""
# Each key and the environment it lives in, by the one file that may name them (decision 0035): no other workflow names
# either, so no other job, and no job a fork's code could reach, holds the key.
KEYED = {PASS_WORKFLOW: re.compile(r"factory-poller|CONTROLLER_APP_KEY", re.I),      # GitHub's names of these
         RUN_JOBS: re.compile(r"factory-run|factory-apply|READER_APP_KEY|PR_REVIEW_APP_KEY", re.I),     # ignore case
         APPROVE_JOB: re.compile(r"factory-approve|APPROVER_TOKEN", re.I)}
# The id GitHub gives the App GitHub Actions: it reports every job in every workflow of the repo.
ACTIONS_APP = 15368
# A workflow that cannot be written within a rule. It is exempt from the rules named and from no other,
# and it is held to its text by a hash taken with the pins left out: to change it, change this.
EXEMPT = {
    "ci.yml": (("install",), "f6eac470f6f955e02f86fb889d311e428298a4ef239ead0fad86509af86a5ded"),    # the org's secret scan downloads gitleaks
}
MAX_RUN_LINES = 10
# The minutes a job keeps beyond its run: steps' limits, for its other steps, which have none: its set-up, each uses: step
# and each post step. In 116 jobs of the required checks' runs to 2026-10-29 they took at most 8 s together (issue 388).
MARGIN = 2
# A limit, of a job or a step: a whole number of minutes above none, in ASCII digits. The runner sets no limit for 0, and
# int() reads digits a YAML reader does not (issue 388).
MINUTES = re.compile(r"^[1-9][0-9]*$")
ENTRY = re.compile(r"^( *)(- )?([A-Za-z_][\w-]*):(?: (.*))?$")
ITEM = re.compile(r"^( *)- (\S.*)$")
COMMAND = re.compile(r"^(make [\w.-]+|python3 -m [\w.]+)$")
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
# The org's rule for its own reusable workflows: a channel tag, never a branch and never a hash.
CHANNEL = re.compile(r"^combsmith/[\w.-]+/\.github/workflows/[\w.-]+\.ya?ml@[\w.-]+/(v\d+-)?(stable|next)$")
LOCAL = re.compile(r"^\./\.github/workflows/[\w.-]+\.ya?ml$")
VERSION = re.compile(r"^#\s*v\d")
RUNNER = re.compile(r"^[a-z]+-\d+(\.\d+)?(-[a-z0-9]+)*$")
IMAGE = re.compile(r"^[\w./-]+(:[\w.-]+|@sha256:[0-9a-f]{64})$")
WHOLE = re.compile(r"^\$\{\{ [^{}]+ \}\}$")
SECRET = re.compile(r"\bsecrets\b(\.(\w+)|\[\s*['\"](\w+)['\"]\s*\])?")
PERSONAL = re.compile(r"(?:^|_)PAT(?:_|$)", re.I)
PIN = re.compile(r"@[0-9a-f]{40} # v[\w.]+")
# The one actions/checkout every workflow uses, and its version. PIN makes any two pins equal where a text is compared
# word for word, so this is what holds the checkout to a version that has `ref:` and `path:` (decision 0023). A bump of
# actions/checkout changes it here too, so a bot's bump cannot merge on its own.
CHECKOUT = ("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "# v7.0.1")
CHECKOUT_USE = re.compile(r"^actions/checkout[@/]", re.I)
# What a Lens's job that needs others has: the one job-level if: that cannot skip it, the step that judges what it
# needs, and the results that step reads.
ALWAYS = "always()"
JUDGE = "python3 -m tools.needs_passed"
NEEDS = "${{ toJSON(needs) }}"
# The job that reads every commit a pull request carries (decision 0041): the base's tool, from a checkout of the base
# with the whole history, told the base, the head and the event by the expressions below and nothing else. It reads the
# opener from the payload the runner leaves, so no expression gives it one, and on a merge group with the job's own
# token, read-only, which it is given by name (decision 0102).
COMMITS = "python3 -m tools.commits_are_the_maintainers"
# The mutant shards (issue 180): each leg is told its index and the count by the matrix itself, never by a number
# written in, so every leg runs its own shard and the count is the matrix's size.
SHARDED = "python3 -m tools.mutants"
INDEX = "${{ strategy.job-index }}"
TOTAL = "${{ strategy.job-total }}"
JUDGING_KEYS = {"name", "needs", "if", "runs-on", "timeout-minutes", "permissions", "env", "steps"}
SHARD_KEYS = {"runs-on", "timeout-minutes", "permissions", "strategy", "env", "steps"}
HEAD = "${{ github.event.pull_request.head.sha || github.event.merge_group.head_sha }}"
JOB_TOKEN = "${{ github.token }}"
EVENT = "${{ github.event_name }}"
# The commit a pull request, or a merge-queue entry, is judged against (decision 0023). A judging job checks out this and
# nothing else; the secret scan, which also runs on a push to main, falls back to the commit pushed.
BASE = "${{ github.event.pull_request.base.sha || github.event.merge_group.base_sha }}"
SCAN = "ci.yml"
# The eval job and its workflow: reserved names, the Harness story's (docs/standards/workflows.md). Its shape, issue
# 309's ruling 10: dispatched alone, one job on its own environment, its steps in order, and each of its two credentials
# named by one step alone, the held-out home's by `fetch`, the model's by `run`.
EVAL_JOB, EVAL_WORKFLOW = "eval", "eval.yml"
EVAL_ENVIRONMENT = "factory-eval"
EVAL_STEP = "python3 -m harness.eval.%s"
# The one upload the eval job may run, by its commit, as CHECKOUT is the one checkout: an action in the one job that
# holds both credentials can read them both (decision 0053), so a bump of it edits this too.
UPLOAD = ("actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9", "# v7.0.2")
EVAL_ORDER = ("checkout", "plan", "install", "fetch", "run", "upload", "judge")
# The CLI's install, the one the Run's jobs hold word for word in RUN_JOBS_FILE: the eval job installs the CLI a live
# Run does, at the Engine's pin and by the vendor's checksum (issue 309, amendment 1). Its version and checksum are given
# under env:, as RUN_JOBS_FILE gives them. Bubblewrap is the one package: the CLI refuses to run with the scrub on and
# none on the runner (decision 0106). It is fetched as root by Ubuntu's signature, so it comes before anything is in the
# job: in the eval job, before the fetch, as in the Run's jobs before the reader.
CLI_INSTALL_RUN = ['url="https://downloads.claude.ai/claude-code-releases/${CLI_VERSION}/linux-x64/claude"',
                   "curl -sSfL --proto '=https' --proto-redir '=https' -o /tmp/claude \"${url}\"",
                   'echo "${CLI_CHECKSUM}  /tmp/claude" | sha256sum -c',
                   "chmod 0755 /tmp/claude",
                   "sudo mv /tmp/claude /usr/local/bin/claude",
                   "sudo apt-get install -y --no-install-recommends bubblewrap"]
EVAL_JOB_KEYS = {"runs-on", "timeout-minutes", "permissions", "environment", "steps"}
# Its runner, the one the CLI's linux-x64 install is for, and its timeout, which the run step's budget is held inside
# (harness/eval/run.py, BUDGET): a shorter one would end the job before the report is uploaded (issue 309, ruling 9).
EVAL_RUNNER = {"runs-on": "ubuntu-24.04", "timeout-minutes": "120"}
# What each step may be given, under with: or env:, exactly: a step's own keys beside these are refused.
EVAL_GIVEN = {
    "checkout": {"with": {"persist-credentials": "false"}},
    "plan": {"env": {"RELEASE": "${{ inputs.release }}"}},
    # The one personal token a workflow here may name, the Maintainer's, read-only on the home alone (decision 0053),
    # and the home's coordinates, secrets and never variables: a step's log shows what it is given, and GitHub masks a
    # secret's value there, and nowhere a variable's.
    "fetch": {"env": {"HELDOUT_TOKEN": "${{ secrets.HELDOUT_TOKEN }}", "HELDOUT_OWNER": "${{ secrets.HELDOUT_OWNER }}",
                      "HELDOUT_REPO": "${{ secrets.HELDOUT_REPO }}"}},
    # The CLI's version and checksum are the Engine's pin's, given at the check (eval_problems).
    "install": {"env": {"CLI_VERSION": None, "CLI_CHECKSUM": None}},
    "run": {"env": {"CLAUDE_CODE_OAUTH_TOKEN": "${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}",
                    "CLAUDE_CLI": "/usr/local/bin/claude"}},
    "upload": {"with": {"name": "eval-report", "path": "eval-report.json", "if-no-files-found": "error",
                        "retention-days": "90"}},
    "judge": {},
}
EVAL_STEP_KEYS = {"uses", "run", "with", "env", "timeout-minutes"}
# The release job and its workflow (issue 197's ruling 4′): dispatched by the Maintainer, with the command and its
# version or target, or on a schedule that cuts only when the repo's FACTORY_RELEASE_AUTO is true and no Pause is set;
# one job, `release`, on its own environment, whose deployment branches are main's alone, so no other ref's copy of
# this file reaches its key. Its token is minted by the one pinned action below, for this repo alone and the grants the
# step needs; the checkout is the commit the run is of, never a ref an output names; and its one step is
# `python3 -m release.move`, given its inputs and the token under env: and nothing else.
RELEASE_WORKFLOW, RELEASE_JOB, RELEASE_ENVIRONMENT = "release.yml", "release", "factory-release"
RELEASE_TOP = {"name": "sf-release", "on": "", "permissions": "{}", "jobs": ""}
# Its triggers, word for word: a list the reader keeps no entry of, an option or a schedule, is held this way alone.
RELEASE_ON = """on:
  workflow_dispatch:
    inputs:
      command:
        required: true
        type: choice
        options:
          - cut
          - move
          - rollback
      version:
        required: false
        type: string
      to:
        required: false
        type: string
  schedule:
    - cron: "41 6 * * 1-5"
"""
RELEASE_RUNNER = {"runs-on": "ubuntu-24.04", "timeout-minutes": "15"}
RELEASE_IF = ("github.event_name == 'workflow_dispatch' || (vars.FACTORY_RELEASE_AUTO == 'true' && "
              "(vars.FACTORY_PAUSED == '' || vars.FACTORY_PAUSED == 'false'))")
RELEASE_JOB_KEYS = {"if", "runs-on", "timeout-minutes", "environment", "concurrency", "permissions", "steps"}
RELEASE_CONCURRENCY = {"group": "sf-release", "cancel-in-progress": "false"}
RELEASE_GRANTED = [("contents", "read")]       # the job's own token: its writes are the App's
# The one action that mints the release App's token, as CHECKOUT is the one checkout: a bump edits this too.
APP_TOKEN = ("actions/create-github-app-token@64ab729a6294000f5aa4a4bc0b73d1f32bc45510", "# v3.3.0")
RELEASE_ORDER = ("mint", "checkout", "step")
RELEASE_STEP = "python3 -m release.move"
RELEASE_GIVEN = {
    "mint": {"with": {"client-id": "${{ vars.RELEASE_APP_CLIENT_ID }}", "private-key": "${{ secrets.RELEASE_APP_KEY }}",
                      "repositories": "software-factory", "permission-contents": "write",
                      "permission-workflows": "write", "permission-deployments": "write",
                      "permission-actions": "read", "permission-checks": "read"}},
    "checkout": {"with": {"persist-credentials": "false"}},
    "step": {"env": {"RELEASE_COMMAND": "${{ inputs.command || 'cut' }}", "RELEASE_VERSION": "${{ inputs.version }}",
                     "RELEASE_TO": "${{ inputs.to }}", "RELEASE_CUT_COMMIT": "${{ github.sha }}",
                     "RELEASE_TOKEN": "${{ steps.mint.outputs.token }}"}},
}
RELEASE_STEP_KEYS = {"mint": {"id", "uses", "with"}, "checkout": {"uses", "with"}, "step": {"run", "env", "timeout-minutes"}}
# What names the release job's environment, its key or its token, in a workflow that is not release.yml.
RELEASE_ONLY = re.compile(r"factory-release|RELEASE_APP_|RELEASE_TOKEN|release\.move", re.I)
EVAL_TOP = {"name": "factory", "on": "", "permissions": "{}", "jobs": ""}
EVAL_ACTIONS = {"checkout", "upload"}
# The model's credential, an organisation secret no branch policy narrows (decision 0053): named in eval.yml's run step
# and in the Run's jobs' workflow, run-jobs.yml, and in no other workflow; run.yml, a shim, names no secret. Within
# run-jobs.yml, that only its run step names it is that workflow's own check, "Harness: run and apply for the review Intent, and the model holds no credential that can
# write" (issue 194), its PR 3.
MODEL_SECRET = re.compile(r"CLAUDE_CODE_OAUTH_TOKEN", re.I)
MODEL_WORKFLOWS = {EVAL_WORKFLOW, "run-jobs.yml"}
# The CLI's environment scrub, which the Engine alone sets beside --tools "" (decision 0050): a workflow can pass the CLI
# no argument, so a step that set the scrub would set it with no word of the tools. And a tool list, by name or flag.
SCRUB = "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"
TOOLS = re.compile(r"tool", re.I)
# What names the held-out home or the eval job's environment, in a workflow that is not eval.yml.
EVAL_ONLY = re.compile(r"factory-eval|HELDOUT_|harness\.eval", re.I)    # GitHub's names of these ignore case
SCAN_BASE = "${{ github.event.pull_request.base.sha || github.event.merge_group.base_sha || github.sha }}"
# gitleaks 8.30.1 reads the ignore file named by --gitleaks-ignore-path and also the one at the top of --source, so the
# head's is deleted on the line before. Its own log options are kept, and --text added, so a head's .gitattributes cannot
# mark a file binary and hide it; and an inline gitleaks:allow, which the head writes, passes over nothing.
SCAN_RUN = ["rm -f .gitleaksignore",
            "gitleaks detect --source . --config base/.gitleaks.toml --gitleaks-ignore-path base/.gitleaksignore "
            "--ignore-gitleaks-allow --log-opts=\"--full-history --all --diff-filter=tuxdb --text\" "
            "--redact --verbose --exit-code 1"]
SCAN_CHECKOUTS = [{"fetch-depth": "0", "persist-credentials": "false"},
                  {"path": "base", "ref": SCAN_BASE, "persist-credentials": "false"}]
# What the secret scan's workflow and its one job may hold, and what its install may be given.
SCAN_TOP = {"name", "on", "permissions", "jobs"}
SCAN_JOB = {"name", "runs-on", "timeout-minutes", "permissions", "steps"}
# The install's whole block. It reads the version and the checksum from its env, so they alone are free, each held to its
# shape and quoted: the version goes into the URL's path, where curl folds `/../`, and the checksum can only accept what
# a gitleaks release serves. A gitleaks without a flag of SCAN_RUN exits non-zero, so the scan fails closed.
INSTALL_RUN = ['tarball="gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"',
               'url="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${tarball}"',
               "curl -sSfL --proto '=https' --proto-redir '=https' -o /tmp/gitleaks.tar.gz \"${url}\"",
               'echo "${GITLEAKS_CHECKSUM}  /tmp/gitleaks.tar.gz" | sha256sum -c',
               "tar -xzf /tmp/gitleaks.tar.gz -C /tmp gitleaks",
               "sudo mv /tmp/gitleaks /usr/local/bin"]
SCAN_ENV = {"GITLEAKS_VERSION": re.compile(r'"[0-9]+\.[0-9]+\.[0-9]+"'),
            "GITLEAKS_CHECKSUM": re.compile(r'"[0-9a-f]{64}"')}
# The only events a workflow with a judging job runs on: on any other there is no base, and its checkout would be the head.
JUDGED = {"pull_request", "merge_group"}
JOB = re.compile(r"^[A-Za-z_][\w-]*$")


# A space or a line break of any kind but the plain space and the newline: YAML reads none of them as Python's strip()
# does, so a line led by one is no comment, and one may end a line where no line ends here (the security pass on #392).
ODD_SPACE = re.compile(r"[^\S \n]")      # Python's \s holds NEL, U+2028 and U+2029, YAML 1.1's line breaks


def _closed(rest: str):
    """Where the quoted value `rest` opens with ends, past its closing quote, or None where it does not close on its
    line: YAML would read the lines after it as more of the value, which these entries do not hold."""
    quote, at = rest[0], 1
    while at < len(rest):
        if quote == '"' and rest[at] == "\\":
            at += 2
            continue
        if rest[at] == quote:
            if quote == "'" and rest[at + 1:at + 2] == "'":
                at += 2
                continue
            return at + 1
        at += 1
    return None


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def read(text: str) -> tuple:
    """(entries, numbers of the lines not in the narrow form). An entry is one `key: value` line.

    Its `path` is the keys above it, `step` numbers the list item it belongs to, and `body` holds
    the lines of a block of text under it. A key written twice in one mapping is not in the narrow form: a
    YAML reader would refuse it or keep one of the two, and the entries would merge what no reader yields. Nor is a
    bare list item anywhere but under a key with no value, beside the items before it: under a key that has one, a
    YAML reader reads it as more of that value, and a `run:` would run a command these entries do not hold (issue 371).
    """
    entries, bad, stack, step, block, seen = [], [], [], 0, None, [set()]
    items = None        # where a bare list item may stand: (the least indent, the indent of the items before it)
    for number, raw in enumerate(text.split("\n"), 1):
        if "\t" in raw or "\r" in raw or ODD_SPACE.search(raw):
            bad.append(number)
            continue
        if block is not None:
            if not raw.strip() or len(raw) - len(raw.lstrip(" ")) > block["indent"]:
                if raw.strip():
                    block["body"].append(raw.strip())
                continue
            block = None
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        found, item = ENTRY.match(line), ITEM.match(line)
        if found is None:
            if item is None or len(item.group(1)) % 2 or item.group(2)[0] in "{[&*!|>'\"" or \
                    re.search(r":(\s|$)", item.group(2)) or items is None or len(item.group(1)) < items[0] or \
                    items[1] not in (None, len(item.group(1))):
                bad.append(number)
            else:
                items = (items[0], len(item.group(1)))
            continue
        indent = len(found.group(1)) + (2 if found.group(2) else 0)
        key, rest = found.group(3), (found.group(4) or "").strip()
        if rest.startswith("#"):
            rest = ""       # a comment alone is no value, as YAML reads it: the key's list may follow (Muse's read of #392)
        quoted = rest.startswith(("'", '"'))
        end = _closed(rest) if quoted else None
        # A quote not closed on its line, or text after the one that closes it: YAML reads it otherwise.
        if quoted and end is None:
            bad.append(number)
            end = len(rest)
        elif quoted and rest[end:].strip()[:1] not in ("", "#"):
            bad.append(number)
        if end is not None:
            value, comment = rest[:end], rest[end:].strip()[1:] if key != "run" else ""
        else:
            value, _, comment = (rest, "", "") if key == "run" else rest.partition(" #")
        value = value.strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        del seen[len(stack) + 1:]
        if found.group(2):
            step += 1
            seen[len(stack)] = set()     # a list item is a mapping of its own
        if key in seen[len(stack)]:
            bad.append(number)
        seen[len(stack)].add(key)
        entry = {"key": key, "value": _unquote(value), "comment": "#" + comment if comment else "",
                 "indent": indent, "line": number, "path": [k for _, k in stack], "step": step, "body": []}
        if value in ("|", "|-", "|+", ">", ">-", ">+"):
            block = entry
        elif indent % 2 or (value and value[0] in "{[&*!|>" and not (key == "permissions" and value == "{}")):
            bad.append(number)
        entries.append(entry)
        stack.append((indent, key))
        seen.append(set())
        items = None if value else (indent, None)
    return entries, bad


def lint(text: str) -> list:
    """(rule, message) for each rule this workflow breaks."""
    entries, bad = read(text)
    found = []

    def under(*path):
        return [e for e in entries if e["path"] == list(path)]

    top = {e["key"]: e for e in under()}
    jobs = under("jobs")
    if bad:
        found.append(("form", "line %d is not in the narrow form" % bad[0]))
    elif "on" not in top or not jobs or not (top["on"]["value"] or under("on")):
        # An on: written as a list of events is never read as events here, so it is no on: section (the security
        # pass on #392).
        found.append(("form", "no on: section, or no job that can be read"))
    elif _on_items(text, top["on"]):
        # Any list item under on:, a bare event or a keyed one, is an on: these entries do not read whole: a bare
        # pull_request_target beside keyed items would be no event here (Argon's read of #392).
        found.append(("form", "line %d writes on: as a list; write each event as a key" % _on_items(text, top["on"])[0]))
    elif any(_scalar_items(text, entries, job["key"], steps_only=True) for job in jobs):
        # A step that is a bare text is one the reading by keys never sees (Argon's read of #392).
        found.append(("form", "line %d is a step of bare text; write it as a uses: or a run: step"
                      % next(n for job in jobs for n in _scalar_items(text, entries, job["key"], steps_only=True))))

    events = {e["key"] for e in under("on")}
    if top.get("on", {}).get("value"):
        events.add(top["on"]["value"])
    if events - EVENTS:
        found.append(("target", "runs on %s" % ", ".join(sorted(events - EVENTS))))
    filtered = [e for e in entries if e["path"][:2] in (["on", "pull_request"], ["on", "merge_group"])]
    if "pull_request" in events and ("merge_group" not in events or filtered):
        found.append(("queue", "runs on pull_request without merge_group, or behind a filter"))

    grant, granted = top.get("permissions"), under("permissions")
    if grant is None or (grant["value"] != "{}" and not granted) or \
            any(e["value"] not in ("read", "none") for e in granted) or \
            any(e["key"] == "permissions" and e["value"] not in ("", "{}") for e in entries):
        found.append(("permissions", "no top-level permissions, one that can write, or read-all or write-all"))
    # A job's grant may write in one place: the pass job's actions: write, which starts the Runs and the successor.
    for e in entries:
        if len(e["path"]) == 3 and e["path"][0] == "jobs" and e["path"][2] == "permissions" and \
                e["value"] not in ("read", "none") and (e["path"][1], e["key"], e["value"]) != (PASS_JOB, "actions", "write"):
            found.append(("permissions", "job %s is granted %s: %s" % (e["path"][1], e["key"], e["value"])))

    for e in entries:
        key, value = e["key"], e["value"]
        if key == "cron" and any(part in ("0", "00") or part[:1] == "*" or part[:2] in ("0-", "0/")
                                 for part in (value.split() or [""])[0].split(",")):
            found.append(("cron", "a schedule that fires at minute 0"))
        if key == "uses" and not LOCAL.match(value) and not CHANNEL.match(value):
            if not PINNED.match(value):
                found.append(("pin", "%s is not pinned to a commit" % value))
            elif not VERSION.match(e["comment"]):
                found.append(("pin", "%s has no version beside its hash" % value.split("@")[0]))
            elif CHECKOUT_USE.match(value) and (value, e["comment"]) != CHECKOUT:
                found.append(("pin", "%s %s is not the listed checkout, %s %s" % ((value, e["comment"]) + CHECKOUT)))
        if key == "runs-on" and not RUNNER.match(value):
            found.append(("runner", "runs on '%s'" % value))
        if key in ("image", "container") and (value or key == "image") and \
                (not IMAGE.match(value) or value.endswith(":latest")):
            found.append(("runner", "uses the image '%s'" % value))
        if key == "continue-on-error" and value != "false":
            found.append(("soft", "continues on error"))
        if key == "secrets" and value:
            found.append(("token", "inherits secrets"))
        if key == "shell":
            found.append(("install", "sets its own shell"))
        if key == "run" and e["path"][-1:] == ["steps"]:     # a step's command; a job may be named run too
            commands = e["body"] if e["body"] else [value]
            if len(commands) > MAX_RUN_LINES:
                found.append(("length", "a run: block of %d lines" % len(commands)))
            if not all(COMMAND.match(c) for c in commands):
                found.append(("install", "runs something other than make or a module of this repo"))
        if key == "uses" and value.lower().startswith("actions/checkout@"):
            if not [x for x in entries if x["step"] == e["step"] and x["key"] == "persist-credentials"
                    and x["value"] == "false" and x["path"][-1:] == ["with"]]:
                found.append(("credentials", "a checkout keeps its credentials"))

    for job in jobs:
        inside = {e["key"]: e for e in under("jobs", job["key"])}
        if "steps" in inside and not MINUTES.match(inside.get("timeout-minutes", {}).get("value", "")):
            found.append(("timeout", "job %s has no timeout-minutes" % job["key"]))
        # A job GitHub stops at its own timeout concludes cancelled, as its check run does, which no required check or
        # Run reads as a failure; a step stopped at its own fails, and its job with it (trials/P-42.step-timeout.json).
        # So each run: step has a limit of its own, and the run: steps together leave their job MARGIN minutes for its
        # other steps, which have none (issue 388).
        steps = under("jobs", job["key"], "steps")
        given = [next((e["value"] for e in steps if e["step"] == s["step"] and e["key"] == "timeout-minutes"), "")
                 for s in steps if s["key"] == "run"]
        if not all(MINUTES.match(minutes) for minutes in given):
            found.append(("timeout", "a run: step of job %s has no timeout-minutes of its own" % job["key"]))
        elif given and MINUTES.match(inside.get("timeout-minutes", {}).get("value", "")) and \
                sum(map(int, given)) + MARGIN > int(inside["timeout-minutes"]["value"]):
            found.append(("timeout", "the run: steps of job %s are given %d minutes together, more than its %s less the %d "
                          "its other steps keep" % (job["key"], sum(map(int, given)), inside["timeout-minutes"]["value"],
                                                    MARGIN)))
        if "environment" in inside and events != {"workflow_call"}:
            found.append(("shim", "job %s names an environment in a workflow that is not called alone" % job["key"]))
    if events & SHIM_EVENTS:
        found += [("shim", why) for why in _shim(text, entries, top, jobs)]
    for e in entries:
        if e["path"][-1:] == ["env"] and e["key"].upper() == SCRUB:
            found.append(("model", "a step sets %s, which only the Engine sets, with --tools \"\"" % SCRUB))
    # A step's environment is its own, its job's and its workflow's, merged: in a workflow that names the model's
    # credential, no env: at any level is handed a tool list.
    if any(MODEL_SECRET.search(e["value"]) for e in entries):
        if any(e["path"][-1:] == ["env"] and (TOOLS.search(e["key"]) or TOOLS.search(e["value"])) for e in entries):
            found.append(("model", "the workflow that holds the model's credential hands an env: a tool list"))
    for job in jobs:
        inside = {e["key"]: e for e in under("jobs", job["key"])}
        calls = inside.get("uses", {}).get("value", "")
        if calls.split("@")[0].endswith("/" + RUN_JOBS):
            lane = {e["key"]: e["value"] for e in under("jobs", job["key"], "concurrency")}
            if lane != {"group": LANE, "cancel-in-progress": "false"}:
                found.append(("lane", "job %s calls the Run's jobs outside its item's lane, or cancels a Run" % job["key"]))
    if "workflow_run" in events:
        found += [("wake", why) for why in _wake(text, entries, top)]

    by_line = {e["line"]: e for e in entries}
    for number, raw in enumerate(text.split("\n"), 1):
        e = by_line.get(number)
        if "${{" in raw:
            passed = e is not None and e["key"] != "script" and (
                e["key"] == "if" or (WHOLE.match(e["value"]) and set(e["path"]) & {"env", "with", "secrets"})
                or (e["path"] == [] and e["key"] == "run-name" and e["value"] == RUN_NAME)
                or (e["path"][-1:] == ["concurrency"] and len(e["path"]) == 3 and e["key"] == "group"
                    and e["value"] == LANE)
                or (e["path"][-1:] == ["outputs"] and len(e["path"]) == 3 and bool(OUTPUT.match(e["value"]))))
            if not passed:
                found.append(("expression", "line %d writes an expression where it could become a command" % number))
        for use in SECRET.finditer("" if raw.lstrip().startswith("#") else raw.split(" #")[0]):
            name = use.group(2) or use.group(3)
            keyed = e is not None and e["key"] == "secrets" and use.start() == raw.find("secrets")
            if (name is None and not keyed) or (name and PERSONAL.search(name)):
                found.append(("token", "line %d names a personal token, or every secret at once" % number))
    return sorted(set(found))


def _uncommented(text: str) -> str:
    """The text with its whole-line comments left out. A ` #` within a line may sit inside a quoted value, so the rest
    of such a line is read as written, and a trailing comment that names the context is refused with it."""
    return "\n".join("" if line.lstrip().startswith("#") else line for line in text.split("\n"))


def _shim(text: str, entries: list, top: dict, jobs: list) -> list:
    """Why a workflow on a shim's events is not a shim: something above its jobs but the name, the events, the grant
    and a run's name; or a job that holds anything but its call, its grant, its concurrency group, an if: and the
    inputs it passes on, each `${{ inputs.<the same name> }}`; or one that calls anything but a file of the Release."""
    whys = ["it holds %s above its jobs" % key for key in sorted(set(top) - SHIM_TOP)]
    for job in jobs:
        inside = {e["key"]: e for e in entries if e["path"] == ["jobs", job["key"]]}
        if set(inside) - SHIM_JOB or not SHIM_NEEDS <= set(inside):
            whys.append("job %s holds %s, not a call, its grant and its concurrency alone"
                        % (job["key"], ", ".join(sorted(inside))))
        held = {e["key"]: e["value"] for e in entries if e["path"] == ["jobs", job["key"], "concurrency"]}
        calls_run = inside.get("uses", {}).get("value", "").split("@")[0].endswith("/" + RUN_JOBS)
        if "concurrency" in inside and not calls_run and (set(held) != {"group", "cancel-in-progress"} or not held["group"]
                                        or held["cancel-in-progress"] != "false"):
            whys.append("job %s holds no group of its own that waits, never cancelling the run in progress" % job["key"])
        given = [e for e in entries if e["path"] == ["jobs", job["key"], "with"]]
        if "with" in inside and (inside["with"]["value"] or not given):
            whys.append("job %s passes its inputs on in one line, not one input to a line" % job["key"])
        if "uses" in inside and not RELEASE.match(inside["uses"]["value"]):
            whys.append("job %s calls %s, not a file of the Release at its channel" % (job["key"], inside["uses"]["value"]))
        for e in entries:
            if e["path"] == ["jobs", job["key"], "with"] and e["value"] != "${{ inputs.%s }}" % e["key"]:
                whys.append("job %s passes %s something but the input of that name" % (job["key"], e["key"]))
    return whys


def _wake(text: str, entries: list, top: dict) -> list:
    """Why a workflow on workflow_run would wake on more than a completion of the workflows it names: its own end,
    every stage of a run, an input, or anything it reads of the run that woke it."""
    whys = []
    keys = {e["key"]: e for e in entries if e["path"] == ["on", "workflow_run"]}
    names = _listed(text, keys["workflows"]) if "workflows" in keys else None
    types = _listed(text, keys["types"]) if "types" in keys else None
    if set(keys) != {"workflows", "types"} or not names or types != ["completed"]:
        whys.append("it wakes on more than the completion of the workflows it names")
    if names and top.get("name", {}).get("value") in names:
        whys.append("it wakes on its own end")
    if any(e["path"][:2] == ["on", "workflow_dispatch"] for e in entries):
        whys.append("it takes an input")
    if GITHUB_ANY.search(_uncommented(text)):
        whys.append("it reads the run that woke it")
    return whys


def _listed(text: str, entry: dict):
    """The values of `entry`: its own, or the items of the block list under it; None where one is not a job's id."""
    if entry["value"]:
        values = [entry["value"]]
    else:
        values = []
        for raw in text.split("\n")[entry["line"]:]:
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            item = ITEM.match(raw.rstrip())
            if item is None or len(item.group(1)) < entry["indent"]:
                break
            values.append(_unquote(item.group(2).partition(" #")[0].strip()))
    return values if values and all(JOB.match(v) for v in values) else None


def _checkout(entry: dict) -> bool:
    return entry["key"] == "uses" and entry["value"].lower().startswith("actions/checkout@")


def _with(entries: list, step: dict) -> dict:
    """{key: value} under the `with:` of the step that `step`, one of its entries, belongs to."""
    return {e["key"]: e["value"] for e in entries
            if e["step"] == step["step"] and e["path"] == step["path"] + ["with"]}


def _steps(entries: list, job: str) -> list:
    """The steps of `job`, in order: for each, {key: entry} of its own keys."""
    steps = {}
    for e in entries:
        if e["path"] == ["jobs", job, "steps"]:
            steps.setdefault(e["step"], {})[e["key"]] = e
    return [steps[number] for number in sorted(steps)]


def _lines(entry) -> list:
    """The command lines of a `run:` entry: its block, or its one line; none for anything else."""
    return (entry["body"] or [entry["value"]]) if entry and entry["key"] == "run" else []


def _block(entry, bad: list):
    """The command lines of a `run:` entry as bash is given them: None where a line of its file cannot be read, which
    read() leaves out of every block, or where its block is not literal, `|`, since `>` folds its lines into one."""
    if bad or (entry and entry["body"] and entry["value"] != "|"):
        return None
    return _lines(entry)


def raw(path: pathlib.Path) -> str:
    """A workflow's text as its bytes say, with no newline translation: `read_text` would turn a carriage return into a
    line end, and a line the shell would run with one in it must reach `read()` to be refused."""
    return path.read_bytes().decode(errors="replace")


def scan_problems(text: str) -> list:
    """Why the secret scan in `text` could be passed by the head it scans: its rules not read from the base.

    Its one job runs four steps, in this order and nothing else: the head's checkout, with its history; the base's,
    under `base/`, at the base's commit; the install, whose whole block is INSTALL_RUN, given a version and a checksum
    of their shapes; and the scan, whose whole block is SCAN_RUN, telling gitleaks the base's `.gitleaks.toml` and
    `.gitleaksignore` on the line after the head's `.gitleaksignore` is deleted. Nothing sets an environment, a
    directory or a container that the scan could run in instead. Both blocks are literal, and a file with a line
    read() cannot read, which it leaves out of a block, holds neither.
    """
    entries, bad = read(text)
    problems = []
    jobs = [e["key"] for e in entries if e["path"] == ["jobs"]]
    steps = _steps(entries, jobs[0]) if len(jobs) == 1 else []
    if [_with(entries, e) for e in entries if _checkout(e)] != SCAN_CHECKOUTS:
        problems.append("%s does not check out the head and then the base, under base/ at `ref: %s`, and nothing "
                        "else, so the scan's rules may not be the base's" % (SCAN, SCAN_BASE))
    install = steps[2] if len(steps) == 4 else {}
    given = {e["key"] for e in entries if install.get("env") and e["step"] == install["env"]["step"]
             and e["path"] == install["env"]["path"] + ["env"]}
    shaped = (len(jobs) == 1 and len(steps) == 4
              and {e["key"] for e in entries if e["path"] == []} <= SCAN_TOP
              and {e["key"] for e in entries if e["path"] == ["jobs", jobs[0]]} <= SCAN_JOB
              and all(set(step) <= {"name", "uses", "with"} and _checkout(step.get("uses", {"key": ""}))
                      for step in steps[:2])
              and set(install) <= {"name", "env", "run", "timeout-minutes"} and given == ({*SCAN_ENV} if "env" in install else set())
              and set(steps[3]) <= {"name", "run", "timeout-minutes"})
    if not shaped:
        problems.append("%s does not run, in this order and nothing else, the head's checkout, the base's, the "
                        "install and the scan, with no environment, directory or container of its own: a step could "
                        "change base/ or what the scan reads" % SCAN)
    if _block(install.get("run"), bad) != INSTALL_RUN:
        problems.append("%s does not install gitleaks by INSTALL_RUN, word for word, as its third step's whole literal "
                        "block in a file read whole: another install could put another program where the scan runs "
                        "gitleaks" % SCAN)
    lines = text.split("\n")
    for key, shape in SCAN_ENV.items():
        values = [lines[e["line"] - 1].strip()[len(key) + 2:] for e in entries if e["key"] == key and install.get("env")
                  and e["step"] == install["env"]["step"] and e["path"] == install["env"]["path"] + ["env"]]
        if len(values) != 1 or not shape.fullmatch(values[0]):
            problems.append("%s does not give the install %s once, as %s: a value of another shape could change what "
                            "the install fetches" % (SCAN, key, shape.pattern))
    if _block(steps[-1].get("run") if steps else None, bad) != SCAN_RUN:
        problems.append("%s does not run, as its last step's whole literal block in a file read whole, `%s` on the line "
                        "after `%s`: it could read the head's .gitleaks.toml or .gitleaksignore, and a change could "
                        "widen the allowlist it needs"
                        % (SCAN, SCAN_RUN[1], SCAN_RUN[0]))
    return problems


def _judging(text: str, entries: list, job: str, jobs: list) -> list:
    """Why the job `job`, which has `needs:` or shares its file with other jobs, would pass, or never report, when one
    of them did not pass.

    A job it does not need is a check nobody requires. With a plain `needs:` it is skipped when one fails, and GitHub
    passes a required check that is skipped. Under `if: always()` it runs whatever they did, so it must judge them: run
    tools.needs_passed on `needs` given whole, as its one step but a checkout, and need every other job.
    """
    mine = [e for e in entries if e["path"][:2] == ["jobs", job]]
    inside = {e["key"]: e for e in mine if e["path"] == ["jobs", job]}
    whys = []
    if inside.get("if", {}).get("value") != ALWAYS:
        whys.append("it has no job-level if: always(), so it is skipped when one of them fails, and a skipped "
                    "required check passes")
    needs = _listed(text, inside["needs"]) if "needs" in inside else []
    others = [j for j in jobs if j != job]
    if "needs" not in inside:
        whys.append("it has no needs:, so the other jobs in its file, %s, are checks nobody requires"
                    % ", ".join(others))
    elif needs is None:
        whys.append("its needs: cannot be read as a list of jobs")
    elif sorted(set(needs)) != sorted(others):
        whys.append("it needs %s, not every other job in its file, %s: a job it does not need is a check nobody "
                    "requires" % (", ".join(needs), ", ".join(others) or "none"))
    steps = [e for e in mine if e["path"] == ["jobs", job, "steps"]]
    runs = [e for e in steps if e["key"] == "run"]
    # One line, no block: in a block an earlier line can exit first, and `>` folds the lines into one command.
    judged = [e for e in runs if e["value"] == JUDGE and not e["body"]]
    if not judged:
        whys.append("it runs no step `%s`, on a line of its own, to fail it when one of them did not pass" % JUDGE)
    elif any(e["key"] == "if" and e["step"] == j["step"] for e in steps for j in judged):
        whys.append("an if: can skip its step `%s`" % JUDGE)
    if len(runs) > 1 or any(e["key"] == "uses" and not e["value"].startswith("actions/checkout@") for e in steps):
        whys.append("its steps are more than a checkout and `%s`, and another could act for it" % JUDGE)
    events = {e["key"] for e in entries if e["path"] == ["on"]}
    events |= {e["value"] for e in entries if e["path"] == [] and e["key"] == "on" and e["value"]}
    if events - JUDGED:
        whys.append("its workflow runs on %s, where there is no base to check out, so `ref: %s` would come out empty "
                    "and the checkout would be the head's: run it on pull_request and merge_group alone"
                    % (", ".join(sorted(events - JUDGED)), BASE))
    if [_with(entries, c) for c in steps if _checkout(c)] != [{"persist-credentials": "false", "ref": BASE}]:
        whys.append("its one checkout is not of the base alone, `ref: %s` and persist-credentials: false and nothing "
                    "else, so the head's own tools/needs_passed.py could give its verdict" % BASE)
    if [(e["path"], e["value"]) for e in mine if e["key"] == "NEEDS"] != [(["jobs", job, "env"], NEEDS)]:
        whys.append("it does not give NEEDS: %s once, in its own env:, so what it needs cannot be read" % NEEDS)
    if [e["key"] for e in mine if e["path"] == ["jobs", job, "env"]] != ["NEEDS"]:
        whys.append("its env: holds other than NEEDS, with which the interpreter that runs `%s` could be changed" % JUDGE)
    # Its exact shape (issue 180): no key the rule does not name, on the job or on a step, so that nothing can change
    # where or how `JUDGE` runs: a working-directory:, a shell:, a container:, a default, an env: on the step.
    if set(inside) - JUDGING_KEYS:
        whys.append("it has keys other than %s: %s, with which a container, a default or a strategy could change what "
                    "runs" % (", ".join(sorted(JUDGING_KEYS)), ", ".join(sorted(set(inside) - JUDGING_KEYS))))
    if {e["key"]: e["value"] for e in mine if e["path"] == ["jobs", job, "permissions"]} != {"contents": "read"}:
        whys.append("it is granted other than contents: read")
    if [set(step) for step in _steps(entries, job)] != [{"uses", "with"}, {"run", "timeout-minutes"}]:
        whys.append("its steps are not a checkout with its with: and then one run: with its own timeout-minutes, "
                    "each holding no other key: a "
                    "working-directory:, a shell:, an env: or an if: on the step would change where or how `%s` runs"
                    % JUDGE)
    return whys


def _shards(entries: list, jobs: list) -> list:
    """Why the workflow would not run every mutant once (issue 180): a job that runs the mutants exists, and its env: is exactly
    MUTANTS_SHARD: INDEX and MUTANTS_SHARDS: TOTAL, the matrix's own index and size, so a number written in cannot make
    every leg run one shard; its matrix is one key, shard; and its shape is closed: the keys SHARD_KEYS and no other,
    contents: read, a checkout of the head with the whole history and `SHARDED` on a line of its own, each step holding
    no other key."""
    whys, found = [], False
    for job in jobs:
        mine = [e for e in entries if e["path"][:2] == ["jobs", job]]
        inside = {e["key"]: e for e in mine if e["path"] == ["jobs", job]}
        runs = [e for e in mine if e["path"] == ["jobs", job, "steps"] and e["key"] == "run"]
        if not any("mutants" in "\n".join([e["value"]] + (e["body"] or [])) for e in runs):
            continue
        found = True
        if set(inside) != SHARD_KEYS:
            whys.append("has the job %s, which runs the mutants, with keys other than %s, or lacking one"
                        % (job, ", ".join(sorted(SHARD_KEYS))))
        if {e["key"]: e["value"] for e in mine if e["path"] == ["jobs", job, "env"]} != {"MUTANTS_SHARD": INDEX,
                                                                                             "MUTANTS_SHARDS": TOTAL}:
            whys.append("has the job %s, which runs the mutants, not told MUTANTS_SHARD: %s and MUTANTS_SHARDS: %s and "
                        "nothing else, so a leg could run another's shard, or every leg one shard" % (job, INDEX, TOTAL))
        if [e["key"] for e in mine if e["path"] == ["jobs", job, "strategy", "matrix"]] != ["shard"]:
            whys.append("has the job %s, which runs the mutants, whose strategy.matrix is not the one key shard" % job)
        if {e["key"]: e["value"] for e in mine if e["path"] == ["jobs", job, "permissions"]} != {"contents": "read"}:
            whys.append("has the job %s, which runs the mutants, granted other than contents: read" % job)
        checkouts = [e for e in mine if e["path"] == ["jobs", job, "steps"] and _checkout(e)]
        held = ([set(step) for step in _steps(entries, job)] == [{"uses", "with"}, {"run", "timeout-minutes"}]
                  and [(e["value"], e["body"] or []) for e in runs] == [(SHARDED, [])]
                  and [_with(entries, c) for c in checkouts] == [{"persist-credentials": "false", "fetch-depth": "0"}])
        if not held:
            whys.append("has the job %s, which runs the mutants, whose steps are not a checkout of the head with the "
                        "whole history and `%s` on a line of its own with its own timeout-minutes, each holding no other key"
                        % (job, SHARDED))
    if not found:
        whys.append("has no job that runs the mutants, so no mutant runs before a merge")
    return whys


def _commits(text: str, entries: list, jobs: list) -> list:
    """Why the workflow's job `commits` would not read every commit the pull request carries from the base (decision
    0041). Its shape is closed: the keys runs-on, timeout-minutes, permissions (contents: read, pull-requests: read, and
    nothing else), env and steps and no other, so no container, strategy, if: or default can change what runs; env:
    exactly BASE_SHA, HEAD_SHA, EVENT and the job's own token as the expressions name them; two steps, a checkout of the base with the whole history and persist-credentials: false,
    and `COMMITS` on a line of its own, each step holding no other key, since a step's env: or if: would override the
    job's or skip it."""
    if "commits" not in jobs:
        return ["has no job commits, which reads every commit the pull request carries from the base"]
    mine = [e for e in entries if e["path"][:2] == ["jobs", "commits"]]
    inside = {e["key"]: e for e in mine if e["path"] == ["jobs", "commits"]}
    whys = []
    if set(inside) != {"runs-on", "timeout-minutes", "permissions", "env", "steps"}:
        whys.append("its job commits has keys other than runs-on, timeout-minutes, permissions, env and steps, or lacks "
                    "one: a container, a strategy, an if: or a default could change what runs")
    if {e["key"]: e["value"] for e in mine if e["path"] == ["jobs", "commits", "permissions"]} \
            != {"contents": "read", "pull-requests": "read"}:
        whys.append("its job commits is granted other than contents: read and pull-requests: read")
    given = {e["key"]: e["value"] for e in mine if e["path"] == ["jobs", "commits", "env"]}
    if given != {"BASE_SHA": BASE, "HEAD_SHA": HEAD, "EVENT": EVENT, "WORKFLOW_TOKEN": JOB_TOKEN}:
        whys.append("its job commits is not told BASE_SHA: %s, HEAD_SHA: %s, EVENT: %s and WORKFLOW_TOKEN: %s in its own "
                    "env:, and nothing else" % (BASE, HEAD, EVENT, JOB_TOKEN))
    steps = _steps(entries, "commits")
    keys = [set(step) for step in steps]
    wanted = {"persist-credentials": "false", "fetch-depth": "0", "ref": BASE}
    if keys != [{"uses", "with"}, {"run", "timeout-minutes"}]:
        whys.append("its job commits's steps are not a checkout with its with: and then one run: with its own "
                    "timeout-minutes, each holding no "
                    "other key: a step's env: or if: would override the job's or skip it, and another step could act "
                    "for it")
    checkouts = [e for e in mine if e["path"] == ["jobs", "commits", "steps"] and _checkout(e)]
    if [_with(entries, c) for c in checkouts] != [wanted]:
        whys.append("its job commits does not check out the base alone, with the whole history: `ref: %s`, "
                    "fetch-depth: 0 and persist-credentials: false and nothing else" % BASE)
    runs = [e for e in mine if e["path"] == ["jobs", "commits", "steps"] and e["key"] == "run"]
    if [(e["value"], e["body"]) for e in runs] != [(COMMITS, [])] and [(e["value"], e["body"]) for e in runs] != [(COMMITS, None)]:
        whys.append("its job commits runs no step `%s`, on a line of its own, as its one run:" % COMMITS)
    return whys


def _kind(step: dict) -> str:
    """What one step of the eval job is: the listed checkout, the upload, one of harness.eval's steps, or None."""
    uses = step.get("uses", {}).get("value", "") if "uses" in step else None
    if uses is not None and "run" not in step:
        if (uses, step["uses"]["comment"]) == CHECKOUT:
            return "checkout"
        return "upload" if (uses, step["uses"]["comment"]) == UPLOAD else None
    command = _lines(step.get("run"))
    if "uses" not in step and step.get("run", {}).get("value") == "|" and command == CLI_INSTALL_RUN:
        return "install"
    # The install is its block alone: a module of that name is no install, and is refused as a step of no kind.
    for name in EVAL_ORDER:
        if name not in EVAL_ACTIONS | {"install"} and command == [EVAL_STEP % name] and "uses" not in step:
            return name
    return None


def eval_problems(text: str, root: pathlib.Path = ROOT) -> list:
    """What is wrong with eval.yml's shape (issue 309, ruling 10), each a sentence. It runs on `workflow_dispatch` alone,
    with one input, the Release it judges, and one job, `eval`, on the environment `factory-eval`, granted
    `contents: read` alone and given no env: of its own. Its steps are EVAL_ORDER, each given exactly what EVAL_GIVEN
    says and nothing else: the Maintainer's token for the held-out home by `fetch` alone, the model's
    credential by `run` alone, so no step holds both, and the upload takes the report alone. Every other spelling is
    refused: a check reads what it names, never what it can guess. The CLI's install is CLI_INSTALL_RUN, word for word,
    given the Engine's pin in config/harness.json and its checksum in CLI_CHECKSUMS, as the Run's jobs' is."""
    entries, bad = read(text)
    if bad:
        return ["line %d is not in the narrow form" % bad[0]]
    try:
        version = json.loads((root / "config" / "harness.json").read_text())["engine"]["version"]
    except (OSError, ValueError, KeyError, TypeError):
        version = None
    if not isinstance(version, str) or version not in CLI_CHECKSUMS:
        return ["config/harness.json pins no CLI whose checksum CLI_CHECKSUMS holds, so no install of it can be held"]
    given_of = dict(EVAL_GIVEN, install={"env": {"CLI_VERSION": version, "CLI_CHECKSUM": CLI_CHECKSUMS[version]}})
    problems = []
    # Nothing above the job: an env: or a default there would reach every step, the model's among them.
    if {e["key"]: e["value"] for e in entries if e["path"] == []} != EVAL_TOP:
        problems.append("it holds name: factory, on:, permissions: {} and jobs:, and nothing else above its job")
    events = {e["key"] for e in entries if e["path"] == ["on"]}
    inputs = [e for e in entries if e["path"][:3] == ["on", "workflow_dispatch", "inputs"]]
    if events != {"workflow_dispatch"} or sorted((e["key"], e["value"]) for e in inputs if len(e["path"]) == 4) != \
            [("required", "true"), ("type", "string")] or [e["key"] for e in inputs if len(e["path"]) == 3] != ["release"]:
        problems.append("runs on workflow_dispatch alone, with one input, release, a required string")
    if [e["key"] for e in entries if e["path"] == ["jobs"]] != [EVAL_JOB]:
        problems.append("it holds the job %s and no other" % EVAL_JOB)
    inside = {e["key"]: e for e in entries if e["path"] == ["jobs", EVAL_JOB]}
    if set(inside) != EVAL_JOB_KEYS or inside["environment"]["value"] != EVAL_ENVIRONMENT:
        problems.append("its job has exactly %s, and runs on the environment %s"
                        % (", ".join(sorted(EVAL_JOB_KEYS)), EVAL_ENVIRONMENT))
    if {k: inside[k]["value"] for k in EVAL_RUNNER if k in inside} != EVAL_RUNNER:
        problems.append("its job runs on %(runs-on)s, with a timeout of %(timeout-minutes)s minutes" % EVAL_RUNNER)
    granted = sorted((e["key"], e["value"]) for e in entries if e["path"] == ["jobs", EVAL_JOB, "permissions"])
    if granted != [("contents", "read")]:
        problems.append("its job is granted contents: read and nothing else")
    steps = _steps(entries, EVAL_JOB)
    kinds = [_kind(step) for step in steps]
    if tuple(kinds) != EVAL_ORDER:
        problems.append("its steps are %s, in that order, and no other" % ", ".join(EVAL_ORDER))
    for step, kind in zip(steps, kinds):
        if kind is None:
            continue
        number = next(iter(step.values()))["step"]
        own = set(step) - EVAL_STEP_KEYS
        if own:
            problems.append("its %s step has a key it may not: %s" % (kind, ", ".join(sorted(own))))
        for under in ("with", "env"):
            given = {e["key"]: e["value"] for e in entries if e["step"] == number
                     and e["path"] == ["jobs", EVAL_JOB, "steps", under]}
            if given != given_of[kind].get(under, {}):
                problems.append("its %s step is given under %s: %s, exactly" % (kind, under, given_of[kind].get(under, {})))
            if under in step and (step[under]["value"] or under not in given_of[kind]):
                problems.append("its %s step has a %s: it is not given" % (kind, under))
    return problems


def _release_kind(step: dict):
    """What one step of the release job is: the token's mint, the listed checkout, the release step, or None."""
    uses = step.get("uses", {}).get("value", "") if "uses" in step else None
    if uses is not None and "run" not in step:
        if (uses, step["uses"]["comment"]) == CHECKOUT:
            return "checkout"
        return "mint" if (uses, step["uses"]["comment"]) == APP_TOKEN else None
    return "step" if _lines(step.get("run")) == [RELEASE_STEP] and "uses" not in step else None


def release_problems(text: str) -> list:
    """What is wrong with release.yml's shape (issue 197, ruling 4′), each a sentence: RELEASE_TOP above one job,
    `release`, dispatched and scheduled as RELEASE_ON writes, run only as RELEASE_IF says, on the environment
    `factory-release`, granted `contents: read` alone, one at a time; its steps RELEASE_ORDER, each given exactly what
    RELEASE_GIVEN says. Every other spelling is refused: a check reads what it names, never what it can guess."""
    entries, bad = read(text)
    if bad:
        return ["line %d is not in the narrow form" % bad[0]]
    problems = []
    if {e["key"]: e["value"] for e in entries if e["path"] == []} != RELEASE_TOP:
        problems.append("it holds name: sf-release, on:, permissions: {} and jobs:, and nothing else above its job")
    # Its triggers are held word for word, as RELEASE_ON writes them: the options and the schedule are lists the reader
    # keeps no entry of, and a blank line or a comment between their items would hide one more from a reading by keys.
    held_on = text[text.find("\non:\n") + 1:text.find("\npermissions:")] if "\non:\n" in text else ""
    if held_on + "\n" != RELEASE_ON:
        problems.append("runs on workflow_dispatch, with the inputs command (cut, move or rollback), version and to, "
                        "and on a schedule, and on nothing else")
    if [e["key"] for e in entries if e["path"] == ["jobs"]] != [RELEASE_JOB]:
        problems.append("it holds the job %s and no other" % RELEASE_JOB)
    inside = {e["key"]: e for e in entries if e["path"] == ["jobs", RELEASE_JOB]}
    if set(inside) != RELEASE_JOB_KEYS or inside["environment"]["value"] != RELEASE_ENVIRONMENT:
        problems.append("its job has exactly %s, and runs on the environment %s"
                        % (", ".join(sorted(RELEASE_JOB_KEYS)), RELEASE_ENVIRONMENT))
    if {k: inside[k]["value"] for k in RELEASE_RUNNER if k in inside} != RELEASE_RUNNER:
        problems.append("its job runs on GitHub's own runner, %s, for at most %s minutes"
                        % (RELEASE_RUNNER["runs-on"], RELEASE_RUNNER["timeout-minutes"]))
    if "if" in inside and inside["if"]["value"] != RELEASE_IF:
        problems.append("its job runs on a dispatch, or on the schedule only when FACTORY_RELEASE_AUTO is true and no "
                        "Pause is set: if: %s" % RELEASE_IF)
    held = {e["key"]: e["value"] for e in entries if e["path"] == ["jobs", RELEASE_JOB, "concurrency"]}
    if held != RELEASE_CONCURRENCY:
        problems.append("its job runs one at a time and never cancels one in progress: concurrency %s" % RELEASE_CONCURRENCY)
    granted = sorted((e["key"], e["value"]) for e in entries if e["path"] == ["jobs", RELEASE_JOB, "permissions"])
    if granted != RELEASE_GRANTED:
        problems.append("its job is granted contents: read and nothing else; its writes are the App's token's")
    steps = _steps(entries, RELEASE_JOB)
    kinds = [_release_kind(step) for step in steps]
    if tuple(kinds) != RELEASE_ORDER or _scalar_items(text, entries, RELEASE_JOB):
        problems.append("its steps are %s, in that order, and no other" % ", ".join(RELEASE_ORDER))
    for step, kind in zip(steps, kinds):
        if kind is None:
            continue
        number = next(iter(step.values()))["step"]
        own = set(step) - RELEASE_STEP_KEYS[kind]
        if own or (kind == "mint" and step.get("id", {}).get("value") != "mint"):
            problems.append("its %s step has exactly %s" % (kind, ", ".join(sorted(RELEASE_STEP_KEYS[kind]))))
        for under in ("with", "env"):
            have = {e["key"]: e["value"] for e in entries if e["step"] == number
                    and e["path"] == ["jobs", RELEASE_JOB, "steps", under]}
            if have != RELEASE_GIVEN[kind].get(under, {}):
                problems.append("its %s step is given under %s: %s, exactly"
                                % (kind, under, RELEASE_GIVEN[kind].get(under, {})))
            # A value written beside `with:` or `env:` is no mapping: the step is given that text, not its keys. A step
            # that takes neither has it as a key of its own, refused above.
            if under in step and step[under]["value"]:
                problems.append("its %s step has a %s: it is not given" % (kind, under))
    return problems


COMPACT_EVENT = "schedule"       # the one event whose value is a list, which may stand at its own key's indent,
COMPACT_ITEM = re.compile(r"- cron:( |$)")   # each item of it a cron, its key read as the reader reads one (Codex on #428)


def _on_items(text: str, on: dict) -> list:
    """The lines of the top-level on: section that are list items where its events stand, keyed or bare: an on:
    written as a list, which `read` keeps only the keyed items of, as entries (Argon's read of #392). A list deeper in,
    an event's `branches:`, is its own. The items may stand at the key's own indent, YAML's compact form. An item at
    the events' level that follows `schedule:`, the one event whose value is a list, is the compact form of that list,
    `- cron:`, and is the event's (Muse's read of #416). Any other item there stays an on: written as a list, after
    another key or under schedule: as anything but a cron: the check allows what it names and refuses what it does not
    read (the Claude review of #428)."""
    section = []
    for number, raw in enumerate(text.split("\n")[on["line"]:], on["line"] + 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        item = raw.lstrip(" ").startswith("- ")
        lead = len(raw) - len(raw.lstrip(" "))
        if lead < on["indent"] or (lead == on["indent"] and not item):
            break       # the next key beside on:, at its own indent however far the root stands in (Muse's read)
        section.append((lead, number, item, raw.strip()))
    events = min((lead for lead, _, _, _ in section), default=0)
    found, key, compact = [], None, False
    for lead, number, item, line in section:
        if lead > events:
            # A list begun deeper under schedule: is its list, and a compact item after it no part of it; a deeper line
            # after its compact crons is no part of theirs (Codex on #428).
            if key == COMPACT_EVENT and compact:
                found.append(number)
            key = None if key == COMPACT_EVENT else key
        elif not item:
            name, _, rest = line.partition(":")
            # A key with a value of its own on its line is never one whose list follows (Codex on #428).
            bare = not rest.strip() or (rest[:1].isspace() and rest.strip().startswith("#"))
            key = name.strip() if bare else line
        elif key != COMPACT_EVENT or not COMPACT_ITEM.match(line):
            found.append(number)
        else:
            compact = True
    return found


def _scalar_items(text: str, entries: list, job: str, steps_only: bool = False) -> list:
    """The lines of `job`'s steps that are no mapping, a bare `- text` item, which `read` keeps no entry of (issue 197,
    Muse's read of #358): such a step is one more step the reading by keys would not see. With `steps_only`, only a
    line where the steps stand: a `- ` deeper in, a block's text, is no step (#416's review)."""
    above = [e for e in entries if e["key"] == "steps" and e["path"] == ["jobs", job]]
    if len(above) != 1:
        return []
    found, indent, items = [], above[0]["indent"], None
    for number, raw in enumerate(text.split("\n")[above[0]["line"]:], above[0]["line"] + 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        lead = len(raw) - len(raw.lstrip(" "))
        # The items may sit at the key's own indent, YAML's compact form, which `read` takes too.
        if lead < indent or (lead == indent and not raw.lstrip(" ").startswith("- ")):
            break
        if items is None and raw.lstrip(" ").startswith("- "):
            items = lead        # where the steps stand
        if (lead == items or not steps_only) and ENTRY.match(raw.rstrip()) is None and ITEM.match(raw.rstrip()) is not None:
            found.append(number)
    return found


def run_problems(text: str, root: pathlib.Path = ROOT) -> list:
    """What is wrong with run.yml: anything but the Run's shim as the ruling gives it, its dispatcher the account that
    config/controller.json names for the pass's own token. While it names none, no run.yml is right."""
    try:
        account = json.loads((root / "config" / "controller.json").read_text())["accounts"]["workflow_token"]
    except (OSError, ValueError, KeyError, TypeError):
        account = None
    if not isinstance(account, dict) or type(account.get("id")) is not int:
        return ["config/controller.json names no account for the pass's own token, so no Run's dispatcher can be held"]
    lines = [line for line in text.split("\n") if line.strip() and not line.lstrip().startswith("#")]
    if lines != (RUN_SHIM % account["id"]).strip("\n").split("\n"):
        return ["it is not the Run's shim, word for word, its dispatcher %d and a Pause starting nothing" % account["id"]]
    return []


def _held(text: str) -> list:
    return [line for line in text.split("\n") if line.strip() and not line.lstrip().startswith("#")]


def run_jobs_problems(text: str, root: pathlib.Path = ROOT) -> list:
    """What is wrong with run-jobs.yml: anything but RUN_JOBS_FILE, word for word but for its comments, its CLI the
    Engine's pin in config/harness.json and the checksum CLI_CHECKSUM."""
    try:
        version = json.loads((root / "config" / "harness.json").read_text())["engine"]["version"]
    except (OSError, ValueError, KeyError, TypeError):
        version = None
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        return ["config/harness.json names no Engine pin, so no install of the CLI can be held"]
    if version not in CLI_CHECKSUMS:
        return ["config/harness.json pins the CLI at %s, and CLI_CHECKSUMS holds no checksum for it" % version]
    if _held(text) != _held(RUN_JOBS_FILE % {"version": version, "checksum": CLI_CHECKSUMS[version]}):
        return ["it is not the Run's three jobs, word for word, its CLI %s by its checksum" % version]
    return []


def pass_problems(text: str) -> list:
    """What is wrong with pass.yml: anything but PASS_FILE, word for word but for its comments."""
    if _held(text) != _held(PASS_FILE):
        return ["it is not the pass, word for word: its record uploaded before it dispatches, its keys on their steps"]
    return []


def approve_job_problems(text: str) -> list:
    """What is wrong with approve-job.yml: anything but APPROVE_JOB_FILE, word for word but for its comments."""
    if _held(text) != _held(APPROVE_JOB_FILE):
        return ["it is not the approving act's one job, word for word"]
    return []


def shim_problems(name: str, text: str, root: pathlib.Path = ROOT) -> list:
    """What is wrong with one live workflow by its file's name: a shim not held word for word by its hash in SHIMS, a
    workflow that wakes on another's end that is not the poller, or the pass job anywhere but the poller and the pass."""
    entries, bad = read(text)
    if bad:
        return []
    events = {e["key"] for e in entries if e["path"] == ["on"]}
    events |= {e["value"] for e in entries if not e["path"] and e["key"] == "on" and e["value"]}
    problems = []
    if events & SHIM_EVENTS and name not in SHAPED:
        held = SHIMS.get(name)
        if held is None or hashlib.sha256(PIN.sub("@PIN", text).encode()).hexdigest() != held:
            problems.append("a shim is held word for word, and this one is not in SHIMS or has changed; if the change "
                            "is meant, record its new hash in SHIMS")
    if "workflow_run" in events and name != WAKES:
        problems.append("only %s wakes on another workflow's end" % WAKES)
    if name == "run.yml":
        problems += run_problems(text, root)
    elif any(e["key"] == "uses" and e["value"].split("@")[0].endswith("/" + RUN_JOBS) for e in entries):
        problems.append("only run.yml calls the Run's jobs, from the pass's own token and never under a Pause")
    if name == RUN_JOBS:
        problems += run_jobs_problems(text, root)
    if name == APPROVE_JOB:
        problems += approve_job_problems(text)
    if name == PASS_WORKFLOW:
        problems += pass_problems(text)
    for owner, named in KEYED.items():
        if name != owner and named.search(_uncommented(text)):
            problems.append("it names a key or the environment that holds it, which only %s names" % owner)
    if any(e["path"] == [] and e["key"] == "run-name" for e in entries) and name != "run.yml":
        problems.append("only run.yml names its run, by the run-name the pass gave it")
    if name in PASS_FILES and EVENT_READ.search(_uncommented(text)):
        problems.append("it reads the run that woke the poller, which says nothing a fork could not write")
    if any(e["path"] == ["jobs"] and e["key"] == PASS_JOB for e in entries) and name not in PASS_FILES:
        problems.append("the job %s is reserved for %s, the one job granted a write" % (PASS_JOB, " and ".join(PASS_FILES)))
    return problems


def lens_job_problems(text: str, check: str) -> list:
    """Why a workflow holding `text` would never report the check run `check` on every head and in the merge queue.

    GitHub names a job's check run by the job's own `name:`, or by its id where it has none; a workflow's or a step's
    `name:` names none. A job with a `strategy.matrix` reports under its name and its values, one with a job-level
    `if:` can be skipped, and one that calls a reusable workflow with `uses:` reports under the caller's and the
    callee's names. A workflow that does not run on both pull_request and merge_group reports on no head, or not in
    the queue. Each would leave the Lens waiting for ever. The one `if:` allowed is `always()`, beside `needs:`, which
    cannot skip the job; a job that needs others is held by _judging.
    """
    entries, _ = read(text)
    top = {e["key"]: e for e in entries if e["path"] == []}
    events = {e["key"] for e in entries if e["path"] == ["on"]}
    if top.get("on", {}).get("value"):
        events.add(top["on"]["value"])
    problems = []
    if not {"pull_request", "merge_group"} <= events:
        problems.append("runs on %s, not on both pull_request and merge_group, so its check would not report on every "
                        "head and in the queue" % (", ".join(sorted(events)) or "nothing"))
    jobs = [e["key"] for e in entries if e["path"] == ["jobs"]]
    named = []
    for job in jobs:
        inside = {e["key"]: e for e in entries if e["path"] == ["jobs", job]}
        if inside.get("name", {}).get("value", job) == check:
            named.append((job, inside))
    if not named:
        return problems + ["runs no job named %r: only a job's own name, or its id where it has none, names its check"
                           % check]
    for job, inside in named:
        matrix = [e for e in entries if e["path"] == ["jobs", job, "strategy"] and e["key"] == "matrix"]
        for there, said in ((matrix, "has a strategy.matrix"),
                            ("if" in inside and (inside["if"]["value"] != ALWAYS or "needs" not in inside),
                             "has a job-level if: other than always() beside needs:"),
                            ("uses" in inside, "calls a reusable workflow with uses:")):
            if there:
                problems.append("has the job %s, and it %s, so its check would never report under that name alone"
                                % (job, said))
        if "needs" in inside or len(jobs) > 1:
            problems += ["has the job %s beside other jobs, and %s" % (job, why)
                         for why in _judging(text, entries, job, jobs)]
    if any("needs" in inside for _, inside in named):     # the required check's workflow, whose job judges the rest
        problems += _commits(text, entries, jobs) + _shards(entries, jobs)
        for key in ("env", "defaults"):
            if key in top:
                problems.append("has a top-level %s:, which every job inherits, where each is told what it is and "
                                "nothing else" % key)
    return problems


def lens_workflows(root: pathlib.Path) -> list:
    """Each required Lens names the workflow file it is read from exactly where GitHub Actions runs it, and that file
    reports its check on every head and in the merge queue (lens_job_problems).

    The Kernel reads a Lens whose App is GitHub Actions only from the file `config/defaults.json` names for it, and
    reads a Lens no workflow runs only from a check that names none. A Lens of GitHub Actions with no file could be
    passed by any job in the repo; another App's with one would never be read. A file gone, moved, or whose job would
    never report under the Lens's check name, would leave the Lens unreadable or waiting on every pull request.
    """
    config = root / "config" / "defaults.json"
    if not config.is_file():
        return []
    try:
        lenses = json.loads(config.read_text())["required_lenses"]["deterministic"]
    except (OSError, ValueError, KeyError, TypeError) as err:
        return ["config/defaults.json: required_lenses.deterministic cannot be read, so no Lens's workflow file can be "
                "checked: %r" % err]
    if not isinstance(lenses, list) or not all(isinstance(lens, dict) for lens in lenses):
        return ["config/defaults.json: required_lenses.deterministic is not a list of Lenses, so no Lens's workflow "
                "file can be checked"]
    problems = []
    for lens in lenses:
        rel, where = lens.get("workflow"), "config/defaults.json: the Lens %s" % lens.get("lens")
        actions = lens.get("app_id") == ACTIONS_APP and type(lens.get("app_id")) is int
        if actions and not isinstance(rel, str):
            problems.append("%s is run by GitHub Actions and names no workflow file; name the file whose job runs it"
                            % where)
        if not actions and rel is not None:
            problems.append("%s names the workflow file %s, and only GitHub Actions runs one; make it null" % (where, rel))
        if not isinstance(rel, str):
            continue
        path = root / rel
        if not path.is_file():
            problems.append("%s is read from %s, which does not exist" % (where, rel))
            continue
        if not isinstance(lens.get("check"), str):
            problems.append("%s names no check, so its workflow file cannot be read for it" % where)
            continue
        problems += ["%s is read from %s, which %s" % (where, rel, why)
                     for why in lens_job_problems(raw(path), lens["check"])]
    return problems


# The one token GitHub mints for each run: never stored, so it has no row in config/credential-ages.json.
MINTED = {"GITHUB_TOKEN"}
MODEL_KIND = "model"


def credential_problems(root: pathlib.Path, live: list) -> list:
    """Every secret a workflow names has a row in `config/credential-ages.json`, and each row's secret is named by exactly
    the workflow files its row lists: one, but the model's credential, which two name (decision 0053), and none for a
    key whose workflow is not built yet (L-37, issue 305), and the model's only by the workflows that may name it. An
    App's key is kept where `config/apps.json` says alone (decision 0009), and is `write` if its App writes anything,
    `read` if not. GitHub reads a secret's name in any case; a comment names none. What cannot be read checks nothing,
    and says so."""
    try:
        rows = json.loads((root / "config" / "credential-ages.json").read_text())["credentials"]
        apps = json.loads((root / "config" / "apps.json").read_text())["apps"]
        keys = {app["key"]["secret"].upper(): app for app in apps.values()}
        if not all(isinstance(app.get("permissions", {}), dict) for app in keys.values()):
            raise TypeError("an App's permissions are not a mapping")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as err:
        return ["config/credential-ages.json or config/apps.json cannot be read, so no workflow's secrets can be checked "
                "against them: %r" % err]
    if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("name"), str)
                                             and isinstance(r.get("workflows"), list)
                                             and all(isinstance(w, str) for w in r["workflows"]) for r in rows):
        return ["config/credential-ages.json: its credentials are not rows each naming a secret and its workflows"]
    named = {}
    for path in live:
        for line in _uncommented(raw(path)).split("\n"):
            for found in SECRET.finditer(line.partition(" #")[0]):     # a trailing comment names nothing either
                name = (found.group(2) or found.group(3) or "").upper()
                if name and name not in MINTED:
                    named.setdefault(name, set()).add(path.name)
    problems, held = [], {}
    for row in rows:
        held.setdefault(row["name"].upper(), []).append(row)
    for name in sorted(set(named) - set(held)):
        problems.append("%s names the secret %s, which config/credential-ages.json has no row for"
                        % (", ".join(sorted(named[name])), name))
    for name, found in sorted(held.items()):
        where = "config/credential-ages.json: %s" % name
        if len(found) > 1:
            problems.append("%s has %d rows; give it one" % (where, len(found)))
        row = found[0]
        if set(row["workflows"]) != named.get(name, set()):
            problems.append("%s lists the workflows %s, and is named by %s" % (where, sorted(row["workflows"]) or "none",
                                                                             sorted(named.get(name, ())) or "none"))
        if len(row["workflows"]) > 1 and row.get("kind") != MODEL_KIND:
            problems.append("%s is named by %d workflows; a secret is named by one, but the model's credential "
                            "(decision 0053)" % (where, len(row["workflows"])))
        if row.get("kind") == MODEL_KIND and not set(row["workflows"]) <= MODEL_WORKFLOWS:
            problems.append("%s is a model credential, which only %s may name" % (where, " and ".join(sorted(MODEL_WORKFLOWS))))
        app = keys.get(name)
        if app is not None:
            writes = any(isinstance(g, dict) and g.get("level") == "write" for g in app.get("permissions", {}).values())
            if row.get("stored") != "environment" or row.get("environment") is not None:
                problems.append("%s is an App's key: it is stored in an environment that config/apps.json alone names, "
                                "so its environment here is null" % where)
            if row.get("kind") != ("write" if writes else "read"):
                problems.append("%s is the key of %s, which %s, so its kind is %s"
                                % (where, app.get("name"), "writes" if writes else "writes nothing",
                                   "write" if writes else "read"))
        elif (row.get("stored") == "environment") != isinstance(row.get("environment"), str):
            problems.append("%s names its environment if and only if it is stored in one" % where)
    for name in sorted(set(keys) - set(held)):
        problems.append("config/apps.json keeps the key %s, which config/credential-ages.json has no row for" % name)
    return problems


def run(root: pathlib.Path = ROOT) -> list:
    problems = lens_workflows(root)
    live = sorted((root / ".github" / "workflows").glob("*.y*ml"))
    example = root / "examples" / "workflows" / "verify.yml"
    for path in live + sorted((root / "examples" / "workflows").glob("*.y*ml")):
        text = raw(path)
        spared, held = EXEMPT.get(path.name, ((), None)) if path in live else ((), None)
        spared = tuple(spared) + (SHAPED.get(path.name, ()) if path in live else ())
        if path in live and path.name == SCAN:
            problems += ["%s: %s" % (path.relative_to(root), p) for p in scan_problems(text)]
        if held and hashlib.sha256(PIN.sub("@PIN", text).encode()).hexdigest() != held:
            problems.append("%s is exempt from a rule, so it is held word for word, and it has changed; "
                            "if the change is meant, record its new hash in EXEMPT" % path.relative_to(root))
        for rule, message in lint(text):
            if rule not in spared:
                problems.append("%s: [%s] %s. The rule: %s" % (path.relative_to(root), rule, message, RULES[rule]))
    for path in live:
        problems += ["%s: %s" % (path.relative_to(root), p) for p in shim_problems(path.name, raw(path), root)]
    # The eval job's name is reserved (docs/standards/workflows.md): the job `eval` lives in eval.yml and nowhere else,
    # since it alone will hold the held-out home's read token (design §4.9).
    for path in live:
        entries, _ = read(raw(path))
        named = [(e["key"], {i["key"]: i for i in entries if i["path"] == ["jobs", e["key"]]})
                 for e in entries if e["path"] == ["jobs"]]
        # GitHub names a check run by the job's own name, or by its id where it has none: both are read.
        jobs = [inside.get("name", {}).get("value", job) for job, inside in named]
        if EVAL_JOB in jobs and path.name != EVAL_WORKFLOW:
            problems.append("%s: the job %s is reserved for %s, the one job that reads the held-out home"
                            % (path.relative_to(root), EVAL_JOB, EVAL_WORKFLOW))
        if path.name == EVAL_WORKFLOW and jobs != [EVAL_JOB]:
            problems.append("%s: holds the job %s and no other, or it is not the eval job's workflow"
                            % (path.relative_to(root), EVAL_JOB))
        if path.name == EVAL_WORKFLOW:
            problems += ["%s: %s" % (path.relative_to(root), p) for p in eval_problems(raw(path), root)]
        else:
            for number, line in enumerate(raw(path).split("\n"), 1):
                if MODEL_SECRET.search(line) and path.name not in MODEL_WORKFLOWS:
                    problems.append("%s: line %d names the model's credential, which only eval.yml's run step and the "
                                    "run job name" % (path.relative_to(root), number))
                if EVAL_ONLY.search(line):
                    problems.append("%s: line %d names the eval job's environment, the held-out home or its steps, "
                                    "which are eval.yml's alone" % (path.relative_to(root), number))
        if path.name == RELEASE_WORKFLOW:
            problems += ["%s: %s" % (path.relative_to(root), p) for p in release_problems(raw(path))]
        else:
            for number, line in enumerate(raw(path).split("\n"), 1):
                if RELEASE_ONLY.search(line):
                    problems.append("%s: line %d names the release job's environment, its key, its token or its step, "
                                    "which are release.yml's alone" % (path.relative_to(root), number))
    if live:
        problems += credential_problems(root, live)
    for folder in sorted((root / ".github").glob("actions*")):
        problems.append("%s: a local action is not read by this check; write a reusable workflow"
                        % folder.relative_to(root))
    if not example.exists():
        return problems + ["examples/workflows/verify.yml, the required check's workflow, is missing"]
    wanted = PIN.sub("@PIN", example.read_text())
    real = root / ".github" / "workflows" / "verify.yml"
    if live and not real.exists():
        problems.append(".github/workflows/ holds workflows and not verify.yml, the required check")
    if real.exists() and PIN.sub("@PIN", real.read_text()) != wanted:
        problems.append("%s is not %s, word for word but for the pins; change both together"
                        % (real.relative_to(root), example.relative_to(root)))
    page = root / "docs" / "standards" / "workflows.md"
    shown = re.search(r"```yaml\n(.*?)```", page.read_text(), re.S) if page.exists() else None
    if shown and PIN.sub("@PIN", shown.group(1)) != wanted:
        problems.append("docs/standards/workflows.md: its example is not %s, word for word but for the pins"
                        % example.relative_to(root))
    tripped = set()
    for path in sorted((root / "examples" / "workflows" / "invalid").glob("*.y*ml")):
        want = path.name.split(".")[0]
        got = sorted({rule for rule, _ in lint(raw(path))})
        tripped.add(want)
        if got != [want]:
            problems.append("invalid/%s: must break the rule '%s' and no other, and breaks %s"
                            % (path.name, want, got or "none"))
    for rule in sorted(set(RULES) - tripped):
        problems.append("the rule '%s' has no counter-example under examples/workflows/invalid/" % rule)
    return problems
