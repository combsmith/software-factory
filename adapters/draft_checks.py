"""How the required checks stand on the head of a draft the Factory opened for an issue: `checks` of a linked pull request
in `issue-facts/1`, read only where the issue rule would act on them (decision 0217, issue 878).

The checks port (`adapters/checks.py`) reads the head's rollup, refusing one of another commit or read while the head
moved. Each required deterministic Lens, `required_lenses.deterministic`, is read from it as the pull requests' Kernel
reads one (`kernel/derive.py`, `lens_reading`), so a check under a Lens's name from another App or file is no Lens's: a
Lens that has not reported, as for a few seconds after a push (trial P-42), is pending, never failing. Then: any Lens
unreadable, or any foreign check under a Lens's name, leaves `checks` null; else any failing is `failing`; any pending,
or concluding, its failing suite not yet concluded, is `pending`; all passing is `passing`. A rollup not read whole, or
one the port refuses, leaves it null: an unreadable fact defers, never passes (the Factory Builder's rulings on issue
878, Q1, Q3 and Q5, option A each).
"""
from __future__ import annotations

from adapters import checks
from adapters.github import Unanswered
from kernel import derive


def verdict(found: list, kernel: dict):
    """`failing`, `pending`, `passing` or None, from the head's checks as the checks port gives them and the Kernel's
    configuration, `kernel`."""
    lenses = kernel["required_lenses"]["deterministic"]
    if derive.foreign_checks(found, kernel):
        return None
    readings = [derive.lens_reading(found, lens, kernel) for lens in lenses]
    if any(r not in ("failing", "pending", "concluding", "passing") for r in readings):
        return None
    if "failing" in readings:
        return "failing"
    if "pending" in readings or "concluding" in readings:
        return "pending"
    return "passing"


def read(transport, pull: dict, kernel: dict):
    """The draft's `checks`, from REST's read of it, `pull`: its head and its base's repo. None where they cannot be read."""
    try:
        found = checks.read(transport, pull)
        if found.get("complete") is not True:
            return None
        return verdict(found["checks"], kernel)
    except (Unanswered, KeyError, TypeError, AttributeError):
        return None


def asked(kernel, own: dict) -> bool:
    """Whether the rule would act on a linked pull request's checks: an author Role named, and the pull request the
    Factory's own, class `agent`, open and a draft (Q2, option A). While no author Role is named nothing is read."""
    return kernel is not None and kernel.get("author_role") is not None and own["class"] == "agent" \
        and own["state"] == "open" and own["is_draft"] is True
