# 1150. The facts port reads a pull request's timeline to ten pages

Status: accepted. Extends decision 0234 with its bound on the facts port's reads of a pull request's own timeline and reviews, as "adapters: bound a pull request's timeline and seen-issue reads by pages" (issue 1009) asks, part 2 of 4, as the Factory Builder ruled on 2026-11-20. It restates the row of decision 1149 that it widens, now that the port says a cut; decisions 0234 and 1149 stand as they are.

## Decision

| What | Decided | Because |
|---|---|---|
| A cut timeline | `timeline_bounded` in `facts/1` says the facts port cut the pull request's own timeline, or its reviews, at its bound. The port gives it in every snapshot. Absent, it is not cut. The Kernel defers a pull request so cut on that reason, the issues' own, after a cut acceptance read and before any list read short, whatever `complete.timeline` claims, and calls a person; a queued one is taken out. Its evidence names the reads not whole, the reviews, the timeline or both, and both where each claims to be; a value that is no truth value is a gap in those same reads (the Solution Architect, 2026-11-24) | Anyone can comment on or review an open pull request, and a timeline past its bound never mends: read short and said no more, it would wait in silence (the Claude and security reads of the acceptance port's bound). The cut acceptance read is said first: the issue it names is what a person can mend |
| A pull request's own reads | The facts port reads a pull request's own timeline, and its reviews, to ten pages each (`timeline.bounded`, and `BOUND` in `timeline.reviews`). A tenth page that names an eleventh leaves the list not whole and cut, `timeline_bounded`, and the eleventh is never asked. A review dismissed past a timeline not read whole, cut or short, leaves the reviews not whole, never the snapshot refused | Anyone can comment on or review an open pull request, and each was read whole on every pass: the amplification the issues port's bound ends, on the pull request side (the Claude and security reads of the acceptance port's bound) |

## Why

Decision 1149 has the Kernel call a person for a pull request whose own timeline was cut, with the port saying no cut yet. This part bounds the facts port's reads of the timeline and the reviews, as decision 0234 bounds the issues port's, and says the cut, so that comments and reviews by anyone cost a bounded number of requests and stop the pull request in plain view.

## Boundaries

| Boundary | Check |
|---|---|
| The facts port reads a pull request's own timeline, and its reviews, to ten pages: ten that end there are whole; a tenth that names an eleventh is not whole, the eleventh is not asked, and a cut timeline or reviews list is said, false where each was read whole or short within the bound; a dismissal past a timeline not read whole leaves the reviews not whole, left out before its commit is asked, and the snapshot is still made | `tests/test_adapters.py::test_a_snapshot_says_whether_its_own_timeline_was_cut`, `tests/test_adapters.py::test_a_dismissed_review_the_timeline_does_not_explain_is_refused`, `adapters/facts.py`, `adapters/timeline.py`, mutant: "the snapshot reads its own timeline past ten pages" |
| Reviews cut alone defer on `timeline_bounded` and name the reviews; a cut beside two whole reads names both | `tests/test_decide.py::test_a_reviews_list_cut_at_its_bound_defers_as_a_cut_timeline_and_names_the_reviews`, `kernel/derive.py`, mutant: "a cut reviews list is named as a cut timeline" |
| Limit: anyone can cut a pull request's own timeline, by some thousand comments or reviews, and more events never mend it: it then waits on a person, and is taken out of the queue if it was in it, a pull request a person queued and marked hands-off among them, until the comments are deleted or it is closed; its Factory check keeps its last title, and the feed carries the call. Its author can do the same to their own. While it is so, reconciliation reads the writes of a cut timeline short on every pass | `tests/test_decide.py::test_a_timeline_cut_at_its_bound_defers_on_its_own_code_and_calls_a_person`, `tests/test_adapters.py::test_a_snapshot_says_whether_its_own_timeline_was_cut`, `adapters/facts.py`, `kernel/derive.py`, `kernel/decide.py`, mutant: "a cut timeline calls no one" |
