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
]
