# 0136. The CLI holds a Run to its tier's cost ceiling, and a Run it stops is the item's

Status: accepted. Replaces `docs/decisions/0122-a-run-the-model-could-not-finish-is-an-attempt-on-its-item.md`. The Factory Builder's ruling of 2026-11-03 on "The tier's cost ceiling is given to the CLI by nothing" (issue 517), found while tracing the first cut's unanswered eval cases. It overturns one line of that record, and nothing else in it.

## Decision

| What | Decided | Because |
|---|---|---|
| The ceiling | `harness/engine.py` gives the CLI the Task's `limits.cost_ceiling_usd` as `--max-budget-usd`, beside its turns as `--max-turns` and its seconds as the call's timeout | Section 3.5 says the ceiling limits the one Run, and until now nothing gave it to anything. The pinned CLI, 2.1.306, lists the flag in its help. It refuses `0` or a word for it when it reads its arguments. In a dry call it took `1.0` to the call, logged in to nothing and with no model reachable, at no cost |
| What it counts | The CLI's own estimate of spend, at list price | Under the subscription credential P-13 at 2.1.306 reported `total_cost_usd` with `costBasis` `list` (`trials/P-13.v2-1-306.json`). It is not a bill, and the CLI stops at its next check, so spend can pass the ceiling a little |
| A Run the ceiling stopped | `error_max_budget_usd` with `is_error` exactly true joins `MODEL_ENDED`, at any exit: `failed`, `no_answer`, the item's, an attempt counting toward no automatic pause, as decision 0122 has it for the turn limit | The ceiling is the tier's own bound. An item that needs more than its tier allows is that item's trouble: it costs an attempt and reaches a person at `max_attempts`. Read as `engine_failed`, one costly item would raise the Factory's automatic pause |
| What 0122 said | Decision 0122's row "What stays the Factory's" held a subtype a later pin adds as the Factory's until a trial names it, and its test held `error_max_budget_usd` so. That line is overturned for this one subtype, and its test now holds another unknown word. Every other row of 0122 stands as it was written: the two subtypes P-13 recorded, what `no_answer` means, what else stays the Factory's, its trial and its limits | This ruling |
| The eval | Record 0131's `SUBTYPES` names it, so a case's cause says `error_max_budget_usd`, not `other`. The case's reason is `no_answer`, which the eval reads as `engine_fault` (decision 0121), as it does a case out of turns | `no_answer` stays an Engine fault in the eval. This ruling does not move that |

## Why

The ceiling was promised by the config and section 3.5 and enforced by nothing, so a Run could spend past it and the ceiling could end nothing. The CLI can hold it, so the Harness need not count spend itself.

What is owed: the subtype is read from the pinned binary's own strings, where the CLI prints "Exceeded USD budget" for it. No trial has recorded the CLI saying it, at the pin or under the subscription credential, so L-51's rule is not yet met. A trial that reaches the ceiling costs money; it is owed, not run. It should record the subtype, the exit, `is_error`, and whether the reported cost is the one the ceiling held. Until then a later pin could name it otherwise, and a Run it stopped would read as `engine_failed` again.

## Boundaries

| Boundary | Check |
|---|---|
| The CLI is given the Task's ceiling once, per tier and per Task, as it reads a number | `tests/test_harness.py::test_the_cli_is_given_no_tool`, `tests/test_harness.py::test_the_cli_holds_the_run_to_its_tiers_cost_ceiling` |
| A Run the ceiling stopped is `no_answer` at any exit, and `engine_failed` without `is_error` exactly true | `tests/test_harness.py::test_the_cli_holds_the_run_to_its_tiers_cost_ceiling`, `tests/test_harness.py::test_a_run_the_model_could_not_finish_is_no_answer_as_the_trial_recorded` |
| Another unknown subtype is still the Factory's | `tests/test_harness.py::test_a_cli_that_fails_or_runs_past_its_time_is_a_failed_result` |
| A ceiling under a cent, which the CLI would refuse, is no limit a tier or a Task can hold | `tools/check_examples.py`, `examples/invalid/harness.a-ceiling-of-nothing.json`, `examples/invalid/task.a-ceiling-of-nothing.json` |
| An eval case the ceiling stopped names the subtype | `tests/test_evals.py::test_a_case_the_engine_stopped_says_what_the_cli_said_of_it` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
