"""The mutants of `schemas/advice.schema.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import ADVICE_RESULT

TARGETS = ("schemas/advice.schema.json",)
MUTANTS = [
    # Decision 0224: the second transport, what an advisory Lens's reader is asked through.
    ('an advisory Finding may hold a category', 'schemas/advice.schema.json',
     '"const": "uncategorised"',
     '"type": "string"', ADVICE_RESULT),
    ('an advisory Finding may hold a criterion', 'schemas/advice.schema.json',
     '"criterion": {\n          "type": "null"\n',
     '"criterion": {\n          "type": ["string", "null"]\n', ADVICE_RESULT),
    ('an advisory Finding may lie on any surface', 'schemas/advice.schema.json',
     '"const": "annotation"',
     '"type": "string"', ADVICE_RESULT),
    ('an advisory Finding may be of any kind of source', 'schemas/advice.schema.json',
     '"const": "advisory"',
     '"type": "string"', ADVICE_RESULT),
    ('advice/1 holds a reason the design does not list', 'schemas/advice.schema.json',
     '"rerun"\n',
     '"rerun",\n        "turns_spent"\n', ADVICE_RESULT),
    ('a reader may be asked a third time', 'schemas/advice.schema.json',
     '"maximum": 2',
     '"maximum": 3', ADVICE_RESULT),
    ("an advisory Finding's id may be any text after its Lens", 'schemas/advice.schema.json',
     '"id": {\n          "description": "The Lens\'s name and the first 32 hex digits of a sha256, so that the id fits the 64 characters of the key result/1 adopts from",\n          "type": "string",\n          "pattern": "^[a-z]{1,31}:[0-9a-f]{32}$"\n        },\n        "source"',
     '"id": {\n          "description": "The Lens\'s name and the first 32 hex digits of a sha256, so that the id fits the 64 characters of the key result/1 adopts from",\n          "type": "string",\n          "pattern": "^[a-z]{1,31}:.+$"\n        },\n        "source"', ADVICE_RESULT),
    ("a model named in capitals is refused", 'schemas/advice.schema.json',
     '"answering_model": {\n          "type": [\n            "string",\n            "null"\n          ],\n          "pattern": "^[A-Za-z0-9]',
     '"answering_model": {\n          "type": [\n            "string",\n            "null"\n          ],\n          "pattern": "^[a-z0-9]', ADVICE_RESULT),
    ("an annotation's key may be any text after its Lens", 'schemas/advice.schema.json',
     '"key": {\n              "type": "string",\n              "pattern": "^[a-z]{1,31}:[0-9a-f]{32}$"',
     '"key": {\n              "type": "string",\n              "pattern": "^[a-z]{1,31}:"', ADVICE_RESULT),
    ("an advisory Finding's path may hold a space", 'schemas/advice.schema.json',
     '"pattern": "^[^\\\\s\\\\x00', '"pattern": "^[^\\\\x00', ADVICE_RESULT),
    ("a read's output may count more tokens than a Result holds", 'schemas/advice.schema.json',
     '"maximum": 1000000000\n        },\n        "cost_usd"', '"maximum": 10000000000\n        },\n        "cost_usd"', ADVICE_RESULT),
    ("a read may say it took more than a day", 'schemas/advice.schema.json',
     '"maximum": 86400', '"maximum": 864000', ADVICE_RESULT),
]
