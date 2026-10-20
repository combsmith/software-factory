# tests/

`test_decide.py` holds one test for each boundary case of the Kernel, `test_issue.py` those of an issue's State,
with builders of its own, and `test_coverage.py` each of a reviewing Result's coverage. `test_tools.py` makes every
check fail. `test_simulator.py` runs the seeded simulation of a pull request, and `test_issue_simulator.py` that of an issue. `test_transitions.py` finds every change of State the Kernel can
make, and who makes it, and holds each to the Lifecycle. `test_hooks.py` feeds each session hook a
violation and a clean case. `support.py` builds ordinary inputs.
The page `docs/standards/tests.md` shows each of these by example.

| Rule | Held by |
|---|---|
| A boundary case is written before the code, and has a mutant | `tools/mutants.py` |
| Assert the outcome and the reason code. Never weaken or delete a test to make a change pass: its mutant survives | `tools/mutants.py` |
| A test's name is used once. A second definition replaces the first without a word | `tools/check_repo.py` |
| The simulation runs fixed seeds, and a seed replays exactly | `test_simulator.py::test_a_seed_replays_exactly`, `test_issue_simulator.py::test_a_seed_replays_exactly` |

Call the Kernel through `go()`, which validates every Decision against its schema. State only what
differs: `facts(is_draft=True)`. A fact that lives inside a list gets
a builder of its own in `support.py`, as `thread()` and `labelled()` are, and a new fact gets a counter-example. A comment such as "I-24" on a test
names an invariant in the design; the test's name is its sentence.
