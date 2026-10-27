# sim/

A fake GitHub around one pull request, and another around one issue. `world.py` drives the real Kernel, plays the poller, the jobs of a Run and the people, injects faults, and checks the invariants after every step. It decides
nothing: every decision comes from `kernel/`. It states each invariant in its own words, so a changed rule may need its invariant changed too. Time is the counter `minute`. `issues.py` is the issue's world, built the same way:
it drives `kernel/issue.py`, plays the Controller's acts, the three issue Runs and the people, and checks I-39 to I-44 after every step. Its queue makes no merge while
the issue is held or declined, and a person none while it is declined: the Controller dequeues the Factory's pull request on a person's hold or close, as the Maintainer ruled (issue 227, "Design: does a merge end a held or a declined issue?").

| Rule | Held by |
|---|---|
| Draw only with `random()`, through `pick()`; other draws differ between Python versions | `tools/check_repo.py` |
| Every set of facts made here is valid, so a new fact is added here with its schema | `tests/test_simulator.py::test_invariants_hold_under_faults` |
| Every change of State made here is declared in `lifecycle/pull_request.json`, with who made it | `tests/test_simulator.py::test_every_change_of_state_is_checked_with_who_made_it` |
| Every change of State the issue's world makes is declared, with who made it, and the exploration of every change finds it | `tests/test_issue_simulator.py::test_invariants_hold_under_faults` |
| A failure names its seed, and the seed replays | `tests/test_simulator.py::test_a_seed_replays_exactly`, `tests/test_issue_simulator.py::test_a_seed_replays_exactly` |
| A rule the fake applies about GitHub is marked `# GitHub: <code>` where it is applied, and listed once in `grounding.py` with its trials, each quoting in `ASKS` what its row asks, and its fixture, or none | `tools/check_trials.py` |
| A rule no trial asks is grounded only once a trial for it is added to section 6 of the design | `tests/test_tools.py::test_a_fixture_named_for_a_rule_must_exist_and_validate` |
| Until then it names that trial, or says in one sentence why none can; `make verify` prints which | `tests/test_tools.py::test_a_rule_no_trial_asks_names_one_or_says_why_none_can` |
| A grounded rule is read as it states, or named with why not; a recorded refusal is no answer | `tests/test_adapters.py::test_the_port_reads_each_grounded_rule_as_the_fake_assumes_it`, `tests/test_adapters.py::test_a_recorded_refusal_is_no_answer` |

The world is one pull request, paused for a span on some seeds, or with a Pause that cannot be read, and on some with no writer's action yet.
On those seeds the Pause may begin early, as an approval falls due or a count is spent (`tests/test_simulator.py::test_the_pause_falls_due_with_an_approval`, `..._with_a_spent_count`).
Its checks pass, fail, time out or give no verdict, and another App can post a passing check under the name of a Lens that failed. On an odd seed it
is the Maintainer's own, of class `maintainer`: GitHub refuses a review by its author, so the Maintainer acts with threads, a Hold and pushes. On an even seed it is an agent's, of class `agent`, and the Maintainer also reviews it:
requests changes, comments or approves (`tests/test_simulator.py::test_the_seeds_serve_a_maintainers_and_an_agents_pull_request`).
On one seed in ten it is a dependency bot's update, on every other such seed to a workflow's pin, whose list of paths can leave one out. A Role's fix, the Maintainer's push and that update
may change the Factory's own rules or a Lens's input (`tests/test_simulator.py::test_the_seeds_change_the_list_by_a_role_the_dependency_bot_and_the_maintainer`).
While the item is queued, the Maintainer may dismiss its approval, open a thread or add a Hold. The queue merges only after a pass has read the item whole and current,
and found the same facts GitHub holds at the merge (`tests/test_simulator.py::test_the_seeds_take_a_pull_request_out_of_the_queue_for_each_cause`).
On three seeds in seven the item has an acceptance contract: a Lens gives each criterion's result, passing or now and then failing, on the content of the moment, results on earlier content stay behind, a second result can disagree with the first, the
oldest can expire, and a pass can read the contract short or with a result on this content for a criterion it does not name. A person approves the contract, or on some seeds has not yet, and can withdraw it; a push can edit or delete it; another App or
workflow can give a result, and a check one for a criterion only a person passes, which on an agent's pull request a person's approval of the content confirms (`tests/test_simulator.py::test_the_seeds_serve_items_with_an_acceptance_contract_and_without`).
Under faults a result on the content expires as its approval falls due (`tests/test_simulator.py::test_the_evidence_expires_as_the_approval_falls_due`).
On every seed a review's Result now and then leaves a criterion of its rubric uncovered: its Run fails by a fault of the item and opens no thread, and the review is admitted again until its attempts hold the item
(`tests/test_simulator.py::test_the_seeds_serve_a_review_that_left_a_criterion_uncovered`). On one seed in eight a new Run is listed unnamed for a pass, which neither admits nor approves (`tests/test_simulator.py::test_the_seeds_list_a_new_run_unnamed`).
On another seed in eight a run never takes its name: it defers admissions only inside `max_unnamed_run_seconds`, and is one alert past it (`tests/test_simulator.py::test_the_seeds_list_a_run_that_never_takes_its_name`).
In each world one Run holds the item's lane and at most one waits behind it; a newer one cancels the one waiting (`tests/test_simulator.py::test_a_newer_run_cancels_the_one_waiting_in_each_world`).
A rule about anything else is not exercised here, so its boundary cases are all that hold it. An invariant is a call to `check()` with its name. When a seed finds a fault, the fix goes in the Kernel with a boundary case in `tests/test_decide.py`.

On one seed in three the ruleset dismisses stale approvals: a push dismisses each standing approval and names the pusher (`tests/test_simulator.py::test_the_seeds_serve_a_ruleset_that_dismisses_stale_approvals_and_one_that_does_not`).
Known to differ, unverified until the fake changes or its trial runs: the queue merges without checking the merge group (`the_merge_group_is_not_checked`; this repo's queue checks it, P-2).
