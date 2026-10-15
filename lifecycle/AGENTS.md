# lifecycle/

The States a Work item can be in and the transitions between them, as data. One file for each
type of Work item. A pull request's State names are the codes in `kernel/terms.py`; an issue's
join them when the Kernel derives an issue's State, which it does not yet.

| Rule | Held by |
|---|---|
| Every State that is not terminal has a staleness limit and a way to a terminal State | `tools/check_lifecycle.py` |
| Take away the transitions marked `human`, and every cycle left passes through one that names its bound | `tests/test_tools.py::test_an_unbounded_factory_cycle_is_caught` |
| So whoever makes the cycle: a Lens, or the platform | `tests/test_tools.py::test_a_cycle_through_a_lens_with_no_bound_is_caught`, `tests/test_tools.py::test_a_cycle_through_the_platform_with_no_bound_is_caught` |
| A bound is a limit the Kernel counts for each item, listed once, in `tools/check_lifecycle.py` | `tests/test_tools.py::test_a_bound_the_kernel_does_not_count_for_each_item_is_caught` |
| And a limit in `config/defaults.json`, which holds its number | `tests/test_tools.py::test_a_bound_that_is_not_a_limit_is_caught` |
| Each type of Work item the Lifecycle schema names has its file here, named for it | `tests/test_tools.py::test_a_work_item_with_no_lifecycle_is_caught` |
| The Factory makes no transition out of a Hold. A person ends a label or a ceiling; a changed diff, by `platform`, ends a Hold on the content | `tests/test_tools.py::test_a_hold_the_factory_could_end_is_caught` |
| Only a person leaves a State in `person_only_exits`: an issue's `held` and `not_served` | `tests/test_tools.py::test_an_issue_the_factory_could_serve_again_is_caught` |
| A pull request that is not served is not ended: GitHub serves it again when it retargets it | `tests/test_tools.py::test_a_pull_request_not_served_can_be_served_again_but_not_by_a_loop` |
| A transition the Kernel makes is declared here | `tests/test_simulator.py::test_invariants_hold_under_faults` |
