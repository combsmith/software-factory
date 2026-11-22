"""The mutants of `schemas/context-eval.schema.json`: tools/mutants.py runs them."""

TARGETS = ("schemas/context-eval.schema.json",)
MUTANTS = [
    # The apply job and the identity port (issue 194, PR 2).
    ('a schema pattern may backtrack', 'schemas/context-eval.schema.json',
     '"pattern": "^[0-9]+(\\\\.[0-9]+)+$"', '"pattern": "^([0-9]+\\\\.?)+$"',
     ('tests.test_tools.Validator.test_no_schema_pattern_backtracks_on_a_long_value',)),
]
