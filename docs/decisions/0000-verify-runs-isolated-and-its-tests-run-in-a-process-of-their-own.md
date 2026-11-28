# 0000. Verify runs isolated and its tests run in a process of their own

Status: accepted. 2026-11-28, the Factory Builder; issue 1050. Narrows decision 0240's two limit rows, "a module of the standard library" and "the tests run in the checks' process": both are closed.

## Decision

The Makefile runs `tools/verify.py` in Python's isolated mode, without site. verify puts the repo's top on the path after the standard library, so a file at the top named as one of its modules is never imported in its place.

verify runs the checks itself and the tests in a process of their own, and imports no test module. It fails when either fails. A test module that ends its process at import then ends only the tests' verdict, never the checks'.

`tools/verify.py` and the `Makefile` hold the exact form. Both are protected paths (decision 0240).

Limits: a test module can still end the tests' process early and hide a failing test, which the mutant run and review still read. A module the checks import from the repo runs in their process; a Role's change to one waits for every model Lens (decision 1351). `python3 -m tools.verify` run by hand is not isolated: only the Makefile's recipes are.

## Why

Decision 0240 named two ways a Role's push could pass a failed check without touching a protected file. A test module could end the shared process at import with exit 0. A top-level file named as a standard module, such as the parser the checks use, was imported in its place. A scratch copy showed both. Protecting every test or listing every standard module was rejected: one isolated process closes both.

## Boundaries

| Boundary | Check |
|---|---|
| A test module that ends its process at import cannot pass a failed check | `tests/test_tools.py::Verify.test_a_test_module_that_ends_its_process_cannot_pass_a_failed_check`, `tools/verify.py`, mutant: "the tests run in the checks' process" |
| verify fails when the checks fail, whatever the tests' process ended | `tests/test_tools.py::Verify.test_a_test_module_that_ends_its_process_cannot_pass_a_failed_check`, `tools/verify.py`, mutant: "a failed check passes verify when the tests pass" |
| A file at the top named as a standard module is not imported by the checks | `tests/test_tools.py::Verify.test_a_file_at_the_top_named_as_a_standard_module_is_not_imported_by_the_checks`, `Makefile`, mutant: "make verify puts the repo's top ahead of the standard library" |
| verify puts the repo's top after the standard library | `tests/test_tools.py::Verify.test_a_file_at_the_top_named_as_a_standard_module_is_not_imported_by_the_checks`, `tools/verify.py`, mutant: "the repo's top comes ahead of the standard library" |
| The tests' process runs no check | `tests/test_tools.py::Verify.test_make_fast_is_verify_without_the_seeded_simulation`, `tools/verify.py`, mutant: "the tests' process runs the checks" |
