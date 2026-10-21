"""One pass of the Controller, as a function of what it read (design sections 2.3, 3.4 and 7.3, issue 193).

`run(reads, config, now, previous, mint)` builds the context from the reads, asks the Kernel about every item through
its two entry points, and returns the pass record, the Runs to dispatch, each named by its run-name, the acts to make,
the view's three files, the alerts, and whether to start a successor. It decides nothing itself: every Decision is the
Kernel's, and what it reports of the Factory's own health is read from the reads and the pass records. It writes
nothing and reads no clock: `now` is given, and so is `mint`, which gives each new id. What it returns is written by the
workflows and the effects port. Every document it returns is validated against its schema, and one that is not valid
is refused whole, so that nothing is dispatched from a pass that cannot be replayed.

`reads` holds what the ports gave, as data:
- `started`: the run that started this pass, `{"event", "actor": {"id", "type"} or None, "attempt"}`;
- `pause`: `FACTORY_PAUSED` as GitHub holds it, `{"org": value, "repos": {repo: value}}`, None where it is not set; a
  scope missing is one that was not read;
- `records`: what `adapters.records.runs` returned, or None if it raised;
- `pull_requests` and `issues`: `[{"facts", "title"}]`, the title beside the facts and never in them;
- `facts_reads`: each facts read's `{"date", "age"}`;
- `usage`: what was read of the window's job-minutes and GraphQL points, by `factory_job_minutes`, `org_job_minutes`
  and `graphql_points_peak_hour`, each missing until a port reads it.

`config` holds `kernel`, the Kernel's configuration; `lifecycles`, each Work item's; `feed`, `config/feed.json`;
`controller`, `config/controller.json`; and `release`, the Release that runs. `previous` is the pass records before this
one, or None if they could not be read.
"""
from __future__ import annotations

import copy
import datetime
import json
import pathlib

from kernel import decide as pull_request
from kernel import issue
from kernel import terms as t
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
# The Release's own schemas, read once as the module loads, as the Release's other data files are.
SCHEMAS = {p.name[: -len(".schema.json")]: json.loads(p.read_text())
           for p in sorted((ROOT / "schemas").glob("*.schema.json"))}
FORMAT = "%Y-%m-%dT%H:%M:%SZ"
# What started a pass, by the run that started it (decision 0043). Any other event is the relay's public one.
SCHEDULE, OWN_REPO, DISPATCHED = "schedule", "workflow_run", "workflow_dispatch"
STARTS = ("schedule", "relay", "public", "own_repo", "successor", "dispatch")
# FACTORY_PAUSED, read exactly as GitHub holds a variable: any other value is unreadable (L-58).
PAUSED, NOT_PAUSED = "true", "false"
# A Run of these outcomes is the Factory's own fault, never the item's (design section 3.10).
CAPACITY, ENVIRONMENT = "capacity", "environment"
NOT_RUN = "not_run"
PERCENTILE = 95       # the delay's percentile, of a hundred


class Refused(ValueError):
    """The pass cannot make a record that validates, so it makes none, and nothing is dispatched."""


def _moment(text):
    """A time in the one format, as a moment, or None if it is not one."""
    try:
        return datetime.datetime.strptime(text, FORMAT)
    except (TypeError, ValueError):
        return None


def _text(moment) -> str:
    return moment.strftime(FORMAT)


def _seconds(later: str, earlier: str):
    """Seconds from `earlier` to `later`, or None if either is no moment."""
    a, b = _moment(later), _moment(earlier)
    return None if a is None or b is None else int((a - b).total_seconds())


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and float("-inf") < value < float("inf")


def _checked(value, kind: str):
    errors = validate(value, SCHEMAS[kind], schemas=SCHEMAS)
    if errors:
        raise Refused("%s: %s" % (kind, "; ".join(errors)))
    return value


def earlier(previous, now: str) -> list:
    """The pass records that ran before `now`, oldest first; a record whose time is no moment is passed over."""
    found = [r for r in previous or [] if isinstance(r, dict) and _moment(r.get("now")) is not None
             and r["now"] < now]
    return sorted(found, key=lambda r: r["now"])


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
    scopes += [("repo", held[repo] if repo in held else object()) for repo in sorted(repos)]
    states = [(name, _scope(value)) for name, value in scopes]
    paused = sorted({name for name, state in states if state == "paused"})
    if paused:
        return True, paused
    unread = sorted({name for name, state in states if state == "unreadable"})
    if unread:
        return None, unread
    return False, []


def automatic_pause(runs: list, now: str, rule: dict) -> bool:
    """Whether Admission pauses itself: environment faults in a row, since any Run last succeeded, from Runs on
    different items, inside the recent window (L-59). An old streak is outside the window; one item's is that item's."""
    recent = [r for r in runs if r["status"] == "completed" and _seconds(now, r["started_at"]) is not None
              and 0 <= _seconds(now, r["started_at"]) <= rule["window_seconds"]]
    recent.sort(key=lambda r: r["started_at"])
    succeeded = [i for i, r in enumerate(recent) if r["conclusion"] == "success"]
    since = recent[succeeded[-1] + 1:] if succeeded else recent
    faults = [r for r in since if r["outcome"] == ENVIRONMENT]
    items = {(r["item"]["repo"], r["item"]["type"], r["item"]["number"]) for r in faults}
    return len(faults) >= rule["faults"] and len(items) >= rule["items"]


def model_deferred_until(runs: list, now: str, window: int):
    """Until when model Runs wait after the newest capacity fault: its start and the window, or None once that is
    past (design section 3.10)."""
    starts = [r["started_at"] for r in runs if r["status"] == "completed" and r["outcome"] == CAPACITY
              and _moment(r["started_at"]) is not None]
    if not starts:
        return None
    until = _text(_moment(max(starts)) + datetime.timedelta(seconds=window))
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
        if _seconds(later, record["now"]) > gap:
            return later
        later = record["now"]
    oldest = before[0]["context"]["passes_since"]
    return oldest if _moment(oldest) is not None else None


def wait_before_reading(previous, now: str, config: dict) -> int:
    """Seconds to wait before this pass reads: none sooner than the gap after the last pass's read began, whatever
    started it (decision 0043). If the records cannot be read, the whole gap."""
    gap = config["controller"]["read_gap_seconds"]
    if previous is None:
        return gap
    before = earlier(previous, now)
    if not before:
        return 0 if not previous else gap
    last = before[-1]
    began = min([r["date"] for r in last["reads"] if _moment(r["date"]) is not None] or [last["now"]])
    return max(0, gap - _seconds(now, began))


def _key(item: dict) -> str:
    kind = "pull" if item["type"] == "pull_request" else "issues"
    return "https://github.com/%s/%s/%d" % (item["repo"], kind, item["number"])


def _run_name(item: dict, intent: str, role: str, content: str, run: str) -> str:
    return _checked("sf %s#%d %s %s %s %s" % (item["repo"], item["number"], intent, role, content, run), "run-name")


def _next_actor(d: dict, feed: dict):
    """Who acts next, read from the Decision's outcome, then its attention class, through config/feed.json alone."""
    rules = feed["next_actor"]
    for row in rules["by_outcome"]:
        if d["outcome"] in row["outcome"]:
            return row["actor"]
    for row in rules["by_attention"]:
        if row["attention"] == d["attention"]:
            if row["actor"] != "by_state":
                return row["actor"]
            for by in rules["by_state"]["rows"]:
                if by["state"] == d["state"]:
                    return by["actor"]
            return rules["by_state"]["default"]
    return None


def _asked(d: dict, feed: dict):
    """What a person is asked, from config/feed.json's row for the reason, only when the item needs one."""
    if d["attention"] != t.NEEDS_YOU:
        return None
    for row in feed["decision_required"]:
        if row["reason"] == d["reason"]:
            return {"question": row["question"], "choices": list(row["choices"]), "evidence": list(d["evidence"])}
    return None


def _age(entry: dict, record: dict, before: list) -> float:
    """Hours the item has been in its State, by the pass records: since the first of the passes in a row, ending with
    this one, that read it in that State."""
    item, state = entry["decision"]["item"], entry["decision"]["state"]
    since = record["now"]
    for older in reversed(before):
        seen = [e for e in older["pull_requests"] + older["issues"] if e["decision"]["item"] == item]
        if not seen or seen[0]["decision"]["state"] != state:
            break
        since = older["now"]
    return round(_seconds(record["now"], since) / 3600.0, 2)


def view(record: dict, before: list, titles: dict, config: dict) -> dict:
    """The feed's two files from one pass record and the records before it (decision 0039). Nothing else is read, so a
    view rebuilt from the records equals the view written pass by pass (decision 0002)."""
    feed = config["feed"]
    items = []
    for entry in record["pull_requests"] + record["issues"]:
        facts, d = entry["facts"], entry["decision"]
        if facts["state"] != "open":
            continue
        mine = [r for r in record["runs"] if r["item"] == d["item"]]
        intents = sorted({r["intent"] for r in mine})
        items.append({
            "item": d["item"], "state": d["state"], "reason": d["reason"], "attention": d["attention"],
            "evidence": list(d["evidence"]), "next_actor": _next_actor(d, feed), "decision_required": _asked(d, feed),
            "content_id": facts.get("content_id"), "age_hours": _age(entry, record, before),
            "attempts": [{"intent": i, "count": len([r for r in mine if r["intent"] == i])} for i in intents],
            "runs": len(mine), "cost_usd": None, "sources": sorted({r["run"] for r in mine}), "url": _key(d["item"]),
            "untrusted": {"title": titles.get(_key(d["item"]), "")}})
    reach = min([r["started_at"] for r in record["runs"]] or [record["now"]])
    meta = {"schema": "view-meta/1", "pass": record["pass"], "release": record["release"],
            "written_at": record["now"], "reaches_back_to": reach}
    listed = {"schema": "view-items/1", "pass": record["pass"], "release": record["release"], "items": items}
    return {"meta": _checked(meta, "view-meta"), "items": _checked(listed, "view-items")}


def rebuild(records: list, titles: dict, config: dict) -> list:
    """The view as each pass record leaves it, rebuilt from the records alone, oldest first."""
    ordered = sorted(records, key=lambda r: r["now"])
    return [view(r, [e for e in ordered if e["now"] < r["now"]], titles, config) for r in ordered]


def _threshold(value, limit) -> dict:
    return {"value": value, "limit": limit, "met": None if value is None else value <= limit}


def _delay_p95(records: list):
    """The 95th percentile of minutes from a change to the first pass that read it: a push to a pull request, or a
    change to an issue's content, made after the pass before. None when no change was read."""
    delays = []
    for before, record in zip(records, records[1:]):
        for entry in record["pull_requests"] + record["issues"]:
            facts = entry["facts"]
            at = facts.get("last_push_at") if "last_push_at" in facts else facts.get("content_changed_at")
            if _moment(at) is not None and before["now"] < at <= record["now"]:
                delays.append(_seconds(record["now"], at))
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
    share = round(factory / org, 4) if _number(factory) and _number(org) and factory >= 0 and org > 0 else None
    points = usage.get("graphql_points_peak_hour")
    points = points if _number(points) and points >= 0 else None
    return {"job_minutes_share": _threshold(share, rule["job_minutes_share"]),
            "graphql_points_per_hour": _threshold(points, rule["graphql_points_per_hour"]),
            "decision_delay_p95_minutes": _threshold(_delay_p95(window), rule["decision_delay_p95_minutes"])}


def health(record: dict, before: list, pause: tuple, automatic: bool, alerts: list, usage, config: dict) -> dict:
    rules = config["controller"]
    # Paused by the scopes that pause and by the faults, unreadable by the scopes that cannot be read, or neither.
    paused, sources = pause
    if paused or automatic:
        state, by = "paused", (list(sources) if paused else []) + ([ENVIRONMENT] if automatic else [])
    elif paused is None:
        state, by = "unreadable", list(sources)
    else:
        state, by = "none", []
    window = [r for r in before if _seconds(record["now"], r["now"]) <= rules["thresholds"]["window_seconds"]]
    window.append(record)
    successors = 0
    for older in reversed(window):
        if older["started_by"] != "successor":
            break
        successors += 1
    recent = max(rules["capacity_window_seconds"], rules["automatic_pause"]["window_seconds"])
    faults = [{"run": r["run"], "item": r["item"], "outcome": r["outcome"], "at": r["started_at"]}
              for r in record["runs"] if r["outcome"] in (CAPACITY, ENVIRONMENT)
              and _seconds(record["now"], r["started_at"]) is not None
              and 0 <= _seconds(record["now"], r["started_at"]) <= recent]
    doc = {"schema": "health/1", "pass": record["pass"], "release": record["release"], "written_at": record["now"],
           "last_pass_at": record["now"], "previous_pass_at": before[-1]["now"] if before else None,
           "relay_started_at": None, "pause": {"state": state, "by": by},
           "chain": {"since": record["context"]["passes_since"], "started_by": record["started_by"],
                     "successors": successors},
           "starts": {code: len([r for r in window if r["started_by"] == code]) for code in STARTS},
           "faults": faults, "alerts": alerts,
           "thresholds": thresholds(window, usage, rules["thresholds"])}
    return _checked(doc, "health")


def run(reads: dict, config: dict, now: str, previous, mint) -> dict:
    """One pass: the record, the Runs to dispatch, the acts, the view, the alerts and whether a successor starts."""
    rules = config["controller"]
    before = earlier(previous, now)
    pulls = copy.deepcopy(reads["pull_requests"])
    issues = copy.deepcopy(reads["issues"])
    repos = {e["facts"]["item"]["repo"] for e in pulls + issues}

    records = reads.get("records")
    readable = (isinstance(records, dict) and isinstance(records.get("runs"), list)
                and isinstance(records.get("unidentified"), list) and isinstance(records.get("reads"), list))
    runs = copy.deepcopy(records["runs"]) if readable else []
    whole = readable and records.get("complete") is True
    pause = human_pause(reads.get("pause"), repos)
    automatic = automatic_pause(runs, now, rules["automatic_pause"])
    context = {
        "paused": True if automatic else pause[0],
        "active_runs": len([r for r in runs if r["status"] != "completed"]) if whole else None,
        "model_deferred_until": model_deferred_until(runs, now, rules["capacity_window_seconds"]) if whole else None,
        "passes_since": passes_since(before, previous, now, rules["not_run_seconds"]),
        "unidentified_runs": list(records["unidentified"]) if readable else None,
    }

    def asked(entries: list, decide, lifecycle: dict, kind: str) -> list:
        kernel = dict(config["kernel"], lifecycle=lifecycle)
        out = []
        for entry in entries:
            # Facts the port gave that are not facts are refused before the Kernel sees them: no record could hold them.
            facts = _checked(entry["facts"], kind)
            facts["complete"] = dict(facts.get("complete") or {})
            # The facts port reads no run: the records port's list says whether the Runs were read whole.
            facts["complete"]["runs"] = facts["complete"].get("runs") is True and whole
            d = decide(facts, runs, context, kernel, now)
            minted = d["outcome"] == t.ADMIT or d.get("action") == "issue_approval"
            out.append({"facts": facts, "decision": d, "run": mint("r") if minted else None})
        return out

    record = {"schema": "pass/1", "pass": mint("p"), "release": config["release"], "now": now,
              "started_by": started_by(reads.get("started"), rules["accounts"]), "context": context, "runs": runs,
              "reads": (copy.deepcopy(records["reads"]) if readable else [])
              + [{"read": "facts", "date": r["date"], "age": r["age"]} for r in reads.get("facts_reads") or []],
              "pull_requests": asked(pulls, pull_request.decide, config["lifecycles"]["pull_request"], "facts"),
              "issues": asked(issues, issue.decide, config["lifecycles"]["issue"], "issue-facts")}
    _checked(record, "pass")
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

    # One cause, one alert, however many items it defers (L-48); an unreadable Pause is one, and so is the automatic one.
    causes = {e["decision"]["reason"] for e in entries} & t.SCOPE_DEFERRALS
    causes |= {"pause_unreadable"} if context["paused"] is None else set()
    causes |= {ENVIRONMENT} if automatic else set()
    alerts = sorted(causes)
    gap = bool(before) and _seconds(now, before[-1]["now"]) > rules["not_run_seconds"]
    titles = {_key(e["facts"]["item"]): e.get("title") if isinstance(e.get("title"), str) else ""
              for e in reads["pull_requests"] + reads["issues"]}
    feed = view(record, before, titles, config)
    feed["health"] = health(record, before, pause, automatic, alerts, reads.get("usage"), config)
    # A successor only for an item due at the pass's end: an act made here, whose next Decision is due at once. A Run's
    # end starts the next pass itself, and a pass deferred by a Run it cannot name starts none (decisions 0036, 0043).
    successor = bool(acts) and context["unidentified_runs"] == []
    return {"record": record, "dispatch": dispatch, "acts": acts, "view": feed, "alerts": alerts,
            "cleared": [NOT_RUN] if gap else [], "successor": successor}
