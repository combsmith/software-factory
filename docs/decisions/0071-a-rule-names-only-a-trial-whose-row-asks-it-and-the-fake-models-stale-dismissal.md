# 0071. A rule names only a trial whose row asks it, and the fake models stale dismissal

Status: accepted. The Factory Builder's rulings of 2026-10-27 on the grounding issue the Why names, option (a) for the approval rule. The Maintainer may overturn it in review. Section 6 of the design is protected: the questions added here to the rows of P-1, P-2, P-7 and P-18 are the Maintainer's to approve, and a trial with two rows there is refused.

## Decision

| What | Decided | Because |
|---|---|---|
| A row asks a rule | Each rule of `sim/grounding.py` quotes, in `ASKS`, the words of each named trial's question in section 6 that ask it: four words at least, exactly as the question's cell gives them, outside any fenced block. `tools/check_trials.py` refuses a named trial with no quote, a quote that is not in that row's question, the row's answer among the rest, a quote too short to name a question, and a quote of a trial the rule does not name or of a rule not listed. A row reworded so that it stops asking a rule refuses the rule | A rule that named the wrong row passed the check: it held only that the row existed. A quote sits beside the rule, where a reviewer reads both; section 6 changes only where a row must gain a question |
| What a quote proves | That the row's question holds those words, and no more: whether they ask the rule is the reviewer's. The quotes were written against each row as it stands, and where a row asks only part of a rule, the part it asks is quoted | A check of meaning would need the meaning written twice |
| The four rules | `the_timeline_shows_each_act` names P-2, whose row now asks whether each enqueue and dequeue is on the timeline with its actor, and P-41, which asks every actor's type; not P-8, which asks the cost of a pass. `an_approval_can_fail_to_land` names no trial: a fault of the item or of the environment that drops an approval cannot be forced on demand. `a_superseded_run_fails` names P-18, whose row now asks whether a job whose step exits non-zero concludes `failure`; not P-17, which asks a run's name. The approval rule is the next row | The issue's table |
| A push and an approval | `an_approval_survives_a_push` is gone. Where the world's ruleset dismisses stale approvals on a push, a push dismisses each standing approval and names the pusher as its dismisser: an App, `an_approval_is_dismissed_by_a_push`, asked by P-7's row and grounded in `trials/P-7.json`; a person, `a_persons_push_names_the_person_as_dismisser`, asked by P-38's row and unverified until P-38 runs, since P-7 saw only an App's push dismiss an approval as stale (the Maintainer's dismissal there was his own, with a message). Where it does not, an approval stands: `an_approval_stands_without_stale_dismissal`, asked by P-1's row, which asks of the live ruleset that the ruleset switch, "The ruleset switch: main requires the machine user's approval of the most recent commit, and slice 1's event is recorded" (issue 198), changes; unverified until P-1 is asked again. The fake draws the setting from the seed, one seed in three dismissing, so every invariant is held under both | P-7 saw the canary's ruleset dismiss the approval, naming the pusher. Main's ruleset does not dismiss stale approvals today (read 2026-10-26), and the switch turns it on: the fake models the setting, never assumes it |
| What the fake does on a person's push | A person's push that dismisses the review carrying the contract's approval ends that approval, as the Kernel reads a person's dismissal (decision 0025), and the person approves the contract again | The Kernel's `approval_stands` ends an approval a person dismissed; the fake must agree with GitHub's facts as the Kernel reads them, or I-29 is checked against a world that differs |
| Found, not changed here | The Kernel's `approval_stands` and `judged_by_a_person` say a stale dismissal is an App's and ends nothing. P-7 shows a stale dismissal names the pusher: under a ruleset that dismisses stale approvals, a person's push reads as that person ending their own approval, and the contract asks to be approved again. That fails closed. Whether a pusher's stale dismissal should end a person's approval is the Kernel's question, for a story of its own | The Kernel is changed only with a boundary case of its own (`kernel/AGENTS.md`) |
| A dismissal and the act count | The port reads a person's push-dismissal as that person's action on the timeline, as the fake reads a writer's push; an App's push-dismissal, a Factory App's among them, is no act of the Factory's, which counts only an approval, a label and a queue entry | `since_writer` in `adapters/timeline.py`, held to P-7's timeline |

## Why

"Grounding: four rules name a §6 row that does not ask them (the_timeline_shows_each_act, an_approval_survives_a_push, an_approval_can_fail_to_land, a_superseded_run_fails)" (issue 265)
found four rules that named a trial whose row asked something else, and the check passed each.
Writing a quote for every rule turned up the same mistake wherever a row had been named by its subject and not by
its question. The approval rule was known wrong: P-7 saw the push dismiss the approval, and the fake kept it.

## Boundaries

| Boundary | Check |
|---|---|
| A rule names only a trial whose row asks it: no quote, a quote not in the question, the answer, a quote too short, a reworded row, a fenced row, a quote of an unnamed trial or of no rule, and ASKS of the wrong shape, are refused | `tests/test_tools.py::test_a_rule_names_only_a_trial_whose_row_asks_it` |
| The approval trials ground the rules they asked | `tests/test_tools.py::test_the_approval_trials_ground_the_rules_they_asked` |
| The seeds serve a ruleset that dismisses stale approvals and one that does not, every invariant holding, items merging under both | `tests/test_simulator.py::test_the_seeds_serve_a_ruleset_that_dismisses_stale_approvals_and_one_that_does_not` |
| A Factory App's stale dismissal is no act, and a person's is that person's action | `tests/test_adapters.py::test_who_last_acted_with_write_access_and_the_factorys_acts_since` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
