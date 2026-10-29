# 0075. A later review by the same Lens supersedes its earlier records for a thread that is gone

Status: accepted. The Factory Builder's rulings of 2026-10-26 and 2026-10-27, option (b), for the issue the Why names. The Maintainer may overturn it in review.

## Decision

| What | Decided | Because |
|---|---|---|
| What supersedes | A later review of the same Lens, a Run of Intent `review-change` whose conclusion is success, its `applied/1` read whole, on the pull request's current content, supersedes every Run of that Lens that started before it, for the rule that every recorded thread is in the threads read and opened by its Lens | A fresh review of the current head says what that Lens now holds of the change |
| Whose | The same Lens only. Another Lens's Run supersedes nothing | A Lens speaks for its own Findings alone |
| Which head | Only a Run on the current content: its head is the current head, at or after any earlier Run's. A Run on any other content supersedes nothing, since no order of heads can be read from a content id; nor does one that started at the same time as, or before, the Run it would supersede, or one whose start, or the earlier Run's, cannot be read | If the order of heads cannot be read, nothing is superseded and the hold stays. So a Run on an older head never releases a hold, even where its content matches an earlier snapshot's: only the snapshot's own content counts, and a Run on it supersedes only Runs that started before it, so a head pushed away and back does not let an older Run release a record a later one made |
| Read whole, and a review | A later Run whose `applied/1` cannot be read leaves the pull request's threads not whole, as before, and supersedes nothing. A Run that failed, was cancelled or timed out reviewed nothing, though one that uploaded no record is read as recording nothing, whole; an adjudication re-reads Findings without reviewing the change; a review whose record is past retention, read as none, cannot be read. None of them supersedes. A start is read only as GitHub writes one, a real time to the second | What cannot be read is never read as none, and only a review can raise a problem again (the Claude review of this record) |
| What stays | A thread the superseding Run also records is still held to its opener; a thread any Run that is not superseded recorded is still held. The join, each Lens thread's category and severity from its Lens's one Finding, does not change | The fresh review's own record holds what it raised |
| A problem that still stands | The later Run raises it again, as a Finding on a thread of its own, which is held to its opener | A deleted Finding is not a resolved one |
| Where the content comes from | `adapters/applied.py`'s `recorded` hands each Lens Run it read whole, with its content and start, and the Runs that recorded each thread; `held` takes the snapshot's own content id. A caller that gives none supersedes nothing | The snapshot is the one read that knows the current content |

## Why

"Applied port: a later review by the same Lens supersedes its earlier records for a thread that is gone" (issue 347) asked for this.
Under `docs/decisions/0069-what-a-lens-recorded-holds-its-threads-and-gives-each-its-category.md` a Lens comment deleted whole took its thread with it, and no read could tell the thread had been resolved
before it went, so the pull request was held for the 90 days of the artifact retention whatever anyone did. A
person's label as an override was not taken: who may apply one needs its own decision.

## Boundaries

| Boundary | Check |
|---|---|
| A later review by the same Lens, read whole, on the current content, releases a thread that is gone; a problem it raises again is held to its opener | `tests/test_adapters.py::test_a_later_review_by_the_same_lens_on_the_current_content_releases_a_thread_that_is_gone` |
| A review by another Lens supersedes nothing | `tests/test_adapters.py::test_a_review_by_another_lens_supersedes_nothing` |
| A review on other content, or that started at the same time or before, or whose start cannot be read, supersedes nothing | `tests/test_adapters.py::test_a_review_on_other_content_or_before_supersedes_nothing` |
| A later review whose record is read short releases nothing | `tests/test_adapters.py::test_a_later_review_whose_record_is_read_short_releases_nothing` |
| A later Run that failed, was cancelled, timed out, or adjudicated, or a review whose record is past retention, releases nothing | `tests/test_adapters.py::test_only_a_later_review_that_succeeded_supersedes` |
| A thread both reviews record is still held to its opener | `tests/test_adapters.py::test_a_thread_both_reviews_record_is_still_held_to_its_opener` |
| The snapshot tells the threads its content | `tests/test_adapters.py::test_a_snapshot_tells_the_threads_its_content_so_a_later_review_supersedes` |
| No current content, missing or empty, supersedes nothing, though a later Run's record names none in the same way | `tests/test_adapters.py::test_a_later_review_by_the_same_lens_on_the_current_content_releases_a_thread_that_is_gone` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
