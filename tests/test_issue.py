"""The boundary cases of an issue's State (design §4.1, the issue Lifecycle), written before the code.

The situations the reviews of the issue Lifecycle said went wrong are one table, seeded by the throwaway model that
held them, `derive_issue_model.py`, and not copied from it. Each rule then has its boundary, from both sides. The
builders live here, not in `tests/support.py`: an issue's facts are not a pull request's.
"""
from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

from kernel import issue
from tests.support import CONFIG, MAINTAINER, ROOT
from tools import check_purity
from tools.jsonschema_lite import validate

LIFECYCLE = json.loads((ROOT / "lifecycle" / "issue.json").read_text())
SCHEMA = json.loads((ROOT / "schemas" / "issue-facts.schema.json").read_text())
ITEM = {"repo": "combsmith/software-factory", "type": "issue", "number": 7}
THIS, OTHER = "sha256:c1c1", "sha256:c2c2"
# Who acts. A person is human with write access, and nobody else is.
WRITER = MAINTAINER
COLLEAGUE = {"kind": "human", "name": "a-colleague", "can_write": True}
OUTSIDER = {"kind": "human", "name": "stranger", "can_write": False}
CONTROLLER = {"kind": "app", "name": "combsmith-sf-controller[bot]", "can_write": True}
READINESS = {"kind": "app", "name": "combsmith-sf-readiness[bot]", "can_write": True}
AUTHOR_APP = {"kind": "app", "name": "combsmith-sf-dev-lead[bot]", "can_write": True}
OTHER_APP = {"kind": "app", "name": "some-other-app[bot]", "can_write": True}
MACHINE = {"kind": "machine_user", "name": CONFIG["approver"], "can_write": True}
# The issues served once the Maintainer turns them on, with the App declared for each label that lets work go.
SERVED = {"served_from": "2026-01-01T00:00:00Z", "left_out_labels": ["epic", "idea"], "left_out_types": ["Epic"],
          "label_apps": {"factory:triage": CONTROLLER["name"], "factory:ready": READINESS["name"]}}
TRIAGE, READY, HOLD, HANDS_OFF, ADMIT = "factory:triage", "factory:ready", "factory:hold", "factory:hands-off", \
    "factory:admit"


def at(minute: int) -> str:
    """A time `minute` minutes after the issue was opened, at noon."""
    return "2026-10-11T12:%02d:00Z" % minute


def config(**issues) -> dict:
    """The configuration, with issues served as SERVED says but for what differs."""
    c = copy.deepcopy(CONFIG)
    c["issues"] = dict(copy.deepcopy(SERVED), **issues)
    return c


def labelled(label: str, by=None, minute: int = 1, action: str = "labeled") -> dict:
    """A label event from the issue's timeline. By default the Maintainer adds `label` a minute after it was opened."""
    return {"label": label, "action": action, "by": dict(WRITER if by is None else by), "at": at(minute)}


def unlabelled(label: str, by=None, minute: int = 2) -> dict:
    return labelled(label, by, minute, "unlabeled")


def pr(number=11, by=None, cls="maintainer", is_open=True, draft=False, merged=None, closed=None, empty=False,
       events=()) -> dict:
    """A pull request that closes the issue. By default the Maintainer's, open and ready. A merged one closed then."""
    if merged is not None and closed is None:
        closed = merged
    return {"number": number, "class": cls, "opener": dict(WRITER if by is None else by), "open": is_open,
            "draft": draft, "merged_at": None if merged is None else at(merged),
            "closed_at": None if closed is None else at(closed), "empty": empty, "label_events": list(events)}


def agents(**over) -> dict:
    """The Factory's own pull request: its author's App opened it."""
    return pr(**dict({"by": AUTHOR_APP, "cls": "agent"}, **over))


def strangers(admitted=False, **over) -> dict:
    """An outsider's pull request, which the Maintainer has once admitted, or not."""
    events = [labelled(ADMIT, minute=3)] if admitted else []
    return pr(**dict({"by": OUTSIDER, "cls": "outside", "events": events}, **over))


def facts(**over) -> dict:
    """An open issue the Maintainer opened at minute 0, with no label and no pull request, read in full."""
    f = {"schema": "issue-facts/1", "item": dict(ITEM), "state": "open", "author": WRITER["name"],
         "author_can_write": True, "type": None, "label_names": [], "assignees": [],
         "life_started_at": at(0), "reopened_last_by": "never", "content_id": THIS, "content_changed_at": at(0),
         "label_events": [], "linked": [], "role_comments": [], "last_writer_action_at": at(0),
         "last_writer_comment_at": None, "complete": {"timeline": True, "linked": True, "runs": True},
         "read_at": at(50)}
    f.update(over)
    return f


def outsiders(**over) -> dict:
    """An issue an outsider opened."""
    return facts(**dict({"author": OUTSIDER["name"], "author_can_write": False}, **over))


def run(intent="judge-readiness", content=THIS, status="completed", minute=4, name="r1", role="readiness") -> dict:
    """A run record on the issue. By default a readiness Run of this content that completed, started at minute 4."""
    return {"run": name, "item": dict(ITEM), "role": role, "intent": intent, "content_id": content, "status": status,
            "conclusion": None if status != "completed" else "success", "outcome": None, "started_at": at(minute)}


def opening(status="in_progress") -> dict:
    return run(intent=issue.OPENING, status=status, minute=6, name="o1", role="dev-lead")


def derive(f, runs=(), cfg=None) -> dict:
    """The Kernel's reading, held to its contract: a declared State or none, a reason that is a code, and evidence."""
    given = copy.deepcopy((f, list(runs), cfg or config()))
    d = issue.derive(*given)
    assert given == copy.deepcopy((f, list(runs), cfg or config())), "the Kernel changed an argument"
    assert d["state"] is None or d["state"] in LIFECYCLE["states"], d
    assert isinstance(d["reason"], str) and d["reason"] and set(d["reason"]) <= set("abcdefghijklmnopqrstuvwxyz_"), d
    assert isinstance(d["evidence"], list) and all(isinstance(e, str) for e in d["evidence"]), d
    return d


def state(f, runs=(), cfg=None):
    return derive(f, runs, cfg)["state"]


ACCEPTED = [labelled(TRIAGE, CONTROLLER, 1)]
READIED = ACCEPTED + [labelled(READY, READINESS, 5)]
JUDGED = [run()]

# (what went wrong, facts, run records, the State the design gives). The reviews' numbering is kept in the names.
CASES = [
    ("an insider's new issue", facts(), [], "new"),
    ("accepted by the Controller", facts(label_events=ACCEPTED), [], "triage"),
    ("the readiness Role's label, for this content", facts(label_events=READIED), JUDGED, "ready"),
    ("review 2, finding 1: an admitted outsider edits; triage must not survive",
     outsiders(content_changed_at=at(5), label_events=[labelled(ADMIT, minute=1), labelled(TRIAGE, CONTROLLER, 2)]), [],
     "new"),
    ("review 2, finding 1: a writer labels an unadmitted outsider's issue ready",
     outsiders(label_events=[labelled(READY, minute=3)]), [], "new"),
    ("review 2, finding 2: the label landed after an edit, for content the Run was not admitted for",
     facts(content_changed_at=at(4), content_id=OTHER, label_events=ACCEPTED + [labelled(READY, READINESS, 5)]),
     [run(minute=3)], "triage"),
    ("content changed after a person's ready",
     facts(content_changed_at=at(9), label_events=ACCEPTED + [labelled(READY, minute=3)]), [], "triage"),
    ("a label added by some other App is not read", facts(label_events=[labelled(READY, OTHER_APP, 3)]), [], "new"),
    ("review 1, blocker 1: a stranger's pull request names a ready issue",
     facts(label_events=[labelled(READY)], linked=[strangers(draft=True)]), [], "ready"),
    ("two strangers' pull requests do not hold it",
     facts(label_events=[labelled(READY)], linked=[strangers(), strangers(number=12)]), [], "ready"),
    ("an admitted outsider's pull request is linked", facts(linked=[strangers(admitted=True)]), [], "in_review"),
    ("a linked draft", facts(linked=[agents(draft=True)]), [], "in_progress"),
    ("review 2, finding 4: a Hold on the draft holds the issue",
     facts(linked=[agents(draft=True, events=[labelled(HOLD)])]), [], "held"),
    ("two linked pull requests open", facts(linked=[pr(), agents(number=12, draft=True)]), [], "held"),
    ("review 2, finding 9: merged, and GitHub has not closed the issue; ready still counts",
     facts(label_events=[labelled(READY)], linked=[pr(is_open=False, merged=5)]), [], "done"),
    ("an empty merge closes it", facts(state="closed", linked=[pr(is_open=False, merged=5, empty=True)]), [],
     "declined"),
    ("closed with no pull request", facts(state="closed"), [], "declined"),
    ("review 2, finding 8: a person's Hold outlasts a reopening",
     facts(life_started_at=at(10), reopened_last_by="writer", label_events=[labelled(HOLD, minute=3)]), [], "held"),
    ("reopened by a writer after done: a new life, old labels and merges not counted",
     facts(life_started_at=at(10), reopened_last_by="writer",
           label_events=[labelled(TRIAGE, CONTROLLER, 1), labelled(READY, minute=2)],
           linked=[pr(is_open=False, merged=5)]), [], "new"),
    ("reopened by someone else after done: no new life",
     facts(reopened_last_by="other", linked=[pr(is_open=False, merged=5)]), [], "done"),
    ("third check, N7: closed, then reopened by its outside author: declined has no way out",
     facts(reopened_last_by="other", label_events=[labelled(TRIAGE, CONTROLLER, 1), labelled(READY, minute=2)]), [],
     "declined"),
    ("third check, N1: an admitted outsider's pull request stays linked after its author pushes again",
     facts(label_events=[labelled(READY)], linked=[strangers(admitted=True)]), [], "in_review"),
    ("third check, N3: acceptance lapses with the Factory's draft open; new, and assigned to the Maintainer",
     outsiders(content_changed_at=at(9), label_events=[labelled(ADMIT)], linked=[agents(draft=True)]), [], "new"),
    ("the Maintainer's own draft on an unadmitted outsider's issue: the issue waits, the pull request goes its own way",
     outsiders(linked=[pr(draft=True)]), [], "new"),
    ("a Hold added by some other App still holds", facts(label_events=[labelled(HOLD, OTHER_APP, 3)]), [], "held"),
    ("hands-off on the linked draft", facts(linked=[agents(draft=True, events=[labelled(HANDS_OFF)])]), [],
     "not_served"),
    ("a label in the same second as an edit does not count",
     facts(content_changed_at=at(3), label_events=[labelled(TRIAGE, CONTROLLER, 1), labelled(READY, minute=3)]), [],
     "triage"),
    ("an empty merge, before GitHub closes the issue: nothing was done, so it is still ready",
     facts(label_events=[labelled(READY)], linked=[pr(is_open=False, merged=5, empty=True)]), [], "ready"),
    ("reopened by a writer while its draft is open: the open pull request still counts",
     facts(life_started_at=at(10), reopened_last_by="writer", linked=[agents(draft=True)]), [], "in_progress"),
    ("hands-off", facts(label_events=[labelled(HANDS_OFF, minute=1), labelled(READY, minute=2)]), [], "not_served"),
    ("left out by the Consumer entry", facts(), [], "not_served", ),
    ("an opening Run holds a ready issue", facts(label_events=[labelled(READY)]), [opening()], "in_progress"),
    ("review 2, finding 3: the same issue seen by apply, its own Run left out, after the label was removed",
     facts(label_events=[labelled(READY), unlabelled(READY)]), [], "new"),
    # The two the issue counts beyond the model's 33.
    ("a Factory ready whose Run record has expired: the time alone is read", facts(label_events=READIED), [], "ready"),
    ("a ready a person removed", facts(label_events=READIED + [unlabelled(READY, minute=7)]), JUDGED, "triage"),
]
# The one case whose Consumer entry serves nothing, by its place in CASES.
UNSERVED = "left out by the Consumer entry"


class Situations(unittest.TestCase):
    def test_the_situations_the_reviews_found_derive_as_the_design_says(self):
        self.assertEqual(len(CASES), 35)
        for name, f, runs, want in CASES:
            cfg = config(served_from=None) if name == UNSERVED else config()
            with self.subTest(name):
                self.assertEqual(state(f, runs, cfg), want)

    def test_every_case_is_valid_facts(self):
        for name, f, _, _ in CASES:
            with self.subTest(name):
                self.assertEqual(validate(f, SCHEMA), [])

    def test_the_same_inputs_give_the_same_state(self):
        for name, f, runs, _ in CASES:
            self.assertEqual(derive(f, runs), derive(copy.deepcopy(f), copy.deepcopy(runs)), name)


class Lifecycle(unittest.TestCase):
    def test_every_state_is_declared_and_every_declared_state_has_a_code(self):
        self.assertEqual(sorted(issue.states()), sorted(LIFECYCLE["states"]))
        self.assertEqual(len(set(issue.states())), len(issue.states()))
        got = {state(f, runs, config(served_from=None) if name == UNSERVED else config()) for name, f, runs, _ in CASES}
        self.assertLessEqual(got, set(LIFECYCLE["states"]))
        self.assertEqual(got, set(LIFECYCLE["states"]))

    def test_the_kernel_module_that_derives_an_issue_is_held_pure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "kernel").mkdir()
            (root / "kernel" / "issue.py").write_text("import time\n\n\ndef derive(facts):\n    return time.time()\n")
            problems = check_purity.run(root)
        self.assertTrue(problems)
        self.assertTrue(all(p.startswith("issue.py:") for p in problems), problems)
        self.assertEqual(check_purity.run(ROOT), [])


class Unreadable(unittest.TestCase):
    """Short and unreadable facts come before row 1, a closed issue's too, and never yield a State."""

    def test_a_list_not_read_in_full_defers(self):
        for name in ("timeline", "linked", "runs"):
            for flag in (False, None, "true", 1):
                for f in (facts(), facts(state="closed"), facts(linked=[pr(is_open=False, merged=5)])):
                    f["complete"] = dict(f["complete"], **{name: flag})
                    d = derive(f)
                    self.assertEqual((d["state"], d["reason"], d["evidence"]), (None, "facts_incomplete", [name]))
        f = facts()
        del f["complete"]
        self.assertEqual(derive(f)["reason"], "facts_incomplete")
        self.assertEqual(derive(facts(complete={"timeline": True, "linked": True}))["evidence"], ["runs"])
        self.assertEqual(derive(facts())["reason"], "acceptance_due")

    def test_an_unreadable_label_event_defers(self):
        bad = [dict(labelled(HOLD), by={"kind": "bot", "name": "x", "can_write": True}),
               dict(labelled(READY), by={"kind": "human", "name": "x[bot]", "can_write": True}),
               dict(labelled(TRIAGE), by={"kind": "human", "name": "", "can_write": True}),
               dict(labelled(ADMIT), by={"kind": "human", "name": "x", "can_write": None}),
               dict(labelled(HANDS_OFF), by={"kind": "machine_user", "name": "someone", "can_write": True}),
               dict(labelled(HOLD), by={"kind": "human", "name": CONFIG["approver"], "can_write": True}),
               dict(labelled(READY), action="removed"), dict(labelled(TRIAGE), at="2026-10-11 12:01"),
               dict(labelled(HOLD), at="2026-02-30T12:00:00Z"), {"label": None, "action": "labeled"}, "factory:hold"]
        for ev in bad:
            for f in (facts(label_events=[ev]), facts(state="closed", label_events=[ev])):
                d = derive(f)
                self.assertEqual((d["state"], d["reason"]), (None, "label_unreadable"), ev)
        no_by = labelled(HOLD)
        del no_by["by"]
        self.assertEqual(derive(facts(label_events=[no_by]))["reason"], "label_unreadable")
        self.assertEqual(derive(facts(label_events=None))["reason"], "label_unreadable")
        # The other side: another label's event is not read, a readable one is, and the machine user is readable.
        other = {"label": "bug", "action": "whatever", "by": None, "at": "never"}
        self.assertEqual(state(facts(label_events=[other])), "new")
        self.assertEqual(state(facts(label_events=[labelled(HOLD, MACHINE)])), "held")

    def test_an_unreadable_linked_pull_request_defers(self):
        good = pr()
        bad = [dict(good, number="11"), dict(good, number=0), dict(good, **{"class": "insider"}),
               dict(good, opener={"kind": "human", "name": "x"}), dict(good, open="yes"), dict(good, draft=None),
               dict(good, empty=0), dict(good, merged_at="soon", closed_at=at(5), open=False),
               dict(good, closed_at=at(5)), dict(good, merged_at=at(5)), dict(good, open=False),
               dict(good, label_events=[dict(labelled(HOLD), by=None)]), dict(good, label_events=None), "11"]
        no_class = dict(good)
        del no_class["class"]
        for entry in bad + [no_class]:
            for f in (facts(linked=[entry]), facts(state="closed", linked=[entry])):
                d = derive(f)
                self.assertEqual((d["state"], d["reason"]), (None, "linked_unreadable"), entry)
        self.assertEqual(derive(facts(linked=None))["reason"], "linked_unreadable")
        # The other side: closed unmerged, merged, and a stranger's pull request are read.
        self.assertEqual(state(facts(linked=[pr(is_open=False, closed=5)])), "new")
        self.assertEqual(state(facts(linked=[pr(is_open=False, merged=5)])), "done")
        self.assertEqual(state(facts(linked=[strangers()])), "new")

    def test_an_unreadable_life_defers(self):
        for over in ({"life_started_at": None}, {"life_started_at": "2026-10-11"}, {"reopened_last_by": "a person"},
                     {"reopened_last_by": None}, {"life_started_at": "2026-13-01T00:00:00Z"}):
            for f in (facts(**over), facts(state="closed", **over)):
                d = derive(f)
                self.assertEqual((d["state"], d["reason"]), (None, "life_unreadable"), over)
        for said in ("writer", "never"):
            self.assertEqual(state(facts(reopened_last_by=said)), "new")

    def test_unreadable_content_defers(self):
        for over in ({"content_id": None}, {"content_id": "c1"}, {"content_id": "sha256:"}, {"content_id": "sha256:C1"},
                     {"content_changed_at": None}, {"content_changed_at": "yesterday"}):
            for f in (facts(**over), facts(state="closed", **over)):
                d = derive(f)
                self.assertEqual((d["state"], d["reason"]), (None, "content_unreadable"), over)

    def test_what_cannot_be_read_is_read_in_its_order(self):
        f = facts(label_events=None, linked=None, life_started_at=None, content_id=None)
        self.assertEqual(derive(f)["reason"], "label_unreadable")
        self.assertEqual(derive(dict(f, label_events=[]))["reason"], "linked_unreadable")
        self.assertEqual(derive(dict(f, label_events=[], linked=[]))["reason"], "life_unreadable")
        self.assertEqual(derive(dict(f, label_events=[], linked=[], life_started_at=at(0)))["reason"],
                         "content_unreadable")
        self.assertEqual(derive(dict(f, complete={"timeline": True, "linked": True, "runs": False}))["reason"],
                         "facts_incomplete")


class Done(unittest.TestCase):
    """Row 1: a linked pull request merged with a non-empty diff in the issue's present life."""

    def test_a_merge_in_this_life_is_done_whatever_else_holds(self):
        merged = [pr(is_open=False, merged=5)]
        d = derive(facts(linked=merged))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("done", "merged", ["11"]))
        for f in (facts(state="closed", linked=merged), outsiders(linked=merged),
                  facts(label_events=[labelled(HOLD)], linked=merged), facts(linked=merged + [pr(12), pr(13)])):
            self.assertEqual(state(f, cfg=config(served_from=None)), "done")

    def test_a_merge_at_the_start_of_a_life_is_done_and_one_before_it_is_not(self):
        merged = [pr(is_open=False, merged=5)]
        for start, want in ((4, "done"), (5, "done"), (6, "new")):
            self.assertEqual(state(facts(life_started_at=at(start), reopened_last_by="writer", linked=merged)), want)

    def test_an_empty_merge_is_not_done(self):
        self.assertEqual(state(facts(linked=[pr(is_open=False, merged=5, empty=True)])), "new")
        self.assertEqual(state(facts(linked=[pr(is_open=False, merged=5, empty=False)])), "done")

    def test_only_a_linked_merge_is_done(self):
        self.assertEqual(state(facts(linked=[strangers(is_open=False, merged=5)])), "new")
        self.assertEqual(state(facts(linked=[pr(cls="dependency", by=OTHER_APP, is_open=False, merged=5)])), "new")
        self.assertEqual(state(facts(linked=[strangers(admitted=True, is_open=False, merged=5)])), "done")
        self.assertEqual(state(facts(linked=[agents(is_open=False, merged=5)])), "done")
        self.assertEqual(state(facts(linked=[pr(is_open=False, closed=5)])), "new")


class Declined(unittest.TestCase):
    """Row 2: closed in any other way, and so it stays unless a person with write access reopens it."""

    def test_a_closed_issue_is_declined(self):
        d = derive(facts(state="closed"))
        self.assertEqual((d["state"], d["reason"]), ("declined", "closed"))
        self.assertEqual(state(facts(state="open")), "new")

    def test_a_reopening_by_anyone_but_a_writer_leaves_it_declined(self):
        d = derive(facts(reopened_last_by="other", label_events=[labelled(READY)]))
        self.assertEqual((d["state"], d["reason"]), ("declined", "reopened_by_other"))
        self.assertEqual(state(facts(reopened_last_by="writer", label_events=[labelled(READY)])), "ready")


class NotServed(unittest.TestCase):
    """Row 3: the Consumer entry does not serve it, or it or its linked draft carries a person's hands-off."""

    def test_no_issue_is_served_until_the_maintainer_turns_issues_on(self):
        self.assertEqual(json.loads((ROOT / "config" / "defaults.json").read_text())["issues"],
                         {"served_from": None, "left_out_labels": [], "left_out_types": [],
                          "label_apps": {"factory:triage": None, "factory:ready": None}})
        d = derive(facts(label_events=[labelled(READY)]), cfg=copy.deepcopy(CONFIG))
        self.assertEqual((d["state"], d["reason"]), ("not_served", "left_out"))
        for cfg in (config(served_from=None), config(served_from="2026-10-11")):
            self.assertEqual(state(facts(), cfg=cfg), "not_served")

    def test_an_issue_whose_life_began_before_the_date_served_is_left_out(self):
        for start, want in (("2026-10-11T11:59:59Z", "new"), (at(0), "new"), ("2026-10-11T12:00:01Z", "not_served")):
            self.assertEqual(state(facts(), cfg=config(served_from=start)), want, start)

    def test_a_left_out_label_or_type_is_not_served(self):
        self.assertEqual(state(facts(label_names=["bug", "epic"])), "not_served")
        self.assertEqual(state(facts(label_names=["bug"])), "new")
        self.assertEqual(state(facts(type="Epic")), "not_served")
        self.assertEqual(state(facts(type="Bug")), "new")

    def test_a_persons_hands_off_is_not_served(self):
        d = derive(facts(label_events=[labelled(HANDS_OFF), labelled(HOLD)]))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("not_served", "hands_off", [HANDS_OFF]))
        self.assertEqual(state(facts(label_events=[labelled(HANDS_OFF), unlabelled(HANDS_OFF)])), "new")

    def test_hands_off_anyone_else_placed_or_a_person_removed_in_that_second_is_a_hold(self):
        for events in ([labelled(HANDS_OFF, OTHER_APP)], [labelled(HANDS_OFF, OUTSIDER)],
                       [labelled(HANDS_OFF, minute=3), unlabelled(HANDS_OFF, minute=3)]):
            d = derive(facts(label_events=events))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("held", "human_hold", [HANDS_OFF]), events)
        # A removal by anyone but a person ends nothing, so in the same second it ties with nothing.
        for by in (CONTROLLER, OTHER_APP):
            events = [labelled(HANDS_OFF, minute=3), unlabelled(HANDS_OFF, by, 3)]
            self.assertEqual(state(facts(label_events=events)), "not_served", by)

    def test_hands_off_on_the_linked_draft_and_only_the_draft(self):
        self.assertEqual(state(facts(linked=[agents(draft=True, events=[labelled(HANDS_OFF)])])), "not_served")
        self.assertEqual(state(facts(linked=[agents(draft=False, events=[labelled(HANDS_OFF)])])), "in_review")
        self.assertEqual(state(facts(linked=[agents(draft=True, events=[labelled(HANDS_OFF, OTHER_APP)])])), "held")
        self.assertEqual(state(facts(linked=[strangers(draft=True, events=[labelled(HANDS_OFF)])])), "new")


class Held(unittest.TestCase):
    """Row 4: a Hold, whoever added it, on the issue or its linked draft; or more than one linked pull request open."""

    def test_a_hold_whoever_added_it_holds(self):
        for by in (WRITER, CONTROLLER, OTHER_APP, OUTSIDER, MACHINE):
            d = derive(facts(label_events=[labelled(HOLD, by)]))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("held", "human_hold", [HOLD]), by)
        self.assertEqual(state(outsiders(label_events=[labelled(HOLD)])), "held")

    def test_only_a_person_releases_a_hold(self):
        self.assertEqual(state(facts(label_events=[labelled(HOLD), unlabelled(HOLD)])), "new")
        self.assertEqual(state(facts(label_events=[labelled(HOLD, OTHER_APP), unlabelled(HOLD, COLLEAGUE)])), "new")
        for by in (CONTROLLER, OUTSIDER, MACHINE):
            self.assertEqual(state(facts(label_events=[labelled(HOLD), unlabelled(HOLD, by)])), "held", by)
        self.assertEqual(state(facts(label_events=[labelled(HOLD, minute=2), unlabelled(HOLD, minute=2)])), "held")

    def test_a_hold_on_the_linked_draft_holds_the_issue(self):
        d = derive(facts(linked=[agents(draft=True, events=[labelled(HOLD, OTHER_APP)])]))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("held", "human_hold", [HOLD]))
        self.assertEqual(state(facts(linked=[agents(draft=True, events=[labelled(HOLD), unlabelled(HOLD)])])),
                         "in_progress")
        self.assertEqual(state(facts(linked=[agents(draft=False, events=[labelled(HOLD)])])), "in_review")
        self.assertEqual(state(facts(linked=[strangers(draft=True, events=[labelled(HOLD)])])), "new")

    def test_more_than_one_linked_pull_request_open_holds(self):
        d = derive(facts(linked=[pr(), agents(number=12, draft=True)]))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("held", "linked_twice", ["11", "12"]))
        self.assertEqual(state(outsiders(linked=[pr(), pr(number=12)])), "held")
        self.assertEqual(state(facts(linked=[pr(), pr(number=12, is_open=False, closed=4)])), "in_review")
        self.assertEqual(state(facts(linked=[pr(), strangers(number=12)])), "in_review")


class Accepted(unittest.TestCase):
    """Row 5. Accepted: served, and a person with write access opened it or factory:admit counts."""

    def test_an_insiders_issue_is_accepted_and_an_outsiders_is_not(self):
        self.assertEqual(state(facts(label_events=[labelled(READY)])), "ready")
        self.assertEqual(state(outsiders(label_events=[labelled(READY)])), "new")
        d = derive(outsiders())
        self.assertEqual((d["state"], d["reason"]), ("new", "not_accepted"))
        self.assertEqual(state(facts(author_can_write=None, label_events=[labelled(READY)])), "new")

    def test_a_persons_admission_after_the_last_edit_accepts_it(self):
        self.assertEqual(state(outsiders(label_events=[labelled(ADMIT), labelled(READY, minute=2)])), "ready")
        for by in (OTHER_APP, CONTROLLER, OUTSIDER, MACHINE):
            self.assertEqual(state(outsiders(label_events=[labelled(ADMIT, by), labelled(READY, minute=2)])), "new", by)

    def test_an_edit_at_or_after_the_admission_ends_it(self):
        for edited, want in ((0, "ready"), (1, "new"), (2, "new")):
            f = outsiders(content_changed_at=at(edited), label_events=[labelled(ADMIT), labelled(READY, minute=3)])
            self.assertEqual(state(f), want, edited)

    def test_an_admission_outlasts_a_reopening_and_ends_when_a_person_removes_it(self):
        events = [labelled(ADMIT), labelled(TRIAGE, CONTROLLER, 12)]
        self.assertEqual(state(outsiders(life_started_at=at(10), reopened_last_by="writer", label_events=events)),
                         "triage")
        self.assertEqual(state(outsiders(label_events=events + [unlabelled(ADMIT, minute=13)])), "new")
        self.assertEqual(state(outsiders(label_events=events + [unlabelled(ADMIT, CONTROLLER, 13)])), "triage")

    def test_acceptance_lapsed_after_work_began_is_told_apart(self):
        lapsed = outsiders(content_changed_at=at(9), label_events=[labelled(ADMIT), labelled(TRIAGE, CONTROLLER, 2)])
        self.assertEqual(derive(lapsed)["reason"], "acceptance_lapsed")
        with_draft = outsiders(content_changed_at=at(9), label_events=[labelled(ADMIT)], linked=[agents(draft=True)])
        self.assertEqual(derive(with_draft)["reason"], "acceptance_lapsed")
        self.assertEqual(derive(outsiders(content_changed_at=at(9), label_events=[labelled(ADMIT)]))["reason"],
                         "not_accepted")
        self.assertEqual(derive(outsiders(linked=[strangers()]))["reason"], "not_accepted")


class Linked(unittest.TestCase):
    """A linked pull request: the Factory's, a person with write access's, or an outsider's the Maintainer once admitted."""

    def test_the_factorys_and_a_writers_pull_requests_are_linked(self):
        for entry in (agents(), pr()):
            d = derive(facts(linked=[entry]))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("in_review", "linked_ready", ["11"]))
        for cls in ("dependency", "outside"):
            self.assertEqual(state(facts(linked=[pr(cls=cls)])), "new", cls)

    def test_an_outsiders_pull_request_is_linked_once_a_person_has_admitted_it(self):
        self.assertEqual(state(facts(linked=[strangers(admitted=True)])), "in_review")
        self.assertEqual(state(facts(linked=[strangers(admitted=True, events=[labelled(ADMIT), unlabelled(ADMIT)])])),
                         "in_review")
        for by in (OTHER_APP, OUTSIDER, MACHINE):
            self.assertEqual(state(facts(linked=[strangers(events=[labelled(ADMIT, by)])])), "new", by)
        self.assertEqual(state(facts(linked=[strangers(events=[labelled(HOLD)])])), "new")


class Working(unittest.TestCase):
    """Rows 6 and 7: one linked pull request open and ready; one open as a draft, or an opening Run holds the issue."""

    def test_a_linked_draft_is_in_progress(self):
        d = derive(facts(linked=[agents(draft=True)]))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("in_progress", "linked_draft", ["11"]))
        self.assertEqual(state(facts(label_events=[labelled(READY)], linked=[agents(draft=True)])), "in_progress")

    def test_an_opening_run_holds_the_issue_until_it_ends(self):
        d = derive(facts(label_events=[labelled(READY)]), [opening()])
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("in_progress", "opening_run", []))
        self.assertEqual(state(facts(), [opening("queued")]), "in_progress")
        self.assertEqual(state(facts(label_events=[labelled(READY)]), [opening("completed")]), "ready")
        self.assertEqual(state(facts(label_events=ACCEPTED), [run(status="in_progress")]), "triage")
        other = dict(opening(), item=dict(ITEM, number=8))
        self.assertEqual(state(facts(label_events=[labelled(READY)]), [other]), "ready")


class Counts(unittest.TestCase):
    """Rows 8 to 10, and when a label counts (I-41)."""

    def test_ready_and_triage_count_when_a_person_or_the_declared_app_added_them(self):
        d = derive(facts(label_events=[labelled(READY)]))
        self.assertEqual((d["state"], d["reason"]), ("ready", "ready"))
        d = derive(facts(label_events=[labelled(TRIAGE, CONTROLLER)]))
        self.assertEqual((d["state"], d["reason"]), ("triage", "triage"))
        self.assertEqual(state(facts(label_events=[labelled(TRIAGE, COLLEAGUE)])), "triage")
        self.assertEqual(state(facts(label_events=READIED), JUDGED), "ready")
        for label, by in ((READY, CONTROLLER), (TRIAGE, READINESS), (READY, OTHER_APP), (TRIAGE, OUTSIDER),
                          (READY, MACHINE), (READY, {"kind": "lens", "name": "pr-review", "can_write": True})):
            self.assertEqual(state(facts(label_events=[labelled(label, by)])), "new", (label, by))
        lens = dict(READINESS, kind="lens")
        self.assertEqual(state(facts(label_events=[labelled(READY, lens)])), "ready")

    def test_only_an_app_is_read_as_the_declared_app(self):
        cfg = config(label_apps={"factory:triage": None, "factory:ready": "readiness"})
        for kind, want in (("app", "ready"), ("lens", "ready"), ("human", "new")):
            by = {"kind": kind, "name": "readiness", "can_write": False}
            self.assertEqual(state(facts(label_events=[labelled(READY, by)]), cfg=cfg), want, kind)

    def test_no_app_counts_until_it_is_declared(self):
        cfg = config(label_apps={"factory:triage": None, "factory:ready": None})
        self.assertEqual(state(facts(label_events=READIED), JUDGED, cfg), "new")
        self.assertEqual(state(facts(label_events=[labelled(READY)]), cfg=cfg), "ready")

    def test_otherwise_it_is_new_and_due_to_be_accepted(self):
        d = derive(facts())
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("new", "acceptance_due", []))

    def test_triage_and_ready_count_only_in_the_present_life(self):
        for label, want in ((READY, "ready"), (TRIAGE, "triage")):
            for added, got in ((11, want), (10, "new"), (9, "new")):
                f = facts(life_started_at=at(10), reopened_last_by="writer", content_changed_at=at(0),
                          label_events=[labelled(label, minute=added)])
                self.assertEqual(state(f), got, (label, added))

    def test_ready_counts_only_after_the_last_edit_and_triage_whenever(self):
        for edited, want in ((2, "ready"), (3, "triage"), (4, "triage")):
            f = facts(content_changed_at=at(edited), label_events=[labelled(TRIAGE, CONTROLLER, 1), labelled(READY, minute=3)])
            self.assertEqual(state(f), want, edited)
        self.assertEqual(state(facts(content_changed_at=at(5), label_events=[labelled(TRIAGE, CONTROLLER, 1)])),
                         "triage")

    def test_a_factory_ready_counts_only_for_the_content_its_run_judged(self):
        self.assertEqual(state(facts(label_events=READIED), [run(content=OTHER)]), "triage")
        self.assertEqual(state(facts(label_events=READIED), [run(content=OTHER, minute=2), run(minute=4, name="r2")]),
                         "ready")
        self.assertEqual(state(facts(label_events=READIED), [run(minute=2), run(content=OTHER, minute=4, name="r2")]),
                         "triage")
        # The Run that completed just before the label: one started after it, or still running, is not it.
        self.assertEqual(state(facts(label_events=READIED), [run(), run(content=OTHER, minute=6, name="r2")]), "ready")
        self.assertEqual(state(facts(label_events=READIED), [run(), run(content=OTHER, minute=5, name="r2",
                                                                         status="in_progress")]), "ready")
        self.assertEqual(state(facts(label_events=READIED), [run(), run(content=OTHER, minute=5, name="r2")]), "triage")
        # Two that started in the same second must both have judged this content.
        self.assertEqual(state(facts(label_events=READIED), [run(), run(content=OTHER, name="r2")]), "triage")
        self.assertEqual(state(facts(label_events=READIED), [run(), run(name="r2")]), "ready")
        # Another issue's Run is not this one's.
        self.assertEqual(state(facts(label_events=READIED), [dict(run(content=OTHER), item=dict(ITEM, number=8))]),
                         "ready")
        # A person's ready is a person's verdict, whatever a Run judged.
        self.assertEqual(state(facts(label_events=[labelled(READY, minute=5)]), [run(content=OTHER)]), "ready")

    def test_a_factory_ready_whose_run_record_has_expired_is_read_by_its_time(self):
        self.assertEqual(state(facts(label_events=READIED)), "ready")
        self.assertEqual(state(facts(content_changed_at=at(5), label_events=READIED)), "triage")

    def test_any_removal_at_or_after_the_latest_add_ends_ready_and_triage(self):
        for by in (WRITER, CONTROLLER, OTHER_APP, OUTSIDER):
            for minute, want in ((5, "triage"), (6, "triage"), (4, "ready")):
                events = READIED + [unlabelled(READY, by, minute)]
                self.assertEqual(state(facts(label_events=events), JUDGED), want, (by, minute))
        again = READIED + [unlabelled(READY, minute=6), labelled(READY, minute=7)]
        self.assertEqual(state(facts(label_events=again)), "ready")
        self.assertEqual(state(facts(label_events=ACCEPTED + [unlabelled(TRIAGE, CONTROLLER, 3)])), "new")

    def test_the_latest_add_is_the_one_read(self):
        self.assertEqual(state(facts(label_events=[labelled(READY, minute=1), labelled(READY, OTHER_APP, 2)])), "new")
        self.assertEqual(state(facts(label_events=[labelled(READY, OTHER_APP, 1), labelled(READY, minute=2)])), "ready")


if __name__ == "__main__":
    unittest.main()
