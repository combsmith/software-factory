"""The mutants of `schemas/run-record.schema.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import BEGAN

TARGETS = ("schemas/run-record.schema.json",)
MUTANTS = [
    # Issue 838: a run record holds a Run that ended on a person's code, as outcome/1 does.
    ("a run record may not say a Run ended person", "schemas/run-record.schema.json",
     '        "superseded",\n        "person",\n', '        "superseded",\n',
     ("tests.test_adapters.Records.test_an_outcome_is_read_once_and_kept_by_its_run_and_attempt",)),
    # Decision 0193: when a Run began is read from its jobs, under P-64's rule.
    ('a run record may not say it never began', 'schemas/run-record.schema.json',
     '        "string",\n        "null"\n      ],\n      "pattern"', '        "string"\n      ],\n      "pattern"', BEGAN),
    # Decision 0224: what a review Run's record says of its advisory reads.
    ("a run record may say it is a re-run's first attempt", 'schemas/run-record.schema.json',
     '      "minimum": 2,\n      "maximum": 100\n',
     '      "minimum": 1,\n      "maximum": 100\n', ('tests.test_controller.Advisory.test_a_review_run_is_told_yes_only_under_a_ceiling_and_a_worst_case_that_are_configured',)),
    ('a run record may count more asks than a Run may send', 'schemas/run-record.schema.json',
     '      "type": "integer",\n      "minimum": 0,\n      "maximum": 100\n    },\n    "advisory_cost_usd"',
     '      "type": "integer",\n      "minimum": 0\n    },\n    "advisory_cost_usd"', ('tests.test_controller.Advisory.test_a_review_run_is_told_yes_only_under_a_ceiling_and_a_worst_case_that_are_configured',)),
    ("a run record's advisory cost has no bound", 'schemas/run-record.schema.json',
     '      "minimum": 0,\n      "maximum": 100000\n    },\n    "advisory_attempt"',
     '      "minimum": 0\n    },\n    "advisory_attempt"', ('tests.test_controller.Advisory.test_a_review_run_is_told_yes_only_under_a_ceiling_and_a_worst_case_that_are_configured',)),
]
