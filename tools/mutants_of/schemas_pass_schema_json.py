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
    # Issue 932: what a record carries for the next pass, read back by it.
    ("a record's doubt may be at any moment", 'schemas/pass.schema.json',
     '"type": "string",\n      "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"\n    },\n    "advisory_unlisted"',
     '"type": "string"\n    },\n    "advisory_unlisted"', ('tests.test_controller.Record.test_a_records_unlisted_yeses_and_doubt_are_held_to_their_form',)),
    ("a record may carry any number unlisted", 'schemas/pass.schema.json',
     '      "maxItems": 1000,\n      "items": {\n        "type": "object",\n        "additionalProperties": false,\n        "required": [\n          "run",\n          "told_at"',
     '      "items": {\n        "type": "object",\n        "additionalProperties": false,\n        "required": [\n          "run",\n          "told_at"', ('tests.test_controller.Record.test_a_records_unlisted_yeses_and_doubt_are_held_to_their_form',)),
    ("an unlisted yes may carry more", 'schemas/pass.schema.json',
     '        "additionalProperties": false,\n        "required": [\n          "run",\n          "told_at"',
     '        "additionalProperties": true,\n        "required": [\n          "run",\n          "told_at"', ('tests.test_controller.Record.test_a_records_unlisted_yeses_and_doubt_are_held_to_their_form',)),
    ("an unlisted yes may be told at no moment", 'schemas/pass.schema.json',
     '        "required": [\n          "run",\n          "told_at"\n        ],',
     '        "required": [\n          "run"\n        ],', ('tests.test_controller.Record.test_a_records_unlisted_yeses_and_doubt_are_held_to_their_form',)),
]
