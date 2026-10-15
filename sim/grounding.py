"""What the fake GitHub in `world.py` assumes about the real one, and what grounds each assumption.

Each rule the fake applies is marked where it is applied, by a comment `# GitHub: <code>`, and is
listed here once: its code, the rule in words, the trials of the design's section 6 that ask it
(empty when none does), and the fixture under `trials/` that grounds it (None until one does).
A rule with no fixture is unverified, and `make verify` prints it (design, section 4.5). A rule no
trial asks can be grounded only once a trial for it is added to section 6.
`tools/check_trials.py` holds this list and the marks to each other, and each fixture named here
to its schema. It reads RULES as a literal, so that it can judge a copy of the repo: keep it one.
"""

RULES = (
    ("a_push_is_new_content", "A push gives the pull request new content", ("P-29",), None),
    ("the_pusher_is_the_last_pusher", "The account that pushed the head is read as its last pusher", ("P-28",), None),
    ("an_app_pushes_to_the_head", "An App can push to the head of a pull request", ("P-7",), None),
    ("an_approval_survives_a_push", "A push leaves an earlier approval in place", ("P-7", "P-29"), None),
    ("a_request_for_changes_survives_a_push", "A push leaves a request for changes standing", (), None),
    ("an_app_can_dismiss_a_review", "An App with pull_requests: write can dismiss a person's review, and the "
     "timeline says which App and what the review was before (previousReviewState)", (), None),
    ("a_push_restarts_the_checks", "A push sets every required check pending again", (), None),
    ("a_check_reports_on_its_own", "A pending required check reports success or failure with no one asking", (), None),
    ("a_check_can_time_out_or_give_no_verdict", "A required check can conclude timed_out, neutral, skipped, cancelled "
     "or stale, and keeps that conclusion until the content changes or a person runs it again", (), None),
    ("a_push_leaves_the_queue", "A push takes the pull request out of the merge queue", (), None),
    ("an_app_enters_the_queue", "An App can put an approved pull request in the merge queue", ("P-2",), None),
    ("the_queue_merges", "A pull request in the merge queue merges, unless a push takes it out first", (), None),
    ("a_pass_comes_before_the_merge", "The merge queue merges a pull request only after a pass has read it whole "
     "and current, and found the same facts GitHub holds at the merge", ("P-2",), None),
    ("an_app_leaves_the_queue", "An App can take a pull request out of the merge queue", ("P-2",), None),
    ("a_writer_can_dismiss_an_approval", "A person with write access can dismiss the machine user's approval, and the "
     "timeline says who and what the review was before", (), None),
    ("the_merge_group_is_not_checked", "The merge queue merges without running the checks on the merge group", (), None),
    ("the_machine_users_approval_counts", "The machine user's approval counts when an App pushed last", ("P-7",), None),
    ("an_approval_can_fail_to_land", "The machine user's approval can fail to land, by a fault of the item or of "
     "the environment, and its Run then concludes failure", ("P-7",), None),
    ("the_queue_can_eject", "The merge queue can take a pull request out without merging it, and its approval stays",
     (), None),
    ("the_timeline_shows_each_act", "Each approval, enqueue, dequeue and label a Factory identity makes is on the "
     "timeline, with its actor, so the acts since a person with write access acted can be counted", ("P-8",), None),
    ("a_lens_review_opens_a_thread", "A Lens's review can open a review thread on the pull request", (), None),
    ("an_app_resolves_a_lens_thread", "The reviewer's App can resolve a thread a Lens opened", ("P-5",), None),
    ("a_run_waits_its_turn", "One Run on an item is in progress, and any number wait queued behind it", (), None),
    ("a_queued_run_is_listed", "A Run is in the list of run records from when it is queued, before its job starts",
     ("P-17",), None),
    ("a_new_run_is_listed_late", "The newest Run can be missing from the list of run records for one pass", ("P-22",), None),
    ("a_run_list_stops_short", "The list of run records can stop short, with the oldest Runs missing", (), None),
    ("a_killed_job_times_out", "A job killed part way concludes timed_out", ("P-18",), None),
    ("a_superseded_run_fails", "A Run whose apply refuses, or that never starts, concludes failure", ("P-17",), None),
    ("a_short_diff_says_so", "A diff read short says so, and is not mistaken for the whole", ("P-29",), None),
    ("a_short_list_says_so", "A list of reviews, threads, checks or timeline events read short says so", (), None),
    ("a_read_can_be_stale", "A read can return what an earlier read did", (), None),
    ("a_tick_can_be_lost", "A scheduled tick can fail to arrive", ("P-8",), None),
    ("anyone_can_comment", "On a public repo anyone can submit a review that only comments", (), None),
)
