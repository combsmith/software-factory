"""The mutants of `schemas/run-record.schema.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import BEGAN

TARGETS = ("schemas/run-record.schema.json",)
MUTANTS = [
    # Decision 0193: when a Run began is read from its jobs, under P-64's rule.
    ('a run record may not say it never began', 'schemas/run-record.schema.json',
     '        "string",\n        "null"\n      ],\n      "pattern"', '        "string"\n      ],\n      "pattern"', BEGAN),
]
