"""The queue act: one enqueue, dequeue or set of resolutions, by the queue App, from a Run with no Engine (issue 381,
decision 0130). It decides nothing itself, and each step that fails writes nothing:

1. Its Decision is read from the pass record by its own Run id, never from an input's text: an act the queue App makes,
   or the Run finds none and does nothing (`superseded`, `no_decision`).
2. A Pause the job reads, the repo's or org's `FACTORY_PAUSED` as GitHub's `vars` context gives the most specific of
   them, stops it unless it is exactly unset or `false` (`superseded`, `paused`). The pass read every scope just before
   it dispatched the act; this read sees a Pause set since, where the repo sets none of its own.
3. The pull request is read again with the queue App's own token, which reads it and its threads and nothing else
   (decision 0130's ruling A): an enqueue and a dequeue are made only while it is open at the head the pass read beside
   the Decision (`superseded`, `closed_under_act` or `head_moved`), and the enqueue is bound to that head by
   `expectedHeadOid`, which GitHub refuses once the head moved (trials/P-57.json). What is already done is recovered
   and nothing is written: an enqueue of a pull request in the merge queue, a dequeue of one not in it, a resolution
   of a thread resolved. A resolution is made only while every thread the Decision names is still there, and stops at
   its first write that fails.
4. Each write is sent once and read back (adapters/queue.py).

The Kernel is not asked again, as the approving act asks it (I-38): the queue App reads no more than the pull request
and its threads, so a Hold placed between the pass and the job is not seen. An enqueue can be dequeued, and a resolution
closes only on the Lens's accepted ruling or decision 0125's supersession. It records `applied/1`, an Effect for each
write, and `outcome/1`: null on success, else the first fault and its code, never `capacity`, since the act runs no
model. Nothing here reads a clock, a file or the network: the job is handed the port through the queue App's token."""
from __future__ import annotations

from adapters import queue as queue_
from controller.writes import QUEUE_INTENTS
from harness import shared
from kernel import terms as t

NOT_PAUSED = ("", "false")


class Port:
    """The queue App's writes through its own token, each narrowed to the item by `adapters.queue.Queuing`."""

    def __init__(self, transport, item: dict, login: str):
        self._transport, self._item, self._login = queue_.Queuing(transport, item), dict(item), login

    def pull(self) -> dict:
        return queue_.pull(self._transport, self._item)

    def enqueue(self, node: str, head: str) -> dict:
        return queue_.enqueue(self._transport, self._item, node, head)

    def dequeue(self, node: str) -> dict:
        return queue_.dequeue(self._transport, node)

    def threads(self) -> dict:
        return queue_.threads(self._transport, self._item)

    def queued(self) -> dict:
        return queue_.queued(self._transport, self._item)

    def resolve(self, thread: str) -> dict:
        return queue_.resolve(self._transport, thread, self._login)


def decision_of(record, run: str):
    """`(Decision, head)` of the pass record's one pull request entry with Run id `run`, if it is an act the queue App
    makes, or None. The head is the commit the pass read beside the facts, or None where it carried none."""
    if not isinstance(record, dict) or shared.errors(record, "pass"):
        return None
    found = [e for e in record["pull_requests"] if e["run"] == run]
    if len(found) != 1:
        return None
    decided = found[0]["decision"]
    if decided["outcome"] != t.ACT or decided.get("action") not in QUEUE_INTENTS:
        return None
    return decided, found[0].get("head")


def _records(run: str, release: str, kind: str, effects: list, why) -> tuple:
    """`(applied/1, outcome/1)`: each Effect as it ended, at least one, and whose fault it was, or null on success."""
    effects = effects or [{"state": "refused", "key": None, "reason": why[1] if why else None}]
    done = {"schema": "applied/1", "run": run, "release": release, "findings": [], "rulings": [],
            "effects": [{"id": "e%d" % (n + 1), "type": kind, "state": e["state"], "key": e["key"], "reason": e["reason"]}
                        for n, e in enumerate(effects)]}
    fault, reason = why if why is not None else (None, None)
    ended = {"schema": "outcome/1", "run": run, "release": release, "outcome": fault, "reason": reason}
    return done, ended


def job(record, run: str, port, config: dict) -> tuple:
    """`(applied/1, outcome/1)` for the queue act of Run `run`. `port` is the queue App's writes; `config` the Release,
    the act its run-name names and the Pause as the job's `vars` gave it."""
    found = decision_of(record, run)
    if found is None:
        return _records(run, config["release"], config["kind"], [], ("superseded", "no_decision"))
    decided, head = found
    release, kind = record["release"], decided["action"]
    if config.get("paused") not in NOT_PAUSED:
        return _records(run, release, kind, [], ("superseded", "paused"))
    if kind == "resolve_thread":
        return _resolve(run, release, decided, port)
    if not isinstance(head, str) or queue_.SHA.fullmatch(head) is None:
        return _records(run, release, kind, [], ("superseded", "head_unknown"))
    read = port.pull()
    if read["fault"] is not None:
        return _records(run, release, kind, [], (read["fault"], read["reason"]))
    if not read["open"]:
        return _records(run, release, kind, [], ("superseded", "closed_under_act"))
    if read["head"] != head:
        return _records(run, release, kind, [], ("superseded", "head_moved"))
    member = port.queued()
    if member["fault"] is not None:
        return _records(run, release, kind, [], (member["fault"]["fault"], member["fault"]["reason"]))
    if member["queued"] == (kind == "enqueue"):
        return _records(run, release, kind, [{"state": "already_applied", "key": read["node"], "reason": None}], None)
    back = port.enqueue(read["node"], head) if kind == "enqueue" else port.dequeue(read["node"])
    return _records(run, release, kind, [back], None if back["fault"] is None else (back["fault"], back["reason"]))


def _resolve(run: str, release: str, decided: dict, port) -> tuple:
    """Each thread the Decision names, resolved by the queue App unless GitHub already shows it resolved. Nothing is
    written unless every one is still there, and nothing after the first write that fails: a Run that fails counts
    toward the Run ceiling, never as an act, so a resolution it landed before failing is bounded there alone."""
    if not decided["evidence"]:
        return _records(run, release, "resolve_thread", [], ("superseded", "no_decision"))
    read = port.threads()
    if read["fault"] is not None:
        return _records(run, release, "resolve_thread", [], (read["fault"]["fault"], read["fault"]["reason"]))
    if any(thread not in read["threads"] for thread in decided["evidence"]):
        return _records(run, release, "resolve_thread", [], ("superseded", "thread_gone"))
    effects = []
    for thread in decided["evidence"]:
        if read["threads"][thread]:
            back = {"state": "already_applied", "key": thread, "fault": None, "reason": None}
        else:
            back = port.resolve(thread)
        effects.append(back)
        if back["fault"] is not None:
            return _records(run, release, "resolve_thread", effects, (back["fault"], back["reason"]))
    return _records(run, release, "resolve_thread", effects, None)
