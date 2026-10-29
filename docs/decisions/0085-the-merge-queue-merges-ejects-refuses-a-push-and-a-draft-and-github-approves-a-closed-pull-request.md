# 0085. The merge queue merges, ejects, refuses a push and a draft; and GitHub approves a closed pull request

Status: accepted. The second machine-user window's P-2 rest and P-7.refused, under the orchestrator's rulings of
2026-10-28. It adds to decision 0081, and grounds the approving act of
"The approving act refuses a pull request that is not open, since GitHub approves a closed one (P-7.refused)" (issue 378).

## Decision

| What | Decided | Because |
|---|---|---|
| P-2's queue | `trials/P-2.queue.json`: on the canary's `main` with a merge queue and `p2-queue-check` required (kept after the window, for P-37), a person's enqueue is merged by the queue, its merge group checked on the group's own commit; a failing merge group ejects its pull request, unmerged, its approval standing; an App's push to a queued branch is refused, 409; a draft is refused the queue and a person's merge. Fail as written, since the pr-review App cannot use the queue | Each part of P-2 the window could ask, recorded |
| The fake's queue rules | `the_queue_can_eject` is grounded on it. `a_push_leaves_the_queue` and `a_draft_is_not_merged`, which it contradicts, keep the text the fake applies and no fixture, and are named known to differ | A rule is grounded only where the fake does what the fixture shows (L-51) |
| P-7.refused | `trials/P-7.refused.json`, fail on its first case: GitHub took the machine user's approval of a closed pull request, and a reopening with no push brought it back approved; it refused an approval of a commit a push left behind (422) and one after the token was deleted (401). Each run's log shows its inputs and GitHub's refusal; each read names its time | The approving act refuses a pull request that is not open itself ("The approving act refuses a pull request that is not open, since GitHub approves a closed one (P-7.refused)", issue 378) |

## Why

These are the window's answers that were not least permissions: what the queue does with what is put in it, and
what GitHub does with an approval it should not count.

## Boundaries

| Boundary | Check |
|---|---|
| The fixtures' refusals are placed | `tests/test_adapters.py::test_a_recorded_refusal_is_no_answer` |
| A rule a fixture grounds is one the fake applies, or named known to differ | `tools/check_trials.py`, `tests/test_adapters.py::test_the_port_reads_each_grounded_rule_as_the_fake_assumes_it` |
