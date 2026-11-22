"""The mutants of `examples/invalid/decision-points.decided-by-another.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import POINT_EACH

TARGETS = ("examples/invalid/decision-points.decided-by-another.json",)
MUTANTS = [
    # Decision 0194: the Maintainer's continue or stop, and what he was shown before it.
    ("the counter-example of another's decision is the Maintainer's own", 'examples/invalid/decision-points.decided-by-another.json',
     '"by": "donpetry-bot"',
     '"by": "don-petry"', POINT_EACH),
]
