# NNNN. `apply` checks every field of a Result that needs no diff before it reads the diff, and a Finding's lines last

Status: accepted. The Factory Builder's ruling of 2026-11-06 on "apply checks a Result's own fields before it reads the diff, so a Result refused for them spends no read" (issue 573), a follow-on to decision 0146. It changes the order in which `apply` refuses a Result, and when it reads the diff, and nothing else in 0146.

## Decision

| What | Decided | Because |
|---|---|---|
| When the diff is read | `job` makes every check of `refusal` but a Finding's lines first, by the facts and the Result alone: a change under the Run, the Result not this Run's or this Release's, a reason its status may not give, a Result that did not complete, one uncovered, its Effects, its Findings' places and adoptions, and its Dispositions. Only a completed Result that posts a Finding and that all of these let through has its diff read again, as decision 0146 reads it, and then its Findings' lines checked | A Result refused for its own fields spends no read, and is refused for itself. Read first, a diff whose bytes were not the content ended such a Result `superseded`, `content_moved`; a head that moved, `superseded`, `head_moved`; and a read that failed, the environment's, `facts_unreadable`, which counts toward a pause |
| The order of the refusals | A posted Finding on lines no hunk of its file holds (`finding_not_in_hunk`) is the last refusal, after the Dispositions, where it was between a Finding's path and its adoption. A Result refused for both is refused for the other | The one check that needs the diff comes after every check that does not, so the diff is read for a Result that may be written |
| Who makes the check | `off_hunks(task, result)` holds the lines. `job` makes it once the Task's diff is built again. `refusal` makes it last, and leaves it out only when `lines` is false, as `job` asks before the diff is read. By default it is made, of the Task's diff, so a caller that forgets fails closed: it refuses, or stops for want of the diff, and never writes a Finding no check held | One function holds the rule, wherever it is asked, and the Factory fails closed |

## Why

`apply` read the diff after a change under the Run was told, but before it checked the Result itself. A Result that was not this Run's, or gave a reason its status may not give, or was uncovered, still had three requests made for it, and a failed one made its ending the environment's. Every check that needs no diff now comes first.

## Boundaries

| Boundary | Check |
|---|---|
| A Result refused for its own fields, its run or its Release, its reason, its status, its coverage or its rubric unread, its Effects, a Finding posted other than once, a Finding's path or its adoption, or a Disposition, reads no diff and is refused for itself, though the read would fail or find the head moved | `tests/test_apply.py::test_a_result_refused_for_its_own_fields_reads_no_diff` |
| A Finding's lines are the last refusal: a Result refused for its adoption or a Disposition too is refused for that; `refusal` leaves the lines out only when asked, and holds them by default | `tests/test_apply.py::test_a_findings_lines_are_held_last_and_only_when_asked` |
| The live path, from what the Decision admitted, still refuses a Finding off every hunk of the diff read again | `tests/test_apply.py::test_the_live_path_holds_a_result_to_what_was_admitted_and_the_diff_read_again` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
