# 0002. State is derived and never stored

Status: accepted. Source: decision 2 of `docs/architecture/adr/0013-factory-mvp-reference-architecture.md`,
as it stood on 2026-10-11. That file records how this was reached; this one is the rule.

## Decision

Each type of Work item has one Lifecycle, held as data under `lifecycle/`. A Work item's State is
computed at every evaluation from two things GitHub holds: the facts of the item, and the records
of the Factory's own Runs. There is no second store. Labels are the human's input vocabulary. The
control room is a view that the Factory writes and never reads.

## Why

A stored copy of State can only go stale, and the proof of concept's worst faults were copies that
disagreed with GitHub. If a pass is lost, the next one reaches the same answer.

## Boundaries

| Boundary | Check |
|---|---|
| One function derives State, and the Kernel keeps nothing between calls | `tools/check_purity.py`, `tests/test_decide.py::test_the_same_inputs_give_the_same_decision` |
| Every transition the Factory makes is declared in the Lifecycle | `tests/test_simulator.py::test_invariants_hold_under_faults` |
| The Lifecycle terminates, and every cycle is bounded or passes through a person | `tools/check_lifecycle.py` |
| No text written by a third party reaches the Kernel: facts carry no prose | `examples/invalid/facts.carries-prose.json`, `tools/check_examples.py` |
| Facts say whether they are complete; incomplete facts never converge and never admit | `examples/invalid/facts.no-completeness.json`, `tests/test_decide.py::test_incomplete_facts_never_converge_or_admit` |
| No decision reads the control room: the Kernel is given facts, run records, context, configuration and the time, and nothing else | `tests/test_decide.py::test_admission_is_given_facts_and_never_an_event` |
| Every decision can be replayed from what was recorded | `tools/make_corpus.py` |
| A view rebuilt from GitHub equals the view updated pass by pass | waiting on `controller/` |
| The status on a Work item is rewritten only when the decision changes | waiting on `harness/` |
