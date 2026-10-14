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
| A security Finding is never accepted as declined or deferred | `tests/test_tools.py::test_security_may_never_be_declined` |
| Nothing merges without an approval of the merged content | `tests/test_simulator.py::test_invariants_hold_under_faults` |
| A request for changes from a person with write access gates, as that person's thread does | not held yet: `tests/test_decide.py::test_a_writers_request_for_changes_does_not_converge` |
| A pull request that loses its approval leaves the merge queue | not held yet: `tests/test_decide.py::test_a_queued_pull_request_with_no_approval_leaves_the_queue` |
| A merge without a standing independent approval has an Override record | waiting on `controller/` |
| The Factory updates a branch only when it conflicts with its base | waiting on `harness/` |
