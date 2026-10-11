# sim/

A fake GitHub around one pull request. `world.py` drives the real Kernel, plays the poller, the
jobs of a Run and the people, injects faults, and checks the invariants after every step. It holds
no rule of its own: every decision comes from `kernel/`. Time is the counter `minute`.

| Rule | Held by |
|---|---|
| Draw only with `random()`, through `pick()`; other draws differ between Python versions | `tools/check_repo.py` |
| Every set of facts made here is valid, so a new fact is added here with its schema | `tests/test_simulator.py::test_invariants_hold_under_faults` |
| Every transition the Kernel makes here is declared in `lifecycle/pull_request.json` | `tests/test_simulator.py::test_invariants_hold_under_faults` |
| A failure names its seed, and the seed replays | `tests/test_simulator.py::test_a_seed_replays_exactly` |
| A rule the fake applies about GitHub cites a response recorded from the real platform | waiting on `adapters/` |

The world is one pull request of class `maintainer`. A rule for another class is not exercised
here, so its boundary cases are all that hold it. An invariant is a call to `check()` with its name. When a seed finds a fault, the fix goes in the
Kernel with a boundary case in `tests/test_decide.py`.
