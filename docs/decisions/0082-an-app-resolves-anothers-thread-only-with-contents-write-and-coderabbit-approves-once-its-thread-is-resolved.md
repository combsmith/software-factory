# 0082. An App resolves another's thread only with contents: write, and CodeRabbit approves once its thread is resolved

Status: accepted. The second machine-user window's threads, P-5 and P-25, under the orchestrator's rulings of
2026-10-28. It adds to decision 0081, whose write rule its fixtures are held to.

## Decision

| What | Decided | Because |
|---|---|---|
| P-5 | `trials/P-5.json`, fail as written: the pr-review App, with every permission it holds, is refused a thread CodeRabbit opened, a person's and the trial-author App's; the trial-author App resolves the two others opened only with `contents: write` | An App resolves another's thread with the same gate the queue has, which no reviewer's App holds |
| The fake's thread rules | `a_lens_review_opens_a_thread` and `an_app_resolves_any_thread` are grounded on P-5, the second with the permission it takes. `an_app_resolves_a_lens_thread`, which P-5 contradicts, keeps the text the fake applies, no fixture, and is named known to differ, until "CodeRabbit's approval follows from its threads being resolved, so it is never counted as a review, and no Role resolves another reviewer's thread" (issue 366) rules who resolves | A rule is grounded only where the fake does what the fixture shows (L-51) |
| P-25 | `trials/P-25.json`, fail: CodeRabbit approved 4 to 6 seconds after its thread was resolved, with no push, and did nothing else in 30 minutes. The canary held no CodeRabbit configuration file, so the feature section 4.2 switches off was on; the trial runs again with it off | Its approval follows from a resolution, so it is never counted as a review ("CodeRabbit's approval follows from its threads being resolved, so it is never counted as a review, and no Role resolves another reviewer's thread", issue 366) |
| A review's text | A review list keeps each review's text only where GitHub sent it empty, as GitHub sent it | A fixture keeps GitHub's words, never a field of its own |

## Why

The window asked whether the reviewer's App can close the threads other reviewers open. It cannot, and the reviewer
that opened one approves when it is closed: both bear on who may resolve another's thread.

## Boundaries

| Boundary | Check |
|---|---|
| P-5's and P-25's refusals are placed | `tests/test_adapters.py::test_a_recorded_refusal_is_no_answer` |
| A rule a fixture grounds is one the fake applies, or named known to differ | `tools/check_trials.py`, `tests/test_adapters.py::test_the_port_reads_each_grounded_rule_as_the_fake_assumes_it` |
