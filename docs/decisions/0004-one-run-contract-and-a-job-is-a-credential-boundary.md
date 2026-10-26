# 0004. One run contract; a job is a credential boundary

Status: accepted. Source: decision 4 of `docs/architecture/adr/0013-factory-mvp-reference-architecture.md`,
as it stood on 2026-10-11. That file records how this was reached; this one is the rule.

## Decision

Every Role has one contract: a schema-versioned Task in, a schema-versioned Result out, and every
side effect a requested Effect. Three jobs carry it. `run` gives a model the Task. `verify` runs
the checks where the author controls nothing. `apply` reads the Work item again and only then makes
the changes. The model never holds a credential that can write.

## Why

A model that reads untrusted text can be talked into anything it is able to do. So what it is able
to do is to ask, in a form a schema can refuse.

## Boundaries

| Boundary | Check |
|---|---|
| Every message that crosses a boundary has a schema and an example, and counter-examples are rejected | `tools/check_examples.py` |
| A schema promises nothing the validator does not enforce | `tests/test_tools.py::test_rejects_a_schema_it_cannot_enforce` |
| No workflow passes data into a `run:` block by expression | `tools/check_workflows.py` |
| No job holds both an LLM credential and a credential that can write to GitHub | `tests/test_tools.py::test_the_runs_jobs_keep_each_key_apart_and_always_leave_the_outcome`, `tests/test_tools.py::test_the_approving_act_holds_the_approvers_token_alone` |
| No job that holds a write credential executes code from the Work item's branch | `tests/test_tools.py::test_the_runs_jobs_keep_each_key_apart_and_always_leave_the_outcome`, `tests/test_tools.py::test_the_approving_act_holds_the_approvers_token_alone` |
| A Result that fails validation applies no Effect, and its schema has no field for a commit hash | `tests/test_harness.py::test_an_answer_that_does_not_validate_is_no_result`; that it applies no Effect, `tests/test_apply.py::test_a_result_not_the_runs_or_not_completed_writes_nothing` |
| A Result's schema has no field for a commit, a Role, an actor or a content id | `examples/invalid/result.carries-a-commit-hash.json`, `examples/invalid/disposition.names-who-decided.json` |
| `apply` re-reads the Work item before any Effect, and writes nothing if it is held, paused, closed or changed | `tests/test_apply.py::test_a_change_under_the_run_writes_nothing_and_is_superseded` |
| `apply` refuses a change under `.github/`, to code owners, or to a Consumer's setup and test commands, unless a manifest permits it and a person approved | waiting on `harness/push.py`, the fix Intent's push |
| `run` and `verify` declare no permissions and use no cache | `tests/test_tools.py::test_the_runs_jobs_keep_each_key_apart_and_always_leave_the_outcome` |
| A Run that reads text from an outsider or a third-party reviewer has no shell and no network tool | `tests/test_harness.py::test_the_cli_is_given_no_tool` |
