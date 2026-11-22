"""The mutants of `schemas/machine-user.schema.json`: tools/mutants.py runs them."""

TARGETS = ("schemas/machine-user.schema.json",)
MUTANTS = [
    # Issue 89: the machine user's role, held to the configuration and compared with GitHub by hand.
    ('the org role may be maintain', 'schemas/machine-user.schema.json',
     '"const": "all_repo_write"', '"type": "string"', ('tests.test_tools.Apps.test_what_the_machine_user_may_never_hold_has_a_counter_example',)),
    ('the role on a repo may be maintain', 'schemas/machine-user.schema.json',
     '"const": "write"', '"type": "string"', ('tests.test_tools.Apps.test_what_the_machine_user_may_never_hold_has_a_counter_example',)),
    ('the team may be at maintain on a repo', 'schemas/machine-user.schema.json',
     '"const": "push"', '"type": "string"', ('tests.test_tools.Apps.test_what_the_machine_user_may_never_hold_has_a_counter_example',)),
    ('the team may have grants of its own', 'schemas/machine-user.schema.json',
     '"const": 0', '"type": "integer"', ('tests.test_tools.Apps.test_what_the_machine_user_may_never_hold_has_a_counter_example',)),
    ('any number of repos may be left out', 'schemas/machine-user.schema.json',
     '"const": 2', '"type": "integer"', ('tests.test_tools.Apps.test_what_the_machine_user_may_never_hold_has_a_counter_example',)),
    ('the teams may be any', 'schemas/machine-user.schema.json',
     '"const": [\n        "org-leads",\n        "organization-members"\n      ]', '"type": "array"', ('tests.test_tools.Apps.test_what_the_machine_user_may_never_hold_has_a_counter_example',)),
]
