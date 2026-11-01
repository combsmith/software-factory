"""One pass of the Controller, as a function of what it read (design sections 2.3, 3.4 and 7.3, issue 193).

`run(reads, config, now, previous, mint)` builds the context from the reads, asks the Kernel about every item through
its entry points, and returns the pass record, the Runs to dispatch, each named by its run-name, the acts to make,
the view's three files, the alerts, and whether to start a successor. It decides nothing itself: every Decision is the
Kernel's, and what it reports of the Factory's own health is read from the reads and the pass records. It writes
nothing and reads no clock: `now` is given, and so is `mint`, which gives each new id. What it returns is written by the
workflows and the effects port. Every document it returns is validated against its schema, and one that is not valid
is refused whole, so that nothing is dispatched from a pass that cannot be replayed.

`reads` holds what the ports gave, as data:
- `started`: the run that started this pass, `{"event", "actor": {"id", "type"} or None, "attempt"}`, the attempt a
  whole number;
- `pause`: `FACTORY_PAUSED` as GitHub holds it, `{"org": value, "repos": {repo: value}}`, None where it is not set; a
  scope missing is one that was not read;
- `records`: what `adapters.records.runs` returned, or None if it raised;
- `pull_requests` and `issues`: `[{"facts", "title"}]`, the title beside the facts and never in them;
- `facts_reads`: each facts read's `{"date", "age"}`;
- `usage`: what was read of the window's job-minutes and GraphQL points, by `factory_job_minutes`, `org_job_minutes`
  and `graphql_points_peak_hour`, each missing until a port reads it;
- `seen`: what `adapters/seen.py` read of each Factory identity's writes, `seen/1`, or None;
- `effects`: the Effects recorded in the window, `{"applied": [applied/1], "written": [written/1], "whole"}`, or None;
  reconciliation matches the one to the other (`controller/reconcile.py`, decision 0061).

`config` holds `kernel`, the Kernel's configuration; `lifecycles`, each Work item's; `feed`, `config/feed.json`;
`controller`, `config/controller.json`; and `release`, the Release that runs. `previous` is the pass records before this
one, or None if they could not be read; a list holding a record that is not a `pass/1` is read as None.
"""
from __future__ import annotations

import copy
import datetime

from controller import credentials as credentials_
from controller import feed as feed_
from controller import health as health_
from controller import reads as reads_
from controller import reconcile as reconcile_
from controller.shared import Refused, checked, key, moment, seconds, text
from kernel import decide as pull_request
from kernel import issue
from kernel import terms as t

# What started a pass, by the run that started it (decision 0043). Any other event is the relay's public one.
SCHEDULE, OWN_REPO, DISPATCHED = "schedule", "workflow_run", "workflow_dispatch"
# FACTORY_PAUSED, read exactly as GitHub holds a variable: any other value is unreadable (L-58).
PAUSED, NOT_PAUSED = "true", "false"
CAPACITY, ENVIRONMENT = health_.CAPACITY, health_.ENVIRONMENT
NOT_RUN = "not_run"
NEVER_STARTED = "runs_never_started"
__all__ = ["Refused", "run", "rebuild", "wait_before_reading", "context_of"]


def earlier(previous, now: str):
    """The pass records that ran before `now`, oldest first; None if they could not be read, or one of them has a time
    that is no moment or no earlier than `now`. A record passed over would hide the pass it records: the last pass's
    read, or the gap the chain began after."""
    if previous is None or any(moment(r["now"]) is None or r["now"] >= now for r in previous):
        return None
    return sorted(previous, key=lambda r: r["now"])


def started_by(started, accounts: dict) -> str:
    """What started the pass, read from its run and never from anything a dispatch carries (decision 0043).

    A re-run is `dispatch`, whatever event it keeps. A schedule's actor is never read. A dispatch is the `successor`
    only by the workflow's own token, an account told by its type and id. Any other event is the relay's public one:
    `relay` from the relay's account, `public` from anyone else. An account the configuration holds as null is no one's.
    """
    started = started if isinstance(started, dict) else {}
    if started.get("attempt") != 1 or isinstance(started.get("attempt"), bool):
        return "dispatch"
    event = started.get("event")
    if event == SCHEDULE:
        return "schedule"
    if event == OWN_REPO:
        return "own_repo"
    actor = started.get("actor") if isinstance(started.get("actor"), dict) else {}
    who = (actor.get("id"), actor.get("type"))

    def is_(account) -> bool:
        return isinstance(account, dict) and (account["id"], account["type"]) == who

    if event == DISPATCHED:
        return "successor" if is_(accounts.get("workflow_token")) else "dispatch"
    return "relay" if is_(accounts.get("relay")) else "public"


def _scope(value) -> str:
    """One scope's FACTORY_PAUSED: paused, not paused, or unreadable. Not set is not paused."""
    if value is None or value == NOT_PAUSED:
        return "none"
    return "paused" if value == PAUSED else "unreadable"


def human_pause(read, repos) -> tuple:
    """`(paused, by)`: a Pause on the org or on any repo the pass reads is a Pause; then a scope that cannot be read
    makes the Pause unreadable (L-58). `by` names each scope that pauses, or that cannot be read."""
    read = read if isinstance(read, dict) else {}
    held = read.get("repos") if isinstance(read.get("repos"), dict) else {}
    scopes = [("org", read["org"] if "org" in read else object())]
    # Every repo read is a scope, whether or not an item of it is decided: a paused repo with nothing open still pauses.
    scopes += [("repo", held[repo] if repo in held else object()) for repo in sorted(set(repos) | set(held))]
    states = [(name, _scope(value)) for name, value in scopes]
    paused = sorted({name for name, state in states if state == "paused"})
    if paused:
        return True, paused
    unread = sorted({name for name, state in states if state == "unreadable"})
    if unread:
        return None, unread
    return False, []


def _streak(runs: list, now: str, rule: dict) -> list:
    """The faults since any Run last succeeded, inside the recent window: Runs that ended `environment`, and Runs GitHub
    started no job of (decision 0114), which write no outcome at all."""
    recent = [r for r in runs if r["status"] == "completed" and seconds(now, r["started_at"]) is not None
              and 0 <= seconds(now, r["started_at"]) < rule["window_seconds"]]
    recent.sort(key=lambda r: r["started_at"])
    succeeded = [i for i, r in enumerate(recent) if r["conclusion"] == "success"]
    since = recent[succeeded[-1] + 1:] if succeeded else recent
    return [r for r in since if r["outcome"] == ENVIRONMENT or r.get("never_ran") is True]


def automatic_pause(runs: list, now: str, rule: dict):
    """Until when every Run waits because Admission paused itself, or None: faults in a row, since any Run last
    succeeded, from Runs on different items, inside the recent window (L-59), held for the window from the newest. An
    old streak is outside the window; one item's is that item's. It stops no act: only a person's Pause stops a dequeue,
    so that nothing but the Maintainer can keep a merge from being stopped (decision 0003)."""
    faults = _streak(runs, now, rule)
    items = {(r["item"]["repo"], r["item"]["type"], r["item"]["number"]) for r in faults}
    if len(faults) < rule["faults"] or len(items) < rule["items"]:
        return None
    return text(moment(faults[-1]["started_at"]) + datetime.timedelta(seconds=rule["window_seconds"]))


def automatic_causes(runs: list, now: str, rule: dict) -> list:
    """What holds the automatic pause, asked once it holds: `environment` for Runs that said so, and `runs_never_started`
    for Runs GitHub started no job of, so one cause is named as itself and not as an outage."""
    return sorted({NEVER_STARTED if r.get("never_ran") is True else ENVIRONMENT for r in _streak(runs, now, rule)})


def capacity_until(runs: list, now: str, window: int):
    """Until when model Runs wait after the newest capacity fault: its start and the window, or None once that is
    past (design section 3.10). A Run's record has no time of its fault, so the window counts from its start."""
    starts = [r["started_at"] for r in runs if r["status"] == "completed" and r["outcome"] == CAPACITY
              and moment(r["started_at"]) is not None and r["started_at"] <= now]
    if not starts:
        return None
    until = text(moment(max(starts)) + datetime.timedelta(seconds=window))
    return until if until > now else None


def passes_since(before: list, previous, now: str, gap: int):
    """The first pass after the last gap of the not-run alert's second reading, read from the pass records: a chain
    that ended with nothing due breaks nothing (decision 0043). With no record before it, a chain starts now; with
    records that cannot be read, or none that reaches the chain's start, it is not known."""
    if previous is None:
        return None
    if not before:
        return now if not previous else None
    later = now
    for record in reversed(before):
        if seconds(later, record["now"]) > gap:
            return later
        later = record["now"]
    oldest = before[0]["context"]["passes_since"]
    return oldest if moment(oldest) is not None else None


def context_of(records, pause_read, repos, rules: dict, now: str, before=(), previous=None) -> tuple:
    """`(listed, whole, runs, pause, automatic, capacity, context)`: the context the Kernel is given, from the records
    port's list, the Pause as read and the repos it is read for, and the pass records before, as one pass builds it.
    `apply` and the approving act build it so too, from their own reads and no records before, so that `passes_since`
    is unreadable, which defers nothing (decision 0043)."""
    listed, whole = reads_.run_records(records)
    runs = copy.deepcopy(records["runs"]) if listed else []
    pause = human_pause(pause_read, repos)
    automatic = automatic_pause(runs, now, rules["automatic_pause"]) if whole else None
    capacity = capacity_until(runs, now, rules["capacity_window_seconds"]) if whole else None
    # Not whole, the count of active Runs is null and defers every Run, so a deferral the list may hide holds too.
    context = {
        "paused": pause[0],
        "active_runs": len([r for r in runs if r["status"] != "completed"]) if whole else None,
        "model_deferred_until": max([u for u in (capacity, automatic) if u is not None], default=None),
        "passes_since": passes_since(list(before), previous, now, rules["not_run_seconds"]),
        "unidentified_runs": list(records["unidentified"]) if listed else None,
    }
    return listed, whole, runs, pause, automatic, capacity, context


def wait_before_reading(previous, now: str, config: dict) -> int:
    """Seconds to wait before this pass reads: none sooner than the gap after the last pass's read began, whatever
    started it (decision 0043). If the records cannot be read, the whole gap."""
    gap = config["controller"]["read_gap_seconds"]
    before = earlier(reads_.previous_records(previous), now)
    if before is None:
        return gap
    if not before:
        return 0
    last = before[-1]
    began = min([r["date"] for r in last["reads"] if moment(r["date"]) is not None] or [last["now"]])
    return max(0, gap - seconds(now, began))


def rebuild(records: list, titles: dict, config: dict) -> list:
    """The feed's two files as each pass record left them, rebuilt from the records alone (decision 0002)."""
    return feed_.rebuild(records, titles, config["feed"],
                         lambda r: pull_request.unnamed_scope(r["context"], config["kernel"], r["now"])["alerts"])


def _run_name(item: dict, intent: str, role: str, content: str, run: str) -> str:
    return checked("sf %s#%d %s %s %s %s" % (item["repo"], item["number"], intent, role, content, run), "run-name")


def _acts(record: dict) -> set:
    """The acts a pass record decided, other than an approval, each by its item, action and content."""
    return {(key(e["decision"]["item"]), e["decision"]["action"], e["decision"].get("content_id"))
            for e in record["pull_requests"] + record["issues"]
            if e["decision"]["outcome"] == t.ACT and e["decision"]["action"] != "issue_approval"}


def run(reads: dict, config: dict, now: str, previous, mint) -> dict:
    """One pass: the record, the Runs to dispatch, the acts, the view, the alerts and whether a successor starts."""
    rules = reads_.configured(config["controller"])
    before = earlier(reads_.previous_records(previous), now)
    previous, before = (None, []) if before is None else (before, before)
    # Facts that are not facts, and an item listed twice, never reach the Kernel and no record could hold them: the
    # item is left out of this pass, as one alert, and every other item is decided as it would be without it.
    pulls, left_out = reads_.items(copy.deepcopy(reads.get("pull_requests")), "facts")
    issues, also = reads_.items(copy.deepcopy(reads.get("issues")), "issue-facts")
    left_out += also
    repos = {e["facts"]["item"]["repo"] for e in pulls + issues}

    records = reads.get("records")
    listed, whole, runs, pause, automatic, capacity, context = context_of(records, reads.get("pause"), repos, rules,
                                                                           now, before, previous)

    def asked(entries: list, decide, lifecycle: dict) -> list:
        kernel = dict(config["kernel"], lifecycle=lifecycle)
        out = []
        for entry in entries:
            facts = entry["facts"]
            facts["complete"] = dict(facts["complete"])
            # The facts port reads no run: the records port's list says whether the Runs were read whole.
            facts["complete"]["runs"] = facts["complete"].get("runs") is True and whole
            d = decide(facts, runs, context, kernel, now)
            minted = d["outcome"] == t.ADMIT or d.get("action") == "issue_approval"
            out.append({"facts": facts, "decision": d, "run": mint("r") if minted else None})
        return out

    # Every write a Factory identity made, matched to an Effect the Factory recorded; one alert for any that is not, and
    # one for a reconciliation that is short (I-33, decision 0061). What it found is in the record before it is checked.
    found = reconcile_.reconcile(reads.get("seen"), reads.get("effects"), runs if listed and whole else None, before,
                                 rules["accounts"])
    record = {"schema": "pass/1", "pass": mint("p"), "release": config["release"], "now": now,
              "started_by": started_by(reads.get("started"), rules["accounts"]), "context": context, "runs": runs,
              "reads": (copy.deepcopy(records["reads"]) if listed else [])
              + [dict(r, read="facts") if isinstance(r, dict) else r for r in reads.get("facts_reads") or []],
              "pull_requests": asked(pulls, pull_request.decide, config["lifecycles"]["pull_request"]),
              "issues": asked(issues, issue.decide, config["lifecycles"]["issue"]),
              "reconciliation": reconcile_.entries(found)}
    checked(record, "pass")
    entries = record["pull_requests"] + record["issues"]
    ids = [record["pass"]] + [e["run"] for e in entries if e["run"] is not None]
    if len(set(ids)) != len(ids):
        raise Refused("pass/1: the mint gave an id twice")

    dispatch, acts = [], []
    for e in entries:
        d = e["decision"]
        if d["outcome"] == t.ADMIT:
            name = _run_name(d["item"], d["admit"]["intent"], d["admit"]["role"], d["admit"]["content_id"], e["run"])
            dispatch.append({"run": e["run"], "name": name})
        elif d["outcome"] == t.ACT and d["action"] == "issue_approval":
            name = _run_name(d["item"], t.ISSUE_APPROVAL, config["kernel"]["owner_role"], d["content_id"], e["run"])
            dispatch.append({"run": e["run"], "name": name})
        elif d["outcome"] == t.ACT:
            acts.append(d)

    # An unnamed Run defers only inside the window or until it completes; past the window it is an alert, by its run id,
    # and past max_unnamed_runs of them every Run defers (issue 270).
    unnamed = pull_request.unnamed_scope(context, config["kernel"], now)

    def gap(later: str, earlier_: str) -> bool:
        return seconds(later, earlier_) > rules["not_run_seconds"]

    # The first pass after six hours with none raises the not-run alert, and the next pass clears it (decision 0043).
    raised = bool(before) and gap(now, before[-1]["now"])
    cleared = len(before) >= 2 and gap(before[-1]["now"], before[-2]["now"]) and not raised
    # A stored credential near its limit, or whose row cannot be read, is one alert, each by its secret's name alone
    # (L-37, issue 305).
    due, names_due = credentials_.due(config.get("credentials"), now)
    causes = automatic_causes(runs, now, rules["automatic_pause"]) if automatic is not None else []
    alerts = health_.alerts([e["decision"]["reason"] for e in entries], context, capacity, causes,
                            bool(left_out), raised, unnamed, reconcile_.alerts(found), due)
    decided = [e["facts"]["item"] for e in entries]
    titles = {key(e["facts"]["item"]): e.get("title") if isinstance(e.get("title"), str) else ""
              for e in pulls + issues if e["facts"]["item"] in decided}
    feed = feed_.view(record, before, titles, config["feed"], unnamed["alerts"], record["reconciliation"])
    record["credentials_due"] = names_due
    feed["health"] = health_.health(record, before, pause, causes, alerts, reads.get("usage"), rules)
    # A successor only for an item due at the pass's end: an act made here, whose next Decision is due at once, and not
    # one the pass before made too, which did not take. A Run's end starts the next pass itself, and a pass deferred by
    # a Run it cannot name starts none (decisions 0036, 0043).
    done = _acts(before[-1]) if before else set()
    due = [d for d in acts if (key(d["item"]), d["action"], d.get("content_id")) not in done]
    successor = bool(due) and not unnamed["defers"] and not unnamed["bounded"]
    # The one write no Decision calls for: recorded, so the effects port can hold a plan's successor to it; and the
    # alerts, which the tracking issue reports.
    record["successor"] = successor
    record["alerts"] = sorted(alerts)
    return {"record": record, "dispatch": dispatch, "acts": acts, "view": feed, "alerts": alerts,
            "cleared": [NOT_RUN] if cleared else [], "left_out": left_out, "successor": successor}
