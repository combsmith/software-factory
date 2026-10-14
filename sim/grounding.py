"""What the fake GitHub in `world.py` assumes about the real one, and what grounds each assumption.

Each rule the fake applies is marked where it is applied, by a comment `# GitHub: <code>`, and is
listed here once: its code, the rule in words, the trial of the design's section 6 that asks it
(None when no trial does), and the fixture under `trials/` that grounds it (None until one does).
A rule with no fixture is unverified, and `make verify` prints it (design, section 4.5).
`tools/check_trials.py` holds this list and the marks to each other, and each fixture named here
to its schema. It reads RULES as a literal, so that it can judge a copy of the repo: keep it one.
"""

RULES = (
    ("a_push_is_new_content", "A push gives the pull request new content, and a moving base does not", "P-29", None),
    ("the_pusher_is_the_last_pusher", "The account that pushed the head is read as its last pusher", "P-28", None),
    ("a_push_restarts_the_checks", "A push sets every required check pending, and each reports on the new head", None, None),
    ("a_push_leaves_the_queue", "A push takes the pull request out of the merge queue", None, None),
    ("an_app_enters_the_queue", "An App can put an approved pull request in the merge queue", "P-2", None),
    ("the_queue_merges", "A pull request in the merge queue merges, unless a push takes it out first", None, None),
    ("the_machine_users_approval_counts", "The machine user's approval counts when an App pushed last", "P-7", None),
    ("an_app_resolves_a_lens_thread", "The reviewer's App can resolve a thread a Lens opened", "P-5", None),
    ("a_queued_run_is_listed", "A Run is in the list of run records from when it is queued, before its job starts", "P-17", None),
    ("a_new_run_is_listed_late", "The newest Run can be missing from the list of run records for one pass", "P-22", None),
    ("a_short_read_says_so", "A list read short says so, and is not mistaken for the whole", "P-29", None),
    ("a_read_can_be_stale", "A read can return what an earlier read did", None, None),
    ("a_tick_can_be_lost", "A scheduled tick can fail to arrive", "P-8", None),
)
