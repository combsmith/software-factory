# 0028. An issue's State is derived in a module of its own

Status: accepted. Taken as a working ruling for "Kernel: derive an issue's State from its facts"
(issue 41) on 2026-10-17, which the Maintainer may overturn in review.

## Decision

An issue's State comes from one function, `derive(facts, runs, config)` in `kernel/issue.py`. It
returns `{state, reason, evidence}`, as the pull request's does, and reads only the issue's own
facts. `kernel/decide.py`, `kernel/derive.py`, `kernel/terms.py` and `kernel/gate.py` are not
edited. When the Controller is built it picks the function by the item's type; if one Kernel entry
is wanted later, the smallest change is a dispatch at the top of `decide.decide`, decided with it.

`kernel/issue.py` imports five names and changes none of them: `is_time`, `runs_on`, `in_progress`
and `standing_labels` from `kernel/derive.py`, and `is_person` from `kernel/gate.py`. There is one calendar, and
one reading of "what a person placed, only a person ends". The pull request's work treats these
five as a contract. Once both are built, the readers they share move into one module.

An issue's facts are `issue-facts/1`, in `schemas/issue-facts.schema.json`. Its control labels are
`label_events`, as on a pull request: label, action, who and when. Each linked pull request carries
its number, its class as the port gives it, its opener, whether it is open or a draft, when it
merged and closed, whether its diff was empty, and its own `label_events`. The Hold, hands-off and
whether a person once admitted it are read from those, with the pull request's own reading.
`factory:triage` and `factory:ready` count from their latest add, and any removal at or after it
ends them: they let work go, so a removal stops it. The flags of `complete` are `timeline`,
`linked` and `runs`. Section 3.3 of the design is corrected to these shapes.

`config/defaults.json` gains one block, `issues`: `served_from`, `left_out_labels`,
`left_out_types`, and `label_apps`, the App whose `factory:triage` and whose `factory:ready` count.
Every value is null or empty: no issue is served, and only a person's label counts, until the
Maintainer turns issues on.

A list read short defers with `facts_incomplete`, and a label event, a linked pull request, the
issue's life or its content that cannot be read defers with a code of its own, before row 1, for a
closed issue too. In the same second the reading that stops work wins: a merge at the start of a
life is `done`, and a label added at an edit or a reopening does not count.

The Run ceiling of row 4 is not derived here. The brakes count it (decision 0003), and the issue's
decision will ask them, as the pull request's does.

## Why

The derivation reads nothing of a pull request's facts, so a module of its own lets the issue's
work and the pull request's run side by side without touching the same lines; the same holds for
the mutants, which sit in a list of their own above the pull request's. Importing the readers,
rather than copying them, keeps one calendar and one reading of who placed a label (L-17). The
event shapes let the pull request's tested reading serve the Hold, hands-off and admission. The
defaults are null because the Consumer entry has no fields for issues yet (design §9.9), and null
fails closed. The Run ceiling stays with the brakes because they count it and nothing else does.

## Boundaries

| Boundary | Check |
|---|---|
| The situations the reviews of the issue Lifecycle found derive as the design says | `tests/test_issue.py::test_the_situations_the_reviews_found_derive_as_the_design_says` |
| Every State the function derives is declared in the Lifecycle, and every declared State has a code | `tests/test_issue.py::test_every_state_is_declared_and_every_declared_state_has_a_code` |
| The module that derives an issue's State is held pure | `tests/test_issue.py::test_the_kernel_module_that_derives_an_issue_is_held_pure` |
| A list read short defers, a closed issue's too | `tests/test_issue.py::test_a_list_not_read_in_full_defers` |
| A label event, a linked pull request, a life or a content that cannot be read defers, in that order | `tests/test_issue.py::test_what_cannot_be_read_is_read_in_its_order` |
| No issue is served until the Maintainer turns issues on, and no App's label counts until it is declared | `tests/test_issue.py::test_no_issue_is_served_until_the_maintainer_turns_issues_on`, `tests/test_issue.py::test_no_app_counts_until_it_is_declared` |
| A merge at the start of a life is done, and a label at an edit or a reopening does not count | `tests/test_issue.py::test_a_merge_at_the_start_of_a_life_is_done_and_one_before_it_is_not`, `tests/test_issue.py::test_triage_and_ready_count_only_in_the_present_life` |
| Any removal at or after the latest add ends `factory:triage` and `factory:ready` | `tests/test_issue.py::test_any_removal_at_or_after_the_latest_add_ends_ready_and_triage` |
