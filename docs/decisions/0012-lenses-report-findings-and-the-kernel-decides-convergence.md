# 0012. Every Lens reports Findings in one schema; the Kernel decides Convergence

Status: accepted. Source: decision 12 of `docs/architecture/adr/0013-factory-mvp-reference-architecture.md`,
as it stood on 2026-10-11. That file records how this was reached; this one is the rule.

## Decision

Every source of judgement on a Work item, whether a Role, a third-party reviewer, a tool or a
person, is a Lens that reports Findings in one schema. Convergence is a Kernel function: every
required Lens has reported on the current content, and no gating Finding is open. Lenses do not
address each other. A Finding from a Lens outside the required set gates only when a required Lens
adopts it. A reviewing Role declares a rubric, which is a floor. A change that has not converged
within its bound is placed on Hold.

## Why

A council of independent Lenses finds more than one reviewer, but only if they stay independent
and something other than their conversation decides. The proof of concept decided by parsing
comments, and waited for reviewers that never answered.

## Boundaries

| Boundary | Check |
|---|---|
| A Finding is a structured record | `schemas/finding.schema.json`, `tools/check_examples.py` |
| A reason is a code, never a sentence | `examples/invalid/decision.sentence-as-reason.json` |
| A required Lens's blocking or major Finding gates; a minor one, or one from a Lens that is not required, does not | `tests/test_decide.py::test_required_lens_major_finding_gates`, `tests/test_decide.py::test_minor_finding_and_unrequired_lens_do_not_gate` |
| A required deterministic Lens is named for the check GitHub reports, and that check reports on every head and in the merge queue | waiting on `adapters/` |
| No model Lens runs on content the deterministic Lenses have not passed | `tests/test_decide.py::test_no_model_review_before_deterministic_checks_pass` |
| A dependency update is judged by the deterministic Lenses alone | not held yet: `tests/test_decide.py::test_a_dependency_update_needs_no_model_review` |
| An empty diff never converges | `tests/test_decide.py::test_empty_diff_never_converges` |
| Rounds between author and owner are bounded, and the bound ends in a Hold | `tests/test_decide.py::test_rounds_are_bounded` |
| Every category of Finding has exactly one owner | `tools/check_authority.py` |
| A rubric is data with a schema | `schemas/rubric.schema.json`, `tools/check_examples.py` |
| A reviewing Result reports on every criterion that applies | waiting on `harness/` |
| With an acceptance contract, every criterion has passing evidence on the current content | waiting on `harness/` |
| No manifest names another Role's output as a trigger | waiting on `roles/` |
