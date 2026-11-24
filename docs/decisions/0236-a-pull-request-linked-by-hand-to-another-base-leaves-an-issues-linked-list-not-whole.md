# 0236. A pull request linked by hand to another base leaves an issue's linked list not whole

Status: accepted. The Factory Builder's ruling of 2026-11-19 on "A Factory write on an issue that closes before the next pass is never reconciled: issues that left are read" (issue 916), part a, from a read of the keyword spans' last pull request, and the Builder's acceptance of trial P-69 the same day. It amends decision 0028's reading of a pull request to another base, which `trials/P-33.json` grounds, for a link made by hand.

## Decision

| What | Decided | Because |
|---|---|---|
| A link by hand on another base | The issues port does not list a pull request whose base is not the default branch, as before (decision 0028); where that pull request is linked by hand now, its last link or unlinking on the issue's timeline a link, the issue's linked list is not whole | GitHub keeps a link by hand, and its closing reference, when the pull request's base moves to another branch: the ConnectedEvent stands with no DisconnectedEvent, and `closedByPullRequestsReferences` still names it (`trials/P-69.json`), unlike P-33's keyword reference. Two links by hand before a merge, one merged and the other moved to another base, all before the first pass that holds the issue, would read `merged` where `merged_while_held` is due once closed issues are read. A pull request a pass saw is caught already by its move (decision 0218); this catches one linked before any pass |
| One unlinked | A pull request unlinked by hand, its last link or unlinking an unlinking, to another base, leaves the list as it was | It is no link now, and its close names nothing |
| The cost | An issue with a pull request linked by hand to another base defers on its linked list read short until the link is undone or, while that pull request is open, its base is the default again; one closed or merged into another base, as a stacked pull request is, keeps it deferred until it is unlinked. The deferral is the plain one, `facts_incomplete`, which calls no one and names no pull request | Its pull requests cannot be read as the Lifecycle reads them. Only a person with write access links by hand, so one can unlink it, but nothing tells them to: a code of its own that calls a person is left for later |

## Why

Once closed issues are read, by that issue's part b, a rival linked by hand and moved to another base before any pass would be read as no rival at all. The trial showed the link outlives the move, so the port can see it and refuse to read the list whole.

## Boundaries

| Boundary | Check |
|---|---|
| A pull request to another base is not listed; linked by hand now, its last link or unlinking a link, it leaves the list not whole, the last in the timeline's order read, never the first nor the latest by time; unlinked, or never linked, it leaves the list as it was | `tests/test_adapters.py::test_only_a_pull_request_to_the_default_branch_is_listed_as_linked`, `adapters/linked.py`, mutant: "a pull request linked by hand to another base leaves the list whole", mutant: "a pull request unlinked by hand to another base leaves the list not whole", mutant: "a referenced pull request linked by hand to another base leaves the list whole", mutant: "a pull request linked by hand and done on another base leaves the list whole", mutant: "the first link by hand is read, not the last", mutant: "a link by hand made again after its unlink is not read", mutant: "the link by hand read is the latest by time, not the last in order" |
