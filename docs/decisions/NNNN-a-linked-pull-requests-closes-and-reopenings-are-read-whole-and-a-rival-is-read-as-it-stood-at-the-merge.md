# NNNN. A linked pull request's closes and reopenings are read whole, and a rival is read as it stood at the merge

Status: accepted. The Factory Builder's ruling of 2026-11-09 on "Facts: a linked pull request's close and reopening, so that row 1 reads a rival as it stood at the merge" (issue 672). It adds to `docs/decisions/0174-two-pull-requests-linked-by-hand-before-an-issues-merge-leave-it-held-and-its-type-changes-are-read-whole.md`, and closes the point that record left open: a rival's close read as it stands now. It amends nothing else.

## Decision

| What | Decided | Because |
|---|---|---|
| The fact | Each linked pull request in `issue-facts/1` carries `close_events`: each close of it and each reopening on its own timeline, with its time, in the timeline's order. A merge raises a close too, at the merge. Each changes whether it is closed, so the two alternate and the first is a close; none comes before it opened; and the last is its close now, a close at its `closed_at`, or none and open. One that cannot be read, or breaks that order, defers, `linked_unreadable`; two in one second, in order, are read | GitHub clears `closed_at` when a pull request is reopened, so the field alone says nothing of a close before. `trials/P-48.json` shows a canary pull request closed, reopened, closed and reopened, and merged, each its own timed event, the merge's close among them. An unreadable fact never yields an action |
| A rival at the merge | Row 1 reads a pull request as closed before the first merge's second where its last close or reopening before that second is a close. A close in that second is no close before it, as before. A rival closed before the merge and reopened after it stood closed at it, so it is no second link, and the reopening moves no done issue | Done to held by a reopening after the merge was a change the issue Lifecycle does not declare, open to anyone who can reopen a pull request (record 0174, "What carries no time") |
| Grounding | The reading waits on a trial: P-48's row in section 6 does not ask it, though its fixture shows it. P-61's row now asks it, and its planned run is to read the pull requests' own timelines too. The rule is `a_pull_requests_close_and_reopening_are_timed` in `sim/grounding.py` | A rule is grounded only by a trial whose row asks it |

## Why

Record 0174 read a rival as closed before the merge from its `closed_at`, which GitHub clears on a reopening. A pull request's own timeline gives each close and reopening with its time, so the Kernel reads how it stood at the merge, as it already does for a link by hand.

## Boundaries

| Boundary | Check |
|---|---|
| Each linked pull request carries its closes and reopenings, each with its time, in the timeline's order, alternating, the first a close, none before it opened, the last its close now; one that cannot be read, or breaks that order, defers | `tests/test_issue.py::test_an_unreadable_linked_pull_request_defers`, `kernel/issue.py`, `schemas/issue-facts.schema.json`, mutant: "a pull request's close events are not read", mutant: "close events that are no list are read", mutant: "a close event may be anything", mutant: "the first close event may be a reopening", mutant: "a close may come before the pull request opened", mutant: "close events may be out of order or repeat the last", mutant: "an open pull request may end on a close", mutant: "a closed pull request need not end on its close", mutant: "a close at another time than closed_at is read" |
| A rival closed before the first merge's second, reopened after it, is no second link at it, and the issue stays done; one closed and reopened before it stood open, and keeps the issue held; one closed in that second is no close before it | `tests/test_issue.py::test_two_links_by_hand_before_the_merge_leave_the_issue_held`, `kernel/issue.py`, mutant: "a rival's close is read as it stands now", mutant: "a reopening before the merge leaves the rival closed", mutant: "a pull request closed before the merge is a link at it", mutant: "a pull request closed in the merge's second is no link at it" |
