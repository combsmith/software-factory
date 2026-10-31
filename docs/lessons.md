# Lessons

What the proof of concept learned the hard way. Each lesson is a failure that happened, the rule it
produced, and the check that holds the rule here. A lesson whose check cannot exist yet names the
part of the repo it is waiting on; `tools/check_context.py` fails when that part appears, until the
lesson names a real check. A lesson that can have no check is not in this file.

Sources: the root causes and defects in sections 2.4, 4 and 12 of
`docs/architecture/factory-mvp-architecture-review.md`; and, in other repos, the proof of concept's
agent instructions, documents and postmortem of June 2026 (combsmith/.github-private, at
commit 684e4b9) and the org's standards (combsmith/.github, at commit 9e2daad). Take the failures from the review; build nothing from its
remedies. Issue and pull-request numbers are in combsmith/.github-private.

## Loops and bounds

### L-01 A Role was woken by its own output
**Failure.** The reviewer's acknowledgement mentioned its own account. The mention listener read that as a request, and 1,481 identical comments were posted over four and a half hours, on "Cache the LSP index and enforce the 30s cold-start SLA with auto-skip" (pull request 860). Nobody saw it for four days.
**Rule.** A Run is admitted from the facts of the Work item, never from an event, and content that has not changed admits no new review.
**Check.** `tests/test_decide.py::test_unchanged_content_causes_no_new_review`, `tests/test_decide.py::test_admission_is_given_facts_and_never_an_event`

### L-02 The runaway could reset the cap that stopped it
**Failure.** The review cap fired once. Its documented way back in was to mention the reviewer, which the loop itself did.
**Rule.** An allowance is renewed by a person with write access, and the Factory makes no transition out of a Hold: a Hold an App took off still binds.
**Check.** `tests/test_decide.py::test_a_writers_action_grants_a_fresh_allowance`, `tests/test_tools.py::test_a_hold_the_factory_could_end_is_caught`, `tests/test_decide.py::test_a_hold_that_anyone_but_a_person_removed_still_binds`

### L-03 The caps counted failures, and counted them per worker
**Failure.** The attempt limit counted only failed runs, and the cap on review cycles re-armed itself. Fixes that succeeded took one pull request to 378 commits in four days, for a diff of 18 files.
**Rule.** Every automated action on a Work item counts toward a ceiling, whether it succeeded or not: a Run toward the Run ceiling, and an act, made with no model, toward the act ceiling. An approval that lands is an act. One that does not land counts toward the Run ceiling, and toward its attempts too when the fault is the item's.
**Check.** `tools/mutants.py`, `tests/test_simulator.py::test_invariants_hold_under_faults`, `tests/test_decide.py::test_acts_are_bounded`, `tests/test_decide.py::test_an_approval_that_does_not_land_is_bounded`, `tests/test_decide.py::test_an_approval_that_keeps_failing_for_the_environment_is_bounded`, `tests/test_simulator.py::test_a_queue_that_ejects_every_time_is_bounded`, `tests/test_approve.py::test_each_fault_of_the_act_is_classed_as_the_design_classes_it`

### L-04 Two agents each answered the other
**Failure.** Every fix was a new commit, every new commit was reviewed, and every review produced a fix. Merged pull requests took seven to ten commits at the median, and each push cost about 56 jobs.
**Rule.** Every cycle with no person in it passes through a bounded counter, whoever makes its transitions: the Factory, a Lens or the platform. Reaching the bound is a Hold.
**Check.** `tools/check_lifecycle.py`, `tests/test_tools.py::test_a_cycle_through_a_lens_with_no_bound_is_caught`, `tests/test_tools.py::test_a_cycle_through_the_platform_with_no_bound_is_caught`, `tests/test_decide.py::test_rounds_are_bounded`, `tests/test_simulator.py::test_a_quiet_world_merges_or_stops_on_a_ceiling`

### L-05 A retry timer restarted what had been stopped
**Failure.** A two-hourly retry job re-dispatched stalled work without looking at why it had stalled, and re-lit loops that had run out.
**Rule.** A held or exhausted Work item admits nothing, whichever tick asks.
**Check.** `tests/test_decide.py::test_hold_label_binds`, `tests/test_decide.py::test_item_faults_exhaust_attempts`

### L-06 Eleven caps, each in a different script
**Failure.** Eleven numeric caps and nine tests of "is this actor automation?" were scattered through scripts and workflows. A control was built, closed as done, and could not fire: "The token-budget breaker is unreachable" (combsmith/.github issue 1155).
**Rule.** Every brake is in the Kernel, and each has a deliberate break that a test must notice.
**Check.** `tools/mutants.py`

## Reading facts

### L-07 "Could not check" was read as "nothing to check"
**Failure.** Four times in one week a check that could not be made was treated as passed: a brake whose input came back empty was skipped, a failed approval was announced as a success, a file that could not be read was overwritten. Separately, a capacity probe with no credential logged "usage 0% — ok" on every call: "check_provider_headroom has never worked" (issue 1862).
**Rule.** An unreadable fact yields a deferral with a reason. It never yields an admission, an approval or a merge. A required check that gave no verdict, `neutral`, `skipped` or `cancelled`, or whose conclusion the Kernel does not know, is unreadable, never passed.
**Check.** `tests/test_decide.py::test_incomplete_facts_never_converge_or_admit`, `tests/test_decide.py::test_unreadable_pause_defers`, `tests/test_decide.py::test_unreadable_capacity_defers`, `tests/test_decide.py::test_an_unknown_mergeable_never_converges`, `tests/test_decide.py::test_a_neutral_required_check_defers`, `examples/invalid/config.a-neutral-check-passes.json`

### L-08 A failing check that was not required halted every merge
**Failure.** A drift check that fails routinely, and is not required, was read as failing CI. The reviewer skipped every pull request: "Non-required failing check silently deadlocks every merge: template-drift fails on all PRs, review agent skips as ci-failing, no approval can land" (issue 1795).
**Rule.** Only a required Lens gates. A check outside the required set informs.
**Check.** `tests/test_decide.py::test_a_failed_check_that_is_not_required_does_not_gate`

### L-09 A list cut off at a page limit looked complete
**Failure.** The diff endpoint refuses above 300 changed files, and review threads were read one hundred deep. The reviewer went on with part of the diff and a note saying so.
**Rule.** Facts say whether each list was read in full. A diff too large to read is a Hold, and no Run is spent finding that out.
**Check.** `examples/invalid/facts.no-completeness.json`, `tests/test_decide.py::test_truncated_or_oversized_diff_is_held_without_a_run`

### L-10 State lived in labels and eighty kinds of comment marker
**Failure.** No file declared the lifecycle. Each script worked out state for itself from labels, reviews and 58 to 80 marker prefixes, and a marker could outlive the thing it described.
**Rule.** State is derived by one function at every evaluation and stored nowhere. Facts carry no prose.
**Check.** `tools/check_purity.py`, `examples/invalid/facts.carries-prose.json`

### L-11 A reason was a sentence
**Failure.** Verdict reasons were free strings at twelve sites, and control flow rode on seven exit codes. The review lists the cause of 410 failed runs as something it could not measure.
**Rule.** A reason is a code. People read a rendering of it.
**Check.** `examples/invalid/decision.sentence-as-reason.json`

### L-12 One hold label had four meanings
**Failure.** "Is this held?" had seven implementations with different label sets. A pull request sat unreviewed for more than two hours past its rate-limit reset, until a person removed a label: the sweep that was to review it again skipped on a hold label first.
**Rule.** One function reads the labels, and each kind of Hold has its own reason code.
**Check.** `tests/test_decide.py::test_hold_label_binds`, `tests/test_decide.py::test_hands_off_is_left_alone`

### L-13 A gate built on comments could not be closed
**Failure.** Every comment needed a verified disposition. A scanner re-posted "passed" on every push, and a reviewer edited one comment in place so that a notice sat beside real findings: "Edited-after-disposition deadlock" (issue 2166). Issues about failed approvals went from 1 to 17 to 45 over three four-week windows.
**Rule.** Only a required Lens or a person with write access gates. No decision reads a comment body.
**Check.** `tests/test_decide.py::test_minor_finding_and_unrequired_lens_do_not_gate`, `tests/test_decide.py::test_a_strangers_thread_does_not_gate`, `examples/invalid/facts.carries-prose.json`

### L-14 The Maintainer's finding had no force where it was written
**Failure.** The Maintainer reported a fault in a plain comment. The author never saw it, the reviewer approved, and the change merged eight minutes later with the fault in it.
**Rule.** A person with write access blocks with a review thread, whatever its severity, or with an ordinary request for changes. The request stands until that person approves or a person with write access dismisses it: new content does not clear it, and nor does an App's dismissal. A plain comment gates nothing, because it has no resolved state (L-13); it is given to the next Run to steer it.
**Check.** `tests/test_decide.py::test_a_writer_thread_gates_whatever_its_severity`, `tests/test_decide.py::test_a_writers_request_for_changes_does_not_converge`, `tests/test_decide.py::test_a_request_for_changes_stands_until_that_person_reviews_again`; a comment reaching the next Run is waiting on `adapters/texts.py`

## Approval and merge

### L-15 Empty pull requests merged and closed their issues
**Failure.** Ten of them: "dev-lead merges zero-diff PRs that close their issues" (issue 1620).
**Rule.** An empty diff never converges.
**Check.** `tests/test_decide.py::test_empty_diff_never_converges`

### L-16 An approval was tied to a commit, not to what was reviewed
**Failure.** One merge to the default branch updated every open pull request, each new head dismissed its approval, and each was reviewed again in full. The reviewer also dismissed its own approval and then skipped the pull request as already reviewed: "pr-review never re-approves after dismissing its own approval" (issue 1933).
**Rule.** A verdict is bound to the content it judged. The same content needs no new review, and other content has none.
**Check.** `tests/test_decide.py::test_unchanged_content_causes_no_new_review`, `tests/test_decide.py::test_an_approval_of_other_content_does_not_stand`

### L-17 The agent resolved the threads that were holding it
**Failure.** Four of the Maintainer's review threads were resolved by the account the author agent ran as, and the pull request merged itself.
**Rule.** No Role decides a Finding about its own work. A person's thread is closed by that person: resolved by anyone else, it stays open. A Lens's thread is closed only by a person with write access, or by the queue App on that Lens's accepted ruling, as the Kernel's act (decision 0086). What a person placed, only a person ends.
**Check.** `tools/check_authority.py`, `tests/test_decide.py::test_an_answered_human_thread_waits_for_that_person`, `tests/test_decide.py::test_a_persons_thread_resolved_by_anyone_but_that_person_stays_open`, `tests/test_decide.py::test_a_lens_thread_resolved_by_anyone_but_a_writer_or_the_queue_on_its_ruling_stays_open`, `tests/test_decide.py::test_only_a_person_ends_a_request_for_changes`

### L-18 The approver was the author, or the last to push
**Failure.** GitHub does not count an approval from either. With two code owners, one the author and the other the last pusher, nobody could approve, and only an administrator's bypass merged anything.
**Rule.** No approval is attempted where the approver is the author or the last pusher. The item is held with that reason.
**Check.** `tests/test_decide.py::test_approver_is_never_the_author_or_last_pusher`

### L-19 The merge queue looked at reviews only on the way in
**Failure.** A pull request was approved, queued, lost its approval, and merged: "Remove a PR from the merge queue when the fleet withdraws its last approval (reviews are only checked when a PR joins the queue)" (issue 2174).
**Rule.** A pull request that loses its approval leaves the queue, and nothing merges without an approval of exactly the content that merges.
**Check.** `tests/test_simulator.py::test_invariants_hold_under_faults` for the merge; `tests/test_decide.py::test_a_queued_pull_request_with_no_approval_leaves_the_queue` for leaving the queue

### L-20 A model reviewed content the checks would have rejected
**Failure.** Every push cost a fresh pass by every reviewer, and outside reviewers posted again on every commit.
**Rule.** No model Lens runs on content the deterministic Lenses have not passed.
**Check.** `tests/test_decide.py::test_no_model_review_before_deterministic_checks_pass`

## Lost work

### L-21 A request existed only as a queued run
**Failure.** A third arrival in a concurrency group evicted the one waiting, with no step run: "[bug] 42% of dev-lead runs are cancelled before doing any work" (issue 1741). A run killed before it wrote its marker was never retried, because no marker read as no failure.
**Rule.** Work is found by reading what is open, not by receiving an event. One Run holds an item, including one still waiting for a runner.
**Check.** `tests/test_simulator.py::test_work_is_never_lost_once_faults_stop`, `tests/test_decide.py::test_one_writer_per_item`

### L-22 The schedule that recovered lost work was itself lost
**Failure.** About six in ten scheduled ticks never arrived, and sweeps meant for every fifteen minutes ran hours apart: "Retry and sweep crons run every 4–8 hours instead of every 2 h / 15 min" (issue 2170).
**Rule.** No decision depends on a particular tick arriving. The next pass reaches the same answer.
**Check.** `tests/test_simulator.py::test_work_is_never_lost_once_faults_stop`

### L-23 Every failure looked the same
**Failure.** A run with no credential exited as a success having done nothing. A guard that refused on purpose was counted as a fleet failure. A rate limit counted toward an item's three attempts, as a fault of the item would.
**Rule.** A failed Run is a fault of the item, of capacity or of the environment, or was superseded. Only the first counts against the item.
**Check.** `tests/test_decide.py::test_capacity_and_environment_faults_are_not_attempts`

### L-24 A deliberate pause looked like an outage
**Failure.** The fleet was taken offline by withholding its model credential: "Make 'agents intentionally paused' a first-class state — deliberate token disable presented as fleet-wide outage (2026-08-16)" (issue 1525). The switch built afterwards was read by one agent of several.
**Rule.** A Pause is an input of its own with a reason of its own, and it stops every act: a Run, an approval, a merge.
**Check.** `tests/test_decide.py::test_human_pause_admits_nothing`, `tests/test_decide.py::test_a_pause_stops_approvals_and_merges_too`

## Checks that could not fail

### L-25 Controls that nothing read, and validators that passed on nothing
**Failure.** A declared stop marker was read by no code. A validator passed because the file it validated did not exist. A canary had to be built to catch a gate that resolved its input to nothing while CI stayed green.
**Rule.** Every check has a test in which it fails, and every rule in the Kernel has a deliberate break that a test must notice.
**Check.** `tests/test_tools.py`, `tools/mutants.py`

### L-26 Test files that no workflow ran
**Failure.** Four test files ran nowhere. The list was kept by hand, and a file named in it but missing was skipped with a warning.
**Rule.** One command discovers every test, and every check on disk is one that command runs.
**Check.** `tests/test_tools.py::test_every_test_file_is_discovered`, `tests/test_tools.py::test_every_check_is_run_by_verify`

### L-27 A green merge deleted a regression test
**Failure.** A pull request merged from a stale base reverted a shipped fix and deleted its test in the same diff, and CI was green.
**Rule.** Remove a rule's test and its deliberate break survives, which fails the required check.
**Check.** `tools/mutants.py`

### L-28 The second definition silently replaced the first
**Failure.** An agent appended functions instead of replacing them: fourteen were defined two to four times. In the standards repo, duplicated functions and a doubled instruction file reached the main branch with nothing to stop them.
**Rule.** A name is defined once in a scope, and a key is written once in an object: the later one replaces the earlier without a word.
**Check.** `tests/test_tools.py::test_a_second_definition_is_caught`, `tests/test_tools.py::test_a_key_written_twice_is_refused`

### L-29 A schema promised more than was checked
**Failure.** A schema validator did not enforce the keyword that described a timestamp unless it was told to, so text that was no timestamp would have passed. A reviewer caught it, in the org's standards repo.
**Rule.** A schema that uses a keyword the validator does not implement is refused.
**Check.** `tests/test_tools.py::test_rejects_a_schema_it_cannot_enforce`

### L-30 It failed on the laptop and passed in CI
**Failure.** About a hundred tests in one file failed on a stock laptop because its shell was older than the code assumed, and its Python was too old for the eval scripts. A failure on a laptop could not be told from a regression.
**Rule.** Nothing is installed, the syntax is that of the oldest Python named, and a seed gives the same run everywhere.
**Check.** `tests/test_tools.py::test_third_party_code_is_caught`, `tests/test_tools.py::test_syntax_newer_than_the_oldest_python_is_caught`, `tests/test_tools.py::test_a_draw_that_differs_between_python_versions_is_caught`, `tests/test_simulator.py::test_a_seed_replays_exactly`

### L-31 A check fetched its rules at run time
**Failure.** Validators that read another repo's default branch turned every repo red 21 seconds after a merge there. A gate script fetched the same way failed open when the fetch failed.
**Rule.** The required check reads nothing outside the commit it judges.
**Check.** `tools/check_repo.py`, `examples/workflows/invalid/install.fetched-at-run-time.yml`

### L-32 One fact was written in eight places
**Failure.** The list of agents existed in at least eight places that already disagreed. Adding one trigger took 32 days and six pull requests.
**Rule.** A fact is written once, as data. Where a value must appear twice, a check compares the two.
**Check.** `tests/test_tools.py::test_a_value_held_twice_must_agree`, `tests/test_tools.py::test_a_second_copy_of_the_review_standard_is_caught`

### L-33 The documents described a system that no longer existed
**Failure.** Four documents contradicted the code. A rule was dropped while the automation that enforced it kept running, and the audit reported the change as drift.
**Rule.** A document names the check that holds each rule, and every path and test it names exists.
**Check.** `tests/test_tools.py::test_a_rule_with_no_check_is_caught`, `tests/test_tools.py::test_a_path_or_a_test_that_does_not_exist_is_caught`

### L-34 Model names were scattered through the tree
**Failure.** Changing a model meant hunting for its full name in scripts, workflows and prompts.
**Rule.** A model is named in one place. Until the engine port exists, no file names one.
**Check.** `tools/check_repo.py`

### L-60 A test that failed under load killed a mutant
**Failure.** On a laptop with a load average near 30, the mutation run reported four mutants killed that CI's shards reported surviving. The code they broke had become dead. An unrelated test had failed under load, and any failing test counted as a kill, so four rules nothing checked passed as checked.
**Rule.** A mutant is killed only by a test that fails on it, fails again when run alone on it, and passes when run alone on the unbroken code, in the same copy. A failure short of that runs the suite once more, and a second is `FLAKY`, which fails the run. A test timed by the wall clock is marked `@wall_clock` and skipped in the mutation run.
**Check.** `tests/test_tools.py::test_a_mutant_whose_only_failure_is_unrelated_survives`, `tests/test_tools.py::test_a_test_that_fails_on_the_unbroken_code_too_kills_nothing`, `tests/test_tools.py::test_a_failure_that_is_not_the_mutants_twice_is_flaky_and_fails_the_check`, `tests/test_tools.py::test_every_test_timed_by_the_wall_clock_is_marked_and_skipped_when_mutating`, `tools/mutants.py`

### L-61 A hook killed for its time filled the disk
**Failure.** The stop hook's `make verify` outlasted the hook's time under four builders' load and was killed at every stop, so the suite's temporary folders, each holding the run's copies of the repo, were never removed. They filled the Maintainer's disk, and every builder's checks then failed for want of space.
**Rule.** A hook's run leaves nothing behind, killed or not: it runs in a process group and a temporary folder of its own, both ended when it ends. A test's copy of the repo goes when the test ends. A run that could not finish is not started again for a while, and sends no session back; CI runs it.
**Check.** `tests/test_hooks.py::test_a_run_killed_for_its_time_leaves_the_temporary_folder_as_it_found_it`, `tests/test_hooks.py::test_a_verify_that_did_not_finish_is_not_started_again_for_a_while`, `tests/test_tools.py::test_a_copy_of_the_repo_is_removed_when_the_test_that_made_it_ends`

## Workflows

### L-35 What ran was whatever a tag pointed at that day
**Failure.** The model's command-line tool resolved to the latest version at run time, while its documentation announced a change of default that would stop every agent authenticating.
**Rule.** What runs is pinned: an action to a full commit hash, a runner image to a version, the Engine's tool to a version.
**Check.** `examples/workflows/invalid/pin.a-tag-can-move.yml`, `examples/workflows/invalid/runner.an-image-that-changes.yml`; the Engine's tool is held by `tests/test_harness.py::test_the_version_is_held_before_and_after_the_call`

### L-36 A required check never reported
**Failure.** A required check behind a path filter does not run, so it never reports, and every merge waits for ever. The same happens in the merge queue to a workflow that does not run on its event.
**Rule.** A workflow that runs on pull requests runs on the merge queue too, and has no path filter.
**Check.** `examples/workflows/invalid/queue.a-required-check-that-never-reports.yml`

### L-37 One person's token served seven purposes
**Failure.** The owner account's token was named 70 times and served seven purposes, and nine workflows passed every secret to whatever they called. Its rotation would show only as a refusal on the next run.
**Rule.** No workflow names a personal access token, and none inherits secrets. The age of each credential is read, and one near its limit raises one alert.
**Check.** `examples/workflows/invalid/token.a-persons-token.yml`, `tests/test_controller.py::test_a_credential_near_its_limit_raises_one_alert`, `tests/test_tools.py::test_every_secret_a_workflow_names_has_a_row_and_each_row_names_its_workflows`

### L-38 A gate was allowed to fail
**Failure.** The eval gate ran only with its failure ignored, and the release never looked at its result.
**Rule.** No step or job continues on error.
**Check.** `examples/workflows/invalid/soft.a-failure-nobody-sees.yml`

### L-39 A hung step ran for six hours
**Failure.** Jobs with no limit ran to the platform's maximum, and about a fifth of sampled job time was a runner asleep waiting for a rate limit.
**Rule.** Every job with steps sets a time limit.
**Check.** `examples/workflows/invalid/timeout.a-hung-step-runs-six-hours.yml`

### L-40 Decisions were written in workflow files
**Failure.** A thousand lines of top-level shell in one script could not be called as a unit, about two thousand more sat inline in workflow files, and a change to a caller's inputs or triggers was exercised by nothing before merge.
**Rule.** A `run:` block is at most ten lines. The decision is in the Kernel, where a test can call it.
**Check.** `examples/workflows/invalid/length.logic-in-a-workflow.yml`, `tools/check_purity.py`

### L-41 Success was reported for work that was not done
**Failure.** "pr-review announces an approval it never created" (issue 1874). The author posted "Fixed" for changes it never pushed, and reported a rebase complete with no commit.
**Rule.** A claim is written by `apply`, from what it wrote and then read back. The model's output has no field for one.
**Check.** `tests/test_apply.py::test_an_effect_is_claimed_only_from_what_was_read_back`

### L-42 The author edited the tests it was judged by
**Failure.** "[Phase 4] Name and guard the "agent optimizes the check, not the intent" failure mode" (issue 1468): a test tool vendored to satisfy a check, and a distributed file edited to turn a monitor green. Separately, the author edited tests to match its own code.
**Rule.** `apply` refuses a change by an implementing Role to a test, a fixture, a threshold or an acceptance contract that judges it.
**Check.** waiting on `harness/push.py`, the fix Intent's push

### L-43 The model held the credential that could write
**Failure.** The author's job held the owner account's token and kept it for pushing. "Never push" was a sentence in the prompt.
**Rule.** No job holds both a model credential and a credential that can write.
**Check.** `tests/test_harness.py::test_the_cli_is_given_exactly_the_named_environment_and_the_one_credential`; that no job holds both, `tests/test_tools.py::test_the_runs_jobs_keep_each_key_apart_and_always_leave_the_outcome`

### L-44 Agents acted as the Maintainer
**Failure.** Agents ran as the owner's account, so the Maintainer could not review an agent's pull requests and the agent skipped the Maintainer's requests as its own. When one Role took its identity from a shared variable, it committed as the review-only machine user: "dev-lead regressed to committing as donpetry-bot (review-only machine user) instead of don-petry" (issue 1316).
**Rule.** Each Role declares its own App, and no two share one.
**Check.** `tests/test_tools.py::test_each_role_writes_through_its_own_app`

### L-45 A merged fix was not what ran
**Failure.** Twice in one week a fix merged and the failure went on, because agents ran from a tag that had not moved. A whole class of change never arrived at all: "Script-only changes never reach the fleet" (issue 1592).
**Rule.** Every Run records the Release it ran, and a change is live only when the Channel that serves it points at it.
**Check.** `examples/invalid/task.a-channel-for-a-release.json`, `tests/test_release.py::test_a_commit_with_no_release_or_two_resolves_to_none`

### L-46 A caller ran ahead of what it called
**Failure.** A caller passed an input the pinned Release did not declare, and every run failed at startup, after merge, because a pull request's own checks run the old caller.
**Rule.** The dispatcher and what it dispatches ride one Release, and a new field is read at every live Channel before anything sends it.
**Check.** One Channel for every shim, `tests/test_tools.py::test_every_shim_calls_one_channel`; a Run on another Release than its pass's doing nothing, `tests/test_steps.py::test_a_run_on_another_release_than_its_pass_builds_no_task`, `tests/test_steps.py::test_a_run_whose_own_release_cannot_be_named_builds_no_task`

### L-47 Promotion counted green runs in a ring with no members
**Failure.** The gate read run conclusions, the rings were empty, all four channels pointed at one commit, and the gate was overridden by hand on four dates in ten days.
**Rule.** A candidate with no Runs behind it, each with Effects read back, is refused.
**Check.** `examples/invalid/rings.promotion-with-no-runs.json`; the gate that reads it waiting on `release/promote.py`

### L-48 Nobody noticed
**Failure.** "Engine-token liveness monitoring: a 7-day fleet-wide dev-lead outage went unalerted, and pr-review fails open" (issue 1587). The daily failure report appears to have stopped as well; the review could not confirm it.
**Rule.** One cause raises one alert, a pass that did not run is itself reported, and an item that needs a person is assigned to one.
**Check.** `tests/test_controller.py::test_one_cause_raises_one_alert`, `tests/test_controller.py::test_the_first_pass_after_six_hours_with_none_raises_the_not_run_alert_and_the_next_clears_it`; assigning an item to a person is waiting on `controller/notify.py`

### L-49 The Maintainer's attention was the real limit
**Failure.** Runs rose about fivefold while merges stayed at 14 to 36 a week. The owner account cleared holds 64 times across 150 merged pull requests.
**Rule.** While more items need the Maintainer than a declared number, only a Run that unblocks a merge is admitted.
**Check.** waiting on `controller/backpressure.py`

### L-50 A credential's permissions were assumed
**Failure.** A change of credential met a refusal on its first real write and was reverted. An App that could write contents could not move a tag on a repo with workflows, and the fleet was broken for six days.
**Rule.** Each write a Role may make is tried once on a canary repo, and the recorded response is what the fake GitHub is held to.
**Check.** `tests/test_effects.py::test_every_write_the_port_sends_has_the_shape_a_trial_recorded`, for a dispatch's answer, from `trials/P-9.json`; the status, the dequeue and the tracking issue are not held yet: `tests/test_effects.py::test_the_status_the_dequeue_and_the_tracking_issue_are_written_as_trials_recorded`

### L-51 The tests passed against a fake that accepted anything
**Failure.** The shared stub of the GitHub command returned empty for calls it did not know, so real flags and filters were never exercised.
**Rule.** Every rule the fake GitHub applies cites a response recorded from the real one, and the required check prints the rules that do not.
**Check.** `tests/test_tools.py::test_a_rule_of_the_fake_that_is_not_listed_is_caught`, `tests/test_tools.py::test_a_fixture_named_for_a_rule_must_exist_and_validate`, `tests/test_tools.py::test_verify_prints_every_rule_no_fixture_grounds`, `tests/test_tools.py::test_a_rule_no_trial_asks_names_one_or_says_why_none_can`; the port's reading of each fixture that grounds a rule of the fake, held to what the rule states, every other named with why it is not read here, the fake not run: `tests/test_adapters.py::test_the_port_reads_each_grounded_rule_as_the_fake_assumes_it`; each refusal a trial recorded placed, and each one a built port asks read as no answer: `tests/test_adapters.py::test_a_recorded_refusal_is_no_answer`

### L-52 The fleet and every session shared one API quota
**Failure.** "The fleet and every session share one GitHub API quota" (issue 2197). It ran out on 2026-10-10 and failed a workflow.
**Rule.** The Factory reads through an App of its own, with a quota of its own, and what a pass costs is read and held to a budget.
**Check.** `tests/test_controller.py::test_the_three_thresholds_of_decision_0011_are_computed_and_shown`; reading what a pass costs is waiting on `adapters/usage.py`

### L-53 The list itself was cut off, and nothing said so
**Failure.** The list of workflow runs stops at 1,000 for a query, however it is paged. A query over the resource limit came back as a success with no data, and a whole repo was read as having no pull requests.
**Rule.** A list read short is unreadable. The list of Runs and the list of items each say whether they are whole, as the facts of one item do.
**Check.** `tests/test_decide.py::test_incomplete_facts_never_converge_or_admit`, `examples/invalid/facts.no-completeness-for-runs.json` for the list of Runs; `examples/invalid/facts.no-completeness-for-timeline.json` for the timeline the acts are counted from; the list of open pull requests, `tests/test_adapters.py::test_open_pull_requests_are_whole_only_if_each_was_read`

### L-54 A wrong fix cleared a gate
**Failure.** A fix added a new test and broke an existing one without editing it. Nobody ran the suite against the state before the fix, and an outside reviewer marked the thread addressed on the strength of the reply.
**Rule.** `verify` compares with the head the Run started from. A test that passed and now fails applies no Effect, and a repo with no test command is recorded as not run, never as passed.
**Check.** An Intent that pushes nothing is recorded `not_run`: `tests/test_steps.py::test_verify_takes_the_results_digest`; the comparison with the head a Run started from is waiting on `harness/push.py`

### L-55 A forced push destroyed the Maintainer's commit
**Failure.** A push leased against a ref that an earlier fetch in the same run had refreshed. The lease passed, and the push discarded a commit the Maintainer had made to steer the work.
**Rule.** `apply` pushes against the exact head its Decision named. A refusal means the Run was superseded.
**Check.** waiting on `harness/push.py`, the fix Intent's push

### L-56 Steering never reached the agent
**Failure.** An issue steered by a comment sat idle, because only its title and body reached the prompt. When comments were added they had to be cut to people with write access, newest first, with what was dropped counted and said.
**Rule.** A Task says what was left out of it, and how much.
**Check.** `tests/test_harness.py::test_a_task_says_what_it_left_out_and_how_much`

### L-57 Who counted as a writer depended on which token asked
**Failure.** GitHub reports an author's standing relative to the token that reads it. Read with the wrong credential, every trusted marker was dropped as untrusted, and the breaker that counted them could never trip.
**Rule.** Whether an actor can write is read with one named credential, and a trial records what each credential is shown.
**Check.** `tests/test_adapters.py::test_an_actor_is_told_by_its_account_type_and_the_configuration`, `tests/test_adapters.py::test_what_each_credential_is_shown_of_a_permission_is_recorded`

### L-58 The pause variable meant different things to different readers
**Failure.** A repo's variable overrode the org's of the same name, and a workflow expression matched its value without regard to case while a script matched it exactly. One spelling delivered a credential to a run that then would not use it.
**Rule.** A Pause on the org or on the repo is a Pause. Any value but an exact true, an exact false or nothing is unreadable.
**Check.** `tests/test_controller.py::test_a_pause_on_the_org_or_the_repo_is_a_pause_and_any_other_value_is_unreadable`

### L-59 An old streak on a quiet repo was read as a live outage
**Failure.** A run of failures that had been fixed weeks before, on a repo with little traffic, was reported as an outage and held every scheduled run red. An outside reviewer's rate limit was at risk of counting toward the fleet's own breaker.
**Rule.** An automatic pause needs faults that agree, from Runs on different items, of the Factory's own capacity, inside a recent window.
**Check.** `tests/test_controller.py::test_an_automatic_pause_needs_agreeing_faults_from_runs_on_different_items_in_a_recent_window`

## Not carried over

These failures were real, and nothing here can hold a rule for them yet, so they are recorded as
open questions and not as lessons: finished work lost when a run timed out, since resuming a Run is
not designed; an issue closed as done with nothing merged, since the issue Lifecycle is not
designed; and a fix that moved a failure instead of removing it, which no check can tell apart from
a fix.
