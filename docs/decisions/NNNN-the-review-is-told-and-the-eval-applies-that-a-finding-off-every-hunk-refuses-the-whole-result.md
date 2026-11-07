# NNNN. The review is told, and the eval applies, that a Finding off every hunk refuses the whole Result

Status: accepted. The Factory Builder's story of 2026-11-07, issue 574, "The prompt and the eval state that a Finding off every hunk refuses the whole Result, after factory/v0.1.0". It answers the cost decision 0146 named: `apply` refuses a whole Result that posts a Finding off every hunk of its file (`finding_not_in_hunk`), while neither the prompt nor the eval said so.

## Decision

| What | Decided | Because |
|---|---|---|
| The prompt | `roles/pr-review/prompt.md` tells the review that each Finding's lines, from `start_line` to `end_line`, are all on one hunk of its file in the diff, lines the diff numbers, and that a Finding on a line read only in the head, or across two hunks, refuses the whole Result, every other Finding with it | The review reads the head too (decision 0138), so it may place a Finding on a line no hunk holds, and lose its other Findings with it |
| The eval | `tools/eval_result.py` fails a case by `finding_not_in_hunk` alone when the Result posts a Finding, as a review's comment or a check run's annotation, its lines given, whose lines are not all on one hunk of its file on the head's side of the case's diff. It reads both with `apply`'s own `posts` and `off_hunks`, over the case's diff numbered as the Task gives it (decision 0137), so the eval and a live Run refuse the same Result | A refused Result posts nothing, so the gate counts the refusal a live Run would meet, and a review that loses its Findings this way scores as one that missed them |
| What the eval leaves to `apply`'s other codes | A fault of the case is told first, as before, and a Result that did not complete as `result_not_completed`, which `apply` refuses first. A Finding the Result does not post is scored as before. A posted Finding with no lines, which `apply` refuses as `finding_has_no_place`, is scored as before too. A posted Finding on a file the diff does not hold is `finding_not_in_hunk` here, though `apply` names it `finding_not_on_change` first | The issue asks for the hunk rule. Either way the Result is refused, and the case fails |
| The report | `eval-report/1` lists `finding_not_in_hunk` among a case's codes, a fail of the reviewer's, as any miss is | A code the report could not carry would leave the case unread |
| The public examples | Left as they are. The example Result posts an annotation on `tests/test_decide.py`, which the example cases' diff does not hold, so the tests that score it post none of its Findings, and a test of this rule posts its own | The canary reviews the example case, and `tests/test_apply.py` builds its own diff to suit the example Result, as these tests now suit the Result to the diff |
| A hunk whose header counts other lines than it holds | Not changed. `apply` reads a hunk's lines from its header, and the scorer's check of a case's `also_at` (decision 0143) from the lines the diff numbers | Git writes the two alike; the example cases' diff is the one that does not |

## Why

Decision 0146 made `apply` refuse a Result whole for a Finding off every hunk, and named the cost: the model was not told, and the eval did not score it, so the gate could pass a review a live Run would refuse. The prompt now says it, and the eval refuses the same Result `apply` refuses, by `apply`'s own code.

## Boundaries

| Boundary | Check |
|---|---|
| A posted Finding on the hunk's first and last lines passes; one a line before or past it, or on a file the diff does not hold, fails by `finding_not_in_hunk` alone, as `apply.off_hunks` refuses it; a comment and an annotation are each held beside the other, on a clean case too; a Finding not posted, or posted with no lines, is scored as before; a fault of the case is told first, and a Result that did not complete as that | `tests/test_evals.py::test_a_posted_finding_off_every_hunk_fails_the_case_as_apply_refuses_the_result` |
| The report carries the code, as one of the reviewer's | `tests/test_evals.py::test_the_gate_holds_each_kinds_bar_and_a_fault_still_closes_it` |
| The prompt tells the review the rule | `tests/test_evals.py::test_the_review_reads_the_head_places_a_finding_where_a_fix_goes_and_cites_what_it_raises` |
| The example Result read whole against the example case fails by it, read through the front door | `tests/test_evals.py::test_the_front_door_scores_two_files_and_says_so_in_its_exit` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
