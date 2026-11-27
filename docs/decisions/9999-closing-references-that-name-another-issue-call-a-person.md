# 9999. Closing references that name another issue call a person

Status: accepted. 2026-11-27, the Solution Architect; issue 1185. Extends decision 1147 with a second acceptance code that calls a person.

## Decision

`closes_another_issue` in `facts/1` says that the closing references of a pull request bound to an issue name another issue. Bound means by its branch and its opening Run (`adapters/acceptance.py`, `bound`). They name another when a reference is of another number or repo, or when GitHub counts more than one. The count needs no page past the first, so a list of more than ten is told too (`another`).

The Kernel defers such a pull request on that code and calls a person; a queued one is taken out. It is read after a cut acceptance read and before a cut timeline or any list read short (`kernel/derive.py`). Absent, the fact is false; a value that is no truth value is a gap in acceptance.

GitHub is taken to list each issue once. The P-33 and P-46 fixtures never show one issue twice, so this is an assumption. If it is wrong, a person is called for nothing.

Limits: a count GitHub has not caught up with, such as a count of one beside no issue, still waits with nobody called until it does. A pull request bound to no issue that closes more than a page of issues waits with nobody called too (issue 1313).

## Why

A bound pull request whose references named another issue was read as not whole, and waited in silence. Its author's description causes it, and no pass mends it. Decision 1147's path does not cover it: that cut is of an issue's timeline, not of this list. A bound on lasting incomplete facts was rejected here: it belongs to every such deferral (issue 1313).

## Boundaries

| Boundary | Check |
|---|---|
| Another issue named defers on its own code, whatever the lists read short claim, calls a person and is taken out of the queue; false, the pull request converges | `tests/test_decide.py::test_a_bound_pull_request_whose_closing_references_name_another_issue_calls_a_person`, `kernel/derive.py`, mutant: "another issue named defers as any read short" |
| It is said after a cut acceptance read and before a cut timeline | `tests/test_decide.py::test_a_bound_pull_request_whose_closing_references_name_another_issue_calls_a_person`, `kernel/derive.py`, mutant: "another issue named is said after a cut timeline" |
| Absent, the fact is false; present and no truth value, it is a gap in acceptance; a value in words is no fact | `tests/test_decide.py::test_a_bound_pull_request_whose_closing_references_name_another_issue_calls_a_person`, `examples/invalid/facts.another-issue-named-in-words.json`, `kernel/derive.py`, mutant: "a named flag that is no truth value is read as none named" |
| Another number, another repo or a count above one names another issue; the bound issue alone, a count not caught up, or a person's pull request, none | `tests/test_adapters.py::test_closing_references_that_name_another_issue_than_the_bound_one_say_so`, `adapters/acceptance.py`, mutant: "a count above one names no other issue" |
| Every snapshot says the fact | `tests/test_adapters.py::test_a_snapshot_says_whether_closing_references_name_another_issue`, `adapters/facts.py`, mutant: "the snapshot leaves out whether another issue is named" |
