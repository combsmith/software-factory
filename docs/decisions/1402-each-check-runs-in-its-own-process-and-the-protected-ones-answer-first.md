# 1402. Each check runs in its own process, and the protected ones answer first

Status: accepted. 2026-11-28, the Solution Architect via the Factory Builder; issue 1377; extends record 1381.

## Decision

`tools/verify.py` imports no check. It runs each check in its own isolated process, with bytecode in a fresh folder outside the tree. A check answers on its last line, naming itself; any other ending fails it.

No Role code runs until every check that runs none has answered and passed. Phase 1 is set by the list, not by name: a check whose whole import closure is on the protected list of `config/hooks.json`. An import by a worked-out name, or a relative one, is not closed; a standard module's name is never looked up in the tree. If a phase 1 check fails, phase 1 is empty, or the list is unreadable, `verify` exits 1 and starts nothing more. Phase 2 is every other check, then the tests. `tools/verify.py` holds the exact form.

Limits:
- Once Role code runs, it can forge any phase 2 result. Review stands against it.
- The closure follows imports only. A protected check that runs a tree file as a process is held by review.
- A patch blinds each check that imports the patched file. `check_examples` is imported by `check_authority`, `check_trials` and `check_gate_sets`; `check_trials` by `check_release`; `check_decisions` by `check_gate_sets`.
- Untested, on Linux: Role code writing to a sibling's pipe through /proc, closed for phase 1 by the order. Root on the runner is not closed; only a separate job that runs no Role code closes it (issue 1387).
- Phase 1 is `repo`, `workflows` and `writes` today; later parts of issue 1377 protect the rest.

## Why

All checks ran in one process, so `os._exit(0)` atop one unprotected check file ended `make checks` with exit 0. One process per check bounds that to the patched check. Role code beside a protected check could still reach its result, so protected checks answer first. Naming phase 1 by hand was rejected.

## Boundaries

| Boundary | Check |
|---|---|
| A check whose process gives no answer fails verify | `tests/test_tools.py::Verify.test_a_check_whose_process_gives_no_answer_fails_verify`, `tools/verify.py`, mutant: "a check that gave no answer passes" |
| A check's process that fails is never read as answering | `tests/test_tools.py::Verify.test_a_check_whose_process_gives_no_answer_fails_verify`, `tools/verify.py`, mutant: "a check's failed exit is read as its answer" |
| An answer that names another check is not taken | `tests/test_tools.py::Verify.test_a_check_whose_process_gives_no_answer_fails_verify`, `tools/verify.py`, mutant: "an answer for another check is taken" |
| A check that ends its process early fails alone, and the others still answer | `tests/test_tools.py::Verify.test_a_check_that_ends_its_process_fails_alone`, `tools/verify.py`, mutant: "the checks run in verify's own process" |
| No check that runs Role code starts once a phase 1 check fails | `tests/test_tools.py::Verify.test_the_checks_that_run_no_role_code_answer_first`, `tools/verify.py`, mutant: "a check that runs Role code starts though one that runs none failed" |
| A check whose closure leaves the protected list runs in phase 2 | `tests/test_tools.py::Verify.test_the_checks_that_run_no_role_code_answer_first`, `tools/verify.py`, mutant: "a check whose closure leaves the protected list runs first" |
| An import by a worked-out name is not closed | `tests/test_tools.py::Verify.test_the_checks_that_run_no_role_code_answer_first`, `tools/verify.py`, mutant: "an import by a worked-out name is read as closed" |
| A list that cannot be read fails, and sorts no check later | `tests/test_tools.py::Verify.test_the_checks_that_run_no_role_code_answer_first`, `tools/verify.py`, mutant: "a list that cannot be read sorts every check later" |
| A file at the top named as a standard module moves no check out of phase 1 | `tests/test_tools.py::Verify.test_the_checks_that_run_no_role_code_answer_first`, `tools/verify.py`, mutant: "a standard module's name is looked up in the tree" |
| After a phase 1 failure, `make verify` runs no test and CI's step fails | `tests/test_tools.py::Verify.test_a_check_that_runs_no_role_code_and_fails_stops_verify_and_its_own_step`, `tools/verify.py`, mutant: "make verify runs the tests after a check that runs no Role code failed" |
| A check's process is isolated | `tests/test_tools.py::Verify.test_a_file_at_the_top_named_as_a_standard_module_is_not_imported_by_the_checks`, `tools/verify.py`, mutant: "a check's process is not isolated" |
| A check's bytecode is kept outside the tree | `tests/test_tools.py::Verify.test_each_checks_process_keeps_its_bytecode_outside_the_tree_and_is_stopped_when_it_hangs`, `tools/verify.py`, mutant: "a check's bytecode is read from the tree" |
| A check that hangs is stopped | `tests/test_tools.py::Verify.test_each_checks_process_keeps_its_bytecode_outside_the_tree_and_is_stopped_when_it_hangs`, `tools/verify.py`, mutant: "a check that hangs holds verify" |
