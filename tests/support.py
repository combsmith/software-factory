"""Builders for facts, run records and context, so each test states only what differs."""
from __future__ import annotations

import copy
import json
import os
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
# The configuration the Kernel is given: the defaults, and the Lifecycle whose staleness limits it reads.
CONFIG = dict(json.loads((ROOT / "config" / "defaults.json").read_text()),
              lifecycle=json.loads((ROOT / "lifecycle" / "pull_request.json").read_text()))
ITEM = {"repo": "combsmith/software-factory", "type": "pull_request", "number": 42}
NOW = "2026-10-11T13:00:00Z"
GREEN = [{"lens": name, "conclusion": "success", "completed_at": "2026-10-11T12:05:00Z"}
         for name in CONFIG["required_lenses"]["deterministic"]]


def pending(test):
    """Mark a rule that is decided and that the Kernel does not hold yet.

    Its test is written and expected to fail. When the rule is built the test passes, and that
    fails the run until this mark comes off and the rule gets its mutant. Under the mutation
    check these tests are skipped, so that none of them can be what notices a mutant.
    """
    if os.environ.get("MUTATING"):
        return unittest.skip("a pending rule is not part of the mutation check")(test)
    return unittest.expectedFailure(test)


def facts(**over) -> dict:
    f = {
        "schema": "facts/1", "item": dict(ITEM), "state": "open", "is_draft": False,
        "class": "maintainer", "author": "don-petry", "last_pusher": "don-petry",
        "targets_protected": True, "mergeable": True, "content_id": "sha256:aaaa",
        "diff": {"files": 2, "lines": 40, "truncated": False}, "labels": [],
        "admitted_at": None, "last_push_at": "2026-10-11T12:00:00Z",
        "last_writer_action_at": "2026-10-11T12:00:00Z", "reviews": [], "threads": [],
        "checks": copy.deepcopy(GREEN), "queue": False, "acts_since_writer": 0,
        "complete": {"reviews": True, "threads": True, "checks": True, "diff": True, "runs": True,
                     "timeline": True},
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
    """What the Controller knows beside the facts. The chain of passes starts at NOW, so no wait here is stale."""
    c = {"paused": False, "active_runs": 0, "model_deferred_until": None, "passes_since": NOW}
    c.update(over)
    return c


# Said for a thread's category to mean the one its kind of opener gives, so that None stays None.
BY_KIND = "by kind"


def thread(tid="T1", kind="lens", name="pr-review", can_write=True, severity="major", resolved=False,
           at="2026-10-11T12:15:00Z", category=BY_KIND) -> dict:
    """A thread as GitHub holds it. A person's is a `human` Finding; by default a Lens's is a `functional` one."""
    if category == BY_KIND:
        category = "human" if kind == "human" else "functional"
    return {"id": tid, "resolved": resolved, "opened_by": {"kind": kind, "name": name, "can_write": can_write},
            "category": category, "severity": severity, "resolved_by": None, "opened_at": at}


def review(state="approved", kind="lens", name="donpetry-bot", can_write=True, content="sha256:aaaa", commit="c1",
           at="2026-10-11T12:15:00Z", dismissed_by=None, dismissed_from=None) -> dict:
    """A review as GitHub holds it. By default, the approver's approval of this content."""
    return {"by": {"kind": kind, "name": name, "can_write": can_write}, "state": state, "commit": commit,
            "content_id": content, "submitted_at": at, "dismissed_by": dismissed_by, "dismissed_from": dismissed_from}


def config(**over) -> dict:
    c = copy.deepcopy(CONFIG)
    c.update(over)
    return c
