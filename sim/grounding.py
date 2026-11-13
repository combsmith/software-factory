"""What the fake GitHub in `world.py` assumes about the real one, and what grounds each assumption.

Each rule the fake applies is marked where it is applied, by a comment `# GitHub: <code>`, and is
listed here once: its code, the rule in words, the trials of the design's section 6 that ask it
(empty when none does), the fixture under `trials/` that grounds it (None until one does; a tuple
when more than one trial's fixture shows it holds), and, where no trial asks it, one sentence saying
why none can, "assumed, no trial can ask it: ..." (None where a trial does).
A rule with no fixture is unverified, and `make verify` prints it with what it waits on (design,
section 4.5). A rule no trial asks can be grounded only once a trial for it is added to section 6,
so each either names the trial that will, or says why none can (issue 190).
A trial a rule names asks it in its row: ASKS quotes, for each, the words of that row's question
that do (issue 265), so a rule that names the wrong row is refused.
`tools/check_trials.py` holds this list and the marks to each other, each quote to its row, and
each fixture named here to its schema. It reads RULES and ASKS as literals, so that it can judge a
copy of the repo: keep them so.
"""

RULES = (
    # trials/P-58.json, trials/P-58.reader.json: the Maintainer's edit, cubic's 23 s after opening, CodeRabbit's and a
    # workflow's bot's each moved the time; a push and a title's edit did not. No editor is read (decision 0140).
    # trials/P-58.deleted.json: a person's two edits, cubic's 9 s after opening and CodeRabbit's each moved it again, and
    # a revision a person then deleted from the history kept its time and moved nothing (issue 549).
    ("a_description_edit_moves_its_time", "An edit of a pull request's description, by a person, a bot or an App, moves "
     "the time of its last edit, `lastEditedAt` and the newest `editedAt` among its `userContentEdits`; a push and an "
     "edit of its title alone move neither", ("P-58",),
     ("trials/P-58.json", "trials/P-58.reader.json", "trials/P-58.deleted.json"), None),
    ("an_app_edits_a_description", "Bots and Apps edit a pull request's description, a reviewer App's summary seconds "
     "after it opens among them", ("P-58",),
     ("trials/P-58.json", "trials/P-58.reader.json", "trials/P-58.deleted.json"), None),
    ("a_push_is_new_content", "A push gives the pull request new content", ("P-29",), "trials/P-29.base.json", None),
    ("the_pusher_is_the_last_pusher", "The account that pushed the head is read as its last pusher, from the newest "
     "entry of the head branch's activity, a person's push and an App's alike: the entry names the App's bot login, "
     "with actor.type Bot", ("P-28",), ("trials/P-28.json", "trials/P-28.app.json"), None),
    # No trial asks this: P-28 saw each push's entry within 11 s and tried nothing shorter. It is the one way the fact
    # can be unreadable, so the fake reads it now and then, and the Kernel must let nothing through on it.
    ("a_push_is_missing_from_the_activity", "The push that left the head can be missing from its branch's activity for "
     "a pass, and the last pusher then reads null",
     (), None,
     "assumed, no trial can ask it: a race between a push and the read of the activity, which no trial can force; P-28 "
     "saw each entry within 11 s"),
    ("an_app_pushes_to_the_head", "An App can push to the head of a pull request", ("P-7",), "trials/P-7.json", None),
    ("an_approval_is_dismissed_by_a_push", "Under a ruleset that dismisses stale approvals on a push, a push dismisses "
     "each standing approval, and the timeline names an App that pushed as its dismisser", ("P-7",),
     "trials/P-7.json", None),
    # trials/P-38.json: the Maintainer's push dismissed two approvals, his own and the machine user's, each named to him.
    ("a_persons_push_names_the_person_as_dismisser", "Under a ruleset that dismisses stale approvals on a push, the "
     "timeline names a person who pushed, as that person, the dismisser of each approval the push dismissed",
     ("P-38",), "trials/P-38.json", None),
    ("an_approval_stands_without_stale_dismissal", "Under a ruleset that does not dismiss stale approvals, a push leaves "
     "an earlier approval in place", ("P-1",), None, None),
    # trials/P-41.json: canary pull requests 64 (a request, a push, two dismissals) and 66 (the controller's labels).
    ("a_request_for_changes_survives_a_push", "A push leaves a request for changes standing", ("P-41",),
     "trials/P-41.json", None),
    ("an_app_can_dismiss_a_review", "An App with pull_requests: write can dismiss a person's review, and the timeline "
     "says which App and what the review was before (previousReviewState)", ("P-41",), "trials/P-41.json", None),
    # trials/P-42.json: a pull request's head, its checks read at once and an hour later, and the new head after a push.
    # trials/P-42.push.json: in the port's own read, the required check concluded on head A and, read at once after head B
    # was pushed, queued on B; for four seconds GitHub listed none on B at all, read and not kept, which the Kernel reads
    # as pending too (issue 807).
    ("a_push_restarts_the_checks", "A push sets every required check pending again", ("P-42",), "trials/P-42.push.json",
     None),
    # trials/P-42.rollup.json: the required check read queued in the status rollup, and 11 minutes later success, with
    # nothing done between but reads. trials/P-42.push.json: so in the port's own read, queued, then success 71 s on.
    ("a_check_reports_on_its_own", "A pending required check reports success or failure with no one asking",
     ("P-42",), "trials/P-42.push.json", None),
    # trials/P-42.json: neutral, skipped and cancelled each kept an hour after the last post, and a job stopped at its
    # timeout concluded cancelled, with its check run and its run (issue 388; a step's own timeout fails,
    # trials/P-42.step-timeout.json). P-42 saw no timed_out and no stale: the rule below says why they stay (issue 496).
    # trials/P-42.port.json: the port's own read of that head ten days on gives each the same conclusion (issue 807).
    ("a_check_can_time_out_or_give_no_verdict", "A required check can time out, concluding cancelled, or give no "
     "verdict, neutral or skipped, and keeps that conclusion until the content changes or a person runs it again",
     ("P-42",), ("trials/P-42.json", "trials/P-42.port.json"), None),
    ("a_check_concludes_timed_out_or_stale", "A required check can conclude timed_out or stale, which the checks API "
     "lists as conclusions", (), None,
     "assumed, no trial can ask it: GitHub concluded a job stopped at its timeout cancelled (trials/P-42.json), and it "
     "gives stale only to a check run left incomplete for 14 days, which no trial can wait for; the fake still gives "
     "both, so the Kernel's reading of each is met"),
    # trials/P-42.rollup.json: the status rollup the port reads held the same runs as filter=latest, by id, name, suite
    # and App, five Apps on one head. It left out a run its job's re-run replaced, and a check a job created that a later
    # one created under its name replaced; a job's run and a created check of one name both stayed there, as in
    # trials/P-35.json (issue 496). trials/P-42.port.json: the port's own read of two such heads, every check run read
    # with its name and App, against the fixture's own nodes (issue 807).
    ("a_check_is_read_by_name_from_every_app", "Every check run on the head is read with its exact name and the id of "
     "the App that reported it, from every App, never merged or renamed; the status rollup leaves out only a run that "
     "its job's re-run, or a later check created under its name in its suite, replaced", ("P-42",),
     ("trials/P-42.rollup.json", "trials/P-42.port.json"), None),
    # trials/P-42.rollup.json: a re-run replaced its own run in the status rollup and the other suite's run of the name
    # stayed, and a later check a job created under a name replaced the one created earlier in its suite; trials/P-35.json
    # shows a job's run and a created check of one name both kept there, either first. One job's re-run also gave its
    # run's other jobs new check runs with their old conclusions, which changes no verdict (issue 496).
    # trials/P-42.port.json: the port's own read of that head ten days on holds the re-run's check run, not the one it
    # replaced, and the other suite's beside it (issue 807).
    ("a_rerun_replaces_only_its_own_run", "A re-run of a job replaces only that job's earlier run, in its own check "
     "suite, and a check a job creates replaces only one created earlier under its name there; a job's run and a "
     "created check of one name both stay, and so do two workflow runs on one commit", ("P-42",),
     ("trials/P-42.rollup.json", "trials/P-42.port.json"), None),
    # trials/P-65.json: on canary pull request 102 each cancelled run's suite and workflow run concluded cancelled, its
    # if: always() judging check failure; the push back to A and the reopening each started a run with a suite of its
    # own beside the cancelled one's, which stayed; a re-run kept its run's id and suite, the rollup giving its latest
    # attempt alone; and one rollup read gave each check run its workflow run's id and its suite's conclusion (issue 749).
    ("a_check_names_its_run_and_suite", "Each check run names its workflow run's id, none for a check no workflow ran, "
     "and its check suite's conclusion, none while the suite has not concluded; a re-run keeps its run's id and suite",
     ("P-65",), "trials/P-65.json", None),
    ("a_cancelled_run_stays_beside_a_later_run", "A workflow run cancelled mid-way concludes its suite cancelled and its "
     "if: always() judging check failure, and stays on its head beside a later run of the same file that a push back to "
     "the head, a reopening or a re-run of an earlier run starts; no run's id says which is later", ("P-65",),
     "trials/P-65.json", None),
    # trials/P-42.json: the pr-review App and an Actions job each posted under p2-queue-check; trials/P-42.port.json: the
    # port's own read of pull request 65's head, a fortnight on, still holds the job's (issue 807).
    ("any_app_posts_a_check_under_any_name", "Any App with checks: write can post a check run under any name, a "
     "required Lens's too, and it stays on that head: a check run cannot be deleted", ("P-42",),
     ("trials/P-42.json", "trials/P-42.port.json"), None),
    ("a_check_is_read_with_its_own_jobs_file", "A check run GitHub Actions reports is read with the path of its check "
     "suite's workflow run only where its details are that job's own, with the permissions the reader and the Controller "
     "hold. A check a job creates with GITHUB_TOKEN lands in the first Actions suite on the head, with that suite's path "
     "and its details at /runs/ID, on another branch's head too, so it reads with none. A dynamic run's file is null, and "
     "a check run no workflow ran, as GitHub Advanced Security's, has no run: each reads with none", ("P-35",),
     "trials/P-35.json", None),
    ("a_job_creates_a_check_in_another_suite", "A job with checks: write can create a check run that lands in another "
     "workflow's suite and reads with its name, App and path; GitHub keeps its details at /runs/ID, and only a real job's "
     "are that job's own", ("P-35",), "trials/P-35.json", None),
    ("actions_runs_a_job_under_any_name", "GitHub Actions reports every job in the repo as one App, 15368, one a pull "
     "request adds in a workflow file of its own under a required Lens's check name among them, and its check run "
     "names that file", ("P-35",), "trials/P-35.json", None),
    # Overturning a failure is not shown, nor what an upload GitHub processes does: each of P-36's failed processing, as
    # default setup refuses them. So the fake does neither.
    ("an_upload_turns_codeqls_success_neutral", "An upload to code scanning under CodeQL's tool and category, by an "
     "identity holding security_events: write, turns the conclusion of the check run CodeQL that GitHub Advanced Security, "
     "57789, reports from success to neutral, on the same check run, though GitHub fails to process the upload",
     ("P-36",), "trials/P-36.json", None),
    # Contradicted by P-2 (trials/P-2.queue.json): GitHub refuses an App's push, through the contents API, to a queued
    # pull request's branch (409), and the queue merges it unchanged; a git push while queued is not asked. Left
    # unverified, as the fake applies it: changing the fake is a story of its own.
    ("a_push_leaves_the_queue", "A push takes the pull request out of the merge queue", ("P-2",), None, None),
    ("an_app_enters_the_queue", "An App can put an approved pull request in the merge queue, with contents: write; "
     "without it GitHub refuses the enqueue", ("P-2",), "trials/P-2.least.json", None),
    ("the_queue_merges", "A pull request in the merge queue merges, unless a push takes it out first",
     ("P-2",), None, None),
    # trials/P-2.port.json: the timeline port's own read of 100, a person's enqueue, and 70, the queue App's, each the
    # enqueue then the merge with no act of a Factory identity's between, and the facts port's read of each head's
    # required check concluded success before it (issue 807). Its verdict stays fail against its condition as written,
    # and grounds the rule as trials/P-5.json, failed as written, grounds its own (the Factory Builder's ruling on #844):
    # the act between enqueue and merge on 70 was the Maintainer's review, a person's act; the queue's merge did not
    # depend on it, since the approval the ruleset requires was already given at the enqueue, the machine user's at
    # 01:59:21Z on 70's head before the queue App's enqueue at 02:24:59Z; and the condition was stricter than the rule,
    # which forbids only a Factory identity's act between.
    ("the_queue_merges_on_its_required_checks", "The merge queue merges a queued pull request once its required checks "
     "pass, whoever enqueued it, with no read of the Factory's between", ("P-2",),
     ("trials/P-2.no-pass.json", "trials/P-2.queue-app.json", "trials/P-2.port.json"), None),
    ("an_app_leaves_the_queue", "An App can take a pull request out of the merge queue, with contents: write; "
     "without it GitHub refuses the dequeue", ("P-2",), "trials/P-2.least.json", None),
    ("a_writer_can_dismiss_an_approval", "A person with write access can dismiss the machine user's approval, and the "
     "timeline says who and what the review was before", ("P-41",), "trials/P-41.json", None),
    # Contradicted by this repo's own merge queue, which ran the verify workflow on #243's merge group and ejected it on
    # a failure. Left unverified, as it is, until P-2 records it: changing the fake is a story of its own.
    ("the_merge_group_is_not_checked", "The merge queue merges without running the checks on the merge group",
     ("P-2",), None, None),
    ("the_machine_users_approval_counts", "The machine user's approval counts when an App pushed last",
     ("P-7",), "trials/P-7.json", None),
    ("an_approval_can_fail_to_land", "The machine user's approval can fail to land, by a fault of the item or of the "
     "environment, and its Run then concludes failure", (), None,
     "assumed, no trial can ask it: a fault of the item or of the environment that drops an approval cannot be forced "
     "on demand"),
    # trials/P-2.port.json: the timeline port's own read of 58, the queue's removal after the enqueue and no merge, and
    # its read of 58's reviews, the machine user's approval standing (issue 807).
    ("the_queue_can_eject", "The merge queue can take a pull request out without merging it, and its approval stays",
     ("P-2",), ("trials/P-2.queue.json", "trials/P-2.port.json"), None),
    ("the_timeline_shows_each_act", "Each approval, enqueue, dequeue and label a Factory identity makes is on the "
     "timeline, with its actor, so the acts since a person with write access acted can be counted",
     ("P-2", "P-41"), None, None),
    ("a_lens_review_opens_a_thread", "A Lens's review can open a review thread on the pull request",
     ("P-5",), "trials/P-5.json", None),
    ("an_app_resolves_any_thread", "An App with contents: write and pull_requests: write can resolve any review "
     "thread, a person's too, and the thread says who resolved it; with pull_requests: write alone GitHub refuses it",
     ("P-5",), "trials/P-5.json", None),
    ("an_app_can_label", "An App can add or remove a control label on a pull request, a Hold or hands-off among them",
     ("P-41",), "trials/P-41.json", None),
    # trials/P-32.json: each label event read in GraphQL with its actor and time; trials/P-32.port.json: the timeline
    # port's own read, the REST timeline, of a pull request a Factory App labelled, each event so (issue 807).
    ("a_label_event_names_its_actor", "The timeline's labeled and unlabeled events say who added or removed each "
     "label, "
     "and when", ("P-32",), ("trials/P-32.json", "trials/P-32.port.json"), None),
    # trials/P-41.json read each actor on its reviews, dismissals and labels by its type; trials/P-41.threads.json each
    # on a thread as the threads port does (decision 0067): every comment's author by GraphQL's type, and the resolver,
    # whom resolvedBy types a User though it was an App, by the permission read of its login, which answers Bot, and
    # User for a person who resolved one.
    ("an_actor_has_a_kind", "Every actor GitHub names on a review, a dismissal, a thread or a label event has an "
     "account type, a User or a Bot, from which, with the configuration, the port tells a person, a Lens's App, any "
     "other App and the machine user apart, never from a name's spelling", ("P-41",),
     ("trials/P-41.json", "trials/P-41.threads.json"), None),
    # trials/P-44.json: four pushes under one concurrency group, cancel-in-progress false; the second and third runs
    # were cancelled as a newer one queued, with no runner and no step, and the running one finished. GitHub lists a
    # Run waiting for the group as pending, which the records port reads as queued. That the group's first Run holds it
    # while it waits for a runner, so that only a Run behind it is cancelled, is GitHub's documented rule, which P-44
    # did not need to show: its first run was in progress at once.
    ("a_run_waits_its_turn", "One Run on an item is in progress and at most one waits: a newer Run in the item's "
     "concurrency group cancels the one waiting, which never starts, and never the one running",
     ("P-44",), "trials/P-44.json", None),
    # trials/P-64.json: of two runs in one group the second's job waited 53 s. While it waited, pending, the jobs API
    # gave its started_at as its creation, as the run's run_started_at stayed; in progress and completed it gave
    # 19:44:48Z, a second after the first job ended. The records port reads that as `began_at` (decision 0193).
    # trials/P-44.json: a job cancelled while it waited ended completed with no runner, its started_at its creation.
    ("a_run_begins_with_its_job", "A Run's record says when it was made; when it left its item's lane and began is its "
     "job's start, given only once the job is in progress or completed with a runner, and a Run cancelled while it "
     "waited never began", ("P-64", "P-44"), ("trials/P-64.json", "trials/P-44.json"), None),
    ("a_queued_run_is_listed", "A Run is in the list of run records from when it is queued, before its job starts",
     ("P-17",), "trials/P-17.json", None),
    ("a_new_run_is_listed_unnamed", "A Run can be listed under its workflow's name, not its run-name, for its first "
     "seconds", ("P-17",), "trials/P-17.json", None),
    ("a_run_whose_name_never_resolves_stays_listed_unnamed", "A run whose run-name never resolves is listed under "
     "its workflow's name for as long as its record is kept", (), None,
     "assumed, no trial can ask it: a run-name that never resolves is a fault of a Factory workflow's name expression "
     "or of the Controller's own dispatch, the one dispatcher whose runs count, not a behaviour of GitHub a trial could "
     "make happen on a sound workflow; GitHub documents that a run-name that cannot be evaluated shows the workflow's "
     "name, as P-17 saw in its first seconds"),
    ("a_new_run_is_listed_late", "The newest Run can be missing from the list of run records for one pass",
     ("P-22",), "trials/P-22.json", None),
    # trials/P-43.json: with a filter, as the records port reads one, this repo's run list stops at 1,000 of the 1,879 it
    # counts; page 1,001 is empty and counts 0, so only the first page's count says the oldest are missing. Unfiltered,
    # the list read whole, all 1,873 runs.
    ("a_run_list_stops_short", "The list of run records can stop short, with the oldest Runs missing",
     ("P-43",), "trials/P-43.json", None),
    # trials/P-42.json and P-42.step-timeout.json show both, but P-42's row asks of a required check, not of a Run's
    # job: P-18's row asks this, and it stays unverified until P-18 has a fixture.
    ("a_run_past_its_limit_fails", "A Run's job stopped by a step's own timeout-minutes concludes failure, a later "
     "if: always() step still running; one GitHub stops at the job's own timeout concludes cancelled", ("P-18",), None,
     None),
    ("a_superseded_run_fails", "A Run whose apply refuses, or that the Kernel refuses as it starts, concludes failure",
     ("P-18",), None, None),
    ("a_short_diff_says_so", "A diff read short says so, and is not mistaken for the whole",
     ("P-29",), "trials/P-29.truncated.json", None),
    # trials/P-43.json: reviews, threads, labels, timeline events, files and a head's checks, each read one to a page,
    # said so, by hasNextPage with an endCursor in GraphQL and a Link with rel=next, or a total_count, in REST.
    ("a_short_list_says_so", "A list of reviews, threads, checks or timeline events read short says so",
     ("P-43",), "trials/P-43.json", None),
    # trials/P-43.json: a rename, a copy and an edit are listed once each, by path; REST's previous_filename names the
    # renamed file's old path, GraphQL's files give none, so the port reads them by REST; an unchanged copy was listed as
    # added, with no source. The compare the port reads, recorded after the trial, names them the same way (issue 138).
    ("a_pull_request_lists_the_paths_it_changes", "Every file a pull request changes is read once, as many as the diff "
     "counts, by its path from the top of the repo, with the path a renamed file had before; an unchanged copy is "
     "listed as an added file", ("P-43",), "trials/P-43.json", None),
    # The port reads a compare, not this list (issue 284): a change of more files than a compare lists, 300 as GitHub
    # documents it and no trial records, is read short by changed_files alone, which the fixture's 3,001 shows.
    ("a_path_list_can_leave_out_a_file", "A list of the files a pull request changes can leave one out while it says it "
     "was read in full; it then holds fewer records than the diff has files: GitHub's list stops at its cap with a 200 "
     "and an empty next page, and only changed_files shows it short", ("P-29",), "trials/P-29.truncated.json", None),
    # trials/P-43.json grounds the half read short, page by page; the half cut off at its limit says so only by the
    # pull request's count of files, as trials/P-29.truncated.json shows (a_path_list_can_leave_out_a_file).
    ("a_short_path_list_says_so", "The list of paths a pull request changes, read short or cut off at its limit, says "
     "so", ("P-43",), "trials/P-43.json", None),
    # trials/P-45.json: Dependabot moved actions/checkout's pin in a canary workflow; it opened the pull request and pushed
    # its head as dependabot[bot], a Bot, id 49699333, which GraphQL names dependabot: the port reads it by id and type.
    ("a_dependency_bot_updates_a_workflow_pin", "A dependency bot's update can change the pin of an Action in a "
     "workflow file; the bot opens it and pushes its head, and its class is dependency",
     ("P-45",), "trials/P-45.json", None),
    # The workflow P-45 updated was an ordinary one, so that a Lens's own is updated alike stays unshown.
    ("a_dependency_bot_updates_a_lens_pin", "A dependency bot's update can change the pin of an Action in a Lens's own "
     "workflow file, as it does any other's", ("P-45",), None, None),
    ("an_acceptance_result_names_its_content", "Each result for a criterion of an item's acceptance contract is read "
     "from the check that gave it, with the content it ran on, and stays when the content changes",
     ("P-42",), None, None),
    ("a_short_acceptance_read_says_so", "An acceptance contract and its results read short say so",
     ("P-43",), None, None),
    ("a_result_can_name_a_criterion_the_contract_does_not", "A check can give a result for a criterion the contract at "
     "the head does not name", ("P-42",), None, None),
    ("a_result_expires_with_its_artifact", "A result for a criterion is gone once the artifact it was read from is past "
     "its retention", ("P-16",), None, None),
    ("a_criterion_can_have_a_result_from_each_check_suite", "A criterion can have a result from each check suite that "
     "ran its check on one content, and they can disagree", ("P-42",), None, None),
    # P-35 shows a check's path can be another workflow's, so a result is not fully read with its reporter's file.
    ("an_acceptance_result_names_its_reporter", "Each result for a criterion is read with the check that reported it: "
     "the check run's name, the id of its App and the path of its workflow file, as a check is read",
     ("P-35", "P-42"), None, None),
    ("any_app_gives_a_result_for_any_criterion", "Any App with checks: write, and any job GitHub Actions runs, can give "
     "a result for any criterion of the contract, one only a person passes among them", ("P-42",), None, None),
    # P-38 shows an approval a person's push dismissed stays on its commit, and P-7 one an App's push dismissed. An App
    # dismissing an approval that is not stale is not shown: P-41's App dismissed a request for changes. Left unverified.
    ("a_contract_approval_stays_on_its_commit", "The contract a person approved is read at the commit of the newest "
     "approving review by a person; an approval an App dismisses, as stale or not, stays on its commit, and the "
     "timeline says who dismissed it", ("P-38",), None, None),
    ("a_push_can_change_the_contract", "A push can edit the acceptance contract or a test it names, or delete the "
     "contract, and the digest at the head then differs from the one a person approved",
     (), None,
     "assumed, no trial can ask it: a push changes any file of the head, the contract among them, by git's own rule "
     "and not GitHub's"),
    ("a_read_can_be_stale", "A read can return what an earlier read did",
     (), None,
     "assumed, no trial can ask it: a read served from a cache or a replica is a race no trial can force"),
    ("a_tick_can_be_lost", "A scheduled tick can fail to arrive", ("P-8",), "trials/P-8.ticks.json", None),
    ("anyone_can_comment", "On a public repo anyone can submit a review that only comments",
     (), None,
     "assumed, no trial can ask it: it needs an account outside the org, which no trial has (#27 is the last story to "
     "use the canary token); GitHub documents that anyone may review a public repo"),
    # The issue world's rules (sim/issues.py, issue 43). trials/P-32.json showed the listing's authorAssociation tells
    # an App nothing of write access (CONTRIBUTOR for the org's owner), so write access is read from the repository's
    # collaborator permission instead (issue 222, decision 0048).
    ("a_logins_permission_is_read_from_the_collaborator_endpoint", "A person's write access is read from the "
     "repository's collaborator permission: admin and write are write access, a maintainer's role among them, which "
     "the field gives as write, and read is not; triage, which GitHub documents as read, was not tried", ("P-47",),
     "trials/P-47.json", None),
    # trials/P-33.json: a pull request to a base that is not the default branch carries no closing reference at all
    # (section 6's fallback: the issue Lifecycle serves the default branch only). The reverse read from the issue is
    # no substitute: willCloseTarget is false for a closed-unmerged pull request that keeps its reference, false for
    # every one once the issue is closed, and a keyword link raises no ConnectedEvent; the port reads the pull request.
    # trials/P-33.port.json: the acceptance port's own read of the five, each issue with its repo, and the timeline
    # port's of 38, whose REST events name who changed the draft flag and when (issue 807).
    ("a_closing_reference_is_read_from_any_pull_request", "The issue a pull request to the default branch closes, and "
     "who opened the pull request, are read from a draft, an open, a merged and a closed-unmerged pull request alike; "
     "one to another base carries no reference", ("P-33",), ("trials/P-33.json", "trials/P-33.port.json"), None),
    ("who_changed_the_draft_flag_is_read", "The timeline says who last marked a pull request ready or converted it to a "
     "draft", ("P-33",), ("trials/P-33.json", "trials/P-33.port.json"), None),
    # trials/P-33.json: pull request 38 marked ready, converted to a draft and marked ready again, each its own event a
    # second or two apart; pull request 37, opened as a draft, has none (decision 0141).
    ("a_draft_change_is_timed", "A pull request's timeline gives each conversion to a draft and each marking ready as an "
     "event of its own, with its time to the second; one opened as a draft has no event for it", ("P-33",),
     "trials/P-33.json", None),
    # Trial P-61 (issue 551) asks these; until its fixture is recorded the world links nothing by hand and sets no type,
    # so it gives none of either.
    ("a_link_by_hand_is_timed", "An issue's timeline gives each link of a pull request by hand, in its Development box, "
     "and each unlinking, as an event of its own with its time to the second; a link by a closing keyword raises none",
     ("P-61",), None, None),
    # Seen in trials/P-48.json, whose pull request was closed, reopened, closed and reopened, and merged, each a timed
    # event, the merge's close among them; but P-48's row in section 6 does not ask it, so it waits on P-61's run (issue 672).
    ("a_pull_requests_close_and_reopening_are_timed", "A pull request's own timeline gives each close and each reopening "
     "as an event of its own with its time, a merge's close among them, and a reopening clears its closed_at",
     ("P-61",), None, None),
    ("a_type_change_is_timed", "An issue's timeline gives each setting, change and removal of its type as an event of "
     "its own with its time to the second, and the type before and after", ("P-61",), None, None),
    # trials/P-46.json: an edit to a merged pull request's description after the merge adds the issue its new keyword
    # names to closingIssuesReferences, and closes nothing: the issue stays open and its timeline gains no close; undoing
    # the edit takes it out again. trials/P-33.json: the merge's own close of the issue names the pull request as the
    # closer. The Kernel reads a merge by that close, never by the references now (issue 267).
    ("a_merge_closes_the_issue_it_names_and_an_edit_after_it_closes_nothing", "A merge closes the open issue its "
     "closing references name, and the issue's timeline names the pull request the closer; an edit to its description "
     "after the merge can add an issue to its references, and closes nothing", ("P-33", "P-46"), "trials/P-46.json",
     None),
    # trials/P-34.json: lastEditedAt moves for the body alone; the title's change is the timeline's RenamedTitleEvent,
    # so the content's time is the newer of the two, which the port computes; updatedAt moves for anything.
    ("an_issues_content_time_is_read_apart", "When an issue's title or body last changed is read apart from when "
     "anything on it changed", ("P-34",), "trials/P-34.json", None),
    ("a_reopening_names_its_actor", "Each reopening of an issue is on its timeline, with who did it",
     ("P-34",), "trials/P-34.json", None),
    ("an_issues_close_and_reopening_say_when", "Each close and each reopening of an issue is on its timeline with its "
     "time, so the first close of its present life is read across a reopening", ("P-34",), "trials/P-34.json", None),
    ("an_issues_run_record_expires", "A run record is gone from the list once it is past the retention",
     ("P-16",), None, None),
    # Contradicted by the fake's issues world, where a person merges a stranger's draft; P-2 (trials/P-2.queue.json) saw
    # GitHub refuse a draft both the queue and a person. Left unverified until the fake refuses it.
    ("a_draft_is_not_merged", "A draft pull request cannot be merged, by a person or by the queue",
     ("P-2",), None, None),
    ("a_forks_run_never_counts", "A pull request from a fork runs its own workflow file, on pull_request, never on a "
     "schedule or a dispatch, and I-34 counts none of it", ("P-27",), "trials/P-27.json", None),
    ("a_pass_starts_its_successor", "A pass can dispatch the next with its own job's token", ("P-9",), "trials/P-9.json",
     None),
    ("a_public_event_starts_a_pass", "An event anyone may cause starts the poller's workflow, within a minute or two",
     ("P-20",), "trials/P-20.json", None),
    ("the_pause_is_read_with_the_controllers_token", "The Controller's token, granted the Variables permission at "
     "repository read, reads FACTORY_PAUSED on a repo it is installed on, and the org's as that repo's list of the "
     "org's variables names it; the org's own endpoint refuses that token, so a pass that asks it there reads the "
     "Pause unreadable", ("P-52",), "trials/P-52.json", None),
)

# What each trial a rule names asks of it: the words of the trial's question in section 6 that ask the rule, at least
# four, held there by tools/check_trials.py (issue 265). A row that does not ask a rule, or stops asking it, refuses the
# rule; so does a quote of a trial the rule does not name.
ASKS = {
    "a_push_is_new_content": {"P-29": "Is the hash of a pull request's own diff stable"},
    "the_pusher_is_the_last_pusher": {
        "P-28": "Can the actor who last pushed a pull request's head be read as a fact?",
    },
    "an_app_pushes_to_the_head": {"P-7": "the last-push rule when an App pushed last"},
    "an_approval_is_dismissed_by_a_push": {"P-7": "does an approval given before a push still stand after it"},
    "a_persons_push_names_the_person_as_dismisser": {"P-38": "who does the timeline record as dismissing it?"},
    "an_approval_stands_without_stale_dismissal": {
        "P-1": "under a ruleset that does not dismiss stale approvals, does an approval given before a push still stand"
              " after it?",
    },
    "a_request_for_changes_survives_a_push": {"P-41": "does a request for changes survive the push"},
    "an_app_can_dismiss_a_review": {"P-41": "can an App with `pull_requests: write` dismiss a person's review"},
    "a_push_restarts_the_checks": {"P-42": "after a push, is every required check pending again"},
    "a_check_reports_on_its_own": {"P-42": "does a required check conclude"},
    "a_check_can_time_out_or_give_no_verdict": {
        "P-42": "does a required check conclude `timed_out`, `neutral`, `skipped`, `cancelled` or `stale` and keep "
              "that conclusion until the content changes or a person runs it again",
    },
    "a_check_is_read_by_name_from_every_app": {
        "P-42": "is every check run read with its exact name and its App's id",
    },
    "a_rerun_replaces_only_its_own_run": {
        "P-42": "two workflow runs on one commit both staying, since `filter=latest` is per check suite",
    },
    "a_check_names_its_run_and_suite": {
        "P-65": "does the one GraphQL rollup read of a head's checks give each check run its workflow run's id and its "
                "check suite's conclusion",
    },
    "a_cancelled_run_stays_beside_a_later_run": {
        "P-65": "does its check suite, and its workflow run, conclude cancelled while the run's judging job, which needs "
                "the cancelled job under if: always(), concludes failure",
    },
    "any_app_posts_a_check_under_any_name": {
        "P-42": "can any App with `checks: write`, or any Actions job, post a check run under a required Lens's "
              "check name",
    },
    "a_check_is_read_with_its_own_jobs_file": {
        "P-35": "Can it be read as the `path` of the check run's check suite's workflow run, with the permissions "
              "the reader and the Controller hold",
    },
    "a_job_creates_a_check_in_another_suite": {
        "P-35": "Where does a check run created through the API with `GITHUB_TOKEN` and `checks: write` land",
    },
    "actions_runs_a_job_under_any_name": {
        "P-35": "does a job a pull request adds in a file of its own, under a required Lens's check name, report "
              "under GitHub Actions with that file's path?",
    },
    "a_description_edit_moves_its_time": {
        "P-58": "Does a pull request's `lastEditedAt` move when its description is edited, and not when only its title is, "
                "or when its head is pushed",
    },
    "an_app_edits_a_description": {"P-58": "does an edit by a bot or an App move it?"},
    "an_upload_turns_codeqls_success_neutral": {
        "P-36": "change the conclusion of the check run `CodeQL` that GitHub Advanced Security reports?",
    },
    "a_push_leaves_the_queue": {"P-2": "Does a push take a queued pull request out"},
    "an_app_enters_the_queue": {"P-2": "Can an App enable auto-merge and enter the merge queue"},
    "the_queue_merges": {"P-2": "take a pull request out of it before the queue merges it?"},
    "the_queue_merges_on_its_required_checks": {"P-2": "does the poller read a change before the queue merges it?"},
    "an_app_leaves_the_queue": {"P-2": "take a pull request out of it before the queue merges it?"},
    "a_writer_can_dismiss_an_approval": {
        "P-41": "a person with write access the machine user's approval, the timeline naming who dismissed and the "
              "review's earlier state",
    },
    "the_merge_group_is_not_checked": {"P-2": "does the queue run the required checks on the merge group?"},
    "the_machine_users_approval_counts": {
        "P-7": "Does the machine user's approval satisfy code-owner review and the last-push rule",
    },
    "the_queue_can_eject": {"P-2": "can the queue eject one without merging it, its approval staying"},
    "the_timeline_shows_each_act": {
        "P-2": "Is each enqueue and dequeue on the pull request's timeline, naming its actor?",
        "P-41": "Is every actor named on a review, a dismissal, a thread and a label event read with its account "
              "type",
    },
    "a_lens_review_opens_a_thread": {"P-5": "a review thread opened by another App"},
    "an_app_resolves_any_thread": {
        "P-5": "Can one App resolve a review thread opened by another App or by a third-party reviewer?",
    },
    "an_app_can_label": {"P-41": "can the Controller's App add and remove a control label on a pull request"},
    "a_label_event_names_its_actor": {"P-32": "who added and who removed each label, with the time"},
    "an_actor_has_a_kind": {
        "P-41": "Is every actor named on a review, a dismissal, a thread and a label event read with its account "
              "type, a User or a Bot?",
    },
    "a_run_begins_with_its_job": {
        "P-64": "does the jobs API's `started_at` for its job say when the job left the queue and began",
        "P-44": "cancel the older pending Run",
    },
    "a_run_waits_its_turn": {
        "P-44": "does GitHub keep one Run running and one pending, cancel the older pending Run, and never cancel "
              "the one running?",
    },
    "a_queued_run_is_listed": {"P-17": "visible for a run whose job never started?"},
    "a_new_run_is_listed_unnamed": {"P-17": "Is a run's name set when the run is created"},
    "a_new_run_is_listed_late": {
        "P-22": "How soon after it is started does a Run appear in the list of run records?",
    },
    "a_run_list_stops_short": {"P-43": "can the list of run records stop short with the oldest Runs missing?"},
    "a_run_past_its_limit_fails": {"P-18": "when a job times out or is cancelled?"},
    "a_superseded_run_fails": {
        "P-18": "does a job whose step exits non-zero conclude `failure`, whether its Run refused before its work "
              "or after it?",
    },
    "a_short_diff_says_so": {"P-29": "how does a truncated diff present?"},
    "a_short_list_says_so": {
        "P-43": "say when it was cut short, by a count, a last page or a next cursor that the same read gives",
    },
    "a_pull_request_lists_the_paths_it_changes": {
        "P-43": "Is every file a pull request changes listed once, by its path from the top of the repo, with the "
              "path a renamed or copied file had before?",
    },
    "a_path_list_can_leave_out_a_file": {"P-29": "how does a truncated diff present?"},
    "a_short_path_list_says_so": {
        "P-43": "acceptance results and the files a pull request changes, say when it was cut short",
    },
    "a_dependency_bot_updates_a_workflow_pin": {
        "P-45": "does it open the pull request and push its head under its own `[bot]` identity",
    },
    "a_dependency_bot_updates_a_lens_pin": {
        "P-45": "When a dependency bot updates an Action's pin in a workflow file",
    },
    "an_acceptance_result_names_its_content": {"P-42": "keep that conclusion until the content changes"},
    "a_short_acceptance_read_says_so": {
        "P-43": "run records, acceptance results and the files a pull request changes, say when it was cut short",
    },
    "a_result_can_name_a_criterion_the_contract_does_not": {
        "P-42": "or a result for any criterion of a contract, one the contract does not name among them",
    },
    "a_result_expires_with_its_artifact": {
        "P-16": "How long are run records, logs and artifacts kept in a public repo?",
    },
    "a_criterion_can_have_a_result_from_each_check_suite": {"P-42": "two workflow runs on one commit both staying"},
    "an_acceptance_result_names_its_reporter": {
        "P-35": "Where does each check run's workflow file come from",
        "P-42": "is every check run read with its exact name and its App's id",
    },
    "any_app_gives_a_result_for_any_criterion": {
        "P-42": "or any Actions job, post a check run under a required Lens's check name, or a result for any "
              "criterion of a contract",
    },
    "a_contract_approval_stays_on_its_commit": {
        "P-38": "does the review stay on the commit it approved, readable with that commit and its reviewer",
    },
    "a_tick_can_be_lost": {"P-8": "how often do scheduled ticks arrive in the new repo?"},
    "a_logins_permission_is_read_from_the_collaborator_endpoint": {
        "P-47": "Can the reader App read a login's repository permission",
    },
    "a_closing_reference_is_read_from_any_pull_request": {
        "P-33": "Can the issue a pull request closes be read from a draft, an open, a merged and a closed-unmerged "
              "pull request alike, with its opening actor; and does a pull request to a branch that is not the "
              "default one carry it?",
    },
    "who_changed_the_draft_flag_is_read": {"P-33": "Can who last changed the draft flag be read?"},
    "a_draft_change_is_timed": {"P-33": "Can who last changed the draft flag be read?"},
    "a_pull_requests_close_and_reopening_are_timed": {
        "P-61": "does a pull request's own timeline give each close and each reopening as an event of its own with its "
              "time, a reopening clearing its closed_at?",
    },
    "a_link_by_hand_is_timed": {
        "P-61": "each link of a pull request by hand in its Development box and its unlinking, as an event of its own "
              "with its time to the second",
    },
    "a_type_change_is_timed": {"P-61": "Does an issue's timeline give each change of its type"},
    "a_merge_closes_the_issue_it_names_and_an_edit_after_it_closes_nothing": {
        "P-33": "Can the issue a pull request closes be read from a draft, an open, a merged and a closed-unmerged "
              "pull request alike",
        "P-46": "Does a merged pull request's closing reference change when its description is edited after the "
              "merge",
    },
    "an_issues_content_time_is_read_apart": {
        "P-34": "Can the time an issue's title or body last changed be read, apart from the time anything on it "
              "changed",
    },
    "a_reopening_names_its_actor": {"P-34": "and each reopening, with who did it?"},
    "an_issues_close_and_reopening_say_when": {"P-34": "and each reopening, with who did it?"},
    "an_issues_run_record_expires": {"P-16": "How long are run records, logs and artifacts kept in a public repo?"},
    "a_draft_is_not_merged": {"P-2": "is a draft ever merged by a person or the queue"},
    "a_forks_run_never_counts": {"P-27": "can it never be a schedule or dispatch run?"},
    "a_pass_starts_its_successor": {"P-9": "Can a pass start the next one with the default workflow token?"},
    "a_public_event_starts_a_pass": {
        "P-20": "Does an event that anyone may cause, such as starring a repo, still start a workflow",
    },
    "the_pause_is_read_with_the_controllers_token": {
        "P-52": "with the Variables permission at repository read alone, read `FACTORY_PAUSED` on a repo it acts in",
    },
}
