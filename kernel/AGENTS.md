# kernel/

Every decision the Factory makes, as pure functions. `derive.py` works out the State of a pull request and answers "where does this item stand": its tests run in order and the first that applies wins.
A queued item is read as if it were not, and stays only if that reading is approved. `decide.py` answers "what now". `terms.py` holds the codes. `gate.py` holds the gate: which open Findings hold a pull request, and the severities that gate.
`brakes.py` is the Kernel's half of the brakes (decision 0003): Admission refuses at a ceiling or under a Pause, and `decide.py` asks the brakes before every act and Run. `issue.py` derives an issue's State (decision 0028).
`coverage.py` says whether a reviewing Result covers its rubric (decision 0029). Brakes, outside `kernel/`, wait on `controller/`. Only `brakes.py`, `gate.py` and `coverage.py` are protected paths; the rest of the Kernel is reported at a stop.

| Rule | Held by |
|---|---|
| No I/O: no file, socket, process, environment variable or clock. The time is the argument `now`. Only `__future__`, `typing` and `kernel` are imported | `tools/check_purity.py` |
| Nothing is kept: a module holds imports, constants and functions, and no function has a default that can change | `tests/test_tools.py::test_state_kept_between_calls_is_caught` |
| Facts in, Decision out, as plain dictionaries and lists. An argument is never changed | `tests/test_decide.py::test_the_same_inputs_give_the_same_decision` |
| No text from outside: no function takes a comment body or a title | `examples/invalid/facts.carries-prose.json` |
| A reason is a code that matches `^[a-z_]+$`, never a sentence | `examples/invalid/decision.sentence-as-reason.json` |
| Fail to a deferral or a Hold. A fact read from outside is never given a default | `tests/test_decide.py::test_unreadable_capacity_defers` |
| The gate imports no Kernel code, the brakes only its codes. Nothing else binds their names or their own; no attribute is assigned | `tests/test_tools.py::test_the_brakes_and_the_gate_stand_apart`, `tests/test_tools.py::test_an_attribute_assigned_is_caught` |
| No number but 0 and 1, but the calendar's that `tools/check_purity.py` pins. A limit is read from `config` | `tests/test_tools.py::test_a_limit_written_into_the_kernel_is_caught`, `tests/test_tools.py::test_only_the_calendar_may_write_a_number` |

## Adding a rule: copy this one

First look in `tests/test_decide.py` for a test marked `@pending` that states your rule. If there is one, take the mark off, move it out of `NotYetHeld`,
and take "not held yet" out of the documents `make verify` names. `python3 -m unittest tests.test_decide` runs the boundary cases in a moment.

"An empty diff never converges" is a whole rule in three parts. Find each and write its twin.

1. The boundary case: `tests/test_decide.py::test_empty_diff_never_converges`. Written first. Assert both sides of the boundary.
2. The rule: the line in `derive.py` that returns the reason `empty_diff`.
3. The mutant: the entry "an empty diff converges" in `tools/mutants.py`. It names the file, the
   exact text of the rule, and what to put in its place. The text must appear once in the file.
   A rule that acts in two places gets a mutant for each; one that changes an existing line gets a mutant that puts the old line back.

Then, only if your rule needs it:

- A person must act on the new reason: add it to `NEEDS_YOU_REASONS` in `decide.py`. A new brake goes in `brakes.py`, and what gates in `gate.py`.
- It reads a new fact: add the field to `schemas/facts.schema.json`, `examples/facts.json`,
  `facts()` in `tests/support.py` and `sim/world.py`, together; a flag in `complete`, to `terms.py` too.
- It reads a new limit: add it to `config/defaults.json` and `schemas/config.schema.json`. A staleness limit stays in `lifecycle/`.
- It makes a new transition between States: declare it in `lifecycle/pull_request.json`, with who makes it. A new reason needs facts in `BASES` in `tests/test_transitions.py`, which asks for them.
- It is a boundary of a record in `docs/decisions/`: add a row there naming your test.
