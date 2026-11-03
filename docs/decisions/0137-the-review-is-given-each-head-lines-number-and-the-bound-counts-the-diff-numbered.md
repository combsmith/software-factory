# 0137. The review is given each head line's number, and the bound counts the diff numbered

Status: accepted. The Factory Builder's ruling of 2026-11-03 on eval run 41718110053 on the commit 746603e9: 22 of 40 passed, with no fault and nothing unanswered; of the finding kind, 7 `location_differs`, 7 `finding_not_raised`, 3 `finding_elsewhere`, and the blocking case `finding_uncited`, `category_differs` and `severity_differs`. The fix is the Role's, never a case's or the gate's. It extends `docs/decisions/0065-a-review-is-given-the-whole-diff-or-is-not-asked-and-the-kernel-holds-the-bound.md`, whose one bound now counts the diff numbered, and `docs/decisions/0050-the-model-is-given-a-task-and-no-tool-and-apply-writes-only-what-it-reads-back.md`, whose Task carries the change; neither is edited.

## Decision

| What | Decided | Because |
|---|---|---|
| The numbers | The Task's diff text leads each line of a hunk that the head's file holds, a context line or an added one, with its line number in the head's file and `\|`, as `87\|+    if not items:`. A removed line, git's note that a file has no last newline, and every line outside a hunk are as git wrote them. A hunk ends when its header's counts are spent, or at a line no hunk holds, so the next file's `--- a/` is never read as a removed line. A row ends at a newline alone, as git ends one: a form feed, a lone carriage return or a Unicode line break inside a line is that line's text, so an author's text can neither forge a header nor end a hunk early. A header's numbers are of nine digits at most, and a longer one is no header, so no diff makes the count raise. `harness/task.py`'s `numbered()` does it | The scorer places a Finding by the head's lines, and the model was left to count them from each hunk's header, inside a diff carried as one JSON string. Counting, it landed one line off on a long diff |
| The text | The text's id is still `diff:<content id>`, and the bytes are still held to the content the Decision admitted before they are numbered. The numbers are added by the Harness, from the bytes, never read from the item | What the Run judges is still only the admitted content; the numbers are the Release's rendering of it |
| One measure | `adapters/pull.py` counts `characters` as `harness/task.py` carries the diff, numbered and escaped, by the same two functions, and the Task's budget counts each file's part the same way. Numbered file by file, a diff is numbered as it is whole, so the Kernel's bound and the Task's cut stay one measure (0065) | Two counts can drift: a port that counted the diff as git wrote it would admit a diff the Task then cuts, and a review would never be asked |
| The prompt | `roles/pr-review/prompt.md` says what the numbers are: the head's line, and none on a removed line; a Finding's `start_line` and `end_line` are the numbers the diff gives the lines where the problem is | A number the model is not told the meaning of is one more thing to guess |
| The cost | The numbers lengthen the diff as the Task carries it. On the public examples, `examples/eval-case.json`, `eval-case.met.json` and `eval-case.with-issue.json`, by 5.8%, 5.8% and 8.0%. On the diffs of this repo's last 60 first-parent commits on `main`, the 42 within the bound, by 4.4% in all, 4.0% at the median and 8.0% at most. So a diff within about that much of `limits.max_diff_characters`, 60000, which a review was given before, is now held `too_large`; the bound itself does not move. What this costs the held-out set was checked privately, and no case is affected | The bound is the Kernel's, and a Task that carries more than it counted would fail at the CLI's argument limit instead |
| What does not change | `tools/eval_result.py`, the set, the rubric, and the bound's value | The gate and the set are the Maintainer's; this is the Role's side |

## Why

The failing codes asked first whether the review is told the place the scorer reads. Path form, citing, category and
severity agree with `tools/eval_result.score`; the lines did not. With the eval's own Task and argv, the CLI at 2.1.317
(the pin is 2.1.306) and model `opus`, on synthetic cases made from this repo's own files, each with one logic error
planted at a known head line: on diffs of about 30 lines the review cited PR-3 at the exact line 5 times of 5. On diffs
of 100 to 140 lines, whose earlier hunks shift the head's numbering from the base's, it was at the line 4 times of 6 and
one line off twice; told how to count in the prompt alone, 5 of 6; given the numbers, 6 of 6. With this record's prompt and Task, 6 of 6 again on the long diffs and 6 of 6 on the short.

## Limits

The samples are small, of synthetic cases and not of the held-out set, and were not made at the pin. Nothing here ties
any held-out case's code to the numbering: one line off would explain a `location_differs` or a `finding_elsewhere`
only where a case expects a narrow place, which this repo cannot read. A `finding_not_raised`, and the blocking case,
read as the review's judgement, which the private replay shows. The next eval run measures it. Nothing here reads a
case.

## Boundaries

| Boundary | Check |
|---|---|
| Each line of a hunk the head holds is led by its number there; a removed line, the no-newline note and a line outside a hunk are as git wrote them; a hunk ends when its counts are spent; a row ends at a newline alone, and a header of a number past nine digits is none; numbered file by file is numbered whole | `tests/test_harness.py::test_each_line_the_head_holds_is_given_its_number_there` |
| The port counts the diff as the Task carries it, numbered, and the Task carries it numbered; an added line's text forging a header is counted as the line it is | `tests/test_adapters.py::test_the_diff_is_counted_as_the_harness_counts_the_task_it_carries` |
| The Task's budget counts the diff numbered, and a review given part of it is never asked | `tests/test_harness.py::test_a_change_over_its_budget_is_cut_at_a_files_boundary_and_says_how_much`, `tests/test_harness.py::test_a_review_given_part_of_the_diff_is_never_asked` |
| A Finding placed at the line the public example's Task numbers passes the scorer, and the review is told what the numbers are | `tests/test_evals.py::test_a_finding_at_the_line_its_task_numbers_is_where_the_scorer_looks` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
