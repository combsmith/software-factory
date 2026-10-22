"""Admission: what, if anything, happens next on one pull request.

decide(facts, runs, context, config, now) -> Decision. No I/O, no clock.
Times are UTC, to the second, in one text format. They compare as text, and the Kernel counts
the seconds between two itself, from the pinned calendar in terms.py.
"""
from __future__ import annotations

from kernel import brakes
from kernel import terms as t
from kernel.derive import (derive, in_progress, moved_at, overdue, run_deferral, runs_on, since_writer, unnamed_past,
                           unnamed_within)

SCHEMA = "decision/1"

WORK_ITEM = "pull_request"      # the Lifecycle this module reads, lifecycle/pull_request.json
NEEDS_YOU_REASONS = frozenset({
    "human_hold", "outside_not_admitted", "empty_diff", "too_large", "human_finding",
    "attempts_exhausted", "run_ceiling", "max_rounds", "approver_is_author_or_last_pusher",
    "awaiting_human", "act_ceiling", "check_unreadable", "review_unreadable", "thread_unreadable", "label_unreadable",
    "acceptance_unreadable", "paths_unreadable", "protected_paths_unreadable",
    "last_pusher_unreadable",
    "contract_not_approved", "contract_changed", "acceptance_reporters_unreadable",
    "run_unreadable", "model_lens_input_needs_person",
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


def _act(facts: dict, state: str, reason: str, evidence: list, mine: list, context: dict, config: dict,
         now: str) -> dict:
    """An act that moves work on, once the brakes let it through. An act that stops work is not decided here."""
    action = _action(reason)
    since = since_writer(mine, facts)
    brake = brakes.on_act(_decision, facts, state, evidence, context, action, since, config["limits"])
    if brake:
        return brake
    # An approval is a Run, so a Run that cannot be told whose it is defers it. An enqueue admits none (decision 0036).
    if action == "issue_approval" and unnamed_within(context, now, config["limits"]) != []:
        return _decision(facts, state, "run_unidentified", evidence, t.DEFER)
    past = unnamed_past(context, now, config["limits"]) if action == "issue_approval" else []
    if past and len(past) > config["limits"]["max_unnamed_runs"]:
        return _decision(facts, state, "runs_unnamed", evidence, t.DEFER)
    return _decision(facts, state, reason, evidence, t.ACT, action=action, content_id=facts["content_id"])


def still_wanted(decided: dict, again: dict) -> bool:
    """Whether an act or a Run may go ahead: the Decision it was started by, `decided`, against `again`, the Kernel asked
    again on what it just read with its own Run left out of the records (I-38, issue 195). A Run is still wanted only if
    the same Run is admitted, the same Role and Intent for the same content, as `kernel.issue.still_admitted` reads an
    issue's. An approval is still wanted only if the approval is issued again, for the same item and content. So a Hold,
    a Pause, a close, new content, a Run in flight, a writer's gate, a wait for a person and an approver who is now the
    author each stop it. Anything else, or anything that cannot be read, is not wanted."""
    if not isinstance(decided, dict) or not isinstance(again, dict) or not isinstance(decided.get("item"), dict) \
            or again.get("item") != decided.get("item"):
        return False
    admit = decided.get("admit")
    if admit is not None:
        # A Run named in part is no Run: an unreadable part never matches itself, and only an admission admits.
        whole = isinstance(admit, dict) and all(isinstance(admit.get(part), str) and admit.get(part)
                                                for part in ("role", "intent", "content_id"))
        return (whole and decided.get("outcome") == t.ADMIT and again.get("outcome") == t.ADMIT
                and again.get("admit") == admit)
    content = decided.get("content_id")
    if decided.get("outcome") != t.ACT or decided.get("action") != "issue_approval" or not isinstance(content, str) \
            or not content:
        return False
    return (again.get("outcome") == t.ACT and again.get("action") == "issue_approval"
            and again.get("content_id") == decided.get("content_id"))


def stuck_runs(context: dict, config: dict, now: str) -> list:
    """The alerts of the whole scope a pass shows in the view: one for each unidentified Run listed for
    max_unnamed_run_seconds or more, by its run id, in the order listed, each run once however often it is listed. It
    stays an alert until a person deletes the run, or it falls from the newest runs the port reads. Nothing that cannot
    be read is named: a list that cannot be read defers every Run instead (decision 0036, issue 270)."""
    limits = config.get("limits") if isinstance(config, dict) else None
    return [{"alert": t.RUN_UNNAMED, "run": run} for run in unnamed_past(context, now, limits)]


def unnamed_scope(context: dict, config: dict, now: str) -> dict:
    """The Kernel's reading of the unnamed Runs for the whole scope, which a pass needs with no item to decide on
    (issue 270, the third entry point by the ruling on issue 193): `defers`, whether every Run waits on an unnamed Run
    inside the window or not yet completed, or on a list that cannot be read; `alerts`, one for each Run unnamed past
    the window; and `bounded`, whether more such Runs are listed than max_unnamed_runs, past which every Run waits."""
    limits = config.get("limits") if isinstance(config, dict) else {}
    alerts = stuck_runs(context, config, now)
    most = limits.get("max_unnamed_runs") if isinstance(limits, dict) else None
    defers = unnamed_within(context, now, limits) != []
    return {"defers": defers, "alerts": alerts, "bounded": not defers and bool(alerts) and len(alerts) > most}


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
        return _act(facts, state, reason, evidence, mine, context, config, now)

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

    # Capacity and the org's concurrency are not brakes: they bound no cycle (§4.1), and only defer; a Run listed
    # before its run-name defers too (decision 0036). Each is read whole, for either kind of Work item, in one place.
    stop = run_deferral(_decision, facts, state, evidence, context, now, limits)
    if stop:
        return stop

    return _decision(facts, state, reason, evidence, t.ADMIT,
                     admit={"role": role, "intent": intent, "content_id": facts["content_id"]})
