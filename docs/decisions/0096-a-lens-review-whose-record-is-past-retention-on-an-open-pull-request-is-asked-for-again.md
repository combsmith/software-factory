# 0096. A Lens review whose record is past retention on an open pull request is asked for again

Status: accepted. The Factory Builder's ruling of 2026-10-26 on "Threads port: a Lens's recorded Finding comment missing from the threads read leaves it unreadable" (issue 338), built as "Kernel: a Lens review whose applied/1 is past retention on an open pull request is asked for again" (issue 346). It answers the accepted miss in decision 0069's row "Retention, the accepted miss", whose decision stands as it was: a record past retention is still read as recording nothing, and now it is also named, so its review is asked for again.

## Decision

| What | Decided | Because |
|---|---|---|
| Telling it apart | `adapters/artifacts.py` tells an `applied/1` past the artifact retention apart from one never uploaded: `applied` reads it as `EXPIRED`, whole. `adapters/applied.py` names its Run among those read, as expired and as reviewing nothing that can be held | A record gone with time and a record never written read alike, and only the first had something in it |
| The fact | `facts/1` gains `expired_reviews`, the run ids of the pull request's Lens Runs whose `applied/1` is past retention. A list the Kernel cannot read, or one holding anything but text, is `facts_incomplete`; the schema holds each to a run id's form | An unreadable fact yields a deferral (I-13) |
| The rule | A Lens whose Run on the item has a record past retention is asked to review the item's current content again (`awaiting_review`, and the Kernel admits it) until a review of exactly that content by that Lens succeeds after the expired Run. Another Lens's expired Run asks nothing of this one. A queued item reads past it, as it reads past any wait for a review | What the expired Run recorded can no longer be held to its threads; a fresh review records what still stands, on threads of its own (decision 0075) |
| The limit | The fresh review does not by itself close the expired Run's own open threads: with no record, their category and severity still cannot be joined, so a required Lens's open one is unreadable. An unreadable fact yields a deferral, never an action, and the Kernel reads threads before it asks for a review, so while such a thread is open the item defers and the review is not asked until a person resolves it. The rule asks again where the expired Run left no open thread, as where a thread it recorded was deleted whole after the window. That is "An expired Lens Run's open threads can be closed without a person, by that Lens's ruling carried out by the queue App" (issue 420), through decision 0086's resolve act, which waits on the queue App | The Builder's ruling: this story asks the review again, and no more |

## Why

A pull request can stay open past the 90 days an artifact is kept, since the stale rule marks attention and never closes or holds one. Its Lens's record then reads as recording nothing, and the problems it raised can no longer be read. Asking that Lens again, on what the pull request now holds, puts a readable record back in their place.

## Boundaries

| Boundary | Check |
|---|---|
| A Lens's Run whose record is past retention asks its review of the current content again; a later review of that content that succeeded answers it; a failed one, one of other content, one before it, or another Lens's does not; another Lens's expired Run asks nothing of this one; a list that cannot be read defers | `tests/test_decide.py::test_a_lens_review_past_retention_is_asked_for_again` |
| A record past retention is told from one never uploaded, and its Run is named expired | `tests/test_adapters.py::test_a_lens_runs_applied_record_is_read_by_the_one_github_run_its_name_names` |
| The snapshot names each Lens Run whose record is past retention | `tests/test_adapters.py::test_a_snapshot_names_each_lens_run_whose_record_is_past_retention` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
