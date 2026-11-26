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
# The default branch's head as the pass read it: the commit an opening Run reads and lands on.
BASE = "b45e0f1d2c3a49586777a6b5c4d3e2f1a0b9c8d7"
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
       events=(), opened=0, closed_issue="merge", drafts=(), links=(), keyword=True, spans=(), closes=None,
       **read) -> dict:
    """A pull request that closes the issue. By default the Maintainer's, opened with the issue, open and ready. A
    merged one closed then, and closed the issue in its second, as the issue's timeline records it (P-33);
    `closed_issue=None` is one the issue's timeline never names, as one whose reference an edit added (P-46). `drafts`
    are its conversions to a draft and its markings ready, as (action, minute), the last of which is its flag now; `links`
    its links to the issue by hand and unlinkings, as (action, minute), none by default, as a closing keyword's; `keyword`
    whether its references name the issue by one now, and `spans` each time it stood as the passes saw it, as (minute
    first seen, minute first seen gone or None), none by default; `closes` its closes and reopenings, as (action, minute),
    by default its one close if it is closed, a merge's among them (issue 672, trials/P-48.json). `checks`, where given,
    is how its head's required checks stand (issue 825)."""
    if merged is not None and closed is None:
        closed = merged
    if closed_issue == "merge":
        closed_issue = merged
    return dict({"number": number, "class": cls, "opener": dict(WRITER if by is None else by), "open": is_open,
            "draft": draft, "opened_at": at(opened), "merged_at": None if merged is None else at(merged),
            "closed_at": None if closed is None else at(closed), "empty": empty, "label_events": list(events),
            "closed_issue_at": None if closed_issue is None else at(closed_issue),
            "draft_events": [{"action": action, "at": at(minute)} for action, minute in drafts],
            "link_events": [{"action": action, "at": at(minute)} for action, minute in links],
            "keyword": keyword, "keyword_spans": [{"seen_at": at(seen), "gone_at": None if gone is None else at(gone)}
                                                  for seen, gone in spans],
            "close_events": [{"action": action, "by": dict(WRITER), "at": at(minute)}
                             for action, minute in (closes if closes is not None else ([("closed", closed)] if closed is not None else []))]}, **read)


def closes(when: str) -> list:
    """A pull request's one close, at `when`, as its timeline gives it (issue 672)."""
    return [{"action": "closed", "by": dict(WRITER), "at": when}]


# The head of the Factory's draft, from this repo, on its work branch, as the linked port reads it with its checks.
DRAFT_HEAD = {"sha": "5c1e2d3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d", "ref": "factory-work/issue-7-1"}


def agents(**over) -> dict:
    """The Factory's own pull request: its author's App opened it, its head's required checks pending, its head read."""
    return pr(**dict({"by": AUTHOR_APP, "cls": "agent", "checks": "pending", "head": dict(DRAFT_HEAD)}, **over))


def strangers(admitted=False, **over) -> dict:
    """An outsider's pull request, which the Maintainer has once admitted, or not."""
    events = [labelled(ADMIT, minute=3)] if admitted else []
    return pr(**dict({"by": OUTSIDER, "cls": "outside", "events": events}, **over))


# The work branch's head, a commit's whole sha, where that branch stands (issue 1059).
BRANCH_HEAD = "9f2c41d07a3be58e1c6d0b4a7e25f3c18d90ab6e"


def facts(**over) -> dict:
    """An open issue the Maintainer opened at minute 0, with no label and no pull request, read in full."""
    f = {"schema": "issue-facts/1", "item": dict(ITEM), "state": "open", "author": dict(WRITER), "type": None, "type_events": [], "label_names": [], "assignees": [],
         "life_started_at": at(0), "reopened_last_by": "never", "content_id": THIS, "content_changed_at": at(0),
         "label_events": [], "linked": [], "role_comments": [], "last_writer_action_at": at(0),
         "last_writer_comment_at": None, "acts_since_writer": 0, "branch_head": None, "base_head": BASE,
         "complete": {"timeline": True, "linked": True, "runs": True, "branch": True}, "timeline_bounded": False,
         "read_at": at(50)}
    f.update(over)
    # A head the case gives is one an earlier opening Run recorded pushing, unless the case says whether it is: the
    # issues port tells it beside the head, and with no branch standing there is nothing to tell.
    if "branch_pushed" not in over:
        f["branch_pushed"] = True if issue.is_commit(f.get("branch_head")) else None
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
            (root / "kernel" / "__init__.py").write_text("")
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

    def test_a_timeline_past_the_ports_bound_defers_on_its_own_code_and_calls_a_person(self):  # issue 849, decision 0234
        # The port stopped at its bound: the issue defers `timeline_bounded`, a closed one's too, before a list read short
        # beside it, and a person is called, since more comments never bring the timeline back under the bound.
        for f in (facts(), facts(state="closed"), facts(complete={"timeline": False, "linked": False, "runs": False})):
            f.update(timeline_bounded=True, complete=dict(f["complete"], timeline=False))
            d = derive(f)
            self.assertEqual((d["state"], d["reason"], d["evidence"]), (None, "timeline_bounded", ["timeline"]))
            self.assertEqual((what(decide(f)), decide(f)["attention"]), (("defer", "timeline_bounded", None), "needs_you"))
        # Cut at a linked pull request's read alone, the issue's own timeline whole, it defers so too (Astra, Kimi).
        f = facts(timeline_bounded=True, complete={"timeline": True, "linked": False, "runs": True})
        self.assertEqual((derive(f)["reason"], decide(f)["attention"]), ("timeline_bounded", "needs_you"))
        # Within the bound, a timeline read short is the plain gap, which mends itself and calls no one.
        short = facts(timeline_bounded=False, complete={"timeline": False, "linked": True, "runs": True})
        self.assertEqual((derive(short)["reason"], derive(short)["evidence"], decide(short)["attention"]),
                         ("facts_incomplete", ["timeline"], "none"))
        self.assertEqual(derive(facts(timeline_bounded=False))["reason"], "acceptance_due")
        # A flag that is not exactly true or false cannot say the timeline is whole: it is a gap in it, never read as
        # within the bound.
        for flag in (None, "false", 0, 1, "true"):
            d = derive(facts(timeline_bounded=flag))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), (None, "facts_incomplete", ["timeline"]), flag)
        f = facts()
        del f["timeline_bounded"]
        self.assertEqual((derive(f)["reason"], derive(f)["evidence"]), ("facts_incomplete", ["timeline"]))
        self.assertEqual(derive(facts(timeline_bounded=None, complete={"timeline": True, "linked": False, "runs": True}))["evidence"],
                         ["linked", "timeline"])

    def test_a_chain_of_spans_the_records_broke_defers_on_its_own_code_and_calls_a_person(self):  # issue 849, decision 0253
        # The pass records break the chain of keyword spans while something names the issue: no later pass mends it, so
        # it defers `spans_broken`, a closed one's too, after a cut read and before a list read short, and calls a person.
        for f in (facts(), facts(state="closed"), facts(complete={"timeline": True, "linked": False, "runs": False})):
            f.update(spans_broken=True, complete=dict(f["complete"], linked=False))
            d = derive(f)
            self.assertEqual((d["state"], d["reason"], d["evidence"]), (None, "spans_broken", ["linked"]))
            self.assertEqual((what(decide(f)), decide(f)["attention"]), (("defer", "spans_broken", None), "needs_you"))
        self.assertEqual(derive(facts(spans_broken=True, timeline_bounded=True))["reason"], "timeline_bounded")
        # The flag defers alone, whatever the lists say (Astra).
        whole = facts(spans_broken=True, complete={"timeline": True, "linked": True, "runs": True})
        self.assertEqual((derive(whole)["reason"], decide(whole)["attention"]), ("spans_broken", "needs_you"))
        # Anything but exact true is not broken: the list read short beside it defers all the same, calling no one.
        for flag in (False, None, "true", 1):
            f = facts(spans_broken=flag, complete={"timeline": True, "linked": False, "runs": True})
            self.assertEqual((derive(f)["reason"], decide(f)["attention"]), ("facts_incomplete", "none"), flag)
        self.assertEqual(derive(facts(spans_broken=False))["reason"], "acceptance_due")

    def test_the_issue_world_meets_a_timeline_past_the_bound_under_faults_and_calls_a_person(self):  # decision 0234
        # The simulator's issue world sets the fact beside a timeline read short, in its own draws, so its fixed seeds
        # meet the deferral, which calls a person each time.
        import unittest.mock
        import sim.issues
        from sim.issues import IssueWorld
        met, seen, real = [], [], sim.issues.issue.decide

        def decide(facts, *a):
            seen.append((facts.get("timeline_bounded"), dict(facts["complete"])))
            return real(facts, *a)
        with unittest.mock.patch.object(sim.issues.issue, "decide", decide):
            for seed in range(1, 11):
                w = IssueWorld(seed)
                for _ in range(300):
                    w.step()
                met += [line for line in w.trace if "pass: None / timeline_bounded" in line]
        self.assertTrue(met)
        self.assertTrue(all(line.endswith("-> defer  [needs_you]") for line in met), met[:3])
        # The flag stands only beside the timeline or the linked list read short (Astra); each short within the bound is
        # met unflagged too.
        self.assertTrue(all(False in (complete["timeline"], complete["linked"]) for bounded, complete in seen if bounded is True))
        self.assertTrue(any(bounded is True and complete["linked"] is False for bounded, complete in seen))
        self.assertTrue(any(bounded is True and complete["timeline"] is False for bounded, complete in seen))
        self.assertTrue(all(bounded in (True, False) for bounded, _ in seen))
        self.assertTrue(any(bounded is False and complete["timeline"] is False for bounded, complete in seen))
        self.assertTrue(any(bounded is False and complete["linked"] is False for bounded, complete in seen))

    def test_the_issue_world_meets_a_broken_chain_of_spans_under_faults_and_calls_a_person(self):  # decision 0253
        # The issue world breaks the chain beside the linked list read short alone, so its fixed seeds meet the deferral,
        # which calls a person each time.
        import unittest.mock
        import sim.issues
        from sim.issues import IssueWorld
        met, seen, real = [], [], sim.issues.issue.decide

        def decide(facts, *a):
            seen.append((facts.get("spans_broken"), dict(facts["complete"])))
            return real(facts, *a)
        with unittest.mock.patch.object(sim.issues.issue, "decide", decide):
            for seed in range(1, 11):
                w = IssueWorld(seed)
                for _ in range(300):
                    w.step()
                met += [line for line in w.trace if "pass: None / spans_broken" in line]
        self.assertTrue(met)
        self.assertTrue(all(line.endswith("-> defer  [needs_you]") for line in met), met[:3])
        self.assertTrue(all(complete["linked"] is False for broken, complete in seen if broken is True))
        # Every pass says it, true or false, and a linked list read short is met unbroken too (Carbon).
        self.assertTrue(all(broken in (True, False) for broken, _ in seen))
        self.assertTrue(any(broken is False and complete["linked"] is False for broken, complete in seen))

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
               dict(good, label_events=[dict(labelled(HOLD), by=None)]), dict(good, label_events=None), "11",
               # Its draft events, each a conversion or a marking ready with its time, the last of them its flag now.
               dict(good, draft_events=None), dict(good, draft_events=[{"action": "ready_for_review"}]),
               dict(good, draft_events=[{"action": "drafted", "at": at(3)}]),
               dict(good, draft_events=[{"action": "converted_to_draft", "at": at(3)}]),
               dict(good, draft=True, draft_events=[{"action": "ready_for_review", "at": at(3)}]),
               # A time in another form or no string, an event that is no object, and one before it opened.
               dict(good, draft_events=[{"action": "ready_for_review", "at": "2026-10-11"}]),
               dict(good, draft=True, draft_events=[{"action": "converted_to_draft", "at": "2026-10-11T12:30:00"}]),
               dict(good, draft_events=[{"action": "ready_for_review", "at": 12}]),
               dict(good, draft_events=["ready_for_review"]),
               dict(good, opened_at=at(2), draft_events=[{"action": "converted_to_draft", "at": at(1)},
                                                         {"action": "ready_for_review", "at": at(3)}]),
               # Its links by hand and unlinkings (issue 551): each one or the other with its time, alternating, the
               # first a link, none before it opened, in order.
               dict(good, link_events=None), dict(good, link_events=["connected"]),
               dict(good, link_events=[{"action": "linked", "at": at(3)}]),
               dict(good, link_events=[{"action": "connected", "at": "2026-10-11"}]),
               dict(good, link_events=[{"action": "connected"}]),
               dict(good, link_events=[{"action": "disconnected", "at": at(3)}]),
               dict(good, link_events=[{"action": "connected", "at": at(3)}, {"action": "connected", "at": at(4)}]),
               dict(good, link_events=[{"action": "connected", "at": at(4)}, {"action": "disconnected", "at": at(3)}]),
               dict(good, opened_at=at(2), link_events=[{"action": "connected", "at": at(1)}]),
               dict(good, link_events=[{"action": "connected", "at": "2026-10-11T12:30:00"}]),
               dict(good, link_events=[{"action": "connected", "at": at(3)}, {"action": "linked", "at": at(4)}]),
               # Its closing keyword (issue 552): whether one names the issue now, and when a pass first saw it, a time
               # or null, no earlier than it opened.
               dict(good, keyword=None), dict(good, keyword="yes"), dict(good, keyword_spans=None),
               {k: v for k, v in good.items() if k != "keyword_spans"},
               # Each span a seen time, and a gone time or null, in order, none before it opened, only the last open.
               dict(good, keyword_spans=[{"seen_at": "soon", "gone_at": None}]),
               dict(good, keyword_spans=[{"seen_at": at(3)}]),
               dict(good, keyword_spans=[{"seen_at": at(3), "gone_at": 12}]),
               dict(good, keyword_spans=["soon"]),
               dict(good, opened_at=at(2), keyword_spans=[{"seen_at": at(1), "gone_at": None}]),
               dict(good, keyword=False, keyword_spans=[{"seen_at": at(3), "gone_at": at(2)}]),
               dict(good, keyword_spans=[{"seen_at": at(1), "gone_at": None}, {"seen_at": at(3), "gone_at": None}]),
               dict(good, keyword_spans=[{"seen_at": at(1), "gone_at": at(4)}, {"seen_at": at(3), "gone_at": None}]),
               dict(good, keyword_spans=[{"seen_at": at(1), "gone_at": at(2)}, {"seen_at": at(2), "gone_at": None}]),
               # Listed for nothing: no keyword now or once seen, no link by hand, no close it made.
               dict(good, keyword=False),
               # Its closes and reopenings (issue 672): each one or the other with its time, alternating, the first a
               # close, none before it opened, in order, and the last its close now: closed_at, or none.
               dict(good, close_events=None), dict(good, close_events=["closed"]),
               dict(good, close_events=[{"action": "merged", "by": dict(WRITER), "at": at(3)}, {"action": "reopened", "by": dict(WRITER), "at": at(4)}]),
               dict(good, close_events=[{"action": "closed", "by": dict(WRITER)}, {"action": "reopened", "by": dict(WRITER), "at": at(4)}]),
               dict(good, close_events=[{"action": "closed", "by": dict(WRITER), "at": "2026-10-11"}, {"action": "reopened", "by": dict(WRITER), "at": at(4)}]),
               dict(good, close_events=[{"action": "reopened", "by": dict(WRITER), "at": at(3)}]),
               dict(good, close_events=[{"action": "closed", "by": dict(WRITER), "at": at(3)}, {"action": "closed", "by": dict(WRITER), "at": at(4)},
                                        {"action": "reopened", "by": dict(WRITER), "at": at(5)}]),
               dict(good, close_events=[{"action": "closed", "by": dict(WRITER), "at": at(4)}, {"action": "reopened", "by": dict(WRITER), "at": at(3)}]),
               dict(good, opened_at=at(2), close_events=[{"action": "closed", "by": dict(WRITER), "at": at(1)}, {"action": "reopened", "by": dict(WRITER), "at": at(3)}]),
               dict(good, close_events=[{"action": "closed", "by": dict(WRITER), "at": at(3)}]),
               pr(is_open=False, closed=5, closes=[]), pr(is_open=False, closed=5, closes=[("closed", 4)]),
               # Its last close more than max_close_lag_seconds after closed_at (300 here), or at it exactly.
               pr(is_open=False, closed=5, closes=[("closed", 11)]), pr(is_open=False, closed=5, closes=[("closed", 10)]),
               # Closed now, but its last event a reopening, in closed_at's second (Astra).
               pr(is_open=False, closed=5, closes=[("closed", 3), ("reopened", 5)]),
               # A close time that is no time, beside a close event that is; and one before the opening, though its
               # close event, within the lag of it, is after the opening.
               dict(pr(is_open=False, closed=5), closed_at="soon"), dict(pr(is_open=False, closed=6, opened=5), closed_at=at(4)),
               # Merged a minute after its close time, its close event at the merge, within the lag of closed_at.
               dict(pr(is_open=False, merged=6, closes=[("closed", 6)]), closed_at=at(5)),
               # A merged pull request closed before its merge's second, or closed and reopened after it (Astra).
               pr(is_open=False, merged=5, closes=[("closed", 4), ("reopened", 6), ("closed", 7)], closed_issue=None),
               dict(pr(is_open=False, merged=5), close_events=[{"action": "closed", "by": dict(WRITER), "at": at(3)},
                                                              {"action": "reopened", "by": dict(WRITER), "at": at(4)},
                                                              {"action": "closed", "by": dict(WRITER), "at": at(5)},
                                                              {"action": "reopened", "by": dict(WRITER), "at": at(6)},
                                                              {"action": "closed", "by": dict(WRITER), "at": at(6)}]),
               pr(is_open=False, merged=5, closes=[("closed", 3), ("reopened", 4)]),
               # Each by whom, read whole as a label event's actor is (issue 552): none, or one that cannot be read.
               dict(good, close_events=[{"action": "closed", "at": at(3)}, {"action": "reopened", "by": dict(WRITER), "at": at(4)}]),
               dict(good, close_events=[{"action": "closed", "by": {"kind": "human", "name": "x"}, "at": at(3)},
                                        {"action": "reopened", "by": dict(WRITER), "at": at(4)}]),
               ]
        no_class = dict(good)
        del no_class["class"]
        # No close events at all is no history, not an empty one (Astra).
        no_closes = dict(good)
        del no_closes["close_events"]
        for entry in bad + [no_class, no_closes]:
            for f in (facts(linked=[entry]), facts(state="closed", linked=[entry])):
                d = derive(f)
                self.assertEqual((d["state"], d["reason"]), (None, "linked_unreadable"), entry)
        self.assertEqual(derive(facts(linked=None))["reason"], "linked_unreadable")
        # The other side: a close GitHub dates a second after closed_at, as it dated an issue's in trials/P-48.json, is
        # read (the Claude review of issue 672).
        trailing = dict(pr(is_open=False, closed=5), close_events=[{"action": "closed", "by": dict(WRITER),
                                                                    "at": "2026-10-11T12:05:01Z"}])
        self.assertNotEqual(derive(facts(linked=[trailing]))["reason"], "linked_unreadable")
        # A close 299 seconds after closed_at, inside the limit, is read; one at 300 is not (above).
        inside = dict(pr(is_open=False, closed=5), close_events=[{"action": "closed", "by": dict(WRITER),
                                                                  "at": "2026-10-11T12:09:59Z"}])
        self.assertNotEqual(derive(facts(linked=[inside]))["reason"], "linked_unreadable")
        # A merged one closed and reopened before its merge, then merged, is read (trials/P-48.json's pull request).
        reopened = pr(is_open=False, merged=5, closes=[("closed", 2), ("reopened", 3), ("closed", 5)])
        self.assertNotEqual(derive(facts(linked=[reopened]))["reason"], "linked_unreadable")
        # With no limit that can be read, only a close in closed_at's own second is read.
        for bad in (None, 0, "300"):
            cfg = config()
            if bad is None:
                del cfg["limits"]["max_close_lag_seconds"]
            else:
                cfg["limits"]["max_close_lag_seconds"] = bad
            self.assertEqual(derive(facts(linked=[trailing]), cfg=cfg)["reason"], "linked_unreadable", bad)
            self.assertNotEqual(derive(facts(linked=[pr(is_open=False, closed=5)]), cfg=cfg)["reason"], "linked_unreadable", bad)
        # One pull request listed twice, which would be two links (issue 551).
        self.assertEqual(derive(facts(linked=[pr(), pr()]))["reason"], "linked_unreadable")
        # The other side: the first number, closed unmerged, merged, and a stranger's pull request are read.
        self.assertEqual(state(facts(linked=[pr(number=1)])), "in_review")
        self.assertEqual(state(facts(linked=[pr(is_open=False, closed=5)])), "new")
        self.assertEqual(state(facts(linked=[pr(is_open=False, merged=5)])), "done")
        self.assertEqual(state(facts(linked=[strangers()])), "new")
        # A keyword first seen in its opening second is read; one taken out, once seen, is listed for that (issue 552).
        self.assertEqual(state(facts(linked=[pr(opened=2, spans=[(2, None)])])), "in_review")
        # Put back since the last pass that saw it taken out: read, its new span not begun yet (issue 552).
        self.assertEqual(state(facts(linked=[pr(spans=[(1, 3)])])), "in_review")
        self.assertEqual(derive(facts(linked=[pr(keyword=False, spans=[(2, None)])]))["reason"], "acceptance_due")
        # Listed for a link by hand alone, or for the close it made, a keyword taken out that no pass saw (issue 552).
        self.assertEqual(state(facts(linked=[pr(keyword=False, links=[("connected", 1)])])), "in_review")
        closer = agents(is_open=False, merged=5, keyword=False)
        self.assertEqual(state(facts(state="closed", closed_first_at=at(5), linked=[closer])), "done")
        self.assertEqual(derive(facts(linked=[pr(keyword=False, spans=[(1, 2)])]))["reason"], "acceptance_due")
        # A span seen gone in the second it was first seen is read (issue 552).
        self.assertEqual(derive(facts(linked=[pr(keyword=False, spans=[(2, 2)])]))["reason"], "acceptance_due")
        # A link by hand in its opening second, unlinked and linked again in one second, is read (issue 551).
        both = pr(links=[("connected", 0), ("disconnected", 3), ("connected", 3)])
        self.assertEqual(state(facts(linked=[both])), "in_review")

    def test_an_issues_type_changes_are_read_whole_or_defer(self):  # issue 551
        # Each change of the type, the type before and after with its time, each from the last, the last the type now.
        task, bug = {"from": None, "to": "Task", "at": at(2)}, {"from": "Task", "to": "Bug", "at": at(3)}
        for over in ({"type_events": None}, {"type_events": ["Task"]}, {"type": "Task", "type_events": [dict(task, at="soon")]},
                     {"type": "Task", "type_events": [{"to": "Task", "at": at(2)}]},
                     {"type": "Task", "type_events": [dict(task, to="")]},
                     {"type": "Bug", "type_events": [dict(bug, at=at(1)), task]},
                     {"type": "Bug", "type_events": [task, dict(bug, **{"from": "Feature"})]},
                     {"type": "Bug", "type_events": [task]}, {"type": None, "type_events": [task]},
                     {"type": "Task", "type_events": [dict(task, **{"from": 5})]},
                     {"type": "Bug", "type_events": [dict(task, at=at(3)), dict(bug, at=at(2))]},
                     {"type": "Task", "type_events": [task, dict(task, **{"from": "Task", "at": at(2)})]}):
            d = derive(facts(**over))
            self.assertEqual((d["state"], d["reason"]), (None, "type_unreadable"), over)
        # The other side: none with no type, the chain to the type now, and a removal that leaves none.
        for over in ({}, {"type": "Bug", "type_events": [task, bug]},
                     {"type": None, "type_events": [task, {"from": "Task", "to": None, "at": at(3)}]}):
            self.assertEqual(derive(facts(**over))["reason"], "acceptance_due", over)

    def test_draft_events_in_the_opening_second_and_after_the_close_are_read(self):  # issue 554
        # Opened as a draft and marked ready in that second: a chronology, read whole. One after the close is read too:
        # no trial says GitHub refuses it, and refusing it would let a closed pull request's author stall the issue.
        for linked, expected in ((pr(drafts=(("ready_for_review", 0),)), ("in_review", "linked_ready")),
                                 (pr(is_open=False, closed=5, draft=True,
                                     drafts=(("ready_for_review", 2), ("converted_to_draft", 6))), ("new", "acceptance_due"))):
            d = derive(facts(linked=[linked]))
            self.assertEqual((d["state"], d["reason"]), expected, linked)

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
        # The Decision defers, open or closed, and its reason is an issue's own (decision 0248).
        closed = facts(state="closed")
        del closed["author"]
        for f in (f, closed):
            self.assertEqual(what(decide(f)), ("defer", "author_unreadable", None))
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
                self.assertEqual(what(decide(f)), ("defer", "content_unreadable", None), over)

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
        closed = facts(state="closed")
        del closed["type"]
        for f in (f, closed):
            self.assertEqual(what(decide(f)), ("defer", "type_unreadable", None))
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
        # Whatever else holds but a State only a person ends that the facts place at the merge (issue 522): an
        # outsider's issue nobody accepted, factory:ready standing, two more pull requests open, whose link carries no
        # time (issue 542).
        for f in (outsiders(linked=merged), facts(label_events=[labelled(READY)], linked=merged),
                  facts(linked=merged + [pr(12), pr(13)])):
            self.assertEqual(state(f), "done")

    def test_a_platform_close_keeps_the_state_a_person_set(self):  # issue 522
        # The queue's merge closes an issue whatever its State: an outsider's late keyword can name one the Controller
        # does not watch (trials/P-48.json), and the Factory leaves a queued item to merge under a person's hands-off.
        # From not served and held, which only a person ends, the close is no person's: the State stays, where the
        # facts place it at the merge.
        merges = [pr(is_open=False, merged=5), agents(is_open=False, merged=5),
                  strangers(admitted=True, is_open=False, merged=5)]
        # A person's hands-off that stood on the issue at the merge, placed in its second too, with a Hold beside it or
        # not, stays until a person removes it; an App's removal ends nothing.
        for merged in merges:
            for events in ([labelled(HANDS_OFF, minute=4)], [labelled(HANDS_OFF, minute=5)],
                           [labelled(HOLD, minute=3), labelled(HANDS_OFF, minute=4)],
                           [labelled(HANDS_OFF, minute=4), unlabelled(HANDS_OFF, OTHER_APP, 6)]):
                f = facts(label_events=events, linked=[merged])
                d = derive(f)
                self.assertEqual((d["state"], d["reason"], d["evidence"]),
                                 ("not_served", "merged_while_hands_off", [str(merged["number"])]), (merged, events))
                d = decide(f)
                self.assertEqual((what(d), d["attention"]), (("nothing", "merged_while_hands_off", None), "needs_you"))
        # A person's removal since ends it, and the merge reads on: done, with a Hold beside the hands-off too, as the
        # Factory leaves a queued item to merge under it; an outsider's merge asks a person as before.
        for events in ([labelled(HANDS_OFF, minute=4), unlabelled(HANDS_OFF, minute=6)],
                       [labelled(HOLD, OTHER_APP, 3), labelled(HANDS_OFF, minute=4), unlabelled(HANDS_OFF, minute=6)]):
            self.assertEqual(derive(facts(label_events=events, linked=merges[:1]))["reason"], "merged", events)
            self.assertEqual(derive(facts(label_events=events, linked=merges[2:]))["reason"], "closed_by_outsider_merge")
        # A Hold or a person's hands-off on a ready linked pull request is not the issue's, as in rows 3 and 4: on the
        # merged one it is done.
        for events in ([labelled(HOLD, minute=4)], [labelled(HANDS_OFF, minute=4)]):
            self.assertEqual(derive(facts(linked=[pr(is_open=False, merged=5, events=events)]))["reason"], "merged", events)
        # Hands-off placed after the merge, lifted before it, or placed and removed by a person in one second, which
        # binds as a Hold, does not keep the issue not served.
        self.assertEqual(derive(facts(label_events=[labelled(HANDS_OFF, minute=6)], linked=merges[:1]))["reason"],
                         "merged")
        self.assertEqual(derive(facts(label_events=[labelled(HANDS_OFF, minute=2), unlabelled(HANDS_OFF, minute=4)],
                                      linked=merges[:1]))["reason"], "merged")
        self.assertEqual(derive(facts(label_events=[labelled(HANDS_OFF, minute=4), unlabelled(HANDS_OFF, minute=4)],
                                      linked=merges[:1]))["reason"], "merged_while_held")
        # The Consumer entry is not read: with issues turned off, or the issue's life begun before the entry's date, a
        # person's hands-off at the merge still asks a person, and so does a Hold.
        for cfg in (config(served_from=None), config(served_from=at(1))):
            d = decide(facts(label_events=[labelled(HANDS_OFF, minute=4)], linked=merges[:1]), cfg=cfg)
            self.assertEqual((d["state"], what(d), d["attention"]),
                             ("not_served", ("nothing", "merged_while_hands_off", None), "needs_you"))
            d = decide(facts(label_events=[labelled(HOLD, minute=4)], linked=merges[:1]), cfg=cfg)
            self.assertEqual((d["state"], what(d), d["attention"]), ("held", ("hold", "merged_while_held", None),
                                                                     "needs_you"))
        # Row 3 before row 4, as everywhere: a person's hands-off before a Hold; a person's close before the merge is
        # read first of all.
        both = dict(label_events=[labelled(HOLD, minute=3), labelled(HANDS_OFF, minute=4)])
        self.assertEqual(derive(facts(linked=merges[:1], **both))["reason"], "merged_while_hands_off")
        d = derive(facts(state="closed", closed_first_at=at(4), linked=merges[:1], **both))
        self.assertEqual(d["reason"], "merged_while_declined")

    def test_a_done_issue_stays_done_whatever_changes_after_the_merge_that_carries_no_time(self):  # issue 522
        # No terminal State is left by a fact with no time: a link made after the merge, a left-out label or type set
        # after it and the Consumer entry, whose configuration has no history, are read as they stand now, so row 1
        # does not read them at the merge (issues 551 and 552), nor a linked draft's labels (decision 0141). Issues
        # turned off, or the entry's date moved past the life's start: done, and an admitted outsider's merge still asks
        # a person, as decision 0132 reads it.
        merged = pr(is_open=False, merged=5)
        closed = dict(state="closed", closed_first_at=at(5))
        for cfg in (config(served_from=None), config(served_from=at(1))):
            for own in (merged, agents(is_open=False, merged=5)):
                d = derive(facts(linked=[own], **closed), cfg=cfg)
                self.assertEqual((d["state"], d["reason"], d["evidence"]), ("done", "merged", ["11"]), cfg)
            f = facts(linked=[strangers(admitted=True, is_open=False, merged=5)], **closed)
            d = decide(f, cfg=cfg)
            self.assertEqual((d["state"], what(d), d["attention"]),
                             ("declined", ("nothing", "closed_by_outsider_merge", None), "needs_you"))
        # A pull request opened before the merge and linked since, ready or a draft, a person's hands-off on a ready
        # one, a left-out label or the type: done.
        for f in (facts(linked=[merged, pr(12, opened=3)]),
                  facts(linked=[merged, strangers(number=12, admitted=True, opened=3)]),
                  facts(linked=[merged, pr(12, opened=3, draft=True)]),
                  facts(linked=[merged, pr(12, events=[labelled(HANDS_OFF, minute=4)])]),
                  facts(label_names=["epic"], linked=[merged]),
                  facts(type="Epic", linked=[merged])):
            d = derive(dict(f, state="closed", closed_first_at=at(5)))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("done", "merged", ["11"]), f)

    def test_a_linked_drafts_labels_leave_a_done_issue_done(self):  # issue 542, decision 0141, trials/P-33.json
        # When a pull request became linked carries no time: one opened before the merge may have been named by a keyword
        # an edit added after it. So row 1 places neither a Hold nor a person's hands-off on a linked draft at the merge,
        # whatever its flag was then, and no fact with no time moves a terminal State, in either direction (ruling A).
        merged = pr(is_open=False, merged=5)
        hands = [labelled(HANDS_OFF, minute=4)]
        hold = [labelled(HOLD, OTHER_APP, 4)]
        for draft, drafts in ((True, ()), (False, (("ready_for_review", 6),)), (True, (("converted_to_draft", 6),)),
                              (False, (("ready_for_review", 3),)), (True, (("converted_to_draft", 5),))):
            for events in (hands, hold):
                linked = agents(number=12, draft=draft, drafts=drafts, events=events)
                d = derive(facts(linked=[merged, linked]))
                self.assertEqual((d["state"], d["reason"]), ("done", "merged"), (drafts, events))
        # The reads' two cases: a draft opened before the merge with a person's hands-off, named by a later edit; and a
        # draft with an App's Hold, marked ready after the merge. Each stays done; so does one with several changes of its
        # flag after the merge, one of the Factory's ready throughout, and a draft opened after the merge (issue 554).
        for linked in (agents(number=12, draft=True, opened=3, events=hands),
                       agents(number=12, draft=False, opened=3, drafts=(("ready_for_review", 7),), events=hold),
                       agents(number=12, draft=True, drafts=(("ready_for_review", 6), ("converted_to_draft", 7),
                                                             ("ready_for_review", 8), ("converted_to_draft", 9)), events=hands),
                       agents(number=12, draft=False, events=hands), agents(number=12, draft=False, events=hold),
                       agents(number=12, draft=True, opened=6, events=[labelled(HANDS_OFF, minute=6)]),
                       agents(number=12, draft=True, opened=6, events=[labelled(HOLD, OTHER_APP, 6)])):
            d = derive(facts(linked=[merged, linked]))
            self.assertEqual((d["state"], d["reason"]), ("done", "merged"), linked)
        # The facts still read whole or defer: a conversion and a marking ready in one second, in the timeline's order,
        # whoever made them, are read, never a stall; a flag that disagrees with its last event, two of one kind in a
        # row, or a time out of order is no chronology, and nothing is read.
        for draft, drafts in ((False, (("converted_to_draft", 3), ("ready_for_review", 3))),
                              (True, (("ready_for_review", 3), ("converted_to_draft", 3)))):
            self.assertEqual(derive(facts(linked=[merged, agents(number=12, draft=draft, drafts=drafts)]))["reason"],
                             "merged")
            self.assertNotEqual(derive(facts(linked=[strangers(number=12, draft=draft, drafts=drafts)]))["state"], None)
        for draft, drafts in ((False, (("converted_to_draft", 3),)), (True, (("ready_for_review", 3),)),
                              (True, (("converted_to_draft", 2), ("converted_to_draft", 3))),
                              (True, (("converted_to_draft", 3), ("ready_for_review", 2), ("converted_to_draft", 4)))):
            d = derive(facts(linked=[merged, agents(number=12, draft=draft, drafts=drafts)]))
            self.assertEqual((d["state"], d["reason"]), (None, "linked_unreadable"), drafts)

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
        # A Hold, whoever placed it, and hands-off anyone but a person placed, on the issue, placed before the merge or in
        # its second (seed 20); a person's close read first, where both stand.
        held = [[labelled(HOLD, minute=4)], [labelled(HOLD, OTHER_APP, 5)], [labelled(HANDS_OFF, OTHER_APP, 4)]]
        for f in [facts(label_events=events, linked=merged) for events in held]:
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
        # Nor does a person's hands-off on a linked draft, placed after the merge or before it: its link carries no time,
        # so it excuses the issue's Hold no more than it holds the issue (decision 0141).
        for minute in (6, 4):
            d = derive(facts(label_events=[labelled(HOLD, minute=4)],
                             linked=merged + [agents(number=12, draft=True, events=[labelled(HANDS_OFF, minute=minute)])]))
            self.assertEqual((d["state"], d["reason"]), ("held", "merged_while_held"), minute)
        # A Hold on a linked draft is not the issue's at the merge, open, closed since or before it: when it became linked
        # carries no time (decision 0141). A Hold an App placed before the merge, took off after it and a person put
        # back, which an App's removal never ended.
        for closed in (6, 5, 4):
            d = derive(facts(linked=merged + [agents(number=12, draft=True, is_open=False, closed=closed,
                                                     events=[labelled(HOLD, OTHER_APP, 3)])]))
            self.assertEqual((d["state"], d["reason"]), ("done", "merged"), closed)
        d = derive(facts(label_events=[labelled(HOLD, OTHER_APP, 4), unlabelled(HOLD, OTHER_APP, 6), labelled(HOLD, minute=6)],
                         linked=merged))
        self.assertEqual((d["state"], d["reason"]), ("held", "merged_while_held"))
        # A Hold a person released after the merge and placed again later is a Hold of its own: the merge stays done.
        self.assertEqual(derive(facts(label_events=[labelled(HOLD, minute=4), unlabelled(HOLD, minute=6),
                                                    labelled(HOLD, minute=7)], linked=merged))["reason"], "merged")
        self.assertEqual(derive(facts(label_events=[labelled(HOLD, minute=4), unlabelled(HOLD, minute=6),
                                                    labelled(HOLD, OTHER_APP, 7)], linked=merged))["reason"], "merged")
        # A Hold a person placed and removed in the merge's own second stood at it: the reading that stops work wins.
        self.assertEqual(derive(facts(label_events=[labelled(HOLD, minute=5), unlabelled(HOLD, minute=5)],
                                      linked=merged))["reason"], "merged_while_held")
        # A label the Kernel does not read carries no time, and an event of it beside a Hold raises nothing.
        d = derive(facts(label_events=[{"label": "bug"}, labelled(HOLD, minute=4)], linked=merged))
        self.assertEqual((d["state"], d["reason"]), ("held", "merged_while_held"))
        # A person's hands-off placed in the merge's own second stood at the merge: it stays (issue 522).
        self.assertEqual(derive(facts(label_events=[labelled(HOLD, minute=3), labelled(HANDS_OFF, minute=5)],
                                      linked=merged))["reason"], "merged_while_hands_off")
        # The first merge in the life is the one each stop is read against: a Hold between two merges touches neither.
        two = [pr(is_open=False, merged=5), pr(number=12, is_open=False, merged=9)]
        self.assertEqual(derive(facts(label_events=[labelled(HOLD, minute=7)], linked=two))["reason"], "merged")
        self.assertEqual(derive(facts(label_events=[labelled(HOLD, minute=4)], linked=two))["reason"], "merged_while_held")
        # The other side. The merge's own close, in its second or after it; a Hold placed after the merge, which does
        # not touch what the merge did; a Hold a person released; an outsider's reopening of a done issue, after the
        # merge; a writer's reopening, which begins a life; a person's hands-off since removed by a person, under
        # which the Factory left a queued item to merge, with a Hold beside it; and the ordinary course.
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
                       (facts(linked=merged), None)):
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

    def test_an_outsiders_merge_never_makes_an_issue_done(self):  # issue 280, trials/P-48.json
        # P-48: an outsider's pull request, admitted and approved, gained a closing keyword after the approval, and
        # the queue's merge closed that issue with the pull request named the closer. The closer, its timeline and its
        # time cannot tell a late keyword from one that was there, so an outsider's merge never makes an issue done: a
        # person decides, whatever the references said and when.
        outsider = strangers(admitted=True, is_open=False, merged=5)
        closed = dict(state="closed", closed_first_at=at(5))
        d = derive(facts(linked=[outsider], **closed))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("declined", "closed_by_outsider_merge", ["11"]))
        d = decide(facts(linked=[outsider], **closed))
        self.assertEqual((d["state"], what(d), d["attention"]), ("declined", ("nothing", "closed_by_outsider_merge", None),
                                                                 "needs_you"))
        # The Factory's own merge, or a person's, beside it in the same second still makes the issue done, and is done's
        # evidence alone.
        for own in (agents(number=12, is_open=False, merged=5), pr(number=12, is_open=False, merged=5)):
            d = derive(facts(linked=[outsider, own], **closed))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("done", "merged", ["12"]), own)
        # Only the outsider's merge closed it: a person's merge later, or in its second closing nothing, changes
        # nothing, and is no evidence.
        for other in (pr(number=12, is_open=False, merged=7, closed_issue=None),
                      pr(number=12, is_open=False, merged=5, closed_issue=None)):
            d = derive(facts(linked=[outsider, other], **closed))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("declined", "closed_by_outsider_merge", ["11"]), other)
        # A person's close or Hold before the outsider's merge is read first, as for any merge (issue 227).
        d = derive(facts(linked=[outsider], state="closed", closed_first_at=at(3)))
        self.assertEqual((d["state"], d["reason"]), ("declined", "merged_while_declined"))
        d = derive(facts(label_events=[labelled(HOLD, minute=1)], linked=[outsider], **closed))
        self.assertEqual((d["state"], d["reason"]), ("held", "merged_while_held"))
        # An outsider's merge before this life, an empty one, or one that closed nothing reads as it did before.
        self.assertEqual(state(facts(life_started_at=at(6), reopened_last_by="writer", reopened_last_at=at(6),
                                     linked=[outsider])), "new")
        self.assertEqual(derive(facts(linked=[dict(outsider, empty=True)], **closed))["reason"], "closed")
        self.assertEqual(derive(facts(linked=[dict(outsider, closed_issue_at=None)], **closed))["reason"],
                         "merged_while_declined")

    def test_two_links_by_hand_before_the_merge_leave_the_issue_held(self):  # issue 551, decision 0132
        # Two pull requests linked by hand before the first merge's second, neither closed before it, were two links at
        # it: the issue stood held, and the merge leaves it held, whichever was linked first.
        closed = dict(state="closed", closed_first_at=at(5))
        own = agents(number=11, is_open=False, merged=5, links=[("connected", 2)])
        for rival in (pr(number=12, links=[("connected", 3)]), pr(number=12, links=[("connected", 1)]),
                      pr(number=12, is_open=False, closed=5, links=[("connected", 3)]),
                      pr(number=12, links=[("connected", 1), ("disconnected", 2), ("connected", 4)]),
                      # Closed and reopened before the merge, it stood open at it (issue 672).
                      pr(number=12, links=[("connected", 1)], closes=[("closed", 2), ("reopened", 4)]),
                      pr(number=12, links=[("connected", 1)], closes=[("closed", 4), ("reopened", 4)])):
            d = derive(facts(linked=[own, rival], **closed))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("held", "merged_while_held", ["11", "12"]), rival)
        # Two queue merges in one second, each linked by hand before it, leave it held too.
        other = agents(number=12, is_open=False, merged=5, links=[("connected", 3)])
        d = derive(facts(linked=[own, other], **closed))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("held", "merged_while_held", ["11", "12"]))
        # The other side: a rival linked in the merge's second, with no time (a closing keyword's), linked after the
        # merge, unlinked before it, or closed before it, is no second link at it; nor is the merge's own link made in
        # its second. The Factory's merge is done (decision 0132).
        for rival in (pr(number=12, links=[("connected", 5)]), pr(number=12), pr(number=12, links=[("connected", 6)]),
                      pr(number=12, links=[("connected", 3), ("disconnected", 4)]),
                      # Unlinked before the merge and linked again after it: no link at it.
                      pr(number=12, links=[("connected", 3), ("disconnected", 4), ("connected", 7)]),
                      pr(number=12, is_open=False, closed=4, links=[("connected", 3)]),
                      # Closed before the merge and reopened after it, which clears its closed_at: it stood closed at
                      # the merge, so the reopening moves no done issue (issue 672).
                      pr(number=12, links=[("connected", 3)], closes=[("closed", 4), ("reopened", 7)]),
                      # Reopened in the merge's second: no order can be told in it, so it stands as before that second,
                      # closed, as a link made in it does (decision 0132).
                      pr(number=12, links=[("connected", 3)], closes=[("closed", 4), ("reopened", 5)]),
                      pr(number=12, is_open=False, closed=9, links=[("connected", 3)],
                         closes=[("closed", 4), ("reopened", 7), ("closed", 9)])):
            d = derive(facts(linked=[own, rival], **closed))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("done", "merged", ["11"]), rival)
        late = agents(number=11, is_open=False, merged=5, links=[("connected", 5)])
        d = derive(facts(linked=[late, pr(number=12, links=[("connected", 3)])], **closed))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("done", "merged", ["11"]))
        # Each is read as it stood at the merge: an outsider's admitted by then holds it, one admitted after does not, so
        # no admission after the merge moves a done issue.
        admitted = strangers(number=13, events=[labelled(ADMIT, minute=4)], links=[("connected", 3)])
        d = derive(facts(linked=[own, admitted], **closed))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("held", "merged_while_held", ["11", "13"]))
        later = strangers(number=13, events=[labelled(ADMIT, minute=9)], links=[("connected", 3)])
        d = derive(facts(linked=[own, later], **closed))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("done", "merged", ["11"]))
        # A person's hands-off that stood beside them at the merge, removed since, excuses them, as it excuses a Hold.
        excused = dict(closed, label_events=[labelled(HANDS_OFF, minute=4), unlabelled(HANDS_OFF, minute=6)])
        d = derive(facts(linked=[own, pr(number=12, links=[("connected", 3)])], **excused))
        self.assertEqual((d["state"], d["reason"]), ("done", "merged"))
        # An unlinking of the rival after the merge, or in its second, lets the merge read on for good, as a Hold's
        # removal does: linked again since, it holds nothing, so no one moves a done issue back and forth.
        for links, held in (([("connected", 3), ("disconnected", 7)], False), ([("connected", 3), ("disconnected", 5)], False),
                            ([("connected", 3), ("disconnected", 7), ("connected", 8)], False),
                            ([("connected", 3), ("disconnected", 7), ("connected", 8), ("disconnected", 9), ("connected", 10)], False)):
            d = derive(facts(linked=[own, pr(number=12, links=links)], **closed))
            self.assertEqual(d["state"], "held" if held else "done", links)

    def test_a_keyword_link_a_pass_saw_before_the_merge_is_a_link_at_it(self):  # issue 552, decision 0132
        # A closing keyword's link stood at the merge where a pass saw it before the merge's second: two such links, or
        # one beside a link by hand, keep the issue held, and a keyword taken out after the merge, which the port keeps
        # listing, moves nothing.
        closed = dict(state="closed", closed_first_at=at(5))
        own = agents(number=11, is_open=False, merged=5, spans=[(2, None)])
        for rival in (pr(number=12, spans=[(3, None)]), pr(number=12, spans=[(1, None)]), pr(number=12, keyword=False, spans=[(3, None)])):
            d = derive(facts(linked=[own, rival], **closed))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("held", "merged_while_held", ["11", "12"]), rival)
        by_hand = agents(number=11, is_open=False, merged=5, links=[("connected", 2)])
        d = derive(facts(linked=[by_hand, pr(number=12, spans=[(3, None)])], **closed))
        self.assertEqual((d["state"], d["reason"]), ("held", "merged_while_held"))
        # The other side: a keyword first seen after the merge, in its second, or by no pass, reaches back to nothing; an
        # outsider's admitted after the merge is no link at it. The Factory's merge is done (decision 0132).
        for rival in (pr(number=12, spans=[(6, None)]), pr(number=12, spans=[(5, None)]), pr(number=12),
                      strangers(number=13, events=[labelled(ADMIT, minute=9)], spans=[(3, None)])):
            d = derive(facts(linked=[own, rival], **closed))
            self.assertEqual((d["state"], d["reason"]), ("done", "merged"), rival)
        # A rival linked by hand too, unlinked by hand after the merge, still holds by its keyword: a keyword's link cannot
        # be unlinked by hand.
        both = pr(number=12, links=[("connected", 1), ("disconnected", 7)], spans=[(3, None)])
        d = derive(facts(linked=[own, both], **closed))
        self.assertEqual((d["state"], d["reason"]), ("held", "merged_while_held"))
        # A keyword a pass saw taken out before the merge's second was no link at it, as rows 4 to 7 read it; one taken
        # out in that second or after still stood.
        for gone, held in ((2, False), (5, True), (6, True)):
            d = derive(facts(linked=[own, pr(number=12, keyword=False, spans=[(1, gone)])], **closed))
            self.assertEqual(d["state"], "held" if held else "done", gone)
        # A keyword taken out before the merge and put back after it reaches back to nothing: no edit after the merge
        # moves a done issue. Put back before the merge, it stood at it; standing at it, taken out and put back after, it
        # still holds.
        for spans, held in (([(1, 2), (7, None)], False), ([(1, 2), (3, None)], True), ([(1, 2), (3, 4), (6, None)], False),
                            ([(1, 6), (7, None)], True)):
            d = derive(facts(linked=[own, pr(number=12, spans=spans)], **closed))
            self.assertEqual(d["state"], "held" if held else "done", spans)
        # Before any merge, a pull request whose keyword an edit took out and no link by hand holds is no open link.
        d = derive(facts(linked=[agents(number=11), pr(number=12, keyword=False, spans=[(1, None)])]))
        self.assertNotEqual(d["reason"], "linked_twice")
        self.assertEqual(derive(facts(linked=[agents(number=11), pr(number=12, spans=[(1, None)])]))["reason"], "linked_twice")
        # One linked by hand alone, its keyword taken out or never there, is an open link while the link stands.
        hand = pr(number=12, keyword=False, links=[("connected", 1)])
        self.assertEqual(derive(facts(linked=[agents(number=11), hand]))["reason"], "linked_twice")
        undone = pr(number=12, keyword=False, links=[("connected", 1), ("disconnected", 2)])
        self.assertNotEqual(derive(facts(linked=[agents(number=11), undone]))["reason"], "linked_twice")
        # Nor is the merge's own keyword first seen in its second a link before it.
        late = agents(number=11, is_open=False, merged=5, spans=[(5, None)])
        d = derive(facts(linked=[late, pr(number=12, spans=[(3, None)])], **closed))
        self.assertEqual((d["state"], d["reason"]), ("done", "merged"))

    def test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold(self):  # issue 552, ruling (2) (a)
        # Two links stood at the merge, so the issue is held. A person's close of the rival after the merge's second
        # releases it for good, as an unlinking by hand does: reopened since, it holds nothing. Its keyword or its link by
        # hand, either way.
        closed = dict(state="closed", closed_first_at=at(5))
        own = agents(number=11, is_open=False, merged=5, spans=[(2, None)])

        def rival(closes, shut_at=None, **over):
            """The rival, linked before the merge, closed and reopened as `closes` says, by whom, as (action, who, minute or
            time), and closed at its last close's time, or `shut_at`, if that is a close."""
            def when(m):
                return at(m) if isinstance(m, int) else m
            last = closes[-1]
            shut = last[0] == "closed"
            return dict(pr(**dict({"number": 12, "spans": [(3, None)]}, **over)), open=not shut,
                        closed_at=(shut_at or when(last[2])) if shut else None,
                        close_events=[{"action": action, "by": dict(who), "at": when(m)} for action, who, m in closes])

        # GitHub may date a close's event up to max_close_lag_seconds (300 here) after the close, so a close counts only
        # with its event that long after the merge's second: a reopening since, by anyone, moves nothing.
        for released in (rival([("closed", WRITER, 10)]), rival([("closed", WRITER, 12)]),
                         rival([("closed", WRITER, 10), ("reopened", WRITER, 11)]),
                         rival([("closed", WRITER, 10), ("reopened", OUTSIDER, 11)]),
                         rival([("closed", WRITER, 10), ("reopened", AUTHOR_APP, 11)]),
                         rival([("closed", WRITER, 10), ("reopened", WRITER, 11), ("closed", AUTHOR_APP, 12)]),
                         # A person's close after an App's and a reopening still releases it.
                         rival([("closed", AUTHOR_APP, 7), ("reopened", WRITER, 8), ("closed", WRITER, 10)]),
                         rival([("closed", WRITER, 10)], spans=[], links=[("connected", 3)])):
            d = derive(facts(linked=[own, released], **closed))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("done", "merged", ["11"]), released)
        # A person's close releases it for good, so the rival's own merge since, after a reopening, moves nothing back.
        merged_since = rival([("closed", WRITER, 11), ("reopened", WRITER, 12), ("closed", WRITER, 13)], merged=13, closed_issue=None)
        d = derive(facts(linked=[own, merged_since], **closed))
        self.assertEqual((d["state"], d["reason"]), ("done", "merged"))
        # A close in the merge's second whose event is dated the lag after it is no chronology at all: it defers.
        d = derive(facts(linked=[own, rival([("closed", WRITER, 10)], shut_at=at(5))], **closed))
        self.assertEqual((d["state"], d["reason"]), (None, "linked_unreadable"))
        # With no limit that can be read, no close releases it: none can be told from one in the merge's second.
        for bad in (None, 0, "300"):
            cfg = config()
            if bad is None:
                del cfg["limits"]["max_close_lag_seconds"]
            else:
                cfg["limits"]["max_close_lag_seconds"] = bad
            undone = rival([("closed", WRITER, "2026-10-11T12:05:01Z"), ("reopened", WRITER, 6)])
            d = derive(facts(linked=[own, undone], **closed), cfg=cfg)
            self.assertEqual((d["state"], d["reason"]), ("held", "merged_while_held"), bad)
        # The other side: a close by anyone but a person releases nothing, nor does a person's reopening of a close
        # that did not; a close in the merge's second carries no order against it, so it stood, as a close there does;
        # and the rival's own merge after it is no close that releases, nor the first merge's own close.
        for holding in (rival([("closed", AUTHOR_APP, 12)]), rival([("closed", OUTSIDER, 12)]),
                        rival([("closed", MACHINE, 12)]), rival([("closed", CONTROLLER, 12)]),
                        rival([("closed", {"kind": "lens", "name": "pr-review", "can_write": True}, 12)]),
                        rival([("closed", {"kind": "queue", "name": "combsmith-sf-queue[bot]", "can_write": True}, 12)]),
                        # A writer's login with no write access read is no person.
                        rival([("closed", dict(WRITER, can_write=False), 12)]),
                        rival([("closed", AUTHOR_APP, 12), ("reopened", WRITER, 13)]),
                        rival([("closed", WRITER, 5)]),
                        # A close whose event is less than the lag after the merge's second may have been in that
                        # second: dated a second after it (Muse), or later, standing or undone since, it releases nothing.
                        rival([("closed", WRITER, "2026-10-11T12:05:01Z")], shut_at=at(5)),
                        rival([("closed", WRITER, "2026-10-11T12:09:59Z")]),
                        rival([("closed", WRITER, "2026-10-11T12:09:59Z"), ("reopened", WRITER, 11)]),
                        rival([("closed", WRITER, 7), ("reopened", WRITER, 8), ("closed", AUTHOR_APP, 13)]),
                        rival([("closed", WRITER, 11)], merged=11, closed_issue=None),
                        rival([("closed", WRITER, 11)], spans=[], links=[("connected", 3)], merged=11, closed_issue=None)):
            d = derive(facts(linked=[own, holding], **closed))
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("held", "merged_while_held", ["11", "12"]), holding)
        # Two queue merges in one second, each a person's queue merge, still leave it held: each close is in that second.
        other = agents(number=12, is_open=False, merged=5, spans=[(3, None)])
        d = derive(facts(linked=[own, other], **closed))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("held", "merged_while_held", ["11", "12"]))
        # A third link that stood keeps it held when a person closes one rival: fewer than two must stand.
        third = pr(number=13, spans=[(4, None)])
        d = derive(facts(linked=[own, rival([("closed", WRITER, 10)]), third], **closed))
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("held", "merged_while_held", ["11", "13"]))

    def test_an_empty_merge_is_not_done(self):
        self.assertEqual(state(facts(linked=[pr(is_open=False, merged=5, empty=True)])), "new")
        self.assertEqual(state(facts(linked=[pr(is_open=False, merged=5, empty=False)])), "done")

    def test_only_a_linked_merge_is_done(self):
        self.assertEqual(state(facts(linked=[strangers(is_open=False, merged=5)])), "new")
        self.assertEqual(state(facts(linked=[pr(cls="dependency", by=OTHER_APP, is_open=False, merged=5)])), "new")
        self.assertEqual(state(facts(linked=[strangers(admitted=True, is_open=False, merged=5)])), "declined")
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


class Stands(unittest.TestCase):
    """How the issue stands for the pull request the Factory opened for it, from its state and its own labels alone
    (decision 0232)."""

    def stands(self, f, cfg=None):
        given = copy.deepcopy((f, cfg or config()))
        got = issue.stands(*given)
        self.assertEqual(given, copy.deepcopy((f, cfg or config())), "the Kernel changed an argument")
        self.assertIn(got, ("open", "held", "closed", None))
        return got

    def test_an_issue_stands_open_held_or_closed_from_its_state_and_its_own_labels(self):
        self.assertEqual(self.stands(facts()), "open")
        # A Hold binds whoever placed it; hands-off anyone but a person placed is one. A person's hands-off, a Hold
        # beside it too, is no stop. factory:admit stops nothing.
        for by in (WRITER, CONTROLLER, OTHER_APP, OUTSIDER, MACHINE):
            self.assertEqual(self.stands(facts(label_events=[labelled(HOLD, by)])), "held", by)
        for by in (CONTROLLER, OTHER_APP, OUTSIDER, MACHINE):
            self.assertEqual(self.stands(facts(label_events=[labelled(HANDS_OFF, by)])), "held", by)
        for by in (WRITER, COLLEAGUE):
            self.assertEqual(self.stands(facts(label_events=[labelled(HANDS_OFF, by)])), "open", by)
            self.assertEqual(self.stands(facts(label_events=[labelled(HANDS_OFF, by), labelled(HOLD, OTHER_APP, 2)])),
                             "open", by)
        # Removed by a person in the second it was placed, a person's hands-off is read as a Hold.
        self.assertEqual(self.stands(facts(label_events=[labelled(HANDS_OFF), unlabelled(HANDS_OFF, minute=1),
                                                          labelled(HANDS_OFF, OTHER_APP, 1)])), "held")
        self.assertEqual(self.stands(facts(label_events=[labelled(HOLD), unlabelled(HOLD)])), "open")
        self.assertEqual(self.stands(facts(label_events=[labelled(HANDS_OFF, OTHER_APP), unlabelled(HANDS_OFF, COLLEAGUE)])),
                         "open")
        for by in (CONTROLLER, OUTSIDER, MACHINE):
            self.assertEqual(self.stands(facts(label_events=[labelled(HOLD), unlabelled(HOLD, by)])), "held", by)
        self.assertEqual(self.stands(facts(label_events=[labelled(ADMIT)])), "open")
        self.assertEqual(self.stands(facts(label_events=[labelled(TRIAGE, CONTROLLER), labelled(READY, READINESS)])), "open")
        # Closed is GitHub's state alone, whoever closed it, and is read before the labels, which may not be read.
        for over in ({}, {"label_events": [labelled(HOLD)]}, {"label_events": None},
                     {"complete": {"timeline": False, "linked": True, "runs": True}}, {"reopened_last_by": "other"}):
            self.assertEqual(self.stands(facts(**dict({"state": "closed"}, **over))), "closed", over)

    def test_no_row_of_the_issues_own_reading_is_read(self):
        # Not served, an outsider's, linked twice, with linked pull requests or Runs read short: a Hold still holds.
        hold = [labelled(HOLD, CONTROLLER)]
        for f, cfg in ((facts(label_events=hold), config(served_from=None)),
                       (facts(label_events=hold, label_names=["epic"]), None),
                       (outsiders(label_events=hold), None),
                       (facts(label_events=hold, linked=[pr(), pr(number=12)]), None),
                       (facts(label_events=hold, linked="not a list"), None),
                       (facts(label_events=hold, author=None), None),
                       (facts(label_events=hold, complete={"timeline": True, "linked": False, "runs": False}), None)):
            self.assertEqual(self.stands(f, cfg), "held")
        # A Hold on a linked draft is the issue's own reading, not the issue's label: it does not stop this one.
        self.assertEqual(self.stands(facts(linked=[agents(draft=True, events=[labelled(HOLD)])])), "open")

    def test_what_cannot_be_read_gives_none(self):
        for f in (facts(state="Closed"), facts(state=None), facts(state=True), {"label_events": []}, None, [], "open",
                  facts(complete={"timeline": False, "linked": True, "runs": True}),
                  facts(complete={"timeline": 1, "linked": True, "runs": True}), facts(complete=None),
                  facts(label_events=None), facts(label_events=[dict(labelled(HOLD), by=None)]),
                  facts(label_events=[dict(labelled(HOLD), at="noon")]),
                  facts(label_events=[dict(labelled(HOLD), action="added")])):
            self.assertIsNone(self.stands(f), f)
        missing = facts()
        del missing["complete"]
        self.assertIsNone(self.stands(missing))
        # Read short, a person's hands-off is not read either: the part not read could hold its removal and a Hold.
        short = {"timeline": False, "linked": True, "runs": True}
        self.assertIsNone(self.stands(facts(label_events=[labelled(HANDS_OFF)], complete=short)))
        self.assertIsNone(self.stands(facts(label_events=[labelled(HANDS_OFF), dict(labelled(HOLD), by=None)])))


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
        # The queue App is never an issue's App, whatever its name (issue 1033); a Lens's App is read as the Lens.
        for kind, want in (("app", "ready"), ("lens", "ready"), ("queue", "new"), ("human", "new")):
            by = {"kind": kind, "name": "readiness", "can_write": False}
            self.assertEqual(state(facts(label_events=[labelled(READY, by)]), [run(minute=0)], cfg), want, kind)
        cfg = config(label_apps={"factory:triage": "triager", "factory:ready": None})
        for kind, want in (("app", "triage"), ("lens", "triage"), ("queue", "new"), ("human", "new")):
            by = {"kind": kind, "name": "triager", "can_write": False}
            self.assertEqual(state(facts(label_events=[labelled(TRIAGE, by)]), cfg=cfg), want, kind)

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


class RunStarts(unittest.TestCase):
    def test_an_issues_decision_is_the_same_whatever_began_at_its_runs_carry(self):  # issue 836, decision 0231
        # No issue rule reads when a Run's jobs began, `began_at`: each reads `started_at`, which the run list gives with
        # no job asked. So the records port is asked the jobs of no issue's Run (decision 0196), and an issue's State and
        # Decision are the same with no `began_at`, a null one, one before the Run's start and one long after it. So
        # are the brakes' counts of an issue's Runs since a writer acted.
        # With each Intent named, and with none, as the committed configuration has them until the Maintainer turns them on.
        settings = (config(), config(intents={name: None for name in INTENTS}))
        kept = [[], JUDGED, [investigated()], [investigated(), run(minute=6, name="r2")], [opening()], JUDGED + [opening()],
                [failed(INVESTIGATE, 3, "i1")], [investigated(status="in_progress")],
                # At the attempts brake and one short of it: the brakes count the Runs started since a writer acted.
                [failed(INVESTIGATE, 1 + i, "f%d" % i) for i in range(LIMITS["max_attempts"])],
                [failed(INVESTIGATE, 1 + i, "f%d" % i) for i in range(LIMITS["max_attempts"] - 1)]]
        asked = [(f, runs) for _, f, runs, _ in CASES] + [(f, runs) for f in (
            facts(), TRIAGED, facts(label_events=READIED), facts(label_events=READIED_BY_A_PERSON)) for runs in kept]
        differing = 0
        for f, runs in asked:
            for cfg in settings:
                for now in (NOW, at(59), "2027-01-01T00:00:00Z"):
                    plain = (derive(f, runs, cfg), decide(f, runs, cfg=cfg, now=now))
                    for began in ("absent", None, "2026-01-01T00:00:00Z", at(0), at(58), "2026-12-31T00:00:00Z", "reversed"):
                        # "reversed": each Run's jobs began in the reverse order of the Runs' starts, so no rule may
                        # order, count or tie Runs by when their jobs began (Muse).
                        told = [dict(r) if began == "absent" else
                                dict(r, began_at=at(59 - int(r["started_at"][14:16]))) if began == "reversed" else
                                dict(r, began_at=began) for r in runs]
                        self.assertEqual((derive(f, told, cfg), decide(f, told, cfg=cfg, now=now)), plain, (f, runs, began))
                    # The start itself is read: the cases are ones a Run's start decides, or the test would hold nothing.
                    moved = [dict(r, started_at="2026-12-31T00:00:00Z") for r in runs]
                    differing += (derive(f, moved, cfg), decide(f, moved, cfg=cfg, now=now)) != plain
        self.assertGreater(differing, 0)


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

    def test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted(self):  # issue 825
        # Slice 2's S9 (rulings-422, section 3): while the draft the Factory opened for the issue fails its required checks,
        # the issue admits another implementing Run, the author Role's, for that draft; bounded by max_implementing_rounds
        # (decision 0242), every implementing Run that completed counted as a round, and by the Run ceiling. Dormant while
        # no author Role is named.
        named = dict(config(), author_role="dev-lead")
        failing = facts(linked=[agents(draft=True, checks="failing")])
        d = decide(failing, cfg=named)
        self.assertEqual((d["outcome"], d["reason"], d["admit"]), ("admit", "linked_draft", {
            "role": "dev-lead", "intent": issue.IMPLEMENT, "content_id": THIS, "pull_request": 11,
            "branch_head": DRAFT_HEAD["sha"]}))
        # Its checks pending, or passing, or its head's checks not yet listed after a push (trial P-42): nothing.
        for checks in ("pending", "passing"):
            self.assertEqual(what(decide(facts(linked=[agents(draft=True, checks=checks)]), cfg=named)),
                             ("nothing", "linked_draft", None), checks)
        # No author Role named, as config/defaults.json names none today: nothing, whatever its checks.
        self.assertEqual(what(decide(failing, cfg=dict(named, author_role=None))), ("nothing", "linked_draft", None))
        # The draft read is the one the issue is in progress on, not the first pull request linked.
        before = agents(number=9, is_open=False, closed=2, checks="passing")
        d = decide(facts(linked=[before, agents(draft=True, checks="failing")]), cfg=named)
        self.assertEqual((d["outcome"], d["reason"], d["admit"].get("pull_request")), ("admit", "linked_draft", 11))
        # Two open drafts are no one draft to read: the issue is held linked twice, whosever they are, in either order.
        for linked in ([pr(number=9, draft=True), agents(draft=True, checks="failing")],
                       [agents(number=9, draft=True, checks="passing"), agents(draft=True, checks="failing")]):
            for order in (linked, linked[::-1]):
                self.assertEqual(what(decide(facts(linked=order), cfg=named))[:2], ("hold", "linked_twice"))
        # Not the Factory's draft: a person's, or a stranger's, waits for its author.
        for other in (pr(draft=True, checks="failing"), strangers(admitted=True, draft=True, checks="failing")):
            self.assertEqual(what(decide(facts(linked=[other]), cfg=named))[:2], ("nothing", "linked_draft"), other["class"])
        # Nor are its checks read there: a person's or a stranger's draft, or any while no author Role is named, with
        # no checks at all is nothing too, never a deferral.
        bare = lambda q: {k: v for k, v in q.items() if k != "checks"}
        for other, cfg in ((pr(draft=True), named), (strangers(admitted=True, draft=True), named),
                           (bare(agents(draft=True)), dict(named, author_role=None))):
            self.assertEqual(what(decide(facts(linked=[other]), cfg=cfg))[:2], ("nothing", "linked_draft"), other["class"])
        # Its checks unreadable, where the rule would read them: a deferral, never a Run.
        for unread in ({}, {"checks": None}, {"checks": "red"}):
            draft = dict(bare(agents(draft=True)), **unread)
            self.assertEqual(what(decide(facts(linked=[draft]), cfg=named)), ("defer", "draft_checks_unreadable", None),
                             unread)
        # One implementing Run in flight: nothing more, the issue working.
        flying = run(intent=issue.IMPLEMENT, status="in_progress", role="dev-lead", name="m1", minute=7)
        d = decide(failing, [flying], cfg=named)
        self.assertEqual((what(d), d["attention"]), (("nothing", "linked_draft", None), "working"))
        # So with its checks pending, or unreadable, behind a Run in flight: the issue working, no deferral and no Hold.
        for draft in (agents(draft=True, checks="pending"), dict(agents(draft=True), checks=None)):
            d = decide(facts(linked=[draft]), [flying], cfg=named)
            self.assertEqual((what(d), d["attention"]), (("nothing", "linked_draft", None), "working"), draft["checks"])
        # max_implementing_rounds implementing Runs completed, each of which left the checks failing: held, the issue
        # calls a person.
        rounds = [run(intent=issue.IMPLEMENT, role="dev-lead", name="m%d" % n, minute=7 + n)
                  for n in range(LIMITS["max_implementing_rounds"])]
        self.assertEqual(what(decide(failing, rounds[:-1], cfg=named)), ("admit", "linked_draft", issue.IMPLEMENT))
        held = ("held", "hold", "attempts_exhausted", "needs_you", [r["run"] for r in rounds])
        d = decide(failing, rounds, cfg=named)
        self.assertEqual((d["state"], d["outcome"], d["reason"], d["attention"], d["evidence"]), held)
        # The rounds are spent only on a draft whose checks fail: pending or passing, its rounds spent are nothing.
        for checks in ("pending", "passing"):
            self.assertEqual(what(decide(facts(linked=[agents(draft=True, checks=checks)]), rounds, cfg=named)),
                             ("nothing", "linked_draft", None), checks)
        # A Run of another Intent that completed is no round: one short of the rounds beside it still admits, and at the
        # rounds it is not named among them.
        judged = run(intent="judge-readiness", name="j1", minute=6)
        self.assertEqual(what(decide(failing, [judged] + rounds[:-1], cfg=named)), ("admit", "linked_draft", issue.IMPLEMENT))
        d = decide(failing, [judged] + rounds, cfg=named)
        self.assertEqual((d["state"], d["outcome"], d["reason"], d["attention"], d["evidence"]), held)
        # Past the bound too, as where the limit was lowered, with the Run ceiling not yet spent.
        past = rounds + [run(intent=issue.IMPLEMENT, role="dev-lead", name="mx", minute=7 + len(rounds))]
        self.assertLess(len(past), LIMITS["max_runs_per_item"])
        self.assertEqual(what(decide(failing, past, cfg=named))[:2], ("hold", "attempts_exhausted"))
        # With another Run in flight, of any Intent, the spent rounds still hold, as every brake does (decision 0003);
        # the implementing Run in flight is no round until it completes.
        other = run(intent="judge-readiness", status="in_progress", name="j0", minute=30)
        d = decide(failing, rounds + [other], cfg=named)
        self.assertEqual((d["state"], d["outcome"], d["reason"], d["attention"], d["evidence"]), held)
        d = decide(failing, rounds[:-1] + [flying], cfg=named)
        self.assertEqual((what(d), d["attention"]), (("nothing", "linked_draft", None), "working"))
        # A writer's action renews the rounds, as it renews every count.
        renewed = dict(failing, last_writer_action_at=at(7 + LIMITS["max_implementing_rounds"]))
        self.assertEqual(what(decide(renewed, rounds, cfg=named)), ("admit", "linked_draft", issue.IMPLEMENT))
        # The Run ceiling bounds it too, whatever Runs spent it.
        spent = [run(intent="judge-readiness", name="j%d" % n, minute=7 + n) for n in range(LIMITS["max_runs_per_item"])]
        self.assertEqual(what(decide(failing, spent, cfg=named))[:2], ("hold", "run_ceiling"))

    def test_the_implementing_rounds_have_a_limit_of_their_own_read_from_no_other_key(self):  # issue 1038, decision 0242
        # Held at max_implementing_rounds whatever max_attempts is: one short admits; at the bound, attempts_exhausted,
        # the rounds as evidence (decision 0217).
        failing = facts(linked=[agents(draft=True, checks="failing")])

        def rounds(n: int) -> list:
            return [run(intent=issue.IMPLEMENT, role="dev-lead", name="m%d" % i, minute=7 + i) for i in range(n)]

        def named(**limits) -> dict:
            # The Run ceiling is set above every count here, so that no Hold below is the ceiling's.
            c = dict(config(), author_role="dev-lead")
            c["limits"] = dict(c["limits"], max_runs_per_item=20, **limits)
            return c

        for top, attempts in ((2, 5), (4, 1), (1, 3)):
            cfg = named(max_implementing_rounds=top, max_attempts=attempts)
            self.assertEqual(what(decide(failing, rounds(top - 1), cfg=cfg)), ("admit", "linked_draft", issue.IMPLEMENT),
                             (top, attempts))
            d = decide(failing, rounds(top), cfg=cfg)
            self.assertEqual((d["state"], what(d)[:2], d["attention"], d["evidence"]),
                             ("held", ("hold", "attempts_exhausted"), "needs_you", [r["run"] for r in rounds(top)]),
                             (top, attempts))
        # A round is any implementing Run that completed, whatever it concluded: one that failed by the item counts as a
        # round too, below the attempts' bound, and is named among the rounds.
        cfg = named(max_implementing_rounds=2, max_attempts=5)
        mixed = [dict(rounds(1)[0], conclusion="failure", outcome="item"), rounds(2)[1]]
        d = decide(failing, mixed, cfg=cfg)
        self.assertEqual((what(d)[:2], d["evidence"]), (("hold", "attempts_exhausted"), ["m0", "m1"]))
        # So is one that spent no model, its Engine never started, which counts apart from the Run ceiling.
        idle = dict(rounds(1)[0], conclusion="failure", outcome="environment", engine_started=False)
        d = decide(failing, [idle, rounds(2)[1]], cfg=cfg)
        self.assertEqual((what(d)[:2], d["evidence"]), (("hold", "attempts_exhausted"), ["m0", "m1"]))
        # Where both bounds are reached, the rounds' Hold is the one given, naming every round, not the attempts' alone.
        both = [rounds(1)[0], dict(rounds(2)[1], conclusion="failure", outcome="item")]
        d = decide(failing, both, cfg=named(max_implementing_rounds=2, max_attempts=1))
        self.assertEqual((what(d)[:2], d["evidence"]), (("hold", "attempts_exhausted"), ["m0", "m1"]))
        # A key missing, null or no whole number of at least one holds the issue, limits_unreadable, naming no Run, with
        # a Run in flight too: never another key's number, nor a deferral.
        missing = object()
        for bad in (missing, None, 0, -1, True, 3.0, "3", [3]):
            cfg = named()
            if bad is missing:
                del cfg["limits"]["max_implementing_rounds"]
            else:
                cfg["limits"]["max_implementing_rounds"] = bad
            for spent in ([], rounds(1)):
                d = decide(failing, spent, cfg=cfg)
                self.assertEqual((d["state"], what(d), d["attention"], d["evidence"]),
                                 ("held", ("hold", "limits_unreadable", None), "needs_you", []), (bad, spent))
            flying = run(intent=issue.IMPLEMENT, status="in_progress", role="dev-lead", name="m9", minute=30)
            d = decide(failing, [flying], cfg=cfg)
            self.assertEqual((d["state"], what(d), d["attention"], d["evidence"]),
                             ("held", ("hold", "limits_unreadable", None), "needs_you", []), bad)
            # Another Intent's loop never reads the rounds' key, readable or not.
            self.assertEqual(what(decide(TRIAGED, cfg=cfg)), ("admit", "triage", INVESTIGATE), bad)
        # Runs that failed by the item are held at max_attempts, the implementing Run's as every Intent's, never at the
        # lower of the two keys.
        cfg = named(max_implementing_rounds=3, max_attempts=1)
        broke = dict(rounds(1)[0], conclusion="failure", outcome="item")
        self.assertEqual(what(decide(failing, [broke], cfg=cfg))[:2], ("hold", "attempts_exhausted"))
        self.assertEqual(what(decide(failing, rounds(1), cfg=cfg)), ("admit", "linked_draft", issue.IMPLEMENT))
        self.assertEqual(what(decide(TRIAGED, [failed(INVESTIGATE, 1, "f0")], cfg=cfg))[:2], ("hold", "attempts_exhausted"))
        cfg = named(max_implementing_rounds=1, max_attempts=3)
        self.assertEqual(what(decide(TRIAGED, [failed(INVESTIGATE, 1, "f0")], cfg=cfg)), ("admit", "triage", INVESTIGATE))

    def test_no_author_role_is_named_while_the_implementing_rule_is_owed_its_reads(self):  # issue 825, decision 0217
        # The implementing rule is dormant until the author Role is named, and four things are owed before it is: the
        # facts port's read of a draft's checks, the records port's reading of an implementing Run as the issue's, the
        # draft's head in the admission, and the draft held to the issue it was opened for (decision 0217). Naming it is
        # a change to this test, made with them.
        named = json.loads((ROOT / "config" / "defaults.json").read_text())["author_role"]
        self.assertIsNone(named, "decision 0217's four reads are owed before the author Role is named")

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
        stale = facts(label_events=[labelled(READY, OTHER_APP, 1)], acts_since_writer=LIMITS["max_acts_per_item"] - 1)
        self.assertEqual(decide(stale).get("action"), "remove_label")
        self.assertEqual(what(decide(stale, ctx=context(paused=True))), ("defer", "paused", None))
        # A readiness Run that adds factory:ready completes after its apply: until then its label does not count.
        d = decide(facts(label_events=READIED), [run(status="in_progress")])
        self.assertEqual((what(d), d["attention"]), (("nothing", "triage", None), "working"))

    def test_an_uncounted_label_waits_at_the_act_ceiling(self):  # issue 1251
        # Removing a label that does not count stops no work: it is braked as any act. At the act ceiling, past it, or
        # with the count unread, the removal waits, in new, triage and ready alike, and the issue reads as it will once
        # the label is removed: it makes no act, and admits only what it admits then. One act below, it is removed.
        top = LIMITS["max_acts_per_item"]
        analysed = [comment(ANALYST, 3)]
        for state, events, comments, runs in (
                ("new", [labelled(TRIAGE, OTHER_APP, 1)], [], []),
                ("new", [labelled(READY, OTHER_APP, 1)], [], []),
                ("triage", ACCEPTED + [labelled(READY, OTHER_APP, 4)], [], []),
                # The readiness App's own label, once its Run's record is gone: no verdict is asked for again.
                ("triage", ACCEPTED + [labelled(READY, READINESS, 5)], analysed, []),
                # An earlier add, taken off, and another App's after it; and an add that is not the last event.
                ("triage", ACCEPTED + [labelled(READY, READINESS, 5), unlabelled(READY, OTHER_APP, 6),
                                       labelled(READY, OTHER_APP, 7)], analysed, []),
                ("triage", [labelled(READY, OTHER_APP, 1), labelled(TRIAGE, CONTROLLER, 2)], [], []),
                ("ready", READIED_BY_A_PERSON + [labelled(TRIAGE, OTHER_APP, 3)], [], []),
                # The readiness App's verdict, which counts by its Run's record, beside another App's factory:triage:
                # the reading keeps the record.
                ("ready", READIED + [labelled(TRIAGE, OTHER_APP, 7)], [], JUDGED)):
            uncounted = [ev for ev in events if ev["by"] in (OTHER_APP, READINESS) and ev["action"] == "labeled"][-1]
            gone = events + [dict(uncounted, action="unlabeled")]
            for acts, ctx in ((top, context()), (top + 1, context()), (None, context()), (top, context(paused=True)),
                              (None, context(paused=True))):
                d = decide(facts(label_events=events, role_comments=comments, acts_since_writer=acts), runs, ctx=ctx)
                removed = decide(facts(label_events=gone, role_comments=comments, acts_since_writer=acts), runs,
                                 ctx=ctx)
                if ctx["paused"] and acts is None:
                    # Under the Pause the removal is stopped there, whether the count can be read or not.
                    self.assertEqual(what(d), ("defer", "paused", None), state)
                    continue
                self.assertEqual((d["state"], what(d), d.get("admit"), d["attention"]),
                                 (removed["state"], what(removed), removed.get("admit"), removed["attention"]),
                                 (state, acts, ctx))
                self.assertNotEqual(d["outcome"], "act", (state, acts))
                self.assertNotEqual((d.get("admit") or {}).get("intent"), JUDGE, (state, acts))
                self.assertTrue(not ctx["paused"] or d["outcome"] not in ("act", "admit"), (state, acts))
            # Under the Pause alone the removal is stopped there, as any act that stops work, on the label.
            d = decide(facts(label_events=events, role_comments=comments, acts_since_writer=top - 1), runs,
                       ctx=context(paused=True))
            self.assertEqual((what(d), d["evidence"]), (("defer", "paused", None), [uncounted["label"]]), state)
            d = decide(facts(label_events=events, role_comments=comments, acts_since_writer=top - 1), runs)
            self.assertEqual((d["state"], what(d)), (state, ("act", "label_not_counted", "remove_label")))
        # In new the ceiling holds the issue, with the label or without it, past the ceiling and under the Pause.
        for events, acts, ctx in (([labelled(READY, OTHER_APP, 1)], top, context()), ([], top, context()),
                                  ([labelled(TRIAGE, OTHER_APP, 1)], top, context()),
                                  ([labelled(READY, OTHER_APP, 1)], top + 1, context()),
                                  ([labelled(READY, OTHER_APP, 1)], top, context(paused=True))):
            d = decide(facts(label_events=events, acts_since_writer=acts), ctx=ctx)
            self.assertEqual((d["state"], what(d), d["attention"]), ("held", ("hold", "act_ceiling", None), "needs_you"),
                             (events, acts, ctx))
        # In triage the investigation the issue wants is admitted at the ceiling, as without the label; the label's
        # own reading, factory:ready, starts no opening.
        d = decide(facts(label_events=ACCEPTED + [labelled(READY, OTHER_APP, 4)], acts_since_writer=top))
        self.assertEqual((d["state"], what(d)), ("triage", ("admit", "triage", INVESTIGATE)))
        # A removal that stops work still passes the ceiling: unmerged closes past their bound place their Hold.
        closes = closed_links(*range(2, 3 + LIMITS["max_unmerged_closes"]))
        d = decide(facts(label_events=[labelled(READY, OTHER_APP, 1)], acts_since_writer=top, linked=closes))
        self.assertEqual(what(d), ("act", "unmerged_closes", "place_hold"))

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
        for kind, want in (("human", "triage"), ("queue", "triage"), ("lens", "judged"), ("app", "judged")):
            by = {"kind": kind, "name": "readiness", "can_write": True}
            f = facts(label_events=ACCEPTED + [labelled(READY, by, 5), unlabelled(READY, CONTROLLER, 6)])
            self.assertEqual(decide(f, [investigated()], cfg=cfg)["reason"], want, kind)

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
        runs = [failed(INVESTIGATE, 1 + i, "e%d" % i, outcome="capacity") for i in range(ceiling)]
        self.assertEqual(what(decide(TRIAGED, runs[:-1])), ("admit", "triage", INVESTIGATE))
        self.assertEqual(what(decide(TRIAGED, runs)), ("hold", "run_ceiling", None))
        # A person's action renews every count.
        renewed = facts(label_events=ACCEPTED, last_writer_action_at=at(30))
        self.assertEqual(what(decide(renewed, runs)), ("admit", "triage", INVESTIGATE))
        # A Run that spent no model counts toward a bound of its own, beside the ceiling, and is renewed with it (0202).
        apart = LIMITS["max_environment_runs_per_item"]
        outside = [dict(failed(INVESTIGATE, 1 + i, "o%d" % i, outcome="environment"), engine_started=False)
                   for i in range(apart)]
        self.assertEqual(what(decide(TRIAGED, outside[:-1])), ("admit", "triage", INVESTIGATE))
        self.assertEqual(what(decide(TRIAGED, outside)), ("hold", "environment_ceiling", None))
        self.assertEqual(what(decide(TRIAGED, outside[:-1] + runs[:-1])), ("admit", "triage", INVESTIGATE))
        self.assertEqual(what(decide(TRIAGED, outside + runs)), ("hold", "run_ceiling", None))
        self.assertEqual(what(decide(renewed, outside)), ("admit", "triage", INVESTIGATE))

    def test_an_issues_run_that_ended_person_holds_the_issue_and_calls_a_person_and_spends_no_attempt(self):  # issue 838
        # The twin of the pull request's rule: the Role's latest Run ended `person` holds the issue for a person, with that
        # Run as evidence, under a Pause too; ended any other way, the next Run is admitted.
        ended = failed(INVESTIGATE, 2, "p1", outcome="person")
        for ctx in (None, context(paused=True), context(paused=None)):
            d = decide(TRIAGED, [ended], ctx=ctx)
            self.assertEqual((d["state"], what(d), d["attention"], d["evidence"]),
                             ("held", ("hold", "run_needs_person", None), "needs_you", ["p1"]), ctx)
        for kind in ("item", "environment", "capacity", "superseded", None):
            self.assertEqual(what(decide(TRIAGED, [dict(ended, outcome=kind)])), ("admit", "triage", INVESTIGATE), kind)
        # The Role's latest Run alone is read, and a writer's action releases the Hold, as it renews the attempts.
        self.assertEqual(what(decide(TRIAGED, [ended, failed(INVESTIGATE, 3, "i3")])), ("admit", "triage", INVESTIGATE))
        self.assertEqual(decide(TRIAGED, [failed(INVESTIGATE, 1, "i1"), ended])["evidence"], ["p1"])
        renewed = facts(label_events=ACCEPTED, last_writer_action_at=at(2))
        self.assertEqual(what(decide(renewed, [ended])), ("admit", "triage", INVESTIGATE))
        self.assertEqual(what(decide(facts(label_events=ACCEPTED, last_writer_action_at=at(1)), [ended]))[1],
                         "run_needs_person")
        # Another Role's Run that ended `person` holds no Run of this Role.
        self.assertEqual(what(decide(TRIAGED, [failed(JUDGE, 2, "p2", outcome="person", role="readiness")])),
                         ("admit", "triage", INVESTIGATE))
        # The implementing Run's too, read before the rounds' brake: one round, then a Run that ended `person`, at a
        # bound of two rounds, holds for the person, not at the rounds.
        failing = facts(linked=[agents(draft=True, checks="failing")])
        cfg = dict(config(), author_role="dev-lead")
        cfg["limits"] = dict(cfg["limits"], max_implementing_rounds=2)
        round_ = run(intent=issue.IMPLEMENT, role="dev-lead", name="m0", minute=7)
        person = dict(run(intent=issue.IMPLEMENT, role="dev-lead", name="p8", minute=8), conclusion="failure",
                      outcome="person")
        d = decide(failing, [round_, person], cfg=cfg)
        self.assertEqual((d["state"], what(d), d["evidence"]), ("held", ("hold", "run_needs_person", None), ["p8"]))
        d = decide(failing, [round_, dict(person, outcome="item")], cfg=cfg)
        self.assertEqual((what(d)[:2], d["evidence"]), (("hold", "attempts_exhausted"), ["m0", "p8"]))
        # A writer's action after it releases it here too, and a draft whose checks do not fail wants no Run to hold.
        renewed = facts(linked=[agents(draft=True, checks="failing")], last_writer_action_at=at(8))
        self.assertEqual(what(decide(renewed, [round_, person], cfg=cfg)), ("admit", "linked_draft", issue.IMPLEMENT))
        for checks in ("pending", "passing"):
            green = facts(linked=[agents(draft=True, checks=checks)])
            self.assertEqual(what(decide(green, [round_, person], cfg=cfg)), ("nothing", "linked_draft", None), checks)
        # It holds with a Run in flight, as the rounds' brake does: a Run waiting is none of the Role's completed Runs.
        cfg["limits"] = dict(cfg["limits"], max_implementing_rounds=3)
        flying = run(intent=issue.IMPLEMENT, status="in_progress", role="dev-lead", name="m9", minute=9)
        d = decide(failing, [round_, person, flying], cfg=cfg)
        self.assertEqual((what(d), d["evidence"]), (("hold", "run_needs_person", None), ["p8"]))

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
        runs = [failed(INVESTIGATE, 1 + i, "e%d" % i, outcome="capacity") for i in range(ceiling)]
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

    def test_an_issues_hold_is_read_before_an_uncounted_label_is_removed(self):  # issue 1216
        # Another App's factory:triage does not count, and is removed. A Hold the Run wanted would place is read first:
        # the issue stays held for a person, and the label waits for the release, as under a person's Hold.
        uncounted = READIED_BY_A_PERSON + [labelled(TRIAGE, OTHER_APP, 3)]
        tried = [failed(OPEN, minute, "f%d" % minute, role="dev-lead") for minute in (1, 2)]
        for f, runs, why in (
                (facts(label_events=uncounted, branch_head=BRANCH_HEAD, branch_pushed=False), [], "branch_not_pushed"),
                (facts(label_events=uncounted), tried + [failed(OPEN, 3, "f3", role="dev-lead")], "attempts_exhausted"),
                (facts(label_events=uncounted), [failed(OPEN, 2, "p1", outcome="person", role="dev-lead")],
                 "run_needs_person"),
                (facts(label_events=ACCEPTED + [labelled(READY, OTHER_APP, 4)]),
                 [failed(INVESTIGATE, minute, "i%d" % minute) for minute in (1, 2, 3)], "attempts_exhausted")):
            d = decide(f, runs)
            self.assertEqual((d["state"], what(d), d["attention"]), ("held", ("hold", why, None), "needs_you"), why)
        # The Run ceiling too, which a Run that ended for capacity spends, with attempts left.
        one = config()
        one["limits"] = dict(one["limits"], max_runs_per_item=1)
        d = decide(facts(label_events=uncounted), [failed(OPEN, 2, "c1", outcome="capacity", role="dev-lead")], cfg=one)
        self.assertEqual((d["state"], what(d)), ("held", ("hold", "run_ceiling", None)))
        # And the ceiling on Runs that spent no model.
        one["limits"] = dict(config()["limits"], max_environment_runs_per_item=1)
        outside = dict(failed(OPEN, 2, "e1", outcome="environment", role="dev-lead"), engine_started=False)
        d = decide(facts(label_events=uncounted), [outside], cfg=one)
        self.assertEqual((d["state"], what(d)), ("held", ("hold", "environment_ceiling", None)))
        # The other side of each: with no Hold, the label is removed.
        for f, runs, why in (
                (facts(label_events=uncounted, branch_head=BRANCH_HEAD, branch_pushed=True), [], "pushed"),
                (facts(label_events=uncounted), tried, "an attempt left"),
                (facts(label_events=uncounted), [failed(OPEN, 2, "i1", role="dev-lead")], "ended for the item")):
            d = decide(f, runs)
            self.assertEqual((what(d), d["label"]), (("act", "label_not_counted", "remove_label"), TRIAGE), why)

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
        worn = [failed(INVESTIGATE, 1 + i, "e%d" % i, outcome="capacity") for i in range(ceiling)]
        outside = [dict(failed(INVESTIGATE, 1 + i, "o%d" % i, outcome="environment"), engine_started=False)
                   for i in range(LIMITS["max_environment_runs_per_item"])]
        stale = facts(life_started_at=at(5), reopened_last_by="writer", label_events=[labelled(TRIAGE, WRITER, 1)])
        cases = [
            ("human_hold", "needs_you", facts(label_events=[labelled(HOLD)]), [], config()),
            ("linked_twice", "needs_you", facts(linked=[pr(), agents(number=12, draft=True)]), [], config()),
            ("acceptance_lapsed", "needs_you",
             outsiders(content_changed_at=at(9), label_events=[labelled(ADMIT), labelled(TRIAGE, CONTROLLER, 2)]), [],
             config()),
            ("attempts_exhausted", "needs_you", TRIAGED, spent, config()),
            ("run_ceiling", "needs_you", TRIAGED, worn, config()),
            ("environment_ceiling", "needs_you", TRIAGED, outside, config()),
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
                                                                           "content_id": THIS, "branch_head": None,
                                                                           "base_head": BASE}))
        d = decide(facts(label_events=READIED_BY_A_PERSON, branch_head=BRANCH_HEAD))
        self.assertEqual(d["admit"]["branch_head"], BRANCH_HEAD)
        self.assertNotIn("branch_head", decide(TRIAGED)["admit"])

    def test_the_opening_run_of_a_branch_that_does_not_exist_is_admitted_for_the_commit_it_lands_on(self):
        # Where the branch does not exist, the Run reads the default branch's head as the pass read it and its one
        # commit lands on it: the admission names that commit, and no other Run's does.
        d = decide(facts(label_events=READIED_BY_A_PERSON, base_head="c0ffee1000000000000000000000000000000000"))
        self.assertEqual((what(d), d["admit"]["base_head"]), (("admit", "ready", OPEN), "c0ffee1000000000000000000000000000000000"))
        self.assertNotIn("base_head", decide(TRIAGED)["admit"])
        # Unread, it defers: a name that is no text, is empty or is no commit's whole name, or a fact left out. Null
        # is unread too: the default branch always has a head.
        for value in ("", list(BASE), 1, None, [BASE], True, "main", BASE[1:], BASE + "0", BASE.upper(), "g" + BASE[1:],
                      " " * len(BASE)):
            self.assertEqual(what(decide(facts(label_events=READIED_BY_A_PERSON, base_head=value))),
                             ("defer", "base_unreadable", None), value)
        f = facts(label_events=READIED_BY_A_PERSON)
        del f["base_head"]
        self.assertEqual(what(decide(f)), ("defer", "base_unreadable", None))
        # What stops the opening Run for a person to act on is said before an unread base, which a later pass reads.
        unread = dict(label_events=READIED_BY_A_PERSON, base_head=None)
        self.assertEqual(what(decide(facts(**unread), cfg=config(intents=intents(opening=None))))[1], "intent_undeclared")
        self.assertEqual(what(decide(outsiders(label_events=[labelled(ADMIT), labelled(READY, minute=2)], base_head=None)))[1],
                         "no_statement")
        # An unreadable branch head is said first: without it nothing says whether a base is needed.
        self.assertEqual(what(decide(facts(label_events=READIED_BY_A_PERSON, branch_head="", base_head="")))[1], "branch_unreadable")
        # Where the branch exists, an earlier Run's commit stands on it and this Run pushes none: no base is asked
        # for, read or not, and none is carried.
        for f in (facts(label_events=READIED_BY_A_PERSON, branch_head=BRANCH_HEAD),
                  facts(label_events=READIED_BY_A_PERSON, branch_head=BRANCH_HEAD, base_head=None),
                  facts(label_events=READIED_BY_A_PERSON, branch_head=BRANCH_HEAD, base_head=1)):
            d = decide(f)
            self.assertEqual((what(d), d["admit"]["branch_head"], "base_head" in d["admit"]),
                             (("admit", "ready", OPEN), BRANCH_HEAD, False))
        # No other State's Run waits on it.
        self.assertEqual(what(decide(facts(label_events=ACCEPTED, base_head=1)))[2], INVESTIGATE)
        # Nor does an act: an issue no one has triaged yet is accepted whatever the base reads, or with none at all.
        new = facts()
        del new["base_head"]
        for f in (new, facts(base_head=None), facts(base_head=""), facts(base_head=1), facts(base_head="main")):
            self.assertEqual(decide(f).get("action"), "accept", f.get("base_head", "left out"))

    def test_an_unreadable_branch_head_defers_the_opening_run_alone(self):
        # Each as though an earlier opening Run recorded pushing it, or none did: the head itself is what is unread.
        for value in ("", 1, ["9f2c41d"], "9f2c41d", "main", BRANCH_HEAD.upper(), BRANCH_HEAD + "0", BRANCH_HEAD[:-1] + "g"):
            for pushed in (True, False):
                self.assertEqual(what(decide(facts(label_events=READIED_BY_A_PERSON, branch_head=value, branch_pushed=pushed))),
                                 ("defer", "branch_unreadable", None), (value, pushed))
        f = facts(label_events=READIED_BY_A_PERSON)
        del f["branch_head"]
        self.assertEqual(what(decide(f)), ("defer", "branch_unreadable", None))
        self.assertEqual(what(decide(facts(label_events=ACCEPTED, branch_head=1)))[2], INVESTIGATE)

    def test_a_work_branch_head_no_opening_run_pushed_holds_the_issue_for_a_person(self):
        # The Solution Architect's rulings of 2026-11-25: the issues port tells whether the next opening's branch stands
        # at a commit an earlier opening Run of this issue recorded pushing, keyed by that commit's sha. Where it stands
        # at one none recorded, a commit the Factory never wrote, the opening is held, one code, and a person is called;
        # with a Run in flight too. A record missing or past its retention is told as no push, so it holds alike.
        pushed = decide(facts(label_events=READIED_BY_A_PERSON, branch_head=BRANCH_HEAD, branch_pushed=True))
        self.assertEqual((what(pushed), pushed["admit"]["branch_head"]), (("admit", "ready", OPEN), BRANCH_HEAD))
        planted = facts(label_events=READIED_BY_A_PERSON, branch_head=BRANCH_HEAD, branch_pushed=False)
        d = decide(planted)
        self.assertEqual((d["state"], what(d), d["attention"], d["evidence"]),
                         ("held", ("hold", "branch_not_pushed", None), "needs_you", [BRANCH_HEAD]))
        # The port never tells false while an opening Run of the issue is in flight (adapters/applied.py's `landed`), so
        # a false told then is a head that Run did not push either, and holds.
        self.assertEqual(what(decide(planted, [opening()]))[:2], ("hold", "branch_not_pushed"))
        # A branch not told is read first: a push told of it calls no one.
        told = dict(planted["complete"], branch=False)
        self.assertEqual(what(decide(dict(planted, complete=told))), ("defer", "branch_unreadable", None))
        # Not told where the head is a commit: missing, null or no boolean, it defers as a branch not told does.
        missing = object()
        for value in (missing, None, 0, 1, "false", "true", [False]):
            f = facts(label_events=READIED_BY_A_PERSON, branch_head=BRANCH_HEAD, branch_pushed=value)
            if value is missing:
                del f["branch_pushed"]
            self.assertEqual(what(decide(f)), ("defer", "branch_unreadable", None), value)
        # Where no branch stands nothing was pushed to tell: left out or null, the first opening goes at the base; a push
        # told of no branch contradicts it, and defers.
        for value in (missing, None):
            f = facts(label_events=READIED_BY_A_PERSON, branch_pushed=value)
            if value is missing:
                del f["branch_pushed"]
            d = decide(f)
            self.assertEqual((what(d), d["admit"]["base_head"]), (("admit", "ready", OPEN), BASE), value)
        for value in (False, True, "x", 0):
            self.assertEqual(what(decide(facts(label_events=READIED_BY_A_PERSON, branch_pushed=value))),
                             ("defer", "branch_unreadable", None), value)
        # Nothing else on the issue waits on it: its State, its investigation and the acceptance act.
        self.assertEqual(derive(planted)["state"], derive(facts(label_events=READIED_BY_A_PERSON))["state"])
        self.assertEqual(what(decide(dict(planted, label_events=ACCEPTED)))[2], INVESTIGATE)
        self.assertEqual(decide(dict(planted, label_events=[])).get("action"), "accept")

    def test_the_work_branch_is_read_as_a_commit_as_no_branch_or_not_told_and_only_no_branch_carries_a_base(self):
        # Issue 1059, decision 0242: the issues port tells three values apart. A commit admits the opening Run for it, a
        # branch read as not standing admits the first opening at the default branch's head, and a branch not told,
        # `complete.branch` anything but exactly true, defers that admission whatever head the facts hold.
        sha = "9f2c41d07a3be58e1c6d0b4a7e25f3c18d90ab6e"
        d = decide(facts(label_events=READIED_BY_A_PERSON, branch_head=sha))
        self.assertEqual((d["outcome"], d["admit"]["branch_head"], "base_head" in d["admit"]), ("admit", sha, False))
        d = decide(facts(label_events=READIED_BY_A_PERSON))
        self.assertEqual((d["outcome"], d["admit"]["branch_head"], d["admit"]["base_head"]), ("admit", None, BASE))
        told = {"timeline": True, "linked": True, "runs": True}
        missing = object()
        for flag in (False, None, "true", 1, missing):
            for head in (None, sha):
                f = facts(label_events=READIED_BY_A_PERSON, branch_head=head,
                          complete=dict(told) if flag is missing else dict(told, branch=flag))
                self.assertEqual(what(decide(f)), ("defer", "branch_unreadable", None), (flag, head))
                # Nothing else on the issue waits on it: its State, its investigation and the acceptance act.
                self.assertEqual(derive(f)["state"], derive(facts(label_events=READIED_BY_A_PERSON))["state"])
                self.assertEqual(what(decide(dict(f, label_events=ACCEPTED)))[2], INVESTIGATE, (flag, head))
                self.assertEqual(decide(dict(f, label_events=[])).get("action"), "accept", (flag, head))
                # Not told, it is unknown whether a base is wanted: an unread base is not what is said.
                unbased = dict(f)
                del unbased["base_head"]
                self.assertEqual(what(decide(unbased)), ("defer", "branch_unreadable", None), (flag, head))
        # The implementing Run pushes to its own draft (decision 0217): the next opening's branch, told or not, neither
        # defers nor admits it. Its draft's own head is what it is admitted at, and one not told defers it.
        named = dict(config(), author_role="dev-lead")
        failing = facts(linked=[agents(draft=True, checks="failing")])
        d = decide(failing, cfg=named)
        self.assertEqual((d["outcome"], d["admit"]["branch_head"]), ("admit", DRAFT_HEAD["sha"]))
        for flag in (False, None, "true", missing):
            f = dict(failing, complete=dict(told) if flag is missing else dict(told, branch=flag), branch_head=None)
            self.assertEqual(decide(f, cfg=named)["admit"], d["admit"], flag)
        # With the next opening's branch told and standing at another commit, the Run still carries its draft's head.
        other = "b" * 40
        self.assertEqual(decide(dict(failing, branch_head=other), cfg=named)["admit"], d["admit"])
        # A draft whose head is another commit at apply refuses the Run (I-21).
        moved = facts(linked=[agents(draft=True, checks="failing", head=dict(DRAFT_HEAD, sha=other))])
        self.assertFalse(issue.still_admitted(d, decide(moved, cfg=named)))
        self.assertTrue(issue.still_admitted(d, decide(failing, cfg=named)))
        # A later opening's draft, its count of two digits, is admitted at its own head as well.
        later = facts(linked=[agents(draft=True, checks="failing", head=dict(DRAFT_HEAD, ref="factory-work/issue-7-12"))])
        self.assertEqual(decide(later, cfg=named)["admit"]["branch_head"], DRAFT_HEAD["sha"])
        for head in (missing, None, {}, {"sha": sha}, {"ref": DRAFT_HEAD["ref"]}, dict(DRAFT_HEAD, sha=sha[:7]),
                     dict(DRAFT_HEAD, sha=sha.upper()), dict(DRAFT_HEAD, ref=""), dict(DRAFT_HEAD, ref=7), "main",
                     dict(DRAFT_HEAD, ref="main"), dict(DRAFT_HEAD, ref="factory-work/issue-8-1"),
                     dict(DRAFT_HEAD, ref="factory-work/issue-7-01"), dict(DRAFT_HEAD, ref="factory-work/issue-7-"),
                     dict(DRAFT_HEAD, ref="factory-work/issue-07-1"), dict(DRAFT_HEAD, ref="factory-work/issue-7-1-2"),
                     dict(DRAFT_HEAD, ref="factory-work/issue-7-x"), dict(DRAFT_HEAD, ref="factory-wurk/issue-7-1")):
            draft = agents(draft=True, checks="failing")
            if head is missing:
                del draft["head"]
            else:
                draft["head"] = head
            f = facts(linked=[draft])
            self.assertEqual(what(decide(f, cfg=named)), ("defer", "branch_unreadable", None), head)
            # Nothing else waits on it: no author Role, or checks that do not fail, admit nothing either way.
            self.assertEqual(what(decide(f, cfg=dict(named, author_role=None))), ("nothing", "linked_draft", None), head)
            passing = facts(linked=[dict(draft, checks="passing")])
            self.assertEqual(what(decide(passing, cfg=named)), ("nothing", "linked_draft", None), head)

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
        settled = [investigated()] + [failed(JUDGE, 4 + i, "j%d" % i, outcome="capacity", role="readiness")
                                      for i in range(self.CEILING - 1)]
        queued = run(status="queued", minute=21, name="q1")
        ended = dict(queued, status="completed", conclusion="failure", outcome="capacity")
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
        settled = [investigated()] + [failed(JUDGE, 4 + i, "j%d" % i, outcome="capacity", role="readiness")
                                      for i in range(self.CEILING - 1)]
        queued = run(status="queued", minute=40, name="q1")
        ended = dict(queued, status="completed", conclusion="failure", outcome="capacity")
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
        settled = [investigated()] + [failed(JUDGE, 4 + i, "j%d" % i, outcome="capacity", role="readiness")
                                      for i in range(self.CEILING - 1)]
        overruled = facts(label_events=ACCEPTED + [labelled(READY, minute=30), unlabelled(READY, minute=31)])
        self.assertEqual(self.reading(overruled, settled), ("triage", "ready_removed", "nothing", "needs_you"))
        self.assertEqual(self.reading(overruled, settled + [waiting]), ("in_progress", "opening_run", "nothing", "working"))
        # The other side: a verdict still wanted is held at the Run ceiling while the opening Run waits.
        self.assertEqual(self.reading(TRIAGED, settled + [waiting]), ("held", "run_ceiling", "hold", "needs_you"))
        spent = [failed(INVESTIGATE, 1 + i, "e%d" % i, outcome="capacity") for i in range(self.CEILING)]
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
        spent = [failed(INVESTIGATE, 1 + i, "e%d" % i, outcome="capacity") for i in range(self.CEILING)]
        queued = investigated(status="queued", minute=20, name="q1")
        self.assertEqual(self.reading(facts(), spent + [queued]), ("new", "acceptance_due", "nothing", "working"))
        self.assertEqual(what(decide(facts(), spent)), ("act", "acceptance_due", "accept"))

    def test_the_run_ceiling_holds_no_issue_that_wants_no_run(self):
        spent = [failed(INVESTIGATE, 4 + i, "e%d" % i, outcome="capacity") for i in range(self.CEILING)]
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
        f = facts(label_events=READIED_BY_A_PERSON, branch_head=BRANCH_HEAD)
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

    def test_the_default_branch_moving_does_not_stop_the_opening_run_and_a_branch_made_does(self):
        # The Run's one commit lands on the commit it was admitted for, wherever the default branch has gone since:
        # nothing holds the default branch still while a Run is in flight.
        f = facts(label_events=READIED_BY_A_PERSON, base_head="c0ffee1000000000000000000000000000000000")
        admitted = decide(f)
        self.assertEqual(admitted["admit"]["base_head"], "c0ffee1000000000000000000000000000000000")
        self.assertRefused(admitted, f, want=True)
        self.assertRefused(admitted, dict(f, base_head="d00d1e5000000000000000000000000000000000"), want=True)
        # But a default branch that cannot be read is no admission, and nothing is written.
        self.assertRefused(admitted, dict(f, base_head=None))
        # The branch made meanwhile, at any commit, is the head moved; so is everything else that stopped it before.
        self.assertRefused(admitted, dict(f, branch_head="c0ffee1000000000000000000000000000000000", branch_pushed=True))
        self.assertRefused(admitted, dict(f, base_head="d00d1e5000000000000000000000000000000000", content_id=OTHER, content_changed_at=at(7)))
        self.assertRefused(admitted, dict(f, base_head="d00d1e5000000000000000000000000000000000", label_events=f["label_events"] + [labelled(HOLD, OTHER_APP, 7)]))
        # An admission that is no mapping is none, on either side, and never matches itself.
        again = decide(f)
        for broken in ("admit", ["admit"], 1):
            self.assertFalse(issue.still_admitted({"admit": broken}, again))
            self.assertFalse(issue.still_admitted(admitted, {"admit": broken}))
            self.assertFalse(issue.still_admitted({"admit": broken}, {"admit": broken}))
        # The Run's own admission names the base it lands on: one that names none, or no commit's whole name, lands
        # on nothing, and nothing is written.
        own = {part: admitted["admit"][part] for part in admitted["admit"] if part != "base_head"}
        for base in ("main", "c0ffee1", "C0FFEE1000000000000000000000000000000000", None, "c0ffee1" + "0" * 34,
                     "c0ffee1" + "0" * 32, "g" + "0" * 39):
            self.assertFalse(issue.still_admitted({"admit": dict(own, base_head=base)}, again), base)
            # Nor does a second asking whose base cannot be read, or two admissions that share one such base.
            self.assertFalse(issue.still_admitted(admitted, {"admit": dict(own, base_head=base)}), base)
            self.assertFalse(issue.still_admitted({"admit": dict(own, base_head=base)}, {"admit": dict(own, base_head=base)}), base)
        self.assertFalse(issue.still_admitted({"admit": own}, again))
        self.assertFalse(issue.still_admitted(admitted, {"admit": own}))
        # A base stands on both admissions or on neither: an admission of a branch that stands carries none.
        standing = decide(dict(f, branch_head="c0ffee1000000000000000000000000000000000", branch_pushed=True))
        self.assertNotIn("base_head", standing["admit"])
        self.assertTrue(issue.still_admitted(standing, standing))
        for base in ("c0ffee1000000000000000000000000000000000", None):
            self.assertFalse(issue.still_admitted({"admit": dict(standing["admit"], base_head=base)}, standing), base)
        # And the branch head is compared on its own: a branch that stands and moved stops the Run.
        self.assertFalse(issue.still_admitted(standing, decide(dict(f, branch_head="d00d1e5000000000000000000000000000000000",
                                                                     branch_pushed=True))))
        # Only the base is left out: an admission that differs in it AND in a part more is another Run's.
        self.assertFalse(issue.still_admitted(admitted, dict(again, admit=dict(again["admit"], base_head="d00d1e5000000000000000000000000000000000", role="qa-lead"))))
        self.assertFalse(issue.still_admitted(admitted, dict(again, admit=dict(again["admit"], extra=1))))
        moved = dict(again["admit"], base_head="d00d1e5000000000000000000000000000000000")
        self.assertFalse(issue.still_admitted(admitted, {"admit": dict(moved, extra=1)}))
        self.assertFalse(issue.still_admitted({"admit": dict(admitted["admit"], extra=1)}, {"admit": moved}))

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
             dict(WAITING, linked=[dict(agents(is_open=False, closed=0), opened_at=START, closed_at=then, close_events=closes(then))]), [],
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
             dict(WAITING, linked=[dict(dependency, open=False, opened_at=START, closed_at=then, close_events=closes(then))]), [], "triage"),
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
             dict(WAITING, linked=[dict(agents(is_open=False, closed=0), opened_at=START, closed_at=later, close_events=closes(later))]), [],
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
        closed = dict(agents(is_open=False, closed=0), opened_at=minutes_after(then, 1), closed_at=then, close_events=closes(then))
        merged = dict(agents(is_open=False, merged=0), opened_at=minutes_after(then, 1), merged_at=then, closed_at=then, close_events=closes(then),
                      closed_issue_at=then)
        # A merge before the opening, though the close is after it: read, the issue would be done.
        merged_first = dict(merged, closed_at=minutes_after(then, 2), close_events=closes(minutes_after(then, 2)))
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
        cycled = dict(strangers(admitted=True, is_open=False, closed=0), opened_at=START, closed_at=then, close_events=closes(then))
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
