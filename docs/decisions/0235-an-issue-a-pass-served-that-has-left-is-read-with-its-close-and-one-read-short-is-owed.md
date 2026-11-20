# 0235. An issue a pass served that has left is read with its close, and one read short is owed

Status: accepted. The Factory Builder's ruling of 2026-11-19 on "A Factory write on an issue that closes before the next pass is never reconciled: issues that left are read" (issue 916), part b: `pass/1`'s reconciliation carries `left_issues` and `owed_issues`, optional, and a pass that could not list the issues carries those it served as owed, with reconciliation short. It completes decision 0230, whose row on an issue that left waited on this. It is built in two parts: the carry and the seen port's close of an issue first, then the pass's reading of which issues left, which fills that row; each part adds its rows below.

## Decision

| What | Decided | Because |
|---|---|---|
| Which issues have left | Those the pass before served, decided or left out unread, and those owed, that the issues this pass serves no longer hold. The listing is of open issues alone, so one not in it has closed, or left the served set | Derived from the record before and this pass's listing alone, as the pull requests that left are (decision 0063): nothing is stored apart |
| How one is read | As a pull request that left is: its timeline and its comments in the window, by the seen port, whole only with its close in the window; one a pass before read as left, inside the window, is read as gone, any close of it standing; past the window it is read no more. A merge is no issue's close | So a Factory label, comment or close on an issue that closed before the next pass is matched, or is the alert, `write_unmatched`, as "write_unmatched clears once the pull request it names leaves the open set, so a machine-user write nobody matched closes its own alarm" (issue 787) asked of a pull request |
| What is carried | Each issue first read as left is stamped in `left_issues`, as `left` stamps a pull request; each that left and could not be read whole is in `owed_issues`, and read again. An open issue served now and read short is not owed: the next pass reads it, served or left | A record with neither carries neither, as one written before them |
| A pass that could not list them | Where the tracking issue's number was not read, the issues' Apps could not be told, or issues are not served, none has left that can be told: every issue served before, owed or kept as left is owed again, none is read, and reconciliation is short. With nothing to owe, nothing is short | An issue not listed for want of a listing is not one that closed |

## Why

Before this, closing an issue was a silent way out of reconciliation for every Factory identity: a write on an issue that closed before the next pass, and the close itself, were never read.

## Boundaries

| Boundary | Check |
|---|---|
| An issue read as left is whole only with its close, in the window, or any once gone; a merge is no issue's close; an open one needs none | `tests/test_reconcile.py::test_an_issue_that_left_is_read_with_its_close`, `adapters/seen.py`, mutant: "an issue that left is read with no close", mutant: "a merge closes an issue that left" |
| Reconciliation carries the issues owed, read until they have been, and those read as left, stamped when first read so and kept until the window passes them; a record with neither carries neither, as one written before them; the pass hands what its reads owe and read as left to its record | `tests/test_reconcile.py::test_the_issues_owed_and_left_are_carried_as_the_pull_requests_are`, `tests/test_controller.py::test_the_pass_carries_the_issues_its_reads_owe_and_read_as_left`, `controller/reconcile.py`, `controller/pass_.py`, mutant: "the issues owed are not carried", mutant: "the issues read as left are not stamped", mutant: "an issue that leaves again keeps its first stamp too", mutant: "an issue kept as left is never dropped by the window", mutant: "the issues owed before are not read", mutant: "the issues kept as left are read past the window", mutant: "the pass carries no issue left unread", mutant: "the pass stamps no issue as left" |
