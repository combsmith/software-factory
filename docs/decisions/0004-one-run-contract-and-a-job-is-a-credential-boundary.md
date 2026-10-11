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
| No job holds both an LLM credential and a credential that can write to GitHub | waiting on `harness/` |
| No job that holds a write credential executes code from the Work item's branch | waiting on `harness/` |
| A Result that fails validation applies no Effect, and its schema has no field for a commit hash | waiting on `harness/` |
| `apply` re-reads the Work item before any Effect, and writes nothing if it is held, paused, closed or changed | waiting on `harness/` |
| `apply` refuses a change under `.github/`, to code owners, or to a Consumer's setup and test commands, unless a manifest permits it and a person approved | waiting on `harness/` |
| `run` and `verify` declare no permissions and use no cache | waiting on `harness/` |
| A Run that reads text from an outsider or a third-party reviewer has no shell and no network tool | waiting on `roles/` |
