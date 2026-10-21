"""The Kernel's half of the brakes (decision 0003): Admission refuses at a ceiling or under a Pause.

The human Pause, the Run ceiling and the loop counts are evaluated here and nowhere else, and decide.py asks them before
every act and Run. Design §2.2's Brakes, outside `kernel/` and holding when Factory code is broken, wait on
`controller/`. Each brake is given `_decision`, Admission's maker of a Decision, and gives the deferral or the Hold it
makes, or None when it lets the act or the Run through. A brake works out no State and imports nothing of the Kernel
but its codes (tools/check_purity.py). Every limit is read from `config`.
"""
from __future__ import annotations

from kernel import terms as t


def paused(_decision, facts, state, evidence, context: dict, **extra):
    """The deferral a Pause makes of this act, or None. It stops every act; one that cannot be read, too."""
    if context.get("paused") is False:
        return None
    if context.get("paused"):
        return _decision(facts, state, "paused", evidence, t.DEFER, **extra)
    return _decision(facts, state, "pause_unreadable", evidence, t.DEFER, **extra)


def _attempts(recent: list, intent: str) -> list:
    """Runs of this Intent that failed by a fault of the item. Only those are attempts (I-23). A Run that ran and left
    no outcome, failed or timed out, is the item's: killed, out of memory or crashed in its own step, it is the loop the
    attempts bound. One cancelled, by a person or its concurrency group, with no outcome is none, and so is a job that
    never started, which the records port reads as cancelled (issue 286's ruling)."""
    return [r for r in recent if r["intent"] == intent and r["status"] == "completed" and r["conclusion"] != "success"
            and (r.get("outcome") == "item" or (r.get("outcome") is None and r["conclusion"] in t.RAN_AND_DIED))]


def _spent(recent: list) -> list:
    """The Runs that count toward the Run ceiling: every Run but an approval that landed.

    A landed approval spends no model and is counted as an act. One that did not land, whatever
    the fault, never reaches the timeline, so the Run ceiling is what bounds it: an approval
    failing for a cause outside the item, such as an expired token, is not issued for ever.
    """
    return [r for r in recent if not (r["intent"] == t.ISSUE_APPROVAL and r["conclusion"] == "success")]


def on_act(_decision, facts: dict, state: str, evidence: list, context: dict, action: str, since: list,
           limits: dict):
    """The deferral or Hold the brakes make of an act that moves work on, or None.

    An approval is a Run with no Engine: its attempts, and the Run ceiling, bound one that does not land. Every act that
    lands is on GitHub's timeline, counted since a writer acted, and the count is held to the act ceiling. A count
    spent holds the item before the Pause is read: a Hold is a reading and no act, and a Pause changes none (issue 169).
    The Pause then stops the act, and a count of acts that cannot be read defers it. An act that stops work is not
    braked here: it is never refused, and only the Pause stops it.
    """
    if action == "issue_approval":
        held = approval_ceilings(_decision, facts, since, limits)
        if held:
            return held
    acts = facts.get("acts_since_writer")
    readable = type(acts) is int and acts >= 0
    if readable and acts >= limits["max_acts_per_item"]:
        return _decision(facts, t.HELD, "act_ceiling", [], t.HOLD)
    stopped = paused(_decision, facts, state, evidence, context)
    if stopped:
        return stopped
    if not readable:
        return _decision(facts, state, "acts_unreadable", evidence, t.DEFER)
    return None


def on_run(_decision, facts: dict, state: str, evidence: list, context: dict, intent: str, recent: list,
           limits: dict):
    """The deferral or Hold the brakes make of a Run of this Intent, or None.

    Its attempts, its rounds and the Run ceiling stop it, and then the Pause: a count spent holds the item under a Pause
    as without one, since a Hold is a reading and no act (issue 169). `recent` is the Runs on the item since a person
    with write access acted, whose action renews every count.
    """
    held = run_ceilings(_decision, facts, evidence, intent, recent, limits)
    if held:
        return held
    pause = paused(_decision, facts, state, evidence, context)
    if pause:
        return pause
    return None


def approval_ceilings(_decision, facts: dict, since: list, limits: dict):
    """The Hold an approval meets at its attempts or the Run ceiling, or None. No deferral is read here."""
    failed = _attempts(since, t.ISSUE_APPROVAL)
    if len(failed) >= limits["max_attempts"]:
        return _decision(facts, t.HELD, "attempts_exhausted", [r["run"] for r in failed], t.HOLD)
    if len(_spent(since)) >= limits["max_runs_per_item"]:
        return _decision(facts, t.HELD, "run_ceiling", [], t.HOLD)
    return None


def run_ceilings(_decision, facts: dict, evidence: list, intent: str, recent: list, limits: dict):
    """The Hold a Run of this Intent meets at its attempts, its rounds or the Run ceiling, or None. No deferral is read
    here: decide.py asks it alone while a Run is in flight, when a spent count holds the item whatever would defer."""
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
    return None
