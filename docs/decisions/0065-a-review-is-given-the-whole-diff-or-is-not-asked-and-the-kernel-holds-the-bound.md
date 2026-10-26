# 0065. A review is given the whole diff or is not asked, and the Kernel holds the bound

Status: accepted. Taken as working rulings on 2026-10-25, which the Maintainer may overturn in review, for "Kernel: a pull request whose diff the Task cannot carry whole is held" (issue 327). It extends `docs/decisions/0050-the-model-is-given-a-task-and-no-tool-and-apply-writes-only-what-it-reads-back.md`, whose Task cuts a diff over its budget at a file's boundary and says what it left out, and moves that budget, which 0050 placed in `config/harness.json` as `texts.diff_characters`, to the Kernel's own limits; 0050 is not edited.

## Decision

| What | Decided | Because |
|---|---|---|
| The bound | `config/defaults.json`'s `limits.max_diff_characters`, 60000, is the one bound on a diff a review is given. The Kernel reads it from its configuration and the Harness from the same file (`harness/run.py`'s `configuration()`); `config/harness.json` no longer holds one | Two bounds can drift: a Kernel that admits what the Harness cuts would have a review judge part of a change as the whole |
| The fact | `facts/1`'s `diff` gains `characters`, optional: the whole diff's length as a Task carries it, escaped as JSON, counted by `adapters/pull.py` from the text GitHub served. A diff GitHub will not serve has none, and nor has one whose bytes are no UTF-8, which the Harness refuses as no text | The Harness counts the Task's diff the same way (`harness/task.py`'s `carried()`), so the Kernel's count and the Harness's are of one thing |
| The hold | `derive` holds a pull request `too_large` when `diff.characters` is absent, is not a whole number, is below 0, or exceeds `max_diff_characters`, in the place it already holds a truncated diff or one of too many lines | An unread fact yields a Hold, never an action (I-13). The Hold is the Kernel's, and a person sees it, rather than a Run spent and failed |
| A Task cut short | The run job writes a `failed` Result, reason `diff_not_whole`, before the CLI is started, when the Task of an Intent in `REVIEWING` left out any of the diff. The issue asked `apply` to refuse it; the run job refuses it earlier, before a model call is spent, and `apply`'s own decision reads the Kernel's Hold | Defence in depth: the Kernel should never admit such a Run, and if it did no review judges part of a change. The fault is the Factory's, an `environment` one |

## Why

A diff over the Task's budget was cut at a file's boundary and the review asked all the same, told only that files were
left out (decision 0050). A review's verdict then covered a change it had not read whole. Holding the pull request
before any Run is admitted keeps the verdict whole, and puts the decision with a person.

## Boundaries

| Boundary | Check |
|---|---|
| A diff at the bound is reviewed; one past it, or whose length was not read, is below 0 or is no whole number, is held `too_large` | `tests/test_decide.py::test_a_diff_no_task_can_carry_whole_is_held_and_one_at_the_bound_is_reviewed` |
| A queued pull request whose diff is past the bound leaves the queue | `tests/test_decide.py::test_every_hold_takes_a_queued_pull_request_out` |
| The port counts the diff as the Harness counts the Task's | `tests/test_adapters.py::test_the_diff_is_counted_as_the_harness_counts_the_task_it_carries` |
| A diff whose bytes are no UTF-8 is given no length, so the Kernel holds what the Harness refuses | `tests/test_adapters.py::test_the_content_is_hashed_over_the_bytes_github_sent` |
| A reviewing Run whose Task left part of the diff out is never asked, and the run job reads the Kernel's bound | `tests/test_harness.py::test_a_review_given_part_of_the_diff_is_never_asked` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
