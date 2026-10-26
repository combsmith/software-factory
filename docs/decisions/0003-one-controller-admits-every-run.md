# 0003. One Controller admits every Run, from current facts

Status: accepted. Source: decision 3 of `docs/architecture/adr/0013-factory-mvp-reference-architecture.md`,
as it stood on 2026-10-11. That file records how this was reached; this one is the rule.

## Decision

Every Run is admitted by one Controller. It is a poller: one pass evaluates every open Work item
in every repo. An event carries no work; it may only ask for a pass. Hold, budget, duplication
and concurrency are evaluated in the admission function and nowhere else. A Pause is evaluated
there and, before any Factory code runs, by the platform. A Run is
started only from a Decision that a pass recorded.

## Why

The platform loses events, so work found by reading current facts cannot be lost with one. A
single decider has no race to lose and one place for every brake.

## Boundaries

| Boundary | Check |
|---|---|
| The admission function takes no event payload | `tests/test_decide.py::test_admission_is_given_facts_and_never_an_event` |
| At most one Run is active per Work item, counting one still waiting for a runner | `tests/test_decide.py::test_one_writer_per_item`, `tests/test_simulator.py::test_invariants_hold_under_faults` |
| An outside item gets no Run until the Maintainer admits it, and admission lapses on the next push | `tests/test_decide.py::test_outside_item_gets_no_run_until_admitted`, `tests/test_decide.py::test_admission_lapses_on_the_next_push` |
| Attempts are counted since the last action by a person with write access | `tests/test_decide.py::test_a_writers_action_grants_a_fresh_allowance`, `tests/test_decide.py::test_with_no_writers_action_every_run_counts`, `tests/test_simulator.py::test_an_approval_that_never_lands_is_bounded` |
| A fault of capacity or of the environment is not an attempt | `tests/test_decide.py::test_capacity_and_environment_faults_are_not_attempts`, `tests/test_decide.py::test_an_approval_that_fails_for_capacity_or_environment_is_not_an_attempt` |
| An approval is a Run with no Engine. One that does not land is bounded by its attempts, and a writer's action renews them | `tests/test_decide.py::test_an_approval_that_does_not_land_is_bounded`, `tests/test_decide.py::test_an_approval_that_landed_is_enqueued_whatever_failed_before`, `tests/test_simulator.py::test_an_approval_that_never_lands_is_bounded`, `tests/test_approve.py::test_each_fault_of_the_act_is_classed_as_the_design_classes_it` |
| An approval that lands is an act, and does not count toward the Run ceiling, which is the cost ceiling | `tests/test_decide.py::test_an_approval_run_does_not_count_toward_the_run_ceiling` |
| An approval that does not land, whatever its fault, counts toward the Run ceiling, so one failing for the environment is not issued for ever | `tests/test_decide.py::test_an_approval_that_keeps_failing_for_the_environment_is_bounded`, `tests/test_simulator.py::test_an_approval_that_keeps_failing_for_the_environment_is_bounded`, `tests/test_approve.py::test_each_fault_of_the_act_is_classed_as_the_design_classes_it` |
| A count the completed Runs have spent holds the item, whatever Run waits and whatever would defer; a superseded Run is no attempt, and an act, the act ceiling's among them, waits for the Run | `tests/test_decide.py::test_spent_attempts_hold_the_item_while_a_run_waits`, `tests/test_decide.py::test_spent_rounds_hold_the_item_while_a_run_waits`, `tests/test_decide.py::test_a_spent_count_holds_whatever_would_defer_while_a_run_waits`, `tests/test_decide.py::test_a_run_in_flight_is_held_by_the_completed_runs_alone`, `tests/test_decide.py::test_an_act_waits_for_a_run_in_flight`, `tests/test_simulator.py::test_invariants_hold_under_faults` |
| Under a Pause, or one that cannot be read, every Hold the brakes give unpaused is given unchanged, with a Run in flight or none, on a pull request and an issue: a Hold is a reading and no act, and a Pause leaves each item where it is | `tests/test_decide.py::test_under_a_pause_spent_attempts_hold_the_item_with_no_run_in_flight`, `tests/test_decide.py::test_under_a_pause_spent_rounds_hold_the_item`, `tests/test_decide.py::test_under_a_pause_a_spent_run_ceiling_holds_the_item`, `tests/test_decide.py::test_under_a_pause_spent_approvals_hold_the_item`, `tests/test_decide.py::test_under_a_pause_the_act_ceiling_holds_the_item`, `tests/test_transitions.py::test_a_pause_changes_no_hold`, `tests/test_issue.py::test_under_a_pause_a_spent_count_holds_the_issue_with_a_run_in_flight_or_none`, `tests/test_simulator.py::test_under_a_pause_a_spent_count_shows` |
| The Run ceiling holds only a pull request that wants a Run or an approval; one that wants neither is not held by it, with a Run in flight or none | `tests/test_decide.py::test_the_run_ceiling_holds_no_item_that_wants_no_run`, `tests/test_decide.py::test_the_run_ceiling_holds_no_item_that_wants_no_run_while_a_run_waits` |
| A failed model Run is not an approval attempt | `tests/test_decide.py::test_a_failed_model_run_is_not_an_approval_attempt` |
| Acts since a person with write access acted are held to `max_acts_per_item`; an unreadable count makes no act | `tests/test_decide.py::test_acts_are_bounded`, `tests/test_decide.py::test_an_unreadable_count_of_acts_makes_no_act`, `examples/invalid/facts.no-count-of-acts.json`, `tests/test_simulator.py::test_a_queue_that_ejects_every_time_is_bounded` |
| The act ceiling stops acts that move work on, and nothing else: a Run is bounded by the Run ceiling, and a Hold is never refused | `tests/test_decide.py::test_the_act_ceiling_stops_acts_and_nothing_else` |
| A dequeue, an act that stops work, is never refused at the act ceiling, and a Run in progress does not delay it | `tests/test_decide.py::test_a_dequeue_is_never_refused_at_the_act_ceiling`, `tests/test_decide.py::test_a_run_in_progress_does_not_keep_a_pull_request_in_the_queue`, `tests/test_simulator.py::test_a_dequeue_at_the_act_ceiling_is_the_one_act_past_it` |
| Every Hold takes a queued pull request out of the merge queue, the one change the Factory makes to a held item; hands-off never acts, and an item that is not served is left alone | `tests/test_decide.py::test_a_hold_takes_a_queued_pull_request_out`, `tests/test_decide.py::test_every_hold_takes_a_queued_pull_request_out`, `tests/test_decide.py::test_an_approver_who_is_the_author_or_last_pusher_takes_it_out_of_the_queue`, `tests/test_decide.py::test_a_draft_leaves_the_queue_and_an_unserved_item_is_left_alone` |
| Acts are counted from GitHub's timeline: each approval, enqueue, dequeue and label a Factory identity made, since a person with write access acted | `tests/test_adapters.py::test_who_last_acted_with_write_access_and_the_factorys_acts_since` |
| A Hold binds from when anyone adds it until a person removes it: one an App or anyone else took off still binds, on a queued item too | `tests/test_decide.py::test_a_hold_that_anyone_but_a_person_removed_still_binds`, `tests/test_simulator.py::test_what_an_app_does_in_a_persons_place_ends_nothing` |
| Hands-off binds only when a person placed it, until a person removes it; placed by anyone else it is read as a Hold, and takes a queued item out | `tests/test_decide.py::test_hands_off_binds_only_when_a_person_placed_it`, `tests/test_simulator.py::test_what_an_app_does_in_a_persons_place_ends_nothing` |
| An outside item is admitted only by a person with write access, after its author's latest push | `tests/test_decide.py::test_admit_admits_only_when_a_person_placed_it` |
| Who added and who removed each label is read from the timeline's events, in the order they happened, and in the same second each label is read the way that stops work; one that cannot be read defers for the Maintainer, and takes a queued item out | `tests/test_decide.py::test_label_events_are_read_in_the_order_they_happened`, `tests/test_decide.py::test_in_the_same_second_each_label_fails_closed`, `tests/test_decide.py::test_a_label_event_that_cannot_be_read_defers`, `examples/invalid/facts.a-label-event-without-who-made-it.json` |
| Anyone else placing a label again does not replace a person's placement: hands-off stays a person's, and an admission keeps the person's time | `tests/test_decide.py::test_what_a_person_placed_is_not_replaced_by_anyone_else_placing_it` |
| Hands-off is never read from a timeline read short: a queued item it would leave alone is taken out | `tests/test_decide.py::test_hands_off_is_not_read_from_a_timeline_read_short` |
| A missing or unreadable Pause or capacity reading admits nothing | `tests/test_decide.py::test_unreadable_pause_defers`, `tests/test_decide.py::test_an_unreadable_pause_stops_approvals_and_merges`, `tests/test_decide.py::test_unreadable_capacity_defers` |
| Each brake is a rule a test would miss if it were removed | `tools/mutants.py` |
| A Pause stops approvals and merges as well as Runs | `tests/test_decide.py::test_a_pause_stops_approvals_and_merges_too`, `tests/test_simulator.py::test_invariants_hold_under_faults` |
| Under a Pause, or one that cannot be read, a dequeue defers, as every act does, and the item is the Maintainer's to see | `tests/test_decide.py::test_under_a_pause_a_dequeue_defers_for_the_maintainer`, `tests/test_simulator.py::test_a_pause_admits_nothing_and_stops_every_act` |
| Under a Pause, a Hold the facts establish is shown first: the approver may not be the author or last pusher | `tests/test_decide.py::test_under_a_pause_a_hold_the_facts_establish_shows_first` |
| A Run's lane is one concurrency group for each Work item, declared on the job, and never cancels what is running | `tests/test_tools.py::test_a_runs_lane_is_its_item_on_the_job_and_cancels_nothing_running`, `examples/workflows/invalid/lane.cancels-the-run-in-progress.yml` |
| Work is never lost once faults stop | `tests/test_simulator.py::test_work_is_never_lost_once_faults_stop` |
| A run record counts only if it is the Factory's own workflow, on the default branch, started by a schedule or a dispatch | `tests/test_adapters.py::test_only_a_dispatch_of_a_role_workflow_from_the_default_branch_in_this_repo_counts`, `tests/test_adapters.py::test_a_status_or_a_conclusion_github_would_not_give_a_run_makes_the_list_short` |
| A human Pause holds even when Factory code is broken; a Run ceiling is enforced outside `kernel/` | waiting on `.github/workflows/poller.yml` |
| One workflow, the one that carries a Run, is the only one that references an LLM credential | waiting on `.github/workflows/run.yml` |
| A Run and an act are held back under a Pause on an issue's seeds | `tests/test_issue_simulator.py::test_invariants_hold_under_faults` |
| On a person's hold or close of an issue, the Controller dequeues the Factory's pull request for it, with the Lifecycle transition recorded, so that no merge lands while the issue is held or declined: the Maintainer's ruling on "Design: does a merge end a held or a declined issue? The issue world met it on seeds 20, 22 and 99" (issue 227) | waiting on `adapters/issues.py`, which reads the issue's hold or close for its pull request; the write's half is the dequeue's, in the effects port's next part |
