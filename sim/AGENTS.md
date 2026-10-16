# sim/

A fake GitHub around one pull request. `world.py` drives the real Kernel, plays the poller, the
jobs of a Run and the people, injects faults, and checks the invariants after every step. It decides
nothing: every decision comes from `kernel/`. It states each invariant in its own words, so a
changed rule may need its invariant changed too. Time is the counter `minute`.

| Rule | Held by |
|---|---|
| Draw only with `random()`, through `pick()`; other draws differ between Python versions | `tools/check_repo.py` |
| Every set of facts made here is valid, so a new fact is added here with its schema | `tests/test_simulator.py::test_invariants_hold_under_faults` |
| Every change of State made here is declared in `lifecycle/pull_request.json`, with who made it | `tests/test_simulator.py::test_every_change_of_state_is_checked_with_who_made_it` |
| A failure names its seed, and the seed replays | `tests/test_simulator.py::test_a_seed_replays_exactly` |
| A rule the fake applies about GitHub is marked `# GitHub: <code>` where it is applied, and listed once in `grounding.py` with its trials and its fixture in `trials/`, or none. Verify prints each with none | `tools/check_trials.py` |
| A rule no trial asks is grounded only once a trial for it is added to section 6 of the design | `tests/test_tools.py::test_a_fixture_named_for_a_rule_must_exist_and_validate` |
| The fake answers in GitHub's own shapes, so that its answers can be compared with a fixture | waiting on `adapters/` |

The world is one pull request, paused for a span on some seeds, or with a Pause that cannot be read, and on some with no writer's action yet.
Its checks pass, fail, time out or give no verdict, and another App can post a passing check under the name of a Lens that failed. On an odd seed it
is the Maintainer's own, of class `maintainer`: GitHub refuses a review by its author, so the Maintainer acts with
threads, a Hold and pushes. On an even seed it is an agent's, of class `agent`, and the Maintainer also reviews it:
requests changes, comments or approves (`tests/test_simulator.py::test_the_seeds_serve_a_maintainers_and_an_agents_pull_request`).
On one seed in ten it is a dependency bot's update, on every other such seed to a workflow's pin, whose list of paths can leave one out. A Role's fix, the Maintainer's push and that update
may change the Factory's own rules or a Lens's input (`tests/test_simulator.py::test_the_seeds_change_the_list_by_a_role_the_dependency_bot_and_the_maintainer`).
While the item is queued, the Maintainer may dismiss its approval, open a thread or add a Hold. The queue merges only after a
pass has read the item whole and current, and found the same facts GitHub holds at the merge
(`tests/test_simulator.py::test_the_seeds_take_a_pull_request_out_of_the_queue_for_each_cause`).
On three seeds in seven the item has an acceptance contract: a Lens gives each criterion's result, passing or now and then failing, on the content of the
moment, results on earlier content stay behind, a second result can disagree with the first, the oldest can expire, and a pass can read
the contract short or with a result on this content for a criterion it does not name
(`tests/test_simulator.py::test_the_seeds_serve_items_with_an_acceptance_contract_and_without`).
A rule about anything else is not exercised here, so its boundary cases are all that hold it. An invariant is a call to `check()` with its name. When a seed finds a fault, the fix goes in the
Kernel with a boundary case in `tests/test_decide.py`.

Known to differ from the design: the lane keeps one Run in progress and any number queued
(`a_run_waits_its_turn`), where GitHub's concurrency group keeps one running and one pending and
cancels the older pending Run. It is listed as unverified and left as it is.
