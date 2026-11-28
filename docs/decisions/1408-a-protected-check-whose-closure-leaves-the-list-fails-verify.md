# 1408. A protected check whose closure leaves the list fails verify

Status: accepted. 2026-11-28, the Factory Builder; issue 1377; extends record 1402.

## Decision

Before phase 1, `tools/verify.py` reads the import closure over `tools/` of each check whose own file is on the protected list. If a file in it is off the list, or an import cannot be followed, verify fails, naming the file, and starts no check.

Its line, `closure`, is phase 1's first answer, so CI's phase 1 step shows it. It is verify's own code, not a check, so no list and no push can move it to phase 2.

Imports are followed as Python runs them: the package's `tools/__init__.py` first, and a package before a file of its name beside it. An import of `*`, or of a builtin that runs text, cannot be followed, so it fails. `unclosed`, `_leaves` and `_found` in `tools/verify.py` hold the exact form.

Limits:
- The closure is counted over `tools/` alone. An import of `kernel/`, `harness/` or `adapters/` is not followed here; that check runs in phase 2, as record 1402 says.
- It follows imports only, as record 1402's closure does.
- It reads only source files. A compiled module or package beside one is held because the list names each module at any suffix and with its package.

## Why

Record 1402 moved a protected check whose closure left the list to phase 2 in silence. One import of an unprotected file then took the check out of phase 1 with no failure. Claude's security read of part 3 found a second route: a module at the top of the repo named as the package `tools/`, which Python never imports, was read as imported. Carbon's read of part 2 found the start was not the module Python imports. Placing the check in `check_repo` was rejected, since a check can be moved to phase 2 and verify cannot.

## Boundaries

| Boundary | Check |
|---|---|
| A protected check whose closure over tools/ leaves the list fails verify, naming the file, before any check runs | `tests/test_tools.py::Verify.test_a_protected_check_whose_closure_leaves_the_list_fails_verify_naming_the_file`, `tools/verify.py`, mutant: "a protected check's closure is not checked before the first phase" |
| An import outside tools/ is not followed by the closure check | `tests/test_tools.py::Verify.test_a_protected_check_whose_closure_leaves_the_list_fails_verify_naming_the_file`, `tools/verify.py`, mutant: "the closure check follows imports outside tools/" |
| A check off the protected list is not held to its closure | `tests/test_tools.py::Verify.test_a_protected_check_whose_closure_leaves_the_list_fails_verify_naming_the_file`, `tools/verify.py`, mutant: "a check off the protected list is held to its closure" |
| A file beside a package of its name is never read as imported | `tests/test_tools.py::Verify.test_a_file_python_never_imports_moves_no_check_out_of_the_first_phase`, `tools/verify.py`, mutant: "a file beside a package is read in its place" |
