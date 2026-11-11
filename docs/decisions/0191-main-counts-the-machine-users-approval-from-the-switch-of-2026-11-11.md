# 0191. `main` counts the machine user's approval, from the switch of 2026-11-11

Status: accepted. The Maintainer's choice of 2026-11-11, "Switch; Factory approves", as the Factory Builder relayed it, on "The ruleset switch: main requires the machine user's approval of the most recent commit, and slice 1's event is recorded" (issue 198), once its dry run had ended. It carries out 0092's row "(a) Toward the `main` ruleset", which said that `main` counted no approval that day and fixed how it must count one.

## Decision

| What | Decided | Because |
|---|---|---|
| The switch | Ruleset 24886320, `main`, asks for one approval, a code owner's, of the last push, with a stale one dismissed on a push. Four fields changed and no other: `required_approving_review_count` from 0 to 1, and `require_code_owner_review`, `require_last_push_approval` and `dismiss_stale_reviews_on_push` from false to true. Nobody bypasses it, as before. The Factory Builder made the change through the Maintainer's login at 02:18Z on 2026-11-11, and `config/rulesets.json` records what GitHub answered after it | 0092 fixed the shape, and the code owners are the machine user's team on every path (0108) |
| What is not shown yet | Two things the switch does not rest on. The Factory's queue step has not enqueued a pull request: the one the dry run merged was enqueued through the Maintainer's login. And how a fix merges while the Release on `next` is broken, 0008's way out of a hermetic check and a person's approval, is that story's to show | The switch asks for the approval, not for who enqueues. A record that claimed either would say more than was seen |
| What a merge now needs | Every pull request to `main` merges only with a code owner's approval of its last push, and a push after that approval dismisses it. The code owners are the team `org-leads` on every path, which holds the machine user and the Maintainer. GitHub counts no approval from an author or a last pusher, so for a pull request the Maintainer authors, which today is every one, the approval that counts is the machine user's, and the Factory's approving act gives it | The ruleset names a code owner, not an account (0108). The Maintainer authors every commit (0005) |
| What it overtakes | Earlier records said, of their own day, that `main` required no review: 0020's Why and its boundary row "What GitHub holds is recorded", the Why of 0018, 0022 and 0026, and 0087's row "What limits a forged name" with its Why. Each stands as written, and none is true of `main` from the switch. 0087's risk is the narrower for it: a forged name now meets the machine user's approval too. | A record is not edited, so the record that changes the fact says which earlier words it leaves behind |
| The undo | The same four fields back, on the Maintainer's word, through his login. The record follows by a pull request that changes this record's test, so the undo is read as a decision | The record is not the ruleset. `tools/rulesets_drift.sh`, run by hand, reads the difference between them |
| What stays | `tools/check_rulesets.py` holds how an approval is counted and whose team owns every path, as 0092 has it, and still lets through a `main` that counts none: it holds the shape, not the day. No check here reads GitHub | A check that refused the earlier state would refuse the undo's record too, when the undo is the urgent thing |

## Why

Through slices 0 and 1 `main` asked for the check and the queue and no review, because the Maintainer authors every pull request and cannot approve his own. The design switches required review on when the Factory's reviewer serves the repo. It does now, so the day and what it rests on are written down where the earlier record said "today".

The switch waited on the dry run, and the dry run ended on 2026-11-11. A Release on `next` reviewed "AGENTS.md: say what is built; drop the model claim no check holds" (pull request 688), the Factory's approving act gave the machine user's approval of its head at 00:25Z, and it merged through the queue at 01:21Z. Seven dry runs before it stopped short of the approval. A ruleset that asks for an approval nothing can give stops every merge, so the approval had to be seen first.

## Boundaries

| Boundary | Check |
|---|---|
| The record is of `main` counting one approval, a code owner's, of the last push, a stale one dismissed, with no required reviewer and nobody bypassing it, read on the day of the switch or after, beside code owners the check accepts | `tests/test_tools.py::test_main_counts_the_machine_users_approval_as_the_switch_left_it`, `config/rulesets.json`; mutant: "the record of main counts no approval"; mutant: "the record of main asks for no code owner's approval"; mutant: "the record of main counts an approval of an earlier push"; mutant: "the record of main leaves a stale approval standing"; mutant: "the record of main is of the day before the switch"; mutant: "the record of main was read before the switch" |
