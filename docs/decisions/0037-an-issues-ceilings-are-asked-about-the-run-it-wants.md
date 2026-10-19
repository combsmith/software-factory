# 0037. An issue's ceilings are asked about the Run it wants

Status: accepted. Taken as a working ruling for
"Kernel: an issue's ceilings are asked about the Run it wants, not the Run in flight" (issue 171) on 2026-10-19, which
the Maintainer may overturn in review. It decides one paragraph of decision 0031 otherwise: the brakes' Hold on an
issue with a Run in flight is no longer the one they would have made of each Run in flight, asked of its own Intent,
but the one they make of the Run the issue wants.

## Decision

A Run in flight on an issue admits nothing, and nothing it wrote is read until it completes. The attempts and the Run
ceiling are still asked, by `brakes.run_ceilings` on its own and never the Pause, about the Run the issue's State wants,
found as `_decide` finds it with no Run in flight: the same reading of the Intents, the same `_wanted`, and the same
records, in flight or not, so that a Role's comment or label stands in for none of its Runs while one is kept. Only the
completed Runs since a person with write access acted are counted: the Run in flight was admitted under the ceiling.
An issue that wants no Run is not held by them, with a Run in flight or none: in `new`, in review, with a linked draft,
and wherever the Intents or the facts name no Run, as when a person overruled the verdict, the verdict is given, the
statement is missing, an Intent is null or the Intents cannot be read. `kernel/decide.py` and `kernel/brakes.py` are
not edited.

An opening Run in flight shows the issue `in_progress`, row 7, ahead of rows 8 to 10. The Run the issue wants is then
found from the State it has with its opening Runs in flight left out, as `apply` reads the issue with its own Run left
out (I-38): a verdict a person overruled, an acceptance due or an investigation whose attempts are spent is read as
such, and the opening Run is not asked of in its place. The issue still shows `in_progress` while that Run waits,
unless a ceiling holds it. Every other Run in flight is still read: a readiness Run's own `factory:ready` does not count
until that Run completes. The Pause, the model provider's deferral and the org's concurrency then defer a Run, as on a
pull request.

## Why

The Run ceiling is the cost ceiling (FR-39), and §4.1 holds an item at a ceiling only while the action it bounds is
wanted. Asked of the Run in flight, it held an issue that wanted no Run while that Run waited, and the Hold ended with
no person once the Run completed: the Factory leaving `held`, which the issue's Lifecycle gives to a person alone. A
pull request's ceilings are asked of the Run it wants (decision 0003), and `apply` asks the issue's Kernel the same
question with its own Run left out, so the reading while a Run waits is the answer `apply` will get. Only the opening
Run moves the State while it waits, so only it is left out; another Run left out would let what it wrote count.

## Boundaries

| Boundary | Check |
|---|---|
| While a Run is in flight, the attempts and the Run ceiling are asked about the Run the issue's State wants, found as with none in flight, and not about the Run in flight; an issue that wants no Run, or one its configuration or facts cannot name, is not held by them, with a Run in flight or none | `tests/test_issue.py::test_the_ceilings_are_asked_about_the_run_the_issue_wants`, `tests/test_issue.py::test_the_ceilings_are_asked_of_the_intent_wanted_and_not_of_the_one_in_flight`, `tests/test_issue.py::test_the_run_ceiling_holds_no_issue_that_wants_no_run`, `tests/test_issue.py::test_an_issue_in_new_wants_no_run_while_one_waits`, `tests/test_issue.py::test_opening_attempts_are_bounded_and_hold_even_while_an_opening_run_is_in_flight`, `tests/test_transitions.py::test_an_issue_explored_is_held_to_the_issue_lifecycle` |
| An opening Run in flight is left out to find the Run the issue wants, and no other Run in flight is | `tests/test_issue.py::test_an_opening_run_in_flight_is_left_out_to_find_the_run_wanted`, `tests/test_issue.py::test_only_the_opening_run_in_flight_is_left_out_and_what_another_wrote_is_not_read` |
