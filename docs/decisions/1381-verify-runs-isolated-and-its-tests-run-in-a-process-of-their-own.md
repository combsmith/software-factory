# 1381. Verify runs isolated and its tests run in a process of their own

Status: accepted. 2026-11-28, the Factory Builder and the Solution Architect; issue 1050. Narrows decision 0240's limit rows "a module of the standard library" and "the tests run in the checks' process".

## Decision

The Makefile runs `tools/verify.py` in Python's isolated mode, without site. verify puts the repo's top after the standard library, so a top-level file named as a standard module is not imported in its place.

`make verify` runs the checks, then the tests in a child process, and imports no test module itself. Either failing fails it. `make tests` runs the tests alone.

`tools/verify.py` and the `Makefile` hold the exact form.

Limits:
- The checks still import modules a Role can change: `tools/mutants_of/`, and the kernel and harness modules `check_examples` imports. Tested: with a check failing, a `tools/mutants_of/` file that runs `os._exit(0)` at import makes `make checks` exit 0. Issue 1377 closes this before the push dispatch lands.
- A test can forge its own result, or end the tests' process with exit 0, as a Role can write a passing test. Review and the mutant run read the tests.
- The isolation holds on CI's Python, 3.12. At a desk on 3.9, `copy` tries `org.python.core`, so a top-level package named org runs in the checks' process. A module the standard library tries and falls back from is the same gap.
- `python3 -m tools.verify` run by hand is not isolated, nor are the mutant shards, which run test code by design.

## Why

Decision 0240 named two ways a push could pass a failed check without touching a protected file. A test module could end the shared process with exit 0 at import. A top-level file named as a standard module was imported in its place. A scratch copy showed both. Protecting every test or listing every standard module was rejected.

## Boundaries

| Boundary | Check |
|---|---|
| A test module that ends its process at import cannot pass a failed check | `tests/test_tools.py::Verify.test_a_test_module_that_ends_its_process_cannot_pass_a_failed_check`, `tools/verify.py`, mutant: "the tests run in the checks' process" |
| verify fails when the checks fail, whatever the tests' process ended | `tests/test_tools.py::Verify.test_a_test_module_that_ends_its_process_cannot_pass_a_failed_check`, `tools/verify.py`, mutant: "a failed check passes verify when the tests pass" |
| A file at the top named as a standard module is not imported by the checks | `tests/test_tools.py::Verify.test_a_file_at_the_top_named_as_a_standard_module_is_not_imported_by_the_checks`, `Makefile`, mutant: "make verify puts the repo's top ahead of the standard library" |
| verify puts the repo's top after the standard library | `tests/test_tools.py::Verify.test_a_file_at_the_top_named_as_a_standard_module_is_not_imported_by_the_checks`, `tools/verify.py`, mutant: "the repo's top comes ahead of the standard library" |
| The tests' process runs no check | `tests/test_tools.py::Verify.test_make_fast_is_verify_without_the_seeded_simulation`, `tools/verify.py`, mutant: "the tests' process runs the checks" |
| make tests runs no check | `tests/test_tools.py::Verify.test_make_fast_is_verify_without_the_seeded_simulation`, `Makefile`, mutant: "make tests runs the checks too" |
| A failed test fails make tests | `tests/test_tools.py::Verify.test_make_fast_is_verify_without_the_seeded_simulation`, `tools/verify.py`, mutant: "a failed test passes make tests" |
