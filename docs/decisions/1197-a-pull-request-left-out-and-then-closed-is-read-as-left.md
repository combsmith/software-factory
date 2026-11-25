# 1197. A pull request left out and then closed is read as left

Status: accepted. 2026-11-25, the Factory Builder; issue 1194. Extends decisions 1045 and 1193: 1045's Limits line, and the paragraph after 1193's, end here.

## Decision

A pull request the last pass left out, by any code, and no longer listed open is read as newly left, and stamped. So is one it decided, and an issue it left out (issue 916). `controller/__main__.py` (`writes_seen`) holds the exact form.

Limits: an entry left out that names no item, or names an issue, is no pull request that left. A pull request left out and still listed open is read open. The item's repository is not compared with the home, as for one decided or an issue: a pass serves one repository (decision 1193).

## Why

A pull request left out of the last pass, its facts unanswered or moved twice, is in neither its decided pull requests nor its owed. Closed before the next pass, no pass read it as left. A Factory write on it after its last read was never reconciled, and its hand approvals and taken heads stayed for good. The Claude review and the security read of pull request 1193 found it.

## Boundaries

| Boundary | Check |
|---|---|
| A pull request the last pass left out, no longer listed, is read as left and stamped; one still listed is read open; a left-out issue is no pull request | `tests/test_controller.py::test_a_pull_request_left_out_and_closed_before_the_next_pass_is_read_as_left`, `controller/__main__.py`, mutant: "a pull request left out is not read as left" |
| What an older record alone left out is not read as left | `tests/test_controller.py::test_a_pull_request_left_out_and_closed_before_the_next_pass_is_read_as_left`, `controller/__main__.py`, mutant: "the oldest record's left out are read as left" |
