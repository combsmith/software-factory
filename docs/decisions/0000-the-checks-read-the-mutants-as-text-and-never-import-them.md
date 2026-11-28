# 0000. The checks read the mutants as text and never import them

Status: accepted. 2026-11-28, the Factory Builder and the Solution Architect; issue 1377.

## Decision

`check_decisions` reads `tools/mutants.py` and every file of `tools/mutants_of/` through ast, and imports none of them. A small reader works out the names, comprehensions and plain helpers those files use. A mutant whose description, file or tests it cannot work out fails the check.

`tools/check_decisions.py` holds the exact form.

Limits:
- The reader can differ from Python where code changes a list in a way it does not see. A test holds its reading equal to the runner's list, and a test can forge its own result.
- `tools/mutants.py`, the runner, is still pushable and imports `tools/mutants_of/`. A patch to either can blind the merge group's mutant leg (issue 1388).
- The checks still import modules of `kernel/`, `harness/` and `adapters/`, and check files a push can change. Issue 1377's later parts close those.

## Why

The checks imported `tools/mutants.py` to read the mutants, and it loads every file of `tools/mutants_of/`. In a clone with a check failing, `os._exit(0)` atop one of those files made `make checks` exit 0. Protecting the mutant files was rejected: nearly every change adds a mutant.

## Boundaries

| Boundary | Check |
|---|---|
| A file of mutants that ends its process at import is read, never run | `tests/test_tools.py::Decisions.test_the_mutants_are_read_as_text_and_never_run`, `tools/check_decisions.py`, mutant: "the mutants are imported, not read as text" |
| A list that another statement names cannot be read | `tests/test_tools.py::Decisions.test_the_mutants_are_read_as_text_and_never_run`, `tools/check_decisions.py`, mutant: "a statement that names MUTANTS leaves it read" |
| A mutant of other than five parts cannot be read | `tests/test_tools.py::Decisions.test_the_mutants_are_read_as_text_and_never_run`, `tools/check_decisions.py`, mutant: "a mutant of four parts is read" |
| The mutants read as text are those the runner runs | `tests/test_tools.py::Decisions.test_the_mutants_read_as_text_are_those_the_runner_runs`, `tools/check_decisions.py`, mutant: "a function's body is read as if it ran at the top" |
