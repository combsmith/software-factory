# 0100. An eval case's expected Finding is as its rubric gives it, read at run time, where the case is

Status: accepted. The Factory Builder's ruling of 2026-10-30 on issue 421, "An eval case's expected Finding has its criterion's severity and category, as a Result's must", which the Maintainer may overturn in review. It extends `docs/decisions/0088-a-finding-that-cites-a-criterion-has-the-rubrics-severity-or-the-result-is-uncovered.md` and `docs/decisions/0095-a-finding-that-cites-a-criterion-is-of-the-rubrics-category-or-the-result-is-uncovered.md` to the set that measures them, and adds a code to the report of `docs/decisions/0078-a-held-out-case-is-reviewed-by-the-task-and-the-engine-a-live-run-and-its-report-tells-nothing-it-expected.md`.

## Decision

| What | Decided | Because |
|---|---|---|
| The rule | A case whose expected Finding is of another severity or category than the rubric gives the criterion it asks about is no answer. `tools/eval_result.py`'s `off_rubric` reads it, and `score` says `unreadable`, `answer_off_rubric`, whatever the Result says | Coverage refuses a Result that cites a criterion at another severity or category. A case that expected one would pass a Result `apply` refuses and fail one it takes: what is measured would not be what runs (section 3.14) |
| Where it is read | At run time, in the eval job, where the cases are: `harness.eval.assess` reads each case, and one off its rubric is `unreadable`, `answer_off_rubric`, and nothing is asked of the model. The repo holds no case, and no check here could read one | The held-out rule: a case's content is never in this repo |
| What it says | The one code, beside the case's id, as every code of the report is. It names neither the severity nor the category, nor what the rubric gives, and holds no case's content and no word of the model's. The run fails by `case_failed`, and the gate stays closed | Its owner mends the case in the home, and a code is enough to find it |
| What the code tells, accepted | Only a case that expects a Finding can be off its rubric, so the code says that case's kind, and a change to the rubric would mark every such case. The Maintainer's ruling closing issue 430, "Evals: the public report's per-case verdicts can publish each case's kind", accepts it, in that issue's closing comment: an id's kind is useless without the case's content, and the model's Task holds no case id | So nothing is designed around it, by the Factory Builder's ruling |
| Not taken | A check in `tools/check_examples.py`. The issue asked for one. The examples are synthetic, and a test holds that each is on its rubric | The Factory Builder's ruling: where the cases live, never in the repo |
| A case the rubric cannot speak to | One that expects no Finding is not off it. One whose rubric lacks the criterion, or whose Role has none, is the scorer's `criterion_unknown`, as before. A rubric read that `kernel/coverage.py`'s `readable_rubric` refuses holds no case to it, so the case is off it | One rule, one code, and a rubric at fault fails closed |

## Why

The review of the rule that a cited Finding's category is the rubric's found that the set measuring the Role was held to neither rule: a case could reward a Result `apply` refuses, and no check would say so.

## Boundaries

| Boundary | Check |
|---|---|
| A case off its rubric, by severity or category, scores nothing, whatever the Result; each criterion is held to its own; a case of a criterion met, and one the rubric lacks, are not off it; the examples are on it | `tests/test_evals.py::test_a_case_whose_expected_finding_is_off_its_rubric_scores_nothing` |
| In the job, such a case asks nothing of the model, is `unreadable` by the code alone, and fails the run | `tests/test_evals.py::test_a_case_off_its_rubric_is_unreadable_by_its_code_and_asks_nothing` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
