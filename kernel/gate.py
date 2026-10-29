"""The gate (design §4.2): which open Findings hold a pull request, and the severities that gate.

A Finding gates when it sends the Work item back to its author. A person's thread or request for changes always
gates; a required model Lens's Finding gates at a severity in GATING_SEVERITIES, or of category SECURITY at any.
derive() reads the gate to work out the State; nothing here works out a State. It imports nothing of the Kernel
(tools/check_purity.py).
"""
from __future__ import annotations

GATING_SEVERITIES = frozenset({"blocking", "major"})
# A Finding of this category gates at any severity: severity is never how a security defect gets merged (FR-33).
SECURITY = "security"


def is_person(actor) -> bool:
    """A person: an actor of kind `human` whose write access is exactly true. Nobody else is, whatever its access (I-28).

    The port tells the kinds apart from GitHub's account type and the configuration, never from a name's spelling
    (L-57), so an App, a Lens's App and the machine user are never a person.
    """
    return isinstance(actor, dict) and actor.get("kind") == "human" and actor.get("can_write") is True


def closed(th: dict) -> bool:
    """Whether a thread was resolved by someone who may close it (L-17).

    A person's thread is closed only by that person. A Lens's is closed only by a person, or by the queue App on that
    Lens's accepted ruling (issue 389): the Lens judges, and resolving the thread is the Kernel's act, which the queue
    App carries out. So no Role decides a Finding about its own work, the author agent resolving the threads that hold
    it closes none, and nor does the Lens's own App. Resolved by anyone else, a thread stays open. A thread that gates
    nothing is closed by whoever resolves it.
    """
    if not th["resolved"]:
        return False
    opener, by = th["opened_by"], th["resolved_by"]
    if is_person(opener):
        return is_person(by) and by["name"] == opener["name"]
    if opener["kind"] == "lens":
        return is_person(by) or (by["kind"] == "queue" and th["ruling"] == "accepted")
    return True


def gating_threads(facts: dict, config: dict) -> list:
    """Open threads that hold the pull request.

    A person with write access always gates. A Lens gates only if it is
    required and its Finding is blocking or major, or is a security Finding
    of any severity. Everyone else informs. A Finding that does not gate is
    an annotation on its Lens's check run, and closes when the Lens stops
    reporting it. A Finding a model Lens has raised gates whatever the class:
    a dependency update needs no review, and still answers one it was given.
    A thread resolved by someone who may not close it is open (closed).
    """
    required = set(config["required_lenses"]["model"])
    out = []
    for th in facts["threads"]:
        if closed(th):
            continue
        by = th["opened_by"]
        if is_person(by):
            out.append(th)
        elif by["kind"] == "lens" and by["name"] in required and (
                th["category"] == SECURITY or th["severity"] in GATING_SEVERITIES):
            out.append(th)
    return out


def verdict_order(rv: dict) -> tuple:
    """When a review was made. A request for changes comes after anything else in the same second: fail closed."""
    return rv["submitted_at"], "changes_requested" in (rv["state"], rv.get("dismissed_from"))


def standing_requests(facts: dict) -> list:
    """Requests for changes that hold the pull request, one for each person with write access.

    A person's latest verdict counts; a review that only comments is none, dismissed or not. A
    request stands across new content, as GitHub keeps it, until that person approves or a person
    with write access dismisses it. An approval answers it even once dismissed, as when an App's
    push dismisses it as stale; it still approves no content. Only a person ends a request: a
    dismissal by an App, a Lens's App, the machine user or a stranger does not clear it, as the
    reviewer's App holds pull_requests: write, and no Role closes a person's objection (L-17); nor
    does anyone's approval but that person's. A request from anyone but a person gates nothing.
    """
    latest = {}
    for rv in sorted(facts["reviews"], key=verdict_order):
        if rv["state"] == "dismissed" and rv["dismissed_from"] == "commented":
            continue
        if is_person(rv["by"]) and rv["state"] != "commented":
            latest[rv["by"]["name"]] = rv
    out = []
    for name, rv in sorted(latest.items()):
        if rv["state"] == "dismissed":
            if rv["dismissed_from"] != "changes_requested":
                continue
            if is_person(rv["dismissed_by"]):
                continue
        elif rv["state"] != "changes_requested":
            continue
        out.append({"id": name, "by": rv["by"], "at": rv["submitted_at"]})
    return out


def gates(facts: dict, config: dict) -> list:
    """Every open Finding that holds the pull request, as {'id', 'by', 'at'}.

    A gating thread, and a request for changes from a person with write access, which gates as
    that person's thread does (decision 0007).
    """
    threads = [{"id": th["id"], "by": th["opened_by"], "at": th["opened_at"]} for th in gating_threads(facts, config)]
    return threads + standing_requests(facts)
