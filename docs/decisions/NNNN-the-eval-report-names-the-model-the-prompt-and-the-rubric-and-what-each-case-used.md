# NNNN. The eval report names the model, the prompt and the rubric, and what each case used

Status: accepted. The Factory Builder's story of 2026-11-07, issue 616, "The eval report records the model, prompt and rubric it ran, and each case's usage", of the gate-v1 set. `config/harness.json` named the model, but `eval-report/1` held no model, prompt or rubric, and nothing of what a case used. So a change between two Releases' scores could come from the model or the prompt and nobody could tell, and the tier's limits could not be tuned from what a run used.

## Decision

| What | Decided | Because |
|---|---|---|
| The model | `models`: each model a case's CLI said answered it, by the id its `modelUsage` gave (`harness/engine.answering`, decision 0147), not the configured name. One where the run is whole. The run line, `tally`, says `answered by …, not the configured …` where they are not the configured model alone | The configured name is what was asked for. What answered is what the score measures, and the Engine already refuses another model's answer |
| The prompt and the rubric | `prompt_sha256` and `rubric_sha256`: the sha256 of `roles/<role>/prompt.md` and `config/rubric-<role>.json` at the commit checked out, the files `harness/run.instructions` tells the model, or null of one that is not there | A hash says whether either changed between two runs and names no word of either. Both are public in this repo, so nothing is told that is not already there |
| What a case used | Each case's `usage`: `turns`, `cost_usd` and `seconds`, numbers read from the CLI's own answer as `result/1` holds them. Turns and cost are null where the CLI reported none or was never asked; seconds are 0 where it was never asked. A value that is no number is none | The tier's limits (issue 615) are set from what cases use. A number names no case content and no word of the model's |
| A gate set | Not here. Issue 612 makes a gate set's public report aggregates alone; its aggregate carries these fields' sums and the identity | Per-case numbers under stable ids are what a gate set must not show; the development set's report shows its cases already |
| The gate | `verdict` reads the report as before, held to its schema. A report from another model is not refused by it | The Engine refuses another model's answer case by case (decision 0147). The run line says so, for the Maintainer to read |

## Why

Two Releases' scores can differ because the model behind the pinned name moved, or because the prompt or rubric changed. The report now names all three, so a change of score can be traced to one of them. Each case's turns, cost and seconds let issue 615 set the tier's limits from what a run used, not from a guess.

## Boundaries

| Boundary | Check |
|---|---|
| The report names the models the CLI said answered, the prompt and rubric by their sha256, or null with neither in the Release, and each case's turns, cost and seconds as the CLI reported them; a case never asked used nothing; a value that is no number is none; a model other than the configured one is said in the run line, and the configured one alone is not | `tests/test_evals.py::test_a_report_names_the_model_prompt_and_rubric_and_what_each_case_used`, `harness/eval/__init__.py`, mutant: "the report keeps no usage of a case", mutant: "what a case used is read as nothing", mutant: "the report names the configured model, not the one that answered", mutant: "the report names no prompt", mutant: "the rubric is read as the prompt", mutant: "a model other than the configured one is not said", mutant: "the run line names the models whatever answered", mutant: "the configured model is not read", mutant: "a cost that is no number is kept", mutant: "turns that are no count are kept" |
| The schema requires each field, and refuses a cost or a model in words and a case with no usage | `tools/check_examples.py`, `schemas/eval-report.schema.json` |
