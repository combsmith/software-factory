# NNNN. A boundary's check names a test, never a file, and a new or changed row names the mutant its test kills

Status: accepted. The Factory Builder's story "A boundary's check names a test, never a file, and a new boundary names the mutant its test kills" (issue 590).

## Decision

| What | Decided | Because |
|---|---|---|
| A test is named as a test | Wherever a rule names its check (a decision's Boundaries, an `AGENTS.md` rule, a lesson's Check, a standard's `Held by:`), `tools/check_context.py`'s `_held` refuses a name under `tests/` that is a file and not `path::name`. The test must exist, as before. The five that named a file are each given the test that holds them: two decision rows (0008's fifth, 0049's seventeenth), the root `AGENTS.md`'s simulator rule, `tools/AGENTS.md`'s hook rule and lesson L-25 | A file of tests passes for any rule, so a row that names one looks held when nothing in particular holds it |
| A new or changed row names its mutant | `tools/check_decisions.py` compares each record's Boundaries with the merge base, as it already does. A row new in this change, or one whose Check changed, names one or more mutants as `mutant: "<description>"`. Each must be in `tools/mutants.py`, change a file the record names in backticks that is not under `tests/`, and list among its killers a test the row names. A killer is a test by its whole id, or by its module and its own name where the row gives no class. A module or a class that kills it is not a test | `tools/mutants.py` already records, for each mutant, the file it changes and the tests that kill it, so whether a row's test fails when its rule breaks is read, not taken on trust |
| What is not a changed row | A row main holds, as it stands. One whose Check differs only in that a test file it named bare is now named by a test of that file, with the same mutants: so the five rows above stay rows main holds. Any other change to the Check is a changed row | About 1,500 rows name no mutant, and they stay as they are. `verify` prints how many still name none |
| What is exempt | A row that waits on a planned part (`waiting on …`), or whose test is not held yet: neither has a test that can kill a mutant | As `_held` already exempts them |
| What it reads | The mutants are read once in a run, by importing the tree's `tools/mutants.py`, and only when a new or changed row needs them. One that cannot be read holds no row: the row is refused | Under a fifth of a second. `check_context` reads no mutant, so the hook that runs it after each edit is no slower |
| What it does not hold | Whether the named mutant breaks the rule as the row states it, and whether each rule the Decision states has a row | Both stay with the review Role, PR-5 |

## Why

A record looked held whenever its row named something under `tests/`. A whole test file passed that rule, and so did a real test that held some other rule. The mutants already say which test notices which break, so a new row can be held to that mechanically: it names a break and a test that kills it, and the check reads both in `tools/mutants.py`. Rows already on main are left alone, so this asks nothing of the 1,500 rows written before the rule.

## Boundaries

| Boundary | Check |
|---|---|
| A check under `tests/` is named as `path::name`; a file of tests, or one with a line number, is refused; a test that is not there names no check | `tests/test_tools.py::test_a_check_names_a_test_never_a_file_of_tests`, `tools/check_context.py`, mutant: "a file of tests holds a rule" |
| A new or changed row names a mutant `tools/mutants.py` holds, and a test | `tests/test_tools.py::test_a_new_or_changed_row_names_the_mutant_its_test_kills`, `tools/check_decisions.py`, mutant: "a new or changed row names no mutant", mutant: "a row may name a mutant mutants.py does not hold", mutant: "a row may name no test for its mutant" |
| Its mutant is killed by a test the row names, by the test's id; a module, a class, or another class's test is not it | `tests/test_tools.py::test_a_new_or_changed_row_names_the_mutant_its_test_kills`, mutant: "a mutant any test kills is the row's", mutant: "a module or a class that kills a mutant is the row's test", mutant: "a test of another class is the row's" |
| Its mutant changes a file the record names, and not a test | `tests/test_tools.py::test_a_new_or_changed_row_names_the_mutant_its_test_kills`, mutant: "a mutant may change a file its record does not name", mutant: "a mutant of a test holds a row" |
| A row that waits on a planned part, or is not held yet, names no mutant; a new record's rows are each new; mutants that cannot be read hold no row | `tests/test_tools.py::test_a_new_or_changed_row_names_the_mutant_its_test_kills`, mutant: "a waiting row names its mutant", mutant: "a row whose test is pending names its mutant", mutant: "a new record's rows are not new", mutant: "mutants that cannot be read hold a row" |
| A row main holds names no mutant until its Check changes; a bare test file named by its test is not a change, and any other change, or a changed mutant, is | `tests/test_tools.py::test_a_row_main_holds_names_no_mutant_until_its_check_changes`, mutant: "every row main holds names its mutant", mutant: "a bare test file named by its test is a changed row", mutant: "a row's Check that changes is the one it was", mutant: "a row whose mutant changed is the row it was" |
| `verify` prints how many rows name no mutant, of how many | `tests/test_tools.py::test_a_row_main_holds_names_no_mutant_until_its_check_changes`, `tools/verify.py`, mutant: "verify counts the rows that name a mutant" |
