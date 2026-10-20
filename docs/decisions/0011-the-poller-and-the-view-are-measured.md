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
| The three thresholds are computed from run records and shown | waiting on `controller/` |
| Until the first Consumer is onboarded, a pass's cost an hour is an estimate: the reader App's reads on the two repos it reaches, GitHub's cost model held to them, and the counts of open items in every repo of the org, marked so (FR-35) | `trials/P-8.json` |
