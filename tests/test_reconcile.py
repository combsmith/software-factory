"""Reconciliation (`controller/reconcile.py`): every write a Factory identity made matched to an Effect the Factory
recorded, one alert for any that is not, never silent when what was seen or recorded cannot be read whole (I-33,
decision 0061)."""
from __future__ import annotations

import copy
import json
import unittest

from adapters import seen as seen_
from adapters.github import Unanswered
from controller import reconcile
from controller.shared import SCHEMAS
from tests.support import ROOT, run
from tools.jsonschema_lite import validate

SINCE = "2026-10-11T00:00:00Z"
ITEM = {"repo": "combsmith/software-factory", "type": "pull_request", "number": 42}
OTHER = dict(ITEM, number=43)
URL = "https://github.com/combsmith/software-factory/pull/42"
ACCOUNTS = json.loads((ROOT / "config" / "controller.json").read_text())["accounts"]
KNOWN = dict(ACCOUNTS, controller={"id": 5000001, "type": "Bot", "login": "combsmith-sf-controller[bot]"},
             roles={"pr-review": {"id": 5000002, "type": "Bot", "login": "combsmith-sf-pr-review[bot]"}})
# The pass job's token's account, once it is set: dispatches are reconciled from then on (ruling 2).
TOKEN = dict(KNOWN, workflow_token={"id": 5000003, "type": "Bot"})


def wrote(by, kind, key=None, item=ITEM, at="2026-10-11T12:00:00Z") -> dict:
    return {"by": by, "kind": kind, "item": item, "key": key, "at": at}


def seen(*writes, merged=(), whole=True) -> dict:
    out = {"schema": "seen/1", "since": SINCE, "whole": whole, "writes": list(writes), "merged": list(merged)}
    assert not validate(out, SCHEMAS["seen"], schemas=SCHEMAS), validate(out, SCHEMAS["seen"], schemas=SCHEMAS)
    return out


def applied(*effects) -> dict:
    return {"schema": "applied/1", "run": "r_01JA7Q", "release": "factory/v0.3.1", "findings": [], "rulings": [],
            "effects": [{"id": "e%d" % (i + 1), "type": t, "state": state, "key": k, "reason": None}
                        for i, (t, k, state) in enumerate(effects)]}


def written(*writes) -> dict:
    return {"schema": "written/1", "pass": "p_01JA7Q", "release": "factory/v0.3.1",
            "writes": [{"id": "w%d" % (i + 1), "type": t, "item": item, "run": r, "state": state, "key": k,
                        "reason": None} for i, (t, item, r, k, state) in enumerate(writes)]}


def recorded(applied_=(), written_=(), whole=True) -> dict:
    return {"applied": list(applied_), "written": list(written_), "whole": whole}


def records(*runs) -> list:
    """The run records the pass read, held to their schema."""
    return list(runs)


NOTHING = object()


def check(s, e=NOTHING, r=NOTHING, before=(), accounts=KNOWN) -> dict:
    return reconcile.reconcile(s, recorded() if e is NOTHING else e, records() if r is NOTHING else r, list(before),
                               accounts)


def kinds(found) -> list:
    return [(u["by"], u["kind"]) for u in found["unmatched"]]


class Matching(unittest.TestCase):
    def test_each_write_is_matched_to_the_effect_that_recorded_it(self):  # I-33, ruling 4
        rows = [(wrote("approver", "approval", "PRR_a"), applied(("approve", "PRR_a", "applied"))),
                (wrote("pr-review", "review", "PRR_r"), applied(("submit_review", "PRR_r", "applied"))),
                (wrote("pr-review", "comment", "IC_c"), applied(("comment", "IC_c", "already_applied"))),
                (wrote("pr-review", "check_run", "CR_c"), applied(("create_check_run", "CR_c", "applied")))]
        for write, done in rows:
            found = check(seen(write), recorded([done]))
            self.assertEqual((found["unmatched"], found["short"]), ([], False), write)
            self.assertEqual(reconcile.alerts(found), [])
            # The same write with no Effect, another key, an Effect of another type, or one that did not land, alarms.
            for other in (recorded(), recorded([applied((done["effects"][0]["type"], "X_other", "applied"))]),
                          recorded([applied(("comment" if write["kind"] != "comment" else "submit_review",
                                             write["key"], "applied"))]),
                          recorded([applied((done["effects"][0]["type"], write["key"], "failed"))])):
                found = check(seen(write), other)
                self.assertEqual(kinds(found), [(write["by"], write["kind"])], (write, other))
                self.assertEqual(reconcile.alerts(found), ["write_unmatched"])
            # A write whose key cannot be read is matched to nothing, whatever was recorded on its item.
            self.assertEqual(kinds(check(seen(dict(write, key=None)), recorded([done]))), [(write["by"], write["kind"])])

    def test_a_resolution_is_the_queue_apps_matched_to_the_act_the_pass_recorded(self):  # issue 389
        # No Role resolves a thread: the queue App does, as the Kernel's act, which the pass records as a write. Its
        # resolution is matched to that write by the thread's id; one the pass did not record, recorded on another
        # thread or as not landed, alarms, and so does any Role's, whatever it recorded.
        accounts = dict(KNOWN, queue={"id": 5000009, "type": "Bot", "login": "combsmith-sf-queue[bot]"})
        act = written(("resolve_thread", ITEM, None, "PRRT_t", "applied"))
        self.assertEqual(check(seen(wrote("queue", "resolution", "PRRT_t")), recorded(written_=[act]),
                               accounts=accounts)["unmatched"], [])
        for other in (recorded(), recorded(written_=[written(("resolve_thread", ITEM, None, "PRRT_u", "applied"))]),
                      recorded(written_=[written(("resolve_thread", ITEM, None, "PRRT_t", "failed"))]),
                      recorded(written_=[written(("not_built", ITEM, None, None, "refused"))])):
            found = check(seen(wrote("queue", "resolution", "PRRT_t")), other, accounts=accounts)
            self.assertEqual(kinds(found), [("queue", "resolution")], other)
        found = check(seen(wrote("pr-review", "resolution", "PRRT_t")), recorded(written_=[act]), accounts=accounts)
        self.assertEqual(kinds(found), [("pr-review", "resolution")])
        # Until the queue App's account is set (issue 381) it is no identity, and leaves nothing short; once set, what
        # was seen tells its account as the queue App.
        told = dict(seen_.identities(KNOWN)[0])
        told[(5000009, "Bot")] = "queue"
        self.assertEqual(seen_.identities(accounts), (told, seen_.identities(KNOWN)[1]))
        # A queue account that is another identity's too cannot be told from it: neither is known.
        twice = dict(accounts, queue=dict(accounts["queue"], id=KNOWN["roles"]["pr-review"]["id"]))
        found, known = seen_.identities(twice)
        self.assertEqual(((5000002, "Bot") in found, known), (False, False))
        self.assertEqual(reconcile._identities(KNOWN)[0].get("queue"), None)
        self.assertEqual(reconcile._identities(accounts), (dict(reconcile._identities(KNOWN)[0], queue="queue"), True))

    def test_the_controllers_writes_are_matched_to_what_the_pass_recorded(self):  # decision 0051
        status = written(("status_on_item", ITEM, None, "CR_s", "applied"))
        self.assertEqual(check(seen(wrote("controller", "check_run", "CR_s")), recorded(written_=[status]))["unmatched"],
                         [])
        # A status is matched by its key alone: a check run on the item whose key cannot be read, or another, alarms.
        for other in (None, "CR_t"):
            self.assertEqual(kinds(check(seen(wrote("controller", "check_run", other)), recorded(written_=[status]))),
                             [("controller", "check_run")], other)
        dequeue = written(("dequeue", ITEM, None, "PR_node", "applied"))
        self.assertEqual(check(seen(wrote("controller", "dequeue")), recorded(written_=[dequeue]))["unmatched"], [])
        # A dequeue GitHub gives no key for is matched by its item, one recorded for each: a second alarms.
        twice = seen(wrote("controller", "dequeue"), wrote("controller", "dequeue", at="2026-10-11T12:05:00Z"))
        self.assertEqual(kinds(check(twice, recorded(written_=[dequeue]))), [("controller", "dequeue")])
        self.assertEqual(check(twice, recorded(written_=[dequeue, dequeue]))["unmatched"], [])
        # A status the pass recorded as failed or refused landed nothing the pass can claim: its write is unmatched.
        for state in ("failed", "refused", "superseded"):
            not_landed = written(("status_on_item", ITEM, None, "CR_s", state))
            self.assertEqual(kinds(check(seen(wrote("controller", "check_run", "CR_s")), recorded(written_=[not_landed]))),
                             [("controller", "check_run")], state)
            not_landed = written(("dequeue", ITEM, None, "PR_node", state))
            self.assertEqual(kinds(check(seen(wrote("controller", "dequeue")), recorded(written_=[not_landed]))),
                             [("controller", "dequeue")], state)
        # A dequeue recorded for another item, or of no item; an enqueue or a label, which no write serves yet; a merge,
        # and an act on the timeline no write makes, alarm.
        self.assertEqual(kinds(check(seen(wrote("controller", "dequeue", item=OTHER)), recorded(written_=[dequeue]))),
                         [("controller", "dequeue")])
        self.assertEqual(kinds(check(seen(wrote("controller", "dequeue", item=None)), recorded(written_=[dequeue]))),
                         [("controller", "dequeue")])
        for kind in ("enqueue", "label", "merge", "review", "approval", "close", "dismissal", "force_push"):
            self.assertEqual(kinds(check(seen(wrote("controller", kind)), recorded(written_=[dequeue]))),
                             [("controller", kind)], kind)

    def test_a_write_no_identity_may_make_alarms_whatever_was_recorded(self):  # decision 0005
        # The machine user only approves: a push, a review that is not an approval, a comment or a resolution alarms,
        # and so does a Role's act on the timeline, or a resolution GitHub names a Role for.
        everything = recorded([applied(("approve", "K", "applied"), ("submit_review", "K", "applied"),
                                       ("comment", "K", "applied"))],
                              [written(("resolve_thread", ITEM, None, "K", "applied"))])
        for write in (wrote("approver", "push", "K"), wrote("approver", "review", "K"), wrote("approver", "comment", "K"),
                      wrote("approver", "resolution", "K"), wrote("pr-review", "label"), wrote("pr-review", "merge"),
                      wrote("pr-review", "approval", "K"),
                      wrote("approver", "dismissal"), wrote("approver", "close")):
            self.assertEqual(kinds(check(seen(write), everything)), [(write["by"], write["kind"])], write)

    def test_every_machine_user_approval_with_no_record_alarms_the_maintainers_own_included(self):
        # The Maintainer, 2026-10-22: "Alarm on all of them". An approval by the machine user with no approve Effect
        # alarms on any pull request, his own approval in the browser among them; nothing is read as a person's.
        found = check(seen(wrote("approver", "approval", "PRR_byhand")))
        self.assertEqual((kinds(found), reconcile.alerts(found)), ([("approver", "approval")], ["write_unmatched"]))

    def test_many_unmatched_writes_raise_one_alert_and_each_is_named(self):  # L-48
        writes = [wrote("approver", "approval", "PRR_%d" % i) for i in range(5)] + [wrote("approver", "push", "P1")]
        found = check(seen(*writes))
        self.assertEqual(reconcile.alerts(found), ["write_unmatched"])
        self.assertEqual(len(reconcile.entries(found)), 6)
        self.assertEqual(reconcile.entries(found)[0], {"alert": "write_unmatched", "by": "approver", "write": "approval",
                                                       "item": URL, "key": "PRR_0"})
        # Two writes GitHub gives no key for read the same, and are named once: the view holds each entry once.
        found = check(seen(wrote("controller", "label"), wrote("controller", "label", at="2026-10-11T12:01:00Z")))
        self.assertEqual(len(found["unmatched"]), 2)
        self.assertEqual(reconcile.entries(found), [{"alert": "write_unmatched", "by": "controller", "write": "label",
                                                     "item": URL, "key": None}])

    def test_a_resolution_github_names_no_resolver_for_raises_nothing(self):  # ruling 3
        self.assertEqual(check(seen(wrote("unattributed", "resolution", "PRRT_x")))["unmatched"], [])

    def test_a_dispatch_is_matched_by_its_run_to_the_pass_that_sent_it(self):  # decision 0051
        r = run(name="r_01JA7Q", at="2026-10-11T12:00:00Z")
        sent = written(("dispatch_run", ITEM, "r_01JA7Q", None, "sent"))
        self.assertEqual(check(seen(), recorded(written_=[sent]), records(r), accounts=TOKEN)["unmatched"], [])
        self.assertEqual(kinds(check(seen(), recorded(), records(r), accounts=TOKEN)), [("workflow_token", "dispatch")])
        # A run started at the window's start is in it; one before it is the reconciliation of an earlier pass.
        self.assertEqual(kinds(check(seen(), recorded(), records(run(name="r_01JA7S", at=SINCE)), accounts=TOKEN)),
                         [("workflow_token", "dispatch")])
        old = run(name="r_01JA7R", at="2026-10-10T12:00:00Z")
        self.assertEqual(check(seen(), recorded(), records(old), accounts=TOKEN)["unmatched"], [])
        approving = written(("dispatch_approval", ITEM, "r_01JA7Q", None, "sent"))
        self.assertEqual(check(seen(), recorded(written_=[approving]), records(r), accounts=TOKEN)["unmatched"], [])
        # A queue act's dispatch is matched as an approval's is (issue 381).
        queued = written(("dispatch_queue", ITEM, "r_01JA7Q", None, "sent"))
        self.assertEqual(check(seen(), recorded(written_=[queued]), records(r), accounts=TOKEN)["unmatched"], [])
        # Records that cannot be read match no dispatch: it is unmatched, beside the short reconciliation.
        found = check(seen(), recorded([dict(applied(("approve", "K", "applied")), effects="none")], [sent]), records(r),
                      accounts=TOKEN)
        self.assertEqual(reconcile.alerts(found), ["reconciliation_unreadable", "write_unmatched"])
        refused = written(("dispatch_run", ITEM, "r_01JA7Q", None, "refused"))
        self.assertEqual(kinds(check(seen(), recorded(written_=[refused]), records(r), accounts=TOKEN)),
                         [("workflow_token", "dispatch")])
        # A dispatch is read by when its run was made, which a re-run keeps (decision 0063): a person's re-run of a
        # Run dispatched before the window is no dispatch in it, and a re-run hides no dispatch made in it.
        rerun = dict(r, dispatched_at="2026-10-10T12:00:00Z", started_at="2026-10-11T12:30:00Z", rerun_by_dispatcher=False)
        self.assertEqual(check(seen(), recorded(), records(rerun), accounts=TOKEN)["unmatched"], [])
        hidden = dict(r, dispatched_at=SINCE, started_at="2026-10-11T12:30:00Z", rerun_by_dispatcher=False)
        self.assertEqual(kinds(check(seen(), recorded(), records(hidden), accounts=TOKEN)), [("workflow_token", "dispatch")])
        self.assertEqual(check(seen(), recorded(written_=[sent]), records(hidden), accounts=TOKEN)["unmatched"], [])
        # A re-run the pass job's own token made is a write no Effect records, whatever its dispatch was.
        self.assertEqual(kinds(check(seen(), recorded(written_=[sent]), records(dict(hidden, rerun_by_dispatcher=True)),
                                     accounts=TOKEN)), [("workflow_token", "rerun")])
        self.assertEqual(kinds(check(seen(), recorded(), records(dict(rerun, rerun_by_dispatcher=True)), accounts=TOKEN)),
                         [("workflow_token", "rerun")])
        # A re-run whose re-runner cannot be read cannot be told from the token's: reconciliation is short.
        self.assertIs(check(seen(), recorded(), records(dict(rerun, rerun_by_dispatcher=None)), accounts=TOKEN)["short"],
                      True)
        self.assertIs(check(seen(), recorded(), records(rerun), accounts=TOKEN)["short"], False)
        # One that started before the window was reconciled by an earlier pass.
        old_rerun = dict(rerun, started_at="2026-10-10T13:00:00Z", rerun_by_dispatcher=True)
        self.assertEqual(check(seen(), recorded(), records(old_rerun), accounts=TOKEN)["unmatched"], [])
        # Until the pass job's token's account is set, no dispatch is reconciled, and run records not read leave
        # nothing short (ruling 2).
        unset = dict(KNOWN, workflow_token=None)
        self.assertEqual(check(seen(), recorded(), records(r), accounts=unset)["unmatched"], [])
        self.assertIs(check(seen(), recorded(), None, accounts=unset)["short"], False)


def passed(evidence=("PRRT_t",), item=ITEM, hands=(), now="2026-10-11T12:00:00Z", **decision) -> dict:
    """A pass record before, whose Decision on `item` is the act `resolve_thread` naming `evidence`, or as changed."""
    record = json.loads((ROOT / "examples" / "pass.json").read_text())
    entry = record["pull_requests"][0]
    entry["facts"]["item"] = dict(item)
    entry["decision"] = dict({"schema": "decision/1", "item": dict(item), "state": "adjudicating", "reason": "resolve_due",
                              "evidence": list(evidence), "attention": "none", "outcome": "act", "action": "resolve_thread",
                              "content_id": "sha256:5d0c"}, **decision)
    record["now"] = now
    record["reconciled"] = dict(Carried.NONE, hands=[{"key": k, "at": now} for k in hands or ()])
    if hands is None:       # a record written before a hand's resolutions were carried
        del record["reconciled"]["hands"]
    return record


HAND = wrote("hand", "resolution", "PRRT_t", at=None)


class Hand(unittest.TestCase):
    """A person's resolution of a thread a Role opened, matched to the Kernel's act that named the thread (issue 854)."""

    def test_a_hands_resolution_of_a_roles_thread_is_matched_to_the_act_the_last_pass_named(self):  # issue 854
        # Until the queue App exists a session carries out the Kernel's `resolve_thread` by hand, as a person's account
        # (decision 0212). The pass that first sees the resolution matches it to the act of the last pass that decided
        # the item: that act named the thread, or the resolution is one nobody recorded.
        found = check(seen(HAND), before=[passed()])
        self.assertEqual((found["unmatched"], found["short"], reconcile.alerts(found)), ([], False, []))
        for why, before in (("another thread", [passed(["PRRT_u"])]), ("another item's act", [passed(item=OTHER)]),
                            ("no thread", [passed([])]),
                            ("an act a brake held", [passed(outcome="defer")]),
                            ("another act", [passed(action="enqueue")]),
                            ("a Decision that is no act", [passed(state="addressing", reason="findings_open", outcome="admit")]),
                            # The last pass that decided the item is the one read: the head may have moved since an earlier.
                            ("an act an earlier pass named and the last did not", [passed(), passed([])])):
            with self.subTest(why):
                found = check(seen(HAND), before=before)
                self.assertEqual((kinds(found), found["short"]), ([("hand", "resolution")], False))
                self.assertEqual(reconcile.alerts(found), ["write_unmatched"])
                self.assertEqual(reconcile.entries(found), [{"alert": "write_unmatched", "by": "hand", "write": "resolution",
                                                             "item": URL, "key": "PRRT_t"}])
        # A pass that did not decide the item, one it could not read, says nothing of it: the one before it is read.
        self.assertEqual(check(seen(HAND), before=[passed([]), passed()])["unmatched"], [])
        self.assertEqual(check(seen(HAND), before=[passed(), passed([], item=OTHER)])["unmatched"], [])
        # A resolution whose thread cannot be read is matched to nothing, and a Run on its item makes it no Run's write.
        self.assertEqual(kinds(check(seen(dict(HAND, key=None)), before=[passed()])), [("hand", "resolution")])
        running = [{"run": "r_01JA7Q", "item": ITEM, "started_at": AT, "status": "in_progress"}]
        found = check(seen(HAND), r=running, before=[passed([])], accounts=dict(KNOWN, workflow_token=None))
        self.assertEqual((kinds(found), found["short"]), ([("hand", "resolution")], False))

    def test_a_hands_resolution_once_matched_is_carried_while_it_is_seen(self):  # issue 854
        # A resolution has no time and is seen at every pass, long after the pass that named its thread: once matched, its
        # thread is carried, stamped again each pass it is seen, and matches from then on.
        effects = dict(recorded(), read={"runs": [], "passes": []}, at={})
        held = reconcile.carried([passed()], effects, seen(HAND), NOW)
        self.assertEqual(held["hands"], [{"key": "PRRT_t", "at": NOW}])
        later = dict(passed([], now=NOW), reconciled=held)
        self.assertEqual(check(seen(HAND), before=[later])["unmatched"], [])
        again = reconcile.carried([later], effects, seen(HAND), "2026-10-11T13:20:00Z")
        self.assertEqual(again["hands"], [{"key": "PRRT_t", "at": "2026-10-11T13:20:00Z"}])
        # A pass that did not see it, its pull request unread, carries it on as it was, until the window passes it.
        self.assertEqual(reconcile.carried([later], effects, seen(), "2026-10-11T13:20:00Z")["hands"], held["hands"])
        old = dict(passed([]), reconciled=dict(held, hands=[{"key": "PRRT_t", "at": EARLY}]))
        self.assertEqual(reconcile.carried([old], effects, seen(), NOW)["hands"], [])
        self.assertEqual(kinds(check(seen(HAND), before=[old])), [("hand", "resolution")])
        # One nobody named is not carried, so it alarms at every pass that sees it; nor is one whose thread cannot be read.
        self.assertEqual(reconcile.carried([passed([])], effects, seen(HAND), NOW)["hands"], [])
        self.assertEqual(reconcile.carried([passed()], effects, seen(dict(HAND, key=None)), NOW)["hands"], [])
        # What is carried is what `pass/1` holds.
        record = dict(passed(), reconciled=held)
        self.assertEqual(validate(record, SCHEMAS["pass"], schemas=SCHEMAS), [])

    def test_a_hands_resolution_no_record_can_judge_is_short_once_and_carried(self):  # issue 854
        # With no record before, or one written before a hand's resolutions were carried, nothing says whether an act
        # named the thread: reconciliation is short for that pass, never silent, and the thread is carried, so that one
        # resolved before the rule does not alarm for as long as its pull request is open.
        effects = dict(recorded(), read={"runs": [], "passes": []}, at={})
        for before in ([], [passed(hands=None)], [passed([], hands=None)]):
            found = check(seen(HAND), before=before)
            self.assertEqual((found["unmatched"], found["short"]), ([], True), before)
            self.assertEqual(reconcile.alerts(found), ["reconciliation_unreadable"])
            self.assertEqual(reconcile.carried(before, effects, seen(HAND), NOW)["hands"], [{"key": "PRRT_t", "at": NOW}])
        # With no hand's resolution seen, such a record leaves nothing short, and the next record carries none.
        self.assertFalse(check(seen(), before=[passed(hands=None)])["short"])
        self.assertEqual(reconcile.carried([passed(hands=None)], effects, seen(), NOW)["hands"], [])


class Short(unittest.TestCase):
    def test_what_cannot_be_read_whole_is_short_never_silent(self):  # ruling 5
        whole = check(seen())
        self.assertEqual((whole["short"], reconcile.alerts(whole)), (False, []))
        bad_applied = dict(applied(("approve", "K", "applied")), effects="none")
        bad_written = dict(written(("dequeue", ITEM, None, None, "applied")), writes="none")
        for found in (check(None), check(seen(whole=False)), check({"schema": "seen/1"}),
                      check(seen(), None), check(seen(), recorded(whole=False)), check(seen(), recorded([bad_applied])),
                      check(seen(), recorded(written_=[bad_written])),
                      check(seen(), recorded(), None, accounts=TOKEN),
                      check(seen(), accounts=dict(KNOWN, controller=None)), check(seen(), accounts=dict(KNOWN, approver=None)),
                      check(seen(), accounts=dict(KNOWN, roles={"pr-review": None})), check(seen(), accounts=None)):
            self.assertTrue(found["short"])
            self.assertEqual(reconcile.alerts(found), ["reconciliation_unreadable"])
        # What was read is still reconciled beside a short reconciliation.
        found = check(seen(wrote("approver", "push", "P"), whole=False))
        self.assertEqual(reconcile.alerts(found), ["reconciliation_unreadable", "write_unmatched"])


class Override(unittest.TestCase):
    def test_a_merge_no_pass_read_as_mergeable_is_an_override_reported_as_information(self):  # decision 0007
        before = json.loads((ROOT / "examples" / "pass.json").read_text())
        before["pull_requests"][0]["facts"]["item"] = dict(ITEM)
        before["now"] = "2026-10-11T12:00:00Z"
        merge = {"item": ITEM, "at": "2026-10-11T12:30:00Z"}

        def at(state, now=before["now"]) -> dict:
            prior = copy.deepcopy(before)
            prior["pull_requests"][0]["decision"]["state"] = state
            prior["now"] = now
            return prior

        for state, want in (("verifying", [{"item": ITEM}]), ("held", [{"item": ITEM}]), ("converged", []),
                            ("queued", [])):
            found = check(seen(merged=[merge]), before=[at(state)])
            self.assertEqual(found["override"], want, state)
            self.assertEqual(reconcile.alerts(found), [])
        # The last pass before the merge is read: not a pass after it, which reads the item as it is once merged, nor
        # an earlier one.
        self.assertEqual(check(seen(merged=[merge]), before=[at("queued"), at("verifying", "2026-10-11T13:00:00Z")])
                         ["override"], [])
        self.assertEqual(check(seen(merged=[merge]), before=[at("verifying", "2026-10-11T11:00:00Z"), at("queued")])
                         ["override"], [])
        self.assertEqual(check(seen(merged=[merge]), before=[at("queued", "2026-10-11T11:00:00Z"), at("verifying")])
                         ["override"], [{"item": ITEM}])
        # A merge of an item no pass read, or with no pass before, is nobody's to report.
        self.assertEqual(check(seen(merged=[dict(merge, item=OTHER)]), before=[at("verifying")])["override"], [])
        self.assertEqual(check(seen(merged=[merge]))["override"], [])
        self.assertEqual(reconcile.entries(check(seen(merged=[merge]), before=[at("verifying")])),
                         [{"alert": "merged_by_override", "by": None, "write": "merge", "item": URL, "key": None}])


APPROVER = {"id": 281750570, "type": "User", "login": "donpetry-bot"}
CONTROLLER = {"id": 5000001, "type": "Bot", "login": "combsmith-sf-controller[bot]"}
ROLE = {"id": 5000002, "type": "Bot", "login": "combsmith-sf-pr-review[bot]"}
PERSON = {"id": 36422719, "type": "User", "login": "don-petry"}
IDENTITIES = {(281750570, "User"): "approver", (5000001, "Bot"): "controller", (5000002, "Bot"): "pr-review"}
APPS = {5364130: "controller", 5364144: "pr-review"}
ISSUE = "/repos/%s/issues/%d" % (ITEM["repo"], ITEM["number"])
PULL = "/repos/%s/pulls/%d" % (ITEM["repo"], ITEM["number"])
COMMENTS = ("GET", ISSUE + "/comments?since=%s&per_page=100" % SINCE)
ACTIVITY = ("GET", "/repos/%s/activity?actor=donpetry-bot&time_period=day&per_page=100" % ITEM["repo"])
NOW = "2026-10-11T13:00:00Z"        # a pass's time, a day or less after SINCE
AT, EARLY = "2026-10-11T12:00:00Z", "2026-10-10T12:00:00Z"


class GitHub:
    """A stand-in GitHub, answering each request by method and path, else a 404; an answer of None is no answer."""

    def __init__(self, over=None):
        self.answers = {COMMENTS: [], ("GET", ISSUE + "/timeline?per_page=100"): [], ACTIVITY: []}
        self.answers.update(over or {})
        self.asked = []

    def send(self, req):
        self.asked.append((req["method"], req["path"]))
        found = self.answers.get((req["method"], req["path"]), "missing")
        if found is None:
            raise Unanswered("no answer")
        if found == "missing":
            return {"status": 404, "headers": {}, "body": {"message": "Not Found"}}
        if isinstance(found, dict) and "status" in found:
            return dict(found, headers={})
        return {"status": 200, "headers": {}, "body": copy.deepcopy(found)}


def check_run(app, ident, at=AT) -> dict:
    """A check run's node as the facts port's checks read keeps it."""
    return {"__typename": "CheckRun", "id": ident, "startedAt": at, "checkSuite": {"app": {"databaseId": app}}}


def kept(**parts) -> dict:
    """What `adapters/facts.snapshot` keeps of a pull request: each read as GitHub gave it, and whether it was whole."""
    out = {name: ([], True) for name in seen_.PARTS}
    out.update({name: (value, True) if isinstance(value, list) else value for name, value in parts.items()})
    return out


def port(parts=NOTHING, over=None, item=ITEM) -> tuple:
    return seen_.read(GitHub(over), item, kept() if parts is NOTHING else parts, IDENTITIES, APPS, SINCE)


class SeenPort(unittest.TestCase):
    def test_each_identitys_writes_are_read_by_its_account_never_its_login(self):  # ruling 2
        reviews = [{"user": APPROVER, "state": "APPROVED", "node_id": "PRR_a", "submitted_at": AT},
                   {"user": APPROVER, "state": "COMMENTED", "node_id": "PRR_b", "submitted_at": AT},
                   {"user": APPROVER, "state": "DISMISSED", "node_id": "PRR_d", "id": 4, "submitted_at": AT},
                   {"user": ROLE, "state": "DISMISSED", "node_id": "PRR_e", "id": 5, "submitted_at": AT},
                   {"user": APPROVER, "state": "PENDING", "node_id": "PRR_q"},
                   {"user": ROLE, "state": "COMMENTED", "node_id": "PRR_r", "submitted_at": SINCE},
                   {"user": dict(PERSON, login="donpetry-bot"), "state": "APPROVED", "node_id": "PRR_p", "submitted_at": AT},
                   {"user": dict(APPROVER, type="Bot"), "state": "APPROVED", "node_id": "PRR_x", "submitted_at": AT},
                   {"user": APPROVER, "state": "APPROVED", "node_id": "PRR_old", "submitted_at": EARLY}]
        comments = [{"user": CONTROLLER, "node_id": "IC_c", "created_at": AT}, {"user": PERSON, "node_id": "IC_p",
                                                                                "created_at": AT}]
        events = [{"event": "labeled", "actor": CONTROLLER, "created_at": AT},
                  {"event": "removed_from_merge_queue", "actor": CONTROLLER, "created_at": AT},
                  {"event": "review_dismissed", "actor": APPROVER, "created_at": AT,
                   "dismissed_review": {"review_id": 4, "state": "approved"}},
                  {"event": "review_dismissed", "actor": PERSON, "created_at": AT,
                   "dismissed_review": {"review_id": 5, "state": "commented"}},
                  {"event": "closed", "actor": ROLE, "created_at": AT},
                  {"event": "review_requested", "actor": ROLE, "created_at": AT},
                  {"event": "assigned", "actor": CONTROLLER, "created_at": AT},
                  {"event": "milestoned", "actor": CONTROLLER, "created_at": AT},
                  {"event": "mentioned", "actor": CONTROLLER, "created_at": AT},
                  {"event": "milestoned", "actor": PERSON, "created_at": AT},
                  {"event": "merged", "actor": PERSON, "created_at": AT},
                  {"event": "commented", "actor": CONTROLLER, "created_at": AT},
                  {"event": "labeled", "actor": PERSON, "created_at": AT}]
        threads_ = [{"id": "PRRT_n", "isResolved": True, "resolvedBy": None},
                    {"id": "PRRT_a", "isResolved": True, "resolvedBy": {"login": "donpetry-bot", "databaseId": 281750570}},
                    # A Role App's resolution, which GraphQL types a User: told by its account id (decision 0067).
                    {"id": "PRRT_r", "isResolved": True, "resolvedBy": {"login": "combsmith-sf-pr-review[bot]",
                                                                        "databaseId": 5000002}},
                    {"id": "PRRT_p", "isResolved": True, "resolvedBy": {"login": "don-petry", "databaseId": 36422719},
                     "comments": {"nodes": [{"replyTo": None, "author": {"__typename": "User", "login": "don-petry",
                                                                         "databaseId": 36422719}}]}},
                    {"id": "PRRT_o", "isResolved": False, "resolvedBy": None}]
        runs = [check_run(5364144, "CR_r"), check_run(5364130, "CR_c"), check_run(15368, "CR_x")]
        writes, merged, whole = port(kept(reviews=reviews, events=events, threads=threads_, check_runs=runs),
                                     {COMMENTS: comments})
        self.assertTrue(whole)
        self.assertEqual([(w["by"], w["kind"], w["key"]) for w in writes],
                         [("approver", "approval", "PRR_a"), ("approver", "review", "PRR_b"),
                          ("approver", "approval", "PRR_d"), ("pr-review", "review", "PRR_e"),
                          ("pr-review", "review", "PRR_r"),
                          ("controller", "comment", "IC_c"), ("controller", "label", None),
                          ("controller", "dequeue", None), ("approver", "dismissal", None),
                          ("pr-review", "close", None), ("pr-review", "review_request", None),
                          ("controller", "assignment", None), ("controller", "other", "milestoned"),
                          ("unattributed", "resolution", "PRRT_n"),
                          ("approver", "resolution", "PRRT_a"), ("pr-review", "resolution", "PRRT_r"), ("pr-review", "check_run", "CR_r"),
                          ("controller", "check_run", "CR_c")])
        # A merge by anyone is read for an Override; and what was seen is seen/1.
        self.assertEqual(merged, [{"item": ITEM, "at": AT}])
        out = seen_.seen([(writes, merged, whole)], SINCE)
        self.assertEqual(validate(out, SCHEMAS["seen"], schemas=SCHEMAS), [])

    def test_a_persons_resolution_of_a_thread_a_role_opened_is_read_as_a_hands(self):  # issue 854
        # The Kernel takes a person's resolution as closing a Lens's Finding, so it is a write to reconcile: read as a
        # hand's, of a thread a Role's own account opened, by the first comment's author. A person's resolution of any
        # other thread is nobody's here, and a Factory identity's is its own, whoever opened the thread.
        def thread(ident, by=PERSON, opened=ROLE, **first):
            comment = dict({"replyTo": None, "author": opened and {
                "__typename": opened["type"], "login": opened["login"], "databaseId": opened["id"]}}, **first)
            return {"id": ident, "isResolved": True, "resolvedBy": by and {"login": by["login"], "databaseId": by["id"]},
                    "comments": {"nodes": [comment]}}

        threads_ = [thread("PRRT_h"), thread("PRRT_p", opened=PERSON), thread("PRRT_a", opened=APPROVER),
                    thread("PRRT_c", opened=CONTROLLER), thread("PRRT_g", opened=None),
                    thread("PRRT_m", author={"__typename": "Mannequin", "login": "gone"}),
                    thread("PRRT_r", by=ROLE), thread("PRRT_n", by=None),
                    dict(thread("PRRT_o"), isResolved=False, resolvedBy=None)]
        writes, _, whole = port(kept(threads=threads_))
        self.assertTrue(whole)
        self.assertEqual([(w["by"], w["kind"], w["key"], w["at"]) for w in writes],
                         [("hand", "resolution", "PRRT_h", None), ("pr-review", "resolution", "PRRT_r", None),
                          ("unattributed", "resolution", "PRRT_n", None)])
        self.assertEqual(validate(seen_.seen([(writes, [], whole)], SINCE), SCHEMAS["seen"], schemas=SCHEMAS), [])
        # An opener that cannot be told from a Role's leaves what was seen short, and no write is read of it: a first
        # comment that replies to another, none, or an author whose account cannot be read.
        unsaid = thread("PRRT_h")
        del unsaid["comments"]["nodes"][0]["replyTo"]
        for why, odd in (("a reply", thread("PRRT_h", replyTo={"id": "PRRC_1"})), ("a reply not said", unsaid),
                         ("no comment", dict(thread("PRRT_h"), comments={"nodes": []})),
                         ("no comments", dict(thread("PRRT_h"), comments=None)),
                         ("an account of no id", thread("PRRT_h", author={"__typename": "Bot", "login": "x", "databaseId": None})),
                         ("an account whose id is no number", thread("PRRT_h", author={"__typename": "Bot", "databaseId": True}))):
            writes, _, whole = port(kept(threads=[odd]))
            self.assertEqual((writes, whole), ([], False), why)
        # Only a person's resolution asks who opened the thread: an identity's is read whoever did, as before.
        writes, _, whole = port(kept(threads=[dict(thread("PRRT_r", by=ROLE), comments=None)]))
        self.assertEqual(([(w["by"], w["key"]) for w in writes], whole), ([("pr-review", "PRRT_r")], True))

    def test_no_read_the_facts_port_made_is_made_twice(self):  # ruling 3
        github = GitHub()
        seen_.read(github, ITEM, kept(), IDENTITIES, APPS, SINCE)
        self.assertEqual(github.asked, [COMMENTS])
        # An issue's timeline is read here, since no snapshot reads it; it has no reviews, threads or check runs.
        github = GitHub({("GET", ISSUE + "/timeline?per_page=100"): [
            {"event": "labeled", "actor": CONTROLLER, "created_at": AT}]})
        writes, _, whole = seen_.read(github, dict(ITEM, type="issue"), None, IDENTITIES, APPS, SINCE)
        self.assertEqual((github.asked, [(w["by"], w["kind"]) for w in writes], whole),
                         ([("GET", ISSUE + "/timeline?per_page=100"), COMMENTS], [("controller", "label")], True))

    def test_a_pull_request_read_as_left_before_is_read_again_though_its_close_is_older_than_the_window(self):  # issue 787
        # A pass before read it as left, inside the window: it is read as one that left, every part of it, and its close,
        # already read then, stands though it is now older than the window. A timeline that names no close is short.
        answers = {("GET", ISSUE + "/timeline?per_page=100"): [{"event": "merged", "actor": PERSON, "created_at": EARLY}],
                   ("GET", PULL + "/reviews?per_page=100"): [
                       {"user": APPROVER, "state": "APPROVED", "node_id": "PRR_g", "submitted_at": AT}],
                   ("POST", "/graphql"): {"data": {"repository": {"pullRequest": {"reviewThreads": {
                       "totalCount": 0, "pageInfo": {"hasNextPage": False}, "nodes": []}}}}},
                   ("GET", PULL): {"head": {"sha": "c0ffee" + "0" * 34}},
                   ("GET", "/repos/%s/commits/%s/check-runs?per_page=100" % (ITEM["repo"], "c0ffee" + "0" * 34)): {
                       "total_count": 0, "check_runs": []}}
        writes, _, whole = seen_.read(GitHub(answers), ITEM, seen_.GONE, IDENTITIES, APPS, SINCE)
        self.assertEqual(([(w["by"], w["kind"], w["key"]) for w in writes], whole), ([("approver", "approval", "PRR_g")], True))
        self.assertIs(seen_.read(GitHub(answers), ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], False)
        none = {**answers, ("GET", ISSUE + "/timeline?per_page=100"): []}
        self.assertIs(seen_.read(GitHub(none), ITEM, seen_.GONE, IDENTITIES, APPS, SINCE)[2], False)

    def test_an_item_that_left_the_open_list_has_its_timeline_read_here(self):  # issue 329
        # A pull request merged or closed between the passes is no longer open, so no snapshot reads it: its timeline
        # is read here, and with it a close by a Factory identity and a merge for an Override.
        # Its reviews, threads and the check runs on its head are read here too, since no snapshot kept them.
        events = [{"event": "closed", "actor": CONTROLLER, "created_at": AT},
                  {"event": "merged", "actor": PERSON, "created_at": AT}]
        head = "c0ffee" + "0" * 34
        answers = {("GET", ISSUE + "/timeline?per_page=100"): events,
                   ("GET", PULL + "/reviews?per_page=100"): [
                       {"user": APPROVER, "state": "APPROVED", "node_id": "PRR_l", "submitted_at": AT}],
                   ("POST", "/graphql"): {"data": {"repository": {"pullRequest": {"reviewThreads": {
                       "totalCount": 1, "pageInfo": {"hasNextPage": False},
                       "nodes": [{"id": "PRRT_l", "isResolved": True, "resolvedBy": None}]}}}}},
                   ("GET", PULL): {"head": {"sha": head}},
                   ("GET", "/repos/%s/commits/%s/check-runs?per_page=100" % (ITEM["repo"], head)): {
                       "total_count": 1, "check_runs": [{"node_id": "CR_l", "started_at": AT, "app": {"id": 5364130}}]}}
        github = GitHub(answers)
        writes, merged, whole = seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)
        self.assertEqual(([(w["by"], w["kind"], w["key"]) for w in writes], merged, whole),
                         ([("approver", "approval", "PRR_l"), ("controller", "close", None),
                           ("unattributed", "resolution", "PRRT_l"), ("controller", "check_run", "CR_l")],
                          [{"item": ITEM, "at": AT}], True))
        # Any of them not read, or a timeline that names no close, which no item that left would, is short.
        for path in list(answers):
            short = {**answers, path: {"status": 502, "body": {}}}
            self.assertIs(seen_.read(GitHub(short), ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], False, path)
        still_open = {**answers, ("GET", ISSUE + "/timeline?per_page=100"): events[:0]}
        self.assertIs(seen_.read(GitHub(still_open), ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], False)
        # A close or a merge alone says it left; one before the window, reopened since, does not.
        for timeline_ in (events[:1], events[1:]):
            ended = {**answers, ("GET", ISSUE + "/timeline?per_page=100"): timeline_}
            self.assertIs(seen_.read(GitHub(ended), ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], True, timeline_)
        reopened = {**answers, ("GET", ISSUE + "/timeline?per_page=100"): [
            dict(events[0], created_at=EARLY), {"event": "reopened", "actor": PERSON, "created_at": EARLY}]}
        self.assertIs(seen_.read(GitHub(reopened), ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], False)
        # Its threads and check runs are whole only when every one GitHub counts was read, of a head that can be read.
        threads_more = {"data": {"repository": {"pullRequest": {"reviewThreads": {
            "totalCount": 2, "pageInfo": {"hasNextPage": True}, "nodes": [{"id": "PRRT_l", "isResolved": False}]}}}}}
        for change in ({("POST", "/graphql"): threads_more},
                       {("POST", "/graphql"): {"data": {"repository": {"pullRequest": {"reviewThreads": {
                           "totalCount": 2, "pageInfo": {"hasNextPage": False}, "nodes": []}}}}}},
                       {("GET", "/repos/%s/commits/%s/check-runs?per_page=100" % (ITEM["repo"], head)): {
                           "total_count": 2, "check_runs": []}},
                       # A check run whose App GitHub gives no id for, null or absent (decision 0181).
                       {("GET", "/repos/%s/commits/%s/check-runs?per_page=100" % (ITEM["repo"], head)): {
                           "total_count": 1, "check_runs": [{"node_id": "CR_h", "started_at": AT, "app": None}]}},
                       {("GET", "/repos/%s/commits/%s/check-runs?per_page=100" % (ITEM["repo"], head)): {
                           "total_count": 1, "check_runs": [{"node_id": "CR_h", "started_at": AT}]}},
                       {("GET", "/repos/%s/commits/%s/check-runs?per_page=100" % (ITEM["repo"], head)): {
                           "total_count": 1, "check_runs": [{"node_id": "CR_h", "started_at": AT, "app": {"id": False}}]}},
                       {("POST", "/graphql"): {"data": {"repository": {"pullRequest": {"reviewThreads": {
                           "totalCount": 1, "pageInfo": {"hasNextPage": True},
                           "nodes": [{"id": "PRRT_l", "isResolved": False}]}}}}}},
                       {("GET", PULL): {"head": {"sha": "abc"}},
                        ("GET", "/repos/%s/commits/abc/check-runs?per_page=100" % ITEM["repo"]): {
                            "total_count": 0, "check_runs": []}}):
            self.assertIs(seen_.read(GitHub({**answers, **change}), ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], False,
                          change)

    def test_a_list_that_cannot_be_read_whole_leaves_what_was_seen_short(self):  # ruling 5
        self.assertIs(port()[2], True)
        bad = {"reviews": [{"user": ROLE, "state": "COMMENTED", "node_id": "P", "submitted_at": "yesterday"}],
               "events": [{"event": "labeled", "actor": CONTROLLER, "created_at": "yesterday"}],
               "check_runs": [check_run(5364144, "CR_r", at=None)]}
        keyless = {"reviews": [{"user": ROLE, "state": "COMMENTED", "node_id": None, "submitted_at": AT}],
                   "threads": [{"id": None, "isResolved": True, "resolvedBy": None}],
                   "check_runs": [check_run(5364144, "CR r")]}
        for parts in [None, {}, dict(kept(), threads=None), dict(kept(), events=([], False)),
                      dict(kept(), reviews=([], False)), dict(kept(), check_runs=([], False)),
                      dict(kept(), threads=([], False)),
                      kept(threads=[{"id": "PRRT_u", "isResolved": True, "resolvedBy": {"login": "x"}}]),
                      # A check run whose App GitHub did not show the reading token (decision 0181).
                      kept(check_runs=[dict(check_run(5364144, "CR_h"), checkSuite={"app": None})]),
                      kept(check_runs=[check_run(False, "CR_h")]), kept(check_runs=[check_run(None, "CR_h")])] \
                + [kept(**{name: value}) for name, value in bad.items()] \
                + [kept(**{name: value}) for name, value in keyless.items()]:
            self.assertIs(port(parts)[2], False, parts)
        unreadable = {"login": "combsmith-sf-controller[bot]"}
        # A dismissed review whose state before the timeline does not give (issue 329); an event no Factory write
        # makes, by an account that cannot be read; a resolver of no positive id (issue 328).
        dismissed = {"user": ROLE, "state": "DISMISSED", "node_id": "PRR_e", "id": 5, "submitted_at": AT}
        for parts in (kept(reviews=[dismissed]),
                      kept(reviews=[dismissed], events=[{"event": "review_dismissed", "actor": PERSON, "created_at": AT,
                                                         "dismissed_review": {"review_id": 5, "state": "pending"}}]),
                      kept(events=[{"event": "milestoned", "actor": unreadable, "created_at": AT}]),
                      kept(events=[{"event": "milestoned", "actor": dict(CONTROLLER, type="Organization"),
                                    "created_at": AT}]),
                      kept(threads=[{"id": "PRRT_z", "isResolved": True, "resolvedBy": {"databaseId": 0}}]),
                      kept(threads=[{"id": "PRRT_z", "isResolved": True, "resolvedBy": {"databaseId": -3}}]),
                      # A dismissal and a review told by no positive id, or a state that is no word, pair with nothing.
                      kept(reviews=[dict(dismissed, id=None)], events=[{"event": "review_dismissed", "actor": PERSON,
                                                                        "created_at": AT,
                                                                        "dismissed_review": {"state": "commented"}}]),
                      kept(reviews=[dict(dismissed, id=True)], events=[{"event": "review_dismissed", "actor": PERSON,
                                                                        "created_at": AT, "dismissed_review": {
                                                                            "review_id": 1, "state": "commented"}}]),
                      kept(reviews=[dict(dismissed, id=1)], events=[{"event": "review_dismissed", "actor": PERSON,
                                                                     "created_at": AT, "dismissed_review": {
                                                                         "review_id": True, "state": "commented"}}]),
                      kept(reviews=[dict(dismissed, id=[5])]),
                      kept(reviews=[dismissed], events=[{"event": "review_dismissed", "actor": PERSON,
                                                         "created_at": AT, "dismissed_review": {
                                                             "review_id": 5, "state": ["commented"]}}]),
                      # An event GitHub gives no name for cannot be told from a write.
                      kept(events=[{"actor": PERSON, "created_at": AT}])):
            self.assertIs(port(parts)[2], False, parts)
        # A resolver whose id is True is no account's, and is never told as an identity of id 1, as True == 1 would.
        writes, _, whole = seen_.read(GitHub(None), ITEM, kept(threads=[{"id": "PRRT_b", "isResolved": True,
                                                                        "resolvedBy": {"databaseId": True}}]),
                                      {(1, "User"): "approver"}, APPS, SINCE)
        self.assertEqual((writes, whole), ([], False))
        # A review of a state GitHub does not give cannot be told.
        self.assertIs(port(kept(reviews=[{"user": ROLE, "state": None, "node_id": "PRR_u", "submitted_at": AT}]))[2],
                      False)
        # A dismissed review whose state before cannot be read is read as an approval, so that a Role's alarms too.
        writes, _, whole = port(kept(reviews=[dismissed]))
        self.assertEqual(([(w["by"], w["kind"]) for w in writes], whole), ([("pr-review", "approval")], False))
        # A dismissed change request is what it was: a review.
        asked = kept(reviews=[dismissed], events=[{"event": "review_dismissed", "actor": PERSON, "created_at": AT,
                                                   "dismissed_review": {"review_id": 5,
                                                                        "state": "changes_requested"}}])
        writes, _, whole = port(asked)
        self.assertEqual(([(w["by"], w["kind"]) for w in writes], whole), ([("pr-review", "review")], True))
        # Only a dismissal says what a review was before: another event of the timeline does not.
        other = kept(reviews=[dismissed], events=[{"event": "labeled", "actor": PERSON, "created_at": AT,
                                                   "dismissed_review": {"review_id": 5, "state": "commented"}}])
        self.assertIs(port(other)[2], False)
        # A person's event no Factory write makes, or one before the window, is no one's to reconcile.
        for event in ({"event": "milestoned", "actor": PERSON, "created_at": AT},
                      {"event": "milestoned", "actor": unreadable, "created_at": EARLY}):
            self.assertEqual(port(kept(events=[event]))[::2], ([], True), event)
        for actor in (unreadable, dict(CONTROLLER, type="Organization"), dict(CONTROLLER, id=0)):
            self.assertIs(port(over={COMMENTS: [{"user": actor, "node_id": "IC_u", "created_at": AT}]})[2], False, actor)
        for parts in (kept(reviews=[{"user": unreadable, "state": "APPROVED", "node_id": "PRR_u", "submitted_at": AT}]),
                      kept(events=[{"event": "labeled", "actor": unreadable, "created_at": AT}]),
                      kept(events=[{"event": "labeled", "actor": CONTROLLER, "created_at": "2026-13-01T00:00:00Z"}])):
            self.assertIs(port(parts)[2], False, parts)
        for answer in ({"status": 403, "body": {}}, None, [{"user": CONTROLLER, "node_id": "IC", "created_at": "x"}],
                       [{"user": CONTROLLER, "node_id": None, "created_at": AT}],
                       [{"user": unreadable, "node_id": "IC_u", "created_at": AT}]):
            self.assertIs(port(over={COMMENTS: answer})[2], False, answer)
        # A pull request whose snapshot kept nothing is short, and its comments are still read.
        writes, _, whole = port(None, {COMMENTS: [{"user": CONTROLLER, "node_id": "IC_c", "created_at": AT}]})
        self.assertEqual(([(w["by"], w["kind"]) for w in writes], whole), ([("controller", "comment")], False))

    def test_the_machine_users_pushes_are_read_from_the_repos_activity(self):  # decision 0005
        entries = [{"id": 7, "actor": APPROVER, "timestamp": AT, "activity_type": "push"},
                   {"id": 8, "actor": PERSON, "timestamp": AT, "activity_type": "push"},
                   {"id": 9, "actor": APPROVER, "timestamp": EARLY, "activity_type": "push"},
                   {"id": 10, "actor": APPROVER, "timestamp": SINCE, "activity_type": "force_push"},
                   {"id": 11, "actor": APPROVER, "timestamp": AT, "activity_type": "pr_merge"},
                   {"id": 12, "actor": APPROVER, "timestamp": AT, "activity_type": "branch_creation"}]
        writes, whole = seen_.pushes(GitHub({ACTIVITY: entries}), ITEM["repo"], APPROVER, SINCE, lambda: NOW)
        # Each is named by the kind its activity gives, never a push for all.
        self.assertEqual(([(w["by"], w["kind"], w["key"], w["item"]) for w in writes], whole),
                         ([("approver", "push", "7", None), ("approver", "force_push", "10", None),
                           ("approver", "merge", "11", None), ("approver", "branch_created", "12", None)], True))
        # An activity of a type not known is the machine user's write all the same, and leaves the read short.
        writes, whole = seen_.pushes(GitHub({ACTIVITY: [dict(entries[0], activity_type="branch_rename")]}),
                                     ITEM["repo"], APPROVER, SINCE, lambda: NOW)
        self.assertEqual(([w["kind"] for w in writes], whole), (["other"], False))
        for answer in ({"status": 500, "body": {}}, None,
                       [{"id": 7, "actor": APPROVER, "timestamp": "x", "activity_type": "push"}],
                       [{"id": None, "actor": APPROVER, "timestamp": AT, "activity_type": "push"}],
                       [{"id": True, "actor": APPROVER, "timestamp": AT, "activity_type": "push"}],
                       [{"id": 7, "actor": {"login": "donpetry-bot"}, "timestamp": AT, "activity_type": "push"}],
                       [{"id": i + 1, "actor": PERSON, "timestamp": AT} for i in range(100)]):
            self.assertIs(seen_.pushes(GitHub({ACTIVITY: answer}), ITEM["repo"], APPROVER, SINCE, lambda: NOW)[1], False,
                          answer)

    def test_the_activity_is_asked_for_a_period_that_covers_the_window(self):  # issue 329
        # GitHub's shortest period that covers the window is asked; a window older than a year is read for the year,
        # and short, since what came before it is not read.
        entry = [{"id": 7, "actor": APPROVER, "timestamp": AT, "activity_type": "push"}]
        # Each period is asked only while it covers the window an hour over, for clocks apart.
        for now, period in (("2026-10-11T23:00:00Z", "day"), ("2026-10-11T23:00:01Z", "week"),
                            ("2026-10-17T23:00:00Z", "week"), ("2026-10-17T23:00:01Z", "month"),
                            ("2026-11-07T23:00:00Z", "month"), ("2026-11-07T23:00:01Z", "quarter"),
                            ("2027-01-07T23:00:00Z", "quarter"), ("2027-01-07T23:00:01Z", "year"),
                            ("2027-10-09T23:00:00Z", "year")):
            path = ("GET", "/repos/%s/activity?actor=donpetry-bot&time_period=%s&per_page=100" % (ITEM["repo"], period))
            self.assertEqual(seen_.pushes(GitHub({path: entry}), ITEM["repo"], APPROVER, SINCE, lambda: now),
                             ([{"by": "approver", "kind": "push", "item": None, "key": "7", "at": AT}], True), now)
        # A window older than a year, a clock before the window, or one that cannot be read is read for the year,
        # and short.
        year = ("GET", "/repos/%s/activity?actor=donpetry-bot&time_period=year&per_page=100" % ITEM["repo"])
        for now in ("2027-10-09T23:00:01Z", "2026-10-01T00:00:00Z", "never"):
            github = GitHub({year: entry})
            self.assertIs(seen_.pushes(github, ITEM["repo"], APPROVER, SINCE, lambda: now)[1], False, now)
            self.assertEqual(github.asked, [year], now)
        # GitHub's own Date decides what its period covered: a clock behind GitHub's leaves the read short.
        day = ("GET", "/repos/%s/activity?actor=donpetry-bot&time_period=day&per_page=100" % ITEM["repo"])

        class Dated(GitHub):
            def send(self, req):
                return dict(super().send(req), headers={"date": self.date})
        for date, whole in (("Sun, 11 Oct 2026 13:00:00 GMT", True), ("Mon, 12 Oct 2026 03:00:00 GMT", False),
                            ("no date", True)):
            github = Dated({day: entry})
            github.date = date
            self.assertIs(seen_.pushes(github, ITEM["repo"], APPROVER, SINCE, lambda: NOW)[1], whole, date)
        # A period longer than GitHub's time needs covers the window all the same.
        week = ("GET", "/repos/%s/activity?actor=donpetry-bot&time_period=week&per_page=100" % ITEM["repo"])
        github = Dated({week: entry})
        github.date = "Sun, 11 Oct 2026 13:00:00 GMT"
        self.assertIs(seen_.pushes(github, ITEM["repo"], APPROVER, SINCE, lambda: "2026-10-12T03:00:00Z")[1], True)

    def test_seen_is_whole_only_when_every_part_was(self):
        whole, short = ([], [], True), ([], [], False)
        self.assertIs(seen_.seen([whole, ([], True)], SINCE)["whole"], True)
        for parts in ([whole, short], [whole, ([], False)], [short]):
            self.assertIs(seen_.seen(parts, SINCE)["whole"], False)

    def test_each_identity_is_told_by_its_account_from_the_configuration(self):  # ruling 2
        found, known = seen_.identities(KNOWN)
        self.assertEqual(found, {(281750570, "User"): "approver", (5000001, "Bot"): "controller",
                                 (5000002, "Bot"): "pr-review"})
        self.assertIs(known, True)
        for accounts in (dict(KNOWN, controller=None), dict(KNOWN, approver=None), dict(KNOWN, roles={"pr-review": None})):
            self.assertIs(seen_.identities(accounts)[1], False)
        # This repo's configuration knows every one, by what GitHub answers of each bot account (P-39.accounts.json).
        self.assertIs(seen_.identities(ACCOUNTS)[1], True)
        answered = json.loads((ROOT / "trials" / "P-39.accounts.json").read_text())["exchanges"]
        self.assertEqual([{k: e["response"]["body"][k] for k in ("login", "id", "type")} for e in answered],
                         [ACCOUNTS["controller"], ACCOUNTS["roles"]["pr-review"]])
        # Two identities of one account cannot be told apart: neither is known (issue 328).
        twice = dict(KNOWN, roles={"pr-review": dict(KNOWN["controller"])})
        self.assertEqual(seen_.identities(twice), ({(281750570, "User"): "approver"}, False))
        # The configuration holds the machine user as trials/P-7.json records it and the approver config/defaults.json
        # names, and a Role App's account for each Role App config/apps.json holds.
        defaults = json.loads((ROOT / "config" / "defaults.json").read_text())
        apps = json.loads((ROOT / "config" / "apps.json").read_text())["apps"]
        self.assertEqual((ACCOUNTS["approver"]["login"], ACCOUNTS["approver"]["id"]), (defaults["approver"], 281750570))
        # The queue App is no Role: its account joins the configuration with the step that writes through it (issue
        # 381), and until then nothing it writes is read. Nor is the release App, which writes tags and no item.
        self.assertEqual(set(ACCOUNTS["roles"]), set(apps) - {"controller", "reader", "queue", "release"})
        # A Role left out of the configuration could not be told at all: the configuration names every one.
        conf = json.loads((ROOT / "config" / "controller.json").read_text())
        self.assertEqual(validate(conf, SCHEMAS["controller"], schemas=SCHEMAS), [])
        self.assertNotEqual(validate(dict(conf, accounts=dict(ACCOUNTS, roles={})), SCHEMAS["controller"],
                                     schemas=SCHEMAS), [])


class Carried(unittest.TestCase):
    """What a pass carries of what it read, so that the next reads only what is new (decisions 0061, 0112)."""
    NOW = "2026-10-11T13:00:00Z"
    NEXT = "2026-10-11T13:20:00Z"
    MADE = "2026-10-11T12:00:00Z"
    RUN = "r_01JA7Q"
    NONE = {"runs": [], "passes": [], "keys": [], "items": [], "dispatched": [], "owed": [], "left": [], "hands": []}

    def effects(self, *a, written_=(), runs=(), passes=(), whole=True, at=None):
        return dict(recorded(a, written_, whole), read={"runs": list(runs), "passes": list(passes)}, at=at or {})

    def test_what_a_pass_read_matches_a_write_in_the_passes_after_it_for_the_window(self):
        read = self.effects(applied(("approve", "K", "applied"), ("comment", "L", "already_applied"), ("comment", "M", "failed")),
                            written_=[written(("dequeue", ITEM, None, None, "applied"), ("status_on_item", ITEM, None, "S", "applied"),
                                              ("dispatch_run", ITEM, self.RUN, None, "sent"))],
                            runs=[self.RUN], passes=[{"id": 41, "attempt": 1}], at={self.RUN: self.MADE, "p_01JA7Q": self.MADE})
        held = reconcile.carried([], read, seen(), self.NOW, [7])
        self.assertEqual(held["runs"], [{"id": self.RUN, "at": self.NOW}])
        self.assertEqual(held["passes"], [{"id": 41, "attempt": 1, "at": self.NOW}])
        self.assertEqual(held["owed"], [7])
        self.assertEqual(sorted((k["where"], k["type"], k["key"]) for k in held["keys"]),
                         [("applied", "approve", "K"), ("applied", "comment", "L"), ("written", "status_on_item", "S")])
        # A key one write alone can match is stamped with when it was read, so it outlasts the write it records, which came
        # after its record's Run began. What any such write could spend is stamped with when its record was made.
        self.assertEqual({k["at"] for k in held["keys"]} | {d["at"] for d in held["dispatched"]}, {self.NOW})
        self.assertEqual({i["at"] for i in held["items"]}, {self.MADE})
        self.assertEqual([(i["type"], i["count"]) for i in held["items"]], [("dequeue", 1)])
        self.assertEqual([d["run"] for d in held["dispatched"]], [self.RUN])
        before = [{"now": self.NOW, "pull_requests": [], "reconciled": held}]
        self.assertEqual(reconcile.known(before), ({self.RUN}, {(41, 1)}))
        self.assertEqual(reconcile.owed(before), [7])
        # Nothing new is read, and what was carried still matches each write; a key no one recorded does not.
        writes = (wrote("approver", "approval", "K"), wrote("pr-review", "comment", "L"), wrote("controller", "check_run", "S"),
                  wrote("controller", "dequeue"))
        found = check(seen(*writes), self.effects(), before=before)
        self.assertEqual((found["unmatched"], found["short"]), ([], False))
        self.assertEqual(kinds(check(seen(wrote("pr-review", "comment", "M")), self.effects(), before=before)), [("pr-review", "comment")])
        # A dequeue is matched as many times as it was recorded, what it read this pass and what was carried together.
        self.assertEqual(kinds(check(seen(wrote("controller", "dequeue"), wrote("controller", "dequeue")), self.effects(), before=before)),
                         [("controller", "dequeue")])
        self.assertEqual(check(seen(wrote("controller", "dequeue"), wrote("controller", "dequeue")),
                               self.effects(written_=[written(("dequeue", ITEM, None, None, "applied"))]), before=before)["unmatched"], [])
        # A dispatch it read is carried too.
        run = {"run": self.RUN, "item": ITEM, "started_at": self.MADE, "status": "completed"}
        self.assertEqual(check(seen(), self.effects(), [run], before=before, accounts=TOKEN)["unmatched"], [])
        self.assertEqual(kinds(check(seen(), self.effects(), [dict(run, run="r_01JA7R")], before=before, accounts=TOKEN)),
                         [("workflow_token", "dispatch")])
        # The next pass's carries what it read after what it was handed, each kind of it, and one with nothing new carries
        # it all on, owing what it itself could not read and no more.
        more = self.effects(applied(("comment", "N", "applied")),
                            written_=[written(("dequeue", ITEM, None, None, "applied"), ("dispatch_run", ITEM, "r_01JA7R", None, "sent"))],
                            runs=["r_01JA7R"], passes=[{"id": 42, "attempt": 1}])
        again = reconcile.carried(before, more, seen(), self.NEXT)
        self.assertEqual(again["runs"], held["runs"] + [{"id": "r_01JA7R", "at": self.NEXT}])
        self.assertEqual(again["passes"], held["passes"] + [{"id": 42, "attempt": 1, "at": self.NEXT}])
        self.assertEqual(again["keys"][:len(held["keys"])], held["keys"])
        self.assertEqual(again["keys"][len(held["keys"]):], [{"where": "applied", "type": "comment", "key": "N", "at": self.NEXT}])
        self.assertEqual([len(again[k]) for k in ("items", "dispatched")], [2, 2])
        self.assertEqual(again["owed"], [])
        self.assertEqual(reconcile.carried(before, self.effects(), seen(), self.NEXT), dict(held, owed=[]))

    def test_what_is_older_than_the_window_is_dropped_and_matches_nothing(self):
        old = {"at": "2026-10-09T00:00:00Z"}
        kept_ = {"at": SINCE}
        held = {"runs": [dict(old, id="r_01JA00"), dict(kept_, id="r_01JA01")],
                "passes": [dict(old, id=1, attempt=1), dict(kept_, id=2, attempt=1)],
                "keys": [dict(old, where="applied", type="comment", key="OLD"), dict(kept_, where="applied", type="comment", key="NEW")],
                "items": [dict(old, type="dequeue", item=reconcile.key(ITEM), count=1)],
                "dispatched": [dict(old, run="r_01JA00"), dict(kept_, run="r_01JA01")], "owed": []}
        before = [{"now": self.NOW, "pull_requests": [], "reconciled": held}]
        out = reconcile.carried(before, self.effects(), seen(), self.NOW)
        self.assertEqual((out["runs"], out["passes"], [k["key"] for k in out["keys"]], out["items"], [d["run"] for d in out["dispatched"]]),
                         ([held["runs"][1]], [held["passes"][1]], ["NEW"], [], ["r_01JA01"]))
        self.assertEqual(check(seen(wrote("pr-review", "comment", "NEW")), self.effects(), before=before)["unmatched"], [])
        self.assertEqual(kinds(check(seen(wrote("pr-review", "comment", "OLD")), self.effects(), before=before)), [("pr-review", "comment")])
        self.assertEqual(kinds(check(seen(wrote("controller", "dequeue")), self.effects(), before=before)), [("controller", "dequeue")])
        dropped = {"run": "r_01JA00", "item": ITEM, "started_at": self.MADE, "status": "completed"}
        self.assertEqual(kinds(check(seen(), self.effects(), [dropped], before=before, accounts=TOKEN)), [("workflow_token", "dispatch")])
        # A record first read late is dropped by when it was made: its credit does not outlast its own write. It is kept for
        # an hour past that, as the write it records came after its record's run began, and no more.
        at = lambda when: self.effects(written_=[written(("dequeue", ITEM, None, None, "applied"))], at={"p_01JA7Q": when})
        too_late = reconcile.carried([], at("2026-10-09T00:00:00Z"), seen(), self.NOW)
        self.assertEqual(reconcile.carried([{"reconciled": too_late}], self.effects(), seen(), self.NEXT)["items"], [])
        hour = "2026-10-10T23:00:00Z"
        self.assertEqual(SINCE, "2026-10-11T00:00:00Z")
        edge = reconcile.carried([], at(hour), seen(), self.NOW)
        self.assertEqual(len(reconcile.carried([{"reconciled": edge}], self.effects(), seen(), self.NEXT)["items"]), 1)
        self.assertEqual(check(seen(wrote("controller", "dequeue")), self.effects(), before=[{"now": self.NOW, "pull_requests": [], "reconciled": edge}])["unmatched"], [])
        past = reconcile.carried([], at("2026-10-10T22:59:59Z"), seen(), self.NOW)
        self.assertEqual(reconcile.carried([{"reconciled": past}], self.effects(), seen(), self.NEXT)["items"], [])
        self.assertEqual(kinds(check(seen(wrote("controller", "dequeue")), self.effects(), before=[{"now": self.NOW, "pull_requests": [], "reconciled": past}])),
                         [("controller", "dequeue")])
        # A key read long after its Run began still matches its write: it is dropped by when it was read.
        read_late = reconcile.carried([], self.effects(applied(("comment", "K", "applied")), at={self.RUN: "2026-10-09T00:00:00Z"}), seen(), self.NOW)
        self.assertEqual(check(seen(wrote("pr-review", "comment", "K")), self.effects(), before=[{"now": self.NOW, "pull_requests": [], "reconciled": read_late}])["unmatched"], [])
        # A stamp that is no time is read as now: it is never read as older than it is.
        odd = reconcile.carried([], self.effects(written_=[written(("dequeue", ITEM, None, None, "applied"))], at={"p_01JA7Q": "x"}), seen(), self.NOW)
        self.assertEqual(odd["items"][0]["at"], self.NOW)

    def test_a_pull_request_that_left_is_kept_until_the_window_passes_it(self):  # issue 787
        # Each pull request a pass first reads as left is stamped with now, whatever else could be read; the next passes
        # keep it, and read it, until the window passes the stamp; one that leaves again is stamped again.
        first = reconcile.carried([], None, seen(), self.NOW, gone=[9])
        self.assertEqual(first["left"], [{"number": 9, "at": self.NOW}])
        before = [{"now": self.NOW, "pull_requests": [], "reconciled": first}]
        self.assertEqual(reconcile.left(before, SINCE), [9])
        kept = reconcile.carried(before, recorded(), seen(), self.NEXT, gone=[7])
        self.assertEqual(kept["left"], [{"number": 9, "at": self.NOW}, {"number": 7, "at": self.NEXT}])
        self.assertEqual(reconcile.carried(before, recorded(), seen(), self.NEXT, gone=[9])["left"], [{"number": 9, "at": self.NEXT}])
        past = dict(seen(), since="2026-10-11T13:00:01Z")
        self.assertEqual(reconcile.carried(before, recorded(), past, self.NEXT)["left"], [])
        self.assertEqual(reconcile.left(before, "2026-10-11T13:00:01Z"), [])
        # A record written before it holds none, and keeps none.
        self.assertEqual(reconcile.left([{"now": self.NOW, "pull_requests": [], "reconciled": dict(self.NONE)}], SINCE), [])

    def test_a_record_that_holds_none_is_read_again_and_what_cannot_be_read_is_carried_on(self):
        # With no last record, or one written before this, nothing is known: everything in the window is read again.
        for before in (None, [], [{"now": self.NOW, "pull_requests": []}], [{"now": self.NOW, "pull_requests": [], "reconciled": None}]):
            self.assertEqual((reconcile.known(before), reconcile.owed(before)), ((set(), set()), []), before)
        # Only the last record is read.
        last = dict(self.NONE, runs=[{"id": self.RUN, "at": self.NOW}])
        first = dict(self.NONE, runs=[{"id": "r_01JA7R", "at": self.NOW}])
        self.assertEqual(reconcile.known([{"reconciled": first}, {"reconciled": last}])[0], {self.RUN})
        # What cannot be read carries on what the last record held, within the window, and reads nothing new; so does a
        # read with no list of what it read. An unreadable seen drops nothing.
        before = [{"now": self.NOW, "pull_requests": [], "reconciled": last}]
        for effects in (None, {"applied": "x"}, recorded([dict(applied(), effects="none")])):
            self.assertEqual(reconcile.carried(before, effects, seen(), self.NEXT), last, effects)
        self.assertEqual(reconcile.carried(before, recorded(), seen(), self.NEXT), last)
        old = dict(last, runs=[{"id": self.RUN, "at": "2026-10-09T00:00:00Z"}])
        self.assertEqual(reconcile.carried([{"reconciled": old}], None, None, self.NEXT), old)
        # So does a seen that is no seen/1: its `since` is not read.
        self.assertEqual(reconcile.carried([{"reconciled": old}], None, {"since": 7}, self.NEXT), old)
        # Carried keys still match where this pass's own read is short, which says so; a seen that cannot be read matches
        # nothing, and is short.
        held = dict(last, keys=[{"where": "applied", "type": "comment", "key": "L", "at": self.NOW}])
        before = [{"now": self.NOW, "pull_requests": [], "reconciled": held}]
        found = check(seen(wrote("pr-review", "comment", "L")), None, before=before)
        self.assertEqual((found["unmatched"], found["short"]), ([], True))
        self.assertTrue(check(None, self.effects(), before=before)["short"])
        # And a pass record holding it is a pass record; one with anything else in it is not.
        record = json.loads((ROOT / "examples" / "pass.json").read_text())
        self.assertEqual(validate(dict(record, reconciled=held), SCHEMAS["pass"], schemas=SCHEMAS), [])
        for odd in (dict(held, more=[]), {k: v for k, v in held.items() if k != "keys"}, {k: v for k, v in held.items() if k != "owed"},
                    dict(held, runs=[{"id": self.RUN}]), dict(held, passes=[{"id": "x", "attempt": 1, "at": self.NOW}]),
                    dict(held, passes=[{"id": 0, "attempt": 1, "at": self.NOW}]), dict(held, passes=[{"id": 1, "at": self.NOW}]),
                    dict(held, passes=[{"id": 1, "attempt": 0, "at": self.NOW}]), dict(held, owed=[0]),
                    dict(held, keys=[{"where": "elsewhere", "type": "comment", "key": "L", "at": self.NOW}]),
                    dict(held, items=[{"type": "dequeue", "item": "x", "count": 0, "at": self.NOW}])):
            self.assertNotEqual(validate(dict(record, reconciled=odd), SCHEMAS["pass"], schemas=SCHEMAS), [], odd)

    def test_a_record_too_wide_for_the_pass_record_leaves_it_short_and_never_refuses_a_pass(self):
        # applied/1 and written/1 are wider than what a pass record carries. One record's key or repo that does not fit is
        # not carried, so it never refuses a pass; it can match nothing GitHub says, and reconciliation says so.
        wide = "K" * 101
        for effects in (self.effects(applied(("comment", wide, "applied")), runs=[self.RUN]),
                        self.effects(written_=[written(("dequeue", dict(ITEM, repo="o/r x"), None, None, "applied"))])):
            out = reconcile.carried([], effects, seen(), self.NOW)
            self.assertEqual((out["keys"], out["items"]), ([], []))
            self.assertEqual(validate(dict(json.loads((ROOT / "examples" / "pass.json").read_text()), reconciled=out), SCHEMAS["pass"], schemas=SCHEMAS), [])
            self.assertTrue(check(seen(), effects)["short"])
        fits = "K" * 100
        out = reconcile.carried([], self.effects(applied(("comment", fits, "applied"))), seen(), self.NOW)
        self.assertEqual([k["key"] for k in out["keys"]], [fits])
        self.assertFalse(check(seen(), self.effects(applied(("comment", fits, "applied"))))["short"])
        # So too a Run's name that does not fit: it is read again, and is not carried.
        odd = "not-a-run"
        out = reconcile.carried([], self.effects(runs=[odd]), seen(), self.NOW)
        self.assertEqual(out["runs"], [])

    def test_a_run_still_running_makes_its_items_writes_short_not_unmatched(self):
        # A Run's apply writes before its job uploads its record, so a write on an item with a Run still running reads as
        # short until the record can be read. Any other write, the Controller's among them, does not wait.
        run = {"run": self.RUN, "item": ITEM, "started_at": self.MADE, "status": "in_progress"}
        other = dict(run, item=dict(ITEM, number=ITEM["number"] + 1))
        review = wrote("pr-review", "review", "K")
        accounts = dict(KNOWN, workflow_token=None)
        found = check(seen(review), recorded(), [run], accounts=accounts)
        self.assertEqual((found["unmatched"], found["short"]), ([], True))
        self.assertEqual(kinds(check(seen(review), recorded(), [other], accounts=accounts)), [("pr-review", "review")])
        self.assertEqual(kinds(check(seen(review), recorded(), [dict(run, status="completed")], accounts=accounts)), [("pr-review", "review")])
        self.assertFalse(check(seen(review), recorded(), [dict(run, status="completed")], accounts=accounts)["short"])
        self.assertEqual(kinds(check(seen(wrote("controller", "check_run", "S")), recorded(), [run], accounts=accounts)), [("controller", "check_run")])
        self.assertEqual(kinds(check(seen(wrote("approver", "push", "P", item=None)), recorded(), [run], accounts=accounts)), [("approver", "push")])


class CommentsGrant(unittest.TestCase):
    def test_the_comments_on_a_pull_request_are_read_with_pull_requests_read(self):
        # trials/P-56.json: the Controller's token, narrowed to pull_requests: read, reads a pull request's comments, each
        # with what adapters/seen.py reads of it, and GitHub names that permission as one it accepts. The canary is public,
        # so a token without the grant read them too, and the header is what says which grant serves them (decision 0068).
        fixture = json.loads((ROOT / "trials" / "P-56.json").read_text())
        self.assertEqual(fixture["verdict"], "pass")
        mint, read, revoke = fixture["exchanges"][:3]
        # The Controller's App minted the narrowed token, made the read with it, and revoked it.
        self.assertEqual(mint["response"]["status"], 201)
        self.assertEqual(mint["request"]["body"]["permissions"], {"pull_requests": "read"})
        self.assertEqual(mint["request"]["body"]["repositories"], [read["request"]["call"].split("/")[3]])
        grants = json.loads((ROOT / "trials" / "P-39.grants.json").read_text())
        listed = [e for e in grants["exchanges"] if e["request"]["call"] == "GET /orgs/combsmith/installations"][0]
        installation = [i["id"] for i in listed["response"]["body"]["installations"] if i["app_slug"] == "combsmith-sf-controller"][0]
        self.assertIn("/app/installations/%d/access_tokens" % installation, mint["request"]["call"])
        self.assertEqual({e["request"]["as"]["name"] for e in (mint, read, revoke)}, {"combsmith-sf-controller"})
        self.assertEqual(revoke["response"]["status"], 204)
        self.assertIn("/comments?since=", read["request"]["call"])
        self.assertEqual(read["response"]["status"], 200)
        self.assertIn("pull_requests=read", read["response"]["headers"]["x-accepted-github-permissions"].split("; "))
        self.assertTrue(read["response"]["body"])
        for comment in read["response"]["body"]:
            # What the pass condition asks of each and adapters/seen.py reads of it.
            self.assertIsInstance(comment["id"], int)
            self.assertIsInstance(comment["node_id"], str)
            self.assertIsInstance(comment["created_at"], str)
            self.assertIsInstance(comment["user"]["id"], int)
            self.assertIsInstance(comment["user"]["type"], str)
        # And no comment's text, which comes from outside, in either read.
        for exchange in fixture["exchanges"]:
            if isinstance(exchange["response"]["body"], list):
                self.assertFalse([c for c in exchange["response"]["body"] if "body" in c])


if __name__ == "__main__":
    unittest.main()
