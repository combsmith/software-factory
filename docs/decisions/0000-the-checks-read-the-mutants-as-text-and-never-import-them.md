# 0000. The checks read the mutants as text and never import them

Status: accepted. 2026-11-28, the Factory Builder and the Solution Architect; issue 1377.

## Decision

`check_decisions` reads `tools/mutants.py` and the files of `tools/mutants_of/` through ast, and imports none of them. It works out each value as Python would, in a narrow grammar where no value can change once bound. Whatever falls outside that grammar fails the check, and so does any mutant whose description, file or tests it cannot work out.

The runner's `areas(ROOT)`, which imports the files of mutants, is read only as `PINNED` in `tools/check_decisions.py` writes it. That file holds the exact grammar. A file or folder at the top of the tree named as a module of Python's own library fails the check, since Python would import it in that module's place.

Limits:
- A change to `areas(ROOT)` fails the check until `PINNED` follows it.
- `tools/mutants.py`, the runner, is still pushable and imports `tools/mutants_of/`. A patch to either can blind the merge group's mutant leg (issue 1388).
- The checks still import modules of `kernel/`, `harness/` and `adapters/`, and check files a push can change. Issue 1377's later parts close those.

## Why

The checks imported `tools/mutants.py`, which loads every file of `tools/mutants_of/`. In a clone with a check failing, `os._exit(0)` atop one of those files made `make checks` exit 0. A first reader that guessed what a statement could change failed open on aliases and calls, so the reader now refuses what it cannot follow. Protecting the mutant files was rejected: nearly every change adds a mutant.

## Boundaries

| Boundary | Check |
|---|---|
| The checks import no file of mutants, and read the list the runner runs | `tests/test_tools.py::Decisions.test_the_mutants_read_as_text_are_those_the_runner_runs`, `tools/check_decisions.py`, mutant: "the runner is imported where the tree is this one" |
| A statement outside the grammar cannot be read | `tests/test_tools.py::Decisions.test_the_mutants_are_read_as_text_and_never_run`, `tools/check_decisions.py`, mutant: "a statement the reader does not know is passed over" |
| A call that could change a value cannot be read, on any path of a function | `tests/test_tools.py::Decisions.test_the_mutants_are_read_as_text_and_never_run`, `tools/check_decisions.py`, mutant: "a function that may change a value on a path it does not take is run" |
| A mutant of other than five parts cannot be read | `tests/test_tools.py::Decisions.test_the_mutants_are_read_as_text_and_never_run`, `tools/check_decisions.py`, mutant: "a mutant of six parts is read" |
| An `areas(ROOT)` other than the pinned one cannot be read | `tests/test_tools.py::Decisions.test_the_mutants_are_read_as_text_and_never_run`, `tools/check_decisions.py`, mutant: "areas(ROOT) is read whatever it pins" |
| A file at the top of the tree named as a module of Python's library cannot be read | `tests/test_tools.py::Decisions.test_the_mutants_are_read_as_text_and_never_run`, `tools/check_decisions.py`, mutant: "a file at the top of the tree may stand in for Python's own module" |
| A change to one file of mutants alone is read again | `tests/test_tools.py::Decisions.test_a_change_to_a_file_of_mutants_alone_is_read_again`, `tools/check_decisions.py`, mutant: "a change to a file of mutants but tools/mutants.py is not read again" |
