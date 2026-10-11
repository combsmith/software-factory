"""Builders for facts, run records and context, so each test states only what differs."""
from __future__ import annotations

import copy
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config" / "defaults.json").read_text())
ITEM = {"repo": "petry-projects/software-factory", "type": "pull_request", "number": 42}
NOW = "2026-10-11T13:00:00Z"
GREEN = [{"lens": name, "conclusion": "success"} for name in CONFIG["required_lenses"]["deterministic"]]


def facts(**over) -> dict:
    f = {
        "schema": "facts/1", "item": dict(ITEM), "state": "open", "is_draft": False,
        "class": "maintainer", "author": "don-petry", "last_pusher": "don-petry",
        "targets_protected": True, "mergeable": True, "content_id": "sha256:aaaa",
        "diff": {"files": 2, "lines": 40, "truncated": False}, "labels": [],
        "admitted_at": None, "last_push_at": "2026-10-11T12:00:00Z",
        "last_writer_action_at": "2026-10-11T12:00:00Z", "reviews": [], "threads": [],
        "checks": copy.deepcopy(GREEN), "queue": False,
        "complete": {"reviews": True, "threads": True, "checks": True, "diff": True},
        "read_at": "2026-10-11T12:59:00Z",
    }
    f.update(over)
    return f


def run(role="pr-review", intent="review-change", content="sha256:aaaa", status="completed",
        conclusion="success", outcome=None, at="2026-10-11T12:10:00Z", name="r1") -> dict:
    if status == "in_progress":
        conclusion = None
    return {"run": name, "item": dict(ITEM), "role": role, "intent": intent, "content_id": content,
            "status": status, "conclusion": conclusion, "outcome": outcome, "started_at": at}


def context(**over) -> dict:
    c = {"paused": False, "active_runs": 0, "model_deferred_until": None}
    c.update(over)
    return c


def thread(tid="T1", kind="lens", name="pr-review", can_write=True, severity="major", resolved=False,
           at="2026-10-11T12:15:00Z") -> dict:
    return {"id": tid, "resolved": resolved, "opened_by": {"kind": kind, "name": name, "can_write": can_write},
            "severity": severity, "resolved_by": None, "opened_at": at}


def config(**over) -> dict:
    c = copy.deepcopy(CONFIG)
    c.update(over)
    return c
