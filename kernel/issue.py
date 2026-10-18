"""Derive the State of an issue from its facts and run records (design §4.1, the issue Lifecycle).

State is never stored. This function is the only definition of an issue's, as derive.py's is of a pull request's,
and it reads only the issue's own facts. Its rows are tried in order and the first that holds gives the State, so
no two States overlap (I-44). It imports the calendar, the run records' readers and the reading of control labels
from derive.py, and who is a person from gate.py, and changes none of them (decision 0028).
"""
from __future__ import annotations

from kernel import terms as t
from kernel.derive import in_progress, is_time, runs_on, standing_labels
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
# The control labels the Kernel reads on an issue: the pull request's three, and the two above.
ISSUE_LABELS = ("factory:hold", "factory:hands-off", "factory:admit", "factory:triage", "factory:ready")
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


def states() -> tuple:
    """Every State this module derives, each a code: lifecycle/issue.json declares the same nine."""
    return (NEW, TRIAGE, READY, IN_PROGRESS, IN_REVIEW, t.HELD, t.NOT_SERVED, DONE, DECLINED)


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
        if ev["label"] not in ISSUE_LABELS:
            continue
        if ev.get("action") not in t.LABEL_ACTIONS or not is_time(ev.get("at")) or not whole_actor(ev.get("by"), config):
            return False
    return True


def readable_link(entry, config: dict) -> bool:
    """Whether a pull request that closes the issue can be read whole. An open one has neither closed nor merged; one
    that is not open says when it closed, and a merge closes it too."""
    if not (isinstance(entry, dict) and type(entry.get("number")) is int and entry["number"] >= 1
            and entry.get("class") in CLASSES and whole_actor(entry.get("opener"), config)
            and all(type(entry.get(flag)) is bool for flag in ("open", "draft", "empty"))):
        return False
    if not all(entry.get(when, "") is None or is_time(entry.get(when)) for when in ("merged_at", "closed_at")):
        return False
    if entry["open"] != (entry["closed_at"] is None) or (entry["open"] and entry["merged_at"] is not None):
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
