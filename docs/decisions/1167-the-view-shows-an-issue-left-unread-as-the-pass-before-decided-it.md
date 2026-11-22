# 1167. The view shows an issue left unread as the pass before decided it

Status: accepted. 2026-11-19, the Factory Builder (ruling B3); issue 849, split from pull request 1128 to fit its size bound. Extends decision 0234.

## Decision

An issue a pass left unread for want of a read alone, its budget spent or its issue list read short, stays in the view. It is shown as the record before decided it, one pass deep (`carried` in `controller/feed.py`). Its age passes over such passes, so a leftover does not restart its time in its State. An issue the pass decided, or left out by name for any other reason, is not carried, nor is any pull request. A rebuild from the records shows the same view.

Limits: the view carries an issue one pass deep, so one left unread two passes in a row is missing from it for the second. An issue's age reaches back only as far as the records the pass has at hand.

## Why

Before the budget of decision 0251, a short list stopped the whole pass and the old view stood. With the pass now going on past a short list (decision 0252), an issue it left unread would drop out of the view for that pass. One pass deep means the carry reads only the record before, so a rebuild from the records gives the same view.

## Boundaries

| Boundary | Check |
|---|---|
| An issue left unread by the budget or a short list is shown as the record before decided it, and a rebuild shows the same | `tests/test_controller.py::test_an_issue_left_unread_by_the_budget_or_the_list_is_shown_as_the_pass_before_decided_it`, `controller/feed.py`, mutant: "the view carries no issue left unread" |
| An issue left out for another reason is not carried, nor one beside the issue the budget left out | `tests/test_controller.py::test_an_issue_left_unread_by_the_budget_or_the_list_is_shown_as_the_pass_before_decided_it`, `controller/feed.py`, mutant: "an issue beside one the budget left out is carried too" |
| A short list carries no issue the pass decided, or left out by name for another reason | `tests/test_controller.py::test_an_issue_left_unread_by_the_budget_or_the_list_is_shown_as_the_pass_before_decided_it`, `controller/feed.py`, mutant: "an issue's own code gives way to a list read short" |
| An issue's age passes over passes that left it unread; a pull request a pass missed beside a short list starts its age again | `tests/test_controller.py::test_an_issue_left_unread_by_the_budget_or_the_list_is_shown_as_the_pass_before_decided_it`, `controller/feed.py`, mutant: "an issue's age stops at a pass that left it unread" |
