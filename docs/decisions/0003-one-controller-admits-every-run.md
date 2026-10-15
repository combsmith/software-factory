# 0003. One Controller admits every Run, from current facts

Status: accepted. Source: decision 3 of `docs/architecture/adr/0013-factory-mvp-reference-architecture.md`,
as it stood on 2026-10-11. That file records how this was reached; this one is the rule.

## Decision

Every Run is admitted by one Controller. It is a poller: one pass evaluates every open Work item
in every repo. An event carries no work; it may only ask for a pass. Hold, budget, duplication
and concurrency are evaluated in the admission function and nowhere else. A Pause is evaluated
there and, before any Factory code runs, by the platform. A Run is
started only from a Decision that a pass recorded.

## Why

The platform loses events, so work found by reading current facts cannot be lost with one. A
single decider has no race to lose and one place for every brake.

## Boundaries

| Boundary | Check |
|---|---|
| The admission function takes no event payload | `tests/test_decide.py::test_admission_is_given_facts_and_never_an_event` |
| At most one Run is active per Work item, counting one still waiting for a runner | `tests/test_decide.py::test_one_writer_per_item`, `tests/test_simulator.py::test_invariants_hold_under_faults` |
| An outside item gets no Run until the Maintainer admits it, and admission lapses on the next push | `tests/test_decide.py::test_outside_item_gets_no_run_until_admitted`, `tests/test_decide.py::test_admission_lapses_on_the_next_push` |
| Attempts are counted since the last action by a person with write access | `tests/test_decide.py::test_a_writers_action_grants_a_fresh_allowance` |
| A fault of capacity or of the environment is not an attempt | `tests/test_decide.py::test_capacity_and_environment_faults_are_not_attempts`, `tests/test_decide.py::test_an_approval_that_fails_for_capacity_or_environment_is_not_an_attempt` |
| An approval is a Run with no Engine. One that does not land is bounded by its attempts, and a writer's action renews them | `tests/test_decide.py::test_an_approval_that_does_not_land_is_bounded`, `tests/test_decide.py::test_an_approval_that_landed_is_enqueued_whatever_failed_before`, `tests/test_simulator.py::test_an_approval_that_never_lands_is_bounded` |
| An approval Run counts toward its own attempts and not toward the Run ceiling, which is the cost ceiling | `tests/test_decide.py::test_an_approval_run_does_not_count_toward_the_run_ceiling` |
| Acts since a person with write access acted are held to `max_acts_per_item`; an unreadable count makes no act | `tests/test_decide.py::test_acts_are_bounded`, `tests/test_decide.py::test_an_unreadable_count_of_acts_makes_no_act`, `examples/invalid/facts.no-count-of-acts.json`, `tests/test_simulator.py::test_a_queue_that_ejects_every_time_is_bounded` |
| The act ceiling stops acts that move work on, and nothing else: a Run is bounded by the Run ceiling, and a Hold is never refused | `tests/test_decide.py::test_the_act_ceiling_stops_acts_and_nothing_else` |
| A dequeue, an act that stops work, is never refused at the act ceiling | `tests/test_decide.py::test_a_dequeue_is_never_refused_at_the_act_ceiling`, not held yet |
| Acts are counted from GitHub's timeline: each approval, enqueue, dequeue and label a Factory identity made, since a person with write access acted | waiting on `adapters/` |
| A missing or unreadable Pause or capacity reading admits nothing | `tests/test_decide.py::test_unreadable_pause_defers`, `tests/test_decide.py::test_an_unreadable_pause_stops_approvals_and_merges`, `tests/test_decide.py::test_unreadable_capacity_defers` |
| Each brake is a rule a test would miss if it were removed | `tools/mutants.py` |
| A Pause stops approvals and merges as well as Runs | `tests/test_decide.py::test_a_pause_stops_approvals_and_merges_too` |
| Under a Pause, a Hold the facts establish is shown first: the approver may not be the author or last pusher | `tests/test_decide.py::test_under_a_pause_a_hold_the_facts_establish_shows_first` |
| A Run's lane is one concurrency group for each Work item, declared on the job, and never cancels what is running | waiting on `harness/` |
| Work is never lost once faults stop | `tests/test_simulator.py::test_work_is_never_lost_once_faults_stop` |
| A run record counts only if it is the Factory's own workflow, on the default branch, started by a schedule or a dispatch | waiting on `adapters/` |
| A human Pause holds even when Factory code is broken; a Run ceiling is enforced outside `kernel/` | waiting on `controller/` |
| One workflow, the one that carries a Run, is the only one that references an LLM credential | waiting on `harness/` |
