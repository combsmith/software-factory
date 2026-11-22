"""The mutants of `schemas/eval-set.schema.json`: tools/mutants.py runs them."""

TARGETS = ("schemas/eval-set.schema.json",)
MUTANTS = [
    # Issue 613, the preflight: each dispatch of a gate set asks a few development cases first, and a broken pipeline stops it.
    ('a preflight of two cases is read', 'schemas/eval-set.schema.json',
     '"minItems": 3,',
     '"minItems": 2,', ('tests.test_evals.EvalJob.test_a_gate_sets_preflight_is_of_the_development_set_and_no_gate_sets_case',)),
    ('a preflight of six cases is read', 'schemas/eval-set.schema.json',
     '"maxItems": 5,',
     '"maxItems": 6,', ('tests.test_evals.EvalJob.test_a_gate_sets_preflight_is_of_the_development_set_and_no_gate_sets_case',)),
]
