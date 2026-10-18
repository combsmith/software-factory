# 0031. What is admitted on an issue, and when apply refuses

Status: accepted. Taken as a working ruling for "Kernel: what is admitted on an issue, and when `apply` refuses"
(issue 42) on 2026-10-17, which the Maintainer may overturn in review.

## Decision

An issue's Admission is one function, `decide(facts, runs, context, config, now)` in `kernel/issue.py`, beside its
`derive`. Its Decision is `issue-decision/1`, in `schemas/issue-decision.schema.json`: a pull request's shape, with an
issue's States, the Controller's three acts and the three Intents. `kernel/decide.py`, `kernel/derive.py`,
`kernel/terms.py`, `kernel/gate.py` and `kernel/brakes.py` are not edited. `kernel/issue.py` imports two names more,
`brakes` and `since_writer`, and has its own maker of a Decision and its own reasons that need a person. The
Controller picks the function by the item's type, as decision 0028 says.

The Controller's acts are Decisions. `place_hold`: the linked pull requests closed in the issue's present life and
since a person last removed `factory:hold` from it number more than `max_unmerged_closes`; a close in the same second
as the life's start or the release is counted. `remove_label`: a `factory:triage` or `factory:ready` stands, from its
latest add, and does not count, in `new`, `triage` or `ready`; never a Hold, an admission or hands-off, never a label a
person added, alone or tied in its second with another's (not counting it is enough, L-17), and not while acceptance
has lapsed, whose labels are what tells the Maintainer that work began. `accept`: at
row 10, once the Controller's App is declared for `factory:triage`, no person has removed it since the content last
changed, and it does not stand, whoever placed it; the brakes' `on_act` bounds it, by the Pause and the act ceiling. Placing a Hold and removing a label are
stopped by the Pause alone. Removing a label also waits while a Run on the issue is in flight, since a readiness Run's
own `factory:ready` does not count until that Run has completed. None is decided once its label is there, or gone.
Every act names the `content_id`, and `remove_label` the label.

In `triage` one Run is admitted at a time. First `investigate-issue`, unless the investigation is current: its Role
completed a successful Run for this `content_id` since `last_writer_action_at`, or, once that record has expired, its
App's entry in `role_comments` is later than both that action and the content's last change. Then `judge-readiness`,
by another Role, unless that Role completed a successful readiness Run for this content since the investigation, or
its App's `factory:ready` or comment is from then or later. A Role's comment or label stands in only while no record
of that Role's Runs of the Intent is kept: a Run that commented and failed has not investigated. And not once
a person removed `factory:ready` since the content changed (I-40). The investigation counts from its first sign. A
failed Run is an attempt, which the brakes bound. Otherwise nothing, with a reason that needs a person. In `ready`,
`open-pull-request`; on an issue a person did not open, only with a statement made after the content changed: the
investigating App's comment, or a comment by a person with write access. While a record of the investigating
Role's Runs is kept, its App's comment is a statement only if one of them succeeded for this content. With neither,
`no_statement`.

`issues.intents` in the configuration maps each Intent to its Role and that Role's App, or to null, which admits
nothing; every one is null by default. Intents that cannot be read, or two that name one Role or one App, defer. A
Run in flight admits nothing, and nothing it wrote is read until it completes. The brakes' Hold still applies: the one
they would have made of each Run in flight, asked of its own Intent and left out of its own count, since it was
admitted under the ceiling. The Pause, the model provider's deferral and the org's concurrency then defer a Run, as on
a pull request. An issue's stale times are not applied yet: what counts as an issue moving is its own question.

Each admission names the `content_id`; the opening Run's names `branch_head` too, a new fact in `issue-facts/1`: the
head of the branch the next opening Run would push to, or null, and a deferral if it cannot be read. `still_admitted`
holds `apply` to the rule of I-21 and I-38: asked again with its own Run left out of the records, the Kernel must admit
the same Role, Intent, content and branch head. `acts_since_writer` is a new fact of `issue-facts/1`, as on a pull
request. `role_comments`, `last_writer_action_at` and `last_writer_comment_at` are read whole, or the issue defers.

Whether a Hold of the brakes also gets the label is decided with `controller/`, for both item types, and §4.1's table
of bounds says so.

## Why

A module of its own keeps the issue's work off the lines the pull request's work changes, as decision 0028 did for the
State. The Controller's acts are Decisions so that every write the Factory makes is one the Kernel decided and a test
can hold. The Controller's App must be declared before it accepts, since a label from an App not declared never
counts, and would be removed and added again for ever. The count of unmerged closes is reset only by a person's
removal of the Hold, which is why the bound places a label at all. A Run in flight is not counted against itself, or
the last Run the ceiling allows would read as held while it ran. A Role's App stands in for its expired run record
because the records are kept 90 days and an issue may wait longer.

## Boundaries

| Boundary | Check |
|---|---|
| The Controller accepts at row 10 once its App is declared, and not again once a person removed factory:triage for this content | `tests/test_issue.py::test_the_controller_accepts_a_new_issue_at_row_10_once_its_app_is_declared`, `tests/test_issue.py::test_a_person_who_removed_triage_since_the_content_changed_is_not_overruled` |
| Until how an act is counted is ruled, the label's presence is the only guard on accepting | `tests/test_issue.py::test_acceptance_is_not_decided_once_triage_is_there_and_the_label_is_the_only_guard` |
| Acceptance is held to the act ceiling and the Pause | `tests/test_issue.py::test_acceptance_is_held_to_the_act_ceiling_and_stopped_by_the_pause` |
| A label that stands and no longer counts is removed, never a Hold, an admission or hands-off, and not under a Run in flight | `tests/test_issue.py::test_a_label_that_stands_and_no_longer_counts_is_removed`, `tests/test_issue.py::test_the_hold_an_admission_and_hands_off_are_never_removed_nor_a_label_once_work_is_linked`, `tests/test_issue.py::test_removing_a_label_is_stopped_by_the_pause_and_waits_for_a_run_in_flight` |
| Unmerged closes at their bound place no Hold, and one past it does, counted in this life since a person released the Hold | `tests/test_issue.py::test_unmerged_closes_past_the_bound_place_a_hold`, `tests/test_issue.py::test_closes_are_counted_in_this_life_since_a_person_released_the_hold` |
| In triage an investigation comes first, and is current once for each content and action by a person with write access | `tests/test_issue.py::test_in_triage_an_investigating_run_is_admitted_first`, `tests/test_issue.py::test_the_investigation_is_current_once_its_role_completed_a_run_for_this_content_since_a_writer_acted`, `tests/test_issue.py::test_once_the_record_has_expired_the_investigating_apps_comment_stands_in` |
| A verdict is given once for each content and investigation, and not after a person removed factory:ready | `tests/test_issue.py::test_a_verdict_is_given_once_for_each_content_and_investigation`, `tests/test_issue.py::test_once_its_record_has_expired_the_readiness_apps_label_or_comment_stands_in`, `tests/test_issue.py::test_a_person_who_removed_ready_since_the_content_changed_overrules_readiness` |
| The opening Run is admitted for its content and branch head, and on an outsider's issue only from a statement | `tests/test_issue.py::test_in_ready_the_opening_run_is_admitted_for_the_content_and_the_branch_head`, `tests/test_issue.py::test_an_outsiders_issue_opens_only_from_a_statement_made_since_its_content_changed` |
| The attempts and the Run ceiling hold at their bound and not before it, and a Run in flight hides no Hold | `tests/test_issue.py::test_the_brakes_bound_investigation_and_readiness`, `tests/test_issue.py::test_a_run_in_flight_admits_nothing_and_the_brakes_hold_still_applies`, `tests/test_issue.py::test_opening_attempts_are_bounded_and_hold_even_while_an_opening_run_is_in_flight` |
| An Intent that is null admits nothing; Intents that cannot be read, or share a Role, defer | `tests/test_issue.py::test_an_intent_not_declared_admits_nothing_and_needs_a_person`, `tests/test_issue.py::test_intents_that_cannot_be_read_or_share_a_role_defer` |
| Asked again with its Run left out, the Kernel refuses it after a label is removed, a Hold added, the content changed or the head moved | `tests/test_issue.py::test_the_opening_run_is_refused_after_a_label_is_removed_a_hold_added_the_content_changed_or_the_head_moved`, `tests/test_issue.py::test_an_investigating_or_readiness_run_is_refused_once_the_issue_changed` |
| Every Decision on an issue is a valid `issue-decision/1`, and a counter-example is rejected | `tests/test_issue.py::test_every_situation_gives_one_valid_decision`, `examples/invalid/issue-decision.sentence-as-reason.json` |
| A Run in flight is read by its own Intent, nothing it wrote is read until it completes, and a Role's comment or label stands in only once no record of its Runs is kept | `tests/test_issue.py::test_nothing_a_run_in_flight_wrote_is_read_until_it_completes`, `tests/test_issue.py::test_a_comment_or_label_stands_in_only_once_every_record_of_its_role_has_expired`, `tests/test_issue.py::test_the_readiness_apps_comment_in_the_second_of_the_investigation_stands_in` |
| Intents that name one App defer, and no label is removed while acceptance has lapsed | `tests/test_issue.py::test_intents_that_share_an_app_defer`, `tests/test_issue.py::test_a_label_is_not_removed_while_acceptance_has_lapsed` |
| Each reason and State calls a person, nobody, or the Factory's next act, as listed; no act is decided whose label stands; a failed investigation's comment is no statement | `tests/test_issue.py::test_each_reason_and_state_calls_whom_it_should`, `tests/test_issue.py::test_no_act_is_decided_whose_label_already_stands`, `tests/test_issue.py::test_a_failed_investigations_comment_is_no_statement` |
| What steers admission, and the branch head, are read whole or defer | `tests/test_issue.py::test_what_steers_admission_is_read_whole_or_defers`, `tests/test_issue.py::test_an_unreadable_branch_head_defers_the_opening_run_alone` |
| An issue's wait past its State's limit in `lifecycle/issue.json`, given with the configuration, shows `stale`: only the attention changes, only on a `ready` wait, and never under a deferral of the whole scope; a Lifecycle not the issue's shows such a wait as stale | `tests/test_issue.py::test_a_wait_past_its_states_limit_shows_stale_and_changes_nothing_else`, `tests/test_issue.py::test_a_person_a_run_nobody_or_a_deferral_of_the_whole_scope_is_never_stale`, `tests/test_issue.py::test_a_wait_counts_no_earlier_than_the_chain_of_passes`, `tests/test_issue.py::test_a_lifecycle_not_the_issues_shows_every_wait_as_stale` |
| An issue moves when its life begins, its content changes, a writer acts or comments, a person or a declared App adds or removes a control label, a Run on it starts, or a linked pull request opens or closes, and at nothing else | `tests/test_issue.py::test_an_issue_moves_at_what_its_own_facts_say_moved_it_and_at_nothing_else` |
| A linked pull request's opening time is read whole, or the issue defers | `tests/test_issue.py::test_a_link_with_no_opening_time_defers`, `examples/invalid/issue-facts.a-link-with-no-opening.json` |
| An issue's Lifecycle whose limit for the State is no finite number of minutes shows the wait as stale; an end the Lifecycle declares never goes stale | `tests/test_issue.py::test_a_lifecycle_whose_limit_cannot_be_read_shows_the_wait_as_stale`, `tests/test_issue.py::test_an_end_never_goes_stale` |
| Any App `issues.label_apps` names moves an issue by any control label it adds or removes; an App named nowhere moves nothing | `tests/test_issue.py::test_any_app_the_configuration_names_moves_an_issue_by_any_control_label` |
| Only the Factory's or a writer's linked pull request moves an issue by opening or closing; an outsider's, even one admitted, moves nothing | `tests/test_issue.py::test_an_outsiders_pull_request_moves_nothing_even_once_admitted` |
| A `now` that is no moment raises nothing on an issue, and shows a wait as stale | `tests/test_issue.py::test_a_now_that_is_no_moment_shows_a_wait_as_stale_and_raises_nothing` |
