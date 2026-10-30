"""Derive the State of a pull request from facts and run records.

State is never stored. This function is the only definition of it.
"""
from __future__ import annotations

from kernel import terms as t
from kernel.gate import closed, gates, is_person, verdict_order


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


def readable_expired(facts: dict) -> bool:
    """Whether the facts say, as a list of run ids, which of the pull request's Lens Runs have an applied/1 past the
    artifact retention. Nothing is read from one that does not: none of them is read as none."""
    found = facts.get("expired_reviews")
    return isinstance(found, list) and all(isinstance(run, str) for run in found)


def review_expired(runs: list, facts: dict, role: str) -> bool:
    """Whether a Run of `role` whose applied/1 is past the artifact retention has no review of exactly this content
    that succeeded after it (issue 346). What it recorded can no longer be read, so its threads cannot be held to their
    Findings: its Lens's review of the current content is asked for again, and the expired record is never read as a
    whole one."""
    gone = [r["started_at"] for r in runs if r["role"] == role and r["run"] in facts["expired_reviews"]]
    if not gone:
        return False
    last = max(gone)
    return not any(r["role"] == role and r["intent"] == "review-change" and r["content_id"] == facts["content_id"]
                   and r["status"] == "completed" and r["conclusion"] == "success" and r["started_at"] > last
                   for r in runs)


def contradicts(run: dict, facts: dict) -> bool:
    """Whether `run`, a review of exactly this content, succeeded and yet names whose fault its failure was. A review
    reports only through a Run that succeeded (decision 0029), and one that failed names its fault, so this one can be
    read as neither: no report is read from it (I-13)."""
    return (run["intent"] == "review-change" and run["content_id"] == facts["content_id"]
            and run["status"] == "completed" and run["conclusion"] == "success" and run.get("outcome") is not None)


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


def from_its_app(check: dict, lens: dict) -> bool:
    """Whether `check` was reported by the App the configuration names for the required Lens `lens`.

    An App is an id that is a whole number, in the facts and in the configuration: never true, nor 15368.0.
    """
    app = check.get("app_id")
    return type(app) is int and type(lens["app_id"]) is int and app == lens["app_id"]


def from_its_workflow(check: dict, lens: dict) -> bool:
    """Whether `check` ran from the workflow file the configuration names for the required Lens `lens`, exactly.

    GitHub Actions is one App for every job in the repo, one a pull request adds on its own branch among them, so a
    Lens it runs is read only from its own file. A Lens no workflow runs names none, and its check must name none
    too. A check that carries no workflow at all was not read whole, and is never given one.
    """
    return "workflow" in check and check["workflow"] == lens["workflow"]


def shown_path(path, config: dict) -> str:
    """`path` as a Decision's evidence shows it: as it is only when it is in the form a Lens's workflow takes and no
    longer than the configuration's limit, and otherwise `unreadable`. A path is text from outside, so a look-alike of
    a Lens's own file, or a character that turns the text round, never reaches a Decision."""
    if not (isinstance(path, str) and path.startswith(t.WORKFLOW_DIR)
            and len(path) <= config["limits"]["max_path_length"]):
        return "unreadable"
    name = path[len(t.WORKFLOW_DIR):]
    for ending in t.WORKFLOW_ENDINGS:
        stem = name[:-len(ending)]
        if name.endswith(ending) and stem != "" and all(c in t.FILE_NAME_CHARS for c in stem):
            return path
    return "unreadable"


def reports_for(check: dict, lens: dict) -> bool:
    """Whether `check` reports for the required Lens `lens`: its check's name, from the App and the workflow file the
    configuration names."""
    return named_for(check, lens) and from_its_app(check, lens) and from_its_workflow(check, lens)


def foreign_checks(checks: list, config: dict) -> list:
    """Each check under a required deterministic Lens's check name that the Lens's own App, or its own workflow file,
    did not report, as evidence.

    Any App with checks: write can post a check under any name, and GitHub Actions runs any job a pull request adds; the
    ruleset pins `verify` to its App, and the Kernel pins every required Lens to its App and its file. Such a check
    makes its Lens unreadable whatever it, or the Lens's own checks, conclude (I-13). One from another App is given as
    `<lens>:from_app:<id>`, the id `unreadable` when it is not a whole number; one from the Lens's App and another
    file as `<lens>:from_workflow:<path>`, the path `unreadable` when no file was read or it is not in the form a
    Lens's workflow takes (shown_path). So the Maintainer can tell it from a check that gave no verdict.
    """
    out = []
    for lens in config["required_lenses"]["deterministic"]:
        for c in checks:
            if not named_for(c, lens) or reports_for(c, lens):
                continue
            if not from_its_app(c, lens):
                app = c.get("app_id")
                said = "%s:from_app:%s" % (lens["lens"], app if type(app) is int else "unreadable")
            else:
                said = "%s:from_workflow:%s" % (lens["lens"], shown_path(c.get("workflow"), config))
            if said not in out:
                out.append(said)
    return out


def lens_reading(checks: list, lens: dict, config: dict) -> str:
    """What a required deterministic Lens says, from every check its own App and workflow file report: as
    `check_reading` gives it.

    Another App's check, or another file's, under its check's name is read before any Lens (foreign_checks). Every check
    from its own App and file is read, never the last alone: any failing one fails the Lens; then any with no verdict
    leaves it unreadable; then any still running is a wait. It passes only when every one of them passes. A Lens that
    has not reported is pending.
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


def readable_name(path) -> bool:
    """Whether `path` is a path from the top of the repo: text whose every name is a name. None is empty, so it is not
    empty, does not start or end with the separator or double it; and none is `.` or `..`."""
    return isinstance(path, str) and not any(name in t.NOT_A_NAME for name in path.split(t.SEPARATOR))


def readable_file(entry) -> bool:
    """One file the pull request changes, read whole: its `path`, and `previous`, the path it had before a rename or a
    copy, null for any other change. Neither is given a default."""
    return (isinstance(entry, dict) and readable_name(entry.get("path")) and "previous" in entry
            and (entry["previous"] is None or readable_name(entry["previous"])))


def readable_paths(changed, files: int) -> bool:
    """Whether the files the pull request changes can be read whole: one record for each of the diff's `files`, no
    more and no fewer, each by its own path once (readable_file). A path that cannot be read could be a protected one
    read as another, and a list of another length left a file out or misread one, though it says it was read in full
    (I-13). Whether it was read in full is `complete.changed_paths`, read with the other flags."""
    if not (isinstance(changed, list) and all(readable_file(entry) for entry in changed)):
        return False
    paths = [entry["path"] for entry in changed]
    return len(changed) == files and len(set(paths)) == len(paths)


def names(changed: list) -> list:
    """Every path the pull request changes, and every path a renamed or copied file had before: either may be on the
    list, as a file moved onto it or off it changes it. The records must be readable (readable_paths)."""
    return [entry["path"] for entry in changed] + [entry["previous"] for entry in changed if entry["previous"] is not None]


def readable_pattern(pattern) -> bool:
    """A protected path or a Lens's input in the shape config/hooks.json gives one: a path (readable_name), with a final
    separator for a directory. One with an empty, `.` or `..` name, or that starts with the separator, matches nothing,
    so read as a pattern it would let a change to the rules through."""
    if not isinstance(pattern, str):
        return False
    return readable_name(pattern[:-1] if pattern.endswith(t.SEPARATOR) else pattern)


def readable_rules(config: dict) -> bool:
    """Whether the protected paths and Lenses' inputs the Kernel is given can be read, and the model Lenses' own inputs
    among them: each a list of at least one pattern, each in its shape (readable_pattern). The Controller builds both
    from the base branch's config/hooks.json, never the head's, by one function (decision 0020, issue 140). A list that
    is empty, or not there, would let a change to the Factory's own rules, or to what a model Lens is given, pass as any
    other (I-13)."""
    return all(isinstance(rules, list) and len(rules) > 0 and all(readable_pattern(p) for p in rules)
               for rules in (config.get("protected_paths"), config.get("model_lens_inputs")))


def fits(pattern: str, path: str) -> bool:
    """Whether `path` fits `pattern` whole, in any case: each wildcard stands for any run of characters within one
    name, none included, and every other character for itself. It is given only a stretch of the path with as many
    names as the pattern's run (reached), so the separators are the pattern's own and no wildcard can stand for one."""
    pattern, path = pattern.casefold(), path.casefold()
    pieces = pattern.split(t.WILDCARD)
    if len(pieces) == 1:
        return path == pattern
    if not path.startswith(pieces[0]):
        return False
    at = len(pieces[0])
    # The leftmost place for each piece between two wildcards leaves the most for the rest, and the least for a
    # wildcard to stand for.
    for piece in pieces[1:-1]:
        found = path.find(piece, at)
        if found < 0:
            return False
        at = found + len(piece)
    end = len(path) - len(pieces[-1])
    return end >= at and path.endswith(pieces[-1])


def runs_of(pattern: str) -> list:
    """`pattern`'s names in order, each run of them between two `**` joined again by the separator, and each `**` that
    is a whole name alone."""
    out = []
    for name in pattern.split(t.SEPARATOR):
        if name != t.ANY_NAMES and out and out[-1] != t.ANY_NAMES:
            out = out[:-1] + [out[-1] + t.SEPARATOR + name]
        else:
            out = out + [name]
    return out


def reached(pattern: str, path: str) -> list:
    """Each count of `path`'s first names that `pattern` names whole, from none up. A run of the pattern's names stands
    for as many names of the path (fits), and `**` as a whole name for any run of names, none included."""
    names_ = path.split(t.SEPARATOR)
    counts = [0]
    for run in runs_of(pattern):
        if run == t.ANY_NAMES:
            counts = list(range(min(counts), len(names_) + 1)) if counts else []
            continue
        size = run.count(t.SEPARATOR) + 1
        counts = [n + size for n in counts
                  if n + size <= len(names_) and fits(run, t.SEPARATOR.join(names_[n:n + size]))]
    return counts


def matches(pattern: str, path: str) -> bool:
    """Whether `path`, one the pull request changes, is what `pattern` names: a protected path or a Lens's input, in
    the one syntax of config/hooks.json, as the session hooks read it (tools/hooks/protected.py, entries), or a path a
    rubric's criterion applies to. A final separator names the directory and everything below it."""
    whole = pattern.rstrip(t.SEPARATOR)
    counts = reached(whole, path)
    if whole != pattern:
        return any(n > 0 for n in counts)
    return path.count(t.SEPARATOR) + 1 in counts


def touched(facts: dict, config: dict) -> list:
    """Each protected path and Lens's input the configuration names that a path this pull request changes is, as the
    configuration gives it, once, in its order: the Factory's own rules, or what a Lens reads to judge the change. The
    paths must be readable (readable_paths). A Decision names the pattern, never the path, which is text from outside.
    """
    changed = names(facts["changed_paths"])
    return [p for p in dict.fromkeys(config["protected_paths"]) if any(matches(p, path) for path in changed)]


def lens_inputs_touched(facts: dict, config: dict) -> list:
    """Each model Lens's own input this pull request changes, as the configuration names it, once, in its order: the
    Role's manifest and prompt, its rubric, and what the Harness gives it and takes back (issue 140)."""
    changed = names(facts["changed_paths"])
    return [p for p in dict.fromkeys(config["model_lens_inputs"]) if any(matches(p, path) for path in changed)]


def judged_by_a_person(facts: dict) -> bool:
    """Whether a person has judged this head, so that no model Lens is the only judge of a change to its own inputs: an
    approval of this content that stands, by a person with write access other than its author and its last pusher
    (issue 140). The machine user's never counts, whoever made it: the Factory's approving act makes it too, and "Only a
    different person with write can approve" (the Maintainer, 2026-10-22). That person's latest verdict counts, as for a
    request for changes (gate): an approval a later request supersedes is none, whoever dismissed the request. Only a
    person's dismissal ends an approval: an App's, a Lens's among them, ends nothing a person did (L-17). An author's own
    change is no judgment of a head, whoever pushed it: a session may push as the Maintainer (L-44)."""
    latest = {}
    for rv in sorted(facts["reviews"], key=verdict_order):
        if is_person(rv["by"]) and rv["state"] != "commented" and rv["dismissed_from"] != "commented":
            latest[rv["by"]["name"]] = rv
    for rv in latest.values():
        another = rv["by"]["name"] != facts["author"] and rv["by"]["name"] != facts["last_pusher"]
        standing = rv["state"] == "approved" or (rv["dismissed_from"] == "approved" and not is_person(rv["dismissed_by"]))
        if another and standing and rv["content_id"] == facts["content_id"]:
            return True
    return False


def required_model_lenses(facts: dict, config: dict) -> list:
    """The model Lenses whose review this pull request needs.

    A dependency update is judged by the deterministic Lenses alone. It is a
    pull request of a class the configuration names, whose head was pushed
    by the identity that opened it, and that changes nothing on the list:
    no protected path and no Lens's input (touched). A Lens is never the only
    judge of a change to what it reads. The class is worked out from who
    opened it; anyone else's push puts content of their own in it, and that
    is reviewed as any change is.
    """
    lenses = config["required_lenses"]
    if (facts["class"] in lenses["model_not_required_for"] and facts["last_pusher"] == facts["author"]
            and not touched(facts, config)):
        return []
    return list(lenses["model"])


def unreadable_thread(th: dict, lenses: list, facts: dict, config: dict) -> bool:
    """Whether a thread cannot be read whole: who opened it, whether it is resolved and by whom, the Lens's ruling on
    it, or, on a required Lens's open thread, its category or severity.

    Who opened and who resolved a thread, and the ruling, decide whether it is closed (closed), so a thread with any of
    them unread could be a person's, or a Lens's, left open. Who resolved a thread belongs to a resolved one alone, as
    who dismissed a review does. A ruling that is null is read: the Lens decided nothing the port could hold.
    """
    if not readable_actor(th.get("opened_by"), facts, config) or type(th.get("resolved")) is not bool:
        return True
    if "ruling" not in th or (th["ruling"] is not None and th["ruling"] not in t.RULINGS):
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
    item from showing; nor does a check under a required Lens's check name from any App or workflow file but that
    Lens's own (reports_for). A time that is not a real moment no later than `now` is passed over, so the wait counts
    from earlier: that shows more, never less. A `now` that is no moment gives no time at all.
    """
    if not is_time(now):
        return None
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


def overdue(lifecycle, work_item: str, state: str, moved, passes_since, now: str) -> bool:
    """Whether a wait in `state` has run past its limit in the item's Lifecycle, for either kind of Work item. The
    Controller gives each item its own type's (decision 0028); one that is not this `work_item`'s, or whose limit for
    `state` is not a finite number of minutes, cannot be read, and is read as past its limit: that shows more, never
    less, and a pure function does not crash on it. A negative limit needs no test of its own: every wait is past it.
    An end the Lifecycle declares never waits."""
    if not (isinstance(lifecycle, dict) and lifecycle.get("work_item") == work_item):
        return True
    ends = lifecycle.get("terminal")
    if isinstance(ends, list) and state in ends:
        return False
    limits = lifecycle.get("stale_after_minutes")
    cap = limits.get(state) if isinstance(limits, dict) else None
    # A bool is no number of minutes; and NaN or an infinity is never less than infinity in size.
    if not (type(cap) in (int, float) and abs(cap) < float("inf")):
        return True
    return stale(lifecycle, state, moved, passes_since, now)


def run_deferral(_decision, facts: dict, state, evidence: list, context: dict, now: str, limits: dict):
    """The deferral that keeps a Run of either kind of Work item from starting now, or None. Capacity and the org's
    concurrency are not brakes: they bound no cycle (§4.1), and only defer, so each is read whole or fails closed, and
    nothing raises. The model provider's deadline that is missing, or that cannot be compared with `now`, either being
    no moment, is unreadable. So is a count of active Runs that is no whole number, a bool among them, or is below zero.
    A Run listed before its run-name may be the Run in flight on this item, so no Run is admitted until it can be named,
    and a list that cannot be read defers too (I-46, decision 0036)."""
    until = context.get("model_deferred_until", "unreadable")
    if until is not None and not (is_time(until) and is_time(now)):
        return _decision(facts, state, "capacity_unreadable", evidence, t.DEFER)
    if until is not None and until > now:
        return _decision(facts, state, "capacity", evidence, t.DEFER)
    active = context.get("active_runs")
    if type(active) is not int or active < 0:
        return _decision(facts, state, "capacity_unreadable", evidence, t.DEFER)
    if active >= limits["org_max_active_runs"]:
        return _decision(facts, state, "concurrency", evidence, t.DEFER)
    if unnamed_within(context, now, limits) != []:
        return _decision(facts, state, "run_unidentified", evidence, t.DEFER)
    past = unnamed_past(context, now, limits)
    if past and len(past) > limits["max_unnamed_runs"]:
        return _decision(facts, state, "runs_unnamed", evidence, t.DEFER)
    return None


def unnamed_runs(context: dict):
    """The context's unidentified Runs, each a run id of digits, when its record was created, and whether it is queued,
    in progress or completed; or None when the list or one of them cannot be read (decision 0036, issue 270)."""
    listed = context.get("unidentified_runs") if isinstance(context, dict) else None
    if not isinstance(listed, list):
        return None
    for entry in listed:
        if not (isinstance(entry, dict) and isinstance(entry.get("run"), str) and entry["run"]
                and all(c in t.DIGITS for c in entry["run"]) and is_time(entry.get("created_at"))
                and entry.get("status") in t.RUN_STATUSES):
            return None
    return listed


def unnamed_age(entry: dict, now: str) -> int:
    """How long ago the unidentified Run's record was created, in seconds; below zero where the clock reads it later."""
    return seconds(now) - seconds(entry["created_at"])


def unnamed_window(limits: dict):
    """max_unnamed_run_seconds and max_unnamed_runs, each a whole number of at least one, or None."""
    if not isinstance(limits, dict):
        return None
    window, most = limits.get("max_unnamed_run_seconds"), limits.get("max_unnamed_runs")
    if not (type(window) is int and window >= 1 and type(most) is int and most >= 1):
        return None
    return window


def unnamed_within(context: dict, now: str, limits: dict):
    """The unidentified Runs that defer every admission, by run id: each inside max_unnamed_run_seconds of its creation,
    which may yet be named as a Run in flight, and each not yet completed, whatever its age, which may be a Run on an
    item running now; or None when the list, a Run of it, the limits or `now` cannot be read. A completed one older
    than the window is no Run waiting for its name: P-17 saw a name listed within 3.7 s (issue 270)."""
    listed = unnamed_runs(context)
    if listed == []:
        return []
    window = unnamed_window(limits)
    if listed is None or window is None or not is_time(now):
        return None
    return [entry["run"] for entry in listed
            if unnamed_age(entry, now) < window or entry["status"] != t.RUN_COMPLETED]


def unnamed_past(context: dict, now: str, limits: dict) -> list:
    """The unidentified Runs listed for max_unnamed_run_seconds or more, by run id, each once, in the order listed: the
    alerts of the whole scope. Read only where unnamed_within can read the list, and empty otherwise. A Run on an item
    among them is missing from that item's counts, so past max_unnamed_runs of them every Run defers (issue 270)."""
    listed, within = unnamed_runs(context), unnamed_within(context, now, limits)
    if listed is None or within is None:
        return []
    window, past = unnamed_window(limits), []
    for entry in listed:
        if unnamed_age(entry, now) >= window and entry["run"] not in past:
            past.append(entry["run"])
    return past


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
    """Whether a review cannot be read whole: its author, state or time, the commit and content it was given on, or
    who dismissed it and what it was, each of which is there even where it is null.

    Any of them could be a request for changes from a person with write access, or a person's approval of the
    acceptance contract or of this content, so nothing may converge on it; a missing fact is never given a default
    (I-13). An approval stands only if given after the last reopening (decision 0079), so a reopening's time that
    cannot be read leaves every review unread.
    """
    if "last_reopened_at" not in facts or not (facts["last_reopened_at"] is None or is_time(facts["last_reopened_at"])):
        return True
    for rv in facts["reviews"]:
        if not isinstance(rv, dict) or rv.get("state") not in t.REVIEW_STATES:
            return True
        if not readable_actor(rv.get("by"), facts, config):
            return True
        if not is_time(rv.get("submitted_at")):
            return True
        if not (isinstance(rv.get("commit"), str) and rv["commit"] != ""):
            return True
        if not in_form(rv.get("content_id"), t.CONTENT_PREFIX, t.HEX_DIGITS):
            return True
        if "dismissed_by" not in rv or "dismissed_from" not in rv:
            return True
        # Who dismissed a review, and what it was, belong to a dismissed review alone: the schema cannot say so.
        if rv["state"] != "dismissed" and (rv.get("dismissed_by") is not None or rv.get("dismissed_from") is not None):
            return True
        if rv["state"] == "dismissed" and not readable_actor(rv.get("dismissed_by"), facts, config):
            return True
        if rv["state"] == "dismissed" and rv.get("dismissed_from") not in t.DISMISSED_FROM:
            return True
    return False


def whose_turn(held: dict, runs: list, config: dict) -> str:
    """Who must act on `held`, an open gate: a thread or a request for changes. 'author', 'owner' or 'human'.

    The author answers a gate with a Run after it was opened. The answer may
    be new content, so this cannot be read from "the last Run on this content".
    A thread still open after the owner has judged that answer was rejected,
    and is the author's again. A person's thread or request, once answered,
    waits for that person: no Role may close it.
    """
    answers = [r["started_at"] for r in runs
               if r["role"] == config["author_role"] and r["status"] == "completed"
               and r["conclusion"] == "success" and r["started_at"] > held["at"]]
    if not answers:
        return "author"
    if held["by"]["kind"] == "human":
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


def in_form(value, prefix: str, digits: str) -> bool:
    """Whether `value` is a name in its one form: `prefix`, then at least one of `digits` and nothing else. A criterion's
    id is `AC-` and decimal digits; a content id is `sha256:` and lower-case hexadecimal digits, as the schema says."""
    return (isinstance(value, str) and value.startswith(prefix) and len(value) > len(prefix)
            and all(c in digits for c in value[len(prefix):]))


def readable_criteria(criteria) -> bool:
    """Whether the criteria of an approved contract can be read whole: at least one, each an object with an id in its
    form, given once, and a kind the Kernel knows. The kind says who may report a criterion's result (reporter)."""
    if not (isinstance(criteria, list) and criteria and all(isinstance(c, dict) for c in criteria)):
        return False
    ids = [c.get("id") for c in criteria]
    if not all(in_form(i, t.CRITERION_PREFIX, t.DIGITS) for i in ids) or len(set(ids)) != len(ids):
        return False
    return all(c.get("kind") in t.CRITERION_KINDS for c in criteria)


def is_digest(value) -> bool:
    """Whether `value` is an acceptance contract's digest in its one form: `sha256:` and a whole SHA-256, in lower-case
    hexadecimal (t.DIGEST_SHAPE). A digest cut short, or padded, could be read as the one approved."""
    return in_form(value, t.CONTENT_PREFIX, t.HEX_DIGITS) and len(value) == len(t.DIGEST_SHAPE)


def readable_approval(approved, facts: dict, config: dict) -> bool:
    """Whether the contract a person approved can be read whole: None, where nobody has approved one; or its digest
    (is_digest), the commit the approving review was given on, who approved it (readable_actor), and its criteria
    (readable_criteria)."""
    if approved is None:
        return True
    return (isinstance(approved, dict) and is_digest(approved.get("digest"))
            and isinstance(approved.get("commit"), str) and approved["commit"] != ""
            and readable_actor(approved.get("by"), facts, config) and readable_criteria(approved.get("criteria")))


def readable_contract(contract, facts: dict, config: dict) -> bool:
    """Whether an acceptance contract, as the facts carry it, can be read whole: the contract a person approved, or
    None (readable_approval); its digest at the head, in a content id's form, or None where the head carries none; and
    every result an object naming a criterion and a content in their forms. None of the three is given a default: a
    contract that says nothing of its approval or its head is not one that nobody approved or that was deleted. A
    result on this content is read further once the contract is known to count (misread_results). Whether it was read
    in full is `complete.acceptance`, read with the other flags."""
    if not (isinstance(contract, dict) and all(name in contract for name in ("approved", "head", "results"))):
        return False
    if not readable_approval(contract["approved"], facts, config):
        return False
    head, results = contract["head"], contract["results"]
    if not (head is None or is_digest(head)) or not isinstance(results, list):
        return False
    for ev in results:
        if not isinstance(ev, dict):
            return False
        if not in_form(ev.get("content_id"), t.CONTENT_PREFIX, t.HEX_DIGITS):
            return False
        if not in_form(ev.get("criterion"), t.CRITERION_PREFIX, t.DIGITS):
            return False
    return True


def misread_results(contract: dict, content: str) -> bool:
    """Whether a result on `content`, this content, was misread: it names a criterion the approved contract does not,
    says a word the Kernel does not know, or carries no check that reported it. Only this content's results are judged,
    so one on earlier content is not read further: a criterion the contract no longer lists, as after a waiver or a
    revision, is no misreading there. The contract must be readable, and approved (readable_contract)."""
    ids = [c["id"] for c in contract["approved"]["criteria"]]
    for ev in contract["results"]:
        if ev["content_id"] != content:
            continue
        if ev["criterion"] not in ids or ev.get("result") not in t.EVIDENCE_RESULTS:
            return True
        if not isinstance(ev.get("check"), dict):
            return True
    return False


def readable_reporters(config: dict) -> bool:
    """Whether the configuration's `acceptance_reporters` can be read: a map from a kind of criterion to the name of a
    Lens, or to None. Missing, or of any other shape, it could make a kind reported by anyone, or by nobody it names
    (I-13). A kind it leaves out has no reporter (reporter)."""
    reporters = config.get("acceptance_reporters")
    return isinstance(reporters, dict) and all(name is None or isinstance(name, str) for name in reporters.values())


def reporter(kind: str, config: dict):
    """The required deterministic Lens whose check alone reports a criterion of `kind`, as the configuration's
    `acceptance_reporters` names it, or None where no check may: a kind it names no Lens for, or names none at all.
    Only a person passes a criterion of kind human, whatever the configuration says (I-10)."""
    if kind == t.HUMAN_KIND:
        return None
    name = config["acceptance_reporters"].get(kind)
    return next((lens for lens in config["required_lenses"]["deterministic"] if lens["lens"] == name), None)


def foreign_results(contract: dict, facts: dict, config: dict) -> list:
    """Each result on this content that the check of its criterion's reporter did not report, as evidence.

    Any App with checks: write can report a result, the implementing Role's own among them, and GitHub Actions runs any
    job a pull request adds: no Role judges its own work (I-10). A result is read as the facts read a check, by
    reports_for, from the Lens the configuration names for its criterion's kind (reporter). One from another App is
    given as `<criterion>:from_app:<id>`, from the Lens's App and another workflow file as
    `<criterion>:from_workflow:<path>`, and from both under another check's name as `<criterion>:from_another_check`,
    in foreign_checks' forms; one for a kind no check reports, whoever reported it, as `<criterion>:no_reporter`. The
    contract must be readable, and approved; earlier content is not judged."""
    kinds = {c["id"]: c["kind"] for c in contract["approved"]["criteria"]}
    out = []
    for ev in contract["results"]:
        if ev["content_id"] != facts["content_id"]:
            continue
        lens, check = reporter(kinds[ev["criterion"]], config), ev["check"]
        if lens is None:
            said = "%s:no_reporter" % ev["criterion"]
        elif reports_for(ev["check"], lens):
            continue
        elif not from_its_app(check, lens):
            shown = check.get("app_id")
            said = "%s:from_app:%s" % (ev["criterion"], shown if type(shown) is int else "unreadable")
        elif not from_its_workflow(check, lens):
            said = "%s:from_workflow:%s" % (ev["criterion"], shown_path(check.get("workflow"), config))
        else:
            said = "%s:from_another_check" % ev["criterion"]
        if said not in out:
            out.append(said)
    return out


def contract_reading(facts: dict, config: dict):
    """What the acceptance contract's own identity says, as a reading, or None where it lets the item be read on.

    The contract that counts is the one a person approved, at one commit (§3.13, decision 0007): the head is the
    author's. So a contract no person approved, the machine user's or an App's approval among them, is a Hold; and so
    is a head whose contract differs from the approved one, a deleted one included, since a digest covers every path
    the contract protects (I-29, I-30). Before them, a contract that cannot be read; after them, a result on this
    content that was misread, or that its criterion's reporter did not report (foreign_results). Each admits nothing.
    Whether there is a contract at all is the linked issue's, never the head's: null is no contract, read in full. A
    fact read from outside is never given a default, so facts with no `acceptance` at all are unreadable."""
    unreadable = {"state": None, "reason": "acceptance_unreadable", "evidence": []}
    if "acceptance" not in facts:
        return unreadable
    contract = facts["acceptance"]
    if contract is None:
        return None
    if not readable_reporters(config):
        return {"state": None, "reason": "acceptance_reporters_unreadable", "evidence": []}
    if not readable_contract(contract, facts, config):
        return unreadable
    approved = contract["approved"]
    if approved is None or not is_person(approved["by"]):
        return {"state": t.HELD, "reason": "contract_not_approved", "evidence": []}
    if not approval_stands(approved, facts):
        return {"state": t.HELD, "reason": "contract_not_approved", "evidence": []}
    if contract["head"] != approved["digest"]:
        return {"state": t.HELD, "reason": "contract_changed", "evidence": []}
    if misread_results(contract, facts["content_id"]):
        return unreadable
    impostors = foreign_results(contract, facts, config)
    if impostors:
        return {"state": None, "reason": "acceptance_unreadable", "evidence": impostors}
    return None


def approval_stands(approved: dict, facts: dict) -> bool:
    """Whether the approval the facts say a person gave the contract is a review GitHub holds: by that person, with
    write access, approving, on the commit the contract was approved at, and not dismissed by a person. An App's
    dismissal, a stale one among them, ends nothing a person did (L-17). The reviews must be readable
    (unreadable_reviews). Otherwise the approval is the port's word alone, and no person approved anything."""
    for rv in facts["reviews"]:
        theirs = is_person(rv["by"]) and rv["by"]["name"] == approved["by"]["name"]
        if theirs and rv["commit"] == approved["commit"] and (
                rv["state"] == "approved" or (rv["dismissed_from"] == "approved" and not is_person(rv["dismissed_by"]))):
            return True
    return False


def confirmed_by_a_person(facts: dict) -> bool:
    """Whether a person approved this content in a review that stands: one such review confirms every criterion of kind
    human there (the Maintainer's ruling of 2026-10-17). It stands until a person dismisses it: a dismissal by an App, a
    Lens's App or the machine user ends nothing a person did (L-17), as it ends no request for changes (gate). It
    approves no content: only the approver's does (standing_approval). A person objects with a request for changes,
    which gates, so a human criterion never fails."""
    return any(is_person(rv["by"]) and rv["content_id"] == facts["content_id"]
               and (rv["state"] == "approved"
                    or (rv["dismissed_from"] == "approved" and not is_person(rv["dismissed_by"])))
               for rv in facts["reviews"])


def acceptance_reading(facts: dict) -> tuple:
    """What Convergence's fourth condition says (§4.2 item 4, §4.8, I-31), as (reading, criteria): 'none' where the item
    has no acceptance contract, 'failing' with the criteria that failed, 'missing' with those that have no passing
    evidence, or 'passing'. The contract is read first, and counts (contract_reading).

    Only a result given on this content counts, from its criterion's reporter. A failure on it is read first, as a
    failed check is: any failing result for a criterion fails it, whatever else was given for it. A criterion of kind
    human passes only on a person's approval of this content (confirmed_by_a_person), and never fails."""
    contract = facts["acceptance"]
    if contract is None:
        return "none", []
    criteria, person = contract["approved"]["criteria"], confirmed_by_a_person(facts)
    said = {}
    for c in criteria:
        if c["kind"] == t.HUMAN_KIND:
            said[c["id"]] = {"passing"} if person else set()
        else:
            said[c["id"]] = {ev["result"] for ev in contract["results"] if ev["criterion"] == c["id"]
                             and ev["content_id"] == facts["content_id"]}
    ids = [c["id"] for c in criteria]
    fails = [c for c in ids if "failing" in said[c]]
    if fails:
        return "failing", fails
    lacking = [c for c in ids if "passing" not in said[c]]
    if lacking:
        return "missing", lacking
    return "passing", []


def standing_approval(facts: dict, config: dict):
    """The approver's undismissed approval of this content, if any.

    Only the approver's approval stands: the machine user's, which readable_actor holds to the approver's name, while
    it has write access, without which GitHub does not count it. A person's approval answers that person's request for
    changes, and approves no content. One submitted before the pull request was last reopened does not stand, though
    GitHub reads it approved again (trials/P-7.reopened.json, issue 378): it may have been given while the pull
    request was closed. Whether it was is read from the timeline, so none stands on a timeline not read whole.
    """
    if facts["complete"]["timeline"] is not True:
        return None
    for rv in facts["reviews"]:
        if (
            rv["by"]["kind"] == t.MACHINE_USER
            and rv["by"]["can_write"] is True
            and rv["state"] == "approved"
            and rv["content_id"] == facts["content_id"]
            and (facts["last_reopened_at"] is None or rv["submitted_at"] > facts["last_reopened_at"])
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
    if d["state"] in t.ADMITS_NOTHING or not facts["queue"] or hands_off(facts, config):
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
    if not readable_expired(facts):
        return {"state": None, "reason": "facts_incomplete", "evidence": ["expired_reviews"]}
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
    # A review is given the whole diff or is not asked: one whose length was not read, or that a Task cannot carry
    # whole, is held as too large, never reviewed in part (issue 327).
    characters = facts["diff"].get("characters")
    if not isinstance(characters, int) or isinstance(characters, bool) \
            or not 0 <= characters <= config["limits"]["max_diff_characters"]:
        return {"state": t.HELD, "reason": "too_large", "evidence": []}
    # A review that cannot be read could be a writer's request for changes. It is read before anything
    # admits a Run or converges: an unreadable fact never yields an action (I-13), only a stop.
    if unreadable_reviews(facts, config):
        return {"state": None, "reason": "review_unreadable", "evidence": []}
    # So could a path the pull request changes: a protected one, or a Lens's input, whose change no model Lens reviewed.
    # The list they are matched against is the configuration's; read before them, it says what a path is.
    if not readable_rules(config):
        return {"state": None, "reason": "protected_paths_unreadable", "evidence": []}
    if not readable_paths(facts.get("changed_paths"), facts["diff"]["files"]):
        return {"state": None, "reason": "paths_unreadable", "evidence": []}
    # So could the last pusher: the port reads it from the head branch's activity, and gives null when the newest entry
    # is not the head commit (P-28). Nobody named, an approval might be the pusher's own (I-26), and a dependency update
    # might be someone else's content, so it is read before the model review is excused and before the approval.
    if not isinstance(facts.get("last_pusher"), str) or facts["last_pusher"] == "":
        return {"state": None, "reason": "last_pusher_unreadable", "evidence": []}
    # So could a required Lens's thread whose category or severity cannot be read: a security Finding at any severity.
    unread = unreadable_threads(facts, config)
    if unread:
        return {"state": None, "reason": "thread_unreadable", "evidence": unread}
    # So could a check that another App, or another workflow file, posted under a required Lens's check name: it is read
    # before any Lens's failure and before a conflict, as a fix Run is an action. It stays on this head, so only a push
    # clears it.
    foreign = foreign_checks(facts["checks"], config)
    if foreign:
        return {"state": t.VERIFYING, "reason": "check_unreadable", "evidence": foreign}
    # Then the acceptance contract's own identity, before anything admits a Run (I-29): one no person approved, or one
    # changed since, is a Hold, and one that cannot be read, or a result from anyone but its reporter, defers. Each
    # admits nothing, so it is read before a conflict and before any Lens's failure, which admit the author's fix Run.
    stop = contract_reading(facts, config)
    if stop is not None:
        return stop
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

    # Then the model Lenses this item needs: a dependency update needs none, and skips nothing else, unless it changes
    # the list. The wait names what on the list it changes. A queued item that changes the list is never read past a
    # review of its head that it lacks: an approval given before the rule, or before a path it changes joined the list,
    # never merges a change to the rules that no model Lens has reviewed (I-45).
    mine = runs_on(runs, facts)
    rules = touched(facts, config)
    lenses = required_model_lenses(facts, config)
    # A review of this content that succeeded and names a fault contradicts itself, so no Lens's report is read from it.
    # It does not end on its own, so a queued item is never read past it.
    odd = [r["run"] for r in mine if r["role"] in lenses and contradicts(r, facts)]
    if odd:
        return {"state": None, "reason": "run_unreadable", "evidence": odd}
    for lens in lenses:
        # A review whose record is past retention is asked for again (issue 346).
        if (not reviewed_clean_or_not(mine, facts, lens) or review_expired(mine, facts, lens)) \
                and ("awaiting_review" not in past or rules):
            return {"state": t.VERIFYING, "reason": "awaiting_review", "evidence": [lens] + rules}

    # Every gate before the approval: a standing approval never passes over a person's objection.
    open_gates = gates(facts, config)
    # A Lens's thread that Lens accepted, still open on GitHub, is resolved by the Kernel's act, which the queue App
    # carries out, before the author is sent back or a Lens's gate holds: the Lens judged it, and only the act closes it
    # (issue 389). A person's gate comes first: it holds the merge whatever the Lens's threads do, and is never hidden
    # behind an act. A queued item reads past it, so a gating thread open on it takes it out of the queue first: the
    # queue checks threads only as an item enters it.
    due = [th["id"] for th in facts["threads"]
           if th["opened_by"]["kind"] == "lens" and not th["resolved"] and th["ruling"] == "accepted"]
    if due and "resolve_due" not in past and not any(g["by"]["kind"] == "human" for g in open_gates):
        return {"state": t.ADJUDICATING, "reason": "resolve_due", "evidence": due}
    if open_gates:
        turns = {g["id"]: whose_turn(g, mine, config) for g in open_gates}
        for_author = [gid for gid, who in turns.items() if who == "author"]
        for_owner = [gid for gid, who in turns.items() if who == "owner"]
        if for_author:
            if any(g["by"]["kind"] == "human" for g in open_gates if g["id"] in for_author):
                return {"state": t.ADDRESSING, "reason": "human_finding", "evidence": for_author}
            return {"state": t.ADDRESSING, "reason": "findings_open", "evidence": for_author}
        if for_owner:
            return {"state": t.ADJUDICATING, "reason": "proposals_await_owner", "evidence": for_owner}
        return {"state": t.ADDRESSING, "reason": "awaiting_human", "evidence": sorted(turns)}

    # Then the acceptance contract's evidence, where the item has one: every criterion has passing evidence on this
    # content (I-31). The contract itself was read above. Neither reading is a wait a queued item is read past: the
    # merge queue knows nothing of the contract.
    said, criteria = acceptance_reading(facts)
    if said == "failing":
        return {"state": t.ADDRESSING, "reason": "acceptance_failed", "evidence": criteria}
    if said == "missing":
        return {"state": t.VERIFYING, "reason": "acceptance_evidence_missing", "evidence": criteria}

    # A change to a model Lens's own inputs needs a person as well as every model Lens's review: with one model family,
    # the only judge that is not the Lens is a person (issue 140). It is no wait a queued item is read past.
    own = lens_inputs_touched(facts, config)
    if own and not judged_by_a_person(facts):
        return {"state": t.VERIFYING, "reason": "model_lens_input_needs_person", "evidence": own}

    # GitHub does not count an approval by the author or the last pusher, so nothing may merge on one (I-26). It is
    # a Hold the facts establish, read here so that a queued item leaves the queue on it too.
    if config["approver"] in (facts["author"], facts["last_pusher"]):
        return {"state": t.HELD, "reason": "approver_is_author_or_last_pusher", "evidence": []}
    approval = standing_approval(facts, config)
    if approval is not None:
        return {"state": t.CONVERGED, "reason": "approved", "evidence": [approval["commit"]]}
    return {"state": t.CONVERGED, "reason": "approval_due", "evidence": []}
