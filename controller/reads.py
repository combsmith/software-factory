"""What a pass reads, held to its schemas before anything is decided from it: the pass records before it, the records
port's list, each item's facts and the Controller's configuration. What cannot be read is unreadable, never guessed:
the records before it are None, the list is not listed, an item is left out, and a configuration is refused."""
from __future__ import annotations

from controller.shared import Refused, errors, key, moment

DIGITS = frozenset("0123456789")


def previous_records(previous):
    """The pass records before this one, or None if they could not be read or one of them is not a pass record."""
    if not isinstance(previous, list) or any(errors(r, "pass") for r in previous):
        return None
    return previous


def run_records(records) -> tuple:
    """`(listed, whole)`: whether the records port's list can be read at all, every run record a run record, every
    unidentified Run a GitHub id and every read a date and an age; and whether it was also read whole."""
    if not isinstance(records, dict):
        return False, False
    runs, unidentified, reads = records.get("runs"), records.get("unidentified"), records.get("reads")
    listed = (isinstance(runs, list) and not any(errors(r, "run-record") for r in runs)
              and isinstance(unidentified, list)
              and all(isinstance(i, str) and i != "" and set(i) <= DIGITS for i in unidentified)
              and isinstance(reads, list) and all(_read(r) for r in reads))
    return listed, listed and records.get("complete") is True


def _read(entry) -> bool:
    """One read of the list, as the pass record keeps it: `runs`, a date and an age in whole seconds."""
    return (isinstance(entry, dict) and set(entry) == {"read", "date", "age"} and entry["read"] == "runs"
            and moment(entry["date"]) is not None and type(entry["age"]) is int and entry["age"] >= 0)


def items(entries, kind: str) -> tuple:
    """`(kept, left_out)`: the entries whose facts are facts of `kind`, and the item of each that is not, as one list.
    An item listed twice is left out every time it is listed, so that one pass never decides it twice."""
    if not isinstance(entries, list):
        # A list of items that could not be read is no evidence that there are none: a pass that wrote an empty feed
        # from it would look healthy. It is refused, and the not-run alert reports it.
        raise Refused("the list of %s could not be read" % ("pull requests" if kind == "facts" else "issues"))
    readable = [e for e in entries if isinstance(e, dict) and not errors(e.get("facts"), kind)]
    # An item listed twice is counted wherever it can be named, readable or not, so a bad copy leaves the good one out.
    seen = [_named(e) for e in entries]
    kept = [e for e in readable if seen.count(key(e["facts"]["item"])) == 1]
    left_out = [e.get("facts", {}).get("item") if isinstance(e, dict) and isinstance(e.get("facts"), dict) else None
                for e in entries if not any(e is k for k in kept)]
    return kept, [i if isinstance(i, dict) else None for i in left_out]


def _named(entry):
    """The item an entry names, as its page, wherever it can be read; None otherwise."""
    item = entry.get("facts", {}).get("item") if isinstance(entry, dict) and isinstance(entry.get("facts"), dict) else None
    if not (isinstance(item, dict) and isinstance(item.get("repo"), str) and item.get("type") in ("pull_request", "issue")
            and type(item.get("number")) is int):
        return None
    return key(item)


def configured(controller: dict) -> dict:
    """The Controller's configuration, if it is a `controller/1`; otherwise refused, since no pass can be told without
    it what started it or when to wait."""
    problems = errors(controller, "controller")
    if problems:
        raise Refused("controller/1: %s" % "; ".join(problems))
    return controller
