"""The mutants of `schemas/controller.schema.json`: tools/mutants.py runs them."""

TARGETS = ("schemas/controller.schema.json",)
MUTANTS = [
    # Issues 328 and 329: what reconciliation left whole, or alarmed on, that it should not have.
    # Issue 887: the follow-ons of #885.
    ('a Role named hand with no account yet is allowed', 'schemas/controller.schema.json',
     '              "enum": []',
     '              "enum": [null]', ('tests.test_reconcile.Hand.test_a_hands_resolution_of_a_roles_thread_is_matched_to_the_act_the_last_pass_named',)),
    ('a Role may be named hand', 'schemas/controller.schema.json',
     '              "enum": []',
     '              "type": ["object", "null"]', ('tests.test_reconcile.Hand.test_a_hands_resolution_of_a_roles_thread_is_matched_to_the_act_the_last_pass_named',)),
]
