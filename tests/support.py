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
# Every required check passing, each under its check run's name as GitHub gives it, from its Lens's own App.
# A check GitHub Actions runs carries the workflow file that ran it; one no workflow ran carries null.
GREEN = [{"name": lens["check"], "app_id": lens["app_id"], "workflow": lens["workflow"], "conclusion": "success",
          "completed_at": "2026-10-11T12:05:00Z"} for lens in CONFIG["required_lenses"]["deterministic"]]
# The Lens each required check reports for, by the check run's name: the name a Decision gives as evidence.
LENS_OF = {lens["check"]: lens["lens"] for lens in CONFIG["required_lenses"]["deterministic"]}
# An App no required Lens is read from: any App with checks: write, the Controller's among them, can post a check.
OTHER_APP = 1000001
# A workflow file no required Lens is read from: GitHub Actions runs every job in the repo, under any name, one a pull
# request adds on its own branch among them.
OTHER_WORKFLOW = ".github/workflows/impostor.yml"
# The Maintainer: a person, which is an actor of kind human with write access, and nobody else is.
MAINTAINER = {"kind": "human", "name": "don-petry", "can_write": True}


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
        "diff": {"files": 2, "lines": 40, "truncated": False}, "label_events": [],
        "last_push_at": "2026-10-11T12:00:00Z",
        "last_writer_action_at": "2026-10-11T12:00:00Z", "reviews": [], "threads": [],
        "checks": copy.deepcopy(GREEN), "queue": False, "acts_since_writer": 0, "acceptance": None,
        "complete": {"acceptance": True, "reviews": True, "threads": True, "checks": True, "diff": True, "runs": True,
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
# Said for who resolved a thread to mean whoever opened it.
BY_OPENER = "by opener"


def thread(tid="T1", kind="lens", name="pr-review", can_write=True, severity="major", resolved=False,
           at="2026-10-11T12:15:00Z", category=BY_KIND, resolved_by=BY_OPENER) -> dict:
    """A thread as GitHub holds it. A person's is a `human` Finding; by default a Lens's is a `functional` one.

    A resolved thread says who resolved it, by default whoever opened it; an open one says nobody.
    """
    if category == BY_KIND:
        category = "human" if kind == "human" else "functional"
    opener = {"kind": kind, "name": name, "can_write": can_write}
    if resolved_by == BY_OPENER:
        resolved_by = dict(opener) if resolved else None
    return {"id": tid, "resolved": resolved, "opened_by": opener, "category": category, "severity": severity,
            "resolved_by": resolved_by, "opened_at": at}


def labelled(label: str, by=None, at="2026-10-11T12:01:00Z", action="labeled") -> dict:
    """A label event from the timeline. By default the Maintainer adds `label`, a minute after the push."""
    return {"label": label, "action": action, "by": dict(MAINTAINER if by is None else by), "at": at}


def unlabelled(label: str, by=None, at="2026-10-11T12:02:00Z") -> dict:
    """`label` removed. By default by the Maintainer, a minute after `labelled` adds it."""
    return labelled(label, by, at, "unlabeled")


def review(state="approved", kind="machine_user", name="donpetry-bot", can_write=True, content="sha256:aaaa",
           commit="c1", at="2026-10-11T12:15:00Z", dismissed_by=None, dismissed_from=None) -> dict:
    """A review as GitHub holds it. By default, the approver's approval of this content: the machine user's."""
    return {"by": {"kind": kind, "name": name, "can_write": can_write}, "state": state, "commit": commit,
            "content_id": content, "submitted_at": at, "dismissed_by": dismissed_by, "dismissed_from": dismissed_from}


def contract(criteria=("AC-1", "AC-2"), results=()) -> dict:
    """An item's acceptance contract as the facts carry it: its criteria by id, never their statements, and each result
    read for one, with the content it was given on. By default, two criteria and no results yet. Whether it was read in
    full is `complete.acceptance`."""
    return {"criteria": list(criteria), "results": [dict(e) for e in results]}


def evidence(criterion="AC-1", result="passing", content="sha256:aaaa") -> dict:
    """One result for one criterion. By default, AC-1 passing on this content."""
    return {"criterion": criterion, "content_id": content, "result": result}


def config(**over) -> dict:
    c = copy.deepcopy(CONFIG)
    c.update(over)
    return c
