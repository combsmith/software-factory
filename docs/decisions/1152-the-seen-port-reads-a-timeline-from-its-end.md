# 1152. The seen port reads a timeline from its end

Status: accepted. Extends decision 0234, as "adapters: bound a pull request's timeline and seen-issue reads by pages" (issue 1009) asks, part 5 of 5, as the Factory Builder ruled on 2026-11-20 (A, with its guard). It narrows decision 1151's first Boundary row: the timelines the seen port reads itself are read from their end, not to ten pages from their start. Decisions 0234, 1150 and 1151 stand otherwise.

## Decision

| What | Decided | Because |
|---|---|---|
| A timeline read from its end | The seen port reads an issue's timeline, an item's that left, and one the snapshot cut, from its end (`_tail` in `adapters/seen.py`; trials/P-43.json), back to `since` or its first page, in ten pages at most. The last page, and a joined first page, are read again; one that changed leaves the read short. One read as gone is read back to its close | A timeline's new writes, and an item's close, are at its end |

## Why

Decisions 1150 and 1151 cut lists at ten pages from their start, so a cut timeline would never give its newest writes again. The seen port reads its timelines from their end instead.

## Boundaries

| Boundary | Check |
|---|---|
| The seen port reads a timeline from its end, never asking the pages between; what it cannot tell, or a page that changed when read again, leaves it short; a timeline the snapshot cut is read again, one it did not cut is not | `tests/test_reconcile.py::test_a_long_timeline_is_read_from_its_end_back_to_since`, `tests/test_reconcile.py::test_a_read_from_the_end_is_short_on_what_it_cannot_tell`, `tests/test_reconcile.py::test_a_read_from_the_end_holds_its_edges`, `tests/test_reconcile.py::test_an_event_that_lands_while_the_end_is_read_leaves_it_short`, `tests/test_reconcile.py::test_a_timeline_the_snapshot_cut_is_read_again_from_its_end`, `tests/test_adapters.py::test_a_snapshot_says_whether_its_own_timeline_was_cut`, `adapters/seen.py`, mutant: "an item that left has its timeline read from its start", mutant: "a joined first page is not read again", mutant: "a list the snapshot cut is not read again" |
| Limit: more than about six pages of a list since `since`, some six hundred events in a pass's window, leave reconciliation of that item short for that pass; and the bracket marks a read short whenever an event lands while it is read, which the next pass reads again | `tests/test_reconcile.py::test_a_long_timeline_is_read_from_its_end_back_to_since`, `tests/test_reconcile.py::test_an_event_that_lands_while_the_end_is_read_leaves_it_short`, `adapters/seen.py`, mutant: "the pages read back have no bound" |
| An item read as gone is read from its end back past `since`, within the same ten pages, until its close is found, so a close older than the events after it is read; one that left is read back to `since` alone; a close past the bound is short | `tests/test_reconcile.py::test_an_item_read_as_gone_is_read_back_to_its_close`, `adapters/seen.py`, mutant: "an item read as gone is read back to since alone" |
