# 1149. A pull request whose own timeline is cut waits on a person

Status: accepted. Extends decision 0234 with its rule for a pull request's own timeline, as "adapters: bound a pull request's timeline and seen-issue reads by pages" (issue 1009) asks, part 1 of 4: the Kernel's rule and the fact it reads, as the Factory Builder ruled on 2026-11-20 (the fact optional, absent read as not cut, as decision 1147's). The facts port bounds the reads in part 2. Decision 0234 stands as it is.

## Decision

| What | Decided | Because |
|---|---|---|
| A cut timeline | `timeline_bounded` in `facts/1` says the facts port cut the pull request's own timeline at its bound. The port gives it in every snapshot, false until it bounds those reads, in the part after this one. Absent, it is not cut, and a value that is no truth value is a gap in the timeline. The Kernel defers a pull request so cut on that reason, the issues' own, after a cut acceptance read and before any list read short, whatever `complete.timeline` claims, and calls a person; a queued one is taken out | Anyone can comment on or review an open pull request, and a timeline past its bound never mends: read short and said no more, it would wait in silence (the Claude and security reads of the acceptance port's bound). The cut acceptance read is said first: the issue it names is what a person can mend |

## Why

The facts port reads a pull request's whole timeline and its reviews every pass, and anyone can comment on or review an open pull request. Once those reads are bounded, a cut must not leave the pull request waiting in silence: this part gives it the issues' own reason, `timeline_bounded`, which defers it and calls a person, after a cut acceptance read.

## Boundaries

| Boundary | Check |
|---|---|
| A pull request whose own timeline was cut defers on `timeline_bounded`, after a cut acceptance read and before any list read short, whatever `complete.timeline` claims; it calls a person and leaves the queue. Absent, it is not cut; present and no truth value, it is a gap; merged or closed is what it is | `tests/test_decide.py::test_a_timeline_cut_at_its_bound_defers_on_its_own_code_and_calls_a_person`, `tests/test_adapters.py::test_a_snapshot_says_whether_its_acceptance_read_was_cut`, `examples/invalid/facts.a-cut-timeline-in-words.json`, `kernel/derive.py`, mutant: "a cut timeline defers as any read short" |
| Hands-off is never read past a timeline cut, or a cut flag that is no truth value: a queued pull request is taken out, and nothing is written on it (Muse) | `tests/test_decide.py::test_hands_off_is_not_read_from_a_timeline_read_short`, `tests/test_decide.py::test_an_item_is_left_alone_for_a_persons_hands_off_or_labels_that_cannot_be_read`, `kernel/derive.py`, mutant: "hands-off is read from a timeline cut at its bound" |
| No approval stands past a timeline cut, or a cut flag that is no truth value (Muse) | `tests/test_decide.py::test_an_approval_from_before_a_reopening_never_stands`, `kernel/derive.py`, mutant: "an approval stands on a timeline cut at its bound" |
| The approving act recovers no approval past a timeline cut at its bound, whatever `complete.timeline` claims: it refuses, and the Kernel decides (Muse) | `tests/test_approve.py::test_no_approval_is_recovered_on_a_timeline_read_short`, `harness/approve.py`, mutant: "an approval is recovered on a timeline cut at its bound" |
