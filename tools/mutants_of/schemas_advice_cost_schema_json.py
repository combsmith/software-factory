"""The mutants of `schemas/advice-cost.schema.json`: tools/mutants.py runs them."""

TARGETS = ("schemas/advice-cost.schema.json",)
MUTANTS = [
    # Decision 0224: the advisory cost a review Run leaves.
    ('an advisory cost may hold more asks than a Run may', 'schemas/advice-cost.schema.json',
     '"minimum": 0,\n      "maximum": 100\n',
     '"minimum": 0,\n      "maximum": 101\n', ('tests.test_adapters.Artifacts.test_a_review_runs_advisory_cost_is_read_as_an_outcome_is_and_never_guessed',)),
    ('an advisory cost may be more than a record holds', 'schemas/advice-cost.schema.json',
     '"minimum": 0,\n      "maximum": 100000\n',
     '"minimum": 0,\n      "maximum": 100001\n', ('tests.test_adapters.Artifacts.test_a_review_runs_advisory_cost_is_read_as_an_outcome_is_and_never_guessed',)),
]
