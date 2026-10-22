"""The approving act: the machine user approves one commit, from a Run with no Engine (design sections 3.6 and 3.10,
issue 195's rulings 4 to 7, decision 0055).

`job(...)` decides nothing itself, and each step that fails writes nothing:

1. Its Decision is read from the pass record by its own Run id, never from an input's text: an act issuing the
   approval, or the Run finds none and does nothing (`superseded`, `no_decision`; section 3.5).
2. The token must be the configuration's approver, a User: a token of anyone else approves nothing, the Maintainer's
   own included (`environment`, `approver_unreadable`).
3. The item is read again: its facts, the head commit its first read gave, the run records and the context, as the pass
   reads them. A pull request that changed while it was read is a change under the act (`superseded`, `head_moved`);
   one that cannot be read is the environment's (`facts_unreadable`).
4. The approver's approval of that commit, if it stands, is recovered by its node id and nothing is written: a re-run
   after an approval landed does not fail (section 3.6).
5. The Kernel is asked again on what was just read, with this Run left out (I-38), and the approval goes ahead only if
   `kernel.decide.still_wanted` says the Kernel still issues it for this content (`superseded`, `not_wanted`). So a
   Hold, a Pause, a close, new content, a Run in flight, a writer's gate, a wait for a person, a change to a model
   Lens's own inputs that no different person approved, and an approver now the author each stop it.
6. One review is posted through the effects port, the approval of the commit read, and read back by its id.

It records `applied/1` with one Effect, `approve`, and `outcome/1`: null on success, else whose fault and a code, never
`capacity`, since the act runs no model. Nothing here reads a clock, a file or the network: the job is handed the item
read again, `read()`, and the port the effects port's approval through the approver's own transport, `Port`. The step
that runs it, on `factory-approve` with the approver's token alone, lands with the approving workflow (#196).
"""
from __future__ import annotations

import re

from adapters import effects
from adapters.facts import Moved
from harness import shared
from kernel import terms as t
from kernel.decide import decide, still_wanted

SHA = re.compile(r"[0-9a-f]{40}")
APPROVAL = "issue_approval"


class Port:
    """The effects port's approval through the approver's own token, as the job asks it. Each step narrows the token's
    transport to what it may send, `effects.Approving`: who the token is; then the item's reads; and the approval of the
    commit the job just read, which only this step may write (decision 0055)."""

    def __init__(self, transport, login: str):
        self._transport, self._login = transport, login

    def whoami(self) -> dict:
        return effects.approver_of(effects.Approving(self._transport))

    def recover(self, item: dict, head: str) -> dict:
        return effects.approval_of(effects.Approving(self._transport, item), item, head, self._login)

    def approve(self, item: dict, head: str) -> dict:
        return effects.approve(effects.Approving(self._transport, item, head), item, head, self._login)


def decision_of(record, run: str):
    """The Decision of the pass record's one entry with Run id `run`, if it is an act issuing the approval, or None."""
    if not isinstance(record, dict) or shared.errors(record, "pass"):
        return None
    found = [e for e in record["pull_requests"] if e["run"] == run]
    if len(found) != 1:
        return None
    decided = found[0]["decision"]
    return decided if decided["outcome"] == t.ACT and decided.get("action") == APPROVAL else None


def _left_out(runs: list, context: dict, run: str, github_run) -> tuple:
    """The run records and the context with this Run left out: of the records, where a Run in flight would admit
    nothing, and of the Runs listed before their name by its own GitHub run id, which would defer it (decision 0036).
    The count of active Runs defers model Runs alone, so an approval leaves it as read."""
    others = [r for r in runs if r.get("run") != run]
    if isinstance(context.get("unidentified_runs"), list):
        context = dict(context, unidentified_runs=[u for u in context["unidentified_runs"]
                                                   if not (isinstance(u, dict) and u.get("run") == github_run)])
    return others, context


def _records(run: str, release: str, state: str, key, why) -> tuple:
    """`(applied/1, outcome/1)`: the one Effect as it ended, and whose fault it was, or null on success."""
    fault, reason = why if why is not None else (None, None)
    done = {"schema": "applied/1", "run": run, "release": release,
            "effects": [{"id": "e1", "type": "approve", "state": state, "key": key, "reason": reason}], "findings": []}
    ended = {"schema": "outcome/1", "run": run, "release": release, "outcome": fault, "reason": reason}
    return done, ended


def job(record, run: str, read, port, config: dict, now: str) -> tuple:
    """`(applied/1, outcome/1)` for the approving act of Run `run`. `read()` is the item read again, `(facts, head,
    runs, context)`; `port` the effects port's approval through the approver's own transport; `config` the approver's
    login, the Kernel's configuration, the job's own GitHub run id and the Release."""
    decided = decision_of(record, run)
    if decided is None:
        return _records(run, config["release"], "refused", None, ("superseded", "no_decision"))
    release = record["release"]
    item = decided["item"]
    me = port.whoami()
    if me["fault"] is not None:
        return _records(run, release, "refused", None, (me["fault"], me["reason"]))
    if me["login"] != config["approver"] or me["type"] != "User":
        return _records(run, release, "refused", None, ("environment", "approver_unreadable"))
    try:
        facts, head, runs, context = read()
    except Moved:
        return _records(run, release, "refused", None, ("superseded", "head_moved"))
    except Exception:     # any read that failed is the environment's, never a Run that died with no outcome (ruling 6)
        return _records(run, release, "refused", None, ("environment", "facts_unreadable"))
    # A Pause that cannot be read is a read that failed: the environment's, not a change under the act.
    if not isinstance(facts, dict) or not isinstance(head, str) or SHA.fullmatch(head) is None \
            or not isinstance(runs, list) \
            or not isinstance(context, dict) or context.get("paused") not in (True, False):
        return _records(run, release, "refused", None, ("environment", "facts_unreadable"))
    done = port.recover(item, head)
    if done["fault"] is not None:
        return _records(run, release, "refused", None, (done["fault"], done["reason"]))
    if done["state"] == "already_applied":
        return _records(run, release, "already_applied", done["key"], None)
    others, context = _left_out(runs, context, run, config["github_run"])
    if not still_wanted(decided, decide(facts, others, context, config["kernel"], now)):
        return _records(run, release, "refused", None, ("superseded", "not_wanted"))
    back = port.approve(item, head)
    return _records(run, release, back["state"], back["key"],
                    None if back["fault"] is None else (back["fault"], back["reason"]))
