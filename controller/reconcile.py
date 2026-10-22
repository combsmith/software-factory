"""Reconciliation: every write a Factory identity made on GitHub matched to an Effect the Factory recorded (I-33,
decision 0061, the working ruling on "Controller: reconciliation, every write by a Factory identity matched to a recorded
Effect (I-33)", issue 306, with the Maintainer's answers).

`reconcile(seen, effects, runs, before, accounts)` is pure, as the pass is. It is given:
- `seen`: what `adapters/seen.py` read, `seen/1`, or None if it could not be read;
- `effects`: the Effects the Factory recorded in the window, `{"applied": [applied/1], "written": [written/1], "whole"}`,
  or None;
- `runs`: the run records the pass read, held to their schema, each a dispatch the pass job's token made; None where
  the list could not be read;
- `before`: the pass records before this one, whose Decisions say whether a merge had an approval standing;
- `accounts`: the configuration's accounts, by which each identity is told.

It returns `{"unmatched": [...], "override": [...], "short": bool}`. A write with no matching Effect is unmatched,
whatever it was: the machine user's approvals with no `approve` Effect among them, the Maintainer's own in the browser
included ("Alarm on all of them", the Maintainer, 2026-10-22). A merge whose item no pass before read as converged or
queued is an Override, reported as information. Reconciliation is short, never silent, when what was seen or what was
recorded cannot be read whole, or when an identity's account is not known, since its writes cannot be told.
"""
from __future__ import annotations

from controller.shared import errors, key

# What each identity may write, and the recorded Effect each kind is matched to: (`applied/1` type or `written/1`
# type). A kind not listed for an identity is never its, so it is unmatched whatever was recorded.
APPLIED = "applied"
WRITTEN = "written"
MATCHES = {
    "approver": {"approval": (APPLIED, "approve")},
    "role": {"review": (APPLIED, "submit_review"), "comment": (APPLIED, "comment"),
             "check_run": (APPLIED, "create_check_run"), "resolution": (APPLIED, "resolve_thread")},
    "controller": {"check_run": (WRITTEN, "status_on_item"), "dequeue": (WRITTEN, "dequeue")},
}
DISPATCHES = ("dispatch_run", "dispatch_approval")
# A Decision that says the item had what a merge needs: an approval of its content standing, read by the Kernel.
MERGEABLE = ("converged", "queued")
LANDED = ("applied", "already_applied")


def _identities(accounts) -> tuple:
    """`(identities, known)`: each writing identity's code and the kind its writes are matched as, and whether every
    one's account is known. The pass job's token's dispatches are read from the records port, not from here."""
    if not isinstance(accounts, dict):
        return {}, False
    roles = accounts.get("roles")
    codes = {"approver": "approver", "controller": "controller"}
    known = all(isinstance(accounts.get(c), dict) for c in codes) and isinstance(roles, dict) \
        and all(isinstance(a, dict) for a in roles.values())
    found = {c: c for c in codes}
    found.update({name: "role" for name in (roles if isinstance(roles, dict) else {})})
    return found, known


def _keys(effects: dict) -> dict:
    """The keys of every Effect recorded as landed, by where it was recorded and its type."""
    out = {}
    for done in effects["applied"]:
        for e in done["effects"]:
            if e["state"] in LANDED and e["key"] is not None:
                out.setdefault((APPLIED, e["type"]), set()).add(e["key"])
    for done in effects["written"]:
        for w in done["writes"]:
            if w["state"] in LANDED:
                # A write is matched by the key read back, and an act on an item by its item too.
                found = out.setdefault((WRITTEN, w["type"]), set())
                found.update(([w["key"]] if w["key"] is not None else []) + ([key(w["item"])] if w["item"] else []))
    return out


def _dispatched(effects: dict) -> set:
    return {w["run"] for done in effects["written"] for w in done["writes"]
            if w["type"] in DISPATCHES and w["state"] in ("sent",) + LANDED and w["run"] is not None}


def _readable(effects) -> bool:
    return (isinstance(effects, dict) and isinstance(effects.get("applied"), list)
            and isinstance(effects.get("written"), list)
            and not any(errors(a, "applied") for a in effects["applied"])
            and not any(errors(w, "written") for w in effects["written"]))


def reconcile(seen, effects, runs, before, accounts) -> dict:
    identities, known = _identities(accounts)
    readable = seen is not None and not errors(seen, "seen")
    recorded = _readable(effects)
    short = not (readable and seen["whole"] is True and recorded and effects.get("whole") is True and known)
    keys = _keys(effects) if recorded else {}
    unmatched, override = [], []
    for w in seen["writes"] if readable else []:
        kind = identities.get(w["by"])
        if w["by"] == "unattributed":
            # GitHub names no resolver when an App resolved a thread: one a Role recorded is its own; any other is
            # nobody's that can be told, and raises nothing (ruling 3).
            continue
        where = MATCHES.get(kind, {}).get(w["kind"])
        landed = where is not None and (w["key"] if w["key"] is not None else key(w["item"])) in keys.get(where, set())
        if not landed:
            unmatched.append({"by": w["by"], "kind": w["kind"], "item": w["item"], "key": w["key"]})
    if readable and recorded:
        since = seen["since"]
        dispatched = _dispatched(effects)
        for r in runs if isinstance(runs, list) else []:
            if r["started_at"] >= since and r["run"] not in dispatched:
                unmatched.append({"by": "workflow_token", "kind": "dispatch", "item": r["item"], "key": r["run"]})
    if not isinstance(runs, list):
        short = True
    last = {}
    for record in before if isinstance(before, list) else []:
        for e in record["pull_requests"]:
            last[key(e["facts"]["item"])] = e["decision"]["state"]
    for m in seen["merged"] if readable else []:
        state = last.get(key(m["item"]))
        if state is not None and state not in MERGEABLE:
            override.append({"item": m["item"]})
    return {"unmatched": unmatched, "override": override, "short": short}


def alerts(found: dict) -> list:
    """The alerts of a reconciliation: one for every unmatched write however many (L-48), one for a reconciliation that
    was short. An Override is information, never an alert."""
    return sorted(({"write_unmatched"} if found["unmatched"] else set())
                  | ({"reconciliation_unreadable"} if found["short"] else set()))


def entries(found: dict) -> list:
    """What the view says of a reconciliation, ids and codes alone: each unmatched write, and each Override."""
    out = [{"alert": "write_unmatched", "by": u["by"], "write": u["kind"],
            "item": key(u["item"]) if u["item"] is not None else None, "key": u["key"]} for u in found["unmatched"]]
    out += [{"alert": "merged_by_override", "item": key(o["item"])} for o in found["override"]]
    return out
