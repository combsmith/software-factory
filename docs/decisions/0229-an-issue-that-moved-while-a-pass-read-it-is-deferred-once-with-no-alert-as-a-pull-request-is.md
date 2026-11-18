# 0229. An issue that moved while a pass read it is deferred once with no alert, as a pull request is

Status: accepted. The Factory Builder's ruling of 2026-11-13 on S3 PR3, ruling (a), held by "A moved issue gets a pull request's one-pass grace, restating 0172's boundary row" (issue 839).

## Decision

| What | Decided | Because |
|---|---|---|
| The grace | An issue the pass left out as `pull_moved`, and which the last pass record read did not leave out as `pull_moved`, is deferred with no alert: no facts, no Decision and no act, and not `facts_unreadable`. The next pass reads it again | Decision 0172 kept the grace for pull requests while no pass read an issue. Since the pass reads the issues port, an issue that changes during its read is left out as moved (decision 0218). Once issues are served, every edit, label or comment made during a read would open the tracking issue, which is the noise 0172 was written to stop |
| What still alerts at once | An issue that moved twice in a row. Any other code on an issue. A last record that cannot be read, is not there, or holds no `left_out`, as for a pull request | An issue that never settles still reaches a person, and a pass fails closed |
| Whose move | A move is its item's own, by its page: an issue and a pull request of one number are two items, and one's move in the last pass is no second move of the other's | GitHub numbers issues and pull requests in one sequence, so today no two share a number; the rule does not lean on that |
| The code | The record keeps the issue's move under the code `pull_moved`, as `pass/1` names a read that moved while it was read | A second code would change `pass/1` for a name alone; the item's type says which it is |
| Derived, never kept | Whether an issue's move is a first is read from the last pass record, by `controller/pass_.py`'s `moved_once`, as a pull request's is | State is derived from facts and run records at every call, never stored |
| Not here | The entry owes a pull request's writes to the next pass after a first move. It reads no writes on issues yet, so nothing is owed for one: that is issue 837's, "The Controller's writes on issues are reconciled before issues are served" | Reconciliation of issue writes is not built, and this record adds none |

## Why

A moved read means "read it again", for an issue as for a pull request. This restates one clause of decision 0172, "A pull request that moved while a pass read it is deferred once with no alert": where 0172's Decision and its first boundary row say that an issue left out as moved is the alert, this record's row holds instead, and 0172's mutant for that clause is replaced by this record's. Nothing else of 0172 changes. The grace costs one pass of delay, twenty minutes at most, and keeps the alert for what does not settle. Without it, turning issues on would make the tracking issue open on ordinary work.

## Boundaries

| Boundary | Check |
|---|---|
| An issue that moved once is deferred with no alert, and its record keeps it under `pull_moved`. One that moved twice in a row is the alert. An issue's move in the last pass is no second move of a pull request of its number, nor a pull request's of an issue. An issue that moved twice beside a pull request that moved once is the alert. Any other code on an issue is the alert at once | `tests/test_controller.py::test_a_pull_request_that_moved_while_read_is_deferred_once_with_no_alert`, `controller/pass_.py`, mutant: "an issue that moved once is the alert", mutant: "an issue that moved twice in a row earns the grace again", mutant: "an issue's move in the last pass counts against a pull request of its number" |
