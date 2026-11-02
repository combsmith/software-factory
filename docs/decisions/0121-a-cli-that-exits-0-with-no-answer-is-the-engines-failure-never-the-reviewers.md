# 0121. A CLI that exits 0 with no answer is the Engine's failure, never the reviewer's

Status: accepted. The Factory Builder's ruling of 2026-11-02, on issue 461, "The Engine: a CLI that exits 0 with no answer writes result_invalid, which the eval reads as the reviewer's", to land before the first real cut.

## Decision

| What | Decided | Because |
|---|---|---|
| The change | Where the CLI exits 0 and its answer holds no `structured_output` object, `harness/engine.py` writes `failed`, `engine_failed`. That covers no output, output that is no JSON, a list with no `result`, and an answer with the field absent or of another type. `result_invalid` stays for a `structured_output` object that does not validate, which is the reviewer's own | A reviewer that gave no answer has not answered badly. Read as `result_invalid`, an Engine with nothing to say looked like a reviewer that failed, and the bar of decision 0120 would have absorbed it |
| No new code | `engine_failed` already says the CLI failed, is in `ENGINE_FAULTS`, closes the eval's gate as `engine_fault`, and is the Factory's in `harness/apply.py`, whose `THE_ROLES` keeps `result_invalid` as the Role's | One meaning, already held everywhere it is read |
| A live Run | A Run with no answer now ends with the outcome `environment`, as the CLI's other failures do, and no longer `item` | It says nothing of the item |
| Its limits | Read from the code alone: no real CLI at the pin has been seen to exit 0 with no answer, and P-13's answer always held the field. A model that spends its turns with no structured output, if the CLI reports that with `is_error` false, would now read as the Engine's | The rule is about what the Factory can tell, and it cannot tell that apart from a CLI that said nothing |

## Why

The eval has to tell a fault of the reviewer from a fault of what ran it, and with a bar that tolerates failures, misreading one as the other would pass a Release on a broken Engine.

## Boundaries

| Boundary | Check |
|---|---|
| A CLI with no answer is `engine_failed`, and an answer that does not validate is `result_invalid` | `tests/test_harness.py::test_an_answer_that_does_not_validate_is_no_result` |
| Through the eval's path it is the case's code, and the run is `engine_fault` however many others passed | `tests/test_evals.py::test_a_cli_with_no_answer_is_the_engines_and_closes_the_gate` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
