"""The mutants of `examples/invalid/decision-points.no-count.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import POINT_EACH

TARGETS = ("examples/invalid/decision-points.no-count.json",)
MUTANTS = [
    # Decision 0194: the Maintainer's continue or stop, and what he was shown before it.
    ('the counter-example with no count has one', 'examples/invalid/decision-points.no-count.json',
     '    "starting_figure": 40,\n',
     '    "starting_figure": 40,\n    "merged": 387,\n', POINT_EACH),
]
