# 0122. A run the model could not finish is an attempt on its item, as the CLI names it

Status: accepted. The Factory Builder's ruling of 2026-11-02 on "A model steered into not answering can raise the Factory's automatic pause, through is_error true" (issue 483). It answers the separate question decision 0121's row "Its limits" left open.

## Decision

| What | Decided | Because |
|---|---|---|
| The code | `harness/engine.py` writes `failed`, `no_answer`, where the CLI says `is_error` exactly true with the subtype `error_max_structured_output_retries` or `error_max_turns`, whatever its exit | P-13 recorded both at the pin. A model reads an item's text, so these are not faults of the Factory |
| What it means | As decision 0121 has it: the outcome is `item`, an attempt, held at the attempts ceiling, counting toward no automatic pause; in the eval the case is `unreadable` and the run `engine_fault` | The code already reads both ways, each where guessing wrong costs less |
| What stays the Factory's | `is_error` true with any other subtype, or `is_error` neither true nor false whatever the subtype; a failing exit with `is_error` false; `engine_timeout`; and a CLI that cannot start. All stay `environment`. `is_error` false at exit 0 is no error, whatever the subtype, and its answer is read as any is | An outage read as `item` would burn attempts on every item (section 3.10). A subtype a later pin adds is read as the Factory's until a trial names it |
| The trial | `tools/trial_p13_ended.sh` at the pin, kept in `trials/P-13.ended.json`, on a schema nothing can meet. Told to keep trying, the run ended `error_max_structured_output_retries`; at one turn, `error_max_turns`; told only to answer, the model gave up, exit 0 and no output, which is `no_answer` by decision 0121 | L-51: a word read from a binary is not a word a CLI was seen to say |
| Its limits | A model out of turns on a real Run now costs the item an attempt, as a model that gave up already did. If a cause common to every item ends each Run this way, a model the alias `opus` comes to name that cannot meet `result/1` among them, every admitted item spends its attempts and is Held, one at a time and with no automatic pause. The Factory stops only item by item, and the eval closes on `no_answer` only when a Release is cut. That is accepted: `max_attempts` bounds each item, and a person sees each Hold. A model error the CLI reports under another subtype can still count toward the automatic pause. `engine_timeout` is still accepted by name in section 3.10. | The rule is about what the Factory can tell, and each cost is bounded or named |

## Why

Three such ends on two items inside an hour would have stopped every model Run. The trial shows a Task's words can lead the model to the retry limit, on a schema nothing can meet. It does not show that an item's text can on `result/1`, which a model can meet. The rule does not need that shown: the Factory cannot tell the two.

## Boundaries

| Boundary | Check |
|---|---|
| Each of the two, as recorded and at any exit, is `no_answer`; a changed version comes first | `tests/test_harness.py::test_a_run_the_model_could_not_finish_is_no_answer_as_the_trial_recorded` |
| Another subtype, or `is_error` neither true nor false, or a failing exit with `is_error` false, is `engine_failed`; `is_error` false at exit 0 is read as any answer | `tests/test_harness.py::test_a_cli_that_fails_or_runs_past_its_time_is_a_failed_result` |
| `no_answer` is `item` in a live Run | `tests/test_apply.py::test_a_result_not_the_runs_or_not_completed_writes_nothing` |
| The trial asks as the Engine does, in an empty directory, keeps codes alone, and refuses before asking at another version, on another's configuration, or with what it keeps in the repo | `tests/test_tools.py::test_it_asks_three_ways_and_keeps_only_codes`, `tests/test_tools.py::test_it_refuses_before_anything_is_asked` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
