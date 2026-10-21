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
| Every change of State the Kernel can make is declared in the Lifecycle with who makes it: a person, a Lens, the Factory or the platform | `tests/test_transitions.py::test_every_change_of_state_is_declared_with_who_makes_it`, `tests/test_simulator.py::test_every_change_of_state_is_checked_with_who_made_it` |
| The Lifecycle terminates, and every cycle is bounded or passes through a person, whoever makes its transitions | `tools/check_lifecycle.py`, `tests/test_tools.py::test_a_cycle_through_a_lens_with_no_bound_is_caught`, `tests/test_tools.py::test_a_cycle_through_the_platform_with_no_bound_is_caught` |
| No text written by a third party reaches the Kernel: facts carry no prose | `examples/invalid/facts.carries-prose.json`, `tools/check_examples.py` |
| Facts say whether they are complete, the list of Runs and the timeline the acts are counted from among them; incomplete facts never converge and never admit | `examples/invalid/facts.no-completeness.json`, `examples/invalid/facts.no-completeness-for-runs.json`, `examples/invalid/facts.no-completeness-for-timeline.json`, `tests/test_decide.py::test_incomplete_facts_never_converge_or_admit`, `tests/test_decide.py::test_a_flag_that_is_not_exactly_true_is_incomplete` |
| A diff served with a 200 is checked against the same read's counts of files, added lines and deleted lines, and a list of files against `changed_files`: a difference is a short read, `complete.diff` or `complete.changed_paths` false. A 406 `too_large` is `diff.truncated`. No read is built from `patch`, which a large file loses while its entry stays; if one ever is, an entry without `patch` is read as short (`trials/P-29.truncated.json`) | `tests/test_adapters.py::test_the_content_is_the_hash_of_the_diff_as_github_served_it`, `tests/test_adapters.py::test_a_diff_that_disagrees_with_the_counts_is_a_short_read`, `tests/test_adapters.py::test_a_diff_github_will_not_serve_is_truncated_and_new_content_at_every_push`, `tests/test_adapters.py::test_a_list_github_stops_short_of_the_count_is_never_the_whole` |
| A merged or closed item keeps its State when a list was read short | `tests/test_decide.py::test_incomplete_facts_are_read_after_a_merged_or_closed_item` |
| No decision reads the control room: the Kernel is given facts, run records, context, configuration and the time, and nothing else | `tests/test_decide.py::test_admission_is_given_facts_and_never_an_event` |
| Every pass records the facts it read and the Decisions it made, so that any of them can be replayed | waiting on `controller/` |
| A view rebuilt from GitHub equals the view updated pass by pass | waiting on `controller/` |
| The status on a Work item is rewritten only when the decision changes | waiting on `harness/` |
