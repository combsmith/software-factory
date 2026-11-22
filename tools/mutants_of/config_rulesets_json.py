"""The mutants of `config/rulesets.json`: tools/mutants.py runs them."""

TARGETS = ("config/rulesets.json",)
MUTANTS = [
    # The record of `main` after issue 198's switch (decision 0191): each field back, and the four together, which
    # `tools/check_rulesets.py` lets through as a `main` that counts no approval.
    ("the record of main counts no approval", 'config/rulesets.json',
     '"required_approving_review_count": 1', '"required_approving_review_count": 0', ('tests.test_tools.Rulesets.test_main_counts_the_machine_users_approval_as_the_switch_left_it',)),
    ("the record of main asks for no code owner's approval", 'config/rulesets.json',
     '"require_code_owner_review": true', '"require_code_owner_review": false', ('tests.test_tools.Rulesets.test_main_counts_the_machine_users_approval_as_the_switch_left_it',)),
    ("the record of main counts an approval of an earlier push", 'config/rulesets.json',
     '"require_last_push_approval": true', '"require_last_push_approval": false', ('tests.test_tools.Rulesets.test_main_counts_the_machine_users_approval_as_the_switch_left_it',)),
    ("the record of main leaves a stale approval standing", 'config/rulesets.json',
     '"dismiss_stale_reviews_on_push": true', '"dismiss_stale_reviews_on_push": false', ('tests.test_tools.Rulesets.test_main_counts_the_machine_users_approval_as_the_switch_left_it',)),
    ("the record of main is of the day before the switch", 'config/rulesets.json',
     '"required_approving_review_count": 1,\n          "dismiss_stale_reviews_on_push": true,\n          "required_reviewers": [],\n          "require_code_owner_review": true,\n          "dismissal_restriction": {\n            "enabled": false,\n            "allowed_actors": []\n          },\n          "require_last_push_approval": true,',
     '"required_approving_review_count": 0,\n          "dismiss_stale_reviews_on_push": false,\n          "required_reviewers": [],\n          "require_code_owner_review": false,\n          "dismissal_restriction": {\n            "enabled": false,\n            "allowed_actors": []\n          },\n          "require_last_push_approval": false,',
     ('tests.test_tools.Rulesets.test_main_counts_the_machine_users_approval_as_the_switch_left_it',)),
    ("the record of main was read before the switch", 'config/rulesets.json',
     '"read_on": "2026-11-11"', '"read_on": "2026-11-09"', ('tests.test_tools.Rulesets.test_main_counts_the_machine_users_approval_as_the_switch_left_it',)),
]
