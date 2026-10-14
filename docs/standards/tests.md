# Tests

How tests are written here. Each rule shows its example first, then says what holds it.
An org standard is cited from petry-projects/.github at commit 9e2daad, by file and heading.

## The boundary case comes first, and brings its mutant

```python
# tests/test_decide.py: written first, and seen to fail
def test_empty_diff_never_converges(self):  # I-24
    f = facts(diff={"files": 0, "lines": 0, "truncated": False})
    self.assertEqual(go(f, REVIEWED)["reason"], "empty_diff")

# tools/mutants.py: the same rule, broken on purpose
("an empty diff converges", "kernel/derive.py",
 'if facts["diff"]["files"] == 0:', "if False:"),
```

A mutant is (name, file, the text of the rule, what to put in its place). The text must appear
exactly once in the file, or the mutant is reported `STALE`. `python3 -m tools.mutants` applies
each in a copy of the repo and runs the tests: a mutant that survives is a rule nothing tests.
A comment such as `# I-24` names an invariant of the design; the test's name is its sentence.

Org standard: the org's AGENTS.md, "Test-Driven Development (TDD)". Stricter here: a mutant for each rule. unittest, where the org asks for pytest, is a departure: `docs/decisions/0014-where-this-repo-departs-from-the-orgs-standards.md`.
Held by: `tools/mutants.py`

## A test asserts the Decision, not the absence of an error

```python
self.assertEqual((d["outcome"], d["reason"]), ("hold", "attempts_exhausted"))   # yes
self.assertIsNotNone(d)                                                         # no
```

Assert the outcome and the reason code. Call the Kernel through `go()` in `tests/test_decide.py`,
which also validates every Decision against its schema. Never weaken a test to make a change
pass: a test that asserts less lets its mutant survive.

Org standard: the org's AGENTS.md, "Forbidden Patterns", which forbids a placeholder assertion and editing a test to make a change pass. The same.
Held by: `tools/mutants.py`

## A test states only what differs

```python
f = facts(labels=["factory:hold"])                        # everything else is ordinary
runs = REVIEWED + [run(role="dev-lead", intent="fix-findings", at="2026-10-11T12:20:00Z", name="r2")]
d = go(f, runs, ctx=context(paused=True))
```

`tests/support.py` builds ordinary facts, run records, threads, context and configuration. A new
fact gets a default there, in `sim/world.py`, in `examples/facts.json` and in
`schemas/facts.schema.json`, all in one change; the simulator validates every set of facts it makes.

Org standard: none. This rule is this repo's own.
Held by: `tests/test_simulator.py::test_invariants_hold_under_faults`

## A check has a test in which it fails

```python
def test_io_in_the_kernel_is_caught(self):
    root = tree({"kernel/x.py": "import os\n\ndef f():\n    return open('x')\n"})
    problems = check_purity.run(root)
    self.assertTrue(caught(problems, "imports os") and caught(problems, "uses open"))
```

`tree()` in `tests/test_tools.py` makes a throwaway repo holding a planted fault, and `clone()`
plants one in a copy of this repo so the check is run from its front door. A check that has never
been seen to fail is not known to work.

Org standard: none. This rule is this repo's own.
Held by: `tests/test_tools.py::test_every_check_has_a_test_in_which_it_fails`

## Every rule on data has a counter-example

```text
examples/facts.json                              must validate
examples/invalid/facts.carries-prose.json        must be rejected
examples/workflows/verify.yml                    must pass every workflow rule
examples/workflows/invalid/pin.a-tag-can-move.yml   must break the rule "pin", and no other
```

A file under `examples/invalid/` is named `<schema>.<what is wrong>.json`. A file under
`examples/workflows/invalid/` is named `<rule>.<what is wrong>.yml`, and a workflow rule with no
such file fails the check.

Org standard: none. This rule is this repo's own.
Held by: `tools/check_examples.py`, `tests/test_tools.py::test_a_rule_with_no_counter_example_is_caught`

## The required check cannot fail at random

```python
def pick(self, options):
    """Choose with random() only, whose sequence is the same on every Python version."""
    options = list(options)
    return options[int(self.rng.random() * len(options))]
```

The simulator runs a fixed list of seeds, and a failure prints its seed and a trace. Draw only
with `random()`. Time is a counter the simulator advances. `SIM_SEEDS=40` shortens a local run.

Org standard: the org's AGENTS.md, "Test-Driven Development (TDD)": unit tests are fast, deterministic and offline. The same; fixed seeds are how.
Held by: `tests/test_simulator.py::test_a_seed_replays_exactly`, `tests/test_tools.py::test_a_draw_that_differs_between_python_versions_is_caught`
