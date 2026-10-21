# 0015. A Lens is read from its own App, and only what gates holds a merge

Status: replaced by `docs/decisions/0018-a-lens-is-read-from-its-own-app-and-workflow-and-only-what-gates-holds-a-merge.md`,
which holds the rule in force and its boundaries.

## Decision

Every source of judgement on a Work item, whether a Role, a third-party reviewer, a tool or a
person, is a Lens that reports Findings in one schema. Convergence is a Kernel function: every
required Lens has passed on the current content, and no gating Finding is open. Lenses do not
address each other. A Finding from a Lens outside the required set gates only when a required Lens
adopts it. A required model Lens's Finding gates when it is `blocking` or `major`, and a `security`
one at any severity. One that does not gate, a `minor` or `info` Finding of any category but
`security`, is an annotation on its Lens's check run and has no Disposition: it closes when its
Lens stops reporting it, as a `mechanical` Finding does. A required deterministic Lens gates through
its check's conclusion. It is read only from the App the configuration names for it, by the exact
name of its check run: a check under its name from any other App leaves it unreadable, for the
Maintainer, before any Lens's failure. Every check its own App reports under that name is read, and
it passes only when every one passes. A reviewing Role declares a rubric, which is a floor. A change
that has not converged within its bound is placed on Hold.

## Why

A council of independent Lenses finds more than one reviewer, but only if they stay independent
and something other than their conversation decides. The proof of concept decided by parsing
comments, and waited for reviewers that never answered.

A Disposition for every small Finding would cost Runs and bring back the gate built on every
comment, and closing one as deferred at the merge cannot work: the ruleset requires resolved
threads, so an open one would hold a merge the Kernel approved. An annotation's report still gives
each Finding one outcome, which is counted. Severity is never how a security defect gets merged.

Any App that can write checks can post one under any name, the Controller's among them, and the
ruleset pins only `verify` to its App. Read by name alone, a passing copy could pass a Lens that
failed, or the last of several checks could hide a failure. Once a dependency update is judged by
the deterministic Lenses alone, they are its only judge.

## Boundaries

| Boundary | Check |
|---|---|
| A Finding is a structured record | `schemas/finding.schema.json`, `tools/check_examples.py` |
| A reason is a code, never a sentence | `examples/invalid/decision.sentence-as-reason.json` |
| A required Lens's blocking or major Finding gates; a minor one of any category but `security`, or one from a Lens that is not required, does not | `tests/test_decide.py::test_required_lens_major_finding_gates`, `tests/test_decide.py::test_minor_finding_and_unrequired_lens_do_not_gate` |
| A required Lens's `security` Finding gates at any severity, in the merge queue too; one from a Lens that is not required gates only once a required Lens adopts it | `tests/test_decide.py::test_a_minor_security_finding_gates`, `tests/test_decide.py::test_a_minor_security_finding_opened_while_queued_takes_it_out_of_the_queue`, `tests/test_decide.py::test_a_security_finding_from_a_lens_that_is_not_required_does_not_gate` |
| A required Lens's open thread whose category or severity is missing, null or not in the schema defers for the Maintainer, and takes a queued item out; a thread from a Lens that is not required may carry neither | `tests/test_decide.py::test_a_required_lens_thread_that_cannot_be_read_defers`, `tests/test_decide.py::test_a_read_that_fails_takes_a_pull_request_out_of_the_queue` |
| A thread's category and severity are read from the required Lens's own Finding record, joined by its surface key, never from the comment text | waiting on `adapters/timeline.py` |
| A thread carries its Finding's category, in the authority table's terms, and the Kernel reads the Finding's categories and severities | `tests/test_tools.py::test_the_kernel_reads_the_categories_and_severities_a_finding_carries`, `examples/invalid/facts.a-thread-without-its-category.json`, `examples/invalid/facts.a-category-nobody-owns.json`, `tests/test_tools.py::test_a_thread_carries_the_categories_a_finding_does` |
| A Finding that does not gate is an annotation on its Lens's check run; a Result that posts one on a thread is refused | waiting on `harness/` |
| A required deterministic Lens names the check GitHub reports for it, and that check reports on every head and in the merge queue | waiting on `adapters/checks.py` |
| No model Lens runs on content the deterministic Lenses have not passed | `tests/test_decide.py::test_no_model_review_before_deterministic_checks_pass` |
| Only `success` passes a required check. `failure` and `timed_out` go back to the author, and are read first; queued, running, waiting and absent checks are waited for; a check that gave no verdict, or whose conclusion the map does not name, defers and needs the Maintainer | `tests/test_decide.py::test_a_neutral_required_check_defers`, `tests/test_decide.py::test_a_timed_out_required_check_goes_back_to_the_author`, `tests/test_decide.py::test_a_queued_running_or_absent_required_check_is_waited_for`, `tests/test_decide.py::test_a_failed_check_is_read_before_an_unreadable_or_waiting_one`, `tests/test_decide.py::test_a_failure_with_cancelled_or_skipped_siblings_goes_back_to_the_author` |
| The configuration cannot make a check with no verdict pass | `tests/test_tools.py::test_only_success_can_pass_a_check`, `examples/invalid/config.a-neutral-check-passes.json`, `examples/invalid/config.conclusion-mapped-to-nothing.json` |
| A required deterministic Lens is read only from the App the configuration names for it, by an id that is a whole number: a check with its name from another App, or with no such id, leaves it unreadable, before any Lens's failure or a conflict, on a queued item too, says which App, and moves nothing | `tests/test_decide.py::test_a_check_from_another_app_is_unreadable_for_its_lens`, `tests/test_decide.py::test_a_check_from_another_app_or_a_failure_beside_a_pass_takes_it_out_of_the_queue`, `tests/test_decide.py::test_only_a_check_from_its_lens_app_moves_an_item`, `examples/invalid/facts.a-check-without-its-app.json`, `examples/invalid/config.a-required-lens-with-no-app.json` |
| Every check a Lens's own App reports under its name is read, never the last alone: any failure fails it, and it passes only when every one passes | `tests/test_decide.py::test_every_check_a_lens_reports_from_its_own_app_is_read` |
| Each deterministic Lens names its check run's exact name and its App, and no Lens or check is named twice | `examples/invalid/config.a-required-lens-with-no-check.json`, `tests/test_tools.py::test_a_lens_or_a_check_named_twice_is_refused` |
| The status on the item has one name, and it is no required Lens's or its check's, in any case | `tests/test_tools.py::test_the_status_on_the_item_never_carries_a_required_lens_name` |
| The port gives every check run with its exact name and the real id of its App, from every App, never dropped, merged or renamed | waiting on `adapters/checks.py` |
| A check is a Lens's only under the exact name of the Lens's check: a job its own App runs under the Lens's name, or under the check's name in another case, passes nothing | `tests/test_decide.py::test_a_check_is_matched_to_a_lens_by_its_check_name_alone` |
| Only a re-run of the same job in the same check suite replaces an earlier check run; two workflow runs on one commit both stay, and both are read | waiting on `adapters/checks.py` |
| A dependency update is judged by the deterministic Lenses alone, and needs no model review | `tests/test_decide.py::test_a_dependency_update_needs_no_model_review` |
| A Finding a model Lens has raised gates whatever the class, a dependency update's too, and after the bot recreates the branch | `tests/test_decide.py::test_a_model_lens_thread_gates_a_dependency_update` |
| A dependency update is a dependency bot's pull request whose head that bot pushed; anyone else's push, and every other class, needs the model review | `tests/test_decide.py::test_a_dependency_update_someone_else_pushed_to_needs_a_model_review`, `tests/test_decide.py::test_every_other_class_needs_a_model_review`, `examples/invalid/config.a-change-by-a-person-skips-the-model-review.json` |
| A dependency update skips the model review and nothing else: every deterministic Lens, a person's thread, a Hold and a Pause still bind, and a `neutral` check does not pass it | `tests/test_decide.py::test_a_dependency_update_is_judged_by_every_deterministic_lens`, `tests/test_decide.py::test_a_neutral_check_does_not_pass_a_dependency_update`, `tests/test_decide.py::test_a_writers_thread_still_gates_a_dependency_update`, `tests/test_decide.py::test_a_dependency_update_skips_the_model_review_and_nothing_else` |
| The configuration names at least one deterministic Lens, so no update is approved with no check at all | `examples/invalid/config.no-deterministic-lens.json` |
| `last_pusher` is the identity GitHub records as having pushed the head, never a commit's author or committer; class `dependency` is given only for an exact App identity, and a fork is always `outside` | `tests/test_adapters.py::test_the_newest_push_to_the_head_names_its_pusher_a_person_or_an_app`, `tests/test_adapters.py::test_an_activity_that_has_not_caught_up_with_the_head_names_no_one`, `tests/test_adapters.py::test_a_fork_is_read_as_no_one_and_its_activity_is_never_asked`, `tests/test_adapters.py::test_the_class_is_the_account_named_or_outside` |
| An empty diff never converges | `tests/test_decide.py::test_empty_diff_never_converges` |
| Rounds between author and owner are bounded, and the bound ends in a Hold | `tests/test_decide.py::test_rounds_are_bounded` |
| Every category of Finding has exactly one owner | `tools/check_authority.py` |
| A rubric is data with a schema | `schemas/rubric.schema.json`, `tools/check_examples.py` |
| A reviewing Result reports on every criterion that applies | waiting on `harness/` |
| With an acceptance contract, every criterion has passing evidence on the current content | `tests/test_decide.py::test_with_a_contract_it_converges_only_when_every_criterion_has_passing_evidence` |
| Evidence given on other content does not count, passing or failing | `tests/test_decide.py::test_evidence_for_other_content_does_not_count` |
| A failing result for a criterion on this content goes back to the author, as a failed check does, and is read before a criterion still waiting for its evidence | `tests/test_decide.py::test_a_failing_criterion_goes_back_to_the_author` |
| An item with no acceptance contract converges as it did before contracts were read | `tests/test_decide.py::test_an_item_with_no_contract_converges_as_it_did` |
| A contract, or a result on this content, that cannot be read, or facts that say nothing of a contract, never converge: the Kernel defers for the Maintainer. A criterion's id and a result's content id are read only in the schema's form | `tests/test_decide.py::test_unreadable_acceptance_never_converges`, `examples/invalid/facts.no-word-on-acceptance.json`, `examples/invalid/facts.an-acceptance-result-in-words.json`, `examples/invalid/facts.an-acceptance-result-without-its-content.json`, `examples/invalid/facts.an-acceptance-contract-with-no-criteria.json`, `examples/invalid/facts.an-acceptance-criterion-named-twice.json` |
| Only this content's results are judged: one on earlier content, for a criterion the contract no longer lists or in any word, makes nothing unreadable | `tests/test_decide.py::test_only_this_contents_results_are_judged` |
| Whether the contract, or that there is none, was read in full is `complete.acceptance`: a read short defers as incomplete facts, and no contract converges only on a full read | `tests/test_decide.py::test_a_contract_read_short_is_incomplete`, `examples/invalid/facts.no-completeness-for-acceptance.json` |
| The facts carry a contract's criteria by id, never their statements | `examples/invalid/facts.acceptance-carries-prose.json` |
| The contract is read after the other three conditions of Convergence and before the approval | `tests/test_decide.py::test_acceptance_is_read_after_every_other_condition_of_convergence` |
| A queued item whose evidence is gone, is for other content, fails or cannot be read leaves the merge queue | `tests/test_decide.py::test_a_queued_item_whose_evidence_goes_missing_or_unreadable_leaves_the_queue`, `tests/test_simulator.py::test_a_queued_item_whose_evidence_is_gone_is_taken_out_before_it_merges` |
| A wait for evidence is a wait in `verifying`, and goes stale past its limit | `tests/test_decide.py::test_a_wait_for_acceptance_evidence_goes_stale` |
| The port reads the contract at the head, and each result for a criterion with the content it ran on, from the check that gave it | waiting on `adapters/acceptance.py` |
| The port reports the latest result per criterion per check suite | waiting on `adapters/acceptance.py` |
| A result counts only from the App the configuration allows for its criterion's kind; never from the author's Role. Issue 108, "Kernel: acceptance evidence from the right reporter, against the approved contract" | waiting on `adapters/acceptance.py` |
| The contract read is the one the Maintainer approved, unchanged since; no fix Run on a contract not yet approved (I-29), in the same story | waiting on `harness/` |
| No manifest names another Role's output as a trigger | waiting on `roles/` |
