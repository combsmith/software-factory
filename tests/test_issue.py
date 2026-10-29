"""The boundary cases of an issue's State (design §4.1, the issue Lifecycle), written before the code.

The situations the reviews of the issue Lifecycle said went wrong are one table, seeded by the throwaway model that
held them, `derive_issue_model.py`, and not copied from it. Each rule then has its boundary, from both sides. The
builders live here, not in `tests/support.py`: an issue's facts are not a pull request's.
"""
from __future__ import annotations

import copy
import datetime
import json
import pathlib
import tempfile
import unittest

from kernel import issue
from tests.support import CONFIG, MAINTAINER, NOW, ROOT, context
from tools import check_purity
from tools.jsonschema_lite import validate

LIFECYCLE = json.loads((ROOT / "lifecycle" / "issue.json").read_text())
SCHEMA = json.loads((ROOT / "schemas" / "issue-facts.schema.json").read_text())
DECISION = json.loads((ROOT / "schemas" / "issue-decision.schema.json").read_text())
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
ANALYST = {"kind": "app", "name": "combsmith-sf-business-analyst[bot]", "can_write": True}
# The Intents the Kernel admits on an issue, each with its Role and that Role's App, once the Maintainer turns them on.
INVESTIGATE, JUDGE, OPEN = "investigate-issue", "judge-readiness", "open-pull-request"
INTENTS = {INVESTIGATE: {"role": "business-analyst", "app": ANALYST["name"]},
           JUDGE: {"role": "readiness", "app": READINESS["name"]},
           OPEN: {"role": "dev-lead", "app": AUTHOR_APP["name"]}}
# The issues served once the Maintainer turns them on, with the App declared for each label that lets work go.
SERVED = {"served_from": "2026-01-01T00:00:00Z", "left_out_labels": ["epic", "idea"], "left_out_types": ["Epic"],
          "label_apps": {"factory:triage": CONTROLLER["name"], "factory:ready": READINESS["name"]},
          "intents": INTENTS}
TRIAGE, READY, HOLD, HANDS_OFF, ADMIT = "factory:triage", "factory:ready", "factory:hold", "factory:hands-off", \
    "factory:admit"


def at(minute: int) -> str:
    """A time `minute` minutes after the issue was opened, at noon."""
    return "2026-10-11T12:%02d:00Z" % minute


def config(**issues) -> dict:
    """The configuration, with issues served as SERVED says but for what differs, and the issue's own Lifecycle."""
    c = copy.deepcopy(CONFIG)
    c["issues"] = dict(copy.deepcopy(SERVED), **issues)
    c["lifecycle"] = copy.deepcopy(LIFECYCLE)
    return c


def labelled(label: str, by=None, minute: int = 1, action: str = "labeled") -> dict:
    """A label event from the issue's timeline. By default the Maintainer adds `label` a minute after it was opened."""
    return {"label": label, "action": action, "by": dict(WRITER if by is None else by), "at": at(minute)}


def unlabelled(label: str, by=None, minute: int = 2) -> dict:
    return labelled(label, by, minute, "unlabeled")


def pr(number=11, by=None, cls="maintainer", is_open=True, draft=False, merged=None, closed=None, empty=False,
       events=(), opened=0, closed_issue="merge") -> dict:
    """A pull request that closes the issue. By default the Maintainer's, opened with the issue, open and ready. A
    merged one closed then, and closed the issue in its second, as the issue's timeline records it (P-33);
    `closed_issue=None` is one the issue's timeline never names, as one whose reference an edit added (P-46)."""
    if merged is not None and closed is None:
        closed = merged
    if closed_issue == "merge":
        closed_issue = merged
    return {"number": number, "class": cls, "opener": dict(WRITER if by is None else by), "open": is_open,
            "draft": draft, "opened_at": at(opened), "merged_at": None if merged is None else at(merged),
            "closed_at": None if closed is None else at(closed), "empty": empty, "label_events": list(events),
            "closed_issue_at": None if closed_issue is None else at(closed_issue)}


def agents(**over) -> dict:
    """The Factory's own pull request: its author's App opened it."""
    return pr(**dict({"by": AUTHOR_APP, "cls": "agent"}, **over))


def strangers(admitted=False, **over) -> dict:
    """An outsider's pull request, which the Maintainer has once admitted, or not."""
    events = [labelled(ADMIT, minute=3)] if admitted else []
    return pr(**dict({"by": OUTSIDER, "cls": "outside", "events": events}, **over))


def facts(**over) -> dict:
    """An open issue the Maintainer opened at minute 0, with no label and no pull request, read in full."""
    f = {"schema": "issue-facts/1", "item": dict(ITEM), "state": "open", "author": dict(WRITER), "type": None, "label_names": [], "assignees": [],
         "life_started_at": at(0), "reopened_last_by": "never", "content_id": THIS, "content_changed_at": at(0),
         "label_events": [], "linked": [], "role_comments": [], "last_writer_action_at": at(0),
         "last_writer_comment_at": None, "acts_since_writer": 0, "branch_head": None,
         "complete": {"timeline": True, "linked": True, "runs": True},
         "read_at": at(50)}
    f.update(over)
    # The two times a close and a reopening carry, as GitHub holds them, unless the case gives them: a person's close
    # a minute after the opening, and a reopening at the start of the present life.
    if "reopened_last_at" not in over:
        f["reopened_last_at"] = f["life_started_at"] if f["reopened_last_by"] in ("writer", "other") else None
    if "closed_first_at" not in over:
        # Closed, a minute after the opening; open after an outsider's reopening, the close it undid in its second.
        f["closed_first_at"] = at(1) if f["state"] == "closed" else (
            f["reopened_last_at"] if f["reopened_last_by"] == "other" else None)
    return f


def outsiders(**over) -> dict:
    """An issue an outsider opened."""
    return facts(**dict({"author": dict(OUTSIDER)}, **over))


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
     facts(reopened_last_by="other", reopened_last_at=at(6), linked=[pr(is_open=False, merged=5)]), [], "done"),
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
    ("a Factory ready whose Run record has expired: nothing shows what was judged", facts(label_events=READIED), [],
     "triage"),
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
        # Every control label a pull request's facts carry is one an issue's are read for, as terms.py lists them.
        for name in issue.t.CONTROL_LABELS:
            no_by = labelled(name)
            del no_by["by"]
            d = derive(facts(label_events=[no_by]))
            self.assertEqual((d["state"], d["reason"]), (None, "label_unreadable"), name)
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
               dict(good, open=False, closed_at="2026-10-11"), dict(good, open=False, closed_at=at(5), merged_at=1),
               # No moment, though it sorts after the opening, so only the reading of the time refuses it.
               dict(good, open=False, closed_at="2026-10-11T25:00:00Z"),
               dict(good, label_events=[dict(labelled(HOLD), by=None)]), dict(good, label_events=None), "11"]
        no_class = dict(good)
        del no_class["class"]
        for entry in bad + [no_class]:
            for f in (facts(linked=[entry]), facts(state="closed", linked=[entry])):
                d = derive(f)
                self.assertEqual((d["state"], d["reason"]), (None, "linked_unreadable"), entry)
        self.assertEqual(derive(facts(linked=None))["reason"], "linked_unreadable")
        # The other side: the first number, closed unmerged, merged, and a stranger's pull request are read.
        self.assertEqual(state(facts(linked=[pr(number=1)])), "in_review")
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

    def test_an_unreadable_author_defers(self):
        for value in (None, "don-petry", {"kind": "human", "name": "don-petry"}, dict(WRITER, kind="User"),
                      dict(WRITER, name="x[bot]"), dict(MACHINE, name="someone"), dict(WRITER, name=CONFIG["approver"])):
            for f in (facts(author=value), facts(state="closed", author=value)):
                d = derive(f)
                self.assertEqual((d["state"], d["reason"]), (None, "author_unreadable"), value)
        f = facts()
        del f["author"]
        self.assertEqual(derive(f)["reason"], "author_unreadable")
        self.assertEqual(state(facts(author=dict(MACHINE))), "new")

    def test_a_content_id_has_as_many_digits_as_the_schema_allows(self):
        pattern = SCHEMA["$defs"]["content_id"]["pattern"]
        self.assertIn("{%d,%d}" % (len(issue.CONTENT_FEWEST), len(issue.CONTENT_MOST)), pattern)
        for digits, readable in ((3, False), (4, True), (64, True), (65, False)):
            d = derive(facts(content_id="sha256:" + "a" * digits))
            self.assertEqual(d["reason"] != "content_unreadable", readable, digits)

    def test_unreadable_content_defers(self):
        for over in ({"content_id": None}, {"content_id": "c1"}, {"content_id": "sha256:"}, {"content_id": "sha256:C1"},
                     {"content_changed_at": None}, {"content_changed_at": "yesterday"}):
            for f in (facts(**over), facts(state="closed", **over)):
                d = derive(f)
                self.assertEqual((d["state"], d["reason"]), (None, "content_unreadable"), over)

    def test_what_cannot_be_read_is_read_in_its_order(self):
        f = facts(state=None, label_events=None, label_names=None, linked=None, life_started_at=None, content_id=None,
                  type=1)
        cfg = config(served_from="today")
        order = (("state", "open", "state_unreadable"), ("label_events", [], "label_unreadable"),
                 ("label_names", [], "label_unreadable"), ("linked", [], "linked_unreadable"),
                 ("life_started_at", at(0), "life_unreadable"), ("content_id", THIS, "content_unreadable"),
                 ("type", None, "type_unreadable"))
        for field, readable, reason in order:
            self.assertEqual(derive(f, cfg=cfg)["reason"], reason, field)
            f = dict(f, **{field: readable})
        self.assertEqual(derive(f, cfg=cfg)["reason"], "issues_unreadable")
        self.assertEqual(derive(f)["reason"], "acceptance_due")
        broken = facts(state=None, label_events=None, complete={"timeline": True, "linked": True, "runs": False})
        self.assertEqual(derive(broken, cfg=cfg)["reason"], "facts_incomplete")

    def test_an_unreadable_state_defers(self):
        for value in ("merged", "OPEN", None, 1):
            for f in (facts(state=value), facts(state=value, linked=[pr(is_open=False, merged=5)])):
                d = derive(f)
                self.assertEqual((d["state"], d["reason"]), (None, "state_unreadable"), value)
        f = facts()
        del f["state"]
        self.assertEqual(derive(f)["reason"], "state_unreadable")
        self.assertEqual(state(facts(state="closed")), "declined")

    def test_unreadable_label_names_defer(self):
        for value in (None, "epic", [None], [""], [1], {"epic": True}):
            d = derive(facts(label_names=value))
            self.assertEqual((d["state"], d["reason"]), (None, "label_unreadable"), value)
        f = facts()
        del f["label_names"]
        self.assertEqual(derive(f)["reason"], "label_unreadable")
        for value in ([], ["bug"]):
            self.assertEqual(state(facts(label_names=value)), "new", value)

    def test_an_unreadable_type_defers(self):
        for value in ("", 1, ["Epic"]):
            d = derive(facts(type=value))
            self.assertEqual((d["state"], d["reason"]), (None, "type_unreadable"), value)
        f = facts()
        del f["type"]
        self.assertEqual(derive(f)["reason"], "type_unreadable")
        for value in (None, "Bug"):
            self.assertEqual(state(facts(type=value)), "new", value)

    def test_an_issues_block_that_cannot_be_read_defers(self):
        missing = copy.deepcopy(CONFIG)
        del missing["issues"]
        apps = SERVED["label_apps"]
        for cfg in (missing, dict(config(), issues=None), dict(config(), issues=[]),
                    config(served_from="2026-10-11"), config(served_from=1),
                    config(left_out_labels=None), config(left_out_labels=[1]), config(left_out_labels="epic"),
                    config(left_out_types=None), config(left_out_types=[""]),
                    config(label_apps=None), config(label_apps={}), config(label_apps={"factory:triage": None}),
                    config(label_apps={"factory:ready": None}), config(label_apps=dict(apps, **{"factory:ready": ""})),
                    config(label_apps=dict(apps, **{"factory:triage": 1}))):
            for f in (facts(), facts(state="closed")):
                d = derive(f, cfg=cfg)
                self.assertEqual((d["state"], d["reason"]), (None, "issues_unreadable"), cfg.get("issues"))
        self.assertEqual(derive(facts(), cfg=copy.deepcopy(CONFIG))["reason"], "left_out")
        self.assertEqual(state(facts(), cfg=config(label_apps={"factory:triage": None, "factory:ready": None})), "new")


class Done(unittest.TestCase):
    """Row 1: a linked pull request merged with a non-empty diff in the issue's present life."""

    def test_a_merge_in_this_life_is_done_whatever_else_holds(self):
        merged = [pr(is_open=False, merged=5)]
        d = derive(facts(linked=merged))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("done", "merged", ["11"]))
        for f in (outsiders(linked=merged), facts(label_events=[labelled(HANDS_OFF)], linked=merged),
                  facts(linked=merged + [pr(12), pr(13)])):
            self.assertEqual(state(f, cfg=config(served_from=None)), "done")

    def test_a_merge_counts_only_where_the_issues_timeline_names_it_the_closer(self):  # issue 267, trials/P-46.json
        # P-46: an edit to a merged pull request's description after the merge added an open issue to its closing
        # references, and GitHub closed nothing; the issue's timeline records no close by it. A merge that closed the
        # issue is recorded at the merge as the closer of the issue's close (P-33), which that edit did not write.
        late = pr(is_open=False, merged=5, closed_issue=None)
        # Read long after the merge, an open issue a merged pull request names that closed nothing is read as if it
        # named nothing: not done, and no wait either; an outsider's reopening before it reads as before.
        self.assertEqual(derive(facts(linked=[late])), derive(facts()))
        self.assertEqual(derive(facts(linked=[late], reopened_last_by="other", reopened_last_at=at(3)))["reason"],
                         "reopened_by_other")
        d = derive(facts(label_events=[labelled(HOLD, minute=4)], linked=[late]))
        self.assertEqual((d["state"], d["reason"]), ("held", "human_hold"))
        # The merge that closed it, in its second or after: done.
        for closer in (5, 6):
            d = derive(facts(state="closed", closed_first_at=at(closer), linked=[pr(is_open=False, merged=5,
                                                                                   closed_issue=closer)]))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("done", "merged", ["11"]))
        # A person's close after a merge that did not close the issue: declined, whatever the references say now.
        d = derive(facts(state="closed", closed_first_at=at(8), linked=[late]))
        self.assertEqual((d["state"], d["reason"]), ("declined", "closed"))
        # A merge that landed while the issue stood closed, its first close before the merge or in its second, closed
        # nothing, and is the contradiction it was (issue 227); so in a life a writer's reopening began.
        for f in (facts(state="closed", closed_first_at=at(4), linked=[late]),
                  facts(state="closed", closed_first_at=at(5), linked=[late]),
                  facts(state="closed", life_started_at=at(2), reopened_last_by="writer", closed_first_at=at(4),
                        linked=[late])):
            d = derive(f)
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("declined", "merged_while_declined", ["11"]), f)
        # An outsider's reopening before the merge left the issue open, so a merge then that closed nothing, while the
        # issue stays open, is read as nothing; one in the merge's second leaves the issue read as closed at it, the
        # reading that names it.
        d = derive(facts(closed_first_at=at(2), reopened_last_by="other", reopened_last_at=at(4), linked=[late]))
        self.assertEqual((d["state"], d["reason"]), ("declined", "reopened_by_other"))
        for f in (facts(closed_first_at=at(2), reopened_last_by="other", reopened_last_at=at(5), linked=[late]),
                  facts(state="closed", closed_first_at=at(2), reopened_last_by="other", reopened_last_at=at(5),
                        linked=[late])):
            d = derive(f)
            self.assertEqual((d["state"], d["reason"]), ("declined", "merged_while_declined"), f)
        # Closed again since, at a time the facts do not carry: read as closed at the merge, so the contradiction is
        # named, not read as a quiet close (the Codex review of the pull request for issue 267).
        d = derive(facts(state="closed", closed_first_at=at(2), reopened_last_by="other", reopened_last_at=at(4),
                         linked=[late]))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("declined", "merged_while_declined", ["11"]))
        # Two merges in one second, the first of the life: one that closed the issue makes it done, though the other
        # closed nothing.
        d = derive(facts(state="closed", closed_first_at=at(5), linked=[pr(is_open=False, merged=5),
                                                                      dict(late, number=12)]))
        self.assertEqual((d["state"], d["reason"]), ("done", "merged"))
        # Of two merges, only the one that closed the issue is done's evidence.
        d = derive(facts(state="closed", closed_first_at=at(6), linked=[late, pr(number=12, is_open=False, merged=6)]))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("done", "merged", ["12"]))

    def test_an_open_issue_waits_quietly_for_the_close_a_merge_makes(self):  # issue 267, trials/P-33.json
        # GitHub closes the issue a second after the merge, and records the close two (P-33). An open issue read within
        # max_close_lag_seconds of a merge that has not closed it yet waits, admits nothing, and asks nobody; read at
        # the limit or after it, the merge closed nothing, as an edit's reference never will (P-46), and is read past.
        lag = LIMITS["max_close_lag_seconds"]
        merged = at(5)
        def read(after: int) -> str:
            return "2026-10-11T12:%02d:%02dZ" % divmod(5 * 60 + after, 60)
        late = pr(is_open=False, merged=5, closed_issue=None)
        ready = dict(facts(label_events=[labelled(READY)], linked=[late]))
        for f in (ready, facts(linked=[late, agents(number=12, draft=True)]),
                  facts(label_events=[labelled(HOLD, minute=4)], linked=[late])):
            d = derive(dict(f, read_at=read(lag - 1)))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), (None, "merge_closing", ["11"]), f)
            d = decide(dict(f, read_at=read(lag - 1)))
            self.assertEqual((what(d), d["attention"]), (("defer", "merge_closing", None), "none"))
        self.assertEqual(derive(dict(ready, read_at=read(lag))), derive(dict(ready, read_at=read(lag), linked=[])))
        self.assertEqual(derive(dict(ready, read_at=read(0)))["reason"], "merge_closing")
        self.assertEqual(merged, read(0))
        # A read the facts time before the merge is no read after it: the issue waits.
        self.assertEqual(derive(dict(ready, read_at=at(0)))["reason"], "merge_closing")
        # A stranger's merge moves nothing, in the lag as after it (I-39); nor an empty merge, nor one before the life.
        for link in (strangers(is_open=False, merged=5, closed_issue=None), dict(late, empty=True)):
            f = dict(ready, linked=[link], read_at=read(1))
            self.assertEqual(derive(f), derive(dict(f, linked=[])))
        f = dict(ready, life_started_at=at(6), reopened_last_by="writer", reopened_last_at=at(6), read_at=read(1))
        self.assertEqual(derive(f), derive(dict(f, linked=[])))
        # A closed issue does not wait: its close is in the facts, and was not this merge's.
        d = derive(facts(state="closed", closed_first_at=at(8), linked=[late], read_at=read(1)))
        self.assertEqual((d["state"], d["reason"]), ("declined", "closed"))
        # A limit or a read time that cannot be read defers, and only where the wait is asked.
        for bad in (None, 0, -1, True, 300.0, "300"):
            cfg = config()
            if bad is None:
                del cfg["limits"]["max_close_lag_seconds"]
            else:
                cfg["limits"]["max_close_lag_seconds"] = bad
            d = derive(dict(ready, read_at=read(1)), cfg=cfg)
            self.assertEqual((d["state"], d["reason"]), (None, "limits_unreadable"), bad)
            self.assertEqual(decide(dict(ready, read_at=read(1)), cfg=cfg)["attention"], "needs_you")
            self.assertEqual(derive(dict(ready, linked=[]), cfg=cfg)["reason"], derive(dict(ready, linked=[]))["reason"])
        for bad in ("now", None, "2026-10-11T12:09"):
            d = derive(dict(ready, read_at=bad))
            self.assertEqual((d["state"], d["reason"]), (None, "linked_unreadable"), bad)

    def test_a_close_of_the_issue_that_cannot_be_read_defers(self):  # issue 267
        # The close a link made is read whole: a time, and only of a merge, no earlier than it. A pull request closes
        # an issue only by merging into the default branch.
        merged = pr(is_open=False, merged=5)
        for bad in ({"closed_issue_at": "5"}, {"closed_issue_at": at(4)}, {"closed_issue_at": 5},
                    {"merged_at": None, "closed_issue_at": at(5)}):
            d = derive(facts(state="closed", closed_first_at=at(5), linked=[dict(merged, **bad)]))
            self.assertEqual((d["state"], d["reason"]), (None, "linked_unreadable"), bad)
        gone = dict(merged)
        del gone["closed_issue_at"]
        self.assertEqual(derive(facts(linked=[gone]))["reason"], "linked_unreadable")
        open_one = dict(pr(), closed_issue_at=at(5))
        self.assertEqual(derive(facts(linked=[open_one]))["reason"], "linked_unreadable")
        # A close in an earlier life, before a writer's reopening began this one, is no merge of this life.
        earlier = facts(life_started_at=at(7), reopened_last_by="writer", reopened_last_at=at(7), linked=[merged])
        self.assertEqual(derive(earlier)["reason"], derive(dict(earlier, linked=[]))["reason"])

    def test_a_merge_read_while_a_person_closed_or_held_the_issue_is_never_done(self):  # issue 227, the ruling
        # The Controller dequeues the Factory's pull request on a person's close or hold, so a merge that landed after
        # a person closed the issue, after an outsider reopened it, or while a Hold stood, is the platform doing what
        # the Controller should have prevented: the State the person put the issue in stays, and the reason names the
        # contradiction, so that a person sees it. Each is read by time against the first merge in the life.
        merged = [pr(is_open=False, merged=5)]
        declined = [
            # A person's close before the merge (seed 22 of the issue world); the merge's own close comes no earlier
            # than the merge, so a close in the merge's second or after it is the merge's.
            facts(state="closed", closed_first_at=at(4), linked=merged),
            # A reopening by someone without write access, which begins no life (I-41), before or in the second of
            # the merge (seed 99): the issue stays open where the merge closed nothing, or closed where it did.
            facts(reopened_last_by="other", reopened_last_at=at(3), linked=merged),
            facts(reopened_last_by="other", reopened_last_at=at(5), linked=merged),
            facts(state="closed", closed_first_at=at(2), reopened_last_by="other", reopened_last_at=at(3), linked=merged),
            # The person's close before the merge, which an outsider's reopening after the merge undid, and which
            # the person then closed again: the first close of the life is still read, so the contradiction does not
            # vanish at a stranger's click, nor at the person's own.
            facts(closed_first_at=at(4), reopened_last_by="other", reopened_last_at=at(7), linked=merged),
            facts(state="closed", closed_first_at=at(4), reopened_last_by="other", reopened_last_at=at(7), linked=merged),
            # A life that began and was closed by a person in one second, before the merge; and one closed in the
            # second it was opened.
            facts(state="closed", closed_first_at=at(3), life_started_at=at(3), reopened_last_by="writer",
                  reopened_last_at=at(3), linked=merged),
            facts(state="closed", closed_first_at=at(0), linked=merged),
        ]
        for f in declined:
            d = derive(f)
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("declined", "merged_while_declined", ["11"]), f)
            d = decide(f)
            self.assertEqual((d["state"], what(d), d["attention"]), ("declined", ("nothing", "merged_while_declined", None),
                                                                     "needs_you"))
        # A Hold, whoever placed it, and hands-off anyone but a person placed, on the issue or on its linked draft,
        # placed before the merge or in its second (seed 20); a person's close read first, where both stand.
        held = [[labelled(HOLD, minute=4)], [labelled(HOLD, OTHER_APP, 5)], [labelled(HANDS_OFF, OTHER_APP, 4)]]
        for f in [facts(label_events=events, linked=merged) for events in held] + [
                facts(linked=merged + [agents(number=12, draft=True, events=[labelled(HOLD, OTHER_APP, 4)])])]:
            d = derive(f)
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("held", "merged_while_held", ["11"]), f)
            d = decide(f)
            self.assertEqual((what(d), d["attention"]), (("hold", "merged_while_held", None), "needs_you"))
        d = derive(facts(state="closed", closed_first_at=at(4), label_events=[labelled(HOLD, minute=4)], linked=merged))
        self.assertEqual((d["state"], d["reason"]), ("declined", "merged_while_declined"))
        # A person's hands-off placed after the merge excuses nothing: the Hold stood when the merge landed; nor does
        # one a person had lifted before it.
        for events in ([labelled(HOLD, minute=4), labelled(HANDS_OFF, minute=6)],
                       [labelled(HOLD, minute=3), labelled(HANDS_OFF, minute=2), unlabelled(HANDS_OFF, minute=4)]):
            d = derive(facts(label_events=events, linked=merged))
            self.assertEqual((d["state"], d["reason"]), ("held", "merged_while_held"), events)
        d = derive(facts(label_events=[labelled(HOLD, minute=4)],
                         linked=merged + [agents(number=12, draft=True, events=[labelled(HANDS_OFF, minute=6)])]))
        self.assertEqual((d["state"], d["reason"]), ("held", "merged_while_held"))
        # A Hold on a linked draft that stood at the merge and closed since; a Hold an App placed before the merge,
        # took off after it and a person put back, which an App's removal never ended.
        for closed in (6, 5):
            d = derive(facts(linked=merged + [agents(number=12, draft=True, is_open=False, closed=closed,
                                                     events=[labelled(HOLD, OTHER_APP, 4)])]))
            self.assertEqual((d["state"], d["reason"]), ("held", "merged_while_held"), closed)
        d = derive(facts(linked=merged + [agents(number=12, draft=True, is_open=False, closed=4,
                                                 events=[labelled(HOLD, OTHER_APP, 3)])]))
        self.assertEqual((d["state"], d["reason"]), ("done", "merged"))
        d = derive(facts(label_events=[labelled(HOLD, OTHER_APP, 4), unlabelled(HOLD, OTHER_APP, 6), labelled(HOLD, minute=6)],
                         linked=merged))
        self.assertEqual((d["state"], d["reason"]), ("held", "merged_while_held"))
        # A Hold a person released after the merge and placed again later is a Hold of its own: the merge stays done.
        self.assertEqual(derive(facts(label_events=[labelled(HOLD, minute=4), unlabelled(HOLD, minute=6),
                                                    labelled(HOLD, minute=7)], linked=merged))["reason"], "merged")
        self.assertEqual(derive(facts(label_events=[labelled(HOLD, minute=4), unlabelled(HOLD, minute=6),
                                                    labelled(HOLD, OTHER_APP, 7)], linked=merged))["reason"], "merged")
        # A Hold a person placed and removed in the merge's own second stood at it: the reading that stops work wins;
        # so did a draft opened in that second with its Hold.
        self.assertEqual(derive(facts(label_events=[labelled(HOLD, minute=5), unlabelled(HOLD, minute=5)],
                                      linked=merged))["reason"], "merged_while_held")
        self.assertEqual(derive(facts(linked=merged + [agents(number=12, draft=True, opened=5,
                                                              events=[labelled(HOLD, OTHER_APP, 5)])]))["reason"],
                         "merged_while_held")
        # A label the Kernel does not read carries no time, and an event of it beside a Hold raises nothing.
        d = derive(facts(label_events=[{"label": "bug"}, labelled(HOLD, minute=4)], linked=merged))
        self.assertEqual((d["state"], d["reason"]), ("held", "merged_while_held"))
        # A person's hands-off placed in the merge's own second stood at the merge: the merge is done.
        self.assertEqual(derive(facts(label_events=[labelled(HOLD, minute=3), labelled(HANDS_OFF, minute=5)],
                                      linked=merged))["reason"], "merged")
        # The first merge in the life is the one each stop is read against: a Hold between two merges touches neither.
        two = [pr(is_open=False, merged=5), pr(number=12, is_open=False, merged=9)]
        self.assertEqual(derive(facts(label_events=[labelled(HOLD, minute=7)], linked=two))["reason"], "merged")
        self.assertEqual(derive(facts(label_events=[labelled(HOLD, minute=4)], linked=two))["reason"], "merged_while_held")
        # The other side. The merge's own close, in its second or after it; a Hold placed after the merge, which does
        # not touch what the merge did; a Hold a person released; an outsider's reopening of a done issue, after the
        # merge; a writer's reopening, which begins a life; a person's hands-off, under which the Factory leaves a
        # queued item to merge, with a Hold beside it or not, on the issue or on its linked draft; an issue the
        # Consumer entry leaves out; and the ordinary course.
        for f, cfg in ((facts(state="closed", closed_first_at=at(5), linked=merged), None),
                       (facts(state="closed", closed_first_at=at(6), linked=merged), None),
                       (facts(label_events=[labelled(HOLD, minute=6)], linked=merged), None),
                       (facts(label_events=[labelled(HOLD, minute=4), unlabelled(HOLD, minute=7)], linked=merged), None),
                       (facts(reopened_last_by="other", reopened_last_at=at(6), linked=merged), None),
                       (facts(reopened_last_by="writer", linked=merged), None),
                       # A close in an earlier life, which a writer's reopening ended: no close in this one.
                       (facts(life_started_at=at(3), reopened_last_by="writer", reopened_last_at=at(3), linked=merged),
                        None),
                       # A person's hands-off that stood at the merge and was lifted by that person since.
                       (facts(label_events=[labelled(HOLD, OTHER_APP, 3), labelled(HANDS_OFF, minute=4),
                                            unlabelled(HANDS_OFF, minute=6)], linked=merged), None),
                       # The merge's own close, which an outsider's later reopening undid, closed again since or not.
                       (facts(closed_first_at=at(5), reopened_last_by="other", reopened_last_at=at(7), linked=merged), None),
                       (facts(state="closed", closed_first_at=at(5), reopened_last_by="other", reopened_last_at=at(7),
                              linked=merged), None),
                       (facts(label_events=[labelled(HANDS_OFF, minute=4)], linked=merged), None),
                       (facts(label_events=[labelled(HOLD, minute=3), labelled(HANDS_OFF, minute=4)], linked=merged), None),
                       (facts(linked=merged + [agents(number=12, draft=True, events=[labelled(HANDS_OFF, minute=4)])]), None),
                       (facts(linked=merged), config(served_from=None)), (facts(linked=merged), None)):
            d = derive(f, cfg=cfg)
            self.assertEqual((d["state"], d["reason"]), ("done", "merged"), f)
        # With no merge, a close, a reopening and a Hold read as they did.
        self.assertEqual(derive(facts(state="closed"))["reason"], "closed")
        self.assertEqual(derive(facts(reopened_last_by="other"))["reason"], "reopened_by_other")
        self.assertEqual(derive(facts(label_events=[labelled(HOLD)]))["reason"], "human_hold")

    def test_a_close_or_a_reopening_without_its_time_cannot_be_read(self):  # issue 227
        # A closed issue says when, an open one says null; a reopening says when, a writer's at the start of the life it
        # began, anyone else's no earlier than that start; never reopened, null. Anything else defers.
        for over in ({"state": "closed", "closed_first_at": None}, {"state": "closed", "closed_first_at": "yesterday"},
                     {"state": "closed", "closed_first_at": 5},
                     {"state": "closed", "closed_first_at": at(2), "life_started_at": at(3), "reopened_last_by": "writer",
                      "reopened_last_at": at(3)},
                     {"state": "open", "closed_first_at": at(1)},
                     {"state": "open", "closed_first_at": at(2), "reopened_last_by": "writer", "life_started_at": at(2),
                      "reopened_last_at": at(2)},
                     {"state": "open", "closed_first_at": None, "reopened_last_by": "other", "reopened_last_at": at(2)},
                     {"state": "closed", "closed_first_at": at(1), "life_started_at": at(2), "reopened_last_by": "writer",
                      "reopened_last_at": at(2)},
                     {"state": "open", "closed_first_at": at(1), "reopened_last_by": "other", "life_started_at": at(2),
                      "reopened_last_at": at(3)},
                     {"state": "open", "closed_first_at": "yesterday", "reopened_last_by": "other", "reopened_last_at": at(2)}):
            f = facts(**over)
            d = decide(f)
            self.assertEqual((d["state"], what(d)), (None, ("defer", "state_unreadable", None)), over)
        for over in ({"reopened_last_by": "never", "reopened_last_at": at(1)},
                     {"reopened_last_by": "writer", "reopened_last_at": None},
                     {"reopened_last_by": "writer", "life_started_at": at(3), "reopened_last_at": at(2)},
                     {"reopened_last_by": "writer", "life_started_at": at(3), "reopened_last_at": at(4)},
                     {"reopened_last_by": "other", "reopened_last_at": None, "closed_first_at": at(1)},
                     {"reopened_last_by": "other", "life_started_at": at(3), "reopened_last_at": at(2), "closed_first_at": at(3)},
                     {"reopened_last_by": "other", "reopened_last_at": at(2), "closed_first_at": at(3)},
                     {"reopened_last_by": "other", "reopened_last_at": "soon", "closed_first_at": at(1)}):
            f = facts(**over)
            d = decide(f)
            self.assertEqual((d["state"], what(d)), (None, ("defer", "life_unreadable", None)), over)
        # Each missing: the same. The other side: each as GitHub gives it reads.
        for key in ("closed_first_at", "reopened_last_at"):
            f = facts()
            del f[key]
            self.assertEqual(decide(f)["outcome"], "defer", key)
        self.assertEqual(state(facts(state="closed", closed_first_at=at(1))), "declined")
        self.assertEqual(state(facts(state="closed", closed_first_at=at(3), life_started_at=at(3), reopened_last_by="writer",
                                     reopened_last_at=at(3))), "declined")
        self.assertEqual(state(facts(reopened_last_by="writer", life_started_at=at(3), reopened_last_at=at(3))), "new")
        self.assertEqual(state(facts(closed_first_at=at(3), reopened_last_by="other", life_started_at=at(3),
                                     reopened_last_at=at(4))), "declined")

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
                          "label_apps": {"factory:triage": None, "factory:ready": None},
                          "intents": {INVESTIGATE: None, JUDGE: None, OPEN: None}})
        d = derive(facts(label_events=[labelled(READY)]), cfg=copy.deepcopy(CONFIG))
        self.assertEqual((d["state"], d["reason"]), ("not_served", "left_out"))
        self.assertEqual(state(facts(), cfg=config(served_from=None)), "not_served")

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

    def test_only_a_persons_removal_of_hands_off_in_that_second_is_a_tie(self):
        # A removal of an earlier placement, at another second, ties with nothing.
        events = [labelled(HANDS_OFF, minute=0), unlabelled(HANDS_OFF, minute=1), labelled(HANDS_OFF, minute=3)]
        self.assertEqual(state(facts(label_events=events)), "not_served")
        # Nor does a person's removal of another label in that second.
        events = [labelled(HOLD, minute=1), unlabelled(HOLD, minute=3), labelled(HANDS_OFF, minute=3)]
        self.assertEqual(state(facts(label_events=events)), "not_served")

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
        # Only a person who opened it accepts it by authorship: an App or the machine user, with write access, does not.
        for by in (CONTROLLER, AUTHOR_APP, OTHER_APP, MACHINE, dict(OUTSIDER, can_write=True)):
            accepted = by["kind"] == "human"
            self.assertEqual(state(facts(author=dict(by), label_events=[labelled(READY)])),
                             "ready" if accepted else "new", by)
            admitted = [labelled(ADMIT), labelled(READY, minute=2)]
            self.assertEqual(state(facts(author=dict(by), label_events=admitted)), "ready", by)

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

    def test_acceptance_lapses_only_once_it_held_and_work_began_in_this_life(self):
        # Never admitted by a person: a label, anyone's, or a linked pull request only waits.
        for f in (outsiders(label_events=[labelled(READY, OTHER_APP, 3)]), outsiders(label_events=[labelled(READY)]),
                  outsiders(label_events=[labelled(TRIAGE, CONTROLLER, 2)]), outsiders(linked=[agents(draft=True)]),
                  outsiders(label_events=[labelled(ADMIT, OTHER_APP, 1), labelled(TRIAGE, CONTROLLER, 2)])):
            self.assertEqual(derive(f)["reason"], "not_accepted", f["label_events"])
        admit = [labelled(ADMIT)]
        for label, by, want in ((READY, WRITER, "acceptance_lapsed"), (READY, READINESS, "acceptance_lapsed"),
                                (TRIAGE, CONTROLLER, "acceptance_lapsed"), (TRIAGE, COLLEAGUE, "acceptance_lapsed"),
                                (READY, OTHER_APP, "not_accepted"), (TRIAGE, READINESS, "not_accepted"),
                                (TRIAGE, OUTSIDER, "not_accepted")):
            f = outsiders(content_changed_at=at(9), label_events=admit + [labelled(label, by, 2)])
            self.assertEqual(derive(f)["reason"], want, (label, by))
        # A label from an earlier life, at the reopening, or since removed, is no work begun in this one.
        for added in (2, 5):
            f = outsiders(life_started_at=at(5), reopened_last_by="writer", content_changed_at=at(9),
                          label_events=admit + [labelled(READY, minute=added)])
            self.assertEqual(derive(f)["reason"], "not_accepted", added)
        f = outsiders(content_changed_at=at(9), label_events=admit + [labelled(READY, minute=2), unlabelled(READY, minute=3)])
        self.assertEqual(derive(f)["reason"], "not_accepted")
        # Adds in one second, a person's and another App's, are read the way that stops: no work begun.
        f = outsiders(content_changed_at=at(9), label_events=admit + [labelled(READY, minute=2), labelled(READY, OTHER_APP, 2)])
        self.assertEqual(derive(f)["reason"], "not_accepted")

    def test_a_closed_link_is_work_begun_only_in_the_life_it_closed_in(self):
        admit = [labelled(ADMIT)]
        for closed_at, want in ((4, "not_accepted"), (5, "acceptance_lapsed"), (6, "acceptance_lapsed")):
            for entry in (agents(is_open=False, closed=closed_at), agents(is_open=False, merged=closed_at, empty=True)):
                f = outsiders(life_started_at=at(5), reopened_last_by="writer", content_changed_at=at(9),
                              label_events=admit, linked=[entry])
                self.assertEqual(derive(f)["reason"], want, (closed_at, entry["merged_at"]))
        f = outsiders(life_started_at=at(5), reopened_last_by="writer", content_changed_at=at(9), label_events=admit,
                      linked=[agents(draft=True)])
        self.assertEqual(derive(f)["reason"], "acceptance_lapsed")

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
        self.assertEqual(state(facts(label_events=[labelled(READY, lens, 5)]), JUDGED), "ready")

    def test_only_an_app_is_read_as_the_declared_app(self):
        cfg = config(label_apps={"factory:triage": None, "factory:ready": "readiness"})
        # The queue App is an App too, typed by its account (issue 389).
        for kind, want in (("app", "ready"), ("lens", "ready"), ("queue", "ready"), ("human", "new")):
            by = {"kind": kind, "name": "readiness", "can_write": False}
            self.assertEqual(state(facts(label_events=[labelled(READY, by)]), [run(minute=0)], cfg), want, kind)

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

    def test_a_factory_ready_counts_only_for_the_content_its_readiness_run_judged(self):
        self.assertEqual(state(facts(label_events=READIED), JUDGED), "ready")
        self.assertEqual(state(facts(label_events=READIED), [run(content=OTHER)]), "triage")
        self.assertEqual(state(facts(label_events=READIED), [run(content=OTHER, minute=2), run(minute=4, name="r2")]),
                         "ready")
        self.assertEqual(state(facts(label_events=READIED), [run(minute=2), run(content=OTHER, minute=4, name="r2")]),
                         "triage")
        # The latest readiness Run that started no later than the label: one started after it is not it.
        self.assertEqual(state(facts(label_events=READIED), [run(), run(content=OTHER, minute=6, name="r2")]), "ready")
        self.assertEqual(state(facts(label_events=READIED), [run(), run(content=OTHER, minute=5, name="r2")]), "triage")
        # Two that started in the same second must both have judged this content.
        self.assertEqual(state(facts(label_events=READIED), [run(), run(content=OTHER, name="r2")]), "triage")
        self.assertEqual(state(facts(label_events=READIED), [run(), run(name="r2")]), "ready")
        # Another issue's Run is not this one's.
        elsewhere = dict(run(minute=4, name="r2"), item=dict(ITEM, number=8))
        self.assertEqual(state(facts(label_events=READIED), [run(content=OTHER, minute=3), elsewhere]), "triage")
        # A person's ready is a person's verdict, whatever a Run judged.
        self.assertEqual(state(facts(label_events=[labelled(READY, minute=5)]), [run(content=OTHER)]), "ready")

    def test_only_a_readiness_run_judges_and_only_once_it_has_completed(self):
        # The readiness Run judged other content; a later Run of another Intent judged this one: not judged here.
        other_intent = run(intent="investigate-issue", minute=4, name="r2", role="business-analyst")
        self.assertEqual(state(facts(label_events=READIED), [run(content=OTHER, minute=2), other_intent]), "triage")
        self.assertEqual(state(facts(label_events=READIED), [other_intent]), "triage")
        # A readiness Run still running has judged nothing, nor has one queued, whatever an earlier one judged.
        for status in ("in_progress", "queued"):
            self.assertEqual(state(facts(label_events=READIED), [run(status=status)]), "triage", status)
            self.assertEqual(state(facts(label_events=READIED), [run(minute=2), run(status=status, name="r2")]),
                             "triage", status)

    def test_a_factory_ready_whose_run_record_has_expired_does_not_count(self):
        self.assertEqual(state(facts(label_events=READIED)), "triage")
        self.assertEqual(state(facts(label_events=READIED), JUDGED), "ready")

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

    def test_adds_in_one_second_are_read_the_way_that_stops_work_whatever_their_order(self):
        person, app = labelled(READY, minute=5), labelled(READY, OTHER_APP, 5)
        for events in ([person, app], [app, person]):
            self.assertEqual(state(facts(label_events=events)), "new", events)
        # Beside the declared App's, a person's add does not excuse the App's from its readiness Run.
        declared_app = labelled(READY, READINESS, 5)
        for events in ([person, declared_app], [declared_app, person]):
            self.assertEqual(state(facts(label_events=events)), "new", events)
            self.assertEqual(state(facts(label_events=events), JUDGED), "ready", events)
        both = [person, labelled(READY, COLLEAGUE, 5)]
        self.assertEqual(state(facts(label_events=both)), "ready")
        triage = [labelled(TRIAGE, CONTROLLER, 2), labelled(TRIAGE, OUTSIDER, 2)]
        for events in (triage, triage[::-1]):
            self.assertEqual(state(facts(label_events=events)), "new", events)


# What is admitted on an issue, and when `apply` refuses (design §4.1; decision 0031). Each boundary from both sides.
LIMITS = CONFIG["limits"]
TRIAGED = facts(label_events=ACCEPTED)
READIED_BY_A_PERSON = [labelled(READY)]


def decide(f, runs=(), ctx=None, cfg=None, now=NOW) -> dict:
    """The Kernel's Decision on an issue, held to its schema; no argument is changed."""
    given = copy.deepcopy((f, list(runs), context() if ctx is None else ctx, cfg or config()))
    d = issue.decide(*copy.deepcopy(given), now)
    again = issue.decide(*copy.deepcopy(given), now)
    assert d == again, "the same inputs gave another Decision"
    args = copy.deepcopy(given)
    issue.decide(*args, now)
    assert args == given, "the Kernel changed an argument"
    errors = validate(d, DECISION)
    assert not errors, (errors, d)
    return d


def what(d) -> tuple:
    """(outcome, reason, and the act or the Intent admitted, if any)."""
    return d["outcome"], d["reason"], d.get("action") or d.get("admit", {}).get("intent")


def investigated(status="completed", content=THIS, minute=3, name="i1", role="business-analyst") -> dict:
    """The investigating Run on the issue. By default it completed, for this content, at minute 3."""
    return run(intent=INVESTIGATE, content=content, status=status, minute=minute, name=name, role=role)


def failed(intent, minute, name, outcome="item", role="business-analyst") -> dict:
    """A Run that completed and failed. By a fault of the item it is an attempt; by any other, it only spends."""
    return dict(run(intent=intent, minute=minute, name=name, role=role), conclusion="failure", outcome=outcome)


def comment(app: dict, minute: int) -> dict:
    """An App's latest comment on the issue."""
    return {"by": app["name"], "at": at(minute)}


def intents(**over) -> dict:
    """The Intents as INTENTS gives them, but for what differs. Python names stand for the Intents' codes."""
    names = {"investigate": INVESTIGATE, "judge": JUDGE, "opening": OPEN}
    return dict(copy.deepcopy(INTENTS), **{names[k]: v for k, v in over.items()})


def closed_links(*minutes) -> list:
    """The Factory's pull requests that closed the issue unmerged, one at each minute."""
    return [agents(number=20 + i, is_open=False, closed=m) for i, m in enumerate(minutes)]


class Outcomes(unittest.TestCase):
    def test_an_issue_that_cannot_be_read_defers_and_one_at_an_end_admits_nothing(self):
        d = decide(facts(state=None))
        self.assertEqual((d["state"], what(d), d["attention"]), (None, ("defer", "state_unreadable", None), "none"))
        d = decide(facts(), cfg=dict(config(), issues=None))
        self.assertEqual((what(d), d["attention"]), (("defer", "issues_unreadable", None), "needs_you"))
        for f, state in ((facts(linked=[pr(is_open=False, merged=5)]), "done"), (facts(state="closed"), "declined"),
                         (facts(label_events=[labelled(HANDS_OFF)]), "not_served")):
            d = decide(f)
            self.assertEqual((d["state"], d["outcome"], d["attention"]), (state, "nothing", "none"), state)
        d = decide(facts(label_events=[labelled(HOLD)]))
        self.assertEqual((d["state"], what(d), d["attention"]), ("held", ("hold", "human_hold", None), "needs_you"))

    def test_every_situation_gives_one_valid_decision(self):
        for name, f, runs, _ in CASES:
            with self.subTest(name):
                decide(f, runs, cfg=config(served_from=None) if name == UNSERVED else config())

    def test_in_review_and_with_a_linked_draft_nothing_is_admitted_whatever_the_intents(self):
        for f, reason in ((facts(linked=[pr()]), "linked_ready"), (facts(linked=[agents(draft=True)]), "linked_draft")):
            for cfg in (config(), config(intents=None)):
                self.assertEqual(what(decide(f, cfg=cfg)), ("nothing", reason, None))


class Acceptance(unittest.TestCase):
    """The Controller accepts an issue at row 10 by adding factory:triage: an act, which on_act bounds."""

    def test_the_controller_accepts_a_new_issue_at_row_10_once_its_app_is_declared(self):
        d = decide(facts())
        self.assertEqual((what(d), d["content_id"], d["attention"]), (("act", "acceptance_due", "accept"), THIS, "ready"))
        undeclared = config(label_apps={"factory:triage": None, "factory:ready": READINESS["name"]})
        self.assertEqual(what(decide(facts(), cfg=undeclared)), ("nothing", "acceptance_due", None))
        # Not row 10: an outsider's issue nobody admitted waits, and one whose acceptance lapsed calls a person.
        d = decide(outsiders())
        self.assertEqual((what(d), d["attention"]), (("nothing", "not_accepted", None), "none"))
        lapsed = outsiders(content_changed_at=at(9), label_events=[labelled(ADMIT), labelled(TRIAGE, CONTROLLER, 2)])
        d = decide(lapsed)
        self.assertEqual((what(d), d["attention"]), (("nothing", "acceptance_lapsed", None), "needs_you"))

    def test_acceptance_is_not_decided_once_triage_is_there_and_the_label_is_the_only_guard(self):
        self.assertNotEqual(decide(TRIAGED).get("action"), "accept")
        # Until an act is counted by the ruling on how acts are recorded, the label's presence is the only guard: one
        # that stands and does not count is removed first, and only then is the issue accepted again.
        at_the_reopening = facts(life_started_at=at(1), reopened_last_by="writer",
                                 label_events=[labelled(TRIAGE, CONTROLLER, 1)])
        d = decide(at_the_reopening)
        self.assertEqual((what(d), d["label"]), (("act", "label_not_counted", "remove_label"), TRIAGE))

    def test_a_person_who_removed_triage_since_the_content_changed_is_not_overruled(self):
        for by, minute, want in ((WRITER, 1, "accept"), (WRITER, 2, None), (WRITER, 3, None), (CONTROLLER, 3, "accept")):
            f = facts(content_changed_at=at(2), label_events=[labelled(TRIAGE, CONTROLLER, 1), unlabelled(TRIAGE, by, minute)])
            d = decide(f)
            self.assertEqual(d.get("action"), want, (by, minute))
            if want is None:
                self.assertEqual((what(d), d["attention"]), (("nothing", "triage_removed", None), "none"))

    def test_acceptance_is_held_to_the_act_ceiling_and_stopped_by_the_pause(self):
        top = LIMITS["max_acts_per_item"]
        self.assertEqual(decide(facts(acts_since_writer=top - 1)).get("action"), "accept")
        d = decide(facts(acts_since_writer=top))
        self.assertEqual((d["state"], what(d)), ("held", ("hold", "act_ceiling", None)))
        for value in (-1, None, "1", True):
            self.assertEqual(what(decide(facts(acts_since_writer=value))), ("defer", "acts_unreadable", None), value)
        f = facts()
        del f["acts_since_writer"]
        self.assertEqual(what(decide(f)), ("defer", "acts_unreadable", None))
        self.assertEqual(what(decide(facts(), ctx=context(paused=True))), ("defer", "paused", None))
        self.assertEqual(what(decide(facts(), ctx=context(paused=None))), ("defer", "pause_unreadable", None))

    def test_acceptance_waits_for_a_run_in_flight(self):
        d = decide(facts(), [run(status="in_progress")])
        self.assertEqual((what(d), d["attention"]), (("nothing", "acceptance_due", None), "working"))


class RemoveLabel(unittest.TestCase):
    """The Controller removes a factory:triage or factory:ready that stands and no longer counts (I-17)."""

    def test_a_label_that_stands_and_no_longer_counts_is_removed(self):
        cases = [(facts(label_events=[labelled(TRIAGE, OTHER_APP, 1)]), TRIAGE),
                 (facts(label_events=[labelled(READY, OTHER_APP, 1)]), READY),
                 (facts(label_events=[labelled(READY, MACHINE, 1)]), READY),
                 (facts(label_events=READIED), READY),
                 (facts(life_started_at=at(5), reopened_last_by="writer",
                        label_events=[labelled(TRIAGE, CONTROLLER, 1), labelled(READY, minute=6)]), TRIAGE)]
        for f, label in cases:
            d = decide(f)
            self.assertEqual((what(d), d["label"], d["evidence"], d["content_id"]),
                             (("act", "label_not_counted", "remove_label"), label, [label], THIS), label)
        # The other side: a person's label, alone or tied in its second with another's, is never removed; not
        # counting it is enough. A label that counts stays, and one already gone is not removed again.
        for f in (facts(content_changed_at=at(4), label_events=ACCEPTED + [labelled(READY, minute=3)]),
                  facts(label_events=ACCEPTED + [labelled(READY, minute=3), labelled(READY, OTHER_APP, 3)])):
            self.assertEqual(what(decide(f)), ("admit", "triage", INVESTIGATE), f["label_events"])
        self.assertEqual(what(decide(facts(label_events=READIED), JUDGED)), ("admit", "ready", OPEN))
        self.assertEqual(what(decide(TRIAGED)), ("admit", "triage", INVESTIGATE))
        gone = facts(label_events=[labelled(TRIAGE, OTHER_APP, 1), unlabelled(TRIAGE, OTHER_APP, 2)])
        self.assertEqual(decide(gone).get("action"), "accept")

    def test_the_hold_an_admission_and_hands_off_are_never_removed_nor_a_label_once_work_is_linked(self):
        self.assertEqual(what(decide(outsiders(label_events=[labelled(ADMIT, OTHER_APP)]))),
                         ("nothing", "not_accepted", None))
        self.assertEqual(decide(facts(label_events=[labelled(HOLD, OTHER_APP)]))["outcome"], "hold")
        self.assertEqual(decide(facts(label_events=[labelled(HANDS_OFF, OTHER_APP)]))["outcome"], "hold")
        linked = facts(label_events=[labelled(TRIAGE, OTHER_APP, 1)], linked=[agents(draft=True)])
        self.assertEqual(what(decide(linked)), ("nothing", "linked_draft", None))

    def test_removing_a_label_is_stopped_by_the_pause_and_waits_for_a_run_in_flight(self):
        stale = facts(label_events=[labelled(READY, OTHER_APP, 1)], acts_since_writer=LIMITS["max_acts_per_item"])
        self.assertEqual(decide(stale).get("action"), "remove_label")
        self.assertEqual(what(decide(stale, ctx=context(paused=True))), ("defer", "paused", None))
        # A readiness Run that adds factory:ready completes after its apply: until then its label does not count.
        d = decide(facts(label_events=READIED), [run(status="in_progress")])
        self.assertEqual((what(d), d["attention"]), (("nothing", "triage", None), "working"))


class UnmergedCloses(unittest.TestCase):
    """The Controller places factory:hold when unmerged closes pass max_unmerged_closes (I-43)."""

    def test_unmerged_closes_past_the_bound_place_a_hold(self):
        top = LIMITS["max_unmerged_closes"]
        within = facts(label_events=READIED_BY_A_PERSON, linked=closed_links(*range(2, 2 + top)))
        self.assertEqual(what(decide(within)), ("admit", "ready", OPEN))
        past = facts(label_events=READIED_BY_A_PERSON, linked=closed_links(*range(2, 3 + top)))
        d = decide(past)
        self.assertEqual((d["state"], what(d), d["attention"], d["content_id"]),
                         ("ready", ("act", "unmerged_closes", "place_hold"), "needs_you", THIS))
        self.assertEqual(d["evidence"], [str(20 + i) for i in range(top + 1)])
        # Only a linked pull request counts: a stranger's that nobody admitted closes nothing here.
        strangers_too = facts(label_events=READIED_BY_A_PERSON,
                              linked=closed_links(*range(2, 2 + top)) + [strangers(number=30, is_open=False, closed=9)])
        self.assertEqual(what(decide(strangers_too)), ("admit", "ready", OPEN))

    def test_a_merge_that_closed_nothing_counts_as_a_close_without_done(self):  # issue 267
        # Read past the lag, a merge that closed nothing is no merge of the issue, and a close of a linked pull request
        # all the same: it counts toward the bound, so a Factory merge GitHub never closes the issue for opens at most
        # max_unmerged_closes more before a person is asked, and so does a reference an edit added after a merge.
        top = LIMITS["max_unmerged_closes"]
        never = [agents(number=20 + i, is_open=False, merged=2 + i, closed_issue=None) for i in range(top + 1)]
        within = facts(label_events=READIED_BY_A_PERSON, linked=never[:top])
        self.assertEqual(what(decide(within)), ("admit", "ready", OPEN))
        d = decide(facts(label_events=READIED_BY_A_PERSON, linked=never))
        self.assertEqual((what(d), d["attention"]), (("act", "unmerged_closes", "place_hold"), "needs_you"))

    def test_closes_are_counted_in_this_life_since_a_person_released_the_hold(self):
        self.assertEqual(LIMITS["max_unmerged_closes"], 1)
        for start, hold in ((5, True), (6, False)):
            f = facts(life_started_at=at(start), reopened_last_by="writer", linked=closed_links(5, 6))
            self.assertEqual(decide(f).get("action") == "place_hold", hold, start)
        placed = labelled(HOLD, CONTROLLER, 4)
        for minute, hold in ((5, True), (6, True), (7, False)):
            f = facts(label_events=READIED_BY_A_PERSON + [placed, unlabelled(HOLD, minute=minute)],
                      linked=closed_links(6, 7))
            self.assertEqual(decide(f).get("action") == "place_hold", hold, minute)
        # Only a person's removal resets the count: anyone else's ends no Hold, and so releases none.
        released = [labelled(HOLD, minute=4), unlabelled(HOLD, minute=5), unlabelled(HOLD, OTHER_APP, 7)]
        f = facts(label_events=READIED_BY_A_PERSON + released, linked=closed_links(6, 7))
        self.assertEqual(decide(f).get("action"), "place_hold")

    def test_placing_a_hold_is_stopped_only_by_the_pause_and_not_once_the_hold_is_there(self):
        past = facts(label_events=READIED_BY_A_PERSON, linked=closed_links(2, 3),
                     acts_since_writer=LIMITS["max_acts_per_item"])
        self.assertEqual(decide(past).get("action"), "place_hold")
        self.assertEqual(decide(past, [opening(status="queued")]).get("action"), "place_hold")
        d = decide(past, ctx=context(paused=True))
        self.assertEqual((what(d), d["attention"]), (("defer", "paused", None), "needs_you"))
        held = facts(label_events=READIED_BY_A_PERSON + [labelled(HOLD, CONTROLLER, 4)], linked=closed_links(2, 3))
        self.assertEqual(what(decide(held)), ("hold", "human_hold", None))


class Investigation(unittest.TestCase):
    """In triage one Run at a time: an investigation unless it is current, then a verdict unless one stands."""

    def test_in_triage_an_investigating_run_is_admitted_first(self):
        d = decide(TRIAGED)
        self.assertEqual((what(d), d["admit"]), (("admit", "triage", INVESTIGATE),
                                                 {"role": "business-analyst", "intent": INVESTIGATE, "content_id": THIS}))
        self.assertEqual(d["attention"], "ready")

    def test_the_investigation_is_current_once_its_role_completed_a_run_for_this_content_since_a_writer_acted(self):
        d = decide(TRIAGED, [investigated()])
        self.assertEqual((what(d), d["admit"]), (("admit", "triage", JUDGE),
                                                 {"role": "readiness", "intent": JUDGE, "content_id": THIS}))
        for runs in ([dict(investigated(), conclusion="failure", outcome="item")], [investigated(content=OTHER)],
                     [investigated(role="readiness")], [investigated(minute=0)],
                     [dict(investigated(), intent=JUDGE)]):
            self.assertEqual(what(decide(TRIAGED, runs)), ("admit", "triage", INVESTIGATE), runs)
        for mark, want in ((2, JUDGE), (3, INVESTIGATE), (4, INVESTIGATE)):
            f = facts(label_events=ACCEPTED, last_writer_action_at=at(mark))
            self.assertEqual(what(decide(f, [investigated()]))[2], want, mark)
        self.assertEqual(what(decide(facts(label_events=ACCEPTED, last_writer_action_at=None), [investigated()]))[2],
                         JUDGE)

    def test_once_the_record_has_expired_the_investigating_apps_comment_stands_in(self):
        self.assertEqual(what(decide(facts(label_events=ACCEPTED, role_comments=[comment(ANALYST, 5)])))[2], JUDGE)
        for over in ({"content_changed_at": at(5)}, {"last_writer_action_at": at(5)},
                     {"role_comments": [comment(OTHER_APP, 6)]}):
            f = facts(**dict({"label_events": ACCEPTED, "role_comments": [comment(ANALYST, 5)]}, **over))
            self.assertEqual(what(decide(f))[2], INVESTIGATE, over)

    def test_a_verdict_is_given_once_for_each_content_and_investigation(self):
        d = decide(TRIAGED, [investigated(), run()])
        self.assertEqual((what(d), d["attention"]), (("nothing", "judged", None), "needs_you"))
        self.assertEqual(what(decide(TRIAGED, [investigated(), run(minute=3, name="r1")])), ("nothing", "judged", None))
        for verdict in (dict(run(), conclusion="failure", outcome="item"), run(content=OTHER), run(minute=2),
                        run(role="business-analyst"), run(intent=OPEN)):
            self.assertEqual(what(decide(TRIAGED, [investigated(), verdict])), ("admit", "triage", JUDGE), verdict)
        # The investigation is read from when it was first shown: a later investigation does not move it.
        self.assertEqual(what(decide(TRIAGED, [investigated(), investigated(minute=5, name="i2"), run()])),
                         ("nothing", "judged", None))

    def test_once_its_record_has_expired_the_readiness_apps_label_or_comment_stands_in(self):
        for added, by, want in ((5, READINESS, "judged"), (3, READINESS, "judged"), (2, READINESS, "triage"),
                                (5, OTHER_APP, "triage")):
            f = facts(label_events=ACCEPTED + [labelled(READY, by, added), unlabelled(READY, CONTROLLER, added + 1)])
            self.assertEqual(decide(f, [investigated()])["reason"], want, (added, by))
        for minute, want in ((5, "judged"), (2, "triage")):
            f = facts(label_events=ACCEPTED, role_comments=[comment(READINESS, minute)])
            self.assertEqual(decide(f, [investigated()])["reason"], want, minute)
        self.assertEqual(decide(facts(label_events=ACCEPTED, role_comments=[comment(OTHER_APP, 5)]),
                                [investigated()])["reason"], "triage")
        # Only the App's add is its label: its removal is no verdict, nor is a person's add under the App's name.
        f = facts(label_events=ACCEPTED + [labelled(READY, READINESS, 2), unlabelled(READY, READINESS, 5)])
        self.assertEqual(decide(f, [investigated()])["reason"], "triage")
        cfg = config(intents=intents(judge={"role": "readiness", "app": "readiness"}))
        person = {"kind": "human", "name": "readiness", "can_write": True}
        f = facts(label_events=ACCEPTED + [labelled(READY, person, 5), unlabelled(READY, CONTROLLER, 6)])
        self.assertEqual(decide(f, [investigated()], cfg=cfg)["reason"], "triage")

    def test_a_person_who_removed_ready_since_the_content_changed_overrules_readiness(self):
        removed = ACCEPTED + [labelled(READY, minute=4), unlabelled(READY, minute=5)]
        d = decide(facts(label_events=removed), [investigated()])
        self.assertEqual((what(d), d["attention"]), (("nothing", "ready_removed", None), "needs_you"))
        before = facts(content_changed_at=at(5), label_events=ACCEPTED + [labelled(READY, minute=2),
                                                                          unlabelled(READY, minute=4)])
        self.assertEqual(what(decide(before, [investigated(minute=6)]))[2], JUDGE)
        at_the_edit = facts(content_changed_at=at(4), label_events=ACCEPTED + [labelled(READY, minute=2),
                                                                               unlabelled(READY, minute=4)])
        self.assertEqual(decide(at_the_edit, [investigated(minute=6)])["reason"], "ready_removed")
        by_the_controller = ACCEPTED + [labelled(READY, minute=4), unlabelled(READY, CONTROLLER, 5)]
        self.assertEqual(what(decide(facts(label_events=by_the_controller), [investigated()]))[2], JUDGE)
        # The removal is the person's action, after which the investigation is no longer current: as ruled, it is
        # investigated again first, and then no verdict is admitted.
        self.assertEqual(what(decide(facts(label_events=removed, last_writer_action_at=at(5)), [investigated()]))[2],
                         INVESTIGATE)

    def test_an_intent_not_declared_admits_nothing_and_needs_a_person(self):
        for cfg, f, runs, intent in ((config(intents=intents(investigate=None)), TRIAGED, [], INVESTIGATE),
                                     (config(intents=intents(judge=None)), TRIAGED, [investigated()], JUDGE),
                                     (config(intents=intents(opening=None)), facts(label_events=READIED_BY_A_PERSON),
                                      [], OPEN)):
            d = decide(f, runs, cfg=cfg)
            self.assertEqual((what(d), d["evidence"], d["attention"]),
                             (("nothing", "intent_undeclared", None), [intent], "needs_you"), intent)
        # By default every Intent is null.
        defaults = json.loads((ROOT / "config" / "defaults.json").read_text())["issues"]["intents"]
        self.assertEqual(defaults, {INVESTIGATE: None, JUDGE: None, OPEN: None})

    def test_intents_that_cannot_be_read_or_share_a_role_defer(self):
        lacking = intents()
        del lacking[JUDGE]
        for value in (None, [], "business-analyst", lacking, intents(investigate={"role": "business-analyst"}),
                      intents(judge={"role": "", "app": READINESS["name"]}), intents(opening={"role": "dev-lead", "app": 1}),
                      intents(investigate="business-analyst")):
            d = decide(TRIAGED, cfg=config(intents=value))
            self.assertEqual((what(d), d["attention"]), (("defer", "intents_unreadable", None), "needs_you"), value)
        missing = config()
        del missing["issues"]["intents"]
        self.assertEqual(what(decide(TRIAGED, cfg=missing)), ("defer", "intents_unreadable", None))
        for name in ("judge", "opening"):
            shared = intents(**{name: {"role": "business-analyst", "app": ANALYST["name"]}})
            self.assertEqual(what(decide(TRIAGED, cfg=config(intents=shared))), ("defer", "intents_share_a_role", None))
        # An Intent that is null shares no Role; and a new issue's acceptance reads no Intent.
        self.assertEqual(what(decide(TRIAGED, cfg=config(intents=intents(judge=None, opening=None))))[2], INVESTIGATE)
        self.assertEqual(decide(facts(), cfg=config(intents=None)).get("action"), "accept")

    def test_the_brakes_bound_investigation_and_readiness(self):
        tries = LIMITS["max_attempts"]
        spent = [failed(INVESTIGATE, 1 + i, "f%d" % i) for i in range(tries)]
        self.assertEqual(what(decide(TRIAGED, spent[:-1])), ("admit", "triage", INVESTIGATE))
        d = decide(TRIAGED, spent)
        self.assertEqual((d["state"], what(d), d["attention"]), ("held", ("hold", "attempts_exhausted", None), "needs_you"))
        judging = [investigated(minute=1)] + [failed(JUDGE, 2 + i, "j%d" % i, role="readiness") for i in range(tries)]
        self.assertEqual(what(decide(TRIAGED, judging[:-1])), ("admit", "triage", JUDGE))
        self.assertEqual(what(decide(TRIAGED, judging)), ("hold", "attempts_exhausted", None))
        ceiling = LIMITS["max_runs_per_item"]
        runs = [failed(INVESTIGATE, 1 + i, "e%d" % i, outcome="environment") for i in range(ceiling)]
        self.assertEqual(what(decide(TRIAGED, runs[:-1])), ("admit", "triage", INVESTIGATE))
        self.assertEqual(what(decide(TRIAGED, runs)), ("hold", "run_ceiling", None))
        # A person's action renews every count.
        renewed = facts(label_events=ACCEPTED, last_writer_action_at=at(30))
        self.assertEqual(what(decide(renewed, runs)), ("admit", "triage", INVESTIGATE))

    def test_an_issues_run_that_ran_and_left_no_outcome_is_an_attempt(self):  # issue 286's ruling
        # An investigating Run that failed or timed out with no outcome is the item's; one cancelled with none is not.
        tries = LIMITS["max_attempts"]
        for conclusion in ("failure", "timed_out"):
            died = [dict(failed(INVESTIGATE, 1 + i, "d%d" % i, outcome=None), conclusion=conclusion) for i in range(tries)]
            self.assertEqual(what(decide(TRIAGED, died[:-1])), ("admit", "triage", INVESTIGATE), conclusion)
            self.assertEqual(what(decide(TRIAGED, died)), ("hold", "attempts_exhausted", None), conclusion)
        gone = [dict(failed(INVESTIGATE, 1 + i, "g%d" % i, outcome=None), conclusion="cancelled") for i in range(tries)]
        self.assertEqual(what(decide(TRIAGED, gone)), ("admit", "triage", INVESTIGATE))

    def test_a_run_in_flight_admits_nothing_and_the_brakes_hold_still_applies(self):
        tries = LIMITS["max_attempts"]
        queued = investigated(status="queued", minute=20, name="q1")
        spent = [failed(INVESTIGATE, 1 + i, "f%d" % i) for i in range(tries)]
        d = decide(TRIAGED, spent[:-1] + [queued])
        self.assertEqual((what(d), d["attention"]), (("nothing", "triage", None), "working"))
        self.assertEqual(what(decide(TRIAGED, spent + [queued])), ("hold", "attempts_exhausted", None))
        # The Run in flight was admitted under the ceiling: it is not counted against itself.
        ceiling = LIMITS["max_runs_per_item"]
        runs = [failed(INVESTIGATE, 1 + i, "e%d" % i, outcome="environment") for i in range(ceiling)]
        self.assertEqual(what(decide(TRIAGED, runs[:-1] + [queued])), ("nothing", "triage", None))
        self.assertEqual(what(decide(TRIAGED, runs + [queued])), ("hold", "run_ceiling", None))
        # Under a Pause, a Run in flight is still only working.
        self.assertEqual(decide(TRIAGED, [queued], ctx=context(paused=True))["attention"], "working")

    def test_under_a_pause_a_spent_count_holds_the_issue_with_a_run_in_flight_or_none(self):  # decision 0003
        # A Hold of the brakes is a reading and no act, and a Pause leaves each item where it is: under a Pause, or one
        # that cannot be read, spent attempts hold the issue as they do without one, whether or not a Run waits.
        tries = LIMITS["max_attempts"]
        queued = investigated(status="queued", minute=20, name="q1")
        spent = [failed(INVESTIGATE, 1 + i, "f%d" % i) for i in range(tries)]
        for paused, why in ((True, "paused"), (None, "pause_unreadable")):
            for flight in ([], [queued]):
                d = decide(TRIAGED, spent + flight, ctx=context(paused=paused))
                self.assertEqual((d["state"], what(d), d["attention"]),
                                 ("held", ("hold", "attempts_exhausted", None), "needs_you"), (paused, flight))
            # The other side: one attempt short, the Pause defers the investigation, and a Run in flight keeps it working.
            d = decide(TRIAGED, spent[:-1], ctx=context(paused=paused))
            self.assertEqual((d["state"], what(d)), ("triage", ("defer", why, None)), paused)
            d = decide(TRIAGED, spent[:-1] + [queued], ctx=context(paused=paused))
            self.assertEqual((d["state"], what(d), d["attention"]), ("triage", ("nothing", "triage", None), "working"))
            # The act ceiling holds a new issue's acceptance under a Pause too; one act short, the Pause defers it.
            d = decide(facts(acts_since_writer=LIMITS["max_acts_per_item"]), ctx=context(paused=paused))
            self.assertEqual((d["state"], what(d)), ("held", ("hold", "act_ceiling", None)), paused)
            d = decide(facts(acts_since_writer=LIMITS["max_acts_per_item"] - 1), ctx=context(paused=paused))
            self.assertEqual((d["state"], what(d)), ("new", ("defer", why, None)), paused)

    def test_the_pause_capacity_and_concurrency_defer_a_run(self):
        self.assertEqual(what(decide(TRIAGED, ctx=context(paused=True))), ("defer", "paused", None))
        for ctx, want in ((context(model_deferred_until="2026-10-11T13:00:01Z"), ("defer", "capacity", None)),
                          (context(model_deferred_until=NOW), ("admit", "triage", INVESTIGATE)),
                          (context(active_runs=None), ("defer", "capacity_unreadable", None)),
                          (context(active_runs=LIMITS["org_max_active_runs"]), ("defer", "concurrency", None)),
                          (context(active_runs=LIMITS["org_max_active_runs"] - 1), ("admit", "triage", INVESTIGATE))):
            self.assertEqual(what(decide(TRIAGED, ctx=ctx)), want, ctx)
        ctx = context()
        del ctx["model_deferred_until"]
        self.assertEqual(what(decide(TRIAGED, ctx=ctx)), ("defer", "capacity_unreadable", None))

    def test_an_active_runs_that_is_no_count_defers_and_raises_nothing(self):  # I-3, issue 218
        # As on a pull request: a count that is no whole number, a bool among them, or is below zero cannot be read, and
        # the Run defers; a whole number is read at the limit and below it. What is asserted first is that it returns.
        unread, limit = ("defer", "capacity_unreadable", None), LIMITS["org_max_active_runs"]
        cases = [(active, unread) for active in ("3", "", [], {}, 3.0, float("nan"), True, False, -1)]
        cases += [(limit, ("defer", "concurrency", None)), (limit - 1, ("admit", "triage", INVESTIGATE)),
                  (0, ("admit", "triage", INVESTIGATE))]
        missing = context()
        del missing["active_runs"]
        for active, want in cases + [(missing, unread)]:
            ctx = active if isinstance(active, dict) and "paused" in active else context(active_runs=active)
            try:
                d = decide(TRIAGED, ctx=ctx)
            except Exception as e:
                self.fail("an active_runs of %r raised %r" % (active, e))
            self.assertEqual((d["state"], what(d)), ("triage", want), active)

    def test_what_steers_admission_is_read_whole_or_defers(self):
        for over, reason in (({"role_comments": None}, "comments_unreadable"),
                             ({"role_comments": [{"by": "", "at": at(5)}]}, "comments_unreadable"),
                             ({"role_comments": [{"by": ANALYST["name"], "at": "today"}]}, "comments_unreadable"),
                             ({"role_comments": ["x"]}, "comments_unreadable"),
                             ({"last_writer_action_at": "today"}, "writer_unreadable"),
                             ({"last_writer_comment_at": 5}, "writer_unreadable")):
            d = decide(facts(**dict({"label_events": ACCEPTED}, **over)))
            self.assertEqual(what(d), ("defer", reason, None), over)
        for name in ("role_comments", "last_writer_action_at", "last_writer_comment_at"):
            f = facts(label_events=ACCEPTED)
            del f[name]
            self.assertEqual(decide(f)["outcome"], "defer", name)


# A run record of the Factory's own workflow, not completed, still listed under the workflow's name: GitHub's run id,
# from trials/P-17.json. Which item it is on cannot be read (decision 0036).
UNNAMED = {"run": "39086879694", "created_at": NOW, "status": "in_progress"}


class UnidentifiedRuns(unittest.TestCase):
    """A Run listed before its run-name may be the Run in flight on this issue: it defers every admission (I-46)."""

    def test_an_unidentified_run_defers_an_issues_run(self):  # I-46, I-13
        d = decide(TRIAGED, ctx=context(unidentified_runs=[UNNAMED]))
        self.assertEqual((d["state"], what(d)), ("triage", ("defer", "run_unidentified", None)))
        # Past max_unnamed_run_seconds it is no Run waiting for its name, and defers the issue's Run no more (issue 270).
        old = (datetime.datetime.strptime(NOW, "%Y-%m-%dT%H:%M:%SZ")
               - datetime.timedelta(seconds=LIMITS["max_unnamed_run_seconds"])).strftime("%Y-%m-%dT%H:%M:%SZ")
        d = decide(TRIAGED, ctx=context(unidentified_runs=[dict(UNNAMED, created_at=old, status="completed")]))
        self.assertEqual(what(d), ("admit", "triage", INVESTIGATE))
        self.assertEqual(what(decide(TRIAGED, ctx=context(unidentified_runs=[]))), ("admit", "triage", INVESTIGATE))
        # Nothing is defaulted: a list that is missing, or is not a list, defers as one with a Run would.
        missing = context()
        del missing["unidentified_runs"]
        for ctx in (missing, context(unidentified_runs=None), context(unidentified_runs=UNNAMED),
                    context(unidentified_runs={}), context(unidentified_runs=""), context(unidentified_runs=())):
            self.assertEqual(what(decide(TRIAGED, ctx=ctx)), ("defer", "run_unidentified", None),
                             ctx.get("unidentified_runs", "missing"))
        # The brakes are asked first: spent attempts hold the issue, and under a Pause the Pause defers.
        spent = [failed(INVESTIGATE, 1 + i, "f%d" % i) for i in range(LIMITS["max_attempts"])]
        d = decide(TRIAGED, spent, ctx=context(unidentified_runs=[UNNAMED]))
        self.assertEqual((d["state"], what(d)), ("held", ("hold", "attempts_exhausted", None)))
        d = decide(TRIAGED, ctx=context(paused=True, unidentified_runs=[UNNAMED]))
        self.assertEqual(what(d), ("defer", "paused", None))

    def test_an_unidentified_run_stops_no_acceptance_and_no_hold(self):  # I-46, I-43
        # Accepting admits no Run, and placing a Hold stops work: neither waits for the name.
        unnamed = context(unidentified_runs=[UNNAMED])
        d = decide(facts(), ctx=unnamed)
        self.assertEqual((d["state"], what(d)), ("new", ("act", "acceptance_due", "accept")))
        past = facts(label_events=READIED_BY_A_PERSON, linked=closed_links(2, 3))
        d = decide(past, ctx=unnamed)
        self.assertEqual((d["state"], what(d)), ("ready", ("act", "unmerged_closes", "place_hold")))


class WhatARunWrites(unittest.TestCase):
    """What a Run in flight has written is read only once it completes, and a Role's comment or label stands in for
    its Runs only once every record of them has expired."""

    def test_nothing_a_run_in_flight_wrote_is_read_until_it_completes(self):
        d = decide(facts(label_events=READIED), [investigated(), run(status="in_progress")])
        self.assertEqual((d["state"], what(d), d["attention"]), ("triage", ("nothing", "triage", None), "working"))
        tries = LIMITS["max_attempts"]
        judging = [investigated(minute=1)] + [failed(JUDGE, 2 + i, "j%d" % i, role="readiness") for i in range(tries)]
        wrote = facts(label_events=ACCEPTED + [labelled(READY, READINESS, 25), unlabelled(READY, CONTROLLER, 26)],
                      role_comments=[comment(READINESS, 25)])
        flying = run(status="in_progress", minute=20, name="q1")
        self.assertEqual(what(decide(wrote, judging + [flying])), ("hold", "attempts_exhausted", None))
        self.assertEqual(what(decide(wrote, judging[:-1] + [flying])), ("nothing", "triage", None))
        spent = [failed(INVESTIGATE, 1 + i, "f%d" % i) for i in range(tries)]
        commented = facts(label_events=ACCEPTED, role_comments=[comment(ANALYST, 25)])
        investigating = investigated(status="in_progress", minute=20, name="q1")
        self.assertEqual(what(decide(commented, spent + [investigating])), ("hold", "attempts_exhausted", None))
        # The Run in flight is read whatever the Intents say, and the brakes are asked of its own Intent.
        d = decide(commented, spent[:-1] + [investigating], cfg=config(intents=None))
        self.assertEqual((what(d), d["attention"]), (("nothing", "triage", None), "working"))

    def test_a_comment_or_label_stands_in_only_once_every_record_of_its_role_has_expired(self):
        commented = facts(label_events=ACCEPTED, role_comments=[comment(ANALYST, 5)])
        self.assertEqual(what(decide(commented))[2], JUDGE)
        a_failure = dict(investigated(minute=4), conclusion="failure", outcome="item")
        self.assertEqual(what(decide(commented, [a_failure]))[2], INVESTIGATE)
        refused = failed(JUDGE, 4, "j1", role="readiness")
        for f in (facts(label_events=ACCEPTED, role_comments=[comment(READINESS, 5)]),
                  facts(label_events=ACCEPTED + [labelled(READY, READINESS, 5), unlabelled(READY, CONTROLLER, 6)])):
            self.assertEqual(decide(f, [investigated()])["reason"], "judged")
            self.assertEqual(what(decide(f, [investigated(), refused]))[2], JUDGE)

    def test_the_readiness_apps_comment_in_the_second_of_the_investigation_stands_in(self):
        for minute, want in ((3, "judged"), (2, "triage")):
            f = facts(label_events=ACCEPTED, role_comments=[comment(READINESS, minute)])
            self.assertEqual(decide(f, [investigated()])["reason"], want, minute)

    def test_intents_that_share_an_app_defer(self):
        for name, app in (("judge", ANALYST["name"]), ("opening", ANALYST["name"]), ("opening", READINESS["name"])):
            shared = intents(**{name: {"role": "someone-else", "app": app}})
            d = decide(TRIAGED, cfg=config(intents=shared))
            self.assertEqual((what(d), d["attention"]), (("defer", "intents_share_an_app", None), "needs_you"), name)

    def test_a_label_is_not_removed_while_acceptance_has_lapsed(self):
        events = [labelled(ADMIT), labelled(READY, READINESS, 2)]
        d = decide(outsiders(content_changed_at=at(9), label_events=events))
        self.assertEqual((what(d), d["attention"]), (("nothing", "acceptance_lapsed", None), "needs_you"))
        d = decide(outsiders(label_events=events))
        self.assertEqual((what(d), d["label"]), (("act", "label_not_counted", "remove_label"), READY))


class Attention(unittest.TestCase):
    """Who each reason and State calls: a person, nobody, or the Factory's own next act."""

    def test_each_reason_and_state_calls_whom_it_should(self):
        tries, ceiling = LIMITS["max_attempts"], LIMITS["max_runs_per_item"]
        spent = [failed(INVESTIGATE, 1 + i, "f%d" % i) for i in range(tries)]
        worn = [failed(INVESTIGATE, 1 + i, "e%d" % i, outcome="environment") for i in range(ceiling)]
        stale = facts(life_started_at=at(5), reopened_last_by="writer", label_events=[labelled(TRIAGE, WRITER, 1)])
        cases = [
            ("human_hold", "needs_you", facts(label_events=[labelled(HOLD)]), [], config()),
            ("linked_twice", "needs_you", facts(linked=[pr(), agents(number=12, draft=True)]), [], config()),
            ("acceptance_lapsed", "needs_you",
             outsiders(content_changed_at=at(9), label_events=[labelled(ADMIT), labelled(TRIAGE, CONTROLLER, 2)]), [],
             config()),
            ("attempts_exhausted", "needs_you", TRIAGED, spent, config()),
            ("run_ceiling", "needs_you", TRIAGED, worn, config()),
            ("act_ceiling", "needs_you", facts(acts_since_writer=LIMITS["max_acts_per_item"]), [], config()),
            ("triage_stands", "needs_you", stale, [], config()),
            ("judged", "needs_you", TRIAGED, [investigated(), run()], config()),
            ("ready_removed", "needs_you",
             facts(label_events=ACCEPTED + [labelled(READY, minute=4), unlabelled(READY, minute=5)]), [investigated()],
             config()),
            ("no_statement", "needs_you", outsiders(label_events=[labelled(ADMIT), labelled(READY, minute=2)]), [],
             config()),
            ("intent_undeclared", "needs_you", TRIAGED, [], config(intents=intents(investigate=None))),
            ("label_unreadable", "needs_you", facts(label_names=None), [], config()),
            ("issues_unreadable", "needs_you", facts(), [], dict(config(), issues=None)),
            ("intents_unreadable", "needs_you", TRIAGED, [], config(intents=None)),
            ("intents_share_a_role", "needs_you", TRIAGED, [],
             config(intents=intents(judge={"role": "business-analyst", "app": READINESS["name"]}))),
            ("intents_share_an_app", "needs_you", TRIAGED, [],
             config(intents=intents(judge={"role": "readiness", "app": ANALYST["name"]}))),
            ("unmerged_closes", "needs_you", facts(label_events=READIED_BY_A_PERSON, linked=closed_links(2, 3)), [],
             config()),
            ("merged", "none", facts(linked=[pr(is_open=False, merged=5)]), [], config()),
            ("closed", "none", facts(state="closed"), [], config()),
            ("hands_off", "none", facts(label_events=[labelled(HANDS_OFF)]), [], config()),
            ("linked_ready", "none", facts(linked=[pr()]), [], config()),
            ("not_accepted", "none", outsiders(), [], config()),
            ("triage_removed", "none",
             facts(content_changed_at=at(2), label_events=[labelled(TRIAGE, CONTROLLER, 1), unlabelled(TRIAGE, minute=2)]),
             [], config()),
            ("acceptance_due", "ready", facts(), [], config()),
            ("linked_draft", "ready", facts(linked=[agents(draft=True)]), [], config()),
        ]
        for reason, attention, f, runs, cfg in cases:
            d = decide(f, runs, cfg=cfg)
            self.assertEqual((d["reason"], d["attention"]), (reason, attention), reason)

    def test_no_act_is_decided_whose_label_already_stands(self):
        # A person's factory:triage from an earlier life does not count, and is never removed: nothing is accepted.
        stale = facts(life_started_at=at(5), reopened_last_by="writer", label_events=[labelled(TRIAGE, WRITER, 1)])
        d = decide(stale)
        self.assertEqual((what(d), d["evidence"]), (("nothing", "triage_stands", None), [TRIAGE]))
        removed = facts(life_started_at=at(5), reopened_last_by="writer",
                        label_events=[labelled(TRIAGE, WRITER, 1), unlabelled(TRIAGE, CONTROLLER, 2)])
        self.assertEqual(decide(removed).get("action"), "accept")

    def test_a_failed_investigations_comment_is_no_statement(self):
        events = [labelled(ADMIT), labelled(READY, minute=3)]
        f = outsiders(label_events=events, role_comments=[comment(ANALYST, 2)])
        self.assertEqual(what(decide(f, [failed(INVESTIGATE, 2, "f1")])), ("nothing", "no_statement", None))
        self.assertEqual(what(decide(f, [investigated(minute=2)]))[2], OPEN)
        self.assertEqual(what(decide(f, [investigated(minute=2, content=OTHER)])), ("nothing", "no_statement", None))
        self.assertEqual(what(decide(f))[2], OPEN)


class Opening(unittest.TestCase):
    """In ready, the opening Run, for the issue's content and the branch head it will push to."""

    def test_in_ready_the_opening_run_is_admitted_for_the_content_and_the_branch_head(self):
        d = decide(facts(label_events=READIED_BY_A_PERSON))
        self.assertEqual((what(d), d["admit"]), (("admit", "ready", OPEN), {"role": "dev-lead", "intent": OPEN,
                                                                           "content_id": THIS, "branch_head": None}))
        d = decide(facts(label_events=READIED_BY_A_PERSON, branch_head="9f2c41d"))
        self.assertEqual(d["admit"]["branch_head"], "9f2c41d")
        self.assertNotIn("branch_head", decide(TRIAGED)["admit"])

    def test_an_unreadable_branch_head_defers_the_opening_run_alone(self):
        for value in ("", 1, ["9f2c41d"]):
            self.assertEqual(what(decide(facts(label_events=READIED_BY_A_PERSON, branch_head=value))),
                             ("defer", "branch_unreadable", None), value)
        f = facts(label_events=READIED_BY_A_PERSON)
        del f["branch_head"]
        self.assertEqual(what(decide(f)), ("defer", "branch_unreadable", None))
        self.assertEqual(what(decide(facts(label_events=ACCEPTED, branch_head=1)))[2], INVESTIGATE)

    def test_an_outsiders_issue_opens_only_from_a_statement_made_since_its_content_changed(self):
        events = [labelled(ADMIT), labelled(READY, minute=2)]
        d = decide(outsiders(label_events=events))
        self.assertEqual((what(d), d["attention"]), (("nothing", "no_statement", None), "needs_you"))
        for over, want in (({"role_comments": [comment(ANALYST, 1)]}, OPEN), ({"role_comments": [comment(ANALYST, 0)]}, None),
                           ({"role_comments": [comment(OTHER_APP, 1)]}, None), ({"last_writer_comment_at": at(1)}, OPEN),
                           ({"last_writer_comment_at": at(0)}, None)):
            d = decide(outsiders(**dict({"label_events": events}, **over)))
            self.assertEqual(what(d)[2], want, over)
        # With no investigating Role declared, no App's comment is a statement.
        cfg = config(intents=intents(investigate=None))
        self.assertEqual(decide(outsiders(label_events=events, role_comments=[comment(ANALYST, 1)]), cfg=cfg)["reason"],
                         "no_statement")

    def test_opening_attempts_are_bounded_and_hold_even_while_an_opening_run_is_in_flight(self):
        tries = LIMITS["max_attempts"]
        spent = [failed(OPEN, 2 + i, "o%d" % i, role="dev-lead") for i in range(tries)]
        ready = facts(label_events=READIED_BY_A_PERSON)
        self.assertEqual(what(decide(ready, spent[:-1])), ("admit", "ready", OPEN))
        self.assertEqual(what(decide(ready, spent)), ("hold", "attempts_exhausted", None))
        d = decide(ready, spent[:-1] + [opening(status="queued")])
        self.assertEqual((d["state"], what(d), d["attention"]), ("in_progress", ("nothing", "opening_run", None), "working"))
        d = decide(ready, spent + [opening(status="queued")])
        self.assertEqual((d["state"], what(d)), ("held", ("hold", "attempts_exhausted", None)))
        undeclared = decide(ready, [opening()], cfg=config(intents=intents(opening=None)))
        self.assertEqual((what(undeclared), undeclared["attention"]), (("nothing", "opening_run", None), "working"))
        # With the opening Intent undeclared, the issue wants no opening Run, and with none in flight it reads
        # intent_undeclared: so its spent attempts hold nothing while the opening Run waits either (decision 0003).
        d = decide(ready, spent, cfg=config(intents=intents(opening=None)))
        self.assertEqual((d["state"], what(d), d["attention"]),
                         ("ready", ("nothing", "intent_undeclared", None), "needs_you"))
        d = decide(ready, spent + [opening(status="queued")], cfg=config(intents=intents(opening=None)))
        self.assertEqual((d["state"], what(d), d["attention"]),
                         ("in_progress", ("nothing", "opening_run", None), "working"))


class WantedRun(unittest.TestCase):
    """While a Run is in flight, the attempts and the Run ceiling are asked about the Run the issue's State wants, found
    as with none in flight, and not about the Run in flight; an issue that wants no Run is not held by them (decision
    0003). Every Run here starts after a person with write access last acted, so each counts."""

    CEILING = LIMITS["max_runs_per_item"]

    def reading(self, f, runs, ctx=None, cfg=None) -> tuple:
        d = decide(f, runs, ctx=ctx, cfg=cfg)
        return d["state"], d["reason"], d["outcome"], d["attention"]

    def test_the_ceilings_are_asked_about_the_run_the_issue_wants(self):
        # An outsider's admitted issue in triage, investigated. Its readiness Run was admitted twice, the second time
        # by a pass that did not see the first (P-22, P-17), and the first failed: the ceiling is reached. Then the
        # outsider edits the issue, its acceptance lapses, and it wants no Run.
        events = [labelled(ADMIT, WRITER, 1), labelled(TRIAGE, CONTROLLER, 2)]
        settled = [investigated()] + [failed(JUDGE, 4 + i, "j%d" % i, outcome="environment", role="readiness")
                                      for i in range(self.CEILING - 1)]
        queued = run(status="queued", minute=21, name="q1")
        ended = dict(queued, status="completed", conclusion="failure", outcome="environment")
        before = outsiders(label_events=events, last_writer_action_at=at(1), role_comments=[comment(ANALYST, 3)])
        edited = dict(before, content_id=OTHER, content_changed_at=at(25))
        self.assertEqual(len(settled), self.CEILING)
        for paused in (False, True, None):
            self.assertEqual(self.reading(edited, settled + [queued], ctx=context(paused=paused)),
                             ("new", "acceptance_lapsed", "nothing", "working"), paused)
        for runs in (settled, settled + [ended]):
            self.assertEqual(self.reading(edited, runs), ("new", "acceptance_lapsed", "nothing", "needs_you"))
        # The other side: without the edit, the issue still wants a verdict, and the ceiling holds it.
        for paused in (False, True, None):
            for runs in (settled + [queued], settled):
                self.assertEqual(self.reading(before, runs, ctx=context(paused=paused)),
                                 ("held", "run_ceiling", "hold", "needs_you"), (paused, len(runs)))

    def test_the_issues_own_example_wants_no_verdict_once_a_person_removed_ready(self):  # issue 171
        # As the issue gives it. Its last_writer_action_at cannot happen: the person who removed factory:ready acted
        # at minute 31, after which none of these Runs would count. It stands as a boundary of what the Kernel reads.
        f = facts(label_events=ACCEPTED + [labelled(READY, minute=30), unlabelled(READY, minute=31)])
        settled = [investigated()] + [failed(JUDGE, 4 + i, "j%d" % i, outcome="environment", role="readiness")
                                      for i in range(self.CEILING - 1)]
        queued = run(status="queued", minute=40, name="q1")
        ended = dict(queued, status="completed", conclusion="failure", outcome="environment")
        for paused in (False, True, None):
            self.assertEqual(self.reading(f, settled + [queued], ctx=context(paused=paused)),
                             ("triage", "triage", "nothing", "working"), paused)
        for runs in (settled, settled + [ended]):
            self.assertEqual(self.reading(f, runs), ("triage", "ready_removed", "nothing", "needs_you"))

    def test_the_ceilings_are_asked_of_the_intent_wanted_and_not_of_the_one_in_flight(self):
        # Three investigations failed for the issue, and a later one succeeded: the issue wants a verdict, whose
        # attempts are not spent, while an investigation admitted twice still waits.
        tries = [failed(INVESTIGATE, 1 + i, "f%d" % i) for i in range(LIMITS["max_attempts"])]
        waiting = investigated(status="queued", minute=7, name="q1")
        self.assertEqual(self.reading(TRIAGED, tries + [investigated(minute=8), waiting]),
                         ("triage", "triage", "nothing", "working"))
        # The other side: with no investigation that succeeded, it wants one, and its spent attempts hold it.
        self.assertEqual(self.reading(TRIAGED, tries + [waiting]), ("held", "attempts_exhausted", "hold", "needs_you"))

    def test_an_opening_run_in_flight_is_left_out_to_find_the_run_wanted(self):
        # An opening Run waiting shows the issue in progress (row 7), but the Run wanted is the one the issue wants
        # without it: a verdict a person overruled, acceptance, or an investigation whose attempts are spent.
        waiting = dict(opening(status="queued"), started_at=at(40), run="q1")
        settled = [investigated()] + [failed(JUDGE, 4 + i, "j%d" % i, outcome="environment", role="readiness")
                                      for i in range(self.CEILING - 1)]
        overruled = facts(label_events=ACCEPTED + [labelled(READY, minute=30), unlabelled(READY, minute=31)])
        self.assertEqual(self.reading(overruled, settled), ("triage", "ready_removed", "nothing", "needs_you"))
        self.assertEqual(self.reading(overruled, settled + [waiting]), ("in_progress", "opening_run", "nothing", "working"))
        # The other side: a verdict still wanted is held at the Run ceiling while the opening Run waits.
        self.assertEqual(self.reading(TRIAGED, settled + [waiting]), ("held", "run_ceiling", "hold", "needs_you"))
        spent = [failed(INVESTIGATE, 1 + i, "e%d" % i, outcome="environment") for i in range(self.CEILING)]
        self.assertEqual(what(decide(facts(), spent)), ("act", "acceptance_due", "accept"))
        self.assertEqual(self.reading(facts(), spent + [waiting]), ("in_progress", "opening_run", "nothing", "working"))
        tries = [failed(INVESTIGATE, 1 + i, "f%d" % i) for i in range(LIMITS["max_attempts"])]
        for runs in (tries, tries + [waiting]):
            self.assertEqual(self.reading(TRIAGED, runs), ("held", "attempts_exhausted", "hold", "needs_you"))
        self.assertEqual(self.reading(TRIAGED, tries[:-1] + [waiting]),
                         ("in_progress", "opening_run", "nothing", "working"))

    def test_only_the_opening_run_in_flight_is_left_out_and_what_another_wrote_is_not_read(self):
        # A readiness Run still in flight has added factory:ready, which does not count until it completes: the issue
        # without the opening Run is in triage, wanting a verdict whose attempts are spent. Read without every Run in
        # flight, the label would count, and the issue would want the opening Run, which nothing holds.
        tries = [failed(JUDGE, 4 + i, "j%d" % i, role="readiness") for i in range(LIMITS["max_attempts"])]
        judging = run(status="in_progress", minute=10, name="q1")
        waiting = dict(opening(status="queued"), started_at=at(15), run="q2")
        f = facts(label_events=ACCEPTED + [labelled(READY, READINESS, 20)])
        self.assertEqual(self.reading(f, [investigated()] + tries + [judging, waiting]),
                         ("held", "attempts_exhausted", "hold", "needs_you"))
        # The other side: one attempt short, nothing holds it, and it shows in progress while the opening Run waits.
        self.assertEqual(self.reading(f, [investigated()] + tries[:-1] + [judging, waiting]),
                         ("in_progress", "opening_run", "nothing", "working"))

    def test_an_issue_in_new_wants_no_run_while_one_waits(self):
        spent = [failed(INVESTIGATE, 1 + i, "e%d" % i, outcome="environment") for i in range(self.CEILING)]
        queued = investigated(status="queued", minute=20, name="q1")
        self.assertEqual(self.reading(facts(), spent + [queued]), ("new", "acceptance_due", "nothing", "working"))
        self.assertEqual(what(decide(facts(), spent)), ("act", "acceptance_due", "accept"))

    def test_the_run_ceiling_holds_no_issue_that_wants_no_run(self):
        spent = [failed(INVESTIGATE, 4 + i, "e%d" % i, outcome="environment") for i in range(self.CEILING)]
        queued = run(status="queued", minute=20, name="q1")
        verdict = [investigated(), run()] + spent[:-2]
        statementless = outsiders(label_events=[labelled(ADMIT), labelled(READY, minute=2)])
        wanting_none = (
            ("in review", facts(linked=[pr()]), spent, None, ("in_review", "linked_ready", "nothing")),
            ("a linked draft", facts(linked=[agents(draft=True)]), spent, None,
             ("in_progress", "linked_draft", "nothing")),
            ("judged", TRIAGED, verdict, None, ("triage", "judged", "nothing")),
            ("no statement", statementless, spent, None, ("ready", "no_statement", "nothing")),
            ("intents unreadable", TRIAGED, spent, config(intents=None), ("triage", "intents_unreadable", "defer")),
        )
        for name, f, settled, cfg, alone in wanting_none:
            self.assertEqual(len(settled), self.CEILING, name)
            self.assertEqual(self.reading(f, settled, cfg=cfg)[:3], alone, name)
            state, reason, outcome, attention = self.reading(f, settled + [queued], cfg=cfg)
            self.assertEqual((state, outcome, attention), (alone[0], "nothing", "working"), name)
        # The other side: an issue that wants a Run is held at the ceiling while another waits.
        ready = facts(label_events=READIED_BY_A_PERSON)
        wanting = (
            ("an investigation", TRIAGED, spent, investigated(status="queued", minute=20, name="q1")),
            ("a verdict", TRIAGED, [investigated()] + spent[:-1], queued),
            ("the opening Run", ready, spent, queued),
            ("the opening Run, in flight", ready, spent, opening(status="queued")),
        )
        for name, f, settled, flying in wanting:
            self.assertEqual(self.reading(f, settled + [flying]), ("held", "run_ceiling", "hold", "needs_you"), name)


class Apply(unittest.TestCase):
    """`apply` asks again with its own Run left out of the records (I-38), and writes nothing unless the Kernel still
    admits that Run: the same Intent, Role and content, and for the opening Run the same branch head (I-21)."""

    def assertRefused(self, admitted, f, runs=(), want=False):
        self.assertEqual(issue.still_admitted(admitted, decide(f, runs)), want, f["label_events"])

    def test_the_opening_run_is_refused_after_a_label_is_removed_a_hold_added_the_content_changed_or_the_head_moved(self):
        f = facts(label_events=READIED_BY_A_PERSON, branch_head="9f2c41d")
        admitted = decide(f)
        self.assertEqual(admitted["outcome"], "admit")
        # In flight, the Run holds the issue; left out, it is the Run still wanted.
        self.assertEqual(decide(f, [opening()])["outcome"], "nothing")
        self.assertRefused(admitted, f, want=True)
        for changed in (dict(f, label_events=f["label_events"] + [unlabelled(READY, minute=7)]),
                        dict(f, label_events=f["label_events"] + [labelled(HOLD, OTHER_APP, 7)]),
                        dict(f, content_id=OTHER, content_changed_at=at(7)),
                        dict(f, branch_head="a07e3c1")):
            self.assertRefused(admitted, changed)

    def test_an_investigating_or_readiness_run_is_refused_once_the_issue_changed(self):
        admitted = decide(TRIAGED)
        self.assertRefused(admitted, TRIAGED, want=True)
        for changed in (dict(TRIAGED, label_events=ACCEPTED + [unlabelled(TRIAGE, minute=7)]),
                        dict(TRIAGED, label_events=ACCEPTED + [labelled(HOLD, OTHER_APP, 7)]),
                        dict(TRIAGED, content_id=OTHER, content_changed_at=at(7))):
            self.assertRefused(admitted, changed)
        judging = decide(TRIAGED, [investigated()])
        self.assertRefused(judging, TRIAGED, [investigated()], want=True)
        self.assertRefused(judging, dict(TRIAGED, content_id=OTHER, content_changed_at=at(7)), [investigated()])
        self.assertRefused(judging, TRIAGED, [investigated(), run()])

    def test_a_decision_that_admits_nothing_admits_no_run(self):
        admitted = decide(TRIAGED)
        for f in (facts(), facts(state="closed"), facts(label_events=ACCEPTED, role_comments=None)):
            self.assertRefused(admitted, f)
        self.assertFalse(issue.still_admitted(decide(facts()), decide(facts())))


# An issue's wait past its State's limit (design §4.1, decision 0034). Each boundary from both sides.
START = at(0)
DEPENDABOT = {"kind": "app", "name": "dependabot[bot]", "can_write": True}


def minutes_after(time: str, minutes: int) -> str:
    """The time `minutes` minutes after `time`, in the one text format."""
    shape = "%Y-%m-%dT%H:%M:%SZ"
    return (datetime.datetime.strptime(time, shape) + datetime.timedelta(minutes=minutes)).strftime(shape)


# When each wait below last moved, an hour after the issue was opened; and passes have run since before it.
MOVED = minutes_after(START, 60)
PASSING = context(passes_since=START)


def limit(state: str) -> int:
    """The limit lifecycle/issue.json sets on a wait in `state`, in minutes."""
    return LIFECYCLE["stale_after_minutes"][state]


def event(label: str, by: dict, time: str, action: str = "labeled") -> dict:
    """A label event at any time, not only in the issue's first hour."""
    return dict(labelled(label, by, action=action), at=time)


# An issue in triage, accepted by the Controller at MOVED, with its investigation due.
WAITING = facts(label_events=[event(TRIAGE, CONTROLLER, MOVED)])


class Stale(unittest.TestCase):
    """A wait past its State's limit in lifecycle/issue.json, while passes ran, is the Maintainer's to see. Only the
    attention changes (I-1), and only on a wait for the Factory's own next act."""

    def test_a_wait_past_its_states_limit_shows_stale_and_changes_nothing_else(self):  # I-1
        moved = facts(last_writer_action_at=MOVED)
        waits = [
            ("new", ("act", "acceptance_due", "accept"), moved),
            ("triage", ("admit", "triage", INVESTIGATE), dict(moved, label_events=ACCEPTED)),
            ("ready", ("admit", "ready", OPEN), dict(moved, label_events=READIED_BY_A_PERSON)),
            ("in_progress", ("nothing", "linked_draft", None), dict(moved, linked=[agents(draft=True)])),
        ]
        for state, want, f in waits:
            with self.subTest(state):
                cap = limit(state)
                before = decide(f, ctx=PASSING, now=minutes_after(MOVED, cap - 1))
                self.assertEqual((before["state"], what(before), before["attention"]), (state, want, "ready"))
                self.assertEqual(decide(f, ctx=PASSING, now=minutes_after(MOVED, cap)), before)
                past = decide(f, ctx=PASSING, now=minutes_after(MOVED, cap + 1))
                self.assertEqual((past["attention"], dict(past, attention="ready")), ("stale", before))

    def test_a_person_a_run_nobody_or_a_deferral_of_the_whole_scope_is_never_stale(self):  # I-1, §4.6
        tries = LIMITS["max_attempts"]
        spent = [failed(INVESTIGATE, 1 + i, "f%d" % i) for i in range(tries)]
        late = minutes_after(MOVED, 10 * max(LIFECYCLE["stale_after_minutes"].values()))
        cases = [
            ("intent_undeclared", "needs_you", TRIAGED, [], {}, config(intents=intents(investigate=None))),
            ("attempts_exhausted", "needs_you", TRIAGED, spent, {}, config()),
            ("human_hold", "needs_you", facts(label_events=[labelled(HOLD)]), [], {}, config()),
            ("triage", "working", TRIAGED, [investigated(status="in_progress")], {}, config()),
            ("not_accepted", "none", outsiders(), [], {}, config()),
            ("linked_ready", "none", facts(linked=[pr()]), [], {}, config()),
            ("hands_off", "none", facts(label_events=[labelled(HANDS_OFF)]), [], {}, config()),
            ("merged", "none", facts(linked=[pr(is_open=False, merged=5)]), [], {}, config()),
            ("paused", "ready", TRIAGED, [], {"paused": True}, config()),
            ("pause_unreadable", "ready", TRIAGED, [], {"paused": None}, config()),
            ("capacity", "ready", TRIAGED, [], {"model_deferred_until": minutes_after(late, 1)}, config()),
            ("capacity_unreadable", "ready", TRIAGED, [], {"active_runs": None}, config()),
            ("concurrency", "ready", TRIAGED, [], {"active_runs": LIMITS["org_max_active_runs"]}, config()),
            ("run_unidentified", "ready", TRIAGED, [], {"unidentified_runs": [dict(UNNAMED, created_at=late)]}, config()),
        ]
        for reason, attention, f, runs, over, cfg in cases:
            with self.subTest(reason):
                d = decide(f, runs, ctx=context(**dict(over, passes_since=START)), cfg=cfg, now=late)
                self.assertEqual((d["reason"], d["attention"]), (reason, attention))
                # Read with no wait at all, the Decision is the same.
                self.assertEqual(d, decide(f, runs, ctx=context(**dict(over, passes_since=late)), cfg=cfg, now=late))

    def test_an_issue_moves_at_what_its_own_facts_say_moved_it_and_at_nothing_else(self):  # §4.1, I-39
        then = minutes_after(MOVED, 2)
        now = minutes_after(MOVED, limit("triage") + 1)
        self.assertEqual(decide(WAITING, ctx=PASSING, now=now)["attention"], "stale")
        self.assertEqual(decide(WAITING, ctx=PASSING, now=minutes_after(MOVED, limit("triage")))["attention"], "ready")
        events = WAITING["label_events"]
        # Each source, at `then`. Where it leads to another State, that State's limit is read.
        sources = [
            ("its life began again", dict(WAITING, life_started_at=then, reopened_last_by="writer", reopened_last_at=then),
             [], "new"),
            ("its content changed", dict(WAITING, content_changed_at=then, content_id=OTHER), [], "triage"),
            ("a writer acted", dict(WAITING, last_writer_action_at=then), [], "triage"),
            ("a writer commented", dict(WAITING, last_writer_comment_at=then), [], "triage"),
            ("a person removed a control label",
             dict(WAITING, label_events=events + [event(HOLD, WRITER, then, "unlabeled")]), [], "triage"),
            ("a person added one", dict(WAITING, label_events=events + [event(TRIAGE, COLLEAGUE, then)]), [], "triage"),
            ("the App declared for it added one",
             dict(WAITING, label_events=events + [event(TRIAGE, CONTROLLER, then)]), [], "triage"),
            ("a Run on it started", WAITING, [dict(investigated(), started_at=then)], "triage"),
            ("a linked pull request opened", dict(WAITING, linked=[dict(agents(draft=True), opened_at=then)]), [],
             "in_progress"),
            ("a writer's linked pull request opened", dict(WAITING, linked=[dict(pr(draft=True), opened_at=then)]), [],
             "in_progress"),
            ("a linked pull request closed",
             dict(WAITING, linked=[dict(agents(is_open=False, closed=0), opened_at=START, closed_at=then)]), [],
             "triage"),
        ]
        for name, f, runs, state in sources:
            with self.subTest(name):
                # The source is the only movement after MOVED: it is when the issue last moved.
                self.assertEqual(issue.moved_at(f, runs, config(), now), then)
                d = decide(f, runs, ctx=PASSING, now=minutes_after(then, limit(state)))
                self.assertEqual((d["state"], d["attention"]), (state, "ready"))
                d = decide(f, runs, ctx=PASSING, now=minutes_after(then, limit(state) + 1))
                self.assertEqual((d["state"], d["attention"]), (state, "stale"))
        # Nothing else moves it, at `then`; nor does any source timed after `now`.
        later = minutes_after(now, 1)
        dependency = dict(pr(by=DEPENDABOT, cls="dependency"), opened_at=then)
        others = [
            ("another App removed a control label",
             dict(WAITING, label_events=events + [event(HOLD, OTHER_APP, then, "unlabeled")]), [], "triage"),
            ("another App added one", dict(WAITING, label_events=events + [event(ADMIT, OTHER_APP, then)]), [],
             "triage"),
            ("a person's label the Kernel does not read",
             dict(WAITING, label_events=events + [event("bug", WRITER, then)]), [], "triage"),
            ("a Role's comment", dict(WAITING, role_comments=[{"by": ANALYST["name"], "at": then}]), [], "triage"),
            ("a dependency bot's pull request opened", dict(WAITING, linked=[dependency]), [], "triage"),
            ("a dependency bot's pull request closed",
             dict(WAITING, linked=[dict(dependency, open=False, opened_at=START, closed_at=then)]), [], "triage"),
            ("a stranger's pull request nobody admitted", dict(WAITING, linked=[dict(strangers(), opened_at=then)]),
             [], "triage"),
            # Each of the sources above, timed after now.
            ("a life begun after now", dict(WAITING, life_started_at=later, reopened_last_by="writer",
                                            reopened_last_at=later), [], "new"),
            ("an edit after now", dict(WAITING, content_changed_at=later, content_id=OTHER), [], "triage"),
            ("a writer's action after now", dict(WAITING, last_writer_action_at=later), [], "triage"),
            ("a writer's comment after now", dict(WAITING, last_writer_comment_at=later), [], "triage"),
            ("a person's label after now", dict(WAITING, label_events=events + [event(TRIAGE, COLLEAGUE, later)]), [],
             "triage"),
            ("a Run started after now", WAITING, [dict(investigated(), started_at=later)], "triage"),
            ("a linked pull request opened after now", dict(WAITING, linked=[dict(agents(draft=True), opened_at=later)]),
             [], "in_progress"),
            ("a linked pull request closed after now",
             dict(WAITING, linked=[dict(agents(is_open=False, closed=0), opened_at=START, closed_at=later)]), [],
             "triage"),
        ]
        for name, f, runs, state in others:
            with self.subTest(name):
                d = decide(f, runs, ctx=PASSING, now=now)
                self.assertEqual((d["state"], d["attention"]), (state, "stale"))
        # A time after now is passed over, and the wait counts from the newest before it.
        f = dict(WAITING, last_writer_comment_at=then, last_writer_action_at=later)
        self.assertEqual(decide(f, ctx=PASSING, now=now)["attention"], "ready")
        # With every source after now, and the passes too, no time is left to count from: the wait shows.
        before = minutes_after(START, -1)
        try:
            moved, d = issue.moved_at(WAITING, [], config(), before), decide(WAITING, ctx=PASSING, now=before)
        except Exception as e:  # what is asserted is that it returns at all
            self.fail("every source after now raised %r" % e)
        self.assertEqual((moved, d["state"], d["attention"]), (None, "triage", "stale"))

    def test_a_wait_counts_no_earlier_than_the_chain_of_passes(self):  # I-1, §4.6
        now = minutes_after(MOVED, limit("triage") + 1)
        since = minutes_after(MOVED, 1000)
        self.assertEqual(decide(WAITING, ctx=context(passes_since=since), now=now)["attention"], "ready")
        for since in (MOVED, START, None, "never", minutes_after(now, 1)):
            self.assertEqual(decide(WAITING, ctx=context(passes_since=since), now=now)["attention"], "stale", since)

    def test_a_lifecycle_not_the_issues_shows_every_wait_as_stale(self):  # §4.1
        now = minutes_after(MOVED, 1)
        own = decide(WAITING, ctx=PASSING, now=now)
        self.assertEqual((what(own), own["attention"]), (("admit", "triage", INVESTIGATE), "ready"))
        # The issue's own limits under another work item's name, lifecycle/pull_request.json, and none that can be read.
        for lifecycle in (dict(LIFECYCLE, work_item="pull_request"), CONFIG["lifecycle"], None, [], "issue"):
            d = decide(WAITING, ctx=PASSING, cfg=dict(config(), lifecycle=lifecycle), now=now)
            self.assertEqual((d["attention"], dict(d, attention="ready")), ("stale", own), lifecycle)
        cfg = config()
        del cfg["lifecycle"]
        self.assertEqual(decide(WAITING, ctx=PASSING, cfg=cfg, now=now)["attention"], "stale")

    def test_a_link_with_no_opening_time_defers(self):
        good = agents(draft=True)
        missing = dict(good)
        del missing["opened_at"]
        for entry in (dict(good, opened_at=None), dict(good, opened_at="2026-10-11"),
                      dict(good, opened_at="2026-02-30T12:00:00Z"), missing):
            for f in (facts(linked=[entry]), facts(state="closed", linked=[entry])):
                d = decide(f)
                self.assertEqual((d["state"], what(d)), (None, ("defer", "linked_unreadable", None)), entry)
        # The other side: read whole, the draft holds the issue in progress.
        self.assertEqual(decide(facts(linked=[good]))["state"], "in_progress")

    def test_a_link_whose_opening_merge_and_close_are_out_of_order_defers(self):
        # Each time is a real moment, but a close before the opening is no chronology: read, its opening would be the
        # issue's newest movement, and hold off its staleness.
        then = minutes_after(MOVED, 2)
        closed = dict(agents(is_open=False, closed=0), opened_at=minutes_after(then, 1), closed_at=then)
        merged = dict(agents(is_open=False, merged=0), opened_at=minutes_after(then, 1), merged_at=then, closed_at=then,
                      closed_issue_at=then)
        # A merge before the opening, though the close is after it: read, the issue would be done.
        merged_first = dict(merged, closed_at=minutes_after(then, 2))
        # A merge after the close, though both are after the opening: a merge closes it, so it cannot come later.
        merged_late = dict(merged, opened_at=MOVED, merged_at=minutes_after(then, 1), closed_issue_at=minutes_after(then, 1))
        for entry in (closed, merged_first, merged, merged_late):
            for f in (dict(WAITING, linked=[entry]), dict(WAITING, state="closed", closed_first_at=then, linked=[entry])):
                d = decide(f, ctx=PASSING, now=minutes_after(MOVED, limit("triage") + 1))
                self.assertEqual((d["state"], what(d)), (None, ("defer", "linked_unreadable", None)), entry)
        # The other side: a close in the second it opened, or after it, is read.
        for opened in (then, MOVED):
            d = decide(dict(WAITING, linked=[dict(closed, opened_at=opened)]), ctx=PASSING,
                       now=minutes_after(then, limit("triage")))
            self.assertEqual((d["state"], what(d), d["attention"]), ("triage", ("admit", "triage", INVESTIGATE), "ready"))
        # And a merge in the second it opened, or after it, and in the second it closed, or before it, is read: the issue
        # is done. A merge and its close in one second is the usual case.
        for entry in (dict(merged_first, opened_at=then), dict(merged_first, opened_at=MOVED),
                      dict(merged, opened_at=MOVED), dict(merged, opened_at=then)):
            d = decide(dict(WAITING, linked=[entry]), ctx=PASSING, now=minutes_after(then, limit("triage")))
            self.assertEqual((d["state"], what(d)), ("done", ("nothing", "merged", None)), entry)

    def test_a_lifecycle_whose_limit_cannot_be_read_shows_the_wait_as_stale(self):  # §4.1
        now = minutes_after(MOVED, 1)
        own = decide(WAITING, ctx=PASSING, now=now)
        limits = LIFECYCLE["stale_after_minutes"]
        # A limit for the State that is no finite number of minutes, a bool among them; json.loads reads NaN too.
        for cap in (json.loads("NaN"), float("inf"), True, "1440", None, [1440]):
            lifecycle = dict(LIFECYCLE, stale_after_minutes=dict(limits, triage=cap))
            d = decide(WAITING, ctx=PASSING, cfg=dict(config(), lifecycle=lifecycle), now=now)
            self.assertEqual((d["attention"], dict(d, attention="ready")), ("stale", own), cap)
        # No limit for the State, no limits that can be read, or a Lifecycle that only names the issue.
        absent = dict(limits)
        del absent["triage"]
        for lifecycle in (dict(LIFECYCLE, stale_after_minutes=absent), dict(LIFECYCLE, stale_after_minutes=None),
                          dict(LIFECYCLE, stale_after_minutes=[]), dict(LIFECYCLE, stale_after_minutes={}),
                          {"work_item": "issue"}):
            d = decide(WAITING, ctx=PASSING, cfg=dict(config(), lifecycle=lifecycle), now=now)
            self.assertEqual((d["attention"], dict(d, attention="ready")), ("stale", own), lifecycle)
        # The other side: a limit in minutes as a whole or a fractional number is read.
        for cap, want in ((1440, "ready"), (1440.0, "ready"), (1.5, "ready"), (0, "stale"), (0.5, "stale")):
            lifecycle = dict(LIFECYCLE, stale_after_minutes=dict(limits, triage=cap))
            d = decide(WAITING, ctx=PASSING, cfg=dict(config(), lifecycle=lifecycle), now=now)
            self.assertEqual(d["attention"], want, cap)

    def test_an_end_never_goes_stale(self):
        # lifecycle/issue.json sets no limit on an end, which never waits.
        far = minutes_after(MOVED, 10 * max(LIFECYCLE["stale_after_minutes"].values()))
        for end in LIFECYCLE["terminal"]:
            self.assertFalse(issue.overdue(LIFECYCLE, end, START, START, far), end)
            # The other side: a Lifecycle whose ends cannot be read has no limit for them, and shows the wait.
            self.assertTrue(issue.overdue(dict(LIFECYCLE, terminal=None), end, START, START, far), end)
        self.assertTrue(issue.overdue(LIFECYCLE, "triage", START, START, far))

    def test_any_app_the_configuration_names_moves_an_issue_by_any_control_label(self):  # §4.1
        added, removed = minutes_after(MOVED, 1), minutes_after(MOVED, 2)
        now = minutes_after(MOVED, limit("triage") + 1)
        # Some other App adds factory:ready, and the Controller, named for factory:triage alone, removes it.
        f = dict(WAITING, label_events=WAITING["label_events"] + [event(READY, OTHER_APP, added),
                                                                  event(READY, CONTROLLER, removed, "unlabeled")])
        self.assertEqual(issue.moved_at(f, [], config(), now), removed)
        d = decide(f, ctx=PASSING, now=now)
        self.assertEqual((d["state"], d["attention"]), ("triage", "ready"))
        # The App named for factory:ready alone moves it too: it removes factory:hold, and the issue stays in triage.
        f = dict(WAITING, label_events=WAITING["label_events"] + [event(HOLD, READINESS, removed, "unlabeled")])
        self.assertEqual(issue.moved_at(f, [], config(), now), removed)
        d = decide(f, ctx=PASSING, now=now)
        self.assertEqual((d["state"], d["attention"]), ("triage", "ready"))
        # Or it adds factory:triage, which only the Controller's counts: the issue is new, with new's limit.
        f = dict(WAITING, label_events=WAITING["label_events"] + [event(TRIAGE, READINESS, removed)])
        self.assertEqual(issue.moved_at(f, [], config(), now), removed)
        d = decide(f, ctx=PASSING, now=minutes_after(removed, limit("new")))
        self.assertEqual((d["state"], d["attention"]), ("new", "ready"))
        d = decide(f, ctx=PASSING, now=minutes_after(removed, limit("new") + 1))
        self.assertEqual((d["state"], d["attention"]), ("new", "stale"))
        # The other side: an App named nowhere moves nothing, by any label.
        f = dict(WAITING, label_events=WAITING["label_events"] + [event(READY, OTHER_APP, added),
                                                                  event(READY, OTHER_APP, removed, "unlabeled")])
        self.assertEqual(issue.moved_at(f, [], config(), now), MOVED)
        self.assertEqual(decide(f, ctx=PASSING, now=now)["attention"], "stale")

    def test_an_outsiders_pull_request_moves_nothing_even_once_admitted(self):  # §4.1
        # Its author could close and reopen it every day, and keep the issue from ever showing.
        then = minutes_after(MOVED, 2)
        now = minutes_after(MOVED, limit("triage") + 1)
        cycled = dict(strangers(admitted=True, is_open=False, closed=0), opened_at=START, closed_at=then)
        reopened = dict(strangers(admitted=True, draft=True), opened_at=then)
        for f, state in ((dict(WAITING, linked=[cycled]), "triage"), (dict(WAITING, linked=[reopened]), "in_progress")):
            d = decide(f, ctx=PASSING, now=now)
            self.assertEqual((d["state"], d["attention"]), (state, "stale"))
            # The other side: the Factory's own pull request, opened or closed at the same moments, moves it.
            ours = [dict(p, **{"class": "agent", "opener": dict(AUTHOR_APP), "label_events": []}) for p in f["linked"]]
            d = decide(dict(f, linked=ours), ctx=PASSING, now=now)
            self.assertEqual((d["state"], d["attention"]), (state, "ready"))

    def test_a_context_that_cannot_be_read_says_nothing_of_the_passes(self):  # I-1, §4.6
        # An issue waiting on its linked draft, which asks the brakes nothing, so only staleness reads the context.
        f, cfg = facts(linked=[agents(draft=True)], last_writer_action_at=MOVED), config()
        for when, want in ((limit("in_progress"), "ready"), (limit("in_progress") + 1, "stale")):
            now = minutes_after(MOVED, when)
            unread = issue.decide(f, [], context(passes_since=None), cfg, now)
            self.assertEqual((unread["state"], what(unread), unread["attention"]),
                             ("in_progress", ("nothing", "linked_draft", None), want))
            for ctx in (None, "paused", [], 5):
                try:
                    d = issue.decide(f, [], ctx, cfg, now)
                except Exception as e:  # what is asserted is that it returns at all
                    self.fail("a context of %r raised %r" % (ctx, e))
                self.assertEqual(d, unread, (ctx, when))
        # The input that once raised: moved a moment ago, so it is not yet stale.
        try:
            d = issue.decide(facts(linked=[agents(draft=True)]), [], None, cfg, at(0))
        except Exception as e:
            self.fail("a context of None raised %r" % e)
        self.assertEqual((d["state"], d["attention"]), ("in_progress", "ready"))
        # An issue that wants a Run asks the brakes, which read no Pause in it: every act and Run defers, as under a
        # Pause that cannot be read, and a deferral of the whole scope is never stale.
        now = minutes_after(MOVED, limit("triage") + 1)
        for f, state in ((WAITING, "triage"), (dict(WAITING, label_events=READIED_BY_A_PERSON), "ready"),
                         (facts(last_writer_action_at=MOVED), "new")):
            unread = issue.decide(f, [], context(passes_since=START, paused=None), cfg, now)
            self.assertEqual((unread["state"], what(unread), unread["attention"]),
                             (state, ("defer", "pause_unreadable", None), "ready"))
            for ctx in (None, "paused", [], 5):
                try:
                    d = issue.decide(f, [], ctx, cfg, now)
                except Exception as e:  # what is asserted is that it returns at all
                    self.fail("a context of %r raised %r" % (ctx, e))
                self.assertEqual(d, unread, (ctx, state))

    def test_a_now_that_is_no_moment_shows_a_wait_as_stale_and_raises_nothing(self):  # §4.1
        own = decide(WAITING, ctx=PASSING, now=minutes_after(MOVED, 1))
        held = decide(facts(label_events=[labelled(HOLD)]), ctx=PASSING, now=minutes_after(MOVED, 1))
        for now in (None, 5, True, float("nan"), "never", "2026-02-30T12:00:00Z"):
            try:
                d = decide(WAITING, ctx=PASSING, now=now)
                h = decide(facts(label_events=[labelled(HOLD)]), ctx=PASSING, now=now)
            except Exception as e:  # what is asserted is that it returns at all
                self.fail("a now of %r raised %r" % (now, e))
            self.assertEqual((d["attention"], dict(d, attention="ready")), ("stale", own), now)
            # The other side: a Decision that never goes stale is as it was.
            self.assertEqual(h, held, now)
            # A capacity deadline cannot be compared with such a now: the Run defers, as on a capacity unread, and a
            # deferral of the whole scope is never stale.
            try:
                d = decide(WAITING, ctx=context(passes_since=START, model_deferred_until=MOVED), now=now)
            except Exception as e:
                self.fail("a now of %r with a capacity deadline raised %r" % (now, e))
            self.assertEqual((d["state"], what(d), d["attention"]), ("triage", ("defer", "capacity_unreadable", None),
                                                                     "ready"), now)
        # Nor can a deadline that is no moment be compared with a real now.
        now = minutes_after(MOVED, 1)
        for until in (5, True, "never", "2026-02-30T12:00:00Z"):
            try:
                d = decide(WAITING, ctx=context(passes_since=START, model_deferred_until=until), now=now)
            except Exception as e:
                self.fail("a capacity deadline of %r raised %r" % (until, e))
            self.assertEqual(what(d), ("defer", "capacity_unreadable", None), until)
        # The other side: a real deadline and a real now compare, at the boundary.
        for until, want in ((minutes_after(now, 1), ("defer", "capacity", None)), (now, ("admit", "triage", INVESTIGATE))):
            self.assertEqual(what(decide(WAITING, ctx=context(passes_since=START, model_deferred_until=until), now=now)),
                             want, until)


if __name__ == "__main__":
    unittest.main()
