# NNNN. A result's check is read as any check, so one a job created is foreign to its reporter

Status: accepted. The Factory Builder's ruling of 2026-11-06 on "Acceptance: a result is read only where its check's details are its own job's (raised by record 0104)" (issue 445). It takes decision 0104's rule to an acceptance result, the way that record's own row for this case names, and adds no fact and no evidence code.

## Decision

| What | Decided | Because |
|---|---|---|
| The read | `adapters/acceptance.py`'s `result_check(node)` gives the check that reported a result, as `facts/1` holds it, its name, App and workflow file, read by `adapters/checks.py`'s `check`. So a check of GitHub Actions' whose details are not its own job's has no file, `workflow` null, whatever file its suite names. The results' port, not built yet, reads each result's check by it | A result's check is a check, and decision 0104 already says how a check made by a job under another's name, App and file is told: by its details, at the port |
| The rule | Such a result is foreign to the Lens that reports its criterion's kind, as `kernel/derive.py`'s `foreign_results` already reads it: `<criterion>:from_workflow:unreadable` where a workflow runs that Lens, and `<criterion>:from_app:<id>` of GitHub Actions' where none does. That holds because no Lens of GitHub Actions' runs with no workflow, which `tools/check_workflows.py` refuses in the configuration. The Kernel does not change | One rule for a check and for a result, read in one place |
| What is not taken | The issue asked for a field in `facts/1`'s result saying whether its check's details are its job's, and a code `<criterion>:not_its_job`. Neither is added: decision 0104 left that fact out for a check, because a fact that said so would move the held-out cases, and the same holds for a result. As there, a person who looks sees why from the check's own URL | No schema and no eval case moves |
| What clears it | A result is matched by content, whatever head its check is on, so a created check's result keeps the item `acceptance_unreadable` until the content changes; a push of the same content does not clear it. That is on the safe side, and a person looks | Named, as decision 0104 names what clears a check's |
| The issue's mutant | The issue named a mutant "an acceptance result is held to a job" to replace; there is none in `tools/mutants.py`, so the two this record adds are new | |
| Until the port is built | `adapters/acceptance.py` gives no contract where an issue asks for one, so no result is read yet. The rule waits in `result_check` for the port that reads results, which takes it | Named so that it is not read as held in a live pass yet |

## Why

Decision 0104 held a required Lens's check to its own job, at the checks port, and named an acceptance result as the case its port would meet the same way. This record is that way: the result's check goes through the same read, so the Kernel's existing rule for a result with no readable file covers a created one, with nothing new for the facts to carry.

## Boundaries

| Boundary | Check |
|---|---|
| A result's check is read as the checks port reads any check: in P-35, a created check under the reporter's name, App and file is read with no file and its result is foreign, `AC-1:from_workflow:unreadable`; a real job's keeps its file and its result is the reporter's; the schema's description names it | `tests/test_adapters.py::test_a_results_check_is_read_as_any_check_and_a_created_one_is_foreign_to_its_reporter` |
| A result whose check has no file is foreign to its reporter | `tests/test_decide.py::test_a_result_counts_only_from_the_reporter_its_kind_names` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
