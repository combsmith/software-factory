"""Derive the State of an issue from its facts and run records, and decide what happens next on it (design §4.1).

State is never stored. `derive` is the only definition of an issue's, as derive.py's is of a pull request's,
and it reads only the issue's own facts. Its rows are tried in order and the first that holds gives the State, so
no two States overlap (I-44). It imports the calendar, the run records' readers, the reading of control labels and
`stale`, the one test of a wait against its Lifecycle's limit, from derive.py, and who is a person from gate.py, and
changes none of them (decision 0028).

`decide` is the issue's Admission: the Controller's acts, and the one Run admitted, with its own schema,
`issue-decision/1`. It asks the brakes before every act and Run, as decide.py does, and edits neither (decision 0031).
It wraps `_decide` as decide.py does: a wait past its State's limit in lifecycle/issue.json shows `stale`, counted
from when the issue last moved, which `moved_at` reads from the issue's own facts (decision 0034).
"""
from __future__ import annotations

from kernel import brakes
from kernel import terms as t
from kernel.derive import in_progress, is_time, runs_on, since_writer, stale, standing_labels
from kernel.gate import is_person

# The States of lifecycle/issue.json that a pull request's do not share. `held` and `not_served` are terms.py's.
NEW = "new"
TRIAGE = "triage"
READY = "ready"
IN_PROGRESS = "in_progress"
IN_REVIEW = "in_review"
DONE = "done"
DECLINED = "declined"

# The labels that let work go. Each counts from its latest add, and any removal at or after it ends it.
LABEL_TRIAGE = "factory:triage"
LABEL_READY = "factory:ready"
# What the issue's facts say was read in full: the flags `complete` requires in schemas/issue-facts.schema.json.
ISSUE_READ_IN_FULL = ("linked", "runs", "timeline")
# Who last reopened the issue: a person with write access, anyone else, or nobody.
REOPENED_BY = ("writer", "other", "never")
# The classes of a pull request, as the port gives them.
CLASSES = ("agent", "maintainer", "dependency", "outside")
# The kinds a declared Factory App may be read as: the Bot account of an App, a Lens's or any other.
APP_KINDS = ("app", "lens")
# What GitHub says of an issue: open, or closed.
ISSUE_STATES = ("open", "closed")
# The fewest and the most digits of a content id after its prefix, as schemas/issue-facts.schema.json gives them,
# written as shapes, as terms.py writes a time's: a length is no limit anyone chooses, and so is not configuration.
CONTENT_FEWEST = "ffff"
CONTENT_MOST = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
# The Intents of an issue's Runs that its State reads, as their run records name them. The issue's decision, which
# admits them, uses these codes. The readiness Run judges whether the issue is ready for this content, and its `apply`
# adds factory:ready. The opening Run creates the work's branch and its draft pull request.
JUDGE_READINESS = "judge-readiness"
OPENING = "open-pull-request"
# The investigating Run, which reads the issue and comments what it found, for this content.
INVESTIGATE = "investigate-issue"
# Every Intent the issue's decision admits, the three above, each mapped in the configuration's `issues.intents` to
# its Role and App. A module holds only constants, so they are written out again.
INTENTS = ("investigate-issue", "judge-readiness", "open-pull-request")

# The work item lifecycle/issue.json names: an issue's limits are read from that Lifecycle and no other.
WORK_ITEM = "issue"
# The classes of linked pull request whose opening or close moves the issue: the Factory's and a writer's.
MOVING_CLASSES = ("agent", "maintainer")
# The issue's Decision, and the Controller's acts on an issue: accept it, remove a label that no longer counts, and
# place a Hold when unmerged closes pass their bound.
SCHEMA = "issue-decision/1"
ACCEPT = "accept"
REMOVE_LABEL = "remove_label"
PLACE_HOLD = "place_hold"
# The States in which an issue admits nothing at all: its two ends, and not served.
ADMITS_NOTHING = frozenset({DONE, DECLINED, t.NOT_SERVED})
# The States whose labels the Controller keeps to what the Kernel reads (I-17).
KEPT = frozenset({NEW, TRIAGE, READY})
# The reasons that need a person: a Hold, a lapse, the brakes, a configuration or a fact that does not mend itself,
# and the end of what the Factory may do on its own. One to a line, so that each has a mutant. A Hold the Controller
# places for unmerged closes calls a person whatever its reason, the Pause's deferral of it too, and is not listed.
NEEDS_YOU_REASONS = frozenset({
    "human_hold",
    "linked_twice",
    "acceptance_lapsed",
    "attempts_exhausted",
    "run_ceiling",
    "act_ceiling",
    "triage_stands",
    "judged",
    "ready_removed",
    "no_statement",
    "intent_undeclared",
    "label_unreadable",
    "issues_unreadable",
    "intents_unreadable",
    "intents_share_a_role",
    "intents_share_an_app",
})
# The States and reasons that call nobody: an end, not served, the pull request's own Lifecycle, an issue nobody
# accepted (I-32), and a person's own decline of the investigation.
QUIET_STATES = frozenset({
    DONE,
    DECLINED,
    t.NOT_SERVED,
    IN_REVIEW,
})
QUIET_REASONS = frozenset({
    "not_accepted",
    "triage_removed",
})


def states() -> tuple:
    """Every State this module derives, each a code: lifecycle/issue.json declares the same nine."""
    return (NEW, TRIAGE, READY, IN_PROGRESS, IN_REVIEW, t.HELD, t.NOT_SERVED, DONE, DECLINED)


def issue_labels() -> tuple:
    """The control labels the Kernel reads on an issue: the pull request's, as terms.py lists them, so that one added
    there is read here too, and factory:triage and factory:ready. A module holds only constants, so it is worked out."""
    return tuple(t.CONTROL_LABELS) + (LABEL_TRIAGE, LABEL_READY)


def unread_lists(facts: dict) -> list:
    """Names of the issue's lists that were not read in full. A flag is whole only if it is exactly true."""
    flags = facts.get("complete")
    flags = flags if isinstance(flags, dict) else {}
    return [name for name in ISSUE_READ_IN_FULL if flags.get(name) is not True]


def whole_actor(actor, config: dict) -> bool:
    """Who acted, read whole: a kind the Kernel knows, a name, and write access exactly true or false. The machine user
    is the approver the configuration names, and nobody else is; a person is never named like an App's bot (L-57)."""
    if not (isinstance(actor, dict) and actor.get("kind") in t.ACTOR_KINDS
            and isinstance(actor.get("name"), str) and actor["name"] != ""
            and type(actor.get("can_write")) is bool):
        return False
    if (actor["kind"] == t.MACHINE_USER) != (actor["name"] == config["approver"]):
        return False
    return not (actor["kind"] == "human" and actor["name"].endswith(t.BOT_SUFFIX))


def readable_events(events, config: dict) -> bool:
    """Whether every event of a control label can be read whole: what was done, by whom, and when. Another label's
    event is not read, but its label must be: it could be a control label's."""
    if not isinstance(events, list):
        return False
    for ev in events:
        if not isinstance(ev, dict) or not isinstance(ev.get("label"), str):
            return False
        if ev["label"] not in issue_labels():
            continue
        if ev.get("action") not in t.LABEL_ACTIONS or not is_time(ev.get("at")) or not whole_actor(ev.get("by"), config):
            return False
    return True


def readable_link(entry, config: dict) -> bool:
    """Whether a pull request that closes the issue can be read whole. Each says when it opened. An open one has neither
    closed nor merged; one that is not open says when it closed, and a merge closes it too: it opened, merged and
    closed in that order."""
    if not (isinstance(entry, dict) and type(entry.get("number")) is int and entry["number"] >= 1
            and entry.get("class") in CLASSES and whole_actor(entry.get("opener"), config)
            and all(type(entry.get(flag)) is bool for flag in ("open", "draft", "empty"))):
        return False
    if not is_time(entry.get("opened_at")):
        return False
    if not all(entry.get(when, "") is None or is_time(entry.get(when)) for when in ("merged_at", "closed_at")):
        return False
    if entry["open"] != (entry["closed_at"] is None) or (entry["open"] and entry["merged_at"] is not None):
        return False
    # The opening, the merge and the close, each that is there, in that order: a merge closes it, so it comes no later
    # than the close, and in the same second as it as a rule. Out of order is no chronology: its opening, read as the
    # newest movement, would hold off staleness, and its merge would make the issue done. A merge is there only with a
    # close, as read above.
    opened_on, merged_on, closed_on = entry["opened_at"], entry["merged_at"], entry["closed_at"]
    if closed_on is not None and closed_on < opened_on:
        return False
    if merged_on is not None and not (opened_on <= merged_on and merged_on <= closed_on):
        return False
    return readable_events(entry.get("label_events"), config)


def readable_content(facts: dict) -> bool:
    """A content id in its one form, `sha256:` and as many lower-case hexadecimal digits as the schema allows, no
    fewer than CONTENT_FEWEST has and no more than CONTENT_MOST; and when the content last changed."""
    cid = facts.get("content_id")
    if not (isinstance(cid, str) and cid.startswith(t.CONTENT_PREFIX)):
        return False
    digits = cid[len(t.CONTENT_PREFIX):]
    return (len(CONTENT_FEWEST) <= len(digits) <= len(CONTENT_MOST) and all(c in t.HEX_DIGITS for c in digits)
            and is_time(facts.get("content_changed_at")))


def readable_names(names) -> bool:
    """Every label's name the issue carries, as a list of names: the Consumer entry may leave any of them out."""
    return isinstance(names, list) and all(isinstance(name, str) and name != "" for name in names)


def readable_type(facts: dict) -> bool:
    """The issue's type, a name or null where it has none, given and never defaulted: the Consumer entry may leave it
    out."""
    return "type" in facts and (facts["type"] is None or (isinstance(facts["type"], str) and facts["type"] != ""))


def readable_issues(config: dict) -> bool:
    """Whether the configuration's `issues` block can be read whole: a date or null, two lists of names, and for each
    label that lets work go an App's name or null. Null serves nothing and declares nobody; anything else could."""
    issues = config.get("issues")
    if not (isinstance(issues, dict) and (issues.get("served_from") is None or is_time(issues.get("served_from")))
            and readable_names(issues.get("left_out_labels")) and readable_names(issues.get("left_out_types"))):
        return False
    apps = issues.get("label_apps")
    return isinstance(apps, dict) and all(
        name in apps and (apps[name] is None or (isinstance(apps[name], str) and apps[name] != ""))
        for name in (LABEL_TRIAGE, LABEL_READY))


def latest_adds(events: list, name: str) -> list:
    """The events that added `name`, factory:triage or factory:ready, in the latest second any did; none if none did, or
    if any removal came at or after them: these labels let work go, so a removal in the same second stops it. Which of
    two adds in one second came last cannot be told, so every one of them is read, and each must count."""
    adds = [ev for ev in events if ev["label"] == name and ev["action"] == "labeled"]
    if not adds:
        return []
    last = max(ev["at"] for ev in adds)
    if any(ev["label"] == name and ev["action"] == "unlabeled" and ev["at"] >= last for ev in events):
        return []
    return [ev for ev in adds if ev["at"] == last]


def declared(by: dict, name: str, config: dict) -> bool:
    """Whether `by` is the one Factory App the configuration declares for the label `name`. None is declared until
    the Apps are registered, and then only a person's label counts."""
    app = config["issues"]["label_apps"].get(name)
    return app is not None and by["kind"] in APP_KINDS and by["name"] == app


def judged_here(at: str, facts: dict, runs: list) -> bool:
    """Whether the readiness Run behind a factory:ready the Factory added at `at` judged the issue's present content:
    the latest readiness Run on the issue that started no later than the label completed, for this content. Runs that
    started in that one second must all have. One still running has judged nothing, and with no record, as once it has
    expired, nothing shows the content was judged: the label does not count, and the issue stays in triage."""
    mine = [r for r in runs_on(runs, facts) if r["intent"] == JUDGE_READINESS and r["started_at"] <= at]
    if not mine:
        return False
    last = max(r["started_at"] for r in mine)
    return all(r["status"] == "completed" and r["content_id"] == facts["content_id"]
               for r in mine if r["started_at"] == last)


def counts(facts: dict, runs: list, config: dict, name: str) -> bool:
    """Whether the label `name` counts (I-41): factory:triage, factory:ready or factory:admit.

    It was added by a person with write access, or by the Factory App declared for it. factory:triage and
    factory:ready were added in the issue's present life; a person's admission outlasts a reopening. factory:ready and
    factory:admit were added after the content last changed. A factory:ready the Factory added counts only for the
    content its readiness Run judged. A label added in the same second as an edit or a reopening does not count.
    """
    if name == t.LABEL_ADMIT:
        standing = standing_labels(facts).get(name)
        placed = [] if standing is None else [standing]
    else:
        placed = latest_adds(facts["label_events"], name)
    if not placed:
        return False
    at = placed[0]["at"]
    if not all(is_person(ev["by"]) or declared(ev["by"], name, config) for ev in placed):
        return False
    if name != t.LABEL_ADMIT and at <= facts["life_started_at"]:
        return False
    if name != LABEL_TRIAGE and at <= facts["content_changed_at"]:
        return False
    if name == LABEL_READY and not all(is_person(ev["by"]) for ev in placed) and not judged_here(at, facts, runs):
        return False
    return True


def added_in_this_life(facts: dict, config: dict, name: str) -> bool:
    """Whether factory:triage or factory:ready stands as added in the present life by a person with write access or the
    App declared for it, whatever else it needs to count."""
    placed = latest_adds(facts["label_events"], name)
    return (bool(placed) and placed[0]["at"] > facts["life_started_at"]
            and all(is_person(ev["by"]) or declared(ev["by"], name, config) for ev in placed))


def admitted_once(entry: dict) -> bool:
    """Whether a person with write access has ever admitted this outsider's pull request. It stays linked when its
    author pushes again, though no Run is admitted on it then (I-36)."""
    return any(ev["label"] == t.LABEL_ADMIT and ev["action"] == "labeled" and is_person(ev["by"])
               for ev in entry["label_events"])


def is_linked(entry: dict) -> bool:
    """Whether a pull request that closes the issue moves it (I-39): a Factory App opened it, or a person with write
    access, or it is an outsider's the Maintainer once admitted. A dependency bot's moves nothing here."""
    if entry["class"] == "agent":
        return True
    if entry["class"] == "maintainer":
        return True
    return entry["class"] == "outside" and admitted_once(entry)


def served(facts: dict, config: dict) -> bool:
    """Whether the Consumer entry serves the issue: its present life began on or after the date issues are served from,
    and neither its type nor any of its labels is left out. With no date, which is the default, none is served."""
    issues = config["issues"]
    start = issues["served_from"]
    if not is_time(start) or facts["life_started_at"] < start:
        return False
    if facts["type"] in issues["left_out_types"]:
        return False
    return not any(label in issues["left_out_labels"] for label in facts["label_names"])


def accepted(facts: dict, runs: list, config: dict) -> bool:
    """Accepted: served, and opened by a person with write access, or factory:admit counts on it (I-42). Whether the
    Consumer entry serves it is row 3, read before this; so rows 6 to 9 are reached only by an accepted issue."""
    return is_person(facts["author"]) or counts(facts, runs, config, t.LABEL_ADMIT)


def work_began(facts: dict, links: list, config: dict) -> bool:
    """Whether acceptance lapsed after work began, which the Maintainer is told: a person once admitted the issue, so
    acceptance held, and it has a linked pull request, or carries factory:triage or factory:ready added in this life by
    a person or the App declared for it. An issue never accepted only waits."""
    if not admitted_once(facts):
        return False
    # An open linked pull request counts in any life; a closed one only in the life it closed in.
    here = [p for p in links if p["open"] or p["closed_at"] >= facts["life_started_at"]]
    return bool(here) or any(added_in_this_life(facts, config, name) for name in (LABEL_TRIAGE, LABEL_READY))


def placed_by_a_person(labels: dict, facts: dict) -> bool:
    """Whether hands-off binds as a person's: a person placed it, and no person removed it in that same second. Placed
    by anyone else, or so removed, it is read as a Hold, as on a pull request."""
    placed = labels.get(t.LABEL_HANDS_OFF)
    if placed is None or not is_person(placed["by"]):
        return False
    return not any(ev["label"] == t.LABEL_HANDS_OFF and ev["action"] == "unlabeled" and ev["at"] == placed["at"]
                   and is_person(ev["by"]) for ev in facts["label_events"])


def out(state, reason: str, evidence: list) -> dict:
    return {"state": state, "reason": reason, "evidence": evidence}


def derive(facts: dict, runs: list, config: dict) -> dict:
    """Return {'state', 'reason', 'evidence'} for one issue. `state` is None when a fact cannot be read.

    What was read short or cannot be read is read first, a closed issue's too: rows 1 and 2 read the linked pull
    requests and the timeline, and neither terminal State admits anything.
    """
    gaps = unread_lists(facts)
    if gaps:
        return out(None, "facts_incomplete", gaps)
    if facts.get("state") not in ISSUE_STATES:
        return out(None, "state_unreadable", [])
    # Who opened the issue, of what kind: only a person who opened it accepts it by authorship.
    if not whole_actor(facts.get("author"), config):
        return out(None, "author_unreadable", [])
    if not readable_events(facts.get("label_events"), config):
        return out(None, "label_unreadable", [])
    if not readable_names(facts.get("label_names")):
        return out(None, "label_unreadable", [])
    if not (isinstance(facts.get("linked"), list) and all(readable_link(p, config) for p in facts["linked"])):
        return out(None, "linked_unreadable", [])
    if not (is_time(facts.get("life_started_at")) and facts.get("reopened_last_by") in REOPENED_BY):
        return out(None, "life_unreadable", [])
    if not readable_content(facts):
        return out(None, "content_unreadable", [])
    if not readable_type(facts):
        return out(None, "type_unreadable", [])
    # What the Consumer entry says of issues is read whole too: a block that cannot be read could serve any issue.
    if not readable_issues(config):
        return out(None, "issues_unreadable", [])

    links = [p for p in facts["linked"] if is_linked(p)]
    open_links = [p for p in links if p["open"]]
    drafts = [p for p in open_links if p["draft"]]
    # Row 1. A merge at the start of a life is in it: the reading that stops work wins.
    merges = [str(p["number"]) for p in links
              if p["merged_at"] is not None and not p["empty"] and p["merged_at"] >= facts["life_started_at"]]
    if merges:
        return out(DONE, "merged", merges)
    # Row 2.
    if facts["state"] != "open":
        return out(DECLINED, "closed", [])
    if facts["reopened_last_by"] == "other":
        return out(DECLINED, "reopened_by_other", [])
    # Row 3.
    if not served(facts, config):
        return out(t.NOT_SERVED, "left_out", [])
    labels = standing_labels(facts)
    if placed_by_a_person(labels, facts) or any(placed_by_a_person(standing_labels(p), p) for p in drafts):
        return out(t.NOT_SERVED, "hands_off", [t.LABEL_HANDS_OFF])
    # Row 4. A Hold, whoever placed it, and hands-off anyone but a person placed, on the issue or its linked draft.
    on_drafts = [standing_labels(p) for p in drafts]
    stops = [name for name in (t.LABEL_HOLD, t.LABEL_HANDS_OFF) if name in labels or any(name in d for d in on_drafts)]
    if stops:
        return out(t.HELD, "human_hold", stops)
    if len(open_links) > 1:
        return out(t.HELD, "linked_twice", [str(p["number"]) for p in open_links])
    # Row 5. If acceptance lapsed after work began, the Maintainer is told.
    if not accepted(facts, runs, config):
        return out(NEW, "acceptance_lapsed" if work_began(facts, links, config) else "not_accepted", [])
    # Rows 6 and 7.
    if open_links and not open_links[0]["draft"]:
        return out(IN_REVIEW, "linked_ready", [str(open_links[0]["number"])])
    if open_links:
        return out(IN_PROGRESS, "linked_draft", [str(open_links[0]["number"])])
    if any(r["intent"] == OPENING for r in in_progress(runs_on(runs, facts))):
        return out(IN_PROGRESS, "opening_run", [])
    # Rows 8 to 10.
    if counts(facts, runs, config, LABEL_READY):
        return out(READY, "ready", [])
    if counts(facts, runs, config, LABEL_TRIAGE):
        return out(TRIAGE, "triage", [])
    return out(NEW, "acceptance_due", [])


# What is admitted on an issue, and when `apply` refuses (design §4.1, decision 0031).


def _attention(state, reason, working: bool) -> str:
    # An unreadable fact that does not mend itself needs a person even with no State.
    if state is None and reason not in NEEDS_YOU_REASONS:
        return t.NONE
    if working:
        return t.WORKING
    if reason in NEEDS_YOU_REASONS:
        return t.NEEDS_YOU
    if state in QUIET_STATES or reason in QUIET_REASONS:
        return t.NONE
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


def readable_comments(comments) -> bool:
    """The latest comment of each Factory App that commented: its App's name, and when."""
    return isinstance(comments, list) and all(
        isinstance(c, dict) and isinstance(c.get("by"), str) and c["by"] != "" and is_time(c.get("at"))
        for c in comments)


def readable_writer(facts: dict) -> bool:
    """When a person with write access last acted, and last commented: a time, or null where none has. Never
    defaulted: a time left out could renew nothing, or everything."""
    return all(facts.get(name, "") is None or is_time(facts.get(name))
               for name in ("last_writer_action_at", "last_writer_comment_at"))


def readable_head(facts: dict) -> bool:
    """The head of the branch the next opening Run would push to: a name, or null while that branch does not exist."""
    return "branch_head" in facts and (facts["branch_head"] is None
                                       or (isinstance(facts["branch_head"], str) and facts["branch_head"] != ""))


def readable_intents(intents) -> bool:
    """Whether `issues.intents` can be read whole: each Intent named, and mapped to null, which admits nothing, or to a
    Role and its App, each a name."""
    if not (isinstance(intents, dict) and all(name in intents for name in INTENTS)):
        return False
    return all(intents[name] is None or (isinstance(intents[name], dict) and all(
        isinstance(intents[name].get(key), str) and intents[name][key] != "" for key in ("role", "app")))
        for name in INTENTS)


def shares_a_role(intents: dict) -> bool:
    """Whether two Intents name one Role: the readiness Role would judge its own investigation."""
    roles = [intents[name]["role"] for name in INTENTS if intents[name] is not None]
    return len(set(roles)) != len(roles)


def shares_an_app(intents: dict) -> bool:
    """Whether two Intents name one App: one Role's comment would then be read as another's, the investigation's as
    the verdict, or the opening Role's as the statement."""
    apps = [intents[name]["app"] for name in INTENTS if intents[name] is not None]
    return len(set(apps)) != len(apps)


def unmerged_closes(facts: dict) -> list:
    """The linked pull requests that closed in the issue's present life without being done, since a person last
    removed factory:hold from it: only that removal, or a new life, resets the count (I-43). A close in the same second
    as either is counted, the reading that stops work."""
    released = [ev["at"] for ev in facts["label_events"]
                if ev["label"] == t.LABEL_HOLD and ev["action"] == "unlabeled" and is_person(ev["by"])]
    since = max([facts["life_started_at"]] + released)
    return [str(p["number"]) for p in facts["linked"]
            if is_linked(p) and not p["open"] and p["closed_at"] >= since]


def not_counted(facts: dict, runs: list, config: dict, state: str, reason: str):
    """factory:ready or factory:triage, if it stands on an issue in new, triage or ready and does not count: what people
    see is then what the Kernel reads (I-17). Never a Hold, an admission or hands-off, and never a label a person added,
    alone or in the same second as another's: not counting it is enough, and what a person placed only a person ends
    (L-17). Not while acceptance has lapsed, whose labels are what tells the Maintainer that work began. None if no such
    label stands."""
    if state not in KEPT or reason == "acceptance_lapsed":
        return None
    for name in (LABEL_READY, LABEL_TRIAGE):
        adds = latest_adds(facts["label_events"], name)
        if adds and not any(is_person(ev["by"]) for ev in adds) and not counts(facts, runs, config, name):
            return name
    return None


def removed_by_a_person(facts: dict, name: str) -> bool:
    """Whether a person removed `name` since the content last changed: the Factory never adds it again for this
    content (I-40). A removal in the same second as the edit counts as after it, the reading that stops work."""
    return any(ev["label"] == name and ev["action"] == "unlabeled" and is_person(ev["by"])
               and ev["at"] >= facts["content_changed_at"] for ev in facts["label_events"])


def investigated_at(facts: dict, mine: list, who: dict):
    """When the investigation became current, or None if it is not. It is current once the investigating Role
    completed a Run for this content, successfully, since a person with write access last acted. Once that record has
    expired, its App's latest comment later than both the edit and that action stands in for it. A failed Run has not
    investigated: it is an attempt, which the brakes bound. While any record of the Role's investigating Runs is kept,
    the comment stands in for none of them: a Run that commented and failed has still not investigated."""
    mark = facts["last_writer_action_at"]
    kept = [r for r in mine if r["intent"] == INVESTIGATE and r["role"] == who["role"]]
    times = [r["started_at"] for r in kept
             if r["conclusion"] == "success" and r["content_id"] == facts["content_id"]]
    if not kept:
        times = [c["at"] for c in facts["role_comments"]
                 if c["by"] == who["app"] and c["at"] > facts["content_changed_at"]]
    times = [when for when in times if mark is None or when > mark]
    return min(times) if times else None


def judged(facts: dict, mine: list, who: dict, since: str) -> bool:
    """Whether the readiness Role has given its verdict on this content since the investigation: a Run that completed
    successfully, or once every record of its readiness Runs has expired, its App's factory:ready or its comment, from
    then or later."""
    kept = [r for r in mine if r["intent"] == JUDGE_READINESS and r["role"] == who["role"]]
    if kept:
        return any(r["conclusion"] == "success" and r["content_id"] == facts["content_id"] and r["started_at"] >= since
                   for r in kept)
    if any(ev["label"] == LABEL_READY and ev["action"] == "labeled" and ev["by"]["kind"] in APP_KINDS
           and ev["by"]["name"] == who["app"] and ev["at"] >= since for ev in facts["label_events"]):
        return True
    return any(c["by"] == who["app"] and c["at"] >= since for c in facts["role_comments"])


def stated(facts: dict, intents: dict, mine: list) -> bool:
    """Whether the work has a statement the opening Run may be given in place of an outsider's text: the investigating
    App's comment, or a comment by a person with write access, made after the content last changed. A person's own
    issue needs none. While a record of the investigating Role's Runs is kept, its App's comment is a statement only
    if one of them succeeded for this content: a Run that commented and failed has not investigated."""
    if is_person(facts["author"]):
        return True
    changed = facts["content_changed_at"]
    who = intents[INVESTIGATE]
    if who is not None and any(c["by"] == who["app"] and c["at"] > changed for c in facts["role_comments"]):
        kept = [r for r in mine if r["intent"] == INVESTIGATE and r["role"] == who["role"]]
        if not kept or any(r["conclusion"] == "success" and r["content_id"] == facts["content_id"] for r in kept):
            return True
    said = facts["last_writer_comment_at"]
    return said is not None and said > changed


def _stop(facts, state, reason, evidence, context, action, **extra) -> dict:
    """An act that stops work, or that takes back a label that lets none go. Only the Pause stops it (decision 0003):
    it is never refused at the act ceiling, and placing a Hold is not delayed by a Run in flight."""
    pause = brakes.paused(_decision, facts, state, evidence, context)
    if pause:
        return pause
    return _decision(facts, state, reason, evidence, t.ACT, action=action, content_id=facts["content_id"], **extra)


def _accept(facts, state, reason, evidence, mine, context, config) -> dict:
    """Row 10: the Controller accepts the issue by adding factory:triage, once its App is declared for it, so that the
    label it adds counts. Not once a person removed it for this content (I-40), and not while factory:triage stands,
    whoever placed it: a person's that does not count is never removed, and adding it again changes nothing. The act
    ceiling bounds it."""
    if reason != "acceptance_due":
        return _decision(facts, state, reason, evidence, t.NOTHING)
    if latest_adds(facts["label_events"], LABEL_TRIAGE):
        return _decision(facts, state, "triage_stands", [LABEL_TRIAGE], t.NOTHING)
    if config["issues"]["label_apps"][LABEL_TRIAGE] is None:
        return _decision(facts, state, reason, evidence, t.NOTHING)
    if removed_by_a_person(facts, LABEL_TRIAGE):
        return _decision(facts, state, "triage_removed", evidence, t.NOTHING)
    brake = brakes.on_act(_decision, facts, state, evidence, context, ACCEPT, since_writer(mine, facts),
                          config["limits"])
    if brake:
        return brake
    return _decision(facts, state, reason, evidence, t.ACT, action=ACCEPT, content_id=facts["content_id"])


def _wanted(facts, state, reason, evidence, mine, intents):
    """The Run the State calls for, as (role, intent, what else its admission carries), or the Decision that admits
    none. In triage one at a time: an investigation unless it is current, then a verdict unless one stands or a person
    overruled it, then nothing. In ready the opening Run, from a statement on an outsider's issue."""
    if state == TRIAGE:
        who = intents[INVESTIGATE]
        if who is None:
            return _decision(facts, state, "intent_undeclared", [INVESTIGATE], t.NOTHING)
        since = investigated_at(facts, mine, who)
        if since is None:
            return (who["role"], INVESTIGATE, {})
        if removed_by_a_person(facts, LABEL_READY):
            return _decision(facts, state, "ready_removed", evidence, t.NOTHING)
        who = intents[JUDGE_READINESS]
        if who is None:
            return _decision(facts, state, "intent_undeclared", [JUDGE_READINESS], t.NOTHING)
        if judged(facts, mine, who, since):
            return _decision(facts, state, "judged", evidence, t.NOTHING)
        return (who["role"], JUDGE_READINESS, {})
    who = intents[OPENING]
    if who is None:
        return _decision(facts, state, "intent_undeclared", [OPENING], t.NOTHING)
    if not stated(facts, intents, mine):
        return _decision(facts, state, "no_statement", evidence, t.NOTHING)
    if not readable_head(facts):
        return _decision(facts, state, "branch_unreadable", evidence, t.DEFER)
    return (who["role"], OPENING, {"branch_head": facts["branch_head"]})


def moved_at(facts: dict, runs: list, config: dict, now: str):
    """When the issue last moved, or None if no time can be read (design §4.1, decision 0034).

    The newest time a writer, a named App or the Factory moved it, read from the issue's own facts: its present life
    began, its content changed, a person with write access acted or commented, a person or an App `issues.label_apps`
    names added or removed a control label, a Run on it started, or the Factory's or a writer's linked pull request
    opened or closed. Nothing else: not a Role's comment, whose Run is counted already, nor an App named nowhere, nor a
    label the Kernel does not read, nor a pull request of any other class, an admitted outsider's among them, which its
    author could close and reopen for ever, so that no stranger can keep an issue from showing. A time that is not a
    real moment no later than `now` is passed over, so the wait counts from earlier: that shows more, never less. A
    `now` that is no moment gives no time at all.
    """
    if not is_time(now):
        return None
    times = [facts["life_started_at"]]
    times += [facts["content_changed_at"]]
    times += [facts.get("last_writer_action_at")]
    times += [facts.get("last_writer_comment_at")]
    times += [ev["at"] for ev in facts["label_events"]
              if ev["label"] in issue_labels() and (is_person(ev["by"]) or named(ev["by"], config))]
    times += [r["started_at"] for r in runs_on(runs, facts)]
    linked = [p for p in facts["linked"] if p["class"] in MOVING_CLASSES]
    times += [p["opened_at"] for p in linked]
    times += [p["closed_at"] for p in linked]
    readable = [x for x in times if is_time(x) and x <= now]
    return max(readable) if readable else None


def named(by: dict, config: dict) -> bool:
    """Whether `by` is an App `issues.label_apps` names, for any label that lets work go."""
    return any(declared(by, name, config) for name in (LABEL_TRIAGE, LABEL_READY))


def overdue(lifecycle, state: str, moved, passes_since, now: str) -> bool:
    """Whether a wait in `state` has run past its limit in the issue's Lifecycle. The Controller gives each item its own
    type's (decision 0028); one that is not the issue's, or whose limit for `state` is not a finite number of minutes,
    cannot be read, and is read as past its limit: that shows more, never less, and a pure function does not crash on
    it. A negative limit needs no test of its own: every wait is past it. An end the Lifecycle declares never waits."""
    if not (isinstance(lifecycle, dict) and lifecycle.get("work_item") == WORK_ITEM):
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


def decide(facts: dict, runs: list, context: dict, config: dict, now: str) -> dict:
    """Return the Decision for one issue: what, if anything, happens next on it. No I/O, no clock."""
    # A context that cannot be read says nothing: not whether the Pause holds, which the brakes then read as
    # unreadable and defer every act and Run, nor the passes, as an unreadable `passes_since` does not.
    known = context if isinstance(context, dict) else {}
    d = _decide(facts, runs, known, config, now)
    # A wait past its State's limit, while passes ran, is the Maintainer's to see. Only what they see changes (I-1).
    # A deferral that holds the whole scope is one cause, reported once (§4.6): the issue keeps the attention it had.
    if (d["attention"] in t.MAY_GO_STALE and d["reason"] not in t.SCOPE_DEFERRALS
            and overdue(config.get("lifecycle"), d["state"], moved_at(facts, runs, config, now),
                        known.get("passes_since"), now)):
        return dict(d, attention=t.STALE)
    return d


def _decide(facts: dict, runs: list, context: dict, config: dict, now: str) -> dict:
    d = derive(facts, runs, config)
    state, reason, evidence = d["state"], d["reason"], d["evidence"]
    # Fail to a deferral, never to an action.
    if state is None:
        return _decision(facts, None, reason, evidence, t.DEFER)
    if state in ADMITS_NOTHING:
        return _decision(facts, state, reason, evidence, t.NOTHING)
    if state == t.HELD:
        return _decision(facts, state, reason, evidence, t.HOLD)
    mine = runs_on(runs, facts)

    # The acts that stop work, read first. Unmerged closes past their bound place a Hold (I-43); a label that stands
    # and does not count is removed, though not while a Run is in flight, whose own label may not count until it ends.
    closes = unmerged_closes(facts)
    if len(closes) > config["limits"]["max_unmerged_closes"]:
        return dict(_stop(facts, state, "unmerged_closes", closes, context, PLACE_HOLD), attention=t.NEEDS_YOU)
    label = not_counted(facts, runs, config, state, reason)
    if label is not None and not in_progress(mine):
        return _stop(facts, state, "label_not_counted", [label], context, REMOVE_LABEL, label=label)

    # What steers what is admitted, read whole.
    if not readable_comments(facts.get("role_comments")):
        return _decision(facts, state, "comments_unreadable", evidence, t.DEFER)
    if not readable_writer(facts):
        return _decision(facts, state, "writer_unreadable", evidence, t.DEFER)

    # A Run in flight admits nothing, and nothing it has written is read until it completes: its comment or its label
    # would move the Intent on. The brakes' Hold still applies, the one they would have made of each Run in flight,
    # which is left out of its own count, since it was admitted under the ceiling (decision 0003).
    limits = config["limits"]
    flight = in_progress(mine)
    if flight:
        done = [r for r in since_writer(mine, facts) if r["status"] == "completed"]
        for r in flight:
            brake = brakes.on_run(_decision, facts, state, evidence, context, r["intent"], done, limits)
            if brake and brake["outcome"] == t.HOLD:
                return brake
        return _decision(facts, state, reason, evidence, t.NOTHING, working=True)
    if state == NEW:
        return _accept(facts, state, reason, evidence, mine, context, config)
    if state == IN_REVIEW or reason == "linked_draft":
        return _decision(facts, state, reason, evidence, t.NOTHING)
    intents = config["issues"].get("intents")
    if not readable_intents(intents):
        return _decision(facts, state, "intents_unreadable", evidence, t.DEFER)
    if shares_a_role(intents):
        return _decision(facts, state, "intents_share_a_role", evidence, t.DEFER)
    if shares_an_app(intents):
        return _decision(facts, state, "intents_share_an_app", evidence, t.DEFER)
    wanted = _wanted(facts, state, reason, evidence, mine, intents)
    if isinstance(wanted, dict):
        return wanted
    role, intent, carried = wanted

    # The brakes on a Run (decision 0003): the Pause, the attempts and the Run ceiling.
    brake = brakes.on_run(_decision, facts, state, evidence, context, intent, since_writer(mine, facts), limits)
    if brake:
        return brake

    # Capacity and the org's concurrency are not brakes: they bound no cycle (§4.1), and only defer.
    until = context.get("model_deferred_until", "unreadable")
    # A deadline missing, or one or a `now` that is no moment, cannot be compared: the deferral fails closed, and
    # nothing raises.
    if until is not None and not (is_time(until) and is_time(now)):
        return _decision(facts, state, "capacity_unreadable", evidence, t.DEFER)
    if until is not None and until > now:
        return _decision(facts, state, "capacity", evidence, t.DEFER)
    active = context.get("active_runs")
    if active is None:
        return _decision(facts, state, "capacity_unreadable", evidence, t.DEFER)
    if active >= limits["org_max_active_runs"]:
        return _decision(facts, state, "concurrency", evidence, t.DEFER)
    # A Run listed before its run-name may be the Run in flight on this issue. Which item it is on cannot be read, so no
    # Run is admitted until it can be; a list that cannot be read defers too (I-46, decision 0036).
    if context.get("unidentified_runs") != []:
        return _decision(facts, state, "run_unidentified", evidence, t.DEFER)

    admit = dict({"role": role, "intent": intent, "content_id": facts["content_id"]}, **carried)
    return _decision(facts, state, reason, evidence, t.ADMIT, admit=admit)


def still_admitted(admitted: dict, again: dict) -> bool:
    """Whether `apply` may write. Before any Effect it asks the Kernel again, leaving its own Run out of the records
    (I-38), and writes nothing unless that admits the same Run: the same Role and Intent, which only one State admits,
    for the same content, and for the opening Run the same branch head (I-21). So a label removed, a Hold added, an
    edit made or a head moved while the Run was in flight each stop it."""
    return again.get("admit") is not None and again.get("admit") == admitted.get("admit")
