# 0121. A CLI that exits 0 with no answer closes the eval, and stays an attempt on its item

Status: accepted. The Factory Builder's ruling of 2026-11-02, on issue 461, "The Engine: a CLI that exits 0 with no answer writes result_invalid, which the eval reads as the reviewer's", to land before the first real cut.

## Decision

| What | Decided | Because |
|---|---|---|
| The code | Where the CLI exits 0 and its answer holds no `structured_output` object, `harness/engine.py` writes `failed`, `no_answer`, a code of its own. That covers no output, output that is no JSON, a list with no `result`, and the field absent or of another type. `result_invalid` stays for a `structured_output` object that does not validate | A reviewer that gave no answer has not answered badly. Read as `result_invalid`, an Engine with nothing to say looked like a reviewer that failed |
| In the eval | `no_answer` is in `ENGINE_FAULTS`: the case is `unreadable` by it, and the run `engine_fault`, however many others passed | With the bar of decision 0120, it would otherwise have counted against the bar, and a Release could pass over a broken Engine. Its own code also tells it from a CLI that failed loudly, and the canary's line names it |
| In a live Run | `no_answer` is in `THE_ROLES` in `harness/apply.py`: the outcome stays `item`, as `result_invalid` was. It stays an attempt, held at the attempts ceiling, and counts toward no automatic pause | It cannot be told from a model that gave none, and a model reads an item's text. As `environment` it would have lifted the attempts ceiling, and text on two items could have paused every Run for an hour |
| Its limits | Read from the code alone: no real CLI at the pin has been seen to exit 0 with no answer, and P-13's answer always held the field. A CLI's own `is_error` true is `engine_failed` as before, and so `environment`, whatever caused it: a separate question, as a model out of turns reads that way too | The rule is about what the Factory can tell |

## Why

The eval has to tell a fault of the reviewer from a fault of what ran it, and with a bar that tolerates failures, misreading one as the other would pass a Release on a broken Engine. A live Run has the opposite risk, so the one code is read two ways, each where the fault of guessing wrong is the smaller.

## Boundaries

| Boundary | Check |
|---|---|
| A CLI with no answer is `no_answer`, and an answer that does not validate is `result_invalid` | `tests/test_harness.py::test_an_answer_that_does_not_validate_is_no_result` |
| Through the eval's path it is the case's code, and the run is `engine_fault` however many others passed | `tests/test_evals.py::test_a_cli_with_no_answer_is_the_engines_and_closes_the_gate` |
| In a live Run it stays an attempt on its item | `tests/test_apply.py::test_a_result_not_the_runs_or_not_completed_writes_nothing` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
