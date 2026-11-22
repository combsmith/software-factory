# 0252. A short issue list reads no issue and stops no pass

Status: accepted. Extends decision 0234 with its part 4 for "Once issues are served, each touched open issue is re-read every pass with no budget of its own, and a short list stops the whole pass" (issue 849): the short list, as the Factory Builder ruled on 2026-11-19 and the Solution Architect on 2026-11-21. Decision 0234 gains only the Boundary row that says its row is held

## Decision

| What | Decided | Because |
|---|---|---|
| What a short list serves | No issue: the one entry it leaves out names no item, so no issue's writes are read for it. No issue that left can be told either, so every issue served, owed or kept as left before is owed again, as decision 0235 owes them where the issues were not listed, and an issue the short list gave is no tracking issue told at its own read | An entry with no item is no issue that left, and a list read short may miss any issue still open |

## Why

Decision 0234 decides that an issue list read short refuses the issues alone and never stops the pass. This part builds it, after decision 0251's budget; passing over a record whose list was read short is decision 0253's.

## Boundaries

| Boundary | Check |
|---|---|
| An issue list read short, or not answered, no longer stops the pass: no issue is read, the pull requests are decided, and the record leaves out one entry naming no item, `issue_list_unreadable`, with its alert, once a pass, and not the alert of facts unread. Issues whose Apps cannot be told are still listed with no date, and none is read | `tests/test_controller.py::test_the_open_issues_are_listed_from_served_from_and_each_read_as_a_pull_request_is`, `tests/test_controller.py::test_a_queues_or_a_lenss_name_declared_as_an_issues_app_refuses_the_issues_alone_and_the_pull_requests_are_decided`, `tests/test_controller.py::test_an_issue_list_read_short_raises_its_own_alert_and_no_other`, `controller/__main__.py`, `controller/pass_.py`, mutant: "an issue list read short stops the pass", mutant: "an issue list read short leaves nothing out", mutant: "an open issue list read short is decided from", mutant: "issues whose Apps cannot be told are listed", mutant: "a list read short serves its itemless entry", mutant: "the issue list read short raises the budget's alert" |
| A list read short tells no issue that left: every issue served before, one it listed too, is owed, none is read, and reconciliation is short | `tests/test_controller.py::test_an_issue_that_left_is_read_with_its_close_and_one_read_short_is_owed`, `controller/__main__.py`, mutant: "a list read short tells the issues that left", mutant: "an issue a list read short gave is told as the tracking issue" |
