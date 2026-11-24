"""The mutants of `schemas/pass.schema.json`: tools/mutants.py runs them."""

TARGETS = ("schemas/pass.schema.json",)
MUTANTS = [
    # Issues 328 and 329: what reconciliation left whole, or alarmed on, that it should not have.
    # Issue 887: the follow-ons of #885.
    ("a hand's carried record may name no thread", 'schemas/pass.schema.json',
     '            "additionalProperties": false,\n            "required": ["key", "at"],\n            "properties": {\n              "key": {"type": "string", "pattern": "^[A-Za-z0-9_=:-]{1,100}$"}',
     '            "additionalProperties": false,\n            "required": ["at"],\n            "properties": {\n              "key": {"type": "string", "pattern": "^[A-Za-z0-9_=:-]{1,100}$"}', ('tests.test_reconcile.Hand.test_a_hands_resolution_once_matched_is_carried_while_it_is_seen',)),
    ("a hand's carried thread may be of any length", 'schemas/pass.schema.json',
     '"key": {"type": "string", "pattern": "^[A-Za-z0-9_=:-]{1,100}$"},\n              "at"',
     '"key": {"type": "string", "pattern": "^[A-Za-z0-9_=:-]+$"},\n              "at"', ('tests.test_reconcile.Hand.test_a_hands_resolution_once_matched_is_carried_while_it_is_seen',)),
    ("a hand's carried thread may be any word", 'schemas/pass.schema.json',
     '"key": {"type": "string", "pattern": "^[A-Za-z0-9_=:-]{1,100}$"},\n              "at"',
     '"key": {"type": "string"},\n              "at"', ('tests.test_reconcile.Hand.test_a_hands_resolution_once_matched_is_carried_while_it_is_seen',)),
    ("a hand's carried thread may carry more", 'schemas/pass.schema.json',
     '            "additionalProperties": false,\n            "required": ["key", "at"],',
     '            "additionalProperties": true,\n            "required": ["key", "at"],', ('tests.test_reconcile.Hand.test_a_hands_resolution_once_matched_is_carried_while_it_is_seen',)),
]
