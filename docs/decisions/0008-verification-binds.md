# 0008. Verification binds

Status: accepted. Source: decision 8 of `docs/architecture/adr/0013-factory-mvp-reference-architecture.md`,
as it stood on 2026-10-11. That file records how this was reached; this one is the rule.

## Decision

The Factory's own verification is a required check from the first commit. It is hermetic: it reads
nothing outside the commit it judges. It is deterministic: randomised exploration runs on a
schedule and blocks nothing. Two commands, `make verify` and then
`python3 -m tools.mutants`, run locally exactly what the required check runs. The Maintainer's own approval never depends on the Factory running.

## Why

A check that is not required is advice, and a check that can fail at random stalls every merge
until someone learns to ignore it. When the Release that serves the Factory is broken, a hermetic
check and a human approval are the way out.

## Boundaries

| Boundary | Check |
|---|---|
| One command runs every check and every test | `tools/verify.py`, `tests/test_tools.py::test_every_check_is_run_by_verify` |
| The check is hermetic: nothing in this repo can import a module that reaches the network | `tools/check_repo.py` |
| The check is deterministic: the simulator runs fixed seeds, and a seed replays exactly | `tests/test_simulator.py::test_a_seed_replays_exactly` |
| The tests can fail: each Kernel rule, broken on purpose, is noticed | `tools/mutants.py` |
| The checks catch what they claim to catch | `tests/test_tools.py` |
| The Lifecycle is checked for termination, dead ends and unbounded cycles, a Lens's and the platform's among them | `tools/check_lifecycle.py`, `tests/test_tools.py::test_a_cycle_through_the_platform_with_no_bound_is_caught` |
| `factory / verify` runs on every pull request and on `merge_group`, with no path filter, and is the example word for word | `examples/workflows/invalid/queue.a-required-check-that-never-reports.yml`, `tests/test_tools.py::test_the_required_check_that_has_drifted_from_its_example_is_caught` |
