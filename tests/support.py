"""Builders for facts, run records and context, so each test states only what differs."""
from __future__ import annotations

import copy
import json
import os
import pathlib
import unittest

from tools.hooks import protected

ROOT = pathlib.Path(__file__).resolve().parent.parent
# The configuration the Kernel is given: the defaults, the Lifecycle whose staleness limits it reads, and the protected
# paths and Lenses' inputs, from the one list the session hooks read too.
CONFIG = dict(json.loads((ROOT / "config" / "defaults.json").read_text()),
              lifecycle=json.loads((ROOT / "lifecycle" / "pull_request.json").read_text()),
              protected_paths=protected.protected_paths())
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
# What a pull request changes by default: neither a protected path nor any Lens's input.
PATHS = ("docs/notes.md", "docs/glossary.md")
# The Maintainer: a person, which is an actor of kind human with write access, and nobody else is.
MAINTAINER = {"kind": "human", "name": "don-petry", "can_write": True}


def wall_clock(test):
    """Mark a test whose verdict rests on how long something takes, against the wall clock.

    Under load it can fail for its own reasons, so it is not one that may notice a mutant: under the mutation check it
    is skipped, as `pending` is. It still runs in `make verify`, with its margins as they are.
    """
    if os.environ.get("MUTATING"):
        return unittest.skip("a test timed by the wall clock is not part of the mutation check")(test)
    return test


def pending(test):
    """Mark a rule that is decided and that the Kernel does not hold yet.

    Its test is written and expected to fail. When the rule is built the test passes, and that
    fails the run until this mark comes off and the rule gets its mutant. Under the mutation
    check these tests are skipped, so that none of them can be what notices a mutant.
    """
    if os.environ.get("MUTATING"):
        return unittest.skip("a pending rule is not part of the mutation check")(test)
    return unittest.expectedFailure(test)


def facts(armed=True, **over) -> dict:
    """Facts for one pull request, with `over` in place of the defaults. Where `acceptance` is a contract a person
    approved, the facts also hold that person's approving review on the commit it names (armed), as GitHub does, unless
    `armed` is False: an approval with no such review is the port's word alone."""
    f = {
        "schema": "facts/1", "item": dict(ITEM), "state": "open", "is_draft": False,
        "class": "maintainer", "author": "don-petry", "last_pusher": "don-petry",
        "targets_protected": True, "mergeable": True, "content_id": "sha256:aaaa",
        "diff": {"files": 2, "lines": 40, "truncated": False}, "changed_paths": [changed(p) for p in PATHS],
        "label_events": [],
        "last_push_at": "2026-10-11T12:00:00Z",
        "last_writer_action_at": "2026-10-11T12:00:00Z", "reviews": [], "threads": [],
        "checks": copy.deepcopy(GREEN), "queue": False, "acts_since_writer": 0, "acceptance": None,
        "complete": {"acceptance": True, "reviews": True, "threads": True, "checks": True, "diff": True,
                     "changed_paths": True, "runs": True, "timeline": True},
        "read_at": "2026-10-11T12:59:00Z",
    }
    f.update(over)
    approval = arming(f["acceptance"]) if armed else None
    if approval is not None:
        f["reviews"] = [approval] + list(f["reviews"])
    return f


def arming(acceptance):
    """The review a person gave the acceptance contract they approved, on the commit it names, before the head was
    pushed and of earlier content: or None where `acceptance` names no person's approval."""
    approved = acceptance.get("approved") if isinstance(acceptance, dict) else None
    if not (isinstance(approved, dict) and isinstance(approved.get("by"), dict) and approved["by"].get("kind") == "human"
            and approved["by"].get("can_write") is True and isinstance(approved.get("commit"), str)
            and approved["commit"] != ""
            and not str(approved["by"].get("name")).endswith("[bot]")):
        return None
    by = approved["by"]
    return review(kind=by["kind"], name=by["name"], content=ARMED_CONTENT, commit=approved["commit"],
                  at="2026-10-11T11:00:00Z")


def changed(path, previous=None) -> dict:
    """One file the pull request changes: its path, and the path it had before a rename or a copy, or null."""
    return {"path": path, "previous": previous}


def run(role="pr-review", intent="review-change", content="sha256:aaaa", status="completed",
        conclusion="success", outcome=None, at="2026-10-11T12:10:00Z", name="r1") -> dict:
    if status == "in_progress":
        conclusion = None
    return {"run": name, "item": dict(ITEM), "role": role, "intent": intent, "content_id": content,
            "status": status, "conclusion": conclusion, "outcome": outcome, "started_at": at}


def context(**over) -> dict:
    """What the Controller knows beside the facts. The chain of passes starts at NOW, so no wait here is stale."""
    c = {"paused": False, "active_runs": 0, "model_deferred_until": None, "passes_since": NOW,
         "unidentified_runs": []}
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


# The digest of the acceptance contract and every path it protects (§3.13), in a content id's form: by default the one
# a person approved, and the one at the head.
DIGEST = "sha256:" + "c0de" * 16
# The commit a person approved the contract at, and its content: the first commit on the work's branch (§4.8).
COMMIT = "c0"
ARMED_CONTENT = "sha256:c0c0"
# The required deterministic Lens that reports a criterion of kind `test`, and its check, as a result carries it.
VERIFY = next(lens for lens in CONFIG["required_lenses"]["deterministic"]
              if lens["lens"] == CONFIG["acceptance_reporters"]["test"])
REPORTER = {"name": VERIFY["check"], "app_id": VERIFY["app_id"], "workflow": VERIFY["workflow"]}


def contract(criteria=("AC-1", "AC-2"), results=(), by=MAINTAINER, head=DIGEST) -> dict:
    """An item's acceptance contract as the facts carry it: the contract a person approved, its digest at the head, and
    each result read for a criterion. The approved contract gives each criterion by id and kind, never its statement: a
    criterion given by id alone is of kind `test`, and one given as (id, kind) is of that kind. By default, two
    criteria, which the Maintainer approved at DIGEST on COMMIT, unchanged at the head, and no results yet. `by` None: no person
    approved it. `head` None: the head carries none. Whether it was read in full is `complete.acceptance`."""
    listed = [{"id": c, "kind": "test"} if isinstance(c, str) else {"id": c[0], "kind": c[1]} for c in criteria]
    approved = None if by is None else {"digest": DIGEST, "commit": COMMIT, "by": dict(by), "criteria": listed}
    return {"approved": approved, "head": head, "results": [dict(e) for e in results]}


def evidence(criterion="AC-1", result="passing", content="sha256:aaaa", check=None) -> dict:
    """One result for one criterion, with the check that reported it. By default, AC-1 passing on this content, from
    the check of the Lens that reports a criterion of kind `test`."""
    return {"criterion": criterion, "content_id": content, "result": result,
            "check": dict(REPORTER if check is None else check)}


def config(**over) -> dict:
    c = copy.deepcopy(CONFIG)
    c.update(over)
    return c
