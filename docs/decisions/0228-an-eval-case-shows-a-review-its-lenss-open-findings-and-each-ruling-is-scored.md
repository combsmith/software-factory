# 0228. An eval case shows a review its Lens's open Findings, and each ruling is scored

Status: accepted. The Factory Builder's rulings of 2026-11-18 on issue 886, "An eval case shows a review its Lens's open Findings and expects a ruling on each: Dispositions are unevaluated until then, before author_role is named": the five choices of the draft design. A second pull request adds the criterion a standing Finding sets aside, and its kind, to this record.

## Decision

| What | Decided | Because |
|---|---|---|
| What a case shows | `eval-case/1` takes an optional `shown`: one to fifty Findings, each by its id, with its category and severity as its Lens raised it, the text its Lens wrote and the ruling a reviewer should give, `accepted` or `rejected`. The category is one the case's Role owns and never `security`, and the severity is one that gates, as the Findings a live review is shown are. A case that shows one id twice is no case to score. A case without it shows none and is scored as before | A live review is shown its Lens's open Findings and rules on each (decision 0227). Nothing measured whether it rules rightly |
| The Task | The eval job gives each shown Finding to the Task as the reader gives a live Run its own: the id among the Task's Findings, and the text `finding:` and the id, before the issue's | What is measured is what runs |
| Who wrote the text | Each text is given under the case's own Role as a Lens, so its trust class is `role`. A case names no writer for it | A live Finding's text is the Lens's own first comment. A case that named a writer could plant a text under another trust class |
| A Finding no Task shows | A case whose Task lists a Finding it does not show whole stops before the Engine, `findings_not_shown`, a fault of the case's own as `diff_not_whole` and `issue_not_whole` are | A live Run would ask nothing and write a failed Result, which would read as the reviewer's failure |
| The score | A completed Result fails a case that shows Findings where one is left with no decision (`ruling_missing`), one is ruled otherwise than expected (`ruling_wrong`), or a Finding the case did not show is ruled (`ruling_unasked`). A Finding ruled twice, a Disposition with both halves, and a criterion covered as `finding_stands` with nothing ruled `rejected` are `ruling_wrong` too: `apply` refuses each whole. The case passes only if every ruling is right and its criterion is | Silence is no ruling, and `apply` refuses a Result that rules a Finding its Run was not shown |
| Where rulings count | In the development set as any case. In no gate set until the Maintainer makes one that names such a case | A gate set's ledger holds its cases by id |

## Why

Since step 2 of "A re-review is given none of its Lens's open Findings, so a thread closes on the silence of one more review" (issue 856), a review's `accepted` ruling releases its Lens's thread. Whether the reviewer rules rightly decided that, and no case measured it: a case could show a review no Finding, and the scorer read no Disposition.

What is not held: the reasoning behind a ruling is not scored, only the ruling. A Result's Dispositions on a case that shows no Finding are not scored either, though `apply` would refuse them. This repo holds no such case: the cases are the Maintainer's to place in the home.

## Boundaries

| Boundary | Check |
|---|---|
| Each Finding a case shows is ruled as the case expects and no other is ruled; a Result that did not complete is scored for none | `tests/test_evals.py::test_each_finding_a_case_shows_is_ruled_as_it_expects`, `tools/eval_result.py`, mutant: "a shown Finding left unruled passes its case", mutant: "a shown Finding ruled otherwise than expected passes its case", mutant: "a ruling on a Finding the case did not show passes its case", mutant: "a shown Finding ruled twice passes its case", mutant: "a Disposition with both halves passes its case", mutant: "rulings are scored on clean cases alone", mutant: "right rulings make up for a criterion not met", mutant: "rulings are scored only where nothing else failed" |
| A case's shown Findings reach the Task by id, each text under the case's Role before the issue's; one the Task does not show stops the case | `tests/test_evals.py::test_a_case_that_shows_findings_gives_them_to_the_task_as_a_live_run_is`, `harness/eval/run.py`, mutant: "a case's Task lists none of the Findings it shows", mutant: "a case whose Task does not show a Finding it lists is asked", mutant: "a case's Finding is written by a person" |
| `eval-case/1` refuses a Finding shown with no id, text, ruling, category or severity, a `security` one, one of a category no Role owns, one that does not gate, the same entry twice, none or more than fifty, and a writer named; one id shown twice is unreadable to the scorer. It takes either severity that gates, `blocking` or `major` | `tests/test_evals.py::test_each_finding_a_case_shows_is_ruled_as_it_expects`, `schemas/eval-case.schema.json`, mutant: "a case shows a Finding with no ruling expected", mutant: "a case shows one Finding twice", mutant: "a case shows a security Finding", mutant: "a case may show a Finding of a category no Role owns", mutant: "a case shows more than fifty Findings", mutant: "a case shows a Finding with no id", mutant: "a case shows a Finding with no text", mutant: "a case shows an info Finding", mutant: "a case may not show a blocking Finding", mutant: "a case shows a person's Finding", `tools/eval_result.py`, mutant: "a case that shows one Finding twice is scored" |
