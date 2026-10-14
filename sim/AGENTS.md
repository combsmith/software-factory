# sim/

A fake GitHub around one pull request. `world.py` drives the real Kernel, plays the poller, the
jobs of a Run and the people, injects faults, and checks the invariants after every step. It decides
nothing: every decision comes from `kernel/`. It states each invariant in its own words, so a
changed rule may need its invariant changed too. Time is the counter `minute`.

| Rule | Held by |
|---|---|
| Draw only with `random()`, through `pick()`; other draws differ between Python versions | `tools/check_repo.py` |
| Every set of facts made here is valid, so a new fact is added here with its schema | `tests/test_simulator.py::test_invariants_hold_under_faults` |
| Every transition a pass makes here is declared in `lifecycle/pull_request.json` | `tests/test_simulator.py::test_invariants_hold_under_faults` |
| A failure names its seed, and the seed replays | `tests/test_simulator.py::test_a_seed_replays_exactly` |
| A rule the fake applies about GitHub is marked `# GitHub: <code>` where it is applied, and listed once in `grounding.py` with its trial and its fixture in `trials/`, or none. Verify prints each with none | `tools/check_trials.py` |
| The fake answers in GitHub's own shapes, so that its answers can be compared with a fixture | waiting on `adapters/` |

The world is one pull request of class `maintainer`, never paused, whose checks pass or fail. A
rule about anything else is not exercised here, so its boundary cases are all that hold it. An invariant is a call to `check()` with its name. When a seed finds a fault, the fix goes in the
Kernel with a boundary case in `tests/test_decide.py`.
