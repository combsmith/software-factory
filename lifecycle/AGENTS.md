# lifecycle/

The States a Work item can be in and the transitions between them, as data. One file for each
type of Work item. A pull request's State names are the codes in `kernel/terms.py`; an issue's
join them when the Kernel derives an issue's State, which it does not yet.

| Rule | Held by |
|---|---|
| Every State that is not terminal has a staleness limit and a way to a terminal State | `tools/check_lifecycle.py` |
| Take away the transitions marked `human`, and every cycle left passes through one that names its bound | `tests/test_tools.py::test_an_unbounded_factory_cycle_is_caught` |
| So whoever makes the cycle: a Lens, or the platform | `tests/test_tools.py::test_a_cycle_through_a_lens_with_no_bound_is_caught`, `tests/test_tools.py::test_a_cycle_through_the_platform_with_no_bound_is_caught` |
| A bound is a limit in `config/defaults.json`, which holds its number; the schema keeps no list of its own | `tests/test_tools.py::test_a_bound_that_is_not_a_limit_is_caught`, `tests/test_tools.py::test_a_bound_is_any_limit_and_only_a_limit` |
| Each type of Work item the Lifecycle schema names has its file here, named for it | `tests/test_tools.py::test_a_work_item_with_no_lifecycle_is_caught` |
| Only a person ends a Hold; the platform only reports that one did, so the transition is `human` | `tests/test_tools.py::test_a_hold_the_factory_could_end_is_caught`, `tests/test_tools.py::test_a_hold_the_platform_could_end_is_caught` |
| So with every State in `person_only_exits`: `held`, and for an issue `not_served` too | `tests/test_tools.py::test_an_issue_the_factory_could_serve_again_is_caught` |
| A transition the Kernel makes is declared here | `tests/test_simulator.py::test_invariants_hold_under_faults` |
