"""The writes one pass plans, `writes/1`, from what the pass returned: pure, as `pass_.py` is. It reads no clock and
reaches nothing; `adapters/effects.py` sends them (#193's rulings for PR 2).

The order is the one they are sent in: first the acts no write serves yet, each recorded `not_built` (a dequeue's
place, ruling 5's first, comes with its write); then the dispatches of Runs and approvals, in the record's item order,
so that a Run waits for a runner from as early as it can; then the tracking issue, one each pass keeps, last but one so
that it can say a write before it failed; and last the successor, so that the next pass starts after this one's
writes. The status on the item takes its place before the tracking issue when its write is built.
"""
from __future__ import annotations

from kernel import terms as t

from controller.shared import checked


def plan(out: dict) -> dict:
    """`writes/1` for the pass `pass_.run` returned as `out`."""
    record = out["record"]
    runs = {e["run"]: e["decision"] for e in record["pull_requests"] + record["issues"] if e["run"] is not None}
    writes = []

    def add(kind: str, item, run=None, name=None, action=None):
        writes.append({"id": "w%d" % (len(writes) + 1), "type": kind, "item": item, "run": run, "name": name,
                       "action": action})

    for act in out["acts"]:
        add("not_built", act["item"], action=act["action"])
    for dispatch in out["dispatch"]:
        decision = runs[dispatch["run"]]
        kind = "dispatch_run" if decision["outcome"] == t.ADMIT else "dispatch_approval"
        add(kind, decision["item"], dispatch["run"], dispatch["name"])
    add("tracking_issue", None)
    if out["successor"]:
        add("dispatch_successor", None)
    return checked({"schema": "writes/1", "pass": record["pass"], "release": record["release"], "writes": writes},
                   "writes")
