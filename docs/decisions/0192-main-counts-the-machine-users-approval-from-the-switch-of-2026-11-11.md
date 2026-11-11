# 0192. `main` counts the machine user's approval, from the switch of 2026-11-11

Status: accepted. The Maintainer's choice of 2026-11-11, "Switch; Factory approves", as the Factory Builder relayed it, on "The ruleset switch: main requires the machine user's approval of the most recent commit, and slice 1's event is recorded" (issue 198), once its dry run had ended. It carries out 0092's row "(a) Toward the `main` ruleset", which said that `main` counted no approval that day and fixed how it must count one.

## Decision

| What | Decided | Because |
|---|---|---|
| The switch | Ruleset 24886320, `main`, asks for one approval, a code owner's, of the last push, with a stale one dismissed on a push. Four fields changed and no other: `required_approving_review_count` from 0 to 1, and `require_code_owner_review`, `require_last_push_approval` and `dismiss_stale_reviews_on_push` from false to true. Nobody bypasses it, as before. The Factory Builder made the change through the Maintainer's login at 02:18Z on 2026-11-11, and `config/rulesets.json` records what GitHub answered after it | 0092 fixed the shape, and the code owners are the machine user's team on every path (0108) |
| What was shown first | A Release on `next` reviewed "AGENTS.md: say what is built; drop the model claim no check holds" (pull request 688). The machine user approved its head at 00:25Z on 2026-11-11, the Factory's queue step enqueued it, and it merged through the queue at 01:21Z, with no person's act between the approval and the merge | A ruleset that asks for an approval nothing can give stops every merge. Seven dry runs before it stopped short of the approval |
| What a merge now needs | Every pull request to `main`, the Maintainer's own among them, merges only with the machine user's approval of its last push, and a push after that approval dismisses it. The Factory's approving act gives the approval. How a fix merges while the Release on `next` is broken is that story's to show, and is not shown yet | The Maintainer authors every commit, and GitHub counts no approval from an author or a last pusher (0005) |
| The undo | The same four fields back, on the Maintainer's word, through his login. The record follows by a pull request that changes this record's test, so the undo is read as a decision | The record is not the ruleset. `tools/rulesets_drift.sh`, run by hand, reads the difference between them |
| What stays | `tools/check_rulesets.py` holds how an approval is counted and whose team owns every path, as 0092 has it, and still lets through a `main` that counts none: it holds the shape, not the day. No check here reads GitHub | A check that refused the earlier state would refuse the undo's record too, when the undo is the urgent thing |

## Why

Through slices 0 and 1 `main` asked for the check and the queue and no review, because the Maintainer authors every pull request and cannot approve his own. The design switches required review on when the Factory's reviewer serves the repo. It does now, so the day and what it rests on are written down where the earlier record said "today".

## Boundaries

| Boundary | Check |
|---|---|
| The record is of `main` counting one approval, a code owner's, of the last push, a stale one dismissed, with no required reviewer and nobody bypassing it, beside code owners the check accepts | `tests/test_tools.py::test_main_counts_the_machine_users_approval_as_the_switch_left_it`, `config/rulesets.json`; mutant: "the record of main counts no approval"; mutant: "the record of main asks for no code owner's approval"; mutant: "the record of main counts an approval of an earlier push"; mutant: "the record of main leaves a stale approval standing"; mutant: "the record of main is of the day before the switch" |
