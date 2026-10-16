"""Derive the State of a pull request from facts and run records.

State is never stored. This function is the only definition of it.
"""
from __future__ import annotations

from kernel import terms as t


def incomplete(facts: dict) -> list:
    """Names of the fact lists that were not read in full.

    A list is whole only if its flag is exactly true. A flag that is missing,
    or is anything else, is not given a default: the list is unreadable.
    """
    flags = facts.get("complete")
    flags = flags if isinstance(flags, dict) else {}
    return [name for name in t.READ_IN_FULL if flags.get(name) is not True]


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


def check_reading(check: dict, config: dict) -> str:
    """What one check says: 'passing', 'failing', 'pending' or 'unreadable'.

    The facts carry GitHub's own conclusion, and the configuration's map says
    what each means. A conclusion the map does not name is unreadable: a Lens
    that gave no verdict has not passed the content (I-27). The caller reads
    any other value as unreadable too.
    """
    return config["check_conclusions"].get(check["conclusion"], "unreadable")


def named_for(check: dict, lens: dict) -> bool:
    """Whether `check` carries the name of the required Lens `lens`'s check run, exactly as the configuration gives it.

    The facts give each check run the name GitHub gives it, and nothing maps it: a job named for the Lens itself, or
    for its check in another case, is some other check.
    """
    return check.get("name") == lens["check"]


def reports_for(check: dict, lens: dict) -> bool:
    """Whether `check` reports for the required Lens `lens`: its check's name, from the App the configuration names.

    An App is an id that is a whole number, in the facts and in the configuration: never true, nor 15368.0.
    """
    app = check.get("app_id")
    return named_for(check, lens) and type(app) is int and type(lens["app_id"]) is int and app == lens["app_id"]


def foreign_checks(checks: list, config: dict) -> list:
    """Each check under a required deterministic Lens's check name that the Lens's own App did not report, as evidence.

    Any App with checks: write can post a check under any name; the ruleset pins `verify` to its App, and the
    Kernel pins every required Lens. Such a check makes its Lens unreadable whatever it, or the Lens's own checks,
    conclude (I-13). Each is given as `<lens>:from_app:<id>`, the id `unreadable` when it is not a whole number,
    so that the Maintainer can tell it from a check that gave no verdict.
    """
    out = []
    for lens in config["required_lenses"]["deterministic"]:
        for c in checks:
            if named_for(c, lens) and not reports_for(c, lens):
                app = c.get("app_id")
                said = "%s:from_app:%s" % (lens["lens"], app if type(app) is int else "unreadable")
                if said not in out:
                    out.append(said)
    return out


def lens_reading(checks: list, lens: dict, config: dict) -> str:
    """What a required deterministic Lens says, from every check its own App reports: as `check_reading` gives it.

    Another App's check under its check's name is read before any Lens (foreign_checks). Every check from its own App is
    read, never the last alone: any failing one fails the Lens; then any with no verdict leaves it unreadable;
    then any still running is a wait. It passes only when every one of them passes. A Lens that has not reported
    is pending.
    """
    mine = [c for c in checks if reports_for(c, lens)]
    if not mine:
        return "pending"
    readings = {check_reading(c, config) for c in mine}
    if "failing" in readings:
        return "failing"
    if readings - {"passing", "pending"}:
        return "unreadable"
    if "pending" in readings:
        return "pending"
    return "passing"


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


def is_person(actor) -> bool:
    """A person: an actor of kind `human` whose write access is exactly true. Nobody else is, whatever its access (I-28).

    The port tells the kinds apart from GitHub's account type and the configuration, never from a name's spelling
    (L-57), so an App, a Lens's App and the machine user are never a person.
    """
    return isinstance(actor, dict) and actor.get("kind") == "human" and actor.get("can_write") is True


def closed(th: dict) -> bool:
    """Whether a thread was resolved by someone who may close it (L-17).

    A person's thread is closed only by that person. A Lens's is closed only by that Lens's own App or by a person: no
    Role decides a Finding about its own work, so the author agent resolving the threads that hold it closes none.
    Resolved by anyone else, a thread stays open. A thread that gates nothing is closed by whoever resolves it.
    """
    if not th["resolved"]:
        return False
    opener, by = th["opened_by"], th["resolved_by"]
    if is_person(opener):
        return is_person(by) and by["name"] == opener["name"]
    if opener["kind"] == "lens":
        return is_person(by) or (by["kind"] == "lens" and by["name"] == opener["name"])
    return True


def gating_threads(facts: dict, config: dict) -> list:
    """Open threads that hold the pull request.

    A person with write access always gates. A Lens gates only if it is
    required and its Finding is blocking or major, or is a security Finding
    of any severity. Everyone else informs. A Finding that does not gate is
    an annotation on its Lens's check run, and closes when the Lens stops
    reporting it. A Finding a model Lens has raised gates whatever the class:
    a dependency update needs no review, and still answers one it was given.
    A thread resolved by someone who may not close it is open (closed).
    """
    required = set(config["required_lenses"]["model"])
    out = []
    for th in facts["threads"]:
        if closed(th):
            continue
        by = th["opened_by"]
        if is_person(by):
            out.append(th)
        elif by["kind"] == "lens" and by["name"] in required and (
                th["category"] == t.SECURITY or th["severity"] in t.GATING_SEVERITIES):
            out.append(th)
    return out


def unreadable_thread(th: dict, lenses: list, facts: dict, config: dict) -> bool:
    """Whether a thread cannot be read whole: who opened it, whether it is resolved and by whom, or, on a required
    Lens's open thread, its category or severity.

    Who opened and who resolved a thread decide whether it is closed (closed), so a thread with either unread could be
    a person's left open. Who resolved a thread belongs to a resolved one alone, as who dismissed a review does.
    """
    if not readable_actor(th.get("opened_by"), facts, config) or type(th.get("resolved")) is not bool:
        return True
    if th["resolved"] and not readable_actor(th.get("resolved_by"), facts, config):
        return True
    if not th["resolved"] and th.get("resolved_by") is not None:
        return True
    return (not closed(th) and th["opened_by"]["kind"] == "lens" and th["opened_by"]["name"] in lenses
            and (th.get("category") not in t.CATEGORIES or th.get("severity") not in t.SEVERITIES))


def unreadable_threads(facts: dict, config: dict) -> list:
    """The ids of threads that cannot be read whole (unreadable_thread).

    Whether a required Lens's thread gates is read from its category and severity, and a security Finding gates at any
    severity, so one that is missing, null, or a word the Kernel does not know could hide a gate: nothing may converge
    on it (I-13). A Lens that is not required gates nothing, and may write both only as prose. A person's thread gates
    whatever it says. A model Lens's thread is read whatever the class, as it gates whatever the class (gating_threads).
    """
    lenses = config["required_lenses"]["model"]
    return [th["id"] for th in facts["threads"] if unreadable_thread(th, lenses, facts, config)]


def is_leap(year: int) -> bool:
    every, unless, still = t.LEAP_YEARS
    return year % every == 0 and (year % unless != 0 or year % still == 0)


def fields(time: str) -> tuple:
    """(year, month, day, hour, minute, second) of a time in the one text format."""
    date, clock = time[:-1].split("T")
    return tuple(int(part) for part in date.split("-")) + tuple(int(part) for part in clock.split(":"))


def days_in(year: int, month: int) -> int:
    """The days of a month, from the pinned calendar."""
    ends = t.DAYS_BEFORE_MONTH[1:] + (t.DAYS_PER_YEAR,)
    return ends[month - 1] - t.DAYS_BEFORE_MONTH[month - 1] + int(is_leap(year) and month == t.FEBRUARY)


def is_time(value) -> bool:
    """A real moment in the one text format: the month 1 to 12, a day its month has, the hour under 24, and the minute
    and second under 60. Times compare as text, so the format is the contract; a time that is no moment is unreadable.
    """
    if not (isinstance(value, str) and len(value) == len(t.TIME_SHAPE)
            and all(c in t.DIGITS if shape == "9" else c == shape for c, shape in zip(value, t.TIME_SHAPE))):
        return False
    year, month, day, hour, minute, second = fields(value)
    return (1 <= month <= len(t.DAYS_BEFORE_MONTH) and 1 <= day <= days_in(year, month)
            and hour < t.HOURS_PER_DAY and minute < t.MINUTES_PER_HOUR and second < t.SECONDS_PER_MINUTE)


def seconds(time: str) -> int:
    """Seconds from the calendar's first day to `time`, a real moment (is_time): the Kernel reads no clock."""
    year, month, day, hour, minute, second = fields(time)
    every, unless, still = t.LEAP_YEARS
    past = year - 1
    days = past * t.DAYS_PER_YEAR + past // every - past // unless + past // still
    days += t.DAYS_BEFORE_MONTH[month - 1] + int(is_leap(year) and month > t.FEBRUARY) + day - 1
    return ((days * t.HOURS_PER_DAY + hour) * t.MINUTES_PER_HOUR + minute) * t.SECONDS_PER_MINUTE + second


def moves(actor) -> bool:
    """Whether what `actor` does moves an item: a person, a Lens's App, or the machine user, the Factory's approver.

    Never a stranger, nor any other App, which no configuration names: any App installed on the repo could keep a
    stalled item from showing (I-28).
    """
    return isinstance(actor, dict) and (actor.get("kind") in ("lens", t.MACHINE_USER) or is_person(actor))


def moved_at(facts: dict, runs: list, config: dict, now: str):
    """When the item last moved, or None if no time can be read.

    State is never stored (decision 0002), so the time an item entered its State is read as the newest time a writer,
    a Lens or the Factory moved it: a push, a required check's completion, a review or a thread by a writer, a Lens's
    App or the machine user (a gating thread is always one; moves), a writer's action and a Run on this item. A
    stranger's comment, another App's, or a check that is not required, moves nothing, or anyone could keep a stalled
    item from showing; nor does a check under a
    required Lens's check name from any App but that Lens's own (reports_for). A time that is not a real
    moment no later than `now` is passed over, so the wait counts from earlier: that shows more, never less.
    """
    required = config["required_lenses"]["deterministic"]
    times = [facts["last_push_at"], facts.get("last_writer_action_at")]
    times += [c.get("completed_at") for c in facts["checks"] if any(reports_for(c, lens) for lens in required)]
    times += [rv.get("submitted_at") for rv in facts["reviews"] if moves(rv.get("by"))]
    times += [th.get("opened_at") for th in facts["threads"] if moves(th.get("opened_by"))]
    times += [r["started_at"] for r in runs_on(runs, facts)]
    readable = [x for x in times if is_time(x) and x <= now]
    return max(readable) if readable else None


def stale(lifecycle: dict, state: str, moved, passes_since, now: str) -> bool:
    """Whether a wait in `state` has run past its Lifecycle's limit. Any Lifecycle: an issue's as well (I-1).

    The wait counts from `moved`, and no earlier than `passes_since`, the start of the current unbroken chain of
    passes: an outage of the poller is one health alert, not one for each item (§4.6). Either, if it is not a real
    moment no later than `now`, is passed over, which shows more, never less. So is a `now` that is no moment.
    """
    if not is_time(now):
        return True
    starts = [x for x in (moved, passes_since) if is_time(x) and x <= now]
    if not starts:
        return True
    waited = seconds(now) - seconds(max(starts))
    return waited > lifecycle["stale_after_minutes"][state] * t.SECONDS_PER_MINUTE


def readable_actor(actor, facts: dict, config: dict) -> bool:
    """Who acted, read whole: a kind the Kernel knows, a name, and write access exactly true or false.

    The kind must agree with the configuration and the class (I-28): the machine user is the approver the
    configuration names, and nobody else is; the author of an agent's or a dependency update's pull request is an App.
    Facts that say otherwise were misread, as a port that took a name's spelling for a kind would (L-57).
    """
    if not (isinstance(actor, dict) and actor.get("kind") in t.ACTOR_KINDS
            and isinstance(actor.get("name"), str) and actor["name"] != ""
            and type(actor.get("can_write")) is bool):
        return False
    if (actor["kind"] == t.MACHINE_USER) != (actor["name"] == config["approver"]):
        return False
    # GitHub gives no User a login with a bracket: a person named like an App's bot was misread. A name's spelling only
    # ever refuses an actor here; it never makes one a person (L-57).
    if actor["kind"] == "human" and actor["name"].endswith(t.BOT_SUFFIX):
        return False
    return not (facts["class"] in t.BOT_CLASSES and actor["name"] == facts["author"] and actor["kind"] != t.APP)


def unreadable_reviews(facts: dict, config: dict) -> bool:
    """Whether a review cannot be read whole: its author, state or time, or who dismissed it and what it was.

    Any of them could be a request for changes from a person with write access, so nothing
    may converge on it; a missing fact is never given a default (I-13).
    """
    for rv in facts["reviews"]:
        if not isinstance(rv, dict) or rv.get("state") not in t.REVIEW_STATES:
            return True
        if not readable_actor(rv.get("by"), facts, config):
            return True
        if not is_time(rv.get("submitted_at")):
            return True
        # Who dismissed a review, and what it was, belong to a dismissed review alone: the schema cannot say so.
        if rv["state"] != "dismissed" and (rv.get("dismissed_by") is not None or rv.get("dismissed_from") is not None):
            return True
        if rv["state"] == "dismissed" and not readable_actor(rv.get("dismissed_by"), facts, config):
            return True
        if rv["state"] == "dismissed" and rv.get("dismissed_from") not in t.DISMISSED_FROM:
            return True
    return False


def verdict_order(rv: dict) -> tuple:
    """When a review was made. A request for changes comes after anything else in the same second: fail closed."""
    return rv["submitted_at"], "changes_requested" in (rv["state"], rv.get("dismissed_from"))


def standing_requests(facts: dict) -> list:
    """Requests for changes that hold the pull request, one for each person with write access.

    A person's latest verdict counts; a review that only comments is none, dismissed or not. A
    request stands across new content, as GitHub keeps it, until that person approves or a person
    with write access dismisses it. An approval answers it even once dismissed, as when an App's
    push dismisses it as stale; it still approves no content. Only a person ends a request: a
    dismissal by an App, a Lens's App, the machine user or a stranger does not clear it, as the
    reviewer's App holds pull_requests: write, and no Role closes a person's objection (L-17); nor
    does anyone's approval but that person's. A request from anyone but a person gates nothing.
    """
    latest = {}
    for rv in sorted(facts["reviews"], key=verdict_order):
        if rv["state"] == "dismissed" and rv["dismissed_from"] == "commented":
            continue
        if is_person(rv["by"]) and rv["state"] != "commented":
            latest[rv["by"]["name"]] = rv
    out = []
    for name, rv in sorted(latest.items()):
        if rv["state"] == "dismissed":
            if rv["dismissed_from"] != "changes_requested":
                continue
            if is_person(rv["dismissed_by"]):
                continue
        elif rv["state"] != "changes_requested":
            continue
        out.append({"id": name, "by": rv["by"], "at": rv["submitted_at"]})
    return out


def gates(facts: dict, config: dict) -> list:
    """Every open Finding that holds the pull request, as {'id', 'by', 'at'}.

    A gating thread, and a request for changes from a person with write access, which gates as
    that person's thread does (decision 0007).
    """
    threads = [{"id": th["id"], "by": th["opened_by"], "at": th["opened_at"]} for th in gating_threads(facts, config)]
    return threads + standing_requests(facts)


def whose_turn(gate: dict, runs: list, config: dict) -> str:
    """Who must act on an open gate, a thread or a request for changes: 'author', 'owner' or 'human'.

    The author answers a gate with a Run after it was opened. The answer may
    be new content, so this cannot be read from "the last Run on this content".
    A thread still open after the owner has judged that answer was rejected,
    and is the author's again. A person's thread or request, once answered,
    waits for that person: no Role may close it.
    """
    answers = [r["started_at"] for r in runs
               if r["role"] == config["author_role"] and r["status"] == "completed"
               and r["conclusion"] == "success" and r["started_at"] > gate["at"]]
    if not answers:
        return "author"
    if gate["by"]["kind"] == "human":
        return "human"
    rulings = [r["started_at"] for r in runs
               if r["intent"] == "adjudicate-findings" and r["status"] == "completed"
               and r["conclusion"] == "success" and r["started_at"] > max(answers)]
    return "author" if rulings else "owner"


def unreadable_labels(facts: dict, config: dict) -> bool:
    """Whether an event of a control label cannot be read whole: what was done to it, by whom, and when.

    Each decides whether a Hold, hands-off or an admission binds, so nothing is decided on one (I-13). An event of
    another label is not read, but its label must be: it could be a control label's.
    """
    for ev in facts["label_events"]:
        if not isinstance(ev, dict) or not isinstance(ev.get("label"), str):
            return True
        if ev["label"] not in t.CONTROL_LABELS:
            continue
        if ev.get("action") not in t.LABEL_ACTIONS:
            return True
        if not is_time(ev.get("at")):
            return True
        if not readable_actor(ev.get("by"), facts, config):
            return True
    return False


def label_order(ev: dict) -> tuple:
    """When a label event happened. Which of two in the same second came first cannot be told, so each label is read
    the way that stops work, as verdict_order reads a review: a Hold or hands-off is placed last, and stands; an
    admission is placed first, and the removal ends it. Hands-off that stands on a tie is read as a Hold (tied)."""
    placed_last = ev["label"] != t.LABEL_ADMIT
    return ev["at"], (ev["action"] == "labeled") == placed_last


def tied(placed: dict, facts: dict) -> bool:
    """Whether a person's removal of the label `placed` placed came in the same second. Hands-off placed so is read as a
    Hold: standing, it could leave a queued item to merge, and ended, it could let the Factory act on an item a person
    marked, so either reading fails open somewhere. Anyone else's removal ends nothing, so it ties with nothing."""
    return any(ev["label"] == placed["label"] and ev["action"] == "unlabeled" and ev["at"] == placed["at"]
               and is_person(ev["by"]) for ev in facts["label_events"])


def standing_labels(facts: dict) -> dict:
    """Each control label that binds, with the event that placed it. The events must be readable (unreadable_labels).

    The timeline's events are read in the order they happened. A label binds from when anyone adds it until a person
    removes it: removed by anyone else, it binds as it was placed. What a person placed, only a person ends (L-17), and
    an App cannot release a Hold (L-02). Nor does anyone else placing it again replace a person's placement, so an App
    that takes a person's label off and puts it back changes nothing: who placed it, and when, is the person's.
    """
    out = {}
    for ev in sorted([ev for ev in facts["label_events"] if ev["label"] in t.CONTROL_LABELS], key=label_order):
        if ev["action"] == "labeled":
            if not (ev["label"] in out and is_person(out[ev["label"]]["by"]) and not is_person(ev["by"])):
                out[ev["label"]] = ev
        elif is_person(ev["by"]):
            out.pop(ev["label"], None)
    return out


def hands_off(facts: dict, config: dict) -> bool:
    """Whether hands-off binds: a person placed it, and the Factory never acts on the item. Placed by anyone else, it
    is read as a Hold, so an App cannot freeze an item in the merge queue, and so is one removed in the same second
    (tied). It is read only from label events read in full and whole: the timeline is paged oldest first, so a read
    cut short could drop a person's later removal.
    """
    if "timeline" in incomplete(facts) or unreadable_labels(facts, config):
        return False
    placed = standing_labels(facts).get(t.LABEL_HANDS_OFF)
    return placed is not None and is_person(placed["by"]) and not tied(placed, facts)


def admitted(facts: dict, labels: dict) -> bool:
    """An outside item is admitted only by a person with write access, after its author's latest push (I-25, I-36).

    `labels` are the control labels that bind (standing_labels). An admission anyone else placed admits nothing.
    """
    if facts["class"] != "outside":
        return True
    placed = labels.get(t.LABEL_ADMIT)
    if placed is None or not is_person(placed["by"]):
        return False
    return placed["at"] > facts["last_push_at"]


def standing_approval(facts: dict, config: dict):
    """The approver's undismissed approval of this content, if any.

    Only the approver's approval stands: the machine user's, which readable_actor holds to the approver's name, while
    it has write access, without which GitHub does not count it. A person's approval answers that person's request for
    changes, and approves no content.
    """
    for rv in facts["reviews"]:
        if (
            rv["by"]["kind"] == t.MACHINE_USER
            and rv["by"]["can_write"] is True
            and rv["state"] == "approved"
            and rv["content_id"] == facts["content_id"]
        ):
            return rv
    return None


def derive(facts: dict, runs: list, config: dict) -> dict:
    """Return {'state', 'reason', 'evidence'} for one pull request, and 'dequeue' when it must leave the merge queue.

    GitHub reads the reviews only as an item enters the queue (L-19). A queued item stays only while, read as if it
    were not queued, it would be approved and ready to merge. A wait that ends on its own is read past: a merge
    state GitHub has not worked out, which it reports each time the base moves, a required check not reported yet,
    and a required Lens that has not reported on this content. Any other reading takes it out, with that reading's
    State and reason: a lost approval and an open gate get codes of their own. An item that is ended or not served
    is left alone, and so is one a person marked hands-off, which the Factory never acts on.
    """
    d = reading(facts, runs, config, ())
    if d["state"] in t.TERMINAL or not facts["queue"] or hands_off(facts, config):
        return d
    d = reading(facts, runs, config, t.QUEUE_WAITS)
    if d["reason"] == "approved":
        return {"state": t.QUEUED, "reason": "in_merge_queue", "evidence": []}
    if d["reason"] == "approval_due":
        d = dict(d, reason="approval_lost")
    elif d["reason"] in t.GATE_REASONS:
        d = dict(d, reason="gate_open", evidence=[g["id"] for g in gates(facts, config)])
    return dict(d, dequeue=True)


def reading(facts: dict, runs: list, config: dict, past: tuple) -> dict:
    """Return {'state', 'reason', 'evidence'} for one pull request, read as if it were not in the merge queue.

    `past` names the waits to read past, by their reasons: none, or for a queued item `t.QUEUE_WAITS`.

    `state` is None when the facts of an open item are incomplete, or the
    merge state is not known: an incomplete read is an unreadable one, and
    nothing may be concluded from it.
    """
    if facts["state"] == "merged":
        return {"state": t.MERGED, "reason": "merged", "evidence": []}
    if facts["state"] == "closed":
        return {"state": t.CLOSED, "reason": "closed", "evidence": []}
    # A merged or closed item is read from no list. The list of Runs is read once a pass for every item.
    gaps = incomplete(facts)
    if gaps:
        return {"state": None, "reason": "facts_incomplete", "evidence": gaps}
    if not facts["targets_protected"]:
        return {"state": t.NOT_SERVED, "reason": "base_not_protected", "evidence": []}
    if facts["is_draft"]:
        return {"state": t.DRAFT, "reason": "draft", "evidence": []}

    # Who added or removed a control label decides whether it binds, so an event that cannot be read is read first.
    if unreadable_labels(facts, config):
        return {"state": None, "reason": "label_unreadable", "evidence": []}
    labels = standing_labels(facts)
    if hands_off(facts, config):
        return {"state": t.HELD, "reason": "hands_off", "evidence": [t.LABEL_HANDS_OFF]}
    # A Hold, and hands-off that anyone but a person placed, which is read as one.
    stops = [name for name in (t.LABEL_HOLD, t.LABEL_HANDS_OFF) if name in labels]
    if stops:
        return {"state": t.HELD, "reason": "human_hold", "evidence": stops}
    if not admitted(facts, labels):
        return {"state": t.HELD, "reason": "outside_not_admitted", "evidence": []}
    if facts["diff"]["files"] == 0:
        return {"state": t.HELD, "reason": "empty_diff", "evidence": []}
    if facts["diff"]["truncated"] or facts["diff"]["lines"] > config["limits"]["max_diff_lines"]:
        return {"state": t.HELD, "reason": "too_large", "evidence": []}
    # A review that cannot be read could be a writer's request for changes. It is read before anything
    # admits a Run or converges: an unreadable fact never yields an action (I-13), only a stop.
    if unreadable_reviews(facts, config):
        return {"state": None, "reason": "review_unreadable", "evidence": []}
    # So could a required Lens's thread whose category or severity cannot be read: a security Finding at any severity.
    unread = unreadable_threads(facts, config)
    if unread:
        return {"state": None, "reason": "thread_unreadable", "evidence": unread}
    # So could a check that another App posted under a required Lens's check name: it is read before any Lens's failure
    # and before a conflict, as a fix Run is an action. It stays on this head, so only a push clears it.
    foreign = foreign_checks(facts["checks"], config)
    if foreign:
        return {"state": t.VERIFYING, "reason": "check_unreadable", "evidence": foreign}
    # GitHub works the merge state out after a push. Until it has, it is unknown, and unreadable.
    mergeable = facts.get("mergeable")
    if mergeable is False:
        return {"state": t.ADDRESSING, "reason": "conflict", "evidence": []}
    if mergeable is not True and "mergeable_unreadable" not in past:
        return {"state": None, "reason": "mergeable_unreadable", "evidence": []}

    # Deterministic Lenses first: a model's time is not spent on content they reject.
    failed, waiting, unreadable = [], [], []
    for lens in config["required_lenses"]["deterministic"]:
        reading = lens_reading(facts["checks"], lens, config)
        if reading == "failing":
            failed.append(lens["lens"])
        elif reading == "pending":
            waiting.append(lens["lens"])
        elif reading != "passing":
            unreadable.append(lens["lens"])
    # A failure is readable and decisive: whatever a check with no verdict would say, the content goes
    # back to the author. Read otherwise, fail-fast's cancelled siblings would hold every failure (I-13).
    if failed:
        return {"state": t.ADDRESSING, "reason": "check_failed", "evidence": failed}
    # Otherwise a check that gave no verdict could have said anything, so nothing is decided on the others.
    if unreadable:
        return {"state": t.VERIFYING, "reason": "check_unreadable", "evidence": unreadable}
    if waiting and "awaiting_checks" not in past:
        return {"state": t.VERIFYING, "reason": "awaiting_checks", "evidence": waiting}

    # Then the model Lenses this item needs: a dependency update needs none, and skips nothing else.
    mine = runs_on(runs, facts)
    for lens in required_model_lenses(facts, config):
        if not reviewed_clean_or_not(mine, facts, lens) and "awaiting_review" not in past:
            return {"state": t.VERIFYING, "reason": "awaiting_review", "evidence": [lens]}

    # Every gate before the approval: a standing approval never passes over a person's objection.
    open_gates = gates(facts, config)
    if open_gates:
        turns = {g["id"]: whose_turn(g, mine, config) for g in open_gates}
        for_author = [gid for gid, who in turns.items() if who == "author"]
        for_owner = [gid for gid, who in turns.items() if who == "owner"]
        if for_author:
            human = any(g["by"]["kind"] == "human" for g in open_gates if g["id"] in for_author)
            return {"state": t.ADDRESSING, "reason": "human_finding" if human else "findings_open",
                    "evidence": for_author}
        if for_owner:
            return {"state": t.ADJUDICATING, "reason": "proposals_await_owner", "evidence": for_owner}
        return {"state": t.ADDRESSING, "reason": "awaiting_human", "evidence": sorted(turns)}

    # GitHub does not count an approval by the author or the last pusher, so nothing may merge on one (I-26). It is
    # a Hold the facts establish, read here so that a queued item leaves the queue on it too.
    if config["approver"] in (facts["author"], facts["last_pusher"]):
        return {"state": t.HELD, "reason": "approver_is_author_or_last_pusher", "evidence": []}
    approval = standing_approval(facts, config)
    if approval is not None:
        return {"state": t.CONVERGED, "reason": "approved", "evidence": [approval["commit"]]}
    return {"state": t.CONVERGED, "reason": "approval_due", "evidence": []}
