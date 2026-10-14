# lifecycle/

The States a Work item can be in and the transitions between them, as data. One file for each
type of Work item. The State names are the codes in `kernel/terms.py`.

| Rule | Held by |
|---|---|
| Every State that is not terminal has a staleness limit and a way to a terminal State | `tools/check_lifecycle.py` |
| A transition the Factory makes that can be part of a cycle names its bound | `tests/test_tools.py::test_an_unbounded_factory_cycle_is_caught` |
| Only a person, or the platform acting for one, ends a Hold | `tests/test_tools.py::test_a_hold_the_factory_could_end_is_caught` |
| A transition the Kernel makes is declared here | `tests/test_simulator.py::test_invariants_hold_under_faults` |
