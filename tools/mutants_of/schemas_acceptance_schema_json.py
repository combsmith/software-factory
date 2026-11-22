"""The mutants of `schemas/acceptance.schema.json`: tools/mutants.py runs them."""

TARGETS = ("schemas/acceptance.schema.json",)
MUTANTS = [
    # Issue 740: an acceptance contract's protected paths are in the hooks' syntax.
    ("a contract's protected path may be in any syntax", 'schemas/acceptance.schema.json',
     '"$ref": "hooks.schema.json#/$defs/path"', '"type": "string"', ('tests.test_tools.Acceptance.test_an_acceptance_contracts_protected_paths_are_in_the_hooks_syntax_and_read_alike',)),
    ("a contract may protect no path", 'schemas/acceptance.schema.json',
     '      "type": "array",\n      "minItems": 1,\n      "items": {\n        "$ref"', '      "type": "array",\n      "items": {\n        "$ref"', ('tests.test_tools.Acceptance.test_an_acceptance_contracts_protected_paths_are_in_the_hooks_syntax_and_read_alike',)),
    ("a contract's protected paths may be one string", 'schemas/acceptance.schema.json',
     '      "type": "array",\n      "minItems": 1,\n      "items": {\n        "$ref"', '      "minItems": 1,\n      "items": {\n        "$ref"', ('tests.test_tools.Acceptance.test_an_acceptance_contracts_protected_paths_are_in_the_hooks_syntax_and_read_alike',)),
    # The apply job and the identity port (issue 194, PR 2).
    ('a schema pattern may backtrack behind its literal text', 'schemas/acceptance.schema.json',
     '"^AC-[0-9]+$"', '"^AC-([0-9]+)+$"',
     ('tests.test_tools.Validator.test_no_schema_pattern_backtracks_on_a_long_value',)),
]
