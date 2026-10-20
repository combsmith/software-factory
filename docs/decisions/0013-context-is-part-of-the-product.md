# 0013. The context authors build from is part of the product

Status: accepted. Source: section 9.14, "Context engineering", of
`docs/architecture/software-factory-design.md`, on the Maintainer's instruction of 2026-10-11. This
is the one record that does not come from ADR-0013.

## Decision

Most of the Factory is written by agents, and an agent builds from what it is given to read. That
context is versioned, reviewed, kept small and checked. The root `AGENTS.md` is short enough to
read in full on every task. Each directory's `AGENTS.md` carries the rules of that place only.
Every rule names the check that holds it. A rule whose check cannot exist yet names the path it is
waiting on, and the required check fails when that path appears until the rule names a real check.

## Why

A rule that no check enforces is a wish, and the proof of concept's 1,100-line instruction file was
mostly wishes that each cost an incident to write down. Instructions that are always loaded compete
with the task for the reader's attention, so what is always loaded is kept small.

## Boundaries

| Boundary | Check |
|---|---|
| The root `AGENTS.md` and each directory's stay under their line limits | `tools/check_context.py` |
| Every rule, boundary, lesson and standard names a check that exists, or a path it is waiting on that does not | `tools/check_context.py` |
| The checks on the context catch what they claim to catch | `tests/test_tools.py::test_a_rule_with_no_check_is_caught`, `tests/test_tools.py::test_a_rule_whose_wait_is_over_is_caught` |
| An agent given only this repo and one sentence can add a rule to the Kernel and pass the required check | `tests/test_evals.py::test_a_fresh_agent_given_the_repo_adds_a_rule_and_passes_the_check`, not held yet |
