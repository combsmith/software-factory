"""Reconciliation: every write a Factory identity made on GitHub matched to an Effect the Factory recorded (I-33,
decision 0061, the working ruling on "Controller: reconciliation, every write by a Factory identity matched to a recorded
Effect (I-33)", issue 306, with the Maintainer's answers).

`reconcile(seen, effects, runs, before, accounts)` is pure, as the pass is. It is given:
- `seen`: what `adapters/seen.py` read, `seen/1`, or None if it could not be read;
- `effects`: the Effects the Factory recorded and this pass read, `{"applied": [applied/1], "written": [written/1], "read":
  {"runs", "passes"}, "whole"}`, or None. What a record before it read is carried in that record, as `carried` says;
- `runs`: the run records the pass read, held to their schema, each a dispatch the pass job's token made; None where
  the list could not be read whole. Dispatches are reconciled only once `accounts.workflow_token` is set (ruling 2);
- `before`: the pass records before this one, whose Decisions say whether a merge had an approval standing;
- `accounts`: the configuration's accounts, by which each identity is told.

It returns `{"unmatched": [...], "override": [...], "short": bool}`. A write with no matching Effect is unmatched,
whatever it was: the machine user's approvals with no `approve` Effect among them, the Maintainer's own in the browser
included ("Alarm on all of them", the Maintainer, 2026-10-22). A merge whose item no pass before read as converged or
queued in the last pass before it is an Override, reported as information. Reconciliation is short, never silent, when
what was seen or what was recorded cannot be read whole, or when an identity's account is not known, since its writes
cannot be told.
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
             "check_run": (APPLIED, "create_check_run")},
    # No Role resolves a thread: the queue App does, as the Kernel's act, recorded as a write of the pass (issue 389).
    "queue": {"resolution": (WRITTEN, "resolve_thread")},
    "controller": {"check_run": (WRITTEN, "status_on_item"), "dequeue": (WRITTEN, "dequeue")},
}
# A write GitHub gives no key for, an event of the timeline, is matched by its item: each recorded once.
BY_ITEM = ("dequeue",)
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
    # The queue App is an identity once its account is set (issue 381); until then nothing is its, and nothing short.
    if isinstance(accounts.get("queue"), dict):
        found["queue"] = "queue"
    return found, known


def _last(before) -> dict:
    """What the last record before this pass carried of what was reconciled; nothing if it holds none."""
    held = before[-1].get("reconciled") if isinstance(before, list) and before else None
    return held if isinstance(held, dict) else {"runs": [], "passes": [], "keys": [], "items": [], "dispatched": []}


def known(before) -> tuple:
    """`(runs, passes)` that a record before this pass read: each is read once. With no last record, or one that holds
    none, nothing is known, and everything in the window is read again (decision 0109)."""
    held = _last(before)
    return {e["id"] for e in held["runs"]}, {e["id"] for e in held["passes"]}


def carried(before, effects, seen, now: str) -> dict:
    """What this pass's record carries for the next: what was read in the window and the keys it held, each stamped with
    when it was read, those older than the window dropped. So a record holds what the Effects it read said, not the
    records themselves, and a pass reads only what is new (decision 0109)."""
    since = seen.get("since") if isinstance(seen, dict) else None
    held = {name: [e for e in rows if since is None or e["at"] >= since] for name, rows in _last(before).items()}
    if not _readable(effects):
        return held
    read = effects.get("read") if isinstance(effects.get("read"), dict) else {}
    keys, items = _keys(effects)
    return {"runs": held["runs"] + [{"id": r, "at": now} for r in read.get("runs", [])],
            "passes": held["passes"] + [{"id": p, "at": now} for p in read.get("passes", [])],
            "keys": held["keys"] + [{"where": where, "type": kind, "key": k, "at": now}
                                    for (where, kind), found in sorted(keys.items()) for k in sorted(found)],
            "items": held["items"] + [{"type": kind, "item": item, "count": count, "at": now}
                                      for (kind, item), count in sorted(items.items())],
            "dispatched": held["dispatched"] + [{"run": r, "at": now} for r in sorted(_dispatched(effects))]}


def _keys(effects: dict, before=None, since=None) -> tuple:
    """`(keys, items)`: the key of every Effect recorded as landed, by where it was recorded and its type; and of a
    write matched by its item, how many were recorded on each. Those a record before this pass carried count too."""
    keys, items = {}, {}
    held = _last(before)
    for e in held["keys"]:
        if since is None or e["at"] >= since:
            keys.setdefault((e["where"], e["type"]), set()).add(e["key"])
    for e in held["items"]:
        if since is None or e["at"] >= since:
            items[(e["type"], e["item"])] = items.get((e["type"], e["item"]), 0) + e["count"]
    for done in effects["applied"]:
        for e in done["effects"]:
            if e["state"] in LANDED and e["key"] is not None:
                keys.setdefault((APPLIED, e["type"]), set()).add(e["key"])
    for done in effects["written"]:
        for w in done["writes"]:
            if w["state"] not in LANDED:
                continue
            if w["type"] in BY_ITEM:
                if w["item"]:
                    items[(w["type"], key(w["item"]))] = items.get((w["type"], key(w["item"])), 0) + 1
            elif w["key"] is not None:
                keys.setdefault((WRITTEN, w["type"]), set()).add(w["key"])
    return keys, items


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
    since = seen["since"] if readable else None
    keys, items = _keys(effects, before, since) if recorded else _keys({"applied": [], "written": []}, before, since)
    unmatched, override = [], []
    for w in seen["writes"] if readable else []:
        kind = identities.get(w["by"])
        if w["by"] == "unattributed":
            # GitHub names no resolver when an App resolved a thread: nobody's that can be told, it raises nothing here
            # (ruling 3), and the thread it resolved is unreadable, so the Kernel defers on it (decision 0067).
            continue
        where = MATCHES.get(kind, {}).get(w["kind"])
        if where is not None and where[1] in BY_ITEM:
            slot = (where[1], key(w["item"]) if w["item"] else None)
            landed = items.get(slot, 0) > 0
            items[slot] = items.get(slot, 0) - 1
        else:
            landed = where is not None and w["key"] is not None and w["key"] in keys.get(where, set())
        if not landed:
            unmatched.append({"by": w["by"], "kind": w["kind"], "item": w["item"], "key": w["key"]})
    # The pass job's token is an identity once its account is set; until then no dispatch is reconciled (ruling 2).
    token = isinstance(accounts, dict) and isinstance(accounts.get("workflow_token"), dict)
    if token and readable:
        # A dispatch whose record cannot be read is unmatched, as any write is (ruling 5).
        dispatched = (_dispatched(effects) if recorded else set()) \
            | {e["run"] for e in _last(before)["dispatched"] if e["at"] >= since}
        for r in runs if isinstance(runs, list) else []:
            # A dispatch is read by when its run was made, which a re-run keeps; a re-run runs nothing (decision
            # 0058), and one the pass job's own token made is a write no Effect records (decision 0063).
            if r.get("dispatched_at", r["started_at"]) >= since and r["run"] not in dispatched:
                unmatched.append({"by": "workflow_token", "kind": "dispatch", "item": r["item"], "key": r["run"]})
            if r.get("rerun_by_dispatcher") is True and r["started_at"] >= since:
                unmatched.append({"by": "workflow_token", "kind": "rerun", "item": r["item"], "key": r["run"]})
            # A re-run whose re-runner, or a run whose attempt, cannot be read cannot be told from the token's.
            if "rerun_by_dispatcher" in r and r["rerun_by_dispatcher"] is None and r["started_at"] >= since:
                short = True
    if token and not isinstance(runs, list):
        short = True
    for m in seen["merged"] if readable else []:
        # What the last pass before the merge read of the item: a pass after it reads it merged.
        state = None
        for record in before if isinstance(before, list) else []:
            if record["now"] < m["at"]:
                for e in record["pull_requests"]:
                    if key(e["facts"]["item"]) == key(m["item"]):
                        state = e["decision"]["state"]
        if state is not None and state not in MERGEABLE:
            override.append({"item": m["item"]})
    return {"unmatched": unmatched, "override": override, "short": short}


def alerts(found: dict) -> list:
    """The alerts of a reconciliation: one for every unmatched write however many (L-48), one for a reconciliation that
    was short. An Override is information, never an alert."""
    return sorted(({"write_unmatched"} if found["unmatched"] else set())
                  | ({"reconciliation_unreadable"} if found["short"] else set()))


def entries(found: dict) -> list:
    """What the view says of a reconciliation, ids and codes alone: each unmatched write, and each Override, once each,
    since two writes GitHub gives no key for read the same."""
    out = []
    for e in [{"alert": "write_unmatched", "by": u["by"], "write": u["kind"],
               "item": key(u["item"]) if u["item"] is not None else None, "key": u["key"]} for u in found["unmatched"]] \
            + [{"alert": "merged_by_override", "by": None, "write": "merge", "item": key(o["item"]), "key": None}
               for o in found["override"]]:
        if e not in out:
            out.append(e)
    return out
