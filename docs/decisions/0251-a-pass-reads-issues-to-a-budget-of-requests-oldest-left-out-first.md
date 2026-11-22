# 0251. A pass reads issues to a budget of requests, oldest left out first

Status: accepted. Extends decision 0234 with its part 3 for "Once issues are served, each touched open issue is re-read every pass with no budget of its own, and a short list stops the whole pass" (issue 849): the budget and the order, as the Factory Builder ruled on 2026-11-19 and the Solution Architect on 2026-11-21. Decision 0234 gains only the Boundary rows that say which of its rows are held. The rows below restate 0234's where this part widens them

## Decision

| What | Decided | Because |
|---|---|---|
| What the budget counts | Every issue request a pass sends, answered or not, and the account reader's permission reads for the issues among them | A permission read is a request that a login acting on an issue makes the pass send (decision 0250) |
| Which first | Those the last record left out by the budget, in the order it left them out, once each and only while listed; then the rest in the listing's order | Derived from the record before alone, which a replay holds |

## Why

Decision 0234 decides a budget of issue requests a pass and an order that leaves no issue out for good. This part builds both. The short list is decision 0252's, and passing over a record whose list was read short is decision 0253's.

## Boundaries

| Boundary | Check |
|---|---|
| The issue reads a pass sends, the account reader's permission reads for them among them, are counted as sent, answered or not, and once `max_issue_requests` are spent no further read starts: each issue not read is left out as `issue_budget`, by its item. A read begun finishes, and every pass reads one issue at least. Those the last record left out by the budget are read first, in the order it left them out, once each and only while listed, an issue alone, each number as often as the listing gives it, then the rest in the listing's order; so, the list unchanged, every issue is read in every run of as many passes as the budget's fit goes into the list. A last record with no left out entries, or none by the budget, gives the listing's order. `max_issue_requests` is a whole number of one or more, 100 in `config/controller.json` | `tests/test_controller.py::test_the_issue_reads_stop_at_the_passs_budget_and_those_left_out_by_it_are_read_first_by_the_next`, `controller/__main__.py`, `controller/pass_.py`, `config/controller.json`, `examples/invalid/controller.a-budget-of-no-issue-request.json`, mutant: "the issues' budget is never spent", mutant: "the issues' budget is spent a request late", mutant: "the issue reads are not counted", mutant: "an issue request that fails is not counted", mutant: "the issues are read in the listing's order", mutant: "the issues are read in the listing's order whatever the budget left out", mutant: "those the budget left out are read in the listing's order", mutant: "any issue left out is read first", mutant: "a pull request the budget left out is read first as an issue", mutant: "a number listed twice and owed is read once", mutant: "the issues' permission reads are not counted" |
| An issue the budget left unread is kept in the record by its code, the issues' alone: it raises its own alert once a pass, `issue_budget_spent`, and not the alert of facts unread, which a fault beside it still raises. A pull request's entry with that code is facts that are not facts | `tests/test_controller.py::test_an_issue_left_unread_by_the_budget_raises_its_own_alert_and_no_other`, `controller/pass_.py`, `controller/reads.py`, mutant: "an issue left unread by the budget is facts that are not facts", mutant: "a pull request may be left out by the issues' codes", mutant: "an issue left unread by the budget is a fault of the facts", mutant: "an issue left unread by the budget raises no alert of its own" |
