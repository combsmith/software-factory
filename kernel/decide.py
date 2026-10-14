"""Admission: what, if anything, happens next on one pull request.

decide(facts, runs, context, config, now) -> Decision. No I/O, no clock.
Times are UTC, to the second, in one text format, and compare as text.
"""
from __future__ import annotations

from kernel import terms as t
from kernel.derive import derive, in_progress, runs_on, since_writer

SCHEMA = "decision/1"

NEEDS_YOU_REASONS = frozenset({
    "human_hold", "outside_not_admitted", "empty_diff", "too_large", "human_finding",
    "attempts_exhausted", "run_ceiling", "max_rounds", "approver_is_author_or_last_pusher",
    "awaiting_human",
})


def _attention(state, reason, working: bool) -> str:
    if state is None:
        return t.NONE
    if working:
        return t.WORKING
    if reason in NEEDS_YOU_REASONS:
        return t.NEEDS_YOU
    if state in t.TERMINAL or state == t.DRAFT or reason == "hands_off":
        return t.NONE
    if state == t.ADDRESSING:
        return t.FAILED
    if state in (t.VERIFYING, t.ADJUDICATING):
        return t.REVIEW
    return t.READY


def _decision(facts, state, reason, evidence, outcome, working=False, **extra) -> dict:
    d = {
        "schema": SCHEMA,
        "item": facts["item"],
        "state": state,
        "reason": reason,
        "evidence": list(evidence),
        "attention": _attention(state, reason, working),
        "outcome": outcome,
    }
    d.update(extra)
    return d


def _pause(context: dict):
    """Why a Pause stops this act, or None. It stops every act; one that cannot be read, too."""
    if context.get("paused") is False:
        return None
    return "paused" if context.get("paused") else "pause_unreadable"


def _wanted_run(state: str, reason: str, config: dict):
    """The Run this State calls for, as (role, intent), or None."""
    if state == t.VERIFYING and reason == "awaiting_review":
        return (config["required_lenses"]["model"][0], "review-change")
    if state == t.ADDRESSING and reason in ("check_failed", "findings_open", "human_finding", "conflict"):
        if config["author_role"] is None:
            return None
        return (config["author_role"], "fix-findings")
    if state == t.ADJUDICATING:
        return (config["owner_role"], "adjudicate-findings")
    return None


def decide(facts: dict, runs: list, context: dict, config: dict, now: str) -> dict:
    d = derive(facts, runs, config)
    state, reason, evidence = d["state"], d["reason"], d["evidence"]

    # Fail to a deferral, never to an action.
    if state is None:
        return _decision(facts, None, reason, evidence, t.DEFER)
    if state in t.TERMINAL or state in (t.DRAFT, t.QUEUED):
        return _decision(facts, state, reason, evidence, t.NOTHING)
    if state == t.HELD:
        return _decision(facts, state, reason, evidence, t.HOLD)

    mine = runs_on(runs, facts)
    if in_progress(mine):
        return _decision(facts, state, reason, evidence, t.NOTHING, working=True)

    if state == t.CONVERGED:
        if config["approver"] in (facts["author"], facts["last_pusher"]):
            return _decision(facts, t.HELD, "approver_is_author_or_last_pusher", [], t.HOLD)
        # The Hold the facts establish first, then the Pause; neither approves. The order is open.
        pause = _pause(context)
        if pause:
            return _decision(facts, state, pause, evidence, t.DEFER)
        action = "enqueue" if reason == "approved" else "issue_approval"
        return _decision(facts, state, reason, evidence, t.ACT, action=action,
                         content_id=facts["content_id"])

    wanted = _wanted_run(state, reason, config)
    if wanted is None:
        return _decision(facts, state, reason, evidence, t.NOTHING)
    role, intent = wanted

    # Brakes and ceilings on a Run, in one place. The Pause stops an approval above, too.
    pause = _pause(context)
    if pause:
        return _decision(facts, state, pause, evidence, t.DEFER)
    limits = config["limits"]
    recent = since_writer(mine, facts)
    attempts = [r for r in recent if r["intent"] == intent and r["status"] == "completed"
                and r["conclusion"] != "success" and r.get("outcome") == "item"]
    if len(attempts) >= limits["max_attempts"]:
        return _decision(facts, t.HELD, "attempts_exhausted", [r["run"] for r in attempts], t.HOLD)
    if intent == "adjudicate-findings":
        rounds = [r for r in recent if r["intent"] == intent and r["status"] == "completed"]
        if len(rounds) >= limits["max_rounds"]:
            return _decision(facts, t.HELD, "max_rounds", evidence, t.HOLD)
    if len(recent) >= limits["max_runs_per_item"]:
        return _decision(facts, t.HELD, "run_ceiling", [], t.HOLD)

    until = context.get("model_deferred_until", "unreadable")
    if until == "unreadable":
        return _decision(facts, state, "capacity_unreadable", evidence, t.DEFER)
    if until is not None and until > now:
        return _decision(facts, state, "capacity", evidence, t.DEFER)
    active = context.get("active_runs")
    if active is None:
        return _decision(facts, state, "capacity_unreadable", evidence, t.DEFER)
    if active >= limits["org_max_active_runs"]:
        return _decision(facts, state, "concurrency", evidence, t.DEFER)

    return _decision(facts, state, reason, evidence, t.ADMIT,
                     admit={"role": role, "intent": intent, "content_id": facts["content_id"]})
