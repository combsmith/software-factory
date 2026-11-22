"""The mutants of `config/apps.json`: tools/mutants.py runs them."""

TARGETS = ("config/apps.json",)
MUTANTS = [
    # P-39 read again on 2026-10-27: the review Role's App is granted what apply reads again and its check run.
    ("the review Role's App is granted no read of the checks", "config/apps.json",
     '            "effect:create_check_run",\n            "read:facts.checks"\n', '            "effect:create_check_run"\n',
     ("tests.test_apply.RoleWrites.test_the_role_app_is_granted_what_apply_reads_again",)),
    ("the review Role's App is granted no check run", "config/apps.json",
     '          "needs": [\n            "effect:create_check_run",\n', '          "needs": [\n',
     ("tests.test_apply.RoleWrites.test_the_role_app_is_granted_checks_to_write_its_check_run",)),
    # Issue 381: the queue App's grant, and each resolution it lands counted as an act.
    ('the queue App does not hold the resolve act', 'config/apps.json',
     '            "effect:dequeue_merge",\n            "effect:resolve_thread"\n',
     '            "effect:dequeue_merge"\n', ('tests.test_tools.Verify.test_every_check_has_a_test_in_which_it_fails',)),
]
