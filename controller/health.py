"""`view/health.json`, `health/1`: what one pass knows of the Factory itself (design section 8.4, decisions 0011 and
0043). The page computes the not-run alert in the browser from when the last pass ran; the pass shows the Pause and
what holds it, the chain, what started the passes of the window, the recent capacity and environment faults, each
cause once, and decision 0011's three thresholds, null where a figure was not read."""
from __future__ import annotations

from controller.shared import checked, key, moment, seconds
from kernel import terms as t

STARTS = ("schedule", "relay", "public", "own_repo", "successor", "dispatch")
CAPACITY, ENVIRONMENT = "capacity", "environment"
PERCENTILE = 95       # the delay's percentile, of a hundred


def number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and float("-inf") < value < float("inf")


def threshold(value, limit, exact=None) -> dict:
    """A figure as shown, rounded, and whether it is met, judged on the figure before it was rounded."""
    exact = value if exact is None else exact
    return {"value": value, "limit": limit, "met": None if value is None else exact <= limit}


def delay_p95(records: list):
    """The 95th percentile of minutes from a change to the first pass that read it: a push to a pull request, or a
    change to an issue's content, made after the window's first pass. None when no change was read."""
    delays, seen = [], {}
    for at_first, record in enumerate(records):
        for entry in record["pull_requests"] + record["issues"]:
            facts = entry["facts"]
            at = facts.get("last_push_at") if "last_push_at" in facts else facts.get("content_changed_at")
            item = key(facts["item"])
            # Counted once, by the first pass that read this change, if it came after the window's first pass, even
            # when passes between them missed the item.
            if moment(at) is None or at > record["now"]:
                continue        # a change no pass has read yet is not seen
            if at_first and seen.get(item) != at and records[0]["now"] < at:
                delays.append(seconds(record["now"], at))
            seen[item] = at
    if not delays:
        return None
    delays.sort()
    # The nearest rank: the smallest delay that at least the percentile of them do not exceed.
    return round(delays[(PERCENTILE * len(delays) + 99) // 100 - 1] / 60.0, 2)


def thresholds(window: list, usage, rule: dict) -> dict:
    """Decision 0011's three, over the window: each figure, its limit, and whether it is met, null where the figure
    was not read."""
    usage = usage if isinstance(usage, dict) else {}
    factory, org = usage.get("factory_job_minutes"), usage.get("org_job_minutes")
    share = factory / org if number(factory) and number(org) and factory >= 0 and org > 0 else None
    points = usage.get("graphql_points_peak_hour")
    points = points if number(points) and points >= 0 else None
    return {"job_minutes_share": threshold(None if share is None else round(share, 4), rule["job_minutes_share"], share),
            "graphql_points_per_hour": threshold(points, rule["graphql_points_per_hour"]),
            "decision_delay_p95_minutes": threshold(delay_p95(window), rule["decision_delay_p95_minutes"])}


def alerts(reasons: list, context: dict, capacity, automatic: bool, left_out: bool, not_run: bool, unnamed: dict) -> list:
    """Each cause once, however many items it defers (L-48). A cause that holds the whole scope is raised from the
    context as well as from the Decisions, so that it is raised with no item to defer. The automatic pause defers as
    `capacity` does, and is the one cause `environment` unless a capacity fault holds too. Facts left out are one cause,
    and so is six hours with no pass. `unnamed` is the Kernel's `unnamed_scope`: an unnamed Run inside the window
    defers, and past `max_unnamed_runs` of them past it every Run does (issue 270)."""
    causes = set(reasons) & t.SCOPE_DEFERRALS
    causes |= {"paused"} if context["paused"] is True else set()
    causes |= {"pause_unreadable"} if context["paused"] is None else set()
    causes |= {"capacity"} if capacity is not None else set()
    causes |= {"capacity_unreadable"} if context["active_runs"] is None else set()
    causes |= {"run_unidentified"} if unnamed["defers"] else set()
    causes |= {"runs_unnamed"} if unnamed["bounded"] else set()
    if automatic and capacity is None:
        causes.discard("capacity")
    causes |= {ENVIRONMENT} if automatic else set()
    causes |= {"facts_unreadable"} if left_out else set()
    causes |= {"not_run"} if not_run else set()
    return sorted(causes)


def health(record: dict, before: list, pause: tuple, automatic: bool, alerts: list, usage, rules: dict) -> dict:
    """The health file of one pass. `pause` is the person's Pause as read, `(paused, scopes)`; `automatic` whether the
    environment faults hold every Run."""
    # Paused by the scopes that pause and by the faults; unreadable by the scopes that cannot be read; or neither.
    paused, scopes = pause
    by = (list(scopes) if paused is not False else []) + ([ENVIRONMENT] if automatic else [])
    state = "paused" if paused or automatic else ("unreadable" if paused is None else "none")
    window = [r for r in before if seconds(record["now"], r["now"]) <= rules["thresholds"]["window_seconds"]]
    window.append(record)
    successors = 0
    for older in reversed(window):
        if older["started_by"] != "successor":
            break
        successors += 1
    recent = max(rules["capacity_window_seconds"], rules["automatic_pause"]["window_seconds"])
    faults = [{"run": r["run"], "item": r["item"], "outcome": r["outcome"], "at": r["started_at"]}
              for r in record["runs"] if r["outcome"] in (CAPACITY, ENVIRONMENT)
              and seconds(record["now"], r["started_at"]) is not None
              and 0 <= seconds(record["now"], r["started_at"]) <= recent]
    doc = {"schema": "health/1", "pass": record["pass"], "release": record["release"], "written_at": record["now"],
           "last_pass_at": record["now"], "previous_pass_at": before[-1]["now"] if before else None,
           "relay_started_at": None, "pause": {"state": state, "by": by},
           "chain": {"since": record["context"]["passes_since"], "started_by": record["started_by"],
                     "successors": successors},
           "starts": {code: len([r for r in window if r["started_by"] == code]) for code in STARTS},
           "faults": faults, "alerts": alerts,
           "thresholds": thresholds(window, usage, rules["thresholds"])}
    return checked(doc, "health")
