# 0131. An unanswered eval case says why, by its class, its place and its code

Status: accepted. The Factory Builder's story of 2026-11-03, after the first cut's eval run 41640659356 on `bb365fa4` closed on `run_fault` with three cases `unanswered` and nothing to say why.

## Decision

| What | Decided | Because |
|---|---|---|
| What reads as `unanswered` | A case is `unanswered` before the deadline only where something raised past the review: an exception in building or answering its Task, a step's code the report has no word for, an interrupt, or a read of the home that raised. A model that ran out of turns is `no_answer`, a call past its seconds `engine_timeout`, a Task over the argument bound `task_too_large`, and a CLI that erred `engine_failed`: each its own code already | Read from `harness/eval/__init__.py`, `harness/eval/run.py`, `harness/run.py` and `harness/engine.py`. The tier's `cost_ceiling_usd` in `config/harness.json` is given to the CLI by nothing, so no cost ceiling can end a case |
| The cause | Each such case carries a `cause` in `eval-report/1`: the exception's class and the last line of this repo's own code outside its tests that it passed, a step's code, or the CLI's subtype and exit and whether its call timed out. A case the Engine stopped carries what the CLI said of it too. Each part is held to a shape that holds no words, and the judge's line counts them | A message, a traceback or the model's answer could quote a case (decision 0053). A class, a line of the Release's own code and the vendor's subtype say what to mend and nothing of what a case expected |
| Two paths mended | An answer nested past what Python parses is no answer, and a call Python refuses, as an argument with a null byte, is `engine_failed`. Neither raises past the Engine any more | Either would have read as a case unanswered, the reviewer's run's fault and no one's to find |

## Why

The run took about eleven minutes against a budget of a hundred and ten, so no case was stopped by the deadline, and nothing in the report or the log said what raised. Which path the three cases took cannot be told from the code alone; the next run's report says it.

## Boundaries

| Boundary | Check |
|---|---|
| A case that raised says its class and last place in this repo, a step's code the report lacks says that code, an interrupt says its own and the cases after it none, a read of the home that raised says the same, and no message reaches the report; the judge's line counts each cause | `tests/test_evals.py::test_an_unanswered_case_says_why_by_its_class_its_place_and_its_code` |
| A case the Engine stopped says the CLI's subtype and exit, or that its call timed out; one that raised after the call says where and what the CLI said; nothing of one case's CLI is another's | `tests/test_evals.py::test_a_case_the_engine_stopped_says_what_the_cli_said_of_it` |
| A cause in words is no `eval-report/1` | `examples/invalid/eval-report.a-cause-in-words.json` |
| An answer nested past Python's parse and a call Python refuses are the Engine's, not raised | `tests/test_harness.py::test_an_answer_python_cannot_parse_or_a_call_it_refuses_is_the_engines` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
