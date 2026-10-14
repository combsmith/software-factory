# lifecycle/

The States a Work item can be in and the transitions between them, as data. One file for each
type of Work item. A pull request's State names are the codes in `kernel/terms.py`; an issue's
join them when the Kernel derives an issue's State, which it does not yet.

| Rule | Held by |
|---|---|
| Every State that is not terminal has a staleness limit and a way to a terminal State | `tools/check_lifecycle.py` |
| A transition the Factory makes that can be part of a cycle names its bound | `tests/test_tools.py::test_an_unbounded_factory_cycle_is_caught` |
| A bound is a limit in `config/defaults.json`, which holds its number | `tests/test_tools.py::test_a_bound_that_is_not_a_limit_is_caught` |
| Each type of Work item the Lifecycle schema names has its file here, named for it | `tests/test_tools.py::test_a_work_item_with_no_lifecycle_is_caught` |
| Only a person, or the platform acting for one, ends a Hold | `tests/test_tools.py::test_a_hold_the_factory_could_end_is_caught` |
| A transition the Kernel makes is declared here | `tests/test_simulator.py::test_invariants_hold_under_faults` |
