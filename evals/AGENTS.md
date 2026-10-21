# evals/

What this repo holds of each held-out eval set: one manifest a directory, `<role>/cases.json`, with the Role, the Intent,
the count of cases and each case's id and sha256. The cases themselves live in a private repo under a different owner
(design §3.13), read only by the eval job (§4.9), and never here, in a pull request, an issue or a note.
`tools/eval_result.py` scores one `result/1` against one case, at run time, where the case is. `context/task.json` is the
context's test (issue 8, "The context's test: a fresh agent adds a rule to the Kernel without being told how"): one task
sentence, the sha256 of its held-out answer, and each run of a fresh agent on it, made by `tools/context_eval.sh` at the
Maintainer's terminal and recorded by `tools/context_eval.py` with no text of the model's.

| Rule | Held by |
|---|---|
| A manifest is `eval-set/1`, and its count is its list's length | `tests/test_evals.py::test_the_manifest_counts_its_cases_and_holds_no_case` |
| Nothing lives here but a manifest in `LIVE` and these rules, and no file here, of any name, holds a case or a diff | `tests/test_evals.py::test_a_case_dropped_under_evals_in_any_file_is_caught` |
| A new file here is added to `LIVE` in `tools/check_examples.py`, with its schema | `tools/check_examples.py` |
| A Result passes a case by raising the Finding it expects, in its category, severity and place, with the coverage agreeing | `tests/test_evals.py::test_a_result_that_raises_the_expected_finding_passes_and_one_that_does_not_fails` |
| A right change passes by covering its criterion as met and raising nothing against it | `tests/test_evals.py::test_a_right_change_is_scored_by_its_coverage` |
| A case or a Result that cannot be read scores nothing, a case whose criterion its Role's rubric lacks among them | `tests/test_evals.py::test_a_case_or_a_result_that_cannot_be_read_scores_nothing` |
| A case expects a Finding in the Finding's own categories and severities | `tests/test_evals.py::test_a_cases_categories_are_the_findings` |
| The review Intent's set has its cases, and the cutover waits on them | `tests/test_evals.py::test_the_review_intents_eval_set_has_its_cases`, not held yet |
| A run's record holds paths, first words, counts and verdicts, and no word of the model's | `tests/test_tools.py::test_the_record_holds_paths_counts_and_verdicts_and_no_model_text` |
| What cannot be read makes no record | `tests/test_tools.py::test_what_cannot_be_read_makes_no_record` |
| The runner gives the CLI the named environment alone and judges by the held-out test, `make verify` and the mutation check | `tests/test_tools.py::test_a_run_is_judged_and_recorded_with_no_model_text` |
| The runner refuses before it asks anything of the model | `tests/test_tools.py::test_each_refusal_stops_before_anything_is_asked` |
| The context's test passes three of three on its task, and the slice-0 exit waits on it | `tests/test_evals.py::test_a_fresh_agent_given_the_repo_adds_a_rule_and_passes_the_check`, not held yet |
