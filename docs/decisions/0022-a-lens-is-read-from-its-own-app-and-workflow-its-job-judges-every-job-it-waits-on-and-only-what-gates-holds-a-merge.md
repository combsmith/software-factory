# 0022. A Lens is read from its own App and workflow, its job judges every job it waits on, and only what gates holds a merge

Status: replaced by `docs/decisions/0026-a-lens-is-read-from-its-own-app-and-workflow-its-job-judges-every-job-it-waits-on-and-only-what-gates-holds-a-merge.md`,
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
name of its check run, and, where GitHub Actions runs it, only from the path of the workflow file
the configuration names: a check under its name from any other App, from another path, or with no
path read, leaves it unreadable, for the Maintainer, before any Lens's failure. The pin is to the
path, not to what the file at that path says. A Lens no workflow
runs names none, and is read only from a check that names none. Every check its own App and file
report under that name is read, and it passes only when every one passes. A Lens's job that waits
on other jobs runs under exactly `if: always()`, waits on every other job in its file, and fails
unless each of them passed. A reviewing Role
declares a rubric, which is a floor. A change that has not converged within its bound is placed on
Hold.

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

GitHub Actions is one App for every job in the repo, so a pin to the App alone binds `verify` and the
secret scan to any Actions job under their check's name, one a pull request adds in a workflow file
of its own among them. The path of the workflow file is the narrowest thing GitHub records of what
ran a check, so a job from another path is not the Lens.

The pin holds the path and nothing more. A pull request from a branch of this repo can change the
file at that path, and its check still reports from it; so can a dependency bot's security update,
which edits the pins in workflow files and, as class `dependency`, has no model review. `verify` also
runs the pull request's own Makefile, tools and tests, and the secret scan reads its own
`.gitleaks.toml`. What holds `.github/` today is: GitHub refusing an App's push there without the
`workflows` permission, which no Factory App holds (`config/apps.json`, `tools/check_apps.py`); the
admission of a fork's pull request by a person, after its last push (I-36); a Role's `apply`, waiting
on `harness/`; and the session hooks, locally. The `main` ruleset requires no review, and pins only
`verify` to its App; pinning each required check is the Maintainer's, in the repo's settings, with
"The Factory repo's rulesets hold the Release tags and each required check's App" (issue 62). That a
change to a Lens's inputs, or to the Factory's own rules, needs a person is
"Kernel: a change to the Factory's own rules or a Lens's inputs needs a person" (issue 113). Whether
an upload to code scanning under CodeQL's tool and category can replace the CodeQL verdict is a
platform fact not yet tried: the fake GitHub assumes it cannot.

The mutation check outgrew one job: `verify` ran it after `make verify`, and the two took up to half
an hour. Run in shards beside the checks, it must still hold `verify`, the one check the ruleset pins
to its App. With a plain `needs:`, `verify` is skipped when a shard fails, and GitHub passes a required
check that is skipped. `!cancelled()` skips it on a cancel, a result uploaded by each shard is still
missing when one crashes, and a required check for each shard would put the count of shards in the
ruleset. `if: always()` is the one job-level `if:` that cannot skip the job, so `verify` reports
whatever the jobs it needs did, and `tools/needs_passed.py` fails it unless every one ended `success`.
A job left out of its `needs:` is a check nobody requires, so it needs every other job in its file.

## Boundaries

| Boundary | Check |
|---|---|
| A Finding is a structured record | `schemas/finding.schema.json`, `tools/check_examples.py` |
| A reason is a code, never a sentence | `examples/invalid/decision.sentence-as-reason.json` |
| A required Lens's blocking or major Finding gates; a minor one of any category but `security`, or one from a Lens that is not required, does not | `tests/test_decide.py::test_required_lens_major_finding_gates`, `tests/test_decide.py::test_minor_finding_and_unrequired_lens_do_not_gate` |
| A required Lens's `security` Finding gates at any severity, in the merge queue too; one from a Lens that is not required gates only once a required Lens adopts it | `tests/test_decide.py::test_a_minor_security_finding_gates`, `tests/test_decide.py::test_a_minor_security_finding_opened_while_queued_takes_it_out_of_the_queue`, `tests/test_decide.py::test_a_security_finding_from_a_lens_that_is_not_required_does_not_gate` |
| A required Lens's open thread whose category or severity is missing, null or not in the schema defers for the Maintainer, and takes a queued item out; a thread from a Lens that is not required may carry neither | `tests/test_decide.py::test_a_required_lens_thread_that_cannot_be_read_defers`, `tests/test_decide.py::test_a_read_that_fails_takes_a_pull_request_out_of_the_queue` |
| A thread's category and severity are read from the required Lens's own Finding record, joined by its surface key, never from the comment text | a person's thread is `human`, and a Lens's has neither until the join: `tests/test_adapters.py::test_each_thread_is_read_with_who_opened_and_resolved_it_and_a_persons_is_human`; the join, from the record `harness/apply.py` uploads, by `adapters/applied.py` (decision 0069): `tests/test_adapters.py::test_a_lens_thread_takes_its_category_from_its_one_finding_the_lens_owns`, `tests/test_adapters.py::test_a_recorded_thread_is_its_lenss` |
| A thread carries its Finding's category, in the authority table's terms, and the Kernel reads the Finding's categories and severities | `tests/test_tools.py::test_the_kernel_reads_the_categories_and_severities_a_finding_carries`, `examples/invalid/facts.a-thread-without-its-category.json`, `examples/invalid/facts.a-category-nobody-owns.json`, `tests/test_tools.py::test_a_thread_carries_the_categories_a_finding_does` |
| A Finding that does not gate is an annotation on its Lens's check run; a Result that posts one on a thread is refused | `tests/test_apply.py::test_effects_the_task_does_not_permit_or_findings_posted_other_than_once_write_nothing` |
| A required deterministic Lens names the check GitHub reports for it, and that check reports on every head and in the merge queue | `tests/test_adapters.py::test_every_check_run_on_the_head_is_read_with_its_name_app_and_workflow`; that the check reports on every head and in the merge queue is not held yet: `tests/test_adapters.py::test_a_required_check_reports_on_every_head_and_a_rerun_replaces_only_its_own` |
| No model Lens runs on content the deterministic Lenses have not passed | `tests/test_decide.py::test_no_model_review_before_deterministic_checks_pass` |
| Only `success` passes a required check. `failure` and `timed_out` go back to the author, and are read first; queued, running, waiting and absent checks are waited for; a check that gave no verdict, or whose conclusion the map does not name, defers and needs the Maintainer | `tests/test_decide.py::test_a_neutral_required_check_defers`, `tests/test_decide.py::test_a_timed_out_required_check_goes_back_to_the_author`, `tests/test_decide.py::test_a_queued_running_or_absent_required_check_is_waited_for`, `tests/test_decide.py::test_a_failed_check_is_read_before_an_unreadable_or_waiting_one`, `tests/test_decide.py::test_a_failure_with_cancelled_or_skipped_siblings_goes_back_to_the_author` |
| The configuration cannot make a check with no verdict pass | `tests/test_tools.py::test_only_success_can_pass_a_check`, `examples/invalid/config.a-neutral-check-passes.json`, `examples/invalid/config.conclusion-mapped-to-nothing.json` |
| A required deterministic Lens is read only from the App the configuration names for it, by an id that is a whole number: a check with its name from another App, or with no such id, leaves it unreadable, before any Lens's failure or a conflict, on a queued item too, says which App, and moves nothing | `tests/test_decide.py::test_a_check_from_another_app_is_unreadable_for_its_lens`, `tests/test_decide.py::test_a_check_from_another_app_or_a_failure_beside_a_pass_takes_it_out_of_the_queue`, `tests/test_decide.py::test_only_a_check_from_its_lens_app_moves_an_item`, `examples/invalid/facts.a-check-without-its-app.json`, `examples/invalid/config.a-required-lens-with-no-app.json` |
| Every check a Lens's own App and workflow file report under its name is read, never the last alone: any failure fails it, and it passes only when every one passes | `tests/test_decide.py::test_every_check_a_lens_reports_from_its_own_app_is_read` |
| A required deterministic Lens that GitHub Actions runs is read only from the path of the workflow file the configuration names for it, exactly: a check with its name from another path of its App, or with no path read, leaves it unreadable, before any Lens's failure or a conflict, on a queued item too, says which path, and moves nothing. One from another App is shown as another App's, whatever path it names | `tests/test_decide.py::test_a_check_from_another_workflow_is_unreadable_for_its_lens`, `tests/test_decide.py::test_a_check_from_another_workflow_takes_it_out_of_the_queue`, `tests/test_decide.py::test_only_a_check_from_its_lens_workflow_moves_an_item`, `examples/invalid/facts.a-check-without-its-workflow.json` |
| A Lens no workflow runs names none, and is read only from a check that names none | `tests/test_decide.py::test_a_check_from_another_workflow_is_unreadable_for_its_lens`, `tests/test_decide.py::test_only_a_check_from_its_lens_workflow_moves_an_item` |
| Each deterministic Lens names its workflow file, and one whose App is GitHub Actions names one; one of another App names none | `examples/invalid/config.a-required-lens-with-no-workflow.json`, `tests/test_tools.py::test_a_lens_run_by_actions_names_its_workflow_and_no_other_does` |
| The file a Lens names exists, runs on both `pull_request` and `merge_group`, and has a job whose own `name:`, or whose id where it has none, is the Lens's check, with no `strategy.matrix` or `uses:`, and no job-level `if:` but exactly `always()` beside `needs:`; a workflow's or a step's `name:` names no check | `tests/test_tools.py::test_a_lens_read_from_a_workflow_that_does_not_run_its_check_is_caught`, `tests/test_tools.py::test_only_a_jobs_own_name_or_its_id_names_a_lens_check`, `tests/test_tools.py::test_a_lens_job_that_would_never_report_under_its_name_is_caught` |
| A Decision shows a workflow path only in the form a Lens's workflow takes, `.github/workflows/` and a name of letters, digits, `.`, `_` and `-` ending .yml or .yaml, no longer than `max_path_length`; any other, dynamic paths among them, is shown `unreadable` | `tests/test_decide.py::test_a_workflow_path_is_shown_only_in_its_form` |
| No Factory App holds `workflows` or `security_events`, and no workflow grants a job `security-events: write` | `tests/test_tools.py::test_no_app_may_change_a_workflow_or_upload_to_code_scanning`, `examples/workflows/invalid/permissions.security-events-on-a-job.yml` |
| The port gives each check run GitHub Actions reports with the path of its check suite's workflow run as GitHub gives it, a dynamic one verbatim, and null only for a check no workflow ran | `tests/test_adapters.py::test_every_check_run_on_the_head_is_read_with_its_name_app_and_workflow`; a dynamic workflow's path is not held yet: `tests/test_adapters.py::test_a_dynamic_workflows_path_is_read_as_github_gives_it` |
| A Role's change to a Lens's own workflow file, a change under `.github/`, is refused unless a person approved it; a change by anyone to a Lens's inputs needs a person, "Kernel: a change to the Factory's own rules or a Lens's inputs needs a person" (issue 113) | waiting on `harness/push.py`, the fix Intent's push |
| Whether an upload to code scanning under CodeQL's tool and category, by an identity holding `security_events: write`, can replace the CodeQL verdict is a platform fact, unverified until trial P-36 grounds it | `sim/grounding.py`, `tools/check_trials.py` |
| A Lens's job with `needs:` has `if: always()`, needs every other job in its file, runs `python3 -m tools.needs_passed` on a line of its own, as its one step but a checkout, and no `if:` can skip it, and gives it `NEEDS: ${{ toJSON(needs) }}` once, in the job's own env | `tests/test_tools.py::test_a_lens_job_that_would_never_report_under_its_name_is_caught` |
| The required check passes only when what it needs can be read, names at least one job, and each ended exactly `success`: a failed, cancelled or skipped job fails it | `tests/test_tools.py::test_the_required_check_fails_unless_every_job_it_needs_passed` |
| Every mutant is in exactly one shard; a shard that cannot be read, or that holds none, fails its run before any test runs | `tests/test_tools.py::test_every_mutant_is_in_exactly_one_shard`, `tests/test_tools.py::test_a_shard_is_read_from_the_matrix_or_the_run_stops` |
| Each deterministic Lens names its check run's exact name and its App, and no Lens or check is named twice | `examples/invalid/config.a-required-lens-with-no-check.json`, `tests/test_tools.py::test_a_lens_or_a_check_named_twice_is_refused` |
| The status on the item has one name, and it is no required Lens's or its check's, in any case | `tests/test_tools.py::test_the_status_on_the_item_never_carries_a_required_lens_name` |
| The port gives every check run with its exact name and the real id of its App, from every App, never dropped, merged or renamed | `tests/test_adapters.py::test_every_check_run_on_the_head_is_read_with_its_name_app_and_workflow` |
| A check is a Lens's only under the exact name of the Lens's check: a job its own App runs under the Lens's name, or under the check's name in another case, passes nothing | `tests/test_decide.py::test_a_check_is_matched_to_a_lens_by_its_check_name_alone` |
| Only a re-run of the same job in the same check suite replaces an earlier check run; two workflow runs on one commit both stay, and both are read | not held yet: `tests/test_adapters.py::test_a_required_check_reports_on_every_head_and_a_rerun_replaces_only_its_own` |
| A dependency update is judged by the deterministic Lenses alone, and needs no model review | `tests/test_decide.py::test_a_dependency_update_needs_no_model_review` |
| A Finding a model Lens has raised gates whatever the class, a dependency update's too, and after the bot recreates the branch | `tests/test_decide.py::test_a_model_lens_thread_gates_a_dependency_update` |
| A dependency update is a dependency bot's pull request whose head that bot pushed; anyone else's push, and every other class, needs the model review | `tests/test_decide.py::test_a_dependency_update_someone_else_pushed_to_needs_a_model_review`, `tests/test_decide.py::test_every_other_class_needs_a_model_review`, `examples/invalid/config.a-change-by-a-person-skips-the-model-review.json` |
| A dependency update skips the model review and nothing else: every deterministic Lens, a person's thread, a Hold and a Pause still bind, and a `neutral` check does not pass it | `tests/test_decide.py::test_a_dependency_update_is_judged_by_every_deterministic_lens`, `tests/test_decide.py::test_a_neutral_check_does_not_pass_a_dependency_update`, `tests/test_decide.py::test_a_writers_thread_still_gates_a_dependency_update`, `tests/test_decide.py::test_a_dependency_update_skips_the_model_review_and_nothing_else` |
| The configuration names at least one deterministic Lens, so no update is approved with no check at all | `examples/invalid/config.no-deterministic-lens.json` |
| `last_pusher` is the identity GitHub records as having pushed the head, never a commit's author or committer; class `dependency` is given only for an exact App identity, and a fork is always `outside` | `tests/test_adapters.py::test_the_newest_push_to_the_head_names_its_pusher_a_person_or_an_app`, `tests/test_adapters.py::test_an_activity_that_has_not_caught_up_with_the_head_names_no_one`, `tests/test_adapters.py::test_only_the_newest_entry_is_read`, `tests/test_adapters.py::test_a_fork_is_read_as_no_one_and_its_activity_is_never_asked`, `tests/test_adapters.py::test_the_class_is_the_account_named_or_outside` |
| An empty diff never converges | `tests/test_decide.py::test_empty_diff_never_converges` |
| Rounds between author and owner are bounded, and the bound ends in a Hold | `tests/test_decide.py::test_rounds_are_bounded` |
| Every category of Finding has exactly one owner | `tools/check_authority.py` |
| A rubric is data with a schema | `schemas/rubric.schema.json`, `tools/check_examples.py` |
| A reviewing Result reports on every criterion that applies | `tests/test_apply.py::test_an_uncovered_result_writes_nothing` |
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
| The port reads the contract at the head, and each result for a criterion with the content it ran on, from the check that gave it | waiting on `adapters/contract.py` |
| The port reports the latest result per criterion per check suite | waiting on `adapters/contract.py` |
| A result counts only from the App the configuration allows for its criterion's kind; never from the author's Role. Issue 108, "Kernel: acceptance evidence from the right reporter, against the approved contract" | `tests/test_decide.py::test_a_result_counts_only_from_the_reporter_its_kind_names`, `tests/test_decide.py::test_a_kind_with_no_reporter_cannot_pass`, `tests/test_decide.py::test_a_human_criterion_is_passed_only_by_a_persons_approval_of_this_content` |
| The contract read is the one the Maintainer approved, unchanged since; no fix Run on a contract not yet approved (I-29), in the same story | `tests/test_decide.py::test_a_contract_no_person_approved_is_a_hold`, `tests/test_decide.py::test_a_contract_changed_since_its_approval_is_a_hold`, `tests/test_decide.py::test_no_run_is_admitted_on_a_contract_not_approved` |
| No manifest names another Role's output as a trigger | role/1 has no field for a trigger: `examples/invalid/role.a-trigger-on-another-roles-output.json` |
