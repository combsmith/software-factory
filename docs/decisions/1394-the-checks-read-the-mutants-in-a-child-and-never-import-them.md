# 1394. The checks read the mutants in a child and never import them

Status: accepted. 2026-11-28, the Solution Architect and the Factory Builder; issue 1377.

## Decision

`check_decisions` gets the list of mutants from a child process. The child imports `tools/mutants.py` and prints the list as JSON. The checks' own process imports no file of mutants. `_listed` in `tools/check_decisions.py` holds the exact form.

What the child prints is untrusted. A child that exits other than 0 fails the check. So does one that prints no list, a list of anything but mutants, or an empty list. The list is read again when the runner or any file of `tools/mutants_of/` changes.

Limits:
- A patched file of mutants can misstate the list the check reads. Review and the merge group's mutant leg read that list.
- `tools/mutants.py`, the runner, is still pushable. On import it runs `tools/__init__.py`, `tools/walk.py`, `tools/verify.py` with the checks it imports, and every file of `tools/mutants_of/`. A patch to the runner or a file of mutants can blind the mutant leg (issue 1388).
- The checks still import modules of `kernel/`, `harness/` and `adapters/`, and check files a push can change. Issue 1377's later parts close those.

## Why

The checks imported `tools/mutants.py`, which loads every file of `tools/mutants_of/`. In a clone with a check failing, `os._exit(0)` atop one of those files made `make checks` exit 0. A reader that worked the files out through ast grew into an interpreter that kept failing open, so it was dropped. The end state waits on issue 1388: files of mutants written as literals, read with `ast.literal_eval`.

## Boundaries

| Boundary | Check |
|---|---|
| The checks import no file of mutants, and read the list the runner runs | `tests/test_tools.py::Decisions.test_the_checks_read_the_mutants_in_a_child_and_never_import_them`, `tools/check_decisions.py`, mutant: "the runner is imported in the checks' process" |
| A child that fails, or prints no list of mutants, holds no row | `tests/test_tools.py::Decisions.test_a_new_or_changed_row_names_the_mutant_its_test_kills`, `tools/check_decisions.py`, mutant: "a child's exit is not read" |
| A change to one file of mutants alone is read again | `tests/test_tools.py::Decisions.test_a_change_to_a_file_of_mutants_alone_is_read_again`, `tools/check_decisions.py`, mutant: "a change to a file of mutants but tools/mutants.py is not read again" |
