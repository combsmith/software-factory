"""The mutants of `release/decision-points.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import POINT_FIRST

TARGETS = ("release/decision-points.json",)
MUTANTS = [
    # Decision 0194: the Maintainer's continue or stop, and what he was shown before it.
    ('the first decision point is of another Release', 'release/decision-points.json',
     '"release": "factory/v0.1.6"',
     '"release": "factory/v0.1.5"', POINT_FIRST),
    ('the count is of what merged before another moment', 'release/decision-points.json',
     '"before": "2026-11-11T03:57:41Z"',
     '"before": "2026-11-11T03:57:42Z"', POINT_FIRST),
    ('the counts were read before the event', 'release/decision-points.json',
     '"read_on": "2026-11-11"',
     '"read_on": "2026-11-10"', POINT_FIRST),
    ("the count is read against a figure that is not the design's", 'release/decision-points.json',
     '"starting_figure": 40',
     '"starting_figure": 41', POINT_FIRST),
]
