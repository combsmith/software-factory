# 0228. An eval case shows a review its Lens's open Findings, and each ruling is scored

Status: accepted. The Factory Builder's rulings of 2026-11-18 on issue 886, "An eval case shows a review its Lens's open Findings and expects a ruling on each: Dispositions are unevaluated until then, before author_role is named": the five choices of the draft design, and that a case whose criterion is set aside counts under the kind `finding`.

## Decision

| What | Decided | Because |
|---|---|---|
| What a case shows | `eval-case/1` takes an optional `shown`: one to fifty Findings, each by its id, with the text its Lens wrote and the ruling a reviewer should give, `accepted` or `rejected`. A case without it shows none and is scored as before | A live review is shown its Lens's open Findings and rules on each (decision 0227). Nothing measured whether it rules rightly |
| The Task | The eval job gives each shown Finding to the Task as the reader gives a live Run its own: the id among the Task's Findings, and the text `finding:` and the id, before the issue's | What is measured is what runs |
| Who wrote the text | Each text is given under the case's own Role as a Lens, so its trust class is `role`. A case names no writer for it | A live Finding's text is the Lens's own first comment. A case that named a writer could plant a text under another trust class |
| A Finding no Task shows | A case whose Task lists a Finding it does not show whole stops before the Engine, `findings_not_shown`, a fault of the case's own as `diff_not_whole` and `issue_not_whole` are | A live Run would ask nothing and write a failed Result, which would read as the reviewer's failure |
| The score | A completed Result fails a case that shows Findings where one is left with no decision (`ruling_missing`), one is ruled otherwise than expected (`ruling_wrong`), or a Finding the case did not show is ruled (`ruling_unasked`). The case passes only if every ruling is right and its criterion is | Silence is no ruling, and `apply` refuses a Result that rules a Finding its Run was not shown |
| A standing Finding's criterion | A case may expect the verdict `not_applicable` with the reason `finding_stands`, and only together, where it shows a Finding it expects ruled `rejected`. Its Result must cover the criterion so, by that code, and raise no Finding for it | The reviewer is told to set aside a criterion whose only fault is a Finding it rules `rejected`. The two verdicts a case could expect, `finding` and `met`, are both wrong for it |
| Its kind | Such a case counts under the kind `finding`, by `kind_of`. It expects no Finding, so no floor per criterion and no blocking rule reads it. No report, aggregate or set schema changes but for the new codes | A standing fault the review must keep held is the recall side. The looser bar is accepted while such cases are in the development set alone; one in a gate set is the Maintainer's to revisit |
| Where rulings count | In the development set as any case. In no gate set until the Maintainer makes one that names such a case | A gate set's ledger holds its cases by id |

## Why

Since step 2 of "A re-review is given none of its Lens's open Findings, so a thread closes on the silence of one more review" (issue 856), a review's `accepted` ruling releases its Lens's thread. Whether the reviewer rules rightly decided that, and no case measured it: a case could show a review no Finding, and the scorer read no Disposition.

What is not held: the reasoning behind a ruling is not scored, only the ruling. A Result's Dispositions on a case that shows no Finding are not scored either, though `apply` would refuse them. This repo holds no such case: the cases are the Maintainer's to place in the home.

## Boundaries

| Boundary | Check |
|---|---|
| Each Finding a case shows is ruled as the case expects and no other is ruled; a Result that did not complete is scored for none | `tests/test_evals.py::test_each_finding_a_case_shows_is_ruled_as_it_expects`, `tools/eval_result.py`, mutant: "a shown Finding left unruled passes its case", mutant: "a shown Finding ruled otherwise than expected passes its case", mutant: "a ruling on a Finding the case did not show passes its case" |
| A criterion is set aside only by `finding_stands`, with the verdict `not_applicable`, on a case that shows a Finding it expects ruled `rejected` | `tests/test_evals.py::test_each_finding_a_case_shows_is_ruled_as_it_expects`, `tools/eval_result.py`, mutant: "a criterion set aside by any code passes a case that expects a standing Finding's", mutant: "a case sets a criterion aside though it expects no shown Finding rejected" |
| A case's shown Findings reach the Task by id, each text under the case's Role before the issue's; one the Task does not show stops the case | `tests/test_evals.py::test_a_case_that_shows_findings_gives_them_to_the_task_as_a_live_run_is`, `harness/eval/run.py`, mutant: "a case's Task lists none of the Findings it shows", mutant: "a case whose Task does not show a Finding it lists is asked", mutant: "a case's Finding is written by a person" |
| A case set aside for a standing Finding counts under the kind `finding`, and a set that holds one is read | `tests/test_evals.py::test_a_set_short_of_a_kind_fails_the_run_and_closes_the_gate_saying_no_count`, `harness/eval/__init__.py`, mutant: "a case set aside for a standing Finding counts among the clean ones", mutant: "a case set aside for a standing Finding is of no kind" |
| `eval-case/1` refuses a Finding shown with no ruling, one shown twice, none shown, a writer named, and any other code than `finding_stands` | `tests/test_evals.py::test_each_finding_a_case_shows_is_ruled_as_it_expects`, `schemas/eval-case.schema.json`, mutant: "a case shows a Finding with no ruling expected", mutant: "a case shows one Finding twice", mutant: "a case sets a criterion aside by any code", `tools/check_examples.py`, `examples/invalid/eval-case.a-finding-shown-with-no-ruling.json` |
