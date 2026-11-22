"""How the issue each pull request the Factory opened stands with, joined to it by `opened_for` (decision 0232).

The entry reads, for each open pull request whose facts name the issue it was opened for, that issue's state and own
label events by `adapters/issues.py`'s `stood`, one read for each issue however many pull requests name it, served or
not, open or closed. `join` puts what `kernel/issue.py`'s `stands` says of it into the pull request's facts as
`issue_stands`, before the Kernel is asked: null where the issue could not be read. It decides nothing itself: the
reading of a label is the Kernel's, and the hold is `kernel/derive.py`'s. A pull request opened for no issue, or left
out unread, is not touched.
"""
from __future__ import annotations

from kernel import issue


def opened_for(facts: dict):
    """The issue the facts name the pull request was opened for, or None. The facts port holds the fact to `facts/1`, a
    number from 1 or null, and the Kernel reads nothing else as an issue (decision 0216)."""
    return facts.get("opened_for")


def wanted(pulls: list) -> list:
    """The issues to read: each named by a pull request, once, in order; one left out unread names none. Never more
    than the pull requests."""
    numbers = []
    for entry in pulls:
        number = opened_for(entry["facts"])
        if number is not None and number not in numbers:
            numbers.append(number)
    return numbers


def join(pulls: list, stood: dict, config: dict) -> list:
    """The pull requests, each opened for an issue with `issue_stands` as `stands` gives it from `stood[N]`, the issue's
    read, or None where it was not read. `config` is the issues' Kernel configuration. Nothing given is changed."""
    out = []
    for entry in pulls:
        number = opened_for(entry["facts"])
        if number is None:
            out.append(entry)
            continue
        out.append(dict(entry, facts=dict(entry["facts"], issue_stands=issue.stands(stood.get(number), config))))
    return out
