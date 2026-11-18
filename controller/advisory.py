"""Whether the day's ceiling admits one more advisory read: the yes or no a pass hands a review Run beside its Decision
(decision 0224, Spend). It is a function of the run records, `now` and the configuration. It reads no clock, no file
and nothing from GitHub, and it asks the Kernel nothing: an advisory Lens changes no Decision.

The day is the UTC date of the pass's `now`. Each review Run that started on it counts once:

- one whose advice was read and that asked no reader counts nothing;
- one whose advice was read and gives its cost counts that cost;
- one that asked and gives no cost, one still running, and one whose advice could not be read each count the worst
  case the configuration names, `advisory_worst_case_usd`. A read is not refused because another is in flight
  (the Factory Builder, 2026-11-18: quality first), and an unknown cost is never nought.

The answer is yes only where the configuration holds a reader, a ceiling and a worst case, the run records were read
whole, and the day's sum and this Run's own worst case together do not pass the ceiling. Neither figure has a default:
with either missing, no reader is asked.
"""
from __future__ import annotations

REVIEWING = "review-change"
CEILING, WORST = "advisory_ceiling_usd_per_day", "advisory_worst_case_usd"
COST, ASKS = "advisory_cost_usd", "advisory_asks"
ENDLESS = float("inf")


def _finite(value) -> bool:
    return value == value and abs(value) != ENDLESS     # no NaN, which equals nothing, and no number without end


def _dollars(value):
    """A figure in dollars that is one: a number above nought, and no truth value."""
    whole = type(value) in (int, float) and _finite(value) and value > 0
    return value if whole else None


def counted(record: dict, worst: float) -> float:
    """What one review Run of the day counts against the ceiling."""
    asks, cost = record.get(ASKS), record.get(COST)
    if type(asks) is not int or asks < 0:
        return worst                    # still running, or its advice not read: not known, so the worst case
    if asks == 0:
        return 0.0
    known = type(cost) in (int, float) and _finite(cost) and cost >= 0
    return float(cost) if known else worst


def spent(records: list, now: str, worst: float) -> float:
    """The day's advisory spend as the run records give it: the sum over the review Runs that started on `now`'s day."""
    day = now[:len("2026-01-01")]
    mine = [r for r in records if r.get("intent") == REVIEWING and isinstance(r.get("started_at"), str)
            and r["started_at"][:len(day)] == day]
    return sum(counted(r, worst) for r in mine)


def admits(records: list, whole: bool, now: str, harness: dict) -> bool:
    """Whether one more review Run may ask its readers today."""
    ceiling, worst = _dollars(harness.get(CEILING)), _dollars(harness.get(WORST))
    if ceiling is None or worst is None or not harness.get("readers") or whole is not True:
        return False
    return spent(records, now, worst) + worst <= ceiling
