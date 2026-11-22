"""The mutants of `schemas/hooks.schema.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import OPENER_TESTS

TARGETS = ("schemas/hooks.schema.json",)
MUTANTS = [
    # Issue 409: a pull request is opened from this repo by an account the configuration lists (decision 0102).
    ("the list is not required", "schemas/hooks.schema.json", '    "maintainer",\n    "openers",\n', '    "maintainer",\n', OPENER_TESTS),
    ("the list may be empty", "schemas/hooks.schema.json", '    "openers": {\n      "type": "array",\n      "minItems": 1,\n', '    "openers": {\n      "type": "array",\n', OPENER_TESTS),
    ("an opener needs no reason", "schemas/hooks.schema.json", '          "id",\n          "is"\n', '          "id"\n', OPENER_TESTS),
    ("an opener needs no id", "schemas/hooks.schema.json", '          "login",\n          "id",\n          "is"\n', '          "login",\n          "is"\n', OPENER_TESTS),
    ("an opener needs no login", "schemas/hooks.schema.json", '          "login",\n          "id",\n          "is"\n', '          "id",\n          "is"\n', OPENER_TESTS),
    ("an opener may be listed twice", "schemas/hooks.schema.json", '      "uniqueItems": true,\n      "items": {\n        "type": "object",\n        "additionalProperties": false,\n        "required": [\n          "login",\n          "id"', '      "items": {\n        "type": "object",\n        "additionalProperties": false,\n        "required": [\n          "login",\n          "id"', OPENER_TESTS),
    ("an App's login is no opener's", "schemas/hooks.schema.json", '(?:\\\\[bot\\\\])?$"', '$"', OPENER_TESTS),
    ("an opener's login may be any text", "schemas/hooks.schema.json", '            "pattern": "^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\\\\[bot\\\\])?$"\n', '            "minLength": 1\n', OPENER_TESTS),
    ("an opener's id may be text", "schemas/hooks.schema.json", '            "type": "integer",\n            "minimum": 1\n          },\n          "is"', '            "minimum": 1\n          },\n          "is"', OPENER_TESTS),
    ("an opener's id may be no account's", "schemas/hooks.schema.json", '            "type": "integer",\n            "minimum": 1\n          },\n          "is"', '            "type": "integer"\n          },\n          "is"', OPENER_TESTS),
]
