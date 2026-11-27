"""Whether the day's ceiling admits one more advisory read: the yes or no a pass hands a review Run beside its Decision
(decision 0224, Spend). It is a function of the run records, `now` and the configuration. It reads no clock, no file
and nothing from GitHub, and it asks the Kernel nothing: an advisory Lens changes no Decision.

The day is the UTC date of the pass's `now`. Every record of a review Run counts, two records of one Run among them,
unless it finished and started on another day; a record whose start or Intent cannot be read is counted, since it cannot
be shown to be another day's or another Intent's. A finished Run is its record's day, `started_at`, which the records keep each attempt by: one run
again on a later day is counted there. A Run still in flight counts on today's sum whatever day it started, so that
what is spent across midnight is carried and no day's reads begin from nought while yesterday's are still running
(the Factory Builder, 2026-11-19).

- A finished Run whose advice was read and that asked no reader, and gives no cost, counts nothing.
- A finished Run that asked, and gives a cost above nought within what a record may hold, counts that cost.
- Every other counts the worst case the configuration names, `advisory_worst_case_usd`: one still running, whatever
  it says; one whose advice was not read; one that asked and gives no cost, or nought, which no read costs; and one
  whose fields do not agree. A read is not refused because another is in flight (the Factory Builder, 2026-11-18:
  quality first), and an unknown cost is never nought.

The answer is yes only where the configuration holds a reader, a ceiling and a worst case, each a figure its schema
would hold, `now` is a time in the one form, the run records were read whole, and the day's sum and this Run's own
worst case together do not pass the ceiling. Neither figure has a default: with either missing, no reader is asked.
Whatever it is handed, it answers, and what it cannot read it answers no to. A caller that admits more than one review
in a pass hands each the ones before it, as records still running, so that each counts the others' worst case.
"""
from __future__ import annotations

import datetime
import re

REVIEWING = "review-change"
CEILING, WORST = "advisory_ceiling_usd_per_day", "advisory_worst_case_usd"
COST, ASKS = "advisory_cost_usd", "advisory_asks"
# The bounds the schemas hold each figure to: harness/1's two figures, and run-record/1's cost and count.
LEAST, MOST, DEAREST, ASKED_MOST = 0.01, 10000, 100000, 100
TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
DAY = len("2026-01-01")


def _number(value, least, most) -> bool:
    """A number, no truth value, from `least` to `most`: so no NaN, which is within no bounds, and none without end."""
    return type(value) in (int, float) and least <= value <= most


def _placed(value) -> bool:
    """A time in the one form, of a day and a clock that exist: `2026-02-30T12:00:00Z` names no day."""
    if not isinstance(value, str) or TIME.fullmatch(value) is None:
        return False
    try:
        datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _another(intent) -> bool:
    """Whether a record is shown to be of another Intent: one whose Intent cannot be read may be a review's, and counts."""
    return isinstance(intent, str) and intent != REVIEWING


def counted(record, worst: float) -> float:
    """What one review Run of the day counts against the ceiling."""
    if not isinstance(record, dict) or record.get("status") != "completed":
        return worst                    # still running, or no record at all: not known, so the worst case
    asks, cost = record.get(ASKS), record.get(COST)
    if type(asks) is not int or not 0 <= asks <= ASKED_MOST:
        return worst                    # its advice not read
    if asks == 0:
        return 0.0 if cost is None or (_number(cost, 0, 0)) else worst
    # A cost is written to a millionth of a dollar: one that rounds to nought is none, and no read costs nothing.
    return float(cost) if _number(cost, 0, DEAREST) and round(cost, 6) > 0 else worst


def spent(records: list, now: str, worst: float) -> float:
    """The day's advisory spend as the run records give it: the sum over the review Runs not shown to be another day's."""
    day, total = now[:DAY], 0.0
    for record in records:
        started = record.get("started_at") if isinstance(record, dict) else None
        placed = _placed(started)
        flying = isinstance(record, dict) and record.get("status") != "completed"
        if isinstance(record, dict) and (_another(record.get("intent"))
                                         or (placed and started[:DAY] != day and not flying)):
            continue
        total += counted(record, worst)
    return total


def admits(records, whole, now, harness) -> bool:
    """Whether one more review Run may ask its readers today."""
    if not isinstance(harness, dict) or not isinstance(records, list) or whole is not True \
            or not _placed(now):
        return False
    ceiling, worst, readers = harness.get(CEILING), harness.get(WORST), harness.get("readers")
    if not _number(ceiling, LEAST, MOST) or not _number(worst, LEAST, MOST) or not isinstance(readers, dict) or not readers:
        return False
    # In millionths of a dollar, as a cost is written: the sum to the nearest, so that it is not refused for the error
    # of adding floats; this Run's own worst case rounded up and the ceiling down, past a float's noise alone, so that
    # a worst case above the ceiling by less than a millionth is still above it.
    return round(spent(records, now, worst) * 1000000) + -(-round(worst * 1000000, 3) // 1) \
        <= round(ceiling * 1000000, 3) // 1
