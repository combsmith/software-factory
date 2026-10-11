# Lessons

What the proof of concept learned the hard way. Each lesson is a failure that happened, the rule it
produced, and the check that holds the rule here. A lesson whose check cannot exist yet names the
part of the repo it is waiting on; `tools/check_context.py` fails when that part appears, until the
lesson names a real check. A lesson that can have no check is not in this file.

Sources, all as they stood on 2026-10-11: the root causes and defects in sections 2.4, 4 and 12 of
`docs/architecture/factory-mvp-architecture-review.md`; and, in other repos, the proof of concept's
agent instructions and its postmortem of June 2026 (petry-projects/.github-private) and the org's
standards (petry-projects/.github). Take the failures from the review; build nothing from its
remedies. Issue and pull-request numbers are in petry-projects/.github-private.

## Loops and bounds

### L-01 A Role was woken by its own output
**Failure.** The reviewer's acknowledgement mentioned its own account. The mention listener read that as a request, and 1,481 identical comments were posted over four and a half hours, on "Cache the LSP index and enforce the 30s cold-start SLA with auto-skip" (pull request 860). Nobody saw it for four days.
**Rule.** Nothing a Role writes can start a Run. A Run is admitted from facts, and unchanged content admits nothing.
**Check.** `tests/test_decide.py::test_unchanged_content_causes_no_new_review`, `tests/test_decide.py::test_admission_is_given_facts_and_never_an_event`

### L-02 The runaway could reset the cap that stopped it
**Failure.** The review cap fired once. Its documented way back in was to mention the reviewer, which the loop itself did. A second bound left the author's own account off its list of automation, so the author's activity reset the count.
**Rule.** An allowance is renewed only by a person with write access, and only a person ends a Hold.
**Check.** `tests/test_decide.py::test_a_writers_action_grants_a_fresh_allowance`, `tests/test_tools.py::test_a_hold_the_factory_could_end_is_caught`

### L-03 The caps counted failures, and counted them per worker
**Failure.** Every cap was per run or per tick, and the attempt limit counted only failed runs. Fixes that succeeded took one pull request to 378 commits and 1,582 comments, for a diff of 18 files.
**Rule.** Every Run on a Work item counts toward one ceiling, whether it succeeded or not.
**Check.** `tools/mutants.py`, `tests/test_simulator.py::test_invariants_hold_under_faults`

### L-04 Two agents each answered the other
**Failure.** Every fix was a new commit, every new commit was reviewed, and every review produced a fix. Merged pull requests took seven to ten commits at the median, and each push cost about 56 jobs.
**Rule.** Every cycle the Factory can make with no person in it passes through a bounded counter, and reaching the bound is a Hold.
**Check.** `tools/check_lifecycle.py`, `tests/test_decide.py::test_rounds_are_bounded`, `tests/test_simulator.py::test_a_quiet_world_merges_or_stops_on_a_ceiling`

### L-05 A retry timer restarted what had been stopped
**Failure.** A two-hourly retry job re-dispatched stalled work without looking at why it had stalled, and re-lit loops that had run out.
**Rule.** A held or exhausted Work item admits nothing, whichever tick asks.
**Check.** `tests/test_decide.py::test_hold_label_binds`, `tests/test_decide.py::test_item_faults_exhaust_attempts`

### L-06 Eleven caps, each in a different script
**Failure.** Eleven numeric caps and nine tests of "is this actor automation?" were scattered through scripts and workflows. A control was built, closed as done, and could not fire: "The token-budget breaker is unreachable" (petry-projects/.github issue 1155).
**Rule.** Every brake is evaluated in one function, and each has a deliberate break that a test must notice.
**Check.** `tools/mutants.py`

## Reading facts

### L-07 "Could not check" was read as "nothing to check"
**Failure.** Four times in one week an unreadable input became an empty one. A capacity probe with no credential logged "usage 0% — ok" on every call: "check_provider_headroom has never worked" (issue 1862).
**Rule.** An unreadable fact yields a deferral with a reason. It never yields an admission, an approval or a merge.
**Check.** `tests/test_decide.py::test_incomplete_facts_never_converge_or_admit`, `tests/test_decide.py::test_unreadable_pause_defers`, `tests/test_decide.py::test_unreadable_capacity_defers`

### L-08 A failing check that was not required halted every merge
**Failure.** A drift check that fails routinely, and is not required, was read as failing CI. The reviewer skipped every pull request: "Non-required failing check silently deadlocks every merge: template-drift fails on all PRs, review agent skips as ci-failing, no approval can land" (issue 1795).
**Rule.** Only a required Lens gates. A check outside the required set informs.
**Check.** `tests/test_decide.py::test_a_failed_check_that_is_not_required_does_not_gate`

### L-09 A list cut off at a page limit looked complete
**Failure.** The diff endpoint fails above 300 changed files, and lists were read one page deep. What came back was treated as all there was.
**Rule.** Facts say whether each list was read in full. A diff too large to read is a Hold, and no Run is spent finding that out.
**Check.** `examples/invalid/facts.no-completeness.json`, `tests/test_decide.py::test_truncated_or_oversized_diff_is_held_without_a_run`

### L-10 State lived in labels and eighty kinds of comment marker
**Failure.** No file declared the lifecycle. Each script worked out state for itself from labels, reviews and 58 to 80 marker prefixes, and a marker could outlive the thing it described.
**Rule.** State is derived by one function at every evaluation and stored nowhere. Facts carry no prose.
**Check.** `tools/check_purity.py`, `examples/invalid/facts.carries-prose.json`

### L-11 A reason was a sentence
**Failure.** Verdict reasons were free strings at twelve sites, and control flow rode on seven exit codes. The cause of 410 failed runs could not be counted.
**Rule.** A reason is a code. People read a rendering of it.
**Check.** `examples/invalid/decision.sentence-as-reason.json`

### L-12 One hold label had four meanings
**Failure.** "Is this held?" had seven implementations with different label sets. A pull request sat unreviewed for hours past its rate-limit reset because one script skipped on the label that another had promised to clear.
**Rule.** One function reads the labels, and each kind of Hold has its own reason code.
**Check.** `tests/test_decide.py::test_hold_label_binds`, `tests/test_decide.py::test_hands_off_is_left_alone`

### L-13 A gate built on comments could not be closed
**Failure.** Every comment needed a verified disposition. A scanner re-posted "passed" on every push, and a reviewer edited one comment in place so that a notice sat beside real findings: "Edited-after-disposition deadlock" (issue 2166). Issues about failed approvals went from 1 to 17 to 45 over three four-week windows.
**Rule.** Only a required Lens or a person with write access gates. No decision reads a comment body.
**Check.** `tests/test_decide.py::test_minor_finding_and_unrequired_lens_do_not_gate`, `tests/test_decide.py::test_a_strangers_thread_does_not_gate`

### L-14 The Maintainer's finding had no force where it was written
**Failure.** The Maintainer reported a fault in a plain comment. The author never saw it, the reviewer approved, and the change merged eight minutes later with the fault in it.
**Rule.** Which channel gates is declared: a review thread from a person with write access always gates, whatever its severity. A plain comment steers.
**Check.** `tests/test_decide.py::test_a_writer_thread_gates_whatever_its_severity`

## Approval and merge

### L-15 Empty pull requests merged and closed their issues
**Failure.** Ten of them: "dev-lead merges zero-diff PRs that close their issues" (issue 1620).
**Rule.** An empty diff never converges.
**Check.** `tests/test_decide.py::test_empty_diff_never_converges`

### L-16 An approval was tied to a commit, not to what was reviewed
**Failure.** One merge to the default branch updated every open pull request, each new head dismissed its approval, and each was reviewed again in full. The reviewer dismissed its own approval and then skipped the pull request as already reviewed: "10 of 11 open PRs have never received an approving review" (issue 1894).
**Rule.** A verdict is bound to the content it judged. The same content needs no new review, and other content has none.
**Check.** `tests/test_decide.py::test_unchanged_content_causes_no_new_review`, `tests/test_decide.py::test_an_approval_of_other_content_does_not_stand`

### L-17 The agent resolved the threads that were holding it
**Failure.** Four of the Maintainer's review threads were resolved by the account the author agent ran as, and the pull request merged itself.
**Rule.** No Role decides a Finding about its own work. A person's thread is closed by that person.
**Check.** `tools/check_authority.py`, `tests/test_decide.py::test_an_answered_human_thread_waits_for_that_person`

### L-18 The approver was the author, or the last to push
**Failure.** GitHub does not count an approval from either. With two code owners, one the author and the other the last pusher, nobody could approve, and only an administrator's bypass merged anything.
**Rule.** No approval is attempted where the approver is the author or the last pusher. The item is held with that reason.
**Check.** `tests/test_decide.py::test_approver_is_never_the_author_or_last_pusher`

### L-19 The merge queue looked at reviews only on the way in
**Failure.** A pull request was approved, queued, lost its approval, and merged: "Remove a PR from the merge queue when the fleet withdraws its last approval (reviews are only checked when a PR joins the queue)" (issue 2174).
**Rule.** Nothing merges without an approval of exactly the content that merges.
**Check.** `tests/test_simulator.py::test_invariants_hold_under_faults`

### L-20 A model reviewed content the checks would have rejected
**Failure.** Every push started every reviewer at once, whatever the checks were about to say.
**Rule.** No model Lens runs on content the deterministic Lenses have not passed.
**Check.** `tests/test_decide.py::test_no_model_review_before_deterministic_checks_pass`

## Lost work

### L-21 A request existed only as a queued run
**Failure.** A third arrival in a concurrency group evicted the one waiting, with no step run: "[bug] 42% of dev-lead runs are cancelled before doing any work" (issue 1741). A run killed before it wrote its marker was never retried, because no marker read as no failure.
**Rule.** Work is found by reading what is open, not by receiving an event. One Run holds an item, including one still waiting for a runner.
**Check.** `tests/test_simulator.py::test_work_is_never_lost_once_faults_stop`, `tests/test_decide.py::test_one_writer_per_item`

### L-22 The schedule that recovered lost work was itself lost
**Failure.** About six in ten scheduled ticks never arrived: "Retry and sweep crons run every 4–8 hours instead of every 2 h / 15 min" (issue 2170).
**Rule.** No decision depends on a particular tick arriving. The next pass reaches the same answer.
**Check.** `tests/test_simulator.py::test_work_is_never_lost_once_faults_stop`

### L-23 Every failure looked the same
**Failure.** A run with no credential exited as a success having done nothing. A guard that refused on purpose was counted as a fleet failure. A fault of the environment used up the item's attempts.
**Rule.** A failed Run is a fault of the item, of capacity or of the environment, or was superseded. Only the first counts against the item.
**Check.** `tests/test_decide.py::test_capacity_and_environment_faults_are_not_attempts`

### L-24 A deliberate pause looked like an outage
**Failure.** The fleet was taken offline by withholding its model credential: "Make 'agents intentionally paused' a first-class state — deliberate token disable presented as fleet-wide outage (2026-08-16)" (issue 1525). The switch meant for pausing was read by one agent of several.
**Rule.** A Pause is an input of its own with a reason of its own, and it stops every admission.
**Check.** `tests/test_decide.py::test_human_pause_admits_nothing`

## Checks that could not fail

### L-25 Controls that nothing read, and validators that passed on nothing
**Failure.** A declared stop marker was read by no code. A validator passed because the file it validated did not exist. A canary stayed green while resolving its input to nothing.
**Rule.** Every check has a test in which it fails, and every rule in the Kernel has a deliberate break that a test must notice.
**Check.** `tests/test_tools.py`, `tools/mutants.py`

### L-26 Test files that no workflow ran
**Failure.** Four test files ran nowhere. The list was kept by hand, and a file named in it but missing was skipped with a warning.
**Rule.** One command discovers every test, and every check on disk is one that command runs.
**Check.** `tests/test_tools.py::test_every_check_is_run_by_verify`

### L-27 A green merge deleted a regression test
**Failure.** A pull request merged from a stale base reverted a shipped fix and deleted its test in the same diff, and CI was green.
**Rule.** Remove a rule's test and its deliberate break survives, which fails the required check.
**Check.** `tools/mutants.py`

### L-28 The second definition silently replaced the first
**Failure.** An agent appended functions instead of replacing them: fourteen were defined two to four times in one file, and the last one won. A doubled instruction file and a JSON key written twice passed every test.
**Rule.** A name is defined once in a scope, and a key is written once in an object.
**Check.** `tests/test_tools.py::test_a_second_definition_is_caught`, `tests/test_tools.py::test_a_key_written_twice_is_refused`

### L-29 A schema promised more than was checked
**Failure.** A validator accepted a malformed timestamp, because the keyword that described it was not enforced by default.
**Rule.** A schema that uses a keyword the validator does not implement is refused.
**Check.** `tests/test_tools.py::test_rejects_a_schema_it_cannot_enforce`

### L-30 It failed on the laptop and passed in CI
**Failure.** About a hundred tests failed on a stock laptop because the shell and the Python there were older than the code assumed. Real regressions hid among them.
**Rule.** Nothing is installed, the syntax is that of the oldest Python named, and a seed gives the same run everywhere.
**Check.** `tests/test_tools.py::test_syntax_newer_than_the_oldest_python_is_caught`, `tests/test_simulator.py::test_a_seed_replays_exactly`

### L-31 A check fetched its rules at run time
**Failure.** Validators that read another repo's default branch turned every repo red 21 seconds after an unrelated merge. A gate script fetched the same way failed open when the fetch failed.
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

## Workflows

### L-35 Text from an event was run as a command
**Failure.** A login, a branch name or a comment was written into a shell step by expression. Whoever chose the text chose the command.
**Rule.** No expression is written into a `run:` block.
**Check.** `examples/workflows/invalid/expression.text-run-as-a-command.yml`

### L-36 What ran was whatever a tag pointed at that day
**Failure.** The model's command-line tool and the runner image floated to the latest version while a default was about to change under them. A guessed commit hash passed CI because its job was skipped.
**Rule.** Every action is pinned to a full commit hash that was looked up, never guessed, and the runner is named by version.
**Check.** `examples/workflows/invalid/pin.a-tag-can-move.yml`, `examples/workflows/invalid/runner.an-image-that-changes.yml`

### L-37 A required check never reported
**Failure.** A required check behind a path filter does not run, so it never reports, and every merge waits for ever. The same happens in the merge queue to a workflow that does not run on its event.
**Rule.** A workflow that runs on pull requests runs on the merge queue too, and has no path filter.
**Check.** `examples/workflows/invalid/queue.a-required-check-that-never-reports.yml`

### L-38 Schedules at the top of the hour were the ones dropped
**Failure.** Jobs set for minute 0 were delayed by hours or never ran.
**Rule.** No schedule fires at minute 0.
**Check.** `examples/workflows/invalid/cron.the-top-of-the-hour.yml`

### L-39 One person's token served seven purposes
**Failure.** The owner account's token was named 70 times, and nine workflows passed every secret to whatever they called. When it expired, the only sign was a refusal on the next run.
**Rule.** No workflow names a personal access token, and none inherits secrets.
**Check.** `examples/workflows/invalid/token.a-persons-token.yml`

### L-40 A gate was allowed to fail
**Failure.** The eval gate ran only with its failure ignored, and the release never looked at its result.
**Rule.** No step or job continues on error.
**Check.** `examples/workflows/invalid/soft.a-failure-nobody-sees.yml`

### L-41 A hung step ran for six hours
**Failure.** Jobs with no limit ran to the platform's maximum, and about a fifth of sampled job time was a runner asleep waiting for a rate limit.
**Rule.** Every job with steps sets a time limit. Waiting is a deferral the Kernel returns, never a sleep.
**Check.** `examples/workflows/invalid/timeout.a-hung-step-runs-six-hours.yml`

### L-42 Decisions were written in workflow files
**Failure.** A thousand lines of top-level shell could not be called as a unit, and every defect in workflow logic was found after merge.
**Rule.** A `run:` block is at most ten lines and calls a module. The decision is in the Kernel, where a test can call it.
**Check.** `examples/workflows/invalid/length.logic-in-a-workflow.yml`

### L-43 A stranger's pull request ran beside the secrets
**Failure.** A workflow on the target-branch event runs with secrets in scope, on a pull request anyone can open, and each one needed its own hand-written guard.
**Rule.** No workflow runs on that event.
**Check.** `examples/workflows/invalid/target.secrets-beside-a-strangers-code.yml`

## Waiting on a part that is not built

### L-44 Success was reported for work that was not done
**Failure.** "pr-review announces an approval it never created" (issue 1874). The author posted "Fixed" for changes it never pushed, and reported a rebase complete with no commit.
**Rule.** A claim is written by `apply`, from what it wrote and then read back. The model's output has no field for one.
**Check.** waiting on `harness/`

### L-45 The author edited the tests it was judged by
**Failure.** "[Phase 4] Name and guard the "agent optimizes the check, not the intent" failure mode" (issue 1468): tests edited to match the code, a fixture changed to turn a monitor green, a test tool vendored to satisfy a check.
**Rule.** `apply` refuses a change by an implementing Role to a test, a fixture, a threshold or an acceptance contract that judges it.
**Check.** waiting on `harness/`

### L-46 The model held the credential that could write
**Failure.** The author's job held the owner account's token and kept it for pushing. "Never push" was a sentence in the prompt.
**Rule.** No job holds both a model credential and a credential that can write.
**Check.** waiting on `harness/`

### L-47 Agents acted as the Maintainer
**Failure.** "dev-lead regressed to committing as donpetry-bot (review-only machine user) instead of don-petry" (issue 1316), because identity came from a shared variable. The Maintainer could not review the agent's pull requests, and the agent skipped the Maintainer's requests as its own.
**Rule.** Each Role declares its own App, and no two share one.
**Check.** waiting on `roles/`

### L-48 A merged fix was not what ran
**Failure.** Twice in one week a fix merged and the failure went on, because agents ran from a tag that had not moved: "Script-only changes never reach the fleet" (issue 1592).
**Rule.** Every Run records the Release it ran, and a change is live only when the Channel that serves it points at it.
**Check.** waiting on `release/`

### L-49 A caller ran ahead of what it called
**Failure.** A caller passed an input the pinned Release did not declare, and every run failed at startup, after merge, because a pull request's own checks run the old caller.
**Rule.** The dispatcher and what it dispatches ride one Release.
**Check.** waiting on `release/`

### L-50 Promotion counted green runs in a ring with no members
**Failure.** The gate read run conclusions, the rings were empty, all four channels pointed at one commit, and the gate was overridden by hand on four dates in ten days.
**Rule.** A candidate with no Runs behind it, each with Effects read back, is refused.
**Check.** waiting on `release/`

### L-51 Nobody noticed
**Failure.** "Engine-token liveness monitoring: a 7-day fleet-wide dev-lead outage went unalerted, and pr-review fails open" (issue 1587). The daily failure report itself stopped, and nothing reported that.
**Rule.** One cause raises one alert, a pass that did not run is itself reported, and an item that needs a person is assigned to one.
**Check.** waiting on `controller/`

### L-52 The Maintainer's attention was the real limit
**Failure.** Runs rose about fivefold while merges stayed at 14 to 36 a week. The Maintainer cleared holds 64 times across 150 merged pull requests.
**Rule.** While more items need the Maintainer than a declared number, only a Run that unblocks a merge is admitted.
**Check.** waiting on `controller/`

### L-53 A credential's permissions were assumed
**Failure.** A change of credential met a refusal on its first real write and was reverted. An App that could write contents could not move a tag on a repo with workflows, and the fleet was broken for six days.
**Rule.** Each write a Role may make is tried once on a canary repo, and the recorded response is what the fake GitHub is held to.
**Check.** waiting on `adapters/`

### L-54 The tests passed against a fake that accepted anything
**Failure.** The shared stub of the GitHub command returned empty for calls it did not know, so real flags and filters were never exercised.
**Rule.** Every rule the fake GitHub applies cites a response recorded from the real one, and the required check prints the rules that do not.
**Check.** waiting on `adapters/`

### L-55 The fleet and every session shared one API quota
**Failure.** "The fleet and every session share one GitHub API quota" (issue 2197). It ran out on 2026-10-10 and failed a workflow.
**Rule.** What a pass costs is a fact that is read, and a pass has a budget.
**Check.** waiting on `adapters/`

## Not carried over

These failures were real, and nothing here can hold a rule for them yet, so they are recorded as
open questions and not as lessons: finished work lost when a run timed out, since resuming a Run is
not designed; an issue closed as done with nothing merged, since the issue Lifecycle is not
designed; and a fix that moved a failure instead of removing it, which no check can tell apart from
a fix.
