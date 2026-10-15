"""Derive the State of a pull request from facts and run records.

State is never stored. This function is the only definition of it.
"""
from __future__ import annotations

from kernel import terms as t


def incomplete(facts: dict) -> list:
    """Names of the fact lists that were not read in full."""
    return sorted(k for k, whole in facts["complete"].items() if not whole)


def runs_on(runs: list, facts: dict) -> list:
    """Run records for this item, oldest first."""
    mine = [r for r in runs if r["item"] == facts["item"]]
    return sorted(mine, key=lambda r: r["started_at"])


def since_writer(runs: list, facts: dict) -> list:
    """Runs started after the last action by a person with write access."""
    mark = facts.get("last_writer_action_at")
    if mark is None:
        return runs
    return [r for r in runs if r["started_at"] > mark]


def in_progress(runs: list) -> list:
    """Runs that hold the item: started, or admitted and still waiting for a runner."""
    return [r for r in runs if r["status"] != "completed"]


def reviewed_clean_or_not(runs: list, facts: dict, role: str) -> bool:
    """Has `role` completed a review of exactly this content?"""
    return any(
        r["role"] == role
        and r["intent"] == "review-change"
        and r["content_id"] == facts["content_id"]
        and r["status"] == "completed"
        and r["conclusion"] == "success"
        for r in runs
    )


def required_model_lenses(facts: dict, config: dict) -> list:
    """The model Lenses whose review this pull request needs.

    A dependency update is judged by the deterministic Lenses alone. It is a
    pull request of a class the configuration names, whose head was pushed
    by the identity that opened it. The class is worked out from who opened
    it; anyone else's push puts content of their own in it, and that is
    reviewed as any change is.
    """
    lenses = config["required_lenses"]
    if facts["class"] in lenses["model_not_required_for"] and facts["last_pusher"] == facts["author"]:
        return []
    return list(lenses["model"])


def gating_threads(facts: dict, config: dict) -> list:
    """Open threads that hold the pull request.

    A person with write access always gates. A Lens gates only if it is
    required and its Finding is blocking or major. Everyone else informs.
    A Finding a model Lens has raised gates whatever the class: a dependency
    update needs no review, and still answers one it was given.
    """
    required = set(config["required_lenses"]["model"])
    out = []
    for th in facts["threads"]:
        if th["resolved"]:
            continue
        by = th["opened_by"]
        if by["kind"] == "human" and by["can_write"]:
            out.append(th)
        elif by["kind"] == "lens" and by["name"] in required and th["severity"] in t.GATING_SEVERITIES:
            out.append(th)
    return out


def whose_turn(thread: dict, runs: list, config: dict) -> str:
    """Who must act on an open gating thread: 'author', 'owner' or 'human'.

    The author answers a thread with a Run after it was opened. The answer may
    be new content, so this cannot be read from "the last Run on this content".
    A thread still open after the owner has judged that answer was rejected,
    and is the author's again. A person's thread, once answered, waits for
    that person: no Role may close it.
    """
    answers = [r["started_at"] for r in runs
               if r["role"] == config["author_role"] and r["status"] == "completed"
               and r["conclusion"] == "success" and r["started_at"] > thread["opened_at"]]
    if not answers:
        return "author"
    if thread["opened_by"]["kind"] == "human":
        return "human"
    rulings = [r["started_at"] for r in runs
               if r["intent"] == "adjudicate-findings" and r["status"] == "completed"
               and r["conclusion"] == "success" and r["started_at"] > max(answers)]
    return "author" if rulings else "owner"


def admitted(facts: dict) -> bool:
    """An outside item is admitted only after its author's latest push."""
    if facts["class"] != "outside":
        return True
    if t.LABEL_ADMIT not in facts["labels"] or facts["admitted_at"] is None:
        return False
    return facts["admitted_at"] > facts["last_push_at"]


def standing_approval(facts: dict, config: dict):
    """The approver's undismissed approval of this content, if any."""
    for rv in facts["reviews"]:
        if (
            rv["actor"] == config["approver"]
            and rv["state"] == "approved"
            and rv["content_id"] == facts["content_id"]
        ):
            return rv
    return None


def derive(facts: dict, runs: list, config: dict) -> dict:
    """Return {'state', 'reason', 'evidence'} for one pull request.

    `state` is None when the facts are incomplete, or the merge state is not
    known: an incomplete read is an unreadable one, and nothing may be
    concluded from it.
    """
    gaps = incomplete(facts)
    if gaps:
        return {"state": None, "reason": "facts_incomplete", "evidence": gaps}

    if facts["state"] == "merged":
        return {"state": t.MERGED, "reason": "merged", "evidence": []}
    if facts["state"] == "closed":
        return {"state": t.CLOSED, "reason": "closed", "evidence": []}
    if not facts["targets_protected"]:
        return {"state": t.NOT_SERVED, "reason": "base_not_protected", "evidence": []}
    if facts["is_draft"]:
        return {"state": t.DRAFT, "reason": "draft", "evidence": []}

    labels = facts["labels"]
    if t.LABEL_HANDS_OFF in labels:
        return {"state": t.HELD, "reason": "hands_off", "evidence": [t.LABEL_HANDS_OFF]}
    if t.LABEL_HOLD in labels:
        return {"state": t.HELD, "reason": "human_hold", "evidence": [t.LABEL_HOLD]}
    if not admitted(facts):
        return {"state": t.HELD, "reason": "outside_not_admitted", "evidence": []}
    if facts["diff"]["files"] == 0:
        return {"state": t.HELD, "reason": "empty_diff", "evidence": []}
    if facts["diff"]["truncated"] or facts["diff"]["lines"] > config["limits"]["max_diff_lines"]:
        return {"state": t.HELD, "reason": "too_large", "evidence": []}
    if facts["queue"]:
        return {"state": t.QUEUED, "reason": "in_merge_queue", "evidence": []}
    # GitHub works the merge state out after a push. Until it has, it is unknown, and unreadable.
    mergeable = facts.get("mergeable")
    if mergeable is False:
        return {"state": t.ADDRESSING, "reason": "conflict", "evidence": []}
    if mergeable is not True:
        return {"state": None, "reason": "mergeable_unreadable", "evidence": []}

    # Deterministic Lenses first: a model's time is not spent on content they reject.
    by_lens = {c["lens"]: c for c in facts["checks"]}
    failed, waiting = [], []
    for lens in config["required_lenses"]["deterministic"]:
        check = by_lens.get(lens)
        if check is None or check["conclusion"] == "pending":
            waiting.append(lens)
        elif check["conclusion"] != "success":
            failed.append(lens)
    if failed:
        return {"state": t.ADDRESSING, "reason": "check_failed", "evidence": failed}
    if waiting:
        return {"state": t.VERIFYING, "reason": "awaiting_checks", "evidence": waiting}

    # Then the model Lenses this item needs: a dependency update needs none, and skips nothing else.
    mine = runs_on(runs, facts)
    for lens in required_model_lenses(facts, config):
        if not reviewed_clean_or_not(mine, facts, lens):
            return {"state": t.VERIFYING, "reason": "awaiting_review", "evidence": [lens]}

    open_gates = gating_threads(facts, config)
    if open_gates:
        turns = {th["id"]: whose_turn(th, mine, config) for th in open_gates}
        for_author = [tid for tid, who in turns.items() if who == "author"]
        for_owner = [tid for tid, who in turns.items() if who == "owner"]
        if for_author:
            human = any(th["opened_by"]["kind"] == "human" for th in open_gates if th["id"] in for_author)
            return {"state": t.ADDRESSING, "reason": "human_finding" if human else "findings_open",
                    "evidence": for_author}
        if for_owner:
            return {"state": t.ADJUDICATING, "reason": "proposals_await_owner", "evidence": for_owner}
        return {"state": t.ADDRESSING, "reason": "awaiting_human", "evidence": sorted(turns)}

    approval = standing_approval(facts, config)
    if approval is not None:
        return {"state": t.CONVERGED, "reason": "approved", "evidence": [approval["commit"]]}
    return {"state": t.CONVERGED, "reason": "approval_due", "evidence": []}
