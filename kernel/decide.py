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
    "awaiting_human", "act_ceiling", "check_unreadable", "review_unreadable",
})


def _attention(state, reason, working: bool) -> str:
    # An unreadable fact that does not mend itself, such as a review, needs a person even with no State.
    if state is None and reason not in NEEDS_YOU_REASONS:
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


def _attempts(recent: list, intent: str) -> list:
    """Runs of this Intent that failed by a fault of the item. Only those are attempts (I-23)."""
    return [r for r in recent if r["intent"] == intent and r["status"] == "completed"
            and r["conclusion"] != "success" and r.get("outcome") == "item"]


def _spent(recent: list) -> list:
    """The Runs that count toward the Run ceiling: every Run but an approval that landed.

    A landed approval spends no model and is counted as an act. One that did not land, whatever
    the fault, never reaches the timeline, so the Run ceiling is what bounds it: an approval
    failing for a cause outside the item, such as an expired token, is not issued for ever.
    """
    return [r for r in recent if not (r["intent"] == t.ISSUE_APPROVAL and r["conclusion"] == "success")]


def _act(facts: dict, state: str, reason: str, evidence: list, mine: list, config: dict) -> dict:
    """An act that moves work on, bounded.

    An approval is a Run with no Engine: its attempts, and the Run ceiling, bound one that does not
    land. Every act that lands is on GitHub's timeline, counted since a writer acted, and the count
    is held to the act ceiling. An act that stops work is not decided here: it is never refused.
    """
    limits = config["limits"]
    action = "enqueue" if reason == "approved" else "issue_approval"
    if action == "issue_approval":
        since = since_writer(mine, facts)
        failed = _attempts(since, t.ISSUE_APPROVAL)
        if len(failed) >= limits["max_attempts"]:
            return _decision(facts, t.HELD, "attempts_exhausted", [r["run"] for r in failed], t.HOLD)
        if len(_spent(since)) >= limits["max_runs_per_item"]:
            return _decision(facts, t.HELD, "run_ceiling", [], t.HOLD)
    acts = facts.get("acts_since_writer")
    if type(acts) is not int or acts < 0:
        return _decision(facts, state, "acts_unreadable", evidence, t.DEFER)
    if acts >= limits["max_acts_per_item"]:
        return _decision(facts, t.HELD, "act_ceiling", [], t.HOLD)
    return _decision(facts, state, reason, evidence, t.ACT, action=action, content_id=facts["content_id"])


def decide(facts: dict, runs: list, context: dict, config: dict, now: str) -> dict:
    d = derive(facts, runs, config)
    state, reason, evidence = d["state"], d["reason"], d["evidence"]

    # An act that stops work, read first: a Hold, a failed read or a draft takes a queued item out too (FR-23,
    # I-13). It is counted, never refused at the act ceiling, and not delayed by a Run in progress. Only a Pause
    # stops it, as it stops every act (decision 0003); then only the Maintainer can stop the merge.
    if d.get("dequeue"):
        paused = _pause(context)
        if paused:
            return _decision(facts, state, paused, evidence, t.DEFER, attention=t.NEEDS_YOU)
        return _decision(facts, state, reason, evidence, t.ACT, action="dequeue", content_id=facts["content_id"])
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
        # A Hold the facts establish, such as an approver who is the author, was read above; then the Pause.
        pause = _pause(context)
        if pause:
            return _decision(facts, state, pause, evidence, t.DEFER)
        return _act(facts, state, reason, evidence, mine, config)

    # A required check that gave no verdict is unreadable: admit nothing, and wait for a person (I-13).
    if reason == "check_unreadable":
        return _decision(facts, state, reason, evidence, t.DEFER)
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
    attempts = _attempts(recent, intent)
    if len(attempts) >= limits["max_attempts"]:
        return _decision(facts, t.HELD, "attempts_exhausted", [r["run"] for r in attempts], t.HOLD)
    if intent == "adjudicate-findings":
        rounds = [r for r in recent if r["intent"] == intent and r["status"] == "completed"]
        if len(rounds) >= limits["max_rounds"]:
            return _decision(facts, t.HELD, "max_rounds", evidence, t.HOLD)
    # The Run ceiling is the cost ceiling (FR-39). A landed approval spent no model, and is counted as an act.
    if len(_spent(recent)) >= limits["max_runs_per_item"]:
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
