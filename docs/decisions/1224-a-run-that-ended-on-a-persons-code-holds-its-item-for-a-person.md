# 1224. A Run that ended on a person's code holds its item for a person

Status: accepted. 2026-11-26, the Solution Architect; issue 838. Extends decisions 0003, 0188 and 0201, and the push port's `WHOSE` (pull request 1222).

## Decision

`outcome/1` gains the fault `person`: the Run ended on a code only a person can mend. The code itself stays in the outcome's `reason`, for the notice. The Kernel reads the fault, never the code; the push port's `WHOSE` says which codes are a person's.

Where the Role whose Run is wanted last ended `person`, among its Runs since a writer acted, passing over one superseded or cancelled with no outcome, the item is held as `run_needs_person` and calls a person (`kernel/decide.py`, `kernel/issue.py`, `needs_person` in `kernel/derive.py`). It is read before the brakes, an issue's implementing rounds among them, so a Pause leaves it standing. Design section 3.10 gains the fault. A writer's action releases it, as it renews `attempts_exhausted`. A person is asked what `attempts_exhausted` asks (`config/feed.json`).

`kernel/brakes.py` is unchanged. A Run that ended `person` is no attempt and no Run that spent no model. It reached a model, so it counts toward the Run ceiling, the cost ceiling.

Limits: only the Role's latest Run is read, so a later Run of that Role ending otherwise lifts the Hold. Of two started in its latest second, either one that ended `person` holds. No Factory code writes `person` until the Harness's push step does.

## Why

A file the port will never be given fails every attempt alike. As the environment's it would pause the Factory; as the item's it would spend attempts that cannot succeed. A new fault keeps every existing count as it was, so no brake reads a person's code.

## Boundaries

| Boundary | Check |
|---|---|
| A Role whose latest Run ended `person` holds the pull request for a person, under a Pause too; any other fault admits the next Run | `tests/test_decide.py::test_a_run_that_ended_person_holds_the_item_and_calls_a_person_and_spends_no_attempt`, `kernel/decide.py`, mutant: "a Run that ended person is run again" |
| The same on an issue | `tests/test_issue.py::test_an_issues_run_that_ended_person_holds_the_issue_and_calls_a_person_and_spends_no_attempt`, `kernel/issue.py`, mutant: "an issue's Run that ended person is run again" |
| Only the Role's latest Run since a writer acted is read | `tests/test_decide.py::test_a_run_that_ended_person_holds_the_item_and_calls_a_person_and_spends_no_attempt`, `kernel/derive.py`, mutant: "the Role's first Run is read in place of its latest" |
| The brakes count it no attempt and no Run that spent no model, but toward the Run ceiling | `tests/test_decide.py::test_a_run_that_ended_person_holds_the_item_and_calls_a_person_and_spends_no_attempt`, `kernel/brakes.py`, mutant: "a Run that ended person is an attempt" |
| The records port keeps a person's fault as it keeps every fault `outcome/1` names | `tests/test_adapters.py::test_an_outcome_is_read_once_and_kept_by_its_run_and_attempt`, `adapters/records.py`, mutant: "a person's fault is read again each pass" |
| The Hold stands beside any Run in flight, such as one a pass reading the list late admitted (issue 1223) | `tests/test_decide.py::test_a_run_that_ended_person_holds_the_item_while_another_run_is_in_flight`, `kernel/decide.py`, mutant: "a Run that ended person is run again beside a Run in flight" |
| The same on an issue | `tests/test_issue.py::test_an_issues_run_that_ended_person_holds_the_issue_while_another_run_is_in_flight`, `kernel/issue.py`, mutant: "an issue's Run that ended person is run again beside a Run in flight" |
| The pull request world ends some Runs `person` and reaches the Hold | `tests/test_simulator.py::test_the_seeds_end_a_run_on_a_persons_code`, `sim/world.py`, mutant: "the world never ends a Run on a person's code" |
| Neither world admits or starts a Run of a Role its own reading holds for a person | `tests/test_simulator.py::test_the_world_breaks_on_a_run_started_for_a_role_held_for_a_person`, `tests/test_issue_simulator.py::test_the_issue_world_breaks_on_a_run_admitted_or_started_for_a_role_held_for_a_person`, `sim/world.py`, mutant: "the world holds no Role for a person" |
| The issue world ends some Runs `person` and reaches the Hold, which a record's expiry also ends | `tests/test_issue_simulator.py::test_the_seeds_end_a_run_on_a_persons_code`, `sim/issues.py`, mutant: "the issue world never ends a Run on a person's code" |
