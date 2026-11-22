"""The mutants of `schemas/decision-points.schema.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import POINT_EACH

TARGETS = ("schemas/decision-points.schema.json",)
MUTANTS = [
    # Decision 0194: the Maintainer's continue or stop, and what he was shown before it.
    ("the schema refuses the Maintainer's stop", 'schemas/decision-points.schema.json',
     '      "continue",\n      "stop",\n',
     '      "continue",\n', POINT_EACH),
    ("the schema refuses the Maintainer's continue", 'schemas/decision-points.schema.json',
     '      "continue",\n      "stop",\n',
     '      "stop",\n', POINT_EACH),
    ('the schema takes a decision that is neither continue nor stop', 'schemas/decision-points.schema.json',
     '     "enum": [\n      "continue",\n      "stop",\n      null\n     ]',
     '     "type": [\n      "string",\n      "null"\n     ]', POINT_EACH),
]
