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
| A fault of capacity or of the environment is not an attempt | `tests/test_decide.py::test_capacity_and_environment_faults_are_not_attempts` |
| A missing or unreadable Pause or capacity reading admits nothing | `tests/test_decide.py::test_unreadable_pause_defers`, `tests/test_decide.py::test_an_unreadable_pause_stops_approvals_and_merges`, `tests/test_decide.py::test_unreadable_capacity_defers` |
| Each brake is a rule a test would miss if it were removed | `tools/mutants.py` |
| A Pause stops approvals and merges as well as Runs | `tests/test_decide.py::test_a_pause_stops_approvals_and_merges_too` |
| A Run's lane is one concurrency group for each Work item, declared on the job, and never cancels what is running | waiting on `harness/` |
| Work is never lost once faults stop | `tests/test_simulator.py::test_work_is_never_lost_once_faults_stop` |
| A run record counts only if it is the Factory's own workflow, on the default branch, started by a schedule or a dispatch | waiting on `adapters/` |
| A human Pause holds even when Factory code is broken; a Run ceiling is enforced outside `kernel/` | waiting on `controller/` |
| One workflow, the one that carries a Run, is the only one that references an LLM credential | waiting on `harness/` |
