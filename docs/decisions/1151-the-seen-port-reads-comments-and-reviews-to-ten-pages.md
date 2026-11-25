# 1151. The seen port reads comments and reviews to ten pages

Status: accepted. Extends decision 0234 with its bound on the seen port's lists of comments and reviews, as "adapters: bound a pull request's timeline and seen-issue reads by pages" (issue 1009) asks, part 3 of 4, as the Factory Builder ruled on 2026-11-20. Decision 0234 stands as it is.

## Decision

| What | Decided | Because |
|---|---|---|
| The seen port's comments and reviews | The seen port reads an item's comments, which GitHub gives as updated from `since` on, the reviews of an item that left, which GitHub lists in the order they were started, and the timelines it reads itself, an issue's and that of a pull request that left, to ten pages; past them what was seen is short, and a reviews list the snapshot cut stays short | Anyone can comment on or review an item, and the seen port read each list whole on every pass (the Claude and security reads of the pull request part, decision 1150) |

## Why

Decisions 1149 and 1150 bound the facts port's reads of a pull request. Reconciliation's seen port read each item's comments, and the reviews of an item that left, whole on every pass, and anyone can comment or review: this part bounds those lists too, and a list past its bound leaves what was seen short.

## Boundaries

| Boundary | Check |
|---|---|
| The seen port reads the comments, the reviews of an item that left, and the timelines it reads itself, an issue's and that of a pull request that left, to ten pages: ten that end there are whole; a tenth that names an eleventh is short, and the eleventh is not asked | `tests/test_reconcile.py::test_a_list_is_read_to_ten_pages_and_past_them_what_was_seen_is_short`, `tests/test_reconcile.py::test_what_a_later_page_holds_is_seen_and_a_cut_snapshot_is_short`, `tests/test_reconcile.py::test_a_long_timeline_is_read_from_its_end_back_to_since`, `tests/test_reconcile.py::test_a_read_from_the_end_is_short_on_what_it_cannot_tell`, `adapters/seen.py`, mutant: "the seen port reads the comments past ten pages", mutant: "a reviews list the snapshot cut is seen whole", mutant: "an issue's timeline is read from its start", mutant: "an item that left has its timeline read from its start" (those timelines are read from their end, decision 1152) |
