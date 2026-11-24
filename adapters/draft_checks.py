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

Beside its checks, `head` gives the draft's own head, the commit and the branch an implementing Run is admitted at
(issue 1059): only for the Factory's draft from this repo, on a branch of the Factory's shape; else null, and the Kernel
defers that Run.
"""
from __future__ import annotations

import re

from adapters import checks
from adapters.github import Unanswered
from kernel import derive, terms

SHA = re.compile(r"[0-9a-f]{40}")
WORK = re.compile(terms.WORK_BRANCH)


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


def head(pull: dict):
    """The draft's own head, `{"sha", "ref"}`, from REST's read of it, `pull`, read where its checks are: the commit an
    implementing Run is admitted at and pushes past (issue 1059). None where it cannot be told the Factory's from this
    repo: a head from another repo, or one whose repo, commit or branch cannot be read, or a branch of another shape than
    the Factory's work branch (decision 0068)."""
    found = pull.get("head") if isinstance(pull.get("head"), dict) else {}
    base = pull.get("base") if isinstance(pull.get("base"), dict) else {}
    held, given = found.get("repo"), base.get("repo")
    mine = held.get("id") if isinstance(held, dict) else None
    home = given.get("id") if isinstance(given, dict) else None
    sha, ref = found.get("sha"), found.get("ref")
    # From this repo as `adapters/pull.own` tells it: the head's repo is the base's, by id.
    if not (type(home) is int and mine == home and type(mine) is int and isinstance(sha, str) and SHA.fullmatch(sha)
            and isinstance(ref, str) and WORK.fullmatch(ref)):
        return None
    return {"sha": sha, "ref": ref}


def asked(kernel, own: dict) -> bool:
    """Whether the rule would act on a linked pull request's checks: an author Role named, and the pull request the
    Factory's own, class `agent`, open and a draft (Q2, option A). While no author Role is named nothing is read."""
    return kernel is not None and kernel.get("author_role") is not None and own["class"] == "agent" \
        and own["state"] == "open" and own["is_draft"] is True
