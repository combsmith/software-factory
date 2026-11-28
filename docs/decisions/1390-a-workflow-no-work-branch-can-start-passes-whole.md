# 1390. A workflow no work branch can start passes whole

Status: accepted. 2026-11-28, the Solution Architect's rulings on decision 1378's follow-up; issue 838. Narrows decision 1378's Decision row "A `run:` step in a job that holds a secret" and its Limits.

## Decision

Decision 1378 reads each step of a job that holds a secret, even where no work branch can start its workflow. Such a workflow now passes whole.

- A workflow on the base's list whose `on:` decision 1378 passes is gated. Its actions and `env:` names need no table rows.
- In a gated workflow, a job that holds a secret calls a workflow of this folder by its `./` path, or the home repo's at a Release or Channel tag, word for word. Otherwise it runs on a label of `HOSTED`. Any other call refuses.
- Every job that holds a secret and runs steps runs on a GitHub-hosted Linux label, gated or not.
- A call by `./` path reaches only a workflow on the list. A key with a capital refuses.
- Every job of a workflow `workflow_call` may start holds a secret, as an input may carry one. A command in it still refuses.

`guards/workflows.py` holds it. `refusal_at` is told the home repo's name.

Limits: whoever can move a factory/ ref, tag or branch, changes what a home call runs: the boundary is the tag rulesets and decision 0124's branch ruleset. A self-hosted runner given a hosted label is the org's setting. A job that holds no secret may run anywhere: issue 1380, "guards: a job with no secret can poison a self-hosted runner". The called workflows still refuse every push here.

## Why

Decision 1378 passed a command where no work branch can start it, yet still refused the actions and `env:` names its table lacks. A gated workflow's files are the reviewed base's, and no work branch can start it, so reading its steps buys nothing. A self-hosted runner can keep one job's files for the next, so a secret's runner is fixed.

## Boundaries

| Boundary | Check |
|---|---|
| A gated workflow passes whole, its steps unread; off the list, or started by a work branch, it is read | `tests/test_guards.py::Gated.test_a_listed_workflow_no_work_branch_can_start_passes_whole`, `guards/workflows.py`, mutant: "a gated workflow is read as the table says" |
| A gated job that holds a secret calls by path, or at the home repo's tag word for word; any other call refuses | `tests/test_guards.py::Gated.test_a_listed_workflow_no_work_branch_can_start_passes_whole`, `guards/workflows.py`, mutant: "a call at a tag of another shape passes" |
| A job that holds a secret and runs steps runs on a GitHub-hosted label | `tests/test_guards.py::Gated.test_a_listed_workflow_no_work_branch_can_start_passes_whole`, `guards/workflows.py`, mutant: "a runner is not read" |
| A secret handed to a called workflow is held in its every job; a `./` call reaches a listed workflow alone | `tests/test_guards.py::Gated.test_a_secret_handed_to_a_called_workflow_is_held`, `guards/workflows.py`, mutant: "a call by path reaches an unlisted workflow" |
| A key with a capital refuses a gated workflow | `tests/test_guards.py::Gated.test_a_key_with_a_capital_refuses_a_gated_workflow`, `guards/workflows.py`, mutant: "a capital key in a gated job passes" |
