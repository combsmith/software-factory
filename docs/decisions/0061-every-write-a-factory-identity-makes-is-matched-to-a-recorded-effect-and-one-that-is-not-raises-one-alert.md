# 0061. Every write a Factory identity makes is matched to a recorded Effect, and one that is not raises one alert

Status: accepted. The working ruling of 2026-10-22 on
"Controller: reconciliation, every write by a Factory identity matched to a recorded Effect (I-33)" (issue 306),
with the Maintainer's answers of 2026-10-22 relayed by the orchestration session.

## Decision

| What | Decided | Because |
|---|---|---|
| Who is reconciled | The machine user, the Controller's App and each Role App, each by its account's id and type as `config/controller.json`'s `accounts` holds it, never a login's spelling; and, once `accounts.workflow_token` is set, the pass job's token, by the records port's runs. Until then no dispatch is reconciled. While an account is not known, reconciliation is short, and the configuration names every Role App | A write by an identity that cannot be told cannot be matched; it is never presumed matched. Ruling 2: no dispatch is sent while the token's account is unset |
| What is read | Per served pull request, the reviews, timeline, review threads and check runs on its head that the facts port read in the same pass, kept by the snapshot of `adapters/facts.py`, so no read is made twice; per served issue, its timeline; per served item, its comments since the window opened; per repo, the machine user's writes to a branch in the last week from its activity, each of the kind its activity type names, asked for by its login and held to its id (`adapters/seen.py`). Of the timeline, every event a Factory write makes, and every one that changes a pull request's state, asks for its review or assigns it, which none makes yet; any other event a Factory identity made that is a write by its actor is `other`, named by its event, so an event GitHub adds alarms rather than going unread. An account is told only by a positive id and a type GitHub gives an actor, a User or a Bot. A dismissed review is read as an approval. A list that cannot be read whole, or a write whose time or key cannot be read, leaves what was seen short | Section 4.9: "each pass compares what the machine user and each App actually did on GitHub with the Effects `apply` recorded". Ruling 3: "not made twice" |
| What it is matched to | A Role's or the approving act's write to the key `applied/1` read back for it, an Effect of its type; the Controller's status to `written/1` by its key; a dequeue, which GitHub gives no key for, by its item, one recorded for each; a dispatch to `written/1`'s dispatch of that Run. A write whose key cannot be read matches nothing. A Run's `applied/1` is read from its artifact as its outcome is (`adapters/artifacts.py`) | Decisions 0051, 0054 and 0055 record each Effect by the key it was read back by |
| What alarms | Any write with no matching Effect: a write no identity may make among them, such as a push by the machine user, a review by it that is no approval, or an act no write serves yet, a close or a dismissal among them. One alert, `write_unmatched`, however many; each named once, by ids and codes, in the view's own field `reconciliation`, every field required, and kept in the pass record under the same name, checked with it before anything is dispatched | The Maintainer, 2026-10-22: "Alarm on all of them". The machine user's approvals with no `approve` Effect alarm on every pull request, his own approvals in the browser included |
| When it is short | What was seen or recorded that cannot be read whole, an account not known, or, once dispatches are reconciled, the records port's list that cannot be read whole, raises `reconciliation_unreadable`. What was read is still reconciled | Never silent: a reconciliation that cannot see is said to be blind |
| A resolution no one is named for | A thread GitHub names no resolver for, as when an App resolved it, raises nothing | GitHub's `resolvedBy` is typed a User, so an App's resolution has no resolver to match |
| An Override | A merge of a served item that the last pass before it read as neither converged nor queued is reported as information, `merged_by_override`, never an alert | Decision 0007's Override row, in scope by the Maintainer's answer 3 |
| Which records are trusted | Only a Run the records port lists, of a Role workflow or of the approving act, has its `applied/1` read, once: its keys are kept in the pass record as `reconciled` for the window | Ruling 4. A record any job could upload could cover a stolen credential's write |

## Why

The machine user's token is long-lived and can approve, and every App's key can write. A write the Factory did not
record means a credential is used outside the Factory. Reconciliation is the detective control that sees it. Each
alert asks the Maintainer to rotate the credential (section 4.9).

The comments read is served by `pull_requests: read`, unverified until a trial of the second token window answers it.
The window leaves out check runs on an older head, writes outside the served items, and resolutions GitHub does not
attribute: stated limits, accepted by the answers. Three more follow from reading what GitHub records of a write's
making: an edit of a write the Factory recorded keeps its key and is not seen, a check run's conclusion among them;
a push after a login renamed and not recorded is not read; and a merge's Override is read only while the merge is in
the window. The extra reads cost one REST read per served item for the comments, one per served issue for its
timeline and one per repo for the activity, beside the reads the facts port makes, which reconciliation shares; and
one artifact download per new Run with Effects. P-8 measured 1,788 GraphQL points an hour and no REST budget near its
limit; these add no GraphQL point.

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
| No read the facts port made is made twice; an issue's timeline is read by the seen port | `tests/test_reconcile.py::test_no_read_the_facts_port_made_is_made_twice` |
| The snapshot keeps its reads for reconciliation only once it is whole | `tests/test_adapters.py::test_a_snapshot_keeps_its_reads_for_reconciliation_only_once_it_is_whole` |
| A list the seen port cannot read whole leaves what was seen short | `tests/test_reconcile.py::test_a_list_that_cannot_be_read_whole_leaves_what_was_seen_short` |
| The machine user's pushes are read from the repo's activity | `tests/test_reconcile.py::test_the_machine_users_pushes_are_read_from_the_repos_activity` |
| A Run's `applied/1` is read whole or not at all | `tests/test_adapters.py::test_a_runs_applied_record_is_read_whole_or_not_at_all` |
| The pass raises one alert, names each write in the view and keeps it in its record | `tests/test_controller.py::test_a_write_no_effect_recorded_raises_one_alert_and_is_named_in_the_view` |
| `pull_requests: read` serves the comments on a pull request | `tests/test_reconcile.py::test_the_comments_on_a_pull_request_are_read_with_pull_requests_read` |
| Trial P-56 answers that on a pull request of the public canary (`trials/P-56.json`): GitHub names `issues=read; pull_requests=read`, and any token reads there. An issue's comments and a private repo stay unasked | `tests/test_reconcile.py::test_the_comments_on_a_pull_request_are_read_with_pull_requests_read` |
| The pass's reads are gathered by the workflow that runs it | waiting on `.github/workflows/poller.yml` |
| Only a listed Run of a Role workflow or of the approving act has its `applied/1` read, once, its keys kept as `reconciled` | waiting on `.github/workflows/poller.yml` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
