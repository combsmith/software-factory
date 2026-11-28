"""Whether the day's ceiling admits one more advisory read: the yes or no a pass hands a review Run beside its Decision
(decision 0224, Spend). It is a function of the run records, `now` and the configuration. It reads no clock, no file
and nothing from GitHub, and it asks the Kernel nothing: an advisory Lens changes no Decision.

The day is the UTC date of the pass's `now`. Every record of a review Run counts, two records of one Run among them,
unless it is shown to be another day's; a record whose start or Intent cannot be read is counted, since it cannot be
shown to be another day's or another Intent's. A finished Run counts on every day it touched, from its `started_at`,
which the records keep each attempt by, to its `ended_at`, or to today where it gives none that can be read: one
that ran across midnight counts on both days (the Solution Architect, 2026-11-27). A Run still in flight counts on
today's sum whatever day it started, so that no day's reads begin from nought while yesterday's are still running (the
Factory Builder, 2026-11-19). A record is of a Run's latest attempt, and `advisory_attempt` names it where it is a
re-run's: each attempt before it counts the worst case, since its cost is not read, and one whose attempt cannot be
read counts as many as a Run may have (the Solution Architect, 2026-11-27: a re-run can only raise the day's sum).

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
in a pass hands each the ones before it, as records still running, so that each counts the others' worst case; it
likewise hands each review an earlier pass told yes whose Run no record lists yet, and each Run listed with no run-name
(issue 932).
"""
from __future__ import annotations

import datetime
import re

REVIEWING = "review-change"
CEILING, WORST = "advisory_ceiling_usd_per_day", "advisory_worst_case_usd"
COST, ASKS, ATTEMPT = "advisory_cost_usd", "advisory_asks", "advisory_attempt"
# The bounds the schemas hold each figure to: harness/1's two figures, and run-record/1's cost, count and attempt.
LEAST, MOST, DEAREST, ASKED_MOST, ATTEMPTS = 0.01, 10000, 100000, 100, 100
INTENT = re.compile(r"[a-z][a-z-]*[a-z]")      # an Intent's name as run-record/1 holds it
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
    """Whether a record is shown to be of another Intent: one named as an Intent is, and not a review's. One whose Intent
    cannot be read, an empty or ill-formed name among them, may be a review's, and counts."""
    return isinstance(intent, str) and INTENT.fullmatch(intent) is not None and intent != REVIEWING


def _earlier(record) -> int:
    """How many attempts before the record's own it counts: none for a first, which names no attempt and no re-runner,
    and as many as a Run may have for one whose attempt cannot be read."""
    if ATTEMPT not in record:
        # A re-run's record names who re-ran it: one that does and names no attempt cannot show it is a first.
        return ATTEMPTS - 1 if "rerun_by_dispatcher" in record else 0
    attempt = record[ATTEMPT]
    return attempt - 1 if type(attempt) is int and 2 <= attempt <= ATTEMPTS else ATTEMPTS - 1


def counted(record, worst: float) -> float:
    """What one review Run of the day counts against the ceiling: its latest attempt, and the worst case for each
    attempt before it."""
    if not isinstance(record, dict):
        return worst                    # no record at all: not known, so the worst case
    return _own(record, worst) + _earlier(record) * worst


def _own(record: dict, worst: float) -> float:
    """What the record's own attempt counts."""
    if record.get("status") != "completed":
        return worst                    # still running: not known, so the worst case
    asks, cost = record.get(ASKS), record.get(COST)
    if type(asks) is not int or not 0 <= asks <= ASKED_MOST:
        return worst                    # its advice not read
    if asks == 0:
        return 0.0 if cost is None or (_number(cost, 0, 0)) else worst
    # A cost is written to a millionth of a dollar: one that rounds to nought is none, and no read costs nothing.
    if type(cost) in (int, float) and cost > DEAREST:
        return float(DEAREST)          # more than a record may hold: at least the most it may, never the worst case alone
    return float(cost) if _number(cost, 0, DEAREST) and round(cost, 6) > 0 else worst


def _elsewhen(record: dict, day: str) -> bool:
    """Whether a finished Run is shown to be another day's: the day and its start can be read, and the day is neither
    its start's, its end's nor one between them. One whose end cannot be read, or is before its start, may have ended on
    any day since its start."""
    started, ended = record.get("started_at"), record.get("ended_at")
    if day is None or not _placed(started):
        return False
    last = ended[:DAY] if _placed(ended) and ended >= started else day
    return not started[:DAY] <= day <= last


def spent(records: list, now: str, worst: float) -> float:
    """The day's advisory spend as the run records give it: the sum over the review Runs not shown to be another day's."""
    day, total = now[:DAY] if _placed(now) else None, 0.0    # a `now` that names no day shows no Run another day's
    for record in records:
        if isinstance(record, dict) and (_another(record.get("intent"))
                                         or (record.get("status") == "completed" and _elsewhen(record, day))):
            continue
        total += counted(record, worst)
    return total


def _exact(figure) -> tuple:
    """A figure as written, as whole units of a tenth to the power of its places: a float's shortest form, which is the
    text JSON gave it. A figure from a hundredth to ten thousand, which repr writes with no power of ten."""
    whole, _, part = repr(figure).partition(".")
    return int(whole + part), len(part)


def admits(records, whole, now, harness) -> bool:
    """Whether one more review Run may ask its readers today."""
    if not isinstance(harness, dict) or not isinstance(records, list) or whole is not True \
            or not _placed(now):
        return False
    ceiling, worst, readers = harness.get(CEILING), harness.get(WORST), harness.get("readers")
    if not _number(ceiling, LEAST, MOST) or not _number(worst, LEAST, MOST) or not isinstance(readers, dict) or not readers \
            or not all(isinstance(block, dict) for block in readers.values()):
        return False
    # The day's sum to the nearest millionth of a dollar, as a cost is written, so that it is not refused for the error
    # of adding floats; this Run's own worst case and the ceiling exactly as written, so that a worst case above the
    # ceiling by any amount is above it, and one equal to it is not.
    figures = [(round(spent(records, now, worst) * 1000000), 6), _exact(worst), _exact(ceiling)]
    places = max(place for _, place in figures)
    total, own, most = (digits * 10 ** (places - place) for digits, place in figures)
    return total + own <= most
