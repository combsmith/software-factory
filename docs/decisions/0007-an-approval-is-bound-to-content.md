# 0007. An approval is bound to content

Status: accepted. Source: decision 7 of `docs/architecture/adr/0013-factory-mvp-reference-architecture.md`,
as it stood on 2026-10-11. That file records how this was reached; this one is the rule.

## Decision

Each verdict is bound to a content identity: a hash of the pull request's own diff against its
merge base. Approval is decided in one Kernel function, from Findings and human transitions. A
review thread or a request for changes from a person with write access always gates. A plain
comment steers and gates nothing. A Finding is decided by the Role that owns its category, never
by the Role whose work it is about.

## Why

An approval that outlives the content it judged is how unreviewed changes merge. A comment has no
resolved state, so a gate built on comments can never be closed.

## Boundaries

| Boundary | Check |
|---|---|
| An approval of other content does not stand, and a review of other content does not count | `tests/test_decide.py::test_an_approval_of_other_content_does_not_stand`, `tests/test_decide.py::test_a_review_of_other_content_does_not_count` |
| Unchanged content causes no new review Run | `tests/test_decide.py::test_unchanged_content_causes_no_new_review` |
| An approval is issued only when the change has converged | `tests/test_decide.py::test_approval_is_issued_only_when_converged` |
| A thread from a person with write access gates; a stranger's does not | `tests/test_decide.py::test_a_writer_thread_gates_whatever_its_severity`, `tests/test_decide.py::test_a_strangers_thread_does_not_gate` |
| An answered thread goes to its owner, not back to the author, even when the answer is new content | `tests/test_decide.py::test_an_answer_that_is_new_content_still_goes_to_the_owner` |
| A person's thread is closed only by that person | `tests/test_decide.py::test_an_answered_human_thread_waits_for_that_person` |
| A person's thread resolved by anyone but that person stays open; a Lens's resolved by anyone but that Lens's own App or a person stays open, the author agent's resolution among them; on a queued item either takes it out | `tests/test_decide.py::test_a_persons_thread_resolved_by_anyone_but_that_person_stays_open`, `tests/test_decide.py::test_a_lens_thread_resolved_by_anyone_but_that_lens_or_a_writer_stays_open`, `tests/test_simulator.py::test_what_an_app_does_in_a_persons_place_ends_nothing` |
| A thread says whether it is resolved, exactly, and a resolved one says who resolved it; one that does not, or that names a resolver while open, defers for the Maintainer | `tests/test_decide.py::test_a_thread_whose_resolution_cannot_be_read_defers`, `examples/invalid/facts.a-thread-resolved-by-a-name-alone.json` |
| Only a person ends a request for changes: no App's, Lens's, machine user's or stranger's dismissal or approval does | `tests/test_decide.py::test_only_a_person_ends_a_request_for_changes` |
| A security Finding is never accepted as declined or deferred | `tests/test_tools.py::test_security_may_never_be_declined` |
| Nothing merges without an approval of the merged content | `tests/test_simulator.py::test_invariants_hold_under_faults` |
| A request for changes from a person with write access gates, as that person's thread does; a stranger's or a Lens's gates nothing | `tests/test_decide.py::test_a_writers_request_for_changes_does_not_converge`, `tests/test_decide.py::test_a_strangers_request_for_changes_does_not_gate` |
| A request for changes stands until that person approves or a person with write access dismisses it. New content, a review that only comments, someone else's approval and an App's dismissal do not clear it | `tests/test_decide.py::test_a_request_for_changes_stands_until_that_person_reviews_again` |
| A request for changes an App dismissed still stands. A dismissed approval approves no content, and still ends that person's earlier request; a dismissed comment changes nothing | `tests/test_decide.py::test_a_request_for_changes_an_app_dismissed_still_stands`, `tests/test_decide.py::test_a_dismissed_approval_neither_gates_nor_approves` |
| Neither the machine user nor the bot that opened an agent's or a dependency update's pull request ends a request, whatever kind the facts give them | `tests/test_decide.py::test_neither_the_machine_user_nor_an_author_bot_ends_a_request` |
| A request and an approval by one person in the same second leave the request standing | `tests/test_decide.py::test_a_request_and_an_approval_in_the_same_second_leave_the_request_standing` |
| A request for changes or a thread from a person with write access, made while the pull request is in the merge queue, takes it out of the queue | `tests/test_decide.py::test_a_request_for_changes_made_while_queued_takes_it_out_of_the_queue`, `tests/test_decide.py::test_a_queued_pull_request_with_no_approval_leaves_the_queue`, `tests/test_simulator.py::test_what_happens_while_queued_takes_the_item_out_before_it_merges` |
| A standing approval never passes over a request for changes | `tests/test_decide.py::test_a_request_for_changes_is_read_after_the_checks_and_before_the_approval` |
| A review that cannot be read whole defers for the Maintainer to see, and is never counted as cleared: its time in another format, what a dismissed one was, or dismissal fields on one not dismissed among it | `tests/test_decide.py::test_an_unreadable_review_never_converges`, `tests/test_decide.py::test_an_unreadable_dismissed_from_defers`, `tests/test_decide.py::test_a_review_time_in_another_format_is_unreadable`, `tests/test_decide.py::test_a_review_not_dismissed_that_carries_dismissal_fields_is_unreadable` |
| An unreadable review admits nothing, and is read after what needs no review. On a queued item it is a stop: the item leaves the merge queue | `tests/test_decide.py::test_an_unreadable_review_admits_nothing`, `tests/test_decide.py::test_an_unreadable_review_is_read_after_what_needs_no_review`, `tests/test_decide.py::test_a_read_that_fails_takes_a_pull_request_out_of_the_queue` |
| A pull request stays in the merge queue only while, read as if it were not queued, it would be approved and ready to merge. It leaves when its approval is lost, a gate opens, a required check fails or gives no verdict, or a read fails. A wait that ends on its own leaves it in | `tests/test_decide.py::test_a_queued_pull_request_with_no_approval_leaves_the_queue`, `tests/test_decide.py::test_a_check_that_no_longer_passes_takes_it_out_of_the_queue`, `tests/test_decide.py::test_a_normal_wait_leaves_a_pull_request_in_the_queue`, `tests/test_decide.py::test_a_read_that_fails_takes_a_pull_request_out_of_the_queue`, `tests/test_simulator.py::test_the_seeds_take_a_pull_request_out_of_the_queue_for_each_cause` |
| A merge without a standing independent approval has an Override record | waiting on `controller/reconcile.py` |
| The Factory updates a branch only when it conflicts with its base | waiting on `harness/push.py`, the fix Intent's push |
