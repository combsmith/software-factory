"""What the fake GitHub in `world.py` assumes about the real one, and what grounds each assumption.

Each rule the fake applies is marked where it is applied, by a comment `# GitHub: <code>`, and is
listed here once: its code, the rule in words, the trials of the design's section 6 that ask it
(empty when none does), the fixture under `trials/` that grounds it (None until one does; a tuple
when more than one trial's fixture shows it holds), and, where no trial asks it, one sentence saying
why none can, "assumed, no trial can ask it: ..." (None where a trial does).
A rule with no fixture is unverified, and `make verify` prints it with what it waits on (design,
section 4.5). A rule no trial asks can be grounded only once a trial for it is added to section 6,
so each either names the trial that will, or says why none can (issue 190).
`tools/check_trials.py` holds this list and the marks to each other, and each fixture named here
to its schema. It reads RULES as a literal, so that it can judge a copy of the repo: keep it one.
"""

RULES = (
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
    # Contradicted by trials/P-7.json: under the ruleset's dismiss_stale_reviews_on_push, the App's push dismissed the
    # machine user's approval, and the timeline names the pusher as the dismisser. Left unverified, as it is: changing
    # the fake is a story of its own (sim/AGENTS.md, "Known to differ").
    ("an_approval_survives_a_push", "A push leaves an earlier approval in place", ("P-7", "P-29"), None, None),
    ("a_request_for_changes_survives_a_push", "A push leaves a request for changes standing", ("P-41",), None, None),
    ("an_app_can_dismiss_a_review", "An App with pull_requests: write can dismiss a person's review, and the timeline "
     "says which App and what the review was before (previousReviewState)", ("P-41",), None, None),
    ("a_push_restarts_the_checks", "A push sets every required check pending again", ("P-42",), None, None),
    ("a_check_reports_on_its_own", "A pending required check reports success or failure with no one asking",
     ("P-42",), None, None),
    ("a_check_can_time_out_or_give_no_verdict", "A required check can conclude timed_out, neutral, skipped, cancelled "
     "or stale, and keeps that conclusion until the content changes or a person runs it again",
     ("P-42",), None, None),
    ("a_check_is_read_by_name_from_every_app", "Every check run on the head is read with its exact name and the id of "
     "the App that reported it, from every App, never dropped, merged or renamed", ("P-42",), None, None),
    ("a_rerun_replaces_only_its_own_run", "Only a re-run of the same job in the same check suite replaces an earlier "
     "check run: filter=latest is per check suite, so two workflow runs on one commit both stay", ("P-42",), None,
     None),
    ("any_app_posts_a_check_under_any_name", "Any App with checks: write can post a check run under any name, a "
     "required Lens's too, and it stays on that head: a check run cannot be deleted", ("P-42",), None, None),
    ("a_check_names_the_workflow_that_ran_it", "Every check run GitHub Actions reports is read with the path of the "
     "workflow file that ran it, the path of its check suite's workflow run as GitHub gives it, a dynamic/ one "
     "verbatim, with the permissions the reader and the Controller hold; a check run no workflow ran, as GitHub "
     "Advanced Security's, is read with none", ("P-35",), None, None),
    ("actions_runs_a_job_under_any_name", "GitHub Actions reports every job in the repo as one App, 15368, one a pull "
     "request adds in a workflow file of its own under a required Lens's check name among them, and its check run "
     "names that file", ("P-35",), None, None),
    ("only_codeql_gives_the_code_scanning_verdict", "Only CodeQL's own analysis gives the conclusion of the check run "
     "CodeQL that GitHub Advanced Security, 57789, reports: an upload to code scanning under CodeQL's tool and "
     "category, by an identity holding security_events: write, cannot replace that verdict on the head",
     ("P-36",), None, None),
    ("a_push_leaves_the_queue", "A push takes the pull request out of the merge queue", ("P-2",), None, None),
    ("an_app_enters_the_queue", "An App can put an approved pull request in the merge queue", ("P-2",), None, None),
    ("the_queue_merges", "A pull request in the merge queue merges, unless a push takes it out first",
     ("P-2",), None, None),
    ("a_pass_comes_before_the_merge", "The merge queue merges a pull request only after a pass has read it whole and "
     "current, and found the same facts GitHub holds at the merge", ("P-2",), None, None),
    ("an_app_leaves_the_queue", "An App can take a pull request out of the merge queue", ("P-2",), None, None),
    ("a_writer_can_dismiss_an_approval", "A person with write access can dismiss the machine user's approval, and the "
     "timeline says who and what the review was before", ("P-41",), None, None),
    # Contradicted by this repo's own merge queue, which ran the verify workflow on #243's merge group and ejected it on
    # a failure. Left unverified, as it is, until P-2 records it: changing the fake is a story of its own.
    ("the_merge_group_is_not_checked", "The merge queue merges without running the checks on the merge group",
     ("P-2",), None, None),
    ("the_machine_users_approval_counts", "The machine user's approval counts when an App pushed last",
     ("P-7",), "trials/P-7.json", None),
    ("an_approval_can_fail_to_land", "The machine user's approval can fail to land, by a fault of the item or of the "
     "environment, and its Run then concludes failure", ("P-7",), None, None),
    ("the_queue_can_eject", "The merge queue can take a pull request out without merging it, and its approval stays",
     ("P-2",), None, None),
    ("the_timeline_shows_each_act", "Each approval, enqueue, dequeue and label a Factory identity makes is on the "
     "timeline, with its actor, so the acts since a person with write access acted can be counted",
     ("P-8",), None, None),
    ("a_lens_review_opens_a_thread", "A Lens's review can open a review thread on the pull request",
     ("P-5",), None, None),
    ("an_app_resolves_a_lens_thread", "The reviewer's App can resolve a thread a Lens opened", ("P-5",), None, None),
    ("an_app_resolves_any_thread", "An App with pull_requests: write can resolve any review thread, a person's too, "
     "and "
     "the thread says who resolved it", ("P-5",), None, None),
    ("an_app_can_label", "An App can add or remove a control label on a pull request, a Hold or hands-off among them",
     ("P-41",), None, None),
    ("a_label_event_names_its_actor", "The timeline's labeled and unlabeled events say who added or removed each "
     "label, "
     "and when", ("P-32",), "trials/P-32.json", None),
    ("an_actor_has_a_kind", "Every actor GitHub names on a review, a dismissal, a thread or a label event has an "
     "account type, a User or a Bot, from which, with the configuration, the port tells a person, a Lens's App, any "
     "other App and the machine user apart, never from a name's spelling", ("P-41",), None, None),
    ("a_run_waits_its_turn", "One Run on an item is in progress, and any number wait queued behind it",
     ("P-44",), None, None),
    ("a_queued_run_is_listed", "A Run is in the list of run records from when it is queued, before its job starts",
     ("P-17",), "trials/P-17.json", None),
    ("a_new_run_is_listed_unnamed", "A Run can be listed under its workflow's name, not its run-name, for its first "
     "seconds", ("P-17",), "trials/P-17.json", None),
    ("a_new_run_is_listed_late", "The newest Run can be missing from the list of run records for one pass",
     ("P-22",), "trials/P-22.json", None),
    ("a_run_list_stops_short", "The list of run records can stop short, with the oldest Runs missing",
     ("P-43",), None, None),
    ("a_killed_job_times_out", "A job killed part way concludes timed_out", ("P-18",), None, None),
    ("a_superseded_run_fails", "A Run whose apply refuses, or that never starts, concludes failure",
     ("P-17",), None, None),
    ("a_short_diff_says_so", "A diff read short says so, and is not mistaken for the whole",
     ("P-29",), "trials/P-29.truncated.json", None),
    ("a_short_list_says_so", "A list of reviews, threads, checks or timeline events read short says so",
     ("P-43",), None, None),
    ("a_pull_request_lists_the_paths_it_changes", "Every file a pull request changes is read once, as many as the diff "
     "counts, by its path from the top of the repo, with the path a renamed or copied file had before",
     ("P-43",), None, None),
    ("a_path_list_can_leave_out_a_file", "A list of the files a pull request changes can leave one out while it says it "
     "was read in full; it then holds fewer records than the diff has files: GitHub's list stops at its cap with a 200 "
     "and an empty next page, and only changed_files shows it short", ("P-29",), "trials/P-29.truncated.json", None),
    ("a_short_path_list_says_so", "The list of paths a pull request changes, read short or cut off at its limit, says "
     "so", ("P-43",), None, None),
    ("a_dependency_bot_updates_a_workflow_pin", "A dependency bot's update can change the pin of an Action in a "
     "workflow file, a Lens's own among them; the bot opens it and pushes its head, and its class is dependency",
     ("P-45",), None, None),
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
    ("an_acceptance_result_names_its_reporter", "Each result for a criterion is read with the check that reported it: "
     "the check run's name, the id of its App and the path of its workflow file, as a check is read",
     ("P-35", "P-42"), None, None),
    ("any_app_gives_a_result_for_any_criterion", "Any App with checks: write, and any job GitHub Actions runs, can give "
     "a result for any criterion of the contract, one only a person passes among them", ("P-42",), None, None),
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
    # The issue world's rules (sim/issues.py, issue 43). Contradicted by trials/P-32.json for an App's read: the
    # listing says MEMBER to a person and CONTRIBUTOR to an App, for an owner's issue. Left unverified, as it is: the
    # Factory reads an issue as the machine user, and no trial has yet asked what that read says.
    ("an_issues_author_has_an_association", "The listing of issues says whether an issue's author has write access",
     ("P-32",), None, None),
    # trials/P-33.json: a pull request to a base that is not the default branch carries no closing reference at all
    # (section 6's fallback: the issue Lifecycle serves the default branch only). The reverse read from the issue is
    # no substitute: willCloseTarget is false for a closed-unmerged pull request that keeps its reference, false for
    # every one once the issue is closed, and a keyword link raises no ConnectedEvent; the port reads the pull request.
    ("a_closing_reference_is_read_from_any_pull_request", "The issue a pull request to the default branch closes, and "
     "who opened the pull request, are read from a draft, an open, a merged and a closed-unmerged pull request alike; "
     "one to another base carries no reference", ("P-33",), "trials/P-33.json", None),
    ("who_changed_the_draft_flag_is_read", "The timeline says who last marked a pull request ready or converted it to a "
     "draft", ("P-33",), "trials/P-33.json", None),
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
    ("a_draft_is_not_merged", "A draft pull request cannot be merged, by a person or by the queue",
     ("P-2",), None, None),
    ("a_forks_run_never_counts", "A pull request from a fork runs its own workflow file, on pull_request, never on a "
     "schedule or a dispatch, and I-34 counts none of it", ("P-27",), "trials/P-27.json", None),
    ("a_pass_starts_its_successor", "A pass can dispatch the next with its own job's token", ("P-9",), "trials/P-9.json",
     None),
    ("a_public_event_starts_a_pass", "An event anyone may cause starts the poller's workflow, within a minute or two",
     ("P-20",), "trials/P-20.json", None),
)
