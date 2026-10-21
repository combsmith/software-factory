# 0011. The poller and the view are measured

Status: accepted. Source: decision 11 of `docs/architecture/adr/0013-factory-mvp-reference-architecture.md`,
as it stood on 2026-10-11. That file records how this was reached; this one is the rule.

## Decision

A poller and a rebuildable view are the settled choices, and each has a number it must meet. Over
two weeks of serving this repo: passes and nudges use at most 10% of the org's job-minutes; a pass
costs at most 3,000 GraphQL points an hour at peak; and the 95th-percentile delay from a change
that produces no event to a Decision is at most 15 minutes. If the delay fails with the relay in
place, or the view cannot be kept equal to a rebuild, a new record replaces the mechanism.

## Why

Both choices were made against what comparable systems do, so they are held to thresholds rather
than trusted. Because the Kernel does no I/O, either can be replaced without touching a decision.

## Boundaries

| Boundary | Check |
|---|---|
| Replacing the poller or the view changes no decision: the Kernel imports neither | `tools/check_purity.py` |
| The three thresholds are computed from run records and shown | `tests/test_controller.py::test_the_three_thresholds_of_decision_0011_are_computed_and_shown`; the job-minutes and the GraphQL points are read by a port, waiting on `adapters/usage.py` |
| W-2 is measured with the relay in place; while the relay is down it is not met, and the outage is itself reported within fifteen minutes (decision 0043) | waiting on `controller/relay.py` |
| Until the first Consumer is onboarded, a pass's cost an hour is an estimate, marked so (FR-35): the reader App's reads on the two repos it reaches, GitHub's cost model held to them, and the counts of open items in every repo of the org, recorded in `trials/P-8.json` | `tests/test_tools.py::test_the_cost_trials_estimate_is_marked_so_and_held_to_its_reads` |
| How often a scheduled tick arrives in this repo is measured once, over a day, by a workflow that does nothing but exist, and set against W-2: the schedule alone does not carry it, and the relay's nudges must; the measurement is `trials/P-8.ticks.json` | `tests/test_tools.py::test_the_tick_probes_intervals_are_held_to_its_runs` |
