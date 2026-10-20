"""Admission: what, if anything, happens next on one pull request.

decide(facts, runs, context, config, now) -> Decision. No I/O, no clock.
Times are UTC, to the second, in one text format. They compare as text, and the Kernel counts
the seconds between two itself, from the pinned calendar in terms.py.
"""
from __future__ import annotations

from kernel import brakes
from kernel import terms as t
from kernel.derive import derive, in_progress, is_time, moved_at, overdue, runs_on, since_writer

SCHEMA = "decision/1"

WORK_ITEM = "pull_request"      # the Lifecycle this module reads, lifecycle/pull_request.json
NEEDS_YOU_REASONS = frozenset({
    "human_hold", "outside_not_admitted", "empty_diff", "too_large", "human_finding",
    "attempts_exhausted", "run_ceiling", "max_rounds", "approver_is_author_or_last_pusher",
    "awaiting_human", "act_ceiling", "check_unreadable", "review_unreadable", "thread_unreadable", "label_unreadable",
    "acceptance_unreadable", "paths_unreadable", "protected_paths_unreadable",
    "contract_not_approved", "contract_changed", "acceptance_reporters_unreadable",
    "run_unreadable",
})


def _attention(state, reason, working: bool) -> str:
    # An unreadable fact that does not mend itself, such as a review, needs a person even with no State.
    if state is None and reason not in NEEDS_YOU_REASONS:
        return t.NONE
    if working:
        return t.WORKING
    if reason in NEEDS_YOU_REASONS:
        return t.NEEDS_YOU
    if state in t.ADMITS_NOTHING or state == t.DRAFT or reason == "hands_off":
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


def _wanted_run(state: str, reason: str, config: dict):
    """The Run this State calls for, as (role, intent), or None."""
    if state == t.VERIFYING and reason == "awaiting_review":
        return (config["required_lenses"]["model"][0], "review-change")
    if state == t.ADDRESSING and reason in ("check_failed", "findings_open", "human_finding", "conflict",
                                              "acceptance_failed"):
        if config["author_role"] is None:
            return None
        return (config["author_role"], "fix-findings")
    if state == t.ADJUDICATING:
        return (config["owner_role"], "adjudicate-findings")
    return None


def _action(reason: str) -> str:
    """The act that moves a converged item on."""
    return "enqueue" if reason == "approved" else "issue_approval"


def _act(facts: dict, state: str, reason: str, evidence: list, mine: list, context: dict, config: dict) -> dict:
    """An act that moves work on, once the brakes let it through. An act that stops work is not decided here."""
    action = _action(reason)
    since = since_writer(mine, facts)
    brake = brakes.on_act(_decision, facts, state, evidence, context, action, since, config["limits"])
    if brake:
        return brake
    # An approval is a Run, so a Run that cannot be told whose it is defers it. An enqueue admits none (decision 0036).
    if action == "issue_approval" and context.get("unidentified_runs") != []:
        return _decision(facts, state, "run_unidentified", evidence, t.DEFER)
    return _decision(facts, state, reason, evidence, t.ACT, action=action, content_id=facts["content_id"])


def decide(facts: dict, runs: list, context: dict, config: dict, now: str) -> dict:
    """Return the Decision for one pull request: what, if anything, happens next on it. No I/O, no clock."""
    # A context that cannot be read says nothing: not whether the Pause holds, which the brakes then read as
    # unreadable and defer every act and Run, nor the passes, as an unreadable `passes_since` does not.
    known = context if isinstance(context, dict) else {}
    d = _decide(facts, runs, known, config, now)
    # A wait past its State's limit, while passes ran, is the Maintainer's to see. Only what they see changes (I-1).
    # A deferral that holds the whole scope is one cause, reported once (§4.6): the item keeps the attention it had.
    # A Lifecycle, a limit or a `now` that cannot be read shows the wait as stale, and raises nothing.
    if (d["attention"] in t.MAY_GO_STALE and d["reason"] not in t.SCOPE_DEFERRALS
            and overdue(config.get("lifecycle"), WORK_ITEM, d["state"], moved_at(facts, runs, config, now),
                        known.get("passes_since"), now)):
        return dict(d, attention=t.STALE)
    return d


def _decide(facts: dict, runs: list, context: dict, config: dict, now: str) -> dict:
    d = derive(facts, runs, config)
    state, reason, evidence = d["state"], d["reason"], d["evidence"]

    # An act that stops work, read first: a Hold, a failed read or a draft takes a queued item out too (FR-23,
    # I-13). It is counted, never refused at the act ceiling, and not delayed by a Run in progress. Only a Pause
    # stops it, as it stops every act (decision 0003); then only the Maintainer can stop the merge.
    if d.get("dequeue"):
        pause = brakes.paused(_decision, facts, state, evidence, context, attention=t.NEEDS_YOU)
        if pause:
            return pause
        return _decision(facts, state, reason, evidence, t.ACT, action="dequeue", content_id=facts["content_id"])
    # Fail to a deferral, never to an action.
    if state is None:
        return _decision(facts, None, reason, evidence, t.DEFER)
    if state in t.ADMITS_NOTHING or state in (t.DRAFT, t.QUEUED):
        return _decision(facts, state, reason, evidence, t.NOTHING)
    if state == t.HELD:
        return _decision(facts, state, reason, evidence, t.HOLD)

    mine = runs_on(runs, facts)
    wanted = _wanted_run(state, reason, config)
    if in_progress(mine):
        # No Run in flight lowers a count: attempts, rounds and the Run ceiling count completed Runs, and only a
        # writer's action renews them. So a count the completed Runs have spent holds the item, whatever Run waits and
        # whatever would defer, a Pause among them: the ceilings are asked alone (decision 0003). The act ceiling is
        # not, since it counts acts and stops nothing but an act, and none is decided while a Run is seen to wait. One
        # listed before its name is not seen, so an enqueue can go ahead beside it; I-38 bounds that (decision 0036).
        done = [r for r in since_writer(mine, facts) if r["status"] == "completed"]
        held = None
        if state == t.CONVERGED and _action(reason) == "issue_approval":
            held = brakes.approval_ceilings(_decision, facts, done, config["limits"])
        elif wanted is not None:
            held = brakes.run_ceilings(_decision, facts, evidence, wanted[1], done, config["limits"])
        if held:
            return held
        return _decision(facts, state, reason, evidence, t.NOTHING, working=True)

    if state == t.CONVERGED:
        # A Hold the facts establish, such as an approver who is the author, was read above; then the brakes.
        return _act(facts, state, reason, evidence, mine, context, config)

    # A required check that gave no verdict is unreadable: admit nothing, and wait for a person (I-13).
    if reason == "check_unreadable":
        return _decision(facts, state, reason, evidence, t.DEFER)
    if wanted is None:
        return _decision(facts, state, reason, evidence, t.NOTHING)
    role, intent = wanted

    # The brakes on a Run, in kernel/brakes.py: the Pause, the loop counts and the Run ceiling. The Pause stops an act
    # above, too.
    limits = config["limits"]
    brake = brakes.on_run(_decision, facts, state, evidence, context, intent, since_writer(mine, facts), limits)
    if brake:
        return brake

    # Capacity and the org's concurrency are not brakes: they bound no cycle (§4.1), and only defer.
    until = context.get("model_deferred_until", "unreadable")
    if until == "unreadable":
        return _decision(facts, state, "capacity_unreadable", evidence, t.DEFER)
    # A deadline that is no moment, or a `now` that is none, cannot be compared: the capacity cannot be read.
    if until is not None and not (is_time(until) and is_time(now)):
        return _decision(facts, state, "capacity_unreadable", evidence, t.DEFER)
    if until is not None and until > now:
        return _decision(facts, state, "capacity", evidence, t.DEFER)
    active = context.get("active_runs")
    if active is None:
        return _decision(facts, state, "capacity_unreadable", evidence, t.DEFER)
    if active >= limits["org_max_active_runs"]:
        return _decision(facts, state, "concurrency", evidence, t.DEFER)
    # A Run listed before its run-name may be the Run in flight on any item, this one among them. Which item it is on
    # cannot be read, so no Run is admitted until it can be; a list that cannot be read defers too (I-46, decision 0036).
    if context.get("unidentified_runs") != []:
        return _decision(facts, state, "run_unidentified", evidence, t.DEFER)

    return _decision(facts, state, reason, evidence, t.ADMIT,
                     admit={"role": role, "intent": intent, "content_id": facts["content_id"]})
