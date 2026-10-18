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
# The Intent of the opening Run, which creates the work's branch and its draft pull request.
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
    """A content id in its one form, `sha256:` and lower-case hexadecimal digits, and when the content last changed."""
    cid = facts.get("content_id")
    return (isinstance(cid, str) and cid.startswith(t.CONTENT_PREFIX) and len(cid) > len(t.CONTENT_PREFIX)
            and all(c in t.HEX_DIGITS for c in cid[len(t.CONTENT_PREFIX):]) and is_time(facts.get("content_changed_at")))


def latest_add(events: list, name: str):
    """The event that added `name`, factory:triage or factory:ready, most lately, or None if none did or any removal
    came at or after it: these labels let work go, so a removal in the same second stops it."""
    adds = [ev for ev in events if ev["label"] == name and ev["action"] == "labeled"]
    if not adds:
        return None
    last = max(adds, key=lambda ev: ev["at"])
    if any(ev["label"] == name and ev["action"] == "unlabeled" and ev["at"] >= last["at"] for ev in events):
        return None
    return last


def declared(by: dict, name: str, config: dict) -> bool:
    """Whether `by` is the one Factory App the configuration declares for the label `name`. None is declared until
    the Apps are registered, and then only a person's label counts."""
    app = config["issues"]["label_apps"].get(name)
    return app is not None and by["kind"] in APP_KINDS and by["name"] == app


def judged_here(placed: dict, facts: dict, runs: list) -> bool:
    """Whether the Run that completed just before the Factory added factory:ready was admitted for the issue's present
    content. Runs that started in the same second as the label are among them, and all must agree. Once the record has
    expired the time alone is read: a label that did not count will long since have been removed."""
    before = [r for r in runs_on(runs, facts) if r["status"] == "completed" and r["started_at"] <= placed["at"]]
    if not before:
        return True
    last = max(r["started_at"] for r in before)
    return all(r["content_id"] == facts["content_id"] for r in before if r["started_at"] == last)


def counts(facts: dict, runs: list, config: dict, name: str) -> bool:
    """Whether the label `name` counts (I-41): factory:triage, factory:ready or factory:admit.

    It was added by a person with write access, or by the Factory App declared for it. factory:triage and
    factory:ready were added in the issue's present life; a person's admission outlasts a reopening. factory:ready and
    factory:admit were added after the content last changed. A factory:ready the Factory added counts only for the
    content its Run judged. A label added in the same second as an edit or a reopening does not count.
    """
    if name == t.LABEL_ADMIT:
        placed = standing_labels(facts).get(name)
    else:
        placed = latest_add(facts["label_events"], name)
    if placed is None:
        return False
    by = placed["by"]
    if not (is_person(by) or declared(by, name, config)):
        return False
    if name != t.LABEL_ADMIT and placed["at"] <= facts["life_started_at"]:
        return False
    if name != LABEL_TRIAGE and placed["at"] <= facts["content_changed_at"]:
        return False
    if name == LABEL_READY and not is_person(by) and not judged_here(placed, facts, runs):
        return False
    return True


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
    if facts.get("type") in issues["left_out_types"]:
        return False
    names = facts.get("label_names")
    return isinstance(names, list) and not any(label in issues["left_out_labels"] for label in names)


def accepted(facts: dict, runs: list, config: dict) -> bool:
    """Accepted: served, and opened by a person with write access, or factory:admit counts on it (I-42). Whether the
    Consumer entry serves it is row 3, read before this; so rows 6 to 9 are reached only by an accepted issue."""
    return facts["author_can_write"] is True or counts(facts, runs, config, t.LABEL_ADMIT)


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
    if not readable_events(facts.get("label_events"), config):
        return out(None, "label_unreadable", [])
    if not (isinstance(facts.get("linked"), list) and all(readable_link(p, config) for p in facts["linked"])):
        return out(None, "linked_unreadable", [])
    if not (is_time(facts.get("life_started_at")) and facts.get("reopened_last_by") in REOPENED_BY):
        return out(None, "life_unreadable", [])
    if not readable_content(facts):
        return out(None, "content_unreadable", [])

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
    # Row 5. Work began if it carries a label that lets work go, or has a linked pull request: the Maintainer is told.
    if not accepted(facts, runs, config):
        began = links or any(latest_add(facts["label_events"], name) for name in (LABEL_TRIAGE, LABEL_READY))
        return out(NEW, "acceptance_lapsed" if began else "not_accepted", [])
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
