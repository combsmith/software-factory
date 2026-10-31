"""Each stored credential's age, and the one alert near its limit (L-37, issue 305; #195's ruling 8 as drafted).

`due(table, now)` is pure, as the pass is. It is given `config/credential-ages.json` as the Release holds it, or None
where it could not be read, and the pass's `now`. It returns the names of the secrets due, sorted, and whether the
alert `credential_due` is raised. A credential's limit is the earlier of its `expires_on`, where it `expires`, and its
`rotated_on` plus `rotate_every_days`, where it has a period, at the start of that day in UTC; it is due once its limit
is `due_within_days` away or less. One with neither has no limit and never falls due by age: the Maintainer's choice is
expiry alone, no rotation periods (2026-10-29). A row that cannot be read is due, named if its name can be read: one
that expires and whose expiry is not given is such a row, and so is one whose period cannot be counted from its last
rotation. A date is read only where it can bring the credential due, so a last rotation without a period is a record
alone. A table that cannot be read is due whole. A coordinate is no credential and has no age, so it is never due, but
one given a date is read as a credential mislabelled.
"""
from __future__ import annotations

import datetime
import re

from controller.shared import moment

ALERT = "credential_due"
COORDINATE = "coordinate"
KINDS = ("write", "model", "read")
NAME = re.compile(r"[A-Z][A-Z0-9_]*")
DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
DATES = ("rotated_on", "expires_on", "rotate_every_days")
NEVER = "never"      # the limit of a credential with no expiry and no period: none, however far off


def _day(value):
    """The start of the day `value` names, in UTC, or None if it names none."""
    if not isinstance(value, str) or not DAY.fullmatch(value):
        return None
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def _count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def limit(row: dict, at: datetime.datetime):
    """The credential's limit, `NEVER` where it has neither an expiry nor a period, or None if a date it is read from
    cannot be read: an expiry it has and is not given, or that names no day; an expiry it is said not to have, or no
    word on whether it has one; a period that is not a whole number of days, or with no last rotation, or one after
    `at`. `rotated_on` is read only for a period: without one it is the record of a rotation, and brings nothing due."""
    rotated, ends_on, every = (row.get(name) for name in DATES)
    if row.get("expires") is True:
        expiry = _day(ends_on)
        if expiry is None:
            return None
    elif row.get("expires") is False and ends_on is None:
        expiry = None
    else:
        return None
    ends = [expiry] if expiry is not None else []
    if every is not None:
        last = _day(rotated)
        if not _count(every) or last is None or last > at:
            return None
        try:
            ends.append(last + datetime.timedelta(days=every))
        except OverflowError:       # a period past the calendar's end is no period this reads
            return None
    return min(ends) if ends else NEVER


def due(table, now: str) -> tuple:
    """`(raised, names)`: whether `credential_due` is raised, and the secrets due by their names, sorted."""
    at = moment(now)
    if at is None or not isinstance(table, dict) or table.get("schema") != "credential-ages/1" \
            or not _count(table.get("due_within_days")) or not isinstance(table.get("credentials"), list) \
            or not table["credentials"]:
        return True, []
    try:
        within = datetime.timedelta(days=table["due_within_days"])
    except OverflowError:
        return True, []
    rows = table["credentials"]
    names = [row.get("name") if isinstance(row, dict) else None for row in rows]
    raised, found = False, set()
    for row, name in zip(rows, names):
        readable = isinstance(name, str) and NAME.fullmatch(name) is not None and names.count(name) == 1
        if readable and row.get("kind") == COORDINATE and row.get("expires") is False \
                and all(field in row and row[field] is None for field in DATES):
            continue
        ends = limit(row, at) if readable and row.get("kind") in KINDS else None
        if ends is NEVER:
            continue
        if ends is None or ends - at <= within:
            raised = True
            if isinstance(name, str) and NAME.fullmatch(name):
                found.add(name)
    return raised, sorted(found)
