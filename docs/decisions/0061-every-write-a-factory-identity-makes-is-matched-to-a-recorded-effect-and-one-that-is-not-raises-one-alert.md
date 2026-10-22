# 0061. Every write a Factory identity makes is matched to a recorded Effect, and one that is not raises one alert

Status: accepted. The working ruling of 2026-10-22 on
"Controller: reconciliation, every write by a Factory identity matched to a recorded Effect (I-33)" (issue 306),
with the Maintainer's answers of 2026-10-22 relayed by the orchestration session.

## Decision

| What | Decided | Because |
|---|---|---|
| Who is reconciled | The machine user, the Controller's App and each Role App, each by its account's id and type as `config/controller.json`'s `accounts` holds it, never a login's spelling; and the pass job's token, by the records port's runs. While an account is not known, reconciliation is short | A write by an identity that cannot be told cannot be matched; it is never presumed matched |
| What is read | Per served pull request, with the Controller's App: its reviews, its comments since the window opened, its timeline's events, its review threads and the check runs on its head; per repo, the machine user's pushes from its activity (`adapters/seen.py`). The window is the last day. A list that cannot be read whole, or may be cut short, leaves what was seen short | Section 4.9: "each pass compares what the machine user and each App actually did on GitHub with the Effects `apply` recorded" |
| What it is matched to | A Role's or the approving act's write to the key `applied/1` read back for it, an Effect of its type; the Controller's to `written/1`, its status by key and its dequeue by item; a dispatch to `written/1`'s dispatch of that Run. A Run's `applied/1` is read from its artifact as its outcome is (`adapters/artifacts.py`) | Decisions 0051, 0054 and 0055 record each Effect by the key it was read back by |
| What alarms | Any write with no matching Effect: a write no identity may make among them, such as a push by the machine user, a review by it that is no approval, or an act no write serves yet. One alert, `write_unmatched`, however many; each named in the view by ids and codes, and kept in the pass record | The Maintainer, 2026-10-22: "Alarm on all of them". The machine user's approvals with no `approve` Effect alarm on every pull request, his own approvals in the browser included |
| When it is short | What was seen or recorded that cannot be read whole, the records port's list that cannot be read, or an account not known, raises `reconciliation_unreadable`. What was read is still reconciled | Never silent: a reconciliation that cannot see is said to be blind |
| A resolution no one is named for | A thread GitHub names no resolver for, as when an App resolved it, raises nothing | GitHub's `resolvedBy` is typed a User, so an App's resolution has no resolver to match |
| An Override | A merge of a served item that the last pass read as neither converged nor queued is reported as information, `merged_by_override`, never an alert | Decision 0007's Override row, in scope by the Maintainer's answer 3 |

## Why

The machine user's token is long-lived and can approve, and every App's key can write. A write the Factory did not
record means a credential is used outside the Factory. Reconciliation is the detective control that sees it. Each
alert asks the Maintainer to rotate the credential (section 4.9).

The comments read is served by `pull_requests: read`, unverified until a trial of the second token window answers it.
The window leaves out check runs on an older head, writes outside the served items, and resolutions GitHub does not
attribute: stated limits, accepted by the answers. The extra reads cost one REST read per served item for the
comments and one per repo for the activity, beside the reads the facts port makes; P-8 measured 1,788 GraphQL points
an hour and no REST budget near its limit.

## Boundaries

| Boundary | Check |
|---|---|
| Each write is matched to the Effect that recorded it, by its key and type; another key, another type, or one that did not land is unmatched | `tests/test_reconcile.py::test_each_write_is_matched_to_the_effect_that_recorded_it` |
| The Controller's writes are matched to what its pass recorded; an act no write serves yet alarms | `tests/test_reconcile.py::test_the_controllers_writes_are_matched_to_what_the_pass_recorded` |
| A write no identity may make alarms whatever was recorded | `tests/test_reconcile.py::test_a_write_no_identity_may_make_alarms_whatever_was_recorded` |
| Every machine-user approval with no record alarms, the Maintainer's own included | `tests/test_reconcile.py::test_every_machine_user_approval_with_no_record_alarms_the_maintainers_own_included` |
| Many unmatched writes raise one alert, and each is named | `tests/test_reconcile.py::test_many_unmatched_writes_raise_one_alert_and_each_is_named` |
| A resolution GitHub names no resolver for raises nothing | `tests/test_reconcile.py::test_a_resolution_github_names_no_resolver_for_raises_nothing` |
| A dispatch is matched by its Run to the pass that sent it | `tests/test_reconcile.py::test_a_dispatch_is_matched_by_its_run_to_the_pass_that_sent_it` |
| What cannot be read whole is short, never silent | `tests/test_reconcile.py::test_what_cannot_be_read_whole_is_short_never_silent` |
| A merge no pass read as mergeable is an Override, reported as information | `tests/test_reconcile.py::test_a_merge_no_pass_read_as_mergeable_is_an_override_reported_as_information` |
| The seen port reads each identity's writes by its account, never its login | `tests/test_reconcile.py::test_each_identitys_writes_are_read_by_its_account_never_its_login` |
| A list the seen port cannot read whole leaves what was seen short | `tests/test_reconcile.py::test_a_list_that_cannot_be_read_whole_leaves_what_was_seen_short` |
| The machine user's pushes are read from the repo's activity | `tests/test_reconcile.py::test_the_machine_users_pushes_are_read_from_the_repos_activity` |
| A Run's `applied/1` is read whole or not at all | `tests/test_adapters.py::test_a_runs_applied_record_is_read_whole_or_not_at_all` |
| The pass raises one alert, names each write in the view and keeps it in its record | `tests/test_controller.py::test_a_write_no_effect_recorded_raises_one_alert_and_is_named_in_the_view` |
| `pull_requests: read` serves the comments on a pull request | `tests/test_reconcile.py::test_the_comments_on_a_pull_request_are_read_with_pull_requests_read`, not held yet: a trial of the second token window |
| The pass's reads are gathered by the workflow that runs it | waiting on `.github/workflows/poller.yml` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
