# software-factory

The decision core of the agentic software factory. This repo starts as a proof of concept of the
Kernel, the schemas and the validators. Nothing here talks to GitHub yet.

## The rules that are never broken

Each rule names the check that enforces it. A rule no check enforces does not belong here.

| Rule | Enforced by |
|---|---|
| The Kernel does no I/O and reads no clock | `tools/check_purity.py` |
| Every message has a schema and a golden example, and counter-examples are rejected | `tools/check_examples.py` |
| A schema uses only keywords the validator implements | `tools/jsonschema_lite.py` fails closed |
| The Lifecycle terminates, and the Factory cannot cycle without a bound or a person | `tools/check_lifecycle.py` |
| Every category of Finding has one owner; security is never declined | `tools/check_authority.py` |
| State is derived from facts and run records, never stored | `kernel/derive.py` is its only definition |
| Every boundary case has a test, written before the code | `tests/test_decide.py` |
| The invariants hold under injected faults, on fixed seeds | `tests/test_simulator.py` |
| The tests can fail | `python3 -m tools.mutants` |
| No third-party code at run time | There is no requirements file, and there must not be one |

## Verify

```
make verify
```

It runs everything a required check would run. `SIM_SEEDS=40 make verify` is a faster local run.
`python3 -m tools.mutants` breaks one Kernel rule at a time and confirms a test notices.

## Where things are

| Path | What |
|---|---|
| `kernel/` | Every decision, as pure functions. Read `kernel/AGENTS.md` before editing |
| `schemas/` | One JSON Schema per message |
| `examples/` | Golden examples; `examples/invalid/` holds what must be rejected |
| `lifecycle/`, `config/` | The Lifecycle, the authority table, defaults and rubrics, as data |
| `tools/` | The checks, and the single `verify` command |
| `sim/` | A fake world that drives the real Kernel and injects faults |
| `tests/` | Boundary cases, tests of the checks, and the seeded simulation |

## Changing the Kernel

1. Write the boundary case in `tests/test_decide.py`. Watch it fail.
2. Change the code.
3. Add a mutant for the new rule to `tools/mutants.py`.
4. `make verify`, then `python3 -m tools.mutants`.

Terms are those of the PRD's glossary and are used exactly. A reason is a code, never a sentence.
