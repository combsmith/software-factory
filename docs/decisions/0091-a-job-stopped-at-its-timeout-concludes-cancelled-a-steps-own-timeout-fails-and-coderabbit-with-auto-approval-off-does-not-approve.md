# 0091. A job stopped at its timeout concludes cancelled, a step's own timeout fails, and CodeRabbit with auto-approval off does not approve

Status: accepted. The second machine-user window's P-42, its step-timeout case run on 2026-10-29, and P-25 run again
with section 4.2's configuration, under the orchestrator's rulings of 2026-10-28 and 2026-10-29.

## Decision

| What | Decided | Because |
|---|---|---|
| P-42 | `trials/P-42.json`, fail as written on `timed_out` alone: a job GitHub stopped at its `timeout-minutes`, in a run no one cancelled, concluded `cancelled`, and so did its check run and its run. The rest held: `neutral`, `skipped` and `cancelled` were unchanged an hour on; each check run carried its name and its App's id; two suites on one commit both stayed; the pr-review App and an Actions job each posted under a required check's name and an unlisted criterion's, and all stayed | The design read a job's timeout as `timed_out`, a failure; GitHub says `cancelled` ("A job stopped at its timeout concludes cancelled, so neither a required check nor a Run reads it as timed_out", issue 388) |
| A step's own timeout | `trials/P-42.step-timeout.json`: a step stopped at its own `timeout-minutes`, below its job's, concludes `failure`, and so do its job and its check run; a later `if: always()` step runs. `continue-on-error` on the step turns all three to `success` | Rule (a) of that issue holds: a job the Factory writes stops its own work under a step limit, with no `continue-on-error` there |
| P-25 | `trials/P-25.second.json`, pass: with the canary's `.coderabbit.yaml` setting `reviews.auto_approvals.enabled: false`, CodeRabbit's review was COMMENTED, and in the 30 minutes after its threads were resolved it neither approved, re-posted, replied nor reopened. The first run's path, a request for changes turned into an approval, did not arise | Section 4.2's remedy holds for the configuration the Factory serves ("CodeRabbit's approval follows from its threads being resolved, so it is never counted as a review, and no Role resolves another reviewer's thread", issue 366) |
| The fake's check rules | `a_push_restarts_the_checks` and `any_app_posts_a_check_under_any_name` are grounded on P-42, each named read in another shape, since the checks port reads the status rollup and P-42 recorded REST lists. `a_check_can_time_out_or_give_no_verdict`, `a_rerun_replaces_only_its_own_run`, `a_check_is_read_by_name_from_every_app` and `a_check_reports_on_its_own` stay unverified, each with why | A rule is grounded only where a fixture shows what the fake assumes (L-51) |

## Why

The window asked how the checks the Kernel reads behave on a head, and whether the reviewer's configuration file is
the remedy the design says it is. The answers fix how a timeout is read and that the remedy stands.

## Boundaries

| Boundary | Check |
|---|---|
| A rule a fixture grounds is one the fake applies, or named read in another shape | `tests/test_adapters.py::test_the_port_reads_each_grounded_rule_as_the_fake_assumes_it` |
| Each fixture holds only redacted reads | `tools/check_trials.py` |
