# evals/

What this repo holds of each held-out eval set: one manifest a directory, `<role>/cases.json`, with the Role, the Intent,
the count of cases and each case's id and sha256. The cases themselves live in a private repo under a different owner
(design §3.13), read only by the eval job (§4.9), and never here, in a pull request, an issue or a note.
`tools/eval_result.py` scores one `result/1` against one case, at run time, where the case is.

| Rule | Held by |
|---|---|
| A manifest is `eval-set/1`, its count is its list's length, and no file here is a case or holds a diff | `tests/test_evals.py::test_the_manifest_counts_its_cases_and_holds_no_case` |
| A new file here is added to `LIVE` in `tools/check_examples.py`, with its schema | `tools/check_examples.py` |
| A Result passes a case by raising the Finding it expects, in its category, severity and place, with the coverage agreeing | `tests/test_evals.py::test_a_result_that_raises_the_expected_finding_passes_and_one_that_does_not_fails` |
| A right change passes by covering its criterion as met and raising nothing against it | `tests/test_evals.py::test_a_right_change_is_scored_by_its_coverage` |
| A case or a Result that cannot be read scores nothing | `tests/test_evals.py::test_a_case_or_a_result_that_cannot_be_read_scores_nothing` |
| The review Intent's set has its cases, and the cutover waits on them | `tests/test_evals.py::test_the_review_intents_eval_set_has_its_cases`, not held yet |
