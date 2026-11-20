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

It returns `{"unmatched": [...], "override": [...], "hand": [...], "short": bool}`. A write with no matching Effect is unmatched,
whatever it was: the machine user's approvals with no `approve` Effect among them, the Maintainer's own in the browser
included ("Alarm on all of them", the Maintainer, 2026-10-22). A merge whose item no pass before read as converged or
queued in the last pass before it is an Override, reported as information, as is a hand approval (decision 0241).
Reconciliation is short, never silent, when
what was seen or what was recorded cannot be read whole, or when an identity's account is not known, since its writes
cannot be told.
"""
from __future__ import annotations

import re

from controller.shared import errors, key, moment

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
DISPATCHES = ("dispatch_run", "dispatch_approval", "dispatch_queue")
# A Decision that says the item had what a merge needs: an approval of its content standing, read by the Kernel.
MERGEABLE = ("converged", "queued")
LANDED = ("applied", "already_applied")
# The waits for a person alone (decisions 0052, 0200, 0207), under which an unmatched approval may be a hand's (0241).
HAND = ("model_lens_input_needs_person", "path_needs_person")
COMMIT = re.compile(r"[0-9a-f]{40}")
STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
LATE = 60 * 60          # how much later than its record's own making a pass's or a Run's write can be: the job's limits


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


EMPTY = {"runs": [], "passes": [], "keys": [], "items": [], "dispatched": [], "owed": [], "left": []}
# What a carried value may be, as `pass/1` holds it: a record's own schema may be wider, and one that does not fit is not
# carried and leaves reconciliation short, so that one record never refuses a pass.
FITS_KEY = re.compile(r"[A-Za-z0-9_=:-]{1,100}")
FITS_RUN = re.compile(r"r_[0-9A-Z]{6,26}")
FITS_ITEM = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/(pull|issues)/[1-9][0-9]*")


def _within(at: str, since: str, late: bool = False) -> bool:
    """Whether a carried stamp is inside the window; one of when a record was made, `late`, by `LATE` more."""
    return at >= since or (late and (moment(since) - moment(at)).total_seconds() <= LATE)


def _last(before) -> dict:
    """What the last record before this pass carried of what was reconciled; nothing if it holds none."""
    held = before[-1].get("reconciled") if isinstance(before, list) and before else None
    return held if isinstance(held, dict) else EMPTY


def known(before) -> tuple:
    """`(runs, passes)` that a record before this pass read: each is read once, a pass's attempt by its attempt, since a
    re-run writes again. With no last record, or one that holds none, nothing is known, and everything in the window is
    read again (decision 0112)."""
    held = _last(before)
    return {e["id"] for e in held["runs"]}, {(e["id"], e["attempt"]) for e in held["passes"]}


def owed(before) -> list:
    """The pull requests a record before this pass could not read the writes on: read until they have been (decision 0112)."""
    return list(_last(before)["owed"])


def left(before, since=None) -> list:
    """The pull requests a record before this pass read as left, inside the window from `since`, or all it holds with no
    `since`: their writes are read on every pass until the window passes when one was first read gone, so a write nobody
    matched keeps its alert as long (issue 787)."""
    return [e["number"] for e in _last(before).get("left", []) if since is None or _within(e["at"], since)]


def _one(doc: dict, kind: str) -> dict:
    return {"applied": [doc], "written": []} if kind == APPLIED else {"applied": [], "written": [doc]}


def unfit(effects) -> bool:
    """Whether a landed Effect's key or item cannot be carried. It can match nothing GitHub says, and reads as short."""
    keys, items = _keys(effects)
    return any(not FITS_KEY.fullmatch(k) for found in keys.values() for k in found) \
        or any(not FITS_ITEM.fullmatch(item) for _, item in items)


def carried(before, effects, seen, now: str, unread=(), gone=()) -> dict:
    """What this pass's record carries for the next: what was read in the window and the keys it held, those older than the
    window dropped, and the pull requests whose writes it could not read. A key, which one write alone can match, is stamped
    with when it was read, so it outlasts the write it records. A write matched by its item is credit any such write could
    spend, so it is stamped with when its record was made, and kept for `LATE` after, as the writes it records are later
    than that; so a late first read does not stretch it. So a record holds what the Effects said, not the records
    themselves, and a pass reads only what is new (decision 0112). Each pull request `gone`, first read as left by this
    pass, is stamped with now, and one a record before stamped is kept until the window passes it (issue 787)."""
    since = seen["since"] if seen is not None and not errors(seen, "seen") else None
    held = {name: [e for e in rows if name == "owed" or since is None or _within(e["at"], since, name == "items")]
            for name, rows in _last(before).items()}
    held["owed"] = sorted(set(unread))
    held["left"] = [e for e in held.get("left", []) if e["number"] not in set(gone)] + [
        {"number": n, "at": now} for n in sorted(set(gone))]
    if not _readable(effects):
        return held
    read = effects.get("read") if isinstance(effects.get("read"), dict) else {}
    stamps = effects.get("at") if isinstance(effects.get("at"), dict) else {}
    out = dict(held, runs=held["runs"] + [{"id": r, "at": now} for r in read.get("runs", []) if FITS_RUN.fullmatch(r)],
               passes=held["passes"] + [dict(p, at=now) for p in read.get("passes", [])],
               keys=list(held["keys"]), items=list(held["items"]), dispatched=list(held["dispatched"]))
    for kind, docs, name in ((APPLIED, effects["applied"], "run"), (WRITTEN, effects["written"], "pass")):
        for doc in docs:
            at = stamps.get(doc[name])
            at = at if isinstance(at, str) and STAMP.fullmatch(at) else now
            keys, items = _keys(_one(doc, kind))
            out["keys"] += [{"where": where, "type": t, "key": k, "at": now} for (where, t), found in sorted(keys.items())
                            for k in sorted(found) if FITS_KEY.fullmatch(k)]
            out["items"] += [{"type": t, "item": item, "count": count, "at": at} for (t, item), count in sorted(items.items())
                             if FITS_ITEM.fullmatch(item)]
            out["dispatched"] += [{"run": r, "at": now} for r in sorted(_dispatched(_one(doc, kind))) if FITS_RUN.fullmatch(r)]
    return out


def _keys(effects: dict, before=None, since=None) -> tuple:
    """`(keys, items)`: the key of every Effect recorded as landed, by where it was recorded and its type; and of a
    write matched by its item, how many were recorded on each. Those a record before this pass carried count too."""
    keys, items = {}, {}
    held = _last(before)
    for e in held["keys"]:
        if since is None or e["at"] >= since:
            keys.setdefault((e["where"], e["type"]), set()).add(e["key"])
    for e in held["items"]:
        if since is None or _within(e["at"], since, True):
            items[(e["type"], e["item"])] = items.get((e["type"], e["item"]), 0) + e["count"]
    for done in effects["applied"]:
        for e in done["effects"]:
            if e["state"] in LANDED and e["key"] is not None:
                keys.setdefault((APPLIED, e["type"]), set()).add(e["key"])
    for done in effects["written"]:
        for w in done["writes"]:
            # The tracking issue written, open, with its assignee dropped is recorded as failed under its number: the
            # issue is there, and its number is kept, which matches no write of any identity (issue 901).
            if w["state"] not in LANDED and (w["type"], w["reason"]) != ("tracking_issue", "assignee_dropped"):
                continue
            if w["type"] in BY_ITEM:
                if w["item"]:
                    items[(w["type"], key(w["item"]))] = items.get((w["type"], key(w["item"])), 0) + 1
            elif w["key"] is not None:
                keys.setdefault((WRITTEN, w["type"]), set()).add(w["key"])
    return keys, items


def tracking(written, before):
    """The numbers the passes recorded landing a write of the tracking issue under, as `written/1` keys one, or writing
    it open with its assignee dropped: those this pass read, `written` as `adapters/passes.written` gives them, and
    those the last record carried. A key of anything but ASCII digits is no number: `'²'.isdigit()` holds, and `int`
    refuses it. None where the passes' records were not read whole: the number may be one not read, and the caller
    serves no issue (issue 901)."""
    if not isinstance(written, dict) or written.get("whole") is not True:
        return None
    keys, _ = _keys({"applied": [], "written": written["written"]}, before)
    return sorted(int(k) for k in keys.get((WRITTEN, "tracking_issue"), ()) if k.isascii() and k.isdecimal())


def _dispatched(effects: dict) -> set:
    return {w["run"] for done in effects["written"] for w in done["writes"]
            if w["type"] in DISPATCHES and w["state"] in ("sent",) + LANDED and w["run"] is not None}


def _readable(effects) -> bool:
    return (isinstance(effects, dict) and isinstance(effects.get("applied"), list)
            and isinstance(effects.get("written"), list)
            and not any(errors(a, "applied") for a in effects["applied"])
            and not any(errors(w, "written") for w in effects["written"]))


def decided(before, item, at):
    """`(reason, head)` of `item` in the last pass record before `at`, or None (decision 0241)."""
    if not isinstance(before, list) or moment(at) is None:
        return None
    last = [r for r in before if isinstance(r, dict) and moment(r.get("now")) is not None and r["now"] < at]
    if not last:
        return None
    for e in last[-1].get("pull_requests", []):
        if key(e["facts"]["item"]) == key(item):
            return e["decision"].get("reason"), e.get("head")
    return None


def hand_approved(w: dict, before, heads: dict) -> bool:
    """Whether unmatched approval `w` is a hand approval: its pull request decided under `HAND` by the last pass record
    before it, at the commit it approved, and no other approval's key holding its head in `heads`; what cannot be read
    is none (decision 0241)."""
    commit = w.get("commit")      # read as a commit of a pull request before it is asked here
    found = decided(before, w["item"], w.get("at"))
    if found is None or found[0] not in HAND or found[1] != commit:
        return False
    return not heads.get((key(w["item"]), commit), set()) - {w["key"]}


def reconcile(seen, effects, runs, before, accounts) -> dict:
    identities, known = _identities(accounts)
    readable = seen is not None and not errors(seen, "seen")
    recorded = _readable(effects)
    short = not (readable and seen["whole"] is True and recorded and effects.get("whole") is True and known)
    short = short or (recorded and unfit(effects))
    # A Run still running may have written what it has yet to record, so its writes read as short, not as unmatched.
    running = {key(r["item"]) for r in runs if r.get("status") != "completed"} if isinstance(runs, list) else set()
    since = seen["since"] if readable else None
    keys, items = _keys(effects, before, since) if recorded else _keys({"applied": [], "written": []}, before, since)
    unmatched, override, hand, approvals = [], [], [], []
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
        entry = None
        if not landed and kind != "controller" and w["item"] and key(w["item"]) in running:
            short = True
        elif not landed:
            entry = {"by": w["by"], "kind": w["kind"], "item": w["item"], "key": w["key"]}
            unmatched.append(entry)
        if w["kind"] == "approval":
            # Every approval takes its head; the machine user's, unmatched, may be judged a hand approval below.
            approvals.append((w, entry if kind == "approver" else None))
    # A carried hand approval stands; any other is judged in the order given, one to a head (decision 0241).
    carried_hand = {e["key"]: e for e in _last(before).get("hand", [])}
    # Each head an approval took, a hand one or an unmatched one, by the keys that took it, until its pull request leaves.
    heads, seconds = {}, []
    for e in list(carried_hand.values()) + _last(before).get("taken", []):
        heads.setdefault((e["item"], e["head"]), set()).add(e["key"])
    of_head = [(w, entry) for w, entry in approvals if isinstance(w.get("commit"), str) and COMMIT.fullmatch(w["commit"])
               and isinstance(w["item"], dict) and w["item"].get("type") == "pull_request"]
    # Two approvals of a head in the same second cannot be told first and second: neither is a hand approval.
    ties = {}
    for w, _ in of_head:
        ties[(key(w["item"]), w["commit"], w["at"])] = ties.get((key(w["item"]), w["commit"], w["at"]), 0) + 1
    taken = []
    # Read only from a whole read, every source of a short one counted: what cannot be read is never information.
    whole = not short
    for w, entry in sorted(of_head, key=lambda a: (a[0]["at"] if isinstance(a[0]["at"], str) else "", a[0]["key"] or "")):
        held = carried_hand.get(w["key"]) if w["key"] is not None else None
        alone = whole and entry is not None and ties[(key(w["item"]), w["commit"], w["at"])] == 1
        if alone and held is not None and held["item"] == key(w["item"]) \
                and (held["head"], held["at"]) == (w["commit"], w["at"]):
            hand.append({"item": w["item"], "key": w["key"], "head": held["head"], "at": held["at"]})
            taken.append(entry)
        elif alone and held is None and w["key"] is not None and hand_approved(w, before, heads):
            heads.setdefault((key(w["item"]), w["commit"]), set()).add(w["key"])
            hand.append({"item": w["item"], "key": w["key"], "head": w["commit"], "at": w["at"]})
            taken.append(entry)
        else:
            # Matched, unmatched or keyless, it takes its head: an approval of that head after it is a second (0241).
            heads.setdefault((key(w["item"]), w["commit"]), set()).add(w["key"])
            if w["key"] is not None:
                seconds.append({"item": w["item"], "key": w["key"], "head": w["commit"]})
    unmatched = [u for u in unmatched if not any(u is t for t in taken)]
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
    return {"unmatched": unmatched, "override": override, "hand": hand, "taken": seconds, "short": short}


def alerts(found: dict) -> list:
    """The alerts of a reconciliation: one for every unmatched write however many (L-48), one for a reconciliation that
    was short. An Override and a hand approval are information, never an alert."""
    return sorted(({"write_unmatched"} if found["unmatched"] else set())
                  | ({"reconciliation_unreadable"} if found["short"] else set()))


def entries(found: dict) -> list:
    """What the view says of a reconciliation, ids and codes alone: each unmatched write, each Override and each hand
    approval, once each, since two writes GitHub gives no key for read the same."""
    out = []
    for e in [{"alert": "write_unmatched", "by": u["by"], "write": u["kind"],
               "item": key(u["item"]) if u["item"] is not None else None, "key": u["key"]} for u in found["unmatched"]] \
            + [{"alert": "merged_by_override", "by": None, "write": "merge", "item": key(o["item"]), "key": None}
               for o in found["override"]] \
            + [{"alert": "hand_approval", "by": "approver", "write": "approval", "item": key(h["item"]), "key": h["key"]}
               for h in found.get("hand", [])]:
        if e not in out:
            out.append(e)
    return out
