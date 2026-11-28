# 1378. A command beside a secret passes where no work branch can start it

Status: accepted. 2026-11-28, the Solution Architect's ruling 1; issue 838. Narrows decision 0239's Decision row "Where the secret clauses are held" and its first two Boundary rows, the grant's and the push's.

## Decision

Decision 0239 refuses a push where a job that holds a secret runs a file a Factory patch may change. A protected workflow proves only that a command's text is the base's: the command can still run files a patch changes. So a command passes only where no work branch can start its workflow before a review.

- A `run:` step in a job that holds a secret passes only where both hold: its workflow file is on the base's list, and its `on:` names only `workflow_dispatch`, `schedule`, or `push` with a list of branches that names the default branch alone.
- Every other event refuses it: `pull_request`, `pull_request_target`, `workflow_run`, `workflow_call`, and a `push` with no branch list among them.
- A key's block scalar, as `run: |`, is now read as its value. Anything else the table does not name still refuses.

`guards/workflows.py` holds it, under the code `STARTED`; `refusal_at` is told the default branch.

Limits: the runner is taken to be GitHub's own; a self-hosted one is not read. A command is read as text: one a person wrote that checks out a work branch runs its files, and so does a person's dispatch on one. A job that calls a workflow of this repo, and the actions and `env:` names the table lacks, still refuse every job here that holds a secret, but the scan's. Nothing calls the guard yet: the push's loop is not built.

## Why

The guard refused every job here that runs a command beside a secret, so once the push called it, no push to this repo could land. Passing a protected workflow whole was rejected: its commands can run files a patch changes (decision 0188). Only an event no work branch can raise keeps those files reviewed before they run beside a secret.

## Boundaries

| Boundary | Check |
|---|---|
| A command beside a secret passes where only a dispatch, the schedule or a push to the default branch starts its workflow, and that workflow is on the list | `tests/test_guards.py::Commands.test_a_command_beside_a_secret_passes_only_where_the_default_branch_alone_may_start_it`, `guards/workflows.py`, mutant: "any event may start a command beside a secret" |
| Any other event, or a push that a branch but the default may start, refuses the command | `tests/test_guards.py::Commands.test_a_command_beside_a_secret_passes_only_where_the_default_branch_alone_may_start_it`, `guards/workflows.py`, mutant: "a pull request may start a command beside a secret" |
| A key's block scalar is read as its value, a secret named in it among it | `tests/test_guards.py::Commands.test_a_keys_block_scalar_is_read_as_its_value`, `guards/workflows.py`, mutant: "a block scalar's text is not searched for a secret" |
