# 0012. Every Lens reports Findings in one schema; the Kernel decides Convergence

Status: replaced by `docs/decisions/0015-a-lens-is-read-from-its-own-app-and-only-what-gates-holds-a-merge.md`, which holds
the rule in force and its boundaries. Source: decision 12 of
`docs/architecture/adr/0013-factory-mvp-reference-architecture.md`, as it stood on 2026-10-11. That file records
how this was reached; this one was the rule.

## Decision

Every source of judgement on a Work item, whether a Role, a third-party reviewer, a tool or a
person, is a Lens that reports Findings in one schema. Convergence is a Kernel function: every
required Lens has passed on the current content, and no gating Finding is open. Lenses do not
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
| A required deterministic Lens is named for the check GitHub reports, and that check reports on every head and in the merge queue | waiting on `adapters/checks.py` |
| No model Lens runs on content the deterministic Lenses have not passed | `tests/test_decide.py::test_no_model_review_before_deterministic_checks_pass` |
| Only `success` passes a required check. `failure` and `timed_out` go back to the author, and are read first; queued, running, waiting and absent checks are waited for; a check that gave no verdict, or whose conclusion the map does not name, defers and needs the Maintainer | `tests/test_decide.py::test_a_neutral_required_check_defers`, `tests/test_decide.py::test_a_timed_out_required_check_goes_back_to_the_author`, `tests/test_decide.py::test_a_queued_running_or_absent_required_check_is_waited_for`, `tests/test_decide.py::test_a_failed_check_is_read_before_an_unreadable_or_waiting_one`, `tests/test_decide.py::test_a_failure_with_cancelled_or_skipped_siblings_goes_back_to_the_author` |
| The configuration cannot make a check with no verdict pass | `tests/test_tools.py::test_only_success_can_pass_a_check`, `examples/invalid/config.a-neutral-check-passes.json`, `examples/invalid/config.conclusion-mapped-to-nothing.json` |
| A dependency update is judged by the deterministic Lenses alone, and needs no model review | `tests/test_decide.py::test_a_dependency_update_needs_no_model_review` |
| A Finding a model Lens has raised gates whatever the class, a dependency update's too, and after the bot recreates the branch | `tests/test_decide.py::test_a_model_lens_thread_gates_a_dependency_update` |
| A dependency update is a dependency bot's pull request whose head that bot pushed; anyone else's push, and every other class, needs the model review | `tests/test_decide.py::test_a_dependency_update_someone_else_pushed_to_needs_a_model_review`, `tests/test_decide.py::test_every_other_class_needs_a_model_review`, `examples/invalid/config.a-change-by-a-person-skips-the-model-review.json` |
| A dependency update skips the model review and nothing else: every deterministic Lens, a person's thread, a Hold and a Pause still bind, and a `neutral` check does not pass it | `tests/test_decide.py::test_a_dependency_update_is_judged_by_every_deterministic_lens`, `tests/test_decide.py::test_a_neutral_check_does_not_pass_a_dependency_update`, `tests/test_decide.py::test_a_writers_thread_still_gates_a_dependency_update`, `tests/test_decide.py::test_a_dependency_update_skips_the_model_review_and_nothing_else` |
| The configuration names at least one deterministic Lens, so no update is approved with no check at all | `examples/invalid/config.no-deterministic-lens.json` |
| `last_pusher` is the identity GitHub records as having pushed the head, never a commit's author or committer; class `dependency` is given only for an exact App identity, and a fork is always `outside` | `tests/test_adapters.py::test_the_newest_push_to_the_head_names_its_pusher_a_person_or_an_app`, `tests/test_adapters.py::test_an_activity_that_has_not_caught_up_with_the_head_names_no_one`, `tests/test_adapters.py::test_only_the_newest_entry_is_read`, `tests/test_adapters.py::test_a_fork_is_read_as_no_one_and_its_activity_is_never_asked`, `tests/test_adapters.py::test_the_class_is_the_account_named_or_outside` |
| An empty diff never converges | `tests/test_decide.py::test_empty_diff_never_converges` |
| Rounds between author and owner are bounded, and the bound ends in a Hold | `tests/test_decide.py::test_rounds_are_bounded` |
| Every category of Finding has exactly one owner | `tools/check_authority.py` |
| A rubric is data with a schema | `schemas/rubric.schema.json`, `tools/check_examples.py` |
| A reviewing Result reports on every criterion that applies | waiting on `harness/` |
| With an acceptance contract, every criterion has passing evidence on the current content | waiting on `harness/` |
| No manifest names another Role's output as a trigger | waiting on `roles/` |
