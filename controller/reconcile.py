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

It returns `{"unmatched": [...], "override": [...], "unjudged": [...], "hand": [...], "taken": [...], "short": bool}`.
A write with no matching Effect is unmatched,
whatever it was: the machine user's approvals with no `approve` Effect among them, the Maintainer's own in the browser
included ("Alarm on all of them", the Maintainer, 2026-10-22). A merge whose item no pass before read as converged or
queued in the last pass before it is an Override, reported as information, as is a hand approval (decision 0241).
Reconciliation is short, never silent, when
what was seen or what was recorded cannot be read whole, or when an identity's account is not known, since its writes
cannot be told.

One write of a person's is reconciled too, a `hand`'s: the resolution of a thread a Role opened (decision 0223). It
is matched to the act `resolve_thread` of the last pass before that decided its item, and then carried, since it has
no time and is seen at every pass. One no act named raises `hand_unmatched`, an alert of its own. One no record before
can judge is `unjudged`: short for that pass, carried, and named in the view, `hand_unjudged`.
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
HAND = "hand"           # who a person's resolution of a thread a Role opened is by, as `adapters/seen.py` reads it
# The waits for a person alone (decisions 0052, 0200, 0207), under which an unmatched approval may be a hand's (0241).
PERSON_WAITS = ("model_lens_input_needs_person", "path_needs_person")
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
    # A Role named as a hand's writes are could not be told from a person: no identity is known then.
    known = known and HAND not in found
    # A Lens's thread is the facts' by the Lens's account, and a hand's by its Role's (`adapters/seen.py`): where the
    # two are not one account, a person's resolution of that Lens's thread is read as no write, so none is known.
    lenses = accounts.get("lenses")
    for lens in lenses if isinstance(lenses, list) else ():
        name = lens.get("lens") if isinstance(lens, dict) else None
        role = roles.get(name) if isinstance(roles, dict) and isinstance(name, str) else None
        if not isinstance(role, dict) or role.get("type") != "Bot" or role.get("id") != lens.get("id"):
            known = False
    # The queue App is an identity once its account is set (issue 381); until then nothing is its, and nothing short.
    if isinstance(accounts.get("queue"), dict):
        found["queue"] = "queue"
    return found, known


EMPTY = {"runs": [], "passes": [], "keys": [], "items": [], "dispatched": [], "owed": [], "left": [], "owed_issues": [],
         "left_issues": []}
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


def _named(before, item: str) -> tuple:
    """`(threads, whole)`: the threads that the last pass before which decided `item` named in its act `resolve_thread`,
    none if its Decision was any other. A pass that did not decide the item, which it could not read, says nothing of it,
    and where no record before decided it, nothing can judge the rest: not whole. Nor can that record if it was written
    before a hand's resolutions were carried: the rule starts for an item where the record that decided it starts it
    (issue 887). A pass that read the item's writes short could not see a resolution made before it: the one before it
    names threads too, and what the passes after it named still stands where nothing before can judge."""
    named = set()
    for record in reversed(before if isinstance(before, list) else []):
        for e in record["pull_requests"]:
            if key(e["facts"]["item"]) == item:
                reconciled = record.get("reconciled") if isinstance(record.get("reconciled"), dict) else {}
                if "hands" not in reconciled:
                    return named, False
                d = e["decision"]
                named |= set(d["evidence"]) if d["outcome"] == "act" and d.get("action") == "resolve_thread" else set()
                if e["facts"]["item"]["number"] not in reconciled.get("owed", ()):
                    return named, True
                break
    return named, False


def _is_hands(w: dict) -> bool:
    """Whether a write seen is a hand's resolution of a thread that can be named, on an item."""
    return w["by"] == HAND and w["kind"] == "resolution" and w["key"] is not None and w["item"] is not None


def _hands(seen: dict, before) -> tuple:
    """`(matched, unjudged)`, each the threads of a hand's resolutions seen: those matched, to what a record before
    carried or to the act that named the thread; and those no record before can judge, the last one carrying none of a
    hand's, or none having decided the item. Any other is unmatched."""
    held = _last(before).get("hands")
    carried_ = {e["key"] for e in held or () if _within(e["at"], seen["since"])}
    matched, unjudged = set(), set()
    for w in filter(_is_hands, seen["writes"]):
        named, whole = _named(before, key(w["item"])) if held is not None else (set(), False)
        if w["key"] in carried_ or w["key"] in named:
            matched.add(w["key"])
        elif not whole:
            unjudged.add(w["key"])
    return matched, unjudged


def owed_issues(before) -> list:
    """The issues a record before this pass could not read the writes on, or carried unread for want of a listing: read
    until they have been (issue 916)."""
    return list(_last(before).get("owed_issues", []))


def left_issues(before, since=None) -> list:
    """The issues a record before this pass read as left, closed since it served them, inside the window from `since`,
    or all it holds with no `since`: read as a pull request that left is (issue 916)."""
    return [e["number"] for e in _last(before).get("left_issues", []) if since is None or _within(e["at"], since)]


def _one(doc: dict, kind: str) -> dict:
    return {"applied": [doc], "written": []} if kind == APPLIED else {"applied": [], "written": [doc]}


def unfit(effects) -> bool:
    """Whether a landed Effect's key or item cannot be carried. It can match nothing GitHub says, and reads as short."""
    keys, items = _keys(effects)
    return any(not FITS_KEY.fullmatch(k) for found in keys.values() for k in found) \
        or any(not FITS_ITEM.fullmatch(item) for _, item in items)


def carried(before, effects, seen, now: str, unread=(), gone=(), unread_issues=(), gone_issues=(), served_issues=(),
            hand=(), taken=(), open_=(), home=None) -> dict:
    """What this pass's record carries for the next: what was read in the window and the keys it held, those older than the
    window dropped, and the pull requests whose writes it could not read. A key, which one write alone can match, is stamped
    with when it was read, so it outlasts the write it records. A write matched by its item is credit any such write could
    spend, so it is stamped with when its record was made, and kept for `LATE` after, as the writes it records are later
    than that; so a late first read does not stretch it. So a record holds what the Effects said, not the records
    themselves, and a pass reads only what is new (decision 0112). Each pull request `gone`, first read as left by this
    pass, is stamped with now, and one a record before stamped is kept until the window passes it (issue 787). So are
    the issues, `unread_issues` and `gone_issues`; but an issue in `served_issues`, served by this pass, keeps no stamp
    of an earlier leaving, so that it is read as left anew once it leaves again, whatever pass between could not list it
    (issue 916). So are `hand` and `taken` until the pass that drops their leaving; one in `open_`, read open, keeps
    its own (decision 0241), and a pull request read open keeps no stamp of an earlier leaving, as a served issue
    (issue 1191). `left` holds numbers alone, so a leaving drops only the rows of `home`, the pass's repository, and
    only `home`'s pull request read open clears a stamp; another's rows stay for good, whatever stamp their number has.
    With no `home`, every repository is read as it (issue 1190)."""
    since = seen["since"] if seen is not None and not errors(seen, "seen") else None
    held = {name: [e for e in rows if name in ("owed", "owed_issues", "hand", "taken") or since is None
                   or _within(e["at"], since, name == "items")]
            for name, rows in _last(before).items()}
    held["owed"] = sorted(set(unread))
    # One clock: kept until the pass that drops the leaving (decision 0241).
    dropped = {e["number"] for e in _last(before).get("left", [])} - {e["number"] for e in held.get("left", [])} - set(gone)
    opened = set(open_)

    def ours(item: str) -> bool:
        return home is None or item.startswith("https://github.com/%s/" % home)

    def stays(item: str) -> bool:
        return not ours(item) or int(item.rsplit("/", 1)[1]) not in dropped or item in opened
    known_hand = {e["key"] for e in held.get("hand", [])}
    hands = [e for e in held.pop("hand", []) if stays(e["item"])] + [
        {"key": h["key"], "item": key(h["item"]), "head": h["head"], "at": h["at"]} for h in hand
        if h["key"] not in known_hand and FITS_KEY.fullmatch(h["key"]) and FITS_ITEM.fullmatch(key(h["item"]))
        and stays(key(h["item"]))]
    if hands:
        held["hand"] = hands
    heads_ = [e for e in held.pop("taken", []) if stays(e["item"])] + [
        {"key": t["key"], "item": key(t["item"]), "head": t["head"]} for t in taken
        if (t["key"] is None or FITS_KEY.fullmatch(t["key"]))
        and FITS_ITEM.fullmatch(key(t["item"])) and stays(key(t["item"]))]
    # Each once, in order: read again, or keyless twice in a pass.
    heads_ = [dict(zip(("key", "item", "head"), row)) for row in dict.fromkeys((e["key"], e["item"], e["head"]) for e in heads_)]
    # One carried as the hand is not carried as taken too, so the record says which was read as the hand.
    hand_rows = {(e["key"], e["item"], e["head"]) for e in hands}
    heads_ = [e for e in heads_ if (e["key"], e["item"], e["head"]) not in hand_rows]
    if heads_:
        held["taken"] = heads_
    restamped = set(gone) | {int(i.rsplit("/", 1)[1]) for i in opened if i.rsplit("/", 2)[1] == "pull" and ours(i)}
    held["left"] = [e for e in held.get("left", []) if e["number"] not in restamped] + [
        {"number": n, "at": now} for n in sorted(set(gone))]
    # A hand's resolution that was matched, or that nothing could judge, is stamped again each pass it is seen.
    matched = set().union(*_hands(seen, before)) if since is not None else set()
    held["hands"] = [e for e in held.get("hands", []) if e["key"] not in matched] + [
        {"key": thread, "at": now} for thread in sorted(matched)]
    if (since is None or not seen["whole"]) and "hands" not in _last(before):
        del held["hands"]       # or the next pass judges threads from before the rule it never read
    held["owed_issues"] = sorted(set(unread_issues))
    newly_gone = set(gone_issues)
    unstamped = newly_gone | set(served_issues)
    held["left_issues"] = [e for e in held.get("left_issues", []) if e["number"] not in unstamped] + [
        {"number": n, "at": now} for n in sorted(newly_gone)]
    # A record with no issue to carry carries neither, as one written before them (issue 916).
    for name in ("owed_issues", "left_issues"):
        if not held[name]:
            del held[name]
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
    # A record whose time cannot be read may be the last before it, so none is read: what cannot be read is no information.
    if any(not isinstance(r, dict) or moment(r.get("now")) is None for r in before):
        return None
    last = [r for r in before if r["now"] < at]
    if not last:
        return None
    for e in last[-1].get("pull_requests", []):
        if key(e["facts"]["item"]) == key(item):
            return e["decision"].get("reason"), e.get("head")
    return None


def hand_approved(w: dict, before, heads: dict) -> bool:
    """Whether unmatched approval `w` is a hand approval: its pull request decided under `PERSON_WAITS` by the last pass record
    before it, at the commit it approved, and no other approval's key holding its head in `heads`; what cannot be read
    is none (decision 0241)."""
    commit = w.get("commit")      # read as a commit of a pull request before it is asked here
    found = decided(before, w["item"], w.get("at"))
    if found is None or found[0] not in PERSON_WAITS or found[1] != commit:
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
    hands, unjudged = _hands(seen, before) if readable else (set(), set())
    short = short or bool(unjudged)
    waved = []
    for w in seen["writes"] if readable else []:
        if w["by"] == HAND:
            # A person's write is no Run's: it is matched to the Kernel's act alone, whatever runs on its item.
            told = {"by": w["by"], "kind": w["kind"], "item": w["item"], "key": w["key"]}
            if _is_hands(w) and w["key"] in unjudged:
                waved.append(told)
            elif not _is_hands(w) or w["key"] not in hands:
                unmatched.append(told)
            continue
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
    # A carried hand approval stands; any other is judged in the order given, one to a head (decision 0241).
    carried_hand = {e["key"]: e for e in _last(before).get("hand", [])}
    # Each head an approval took, a hand one or any other, by the keys that took it, until the window passes its leaving.
    heads, seconds = {}, []
    for e in list(carried_hand.values()) + _last(before).get("taken", []):
        heads.setdefault((e["item"], e["head"]), set()).add(e["key"])
    of_head = [(w, entry) for w, entry in approvals if isinstance(w.get("commit"), str) and COMMIT.fullmatch(w["commit"])
               and isinstance(w["item"], dict) and w["item"].get("type") == "pull_request"]
    # Two approvals of a head in the same second cannot be told first and second: neither is a hand approval.
    ties = {}
    for w, _ in of_head:
        ties[(key(w["item"]), w["commit"], w["at"])] = ties.get((key(w["item"]), w["commit"], w["at"]), 0) + 1
    # Nor can a head one approval of which has a time that cannot be read.
    unordered = {(key(w["item"]), w["commit"]) for w, _ in of_head if moment(w["at"]) is None}
    taken = []
    # Read only from a whole read, every source of a short one counted: what cannot be read is never information.
    whole = not short
    for w, entry in sorted(of_head, key=lambda a: (a[0]["at"] if isinstance(a[0]["at"], str) else "", a[0]["key"] or "")):
        held = carried_hand.get(w["key"]) if w["key"] is not None else None
        alone = whole and entry is not None and ties[(key(w["item"]), w["commit"], w["at"])] == 1 \
            and (key(w["item"]), w["commit"]) not in unordered
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
            seconds.append({"item": w["item"], "key": w["key"], "head": w["commit"]})
    unmatched = [u for u in unmatched if not any(u is t for t in taken)]
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
    # An issue read whole by its 404 or 410 is named once, as information (decision 0235).
    gone = [g for g in seen.get("gone", []) if isinstance(g, dict)] if readable else []
    return {"unmatched": unmatched, "override": override, "unjudged": waved, "hand": hand, "taken": seconds,
            "short": short, "gone": gone}


def alerts(found: dict) -> list:
    """The alerts of a reconciliation: one for every unmatched write of an identity's however many (L-48), one of its
    own for every unmatched resolution by a hand, so that a hand's, which stands as long as its pull request is open,
    never hides an identity's (decision 0223), and one for a reconciliation that was short. An Override and a hand
    approval (decision 0241) are information, never an alert."""
    return sorted(({"write_unmatched"} if any(u["by"] != HAND for u in found["unmatched"]) else set())
                  | ({"hand_unmatched"} if any(u["by"] == HAND for u in found["unmatched"]) else set())
                  | ({"reconciliation_unreadable"} if found["short"] else set()))


def entries(found: dict) -> list:
    """What the view says of a reconciliation, ids and codes alone: each unmatched write, each Override, each hand
    approval, and each issue read whole by its 404 or 410, its answer as its key (decision 0235), once each, since two
    writes GitHub gives no key for read the same."""
    out = []
    for e in [{"alert": "hand_unmatched" if u["by"] == HAND else "write_unmatched", "by": u["by"], "write": u["kind"],
               "item": key(u["item"]) if u["item"] is not None else None, "key": u["key"]} for u in found["unmatched"]] \
            + [{"alert": "hand_unjudged", "by": u["by"], "write": u["kind"], "item": key(u["item"]), "key": u["key"]}
               for u in found.get("unjudged", [])] \
            + [{"alert": "merged_by_override", "by": None, "write": "merge", "item": key(o["item"]), "key": None}
               for o in found["override"]] \
            + [{"alert": "hand_approval", "by": "approver", "write": "approval", "item": key(h["item"]), "key": h["key"]}
               for h in found.get("hand", [])] \
            + [{"alert": "issue_gone", "by": None, "write": "other", "item": key(g["item"]), "key": str(g["answer"])}
               for g in found.get("gone", [])]:
        if e not in out:
            out.append(e)
    return out
