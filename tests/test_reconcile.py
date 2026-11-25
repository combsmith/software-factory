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
             roles={"pr-review": {"id": 5000002, "type": "Bot", "login": "combsmith-sf-pr-review[bot]"}},
             lenses=[{"lens": "pr-review", "login": "combsmith-sf-pr-review[bot]", "id": 5000002}])
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

    def test_a_write_on_an_issue_is_matched_as_one_on_a_pull_request_is(self):  # issue 837
        # A Factory identity's write on an issue is matched to the Effect that recorded it, by its key, as on a pull
        # request; one no Effect recorded is the alert, named by the issue's own page. No Effect yet records a label
        # on an issue, so the Controller's is unmatched whatever was recorded.
        issue = dict(ITEM, type="issue")
        comment, done = wrote("pr-review", "comment", "IC_c", item=issue), applied(("comment", "IC_c", "applied"))
        found = check(seen(comment), recorded([done]))
        self.assertEqual((found["unmatched"], found["short"], reconcile.alerts(found)), ([], False, []))
        everything = recorded([done], [written(("status_on_item", issue, None, "K", "applied"), ("dequeue", issue, None, None, "applied"))])
        for write, other in ((comment, recorded()), (wrote("controller", "label", item=issue), everything),
                             (wrote("controller", "close", item=issue), everything),
                             (wrote("approver", "comment", "IC_c", item=issue), everything)):
            found = check(seen(write), other)
            self.assertEqual((kinds(found), reconcile.alerts(found)), ([(write["by"], write["kind"])], ["write_unmatched"]), write)
            self.assertEqual(reconcile.entries(found)[0]["item"], URL.replace("/pull/", "/issues/"), write)
        # What was seen of an issue not whole is short, and says so.
        self.assertEqual(reconcile.alerts(check(seen(whole=False))), ["reconciliation_unreadable"])

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
    """A person's resolution of a thread a Role opened, matched to the Kernel's act that named the thread (decision 0223)."""

    def test_a_hands_resolution_of_a_roles_thread_is_matched_to_the_act_the_last_pass_named(self):  # issue 854
        # A hand's resolution matches the act of the last pass that decided the item, or is unmatched (decision 0223).
        found = check(seen(HAND), before=[passed()])
        self.assertEqual((found["unmatched"], found["unjudged"], found["short"], reconcile.alerts(found)), ([], [], False, []))
        review = dict(state="verifying", reason="awaiting_review", outcome="admit", action=None)
        for why, before in (("another thread", [passed(["PRRT_u"])]), ("no thread", [passed([])]),
                            ("an act a brake held", [passed(outcome="defer")]),
                            ("another act", [passed(action="enqueue")]),
                            ("a Decision that is no act", [passed(**review)]),
                            # The last pass that decided the item is the one read: the head may have moved since an earlier.
                            ("an act an earlier pass named and the last did not", [passed(), passed([])]),
                            ("an act an earlier pass named, and the last a review", [passed(), passed(**review)])):
            with self.subTest(why):
                found = check(seen(HAND), before=before)
                self.assertEqual((kinds(found), found["unjudged"], found["short"]), ([("hand", "resolution")], [], False))
                self.assertEqual(reconcile.alerts(found), ["hand_unmatched"])
                self.assertEqual(reconcile.entries(found), [{"alert": "hand_unmatched", "by": "hand", "write": "resolution",
                                                             "item": URL, "key": "PRRT_t"}])
        # A pass that did not decide the item, one it could not read, says nothing of it: the one before it is read.
        self.assertEqual(check(seen(HAND), before=[passed([]), passed()])["unmatched"], [])
        found = check(seen(HAND), before=[passed(), passed([], item=OTHER)])
        self.assertEqual((found["unmatched"], found["unjudged"], found["short"]), ([], [], False))
        self.assertEqual(kinds(check(seen(HAND), before=[passed([]), passed(item=OTHER)])), [("hand", "resolution")])
        # Each thread an act names is matched (Astra, issue 887).
        self.assertEqual(check(seen(HAND), before=[passed(["PRRT_a", "PRRT_t"])])["unmatched"], [])
        # A pass that read the item's writes short could not see a resolution older than its Decision: the act before it
        # matches, and no pass before it that read the item whole.
        blind = passed([], action=None, outcome="admit", state="verifying", reason="awaiting_review")
        blind["reconciled"]["owed"] = [42]
        for before, found_ in (([passed(), blind], []), ([passed(), passed([]), blind], [("hand", "resolution")]),
                               ([passed(hands=None), blind], [])):
            self.assertEqual(kinds(check(seen(HAND), before=before)), found_, before)
        # What such a pass named itself still matches where nothing before it can judge the rest.
        blind_t = passed()
        blind_t["reconciled"]["owed"] = [42]
        for before in ([blind_t], [passed(hands=None), blind_t]):
            found = check(seen(HAND), before=before)
            self.assertEqual((found["unmatched"], found["unjudged"], found["short"]), ([], [], False), before)
        # The item's Decision is read wherever it stands in its record.
        second = passed(item=OTHER)
        second["pull_requests"].append(passed([])["pull_requests"][0])
        self.assertEqual(kinds(check(seen(HAND), before=[second])), [("hand", "resolution")])
        # A resolution whose thread or item cannot be read is matched to nothing, and a Run on its item makes it no Run's.
        for odd in (dict(HAND, key=None), dict(HAND, item=None), dict(HAND, kind="comment")):
            self.assertEqual(kinds(check(seen(odd), before=[passed()])), [("hand", odd["kind"])], odd)
        running = [{"run": "r_01JA7Q", "item": ITEM, "started_at": AT, "status": "in_progress"}]
        found = check(seen(HAND), r=running, before=[passed([])], accounts=dict(KNOWN, workflow_token=None))
        self.assertEqual((kinds(found), found["short"]), ([("hand", "resolution")], False))
        # A hand's resolution has its own alert, so that one standing never hides an identity's write nobody recorded.
        both = check(seen(HAND, wrote("approver", "approval", "PRR_a")), before=[passed([])])
        self.assertEqual(reconcile.alerts(both), ["hand_unmatched", "write_unmatched"])
        self.assertEqual(reconcile.alerts(check(seen(wrote("approver", "approval", "PRR_a")), before=[passed()])),
                         ["write_unmatched"])
        # A Role named `hand` could not be told from a person: no identity is known, and it is short.
        named = dict(KNOWN, roles=dict(KNOWN["roles"], hand=KNOWN["roles"]["pr-review"]))
        self.assertTrue(check(seen(), before=[passed()], accounts=named)["short"])
        # A Lens whose account is not its Role's, by its id or its type, or that has no Role, is a thread the facts read as
        # that Lens's and the seen port as no Role's: a person's resolution of it is no write, so it is short (issue 887).
        lens = KNOWN["lenses"][0]
        qa = {"id": 6000001, "type": "Bot", "login": "combsmith-sf-qa-lead[bot]"}
        for why, accounts in (("another id", dict(KNOWN, lenses=[dict(lens, id=999000111)])),
                              ("a Role of another type", dict(KNOWN, roles={"pr-review": dict(KNOWN["roles"]["pr-review"], type="User")})),
                              ("no Role", dict(KNOWN, lenses=[dict(lens, lens="qa-lead")])),
                              ("a second Lens", dict(KNOWN, roles=dict(KNOWN["roles"], **{"qa-lead": qa}),
                                                     lenses=[lens, {"lens": "qa-lead", "login": qa["login"], "id": 6000002}])),
                              ("a Lens of no name", dict(KNOWN, lenses=[dict(lens, lens=[])])), ("a Lens that is none", dict(KNOWN, lenses=[None]))):
            self.assertTrue(check(seen(), before=[passed()], accounts=accounts)["short"], why)
        self.assertFalse(check(seen(), before=[passed()], accounts=dict(KNOWN, lenses=[]))["short"])
        self.assertFalse(check(seen(), before=[passed()],
                               accounts=dict(KNOWN, roles=dict(KNOWN["roles"], **{"qa-lead": qa}),
                                             lenses=[lens, {"lens": "qa-lead", "login": qa["login"], "id": 6000001}]))["short"])
        # And controller/1 refuses the name, so that no such configuration reaches a pass (issue 887).
        config = json.loads((ROOT / "config" / "controller.json").read_text())
        self.assertEqual(validate(config, SCHEMAS["controller"], schemas=SCHEMAS), [])
        for account in (config["accounts"]["roles"]["pr-review"], None):
            config["accounts"]["roles"]["hand"] = account
            self.assertEqual(len(validate(config, SCHEMAS["controller"], schemas=SCHEMAS)), 1, account)
        # A resolution an identity made is no hand's, whatever it resolved: it is never judged as one (issue 887).
        role = wrote("pr-review", "resolution", "PRRT_t", at=None)
        self.assertEqual([check(seen(role), before=[passed(hands=None)])[k] for k in ("unjudged", "short")], [[], False])
        self.assertEqual(reconcile.carried([passed()], dict(recorded(), read={"runs": [], "passes": []}, at={}),
                                           seen(role), NOW)["hands"], [])

    def test_a_hands_resolution_once_matched_is_carried_while_it_is_seen(self):  # issue 854
        # Once matched, a thread is carried, stamped again at each pass that sees it, and matches from then on.
        effects = dict(recorded(), read={"runs": [], "passes": []}, at={})
        held = reconcile.carried([passed()], effects, seen(HAND), NOW)
        self.assertEqual(held["hands"], [{"key": "PRRT_t", "at": NOW}])
        later = dict(passed([], now=NOW), reconciled=held)
        found = check(seen(HAND), before=[later])
        self.assertEqual((found["unmatched"], found["unjudged"], found["short"], reconcile.alerts(found)), ([], [], False, []))
        self.assertEqual(kinds(check(seen(dict(HAND, key="PRRT_u")), before=[later])), [("hand", "resolution")])  # its own
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
        record = dict(passed(), reconciled=held, alerts=["hand_unmatched"])
        self.assertEqual(validate(record, SCHEMAS["pass"], schemas=SCHEMAS), [])
        # And no other: a key that is no thread's, a time that is none, and anything beside the two (issue 887).
        for odd in ({"key": "PRRT t", "at": NOW}, {"key": "PRRT_t", "at": "2026-13-11T12:00:00Z"}, {"key": "PRRT_t"},
                    {"at": NOW}, {"key": "A" * 101, "at": NOW}, {"key": "PRRT_t", "at": NOW, "by": "hand"}, "PRRT_t"):
            bad = dict(record, reconciled=dict(held, hands=[odd]))
            self.assertEqual(len(validate(bad, SCHEMAS["pass"], schemas=SCHEMAS)), 1, odd)
        longest = dict(record, reconciled=dict(held, hands=[{"key": "A" * 100, "at": NOW}]))
        self.assertEqual(validate(longest, SCHEMAS["pass"], schemas=SCHEMAS), [])

    def test_a_hands_resolution_no_record_can_judge_is_short_once_carried_and_named(self):  # issue 854
        # Where no record can say whether an act named the thread, the pass is short, carries it and names it: with no
        # record before, one that carried no `hands`, or none that decided the item.
        effects = dict(recorded(), read={"runs": [], "passes": []}, at={})
        waved = [{"alert": "hand_unjudged", "by": "hand", "write": "resolution", "item": URL, "key": "PRRT_t"}]
        review = dict(state="verifying", reason="awaiting_review", outcome="admit", action=None)
        # The rule starts for an item where the record that decided it starts it, not where the last record does: one
        # written before it decided the item, and a later one that carries hands did not (issue 887).
        for before in ([], [passed(hands=None)], [passed([], hands=None)], [passed(item=OTHER), passed(item=OTHER)],
                       [passed(hands=None, **review), passed([], item=OTHER)],
                       # Nor does a last record that carried none, though it did not decide the item and an earlier did.
                       [passed(hands=["PRRT_t"], **review), passed([], item=OTHER, hands=None)],
                       # The record that decided the item is the one read, though an earlier one named the thread.
                       [passed(), passed(hands=None, **review), passed([], item=OTHER)]):
            found = check(seen(HAND), before=before)
            self.assertEqual((found["unmatched"], found["short"]), ([], True), before)
            self.assertEqual((reconcile.alerts(found), reconcile.entries(found)), (["reconciliation_unreadable"], waved))
            self.assertEqual(validate(waved[0], SCHEMAS["view-meta"]["$defs"]["entry"], schemas=SCHEMAS), [])
            held = reconcile.carried(before, effects, seen(HAND), NOW)
            self.assertEqual(held["hands"], [{"key": "PRRT_t", "at": NOW}])
            # The pass after it reads what was carried: matched, and short no more.
            after = check(seen(HAND), before=[dict(passed([], now=NOW), reconciled=held)])
            self.assertEqual((after["unmatched"], after["unjudged"], after["short"], reconcile.alerts(after)), ([], [], False, []))
        # A resolution whose thread cannot be read is unmatched even then, and never carried: `pass/1` holds no such key.
        nameless = seen(dict(HAND, key=None))
        self.assertEqual(kinds(check(nameless)), [("hand", "resolution")])
        self.assertEqual(reconcile.carried([], effects, nameless, NOW)["hands"], [])
        # With no hand's resolution seen, such a record leaves nothing short, and the next record carries none.
        self.assertFalse(check(seen(), before=[passed(hands=None)])["short"])
        self.assertEqual(reconcile.carried([passed(hands=None)], effects, seen(), NOW)["hands"], [])
        # Nor does a pass that could not read what was seen, or read it short, or the next would judge threads it never read.
        self.assertNotIn("hands", reconcile.carried([passed(hands=None)], effects, None, NOW))
        self.assertNotIn("hands", reconcile.carried([passed(hands=None)], effects, seen(HAND, whole=False), NOW))


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

    def test_an_issue_read_whole_by_its_end_is_named_once_as_information(self):  # decision 1145
        issue = dict(ITEM, type="issue", number=41)
        told = dict(seen(), gone=[{"item": issue, "answer": 404}, {"item": issue, "answer": 404},
                                  {"item": dict(issue, number=43), "answer": 410}])
        assert not validate(told, SCHEMAS["seen"], schemas=SCHEMAS)
        found = check(told)
        self.assertEqual((reconcile.alerts(found), found["short"]), ([], False))
        url = "https://github.com/%s/issues/%d"
        self.assertEqual(reconcile.entries(found), [{"alert": "issue_gone", "by": None, "write": "other", "item": url % (ITEM["repo"], n),
                                                     "key": code} for n, code in ((41, "404"), (43, "410"))])
        # Only an issue, and only a 404 or a 410, is one (Astra).
        for wrong in ({"item": dict(issue, type="pull_request"), "answer": 404}, {"item": issue, "answer": 403}):
            self.assertTrue(validate(dict(seen(), gone=[wrong]), SCHEMAS["seen"], schemas=SCHEMAS), wrong)
        # What was seen that cannot be read tells nothing.
        self.assertEqual(check(dict(told, schema="seen/2"))["gone"], [])


HEAD, OTHER_HEAD = "a" * 40, "b" * 40
GIVEN = "2026-10-11T12:30:00Z"


def approval(key="PRR_1", commit=HEAD, at=GIVEN, item=ITEM) -> dict:
    """The machine user's approval as the seen port reads it, with the commit it approved."""
    return dict(wrote("approver", "approval", key, item=item, at=at), commit=commit)


def decided_as(reason, head=HEAD, now="2026-10-11T12:00:00Z", item=ITEM, reconciled=None) -> dict:
    """A pass record before, holding the one Decision on `item` that reconciliation reads: its reason and its head."""
    entry = {"facts": {"item": dict(item)}, "decision": {"reason": reason}}
    if head is not None:
        entry["head"] = head
    record = {"now": now, "pull_requests": [entry]}
    if reconciled is not None:
        record["reconciled"] = reconciled
    return record


class HandApproval(unittest.TestCase):
    """The Maintainer's hand approval as the machine user, of a pull request only a person may approve, is reported as
    information and raises no alert; any other approval no Effect recorded is unmatched (decision 0241)."""

    def test_a_hand_approval_of_a_hand_pr_at_the_head_its_pass_read_is_information(self):
        for reason in ("model_lens_input_needs_person", "path_needs_person"):
            found = check(seen(approval()), before=[decided_as(reason)])
            self.assertEqual((found["unmatched"], found["short"]), ([], False), reason)
            self.assertEqual(found["hand"], [{"item": ITEM, "key": "PRR_1", "head": HEAD, "at": GIVEN}], reason)
            self.assertEqual(reconcile.alerts(found), [], reason)
            self.assertEqual(reconcile.entries(found), [{"alert": "hand_approval", "by": "approver", "write": "approval",
                                                         "item": URL, "key": "PRR_1"}], reason)

    def test_a_hand_approval_of_a_non_hand_pr_never_passes_as_information(self):
        # Any other wait, or none, is no hand PR's: the approval is unmatched and raises the alert, as 0061 has it.
        for reason in ("awaiting_review", "approval_due", "check_failed", None):
            found = check(seen(approval()), before=[decided_as(reason)])
            self.assertEqual((kinds(found), found["hand"]), ([("approver", "approval")], []), reason)
            self.assertEqual(reconcile.alerts(found), ["write_unmatched"], reason)

    def test_a_second_approval_of_the_same_head_is_unmatched(self):
        first, second = approval("PRR_1"), approval("PRR_2", at="2026-10-11T12:40:00Z")
        found = check(seen(second, first), before=[decided_as("model_lens_input_needs_person")])
        self.assertEqual([h["key"] for h in found["hand"]], ["PRR_1"])
        self.assertEqual([u["key"] for u in found["unmatched"]], ["PRR_2"])
        # Each head has its own: an approval of the pull request's next head, as its own pass read it, stands too.
        later = approval("PRR_3", commit=OTHER_HEAD, at="2026-10-11T13:10:00Z")
        before = [decided_as("model_lens_input_needs_person"),
                  decided_as("model_lens_input_needs_person", OTHER_HEAD, now="2026-10-11T13:00:00Z")]
        self.assertEqual([h["key"] for h in check(seen(first, later), before=before)["hand"]], ["PRR_1", "PRR_3"])

    def test_an_unmatched_approval_takes_its_head(self):
        # An approval read unmatched, its pass reading no hand wait, still takes its head: one after it is a second,
        # in the same pass and, carried, in the passes after, until the window passes its leaving (decision 0241).
        hand = "model_lens_input_needs_person"
        first, second = approval("PRR_1", at="2026-10-11T11:30:00Z"), approval("PRR_2")
        before = [decided_as("awaiting_review", now="2026-10-11T11:00:00Z"), decided_as(hand)]
        found = check(seen(first, second), before=before)
        self.assertEqual(([u["key"] for u in found["unmatched"]], found["hand"]), (["PRR_1", "PRR_2"], []))
        self.assertEqual([t["key"] for t in found["taken"]], ["PRR_1", "PRR_2"])
        held = dict(reconcile.EMPTY, taken=[{"key": "PRR_1", "item": URL, "head": HEAD}, {"key": "PRR_2", "item": URL, "head": HEAD}])
        # The first is out of the window and of what was seen; the second, alone, is still a second.
        later = [decided_as(hand, reconciled=held)]
        self.assertEqual(kinds(check(seen(second), before=later)), [("approver", "approval")])
        # An approval with no commit takes no head, as it can be no hand approval's.
        self.assertEqual(check(seen(approval("PRR_3", commit=None)), before=before)["taken"], [])

    def test_a_head_is_taken_by_any_approval_and_none_is_read_from_a_short_read_or_a_tie(self):
        hand = "model_lens_input_needs_person"
        before = [decided_as("awaiting_review", now="2026-10-11T11:00:00Z"), decided_as(hand)]
        # The Factory's own approval, matched to its Effect, takes its head as an unmatched one does.
        matched = recorded([applied(("approve", "PRR_1", "applied"))])
        found = check(seen(approval("PRR_1", at="2026-10-11T11:30:00Z"), approval("PRR_2")), matched, before=before)
        self.assertEqual(([u["key"] for u in found["unmatched"]], found["hand"]), (["PRR_2"], []))
        self.assertEqual([t["key"] for t in found["taken"]], ["PRR_1", "PRR_2"])
        # So does one with no key, in the pass that reads it.
        keyless = check(seen(approval(None, at="2026-10-11T12:20:00Z"), approval("PRR_2")), before=[decided_as(hand)])
        self.assertEqual((keyless["hand"], len(keyless["unmatched"])), ([], 2))
        # Two approvals of a head in the same second are both unmatched: neither can be told first.
        tie = check(seen(approval("PRR_z"), approval("PRR_a")), before=[decided_as(hand)])
        self.assertEqual((tie["hand"], sorted(u["key"] for u in tie["unmatched"])), ([], ["PRR_a", "PRR_z"]))
        # Nor can they where one's time cannot be read, matched or not; a tie is of one pull request's head alone.
        unordered = check(seen(approval("PRR_1", at="2026-10-11T12:20:00Z"), approval("PRR_2", at="2026-11-31T12:00:00Z")),
                          recorded([applied(("approve", "PRR_2", "applied"))]), before=[decided_as(hand)])
        self.assertEqual((unordered["hand"], kinds(unordered)), ([], [("approver", "approval")]))
        both = dict(decided_as(hand), pull_requests=decided_as(hand)["pull_requests"] + decided_as(hand, item=OTHER)["pull_requests"])
        apart = check(seen(approval("PRR_a"), approval("PRR_b", item=OTHER)), before=[both])
        self.assertEqual(([h["key"] for h in apart["hand"]], apart["unmatched"]), (["PRR_a", "PRR_b"], []))
        # A read that is short, of what was seen or of what was recorded, makes no hand approval.
        for name, s_, e in (("seen short", seen(approval(), whole=False), recorded()),
                            ("recorded short", seen(approval()), recorded(whole=False)),
                            ("recorded unread", seen(approval()), None)):
            short = check(s_, e, before=[decided_as(hand)])
            self.assertEqual((kinds(short), short["hand"], short["short"]), ([("approver", "approval")], [], True), name)
        # A carried one is read as one only on a whole read, while the review reads as it did, and alone in its second.
        first = check(seen(approval()), before=[decided_as(hand)])
        held = dict(reconcile.EMPTY, hand=[{"key": "PRR_1", "item": URL, "head": HEAD, "at": GIVEN}])
        self.assertEqual(first["hand"], [{"item": ITEM, "key": "PRR_1", "head": HEAD, "at": GIVEN}])
        later = [decided_as("awaiting_review", item=OTHER, reconciled=held)]
        self.assertEqual(len(check(seen(approval()), before=later)["hand"]), 1)
        self.assertEqual(kinds(check(seen(approval(), whole=False), before=later)), [("approver", "approval")])
        self.assertEqual(len(check(seen(approval(), approval("PRR_2")), before=later)["unmatched"]), 2)
        # A carried key whose review reads otherwise now is not judged again as a new one, though a pass that would
        # read it so is at hand.
        moved = [dict(decided_as(hand, now="2026-10-11T12:35:00Z"), reconciled=held)]
        self.assertEqual(kinds(check(seen(approval(at="2026-10-11T12:40:00Z")), before=moved)), [("approver", "approval")])
        # A short read found in the writes themselves, a Run still running on another item, counts too.
        role = wrote("pr-review", "comment", "IC_1", item=OTHER, at=GIVEN)
        running = [{"run": "r_01JA7Q", "item": OTHER, "started_at": GIVEN, "status": "in_progress"}]
        busy = check(seen(approval(), role), r=running, before=[decided_as(hand)])
        self.assertEqual((busy["hand"], busy["short"]), ([], True))
        # So does one found in the Runs, once the pass job's token is an identity: a list that cannot be read, or a
        # re-run whose re-runner cannot be read, read before any approval is judged.
        rerun = [{"run": "r_01JA7R", "item": OTHER, "started_at": GIVEN, "dispatched_at": GIVEN, "status": "completed",
                  "rerun_by_dispatcher": None}]
        for name, r_ in (("runs unread", None), ("re-runner unread", rerun)):
            token = check(seen(approval()), r=r_, before=[decided_as(hand)], accounts=TOKEN)
            self.assertEqual((("approver", "approval") in kinds(token), token["hand"], token["short"]), (True, [], True),
                             name)
        # The Factory's own approval, matched, is neither unmatched nor a hand approval, but takes its head.
        own = check(seen(approval()), recorded([applied(("approve", "PRR_1", "applied"))]), before=[decided_as(hand)])
        self.assertEqual((own["unmatched"], own["hand"], [t["key"] for t in own["taken"]]), ([], [], ["PRR_1"]))
        # A Role's approval takes its head too: the machine user's after it is a second.
        first_role = check(seen(dict(wrote("pr-review", "approval", "PRR_9", at="2026-10-11T12:20:00Z"), commit=HEAD),
                                approval("PRR_2")), before=[decided_as(hand)])
        self.assertEqual((first_role["hand"], [u["key"] for u in first_role["unmatched"]]), ([], ["PRR_9", "PRR_2"]))
        for changed in (approval(commit=None), approval(commit=OTHER_HEAD), approval(at="2026-10-11T12:31:00Z")):
            self.assertEqual(kinds(check(seen(changed), before=later)), [("approver", "approval")], changed)

    def test_hand_and_taken_are_carried_until_the_window_passes_their_leaving(self):
        hand = "model_lens_input_needs_person"
        found = check(seen(approval()), before=[decided_as(hand)])
        held = reconcile.carried([decided_as(hand)], recorded(), seen(), NOW, hand=found["hand"], taken=found["taken"])
        self.assertEqual((held["hand"], "taken" in held), ([{"key": "PRR_1", "item": URL, "head": HEAD, "at": GIVEN}], False))
        record = dict(json.loads((ROOT / "examples" / "pass.json").read_text()), reconciled=held)
        self.assertEqual(validate(record, SCHEMAS["pass"], schemas=SCHEMAS), [])
        # Kept, once, however old, while the pull request is open; read again, it is not carried twice.
        old = dict(held, hand=[dict(held["hand"][0], at="2026-10-09T00:00:00Z")])
        aged = [dict(decided_as(hand), reconciled=old)]
        self.assertEqual(reconcile.carried(aged, recorded(), seen(), NOW, hand=found["hand"])["hand"], old["hand"])
        # An unmatched approval's head is carried too, a keyless one's among them, once each.
        second = check(seen(approval("PRR_2"), approval(None, at="2026-10-11T12:40:00Z")), before=aged)
        self.assertEqual([t["key"] for t in second["taken"]], ["PRR_2", None])
        taken = reconcile.carried(aged, recorded(), seen(), NOW, taken=second["taken"])
        self.assertEqual(taken["taken"], [{"key": "PRR_2", "item": URL, "head": HEAD}, {"key": None, "item": URL, "head": HEAD}])
        self.assertEqual(validate(dict(record, reconciled=taken), SCHEMAS["pass"], schemas=SCHEMAS), [])
        again = [dict(decided_as(hand), reconciled=taken)]
        self.assertEqual(reconcile.carried(again, recorded(), seen(), NOW, taken=second["taken"])["taken"], taken["taken"])
        # One read as the hand is not carried as taken too, whichever pass read it so.
        reread = check(seen(approval(), whole=False), before=aged)["taken"]
        self.assertEqual([t["key"] for t in reread], ["PRR_1"])
        self.assertNotIn("taken", reconcile.carried(aged, recorded(), seen(), NOW, taken=reread))
        was = [dict(decided_as(hand), reconciled=reconcile.carried([decided_as(hand)], recorded(), seen(), NOW, taken=reread))]
        self.assertEqual([h["key"] for h in check(seen(approval()), before=was)["hand"]], ["PRR_1"])
        now_hand = reconcile.carried(was, recorded(), seen(), NOW, hand=found["hand"])
        self.assertEqual((now_hand["hand"], "taken" in now_hand), (held["hand"], False))
        # A carried hand whose review now reads another head keeps that head taken.
        moved = check(seen(approval(commit=OTHER_HEAD)), before=aged)["taken"]
        self.assertEqual(reconcile.carried(aged, recorded(), seen(), NOW, taken=moved)["taken"],
                         [{"key": "PRR_1", "item": URL, "head": OTHER_HEAD}])
        # Two hands new in one pass are both carried; a keyless head carried alone keeps its head taken.
        two = reconcile.carried([decided_as(hand)], recorded(), seen(), NOW, hand=found["hand"] + [dict(found["hand"][0], key="PRR_3")])
        self.assertEqual([e["key"] for e in two["hand"]], ["PRR_1", "PRR_3"])
        keyless = [decided_as(hand, reconciled=dict(reconcile.EMPTY, taken=[{"key": None, "item": URL, "head": HEAD}]))]
        self.assertEqual(check(seen(approval("PRR_2")), before=keyless)["hand"], [])
        # Two keyless approvals of a head in one pass are carried as one.
        twice = check(seen(approval(None, at="2026-10-11T12:40:00Z"), approval(None, at="2026-10-11T12:45:00Z")), before=aged)
        self.assertEqual(reconcile.carried(aged, recorded(), seen(), NOW, taken=twice["taken"])["taken"],
                         [{"key": None, "item": URL, "head": HEAD}])
        # A matched approval's head and a Role's are carried as an unmatched one's is.
        role = dict(wrote("pr-review", "approval", "PRR_9", at="2026-10-11T12:20:00Z"), commit=HEAD)
        own = check(seen(approval("PRR_4"), role), recorded([applied(("approve", "PRR_4", "applied"))]), before=[decided_as(hand)])
        self.assertEqual(sorted(t["key"] for t in reconcile.carried([decided_as(hand)], recorded(), seen(), NOW,
                                                                    taken=own["taken"])["taken"]), ["PRR_4", "PRR_9"])
        # Two keyless approvals of two heads are two.
        apart = seen(approval(None, at="2026-10-11T12:40:00Z"), approval(None, commit=OTHER_HEAD, at="2026-10-11T12:45:00Z"))
        heads = reconcile.carried(aged, recorded(), seen(), NOW, taken=check(apart, before=aged)["taken"])["taken"]
        self.assertEqual([t["head"] for t in heads], [HEAD, OTHER_HEAD])
        # A short read drops neither, and carries a head it took new.
        fresh_short = check(seen(approval(None), whole=False), before=[decided_as(hand)])
        self.assertEqual((fresh_short["hand"], fresh_short["short"]), ([], True))
        for name, effects, s in (("effects unread", None, seen()), ("seen unread", recorded(), None),
                                 ("seen short", recorded(), seen(whole=False))):
            short = reconcile.carried(again, effects, s, "2026-10-13T12:00:00Z")
            self.assertEqual((short["hand"], short["taken"]), (taken["hand"], taken["taken"]), name)
            self.assertEqual(reconcile.carried([decided_as(hand)], effects, s, NOW, taken=fresh_short["taken"])["taken"],
                             [{"key": None, "item": URL, "head": HEAD}], name)
        # One read as leaving keeps its own, and what is new for it is carried.
        other = [{"key": None, "item": URL.replace("/42", "/43"), "head": HEAD}]
        theirs = [dict(taken["hand"][0], key="PRR_8", item=other[0]["item"])]
        both = dict(taken, taken=taken["taken"] + other, hand=taken["hand"] + theirs)
        new = [{"key": "PRR_6", "item": ITEM, "head": OTHER_HEAD}]
        leaving = reconcile.carried([dict(decided_as(hand), reconciled=both)], recorded(), seen(), NOW, gone=[42], taken=new,
                                   hand=[dict(found["hand"][0], key="PRR_3")])
        self.assertEqual(([e["key"] for e in leaving["hand"]], [e["key"] for e in leaving["taken"]], leaving["left"]),
                         (["PRR_1", "PRR_8", "PRR_3"], ["PRR_2", None, None, "PRR_6"], [{"number": 42, "at": NOW}]))
        stamped = dict(reconcile.EMPTY, left=[{"number": 42, "at": NOW}])
        fresh = reconcile.carried([dict(decided_as(hand), reconciled=stamped)], recorded(), seen(), NOW,
                                  hand=found["hand"], taken=second["taken"])
        self.assertEqual((fresh["hand"], [t["key"] for t in fresh["taken"]]), (held["hand"], ["PRR_2", None]))
        # Kept so by the passes after, while its leaving is held, by the same window.
        later = reconcile.carried([dict(decided_as(hand), reconciled=leaving)], recorded(), seen(), "2026-10-11T14:00:00Z")
        self.assertEqual((later["hand"], later["taken"], later["left"]), (leaving["hand"], leaving["taken"], leaving["left"]))
        # Dropped by the pass whose window passes its leaving, with what is new for it, another's kept.
        aged = [dict(decided_as(hand), reconciled=dict(leaving, left=[{"number": 42, "at": EARLY}]))]
        past = reconcile.carried(aged, recorded(), seen(), NOW, hand=[dict(found["hand"][0], key="PRR_5")], taken=new)
        self.assertEqual(([e["key"] for e in past["hand"]], [e["key"] for e in past["taken"]], past["left"]),
                         (["PRR_8"], [None], []))
        alone = [dict(decided_as(hand), reconciled=dict(taken, left=[{"number": 42, "at": EARLY}]))]
        for name in ("hand", "taken"):
            self.assertNotIn(name, reconcile.carried(alone, recorded(), seen(), NOW), name)
        # A read of what was seen that cannot be read reads no window, and drops nothing.
        unread = reconcile.carried(aged, recorded(), None, NOW)
        self.assertEqual((unread["hand"], unread["taken"]), (leaving["hand"], leaving["taken"]))
        # Reopened, or leaving again, it keeps its own, as it does when another repository's of that number is read open.
        reopened = reconcile.carried(aged, recorded(), seen(), NOW, open_=[URL])
        self.assertEqual((reopened["hand"], reopened["taken"], reopened["left"]), (leaving["hand"], leaving["taken"], []))
        again_ = reconcile.carried(aged, recorded(), seen(), NOW, gone=[42])
        self.assertEqual((again_["hand"], again_["taken"], again_["left"]),
                         (leaving["hand"], leaving["taken"], [{"number": 42, "at": NOW}]))
        elsewhere = reconcile.carried(aged, recorded(), seen(), NOW, open_=[URL.replace("software-factory", "elsewhere")])
        self.assertEqual((elsewhere["hand"], elsewhere["taken"], elsewhere["left"]), (leaving["hand"], leaving["taken"], []))
        # Only that number's rows: another whose leaving the window passed drops though one is read open.
        two_aged = [dict(decided_as(hand), reconciled=dict(leaving, left=[{"number": n, "at": EARLY} for n in (42, 43)]))]
        one = reconcile.carried(two_aged, recorded(), seen(), NOW, open_=[URL])
        self.assertEqual((one["hand"], one["taken"], one["left"]),
                         ([e for e in leaving["hand"] if not e["item"].endswith("/43")],
                          [e for e in leaving["taken"] if not e["item"].endswith("/43")], []))
        self.assertNotIn("hand", reconcile.carried([], recorded(), seen(), NOW))
        # Read open inside the window, it keeps no stamp of its leaving (issue 1191); an issue of its number is no reopening.
        inside = [dict(decided_as(hand), reconciled=dict(leaving, left=leaving["left"] + [{"number": 43, "at": GIVEN}]))]
        back = reconcile.carried(inside, recorded(), seen(), NOW, open_=[URL])
        self.assertEqual((back["hand"], back["taken"], back["left"]),
                         (leaving["hand"], leaving["taken"], [{"number": 43, "at": GIVEN}]))
        issue = reconcile.carried(inside, recorded(), seen(), NOW, open_=[URL.replace("/pull/", "/issues/")])
        self.assertEqual(issue["left"], inside[0]["reconciled"]["left"])
        # Both read open and one newly left in one pass, with no window read: the newly left alone is stamped.
        mixed = reconcile.carried(inside, recorded(), None, NOW, gone=[44], open_=[URL, URL.replace("/42", "/43")])
        self.assertEqual(mixed["left"], [{"number": 44, "at": NOW}])
        # Another repository's row of that number, or one spelled otherwise, stays for good: a leaving is ours alone (issue 1190).
        far, home = URL.replace("combsmith/", "elsewhere/"), "combsmith/software-factory"
        cased = URL.replace(home, "Combsmith/Software-Factory")
        foreign = dict(leaving, hand=leaving["hand"] + [dict(leaving["hand"][0], key="PRR_F", item=far)],
                       taken=leaving["taken"] + [{"key": None, "item": i, "head": HEAD} for i in (far, cased)],
                       left=[{"number": 42, "at": EARLY}])
        kept = reconcile.carried([dict(decided_as(hand), reconciled=foreign)], recorded(), seen(), NOW, home=home)
        self.assertEqual(([e["key"] for e in kept["hand"]], [e["item"] for e in kept["taken"]]),
                         (["PRR_8", "PRR_F"], [other[0]["item"], far, cased]))
        # Any pull request of that number read open clears the stamp, a home spelled otherwise among them, and keeps
        # the home's rows in the very pass whose window passes their leaving.
        for spelled in (far, cased):
            self.assertEqual(reconcile.carried(inside, recorded(), seen(), NOW, open_=[spelled], home=home)["left"],
                             [{"number": 43, "at": GIVEN}], spelled)
            same = reconcile.carried(aged, recorded(), seen(), NOW, open_=[spelled], home=home)
            self.assertEqual((same["hand"], same["taken"], same["left"]), (leaving["hand"], leaving["taken"], []), spelled)
        # The home as the configuration spells it, in any case, is the only one ours.
        upper = reconcile.carried([dict(decided_as(hand), reconciled=foreign)], recorded(), seen(), NOW,
                                  home="Combsmith/Software-Factory")
        self.assertEqual(([e["key"] for e in upper["hand"]], [e["item"] for e in upper["taken"]]),
                         (["PRR_1", "PRR_8", "PRR_3", "PRR_F"], [e["item"] for e in leaving["taken"]] + [far]))
        # What is new is judged so too: another repository's head is carried, and a home hand read in a new spelling.
        aged_home = [dict(decided_as(hand), reconciled=dict(reconcile.EMPTY, left=[{"number": 42, "at": EARLY}],
                                                              hand=[dict(held["hand"][0])]))]
        heads_new = [{"key": None, "item": dict(ITEM, repo=r), "head": HEAD} for r in ("elsewhere/software-factory", home)]
        renamed = dict(found["hand"][0], item=dict(ITEM, repo="Combsmith/Software-Factory"))
        new_ = reconcile.carried(aged_home, recorded(), seen(), NOW, taken=heads_new, hand=[renamed], home=home)
        self.assertEqual((new_["taken"], [(e["key"], e["item"]) for e in new_["hand"]]),
                         ([{"key": None, "item": far, "head": HEAD}], [("PRR_1", cased)]))

    def test_an_approval_of_a_head_the_pass_did_not_decide_or_whose_commit_cannot_be_read_is_unmatched(self):
        hand = "model_lens_input_needs_person"
        for name, write, before in (
                ("another head", approval(commit=OTHER_HEAD), [decided_as(hand)]),
                ("no commit", approval(commit=None), [decided_as(hand)]),
                ("no commit, and no head on the entry", approval(commit=None), [decided_as(hand, head=None)]),
                ("no time", approval(at=None), [decided_as(hand)]),
                ("no head on the entry", approval(), [decided_as(hand, head=None)]),
                ("another item decided", approval(), [decided_as(hand, item=OTHER)]),
                ("no record before", approval(), []),
                ("only a record after", approval(), [decided_as(hand, now="2026-10-11T12:45:00Z")]),
                # The last pass before the approval is read, not an earlier one.
                ("the last before is no hand wait", approval(),
                 [decided_as(hand, now="2026-10-11T11:00:00Z"), decided_as("awaiting_review")]),
                ("no key", approval(key=None), [decided_as(hand)]),
                ("a pass at the very second", approval(), [decided_as(hand, now=GIVEN)]),
                # The last pass before it is read, though an earlier one decided the item.
                ("the last before did not decide it", approval(),
                 [decided_as(hand, now="2026-10-11T11:00:00Z"), decided_as(hand, item=OTHER)])):
            found = check(seen(write), before=before)
            self.assertEqual((kinds(found), found["hand"]), ([("approver", "approval")], []), name)
        # A time that cannot be read finds no record.
        self.assertIsNone(reconcile.decided([decided_as(hand)], ITEM, "soon"))
        self.assertIsNone(reconcile.decided([decided_as(hand, now="2026-11-30T12:00:00Z")], ITEM, "2026-11-31T12:30:00Z"))
        self.assertIsNone(reconcile.decided([decided_as(hand, now="2026-10-11")], ITEM, GIVEN))
        # A record whose time cannot be read may be the last before the approval: an earlier hand wait is not read.
        self.assertIsNone(reconcile.decided([decided_as(hand, now="2026-11-30T12:00:00Z"),
                                             decided_as("awaiting_review", now="2026-11-31T12:20:00Z")], ITEM,
                                            "2026-12-01T12:30:00Z"))
        self.assertEqual(reconcile.decided([decided_as(hand)], ITEM, GIVEN), (hand, HEAD))
        # The last before is read, so an earlier no-hand wait does not spoil one that is.
        self.assertEqual(len(check(seen(approval()), before=[decided_as("awaiting_review", now="2026-10-11T11:00:00Z"),
                                                            decided_as(hand)])["hand"]), 1)
        # Only the machine user's approval can be a hand approval: a Role's approval on that head stays unmatched.
        self.assertEqual(kinds(check(seen(dict(wrote("pr-review", "approval", "PRR_9", at=GIVEN), commit=HEAD)),
                                     before=[decided_as(hand)])), [("pr-review", "approval")])

    def test_a_carried_hand_approval_is_read_as_one_and_its_head_stays_taken(self):
        hand = "model_lens_input_needs_person"
        held = dict(reconcile.EMPTY, hand=[{"key": "PRR_1", "item": URL, "head": HEAD, "at": GIVEN}])
        # Two passes on, no record at hand decided the item, and the carried entry still reads it as one; a second
        # approval of that head does not stand.
        later = [decided_as("awaiting_review", now="2026-10-11T13:30:00Z", item=OTHER, reconciled=held)]
        again = check(seen(approval(), approval("PRR_2", at="2026-10-11T13:40:00Z")), before=later)
        self.assertEqual(([h["key"] for h in again["hand"]], [u["key"] for u in again["unmatched"]]), (["PRR_1"], ["PRR_2"]))
        # An approval of another pull request at the same commit is judged on its own, by the pass that read that one.
        own = [decided_as(hand, now="2026-10-11T13:30:00Z", item=OTHER, reconciled=held)]
        mixed = check(seen(approval(), approval("PRR_3", item=OTHER, at="2026-10-11T13:45:00Z")), before=own)
        self.assertEqual([(h["item"]["number"], h["key"]) for h in mixed["hand"]], [(42, "PRR_1"), (43, "PRR_3")])
        # A head a carried entry took is taken, though the pass that read the item is still at hand.
        both = [dict(decided_as(hand), reconciled=held)]
        self.assertEqual(kinds(check(seen(approval("PRR_2", at="2026-10-11T12:40:00Z")), before=both)),
                         [("approver", "approval")])
        # A carried entry names its pull request: the same key on another is not it.
        self.assertEqual(kinds(check(seen(approval(item=OTHER)), before=later)), [("approver", "approval")])
        # Its head stays taken past the window, while its pull request is open: a later approval of that head, though
        # the pass that read it waiting is at hand, is unmatched. Once the pull request leaves, it is dropped.
        old = dict(held, hand=[dict(held["hand"][0], at="2026-10-09T00:00:00Z")])
        aged = [dict(decided_as(hand), reconciled=old)]
        self.assertEqual(kinds(check(seen(approval("PRR_2")), before=aged)), [("approver", "approval")])


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


class Pages(GitHub):
    """A stand-in GitHub that gives each list in `lists` page by page, as GitHub links them (trials/P-43.json): each
    page names the next and the last, or no last where `last` is false. `again` gives a page's items, and whether it
    then names a next one, when it is asked a second time, as after an event landed."""

    def __init__(self, lists, over=None, last=True, again=None, first_more=()):
        super().__init__(over)
        self.lists, self.last, self.again, self.times = lists, last, dict(again or {}), {}
        self.first_more = set(first_more)

    def send(self, req):
        base, _, page = req["path"].partition("&page=")
        if base not in self.lists:
            return super().send(req)
        self.asked.append((req["method"], req["path"]))
        pages, n = self.lists[base], int(page or 1)
        self.times[base, n] = self.times.get((base, n), 0) + 1
        items, more = (pages[n - 1] if n <= len(pages) else []), n < len(pages)
        if self.times[base, n] > 1 and n in self.again:
            items, more = self.again[n]
        if self.times[base, n] == 1 and n in self.first_more:
            more = True
        link = ['<https://api.github.com%s&page=%d>; rel="next"' % (base, n + 1)] if more else []
        if self.last and len(pages) > 1:
            link.append('<https://api.github.com%s&page=%d>; rel="last"' % (base, len(pages)))
        return {"status": 200, "headers": {"link": ", ".join(link)}, "body": copy.deepcopy(items)}


# What an item that left answers beyond its timeline: no reviews, threads or check runs.
LEFT_ANSWERS = {("GET", PULL + "/reviews?per_page=100"): [],
                ("POST", "/graphql"): {"data": {"repository": {"pullRequest": {"reviewThreads": {
                    "totalCount": 0, "pageInfo": {"hasNextPage": False}, "nodes": []}}}}},
                ("GET", PULL): {"head": {"sha": "c0ffee" + "0" * 34}},
                ("GET", "/repos/%s/commits/%s/check-runs?per_page=100" % (ITEM["repo"], "c0ffee" + "0" * 34)): {
                    "total_count": 0, "check_runs": []}}


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
    def test_a_list_is_read_to_ten_pages_and_past_them_what_was_seen_is_short(self):  # issue 1009, decision 0234
        # The comments, which GitHub gives as updated from `since` on, are read to ten pages: ten that end there are
        # whole; a tenth that names an eleventh is not, and the eleventh is never asked.
        for last, whole in ((10, True), (11, False)):
            github = Pages({COMMENTS[1]: [[] for _ in range(last)]})
            self.assertIs(seen_.read(github, ITEM, kept(), IDENTITIES, APPS, SINCE)[2], whole, last)
            self.assertEqual(len([path for _, path in github.asked if "/comments?" in path]), 10, last)
        # The reviews of an item that left, which GitHub lists in the order they were started, are read forward so too.
        close = [{"event": "closed", "actor": CONTROLLER, "created_at": AT, "id": 9}]
        reviews = PULL + "/reviews?per_page=100"
        for count, whole in ((10, True), (11, False)):
            answers = {k: v for k, v in LEFT_ANSWERS.items() if k != ("GET", reviews)}
            github = Pages({ISSUE + "/timeline?per_page=100": [close], reviews: [[] for _ in range(count)]}, answers)
            self.assertIs(seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], whole, count)
            self.assertEqual(len([path for _, path in github.asked if "/reviews?" in path]), 10, count)

    def test_a_long_timeline_is_read_from_its_end_back_to_since(self):  # issue 1009, decision 0234, P-43
        # An item that left with a timeline of thirty pages: its close and the writes since `since` are on its last
        # pages. The first page names the last; the last pages are read back until one reaches before `since`, and the
        # last is read again: the close is found, and the pages between are never asked.
        old = [{"event": "commented", "actor": PERSON, "created_at": EARLY}]
        new = [{"event": "commented", "actor": PERSON, "created_at": AT}]
        close = [{"event": "closed", "actor": CONTROLLER, "created_at": AT, "id": 9}]
        timeline_ = [old] * 27 + [old + new, new, close]
        github = Pages({ISSUE + "/timeline?per_page=100": timeline_}, LEFT_ANSWERS)
        writes, merged, whole = seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)
        self.assertIs(whole, True)
        self.assertIn(("controller", "close", None), [(w["by"], w["kind"], w["key"]) for w in writes])
        pages = [path for _, path in github.asked if "/timeline" in path]
        self.assertEqual(pages, [ISSUE + "/timeline?per_page=100"] + [ISSUE + "/timeline?per_page=100&page=%d" % n
                                                                      for n in (30, 29, 28, 30)])
        # Never reaching `since` within the bound, nor the first page, is short; so is a last page GitHub does not name.
        github = Pages({ISSUE + "/timeline?per_page=100": [new] * 29 + [close]}, LEFT_ANSWERS)
        self.assertIs(seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], False)
        self.assertLessEqual(len([p for _, p in github.asked if "/timeline" in p]), 10)
        github = Pages({ISSUE + "/timeline?per_page=100": timeline_}, LEFT_ANSWERS, last=False)
        self.assertIs(seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], False)
        # A short timeline is read back to its first page, joined, each event once.
        github = Pages({ISSUE + "/timeline?per_page=100": [new, close, close]}, LEFT_ANSWERS)
        writes, _, whole = seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)
        self.assertIs(whole, True)
        self.assertEqual([w["kind"] for w in writes].count("close"), 1)
        # Ids of different kinds are told apart: a label and a close of one id are both kept.
        comment = [{"event": "labeled", "actor": CONTROLLER, "created_at": AT, "id": 9, "label": {"name": "factory:ready"}}]
        github = Pages({ISSUE + "/timeline?per_page=100": [new, comment, close]}, LEFT_ANSWERS)
        writes, _, _ = seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)
        self.assertIn("close", [w["kind"] for w in writes])
        self.assertTrue(any(w["kind"] != "close" and w["by"] == "controller" for w in writes))

    def test_an_item_read_as_gone_is_read_back_to_its_close(self):  # issue 1009, the Claude read of part 4
        # One read as gone is whole with its close of any age. Where events after the close, all before `since`, fill
        # the pages after it, the read goes on back past `since`, within the bound, until it finds the close.
        old = [{"event": "commented", "actor": PERSON, "created_at": EARLY}]
        closed = [{"event": "closed", "actor": CONTROLLER, "created_at": EARLY, "id": 9}]
        path = ISSUE + "/timeline?per_page=100"
        for pages_ in ([old, closed, old], [old, old, closed, old], [old] * 5 + [closed] + [old] * 6):
            github = Pages({path: pages_}, LEFT_ANSWERS)
            self.assertIs(seen_.read(github, ITEM, seen_.GONE, IDENTITIES, APPS, SINCE)[2], True, len(pages_))
            self.assertLessEqual(len([p for _, p in github.asked if "/timeline" in p]), 10)
        # One that left is read back to `since` alone, its close in the window; and past the bound a close is short.
        github = Pages({path: [old, closed, old]}, LEFT_ANSWERS)
        self.assertIs(seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], False)
        self.assertEqual([p for _, p in github.asked if "/timeline" in p][1:], [path + "&page=3", path + "&page=3"])
        github = Pages({path: [old] * 3 + [closed] + [old] * 10}, LEFT_ANSWERS)
        self.assertIs(seen_.read(github, ITEM, seen_.GONE, IDENTITIES, APPS, SINCE)[2], False)
        # Its close on the eighth page from the end is past the bound too (Carbon).
        github = Pages({path: [old] * 5 + [closed] + [old] * 7}, LEFT_ANSWERS)
        self.assertIs(seen_.read(github, ITEM, seen_.GONE, IDENTITIES, APPS, SINCE)[2], False)
        self.assertLessEqual(len([p for _, p in github.asked if "/timeline" in p]), 10)
        # Its close found on the last page, the read still goes back to `since`: what was written before the close in
        # the window is read too, and the read is whole (Carbon).
        new = [{"event": "commented", "actor": PERSON, "created_at": AT}]
        late = [{"event": "closed", "actor": CONTROLLER, "created_at": "2026-10-11T13:00:00Z", "id": 9}]
        github = Pages({path: [old, new, late]}, LEFT_ANSWERS)
        self.assertIs(seen_.read(github, ITEM, seen_.GONE, IDENTITIES, APPS, SINCE)[2], True)
        self.assertIn(path + "&page=2", [p for _, p in github.asked])
        # An issue's read back ends at its close alone, never at a merge before it (Carbon).
        merged = [{"event": "merged", "actor": PERSON, "created_at": EARLY, "id": 8}]
        github = Pages({path: [old, closed, merged, old]}, {**LEFT_ANSWERS, ("GET", ISSUE): {"number": 42, "state": "closed"}})
        self.assertIs(seen_.read(github, dict(ITEM, type="issue"), seen_.GONE, IDENTITIES, APPS, SINCE)[2], True)
        # A pull request's merge ends its read back, as a close does (Astra).
        github = Pages({path: [old, old, merged]}, LEFT_ANSWERS)
        self.assertIs(seen_.read(github, ITEM, seen_.GONE, IDENTITIES, APPS, SINCE)[2], True)
        self.assertEqual([p for _, p in github.asked if "/timeline" in p][1:], [path + "&page=3", path + "&page=3"])
        # An issue read as gone that REST reads open again has no close to find: it is read back to `since` alone (Carbon).
        github = Pages({path: [old] * 27 + [old + new, new, new]}, {**LEFT_ANSWERS, ("GET", ISSUE): {"number": 42, "state": "open"}})
        self.assertIs(seen_.read(github, dict(ITEM, type="issue"), seen_.GONE, IDENTITIES, APPS, SINCE)[2], True)
        self.assertEqual(len([p for _, p in github.asked if "/timeline" in p]), 5)
        # Items GitHub gives no id, as commits, are kept each, never told apart as one (Carbon).
        commits = [{"event": "committed", "sha": "1" * 40}, {"event": "committed", "sha": "2" * 40}]
        kept, whole = seen_._tail(Pages({path: [old, old, commits + new]}), path, SINCE)
        self.assertEqual(([k.get("sha") for k in kept if k.get("event") == "committed"], whole), (["1" * 40, "2" * 40], True))

    def test_a_read_from_the_end_is_short_on_what_it_cannot_tell(self):  # issue 1009, the readers of a1b28476
        new = [{"event": "commented", "actor": PERSON, "created_at": AT}]
        old = [{"event": "commented", "actor": PERSON, "created_at": EARLY}]
        close = [{"event": "closed", "actor": CONTROLLER, "created_at": AT, "id": 9}]
        path = ISSUE + "/timeline?per_page=100"

        def left(github):
            return seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)
        # A moment that cannot be read never says the read reached `since`: the page before it is read, and its close.
        writes, _, whole = left(Pages({path: [old, close, [{"event": "commented", "actor": PERSON, "created_at": ""}]]},
                                      LEFT_ANSWERS))
        self.assertEqual((whole, [w["kind"] for w in writes]), (True, ["close"]))
        # A last page that answers empty, as one the list shrank from, is short.
        self.assertIs(left(Pages({path: [old, close, []]}, LEFT_ANSWERS))[2], False)
        # An id that cannot be a key leaves the read short, never refused.
        self.assertIs(left(Pages({path: [new, [dict(close[0], id=[])], close]}, LEFT_ANSWERS))[2], False)
        # A truth value is no id either, though Python counts it a number (Carbon).
        self.assertIs(left(Pages({path: [new, [dict(close[0], id=True)], close]}, LEFT_ANSWERS))[2], False)
        # A last page that named a next one when first read is short, though it names none when read again.
        self.assertIs(left(Pages({path: [old] * 27 + [old + new, new, close]}, LEFT_ANSWERS, first_more={30}))[2], False)
        # The bound is ten pages: the first, seven read back, the last again, and the first again where joined. A
        # read back that reaches `since` on the seventh page back is whole; one that needs an eighth is short.
        for reach, whole in ((24, True), (23, False)):
            pages_ = [old] * (reach - 1) + [old + new] + [new] * (29 - reach) + [close]
            github = Pages({path: pages_}, LEFT_ANSWERS)
            self.assertIs(left(github)[2], whole, reach)
            self.assertLessEqual(len([p for _, p in github.asked if "/timeline" in p]), 10, reach)
        # A joined first page's writes are read too.
        label = [{"event": "labeled", "actor": CONTROLLER, "created_at": AT, "id": 5, "label": {"name": "factory:ready"}}]
        writes, _, whole = left(Pages({path: [label, new, close]}, LEFT_ANSWERS))
        self.assertEqual((whole, sorted(w["kind"] for w in writes)), (True, ["close", "label"]))
        # Joined at the bound: eight pages are read whole in ten requests, nine are not (Carbon).
        for between, whole in ((6, True), (7, False)):
            github = Pages({path: [label] + [new] * between + [close]}, LEFT_ANSWERS)
            self.assertIs(left(github)[2], whole, between)
            self.assertLessEqual(len([p for _, p in github.asked if "/timeline" in p]), 10, between)
        # A steady timeline that ends with a commit, which carries no id and no moment, is whole (Carbon).
        commit = {"event": "committed", "sha": "a" * 40}
        self.assertIs(left(Pages({path: [old] * 27 + [old + new, new, close + [commit]]}, LEFT_ANSWERS))[2], True)
        # An issue's timeline is read from its end too.
        issue = dict(ITEM, type="issue")
        github = Pages({path: [old] * 27 + [old + new, new, close]})
        writes, _, whole = seen_.read(github, issue, None, IDENTITIES, APPS, SINCE)
        self.assertEqual((whole, [w["kind"] for w in writes]), (True, ["close"]))

    def test_a_read_from_the_end_holds_its_edges(self):  # issue 1009, the readers of 4a416a5f
        new = [{"event": "commented", "actor": PERSON, "created_at": AT}]
        old = [{"event": "commented", "actor": PERSON, "created_at": EARLY}]
        close = [{"event": "closed", "actor": CONTROLLER, "created_at": AT, "id": 9}]
        path = ISSUE + "/timeline?per_page=100"

        def left(github):
            return seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)
        # A moment at `since` itself is not before it: the read goes on to the close behind it (Muse).
        at_since = [dict(close[0], created_at=SINCE)]
        writes, _, whole = left(Pages({path: [old, at_since, [{"event": "commented", "actor": PERSON,
                                                                "created_at": SINCE}]]}, LEFT_ANSWERS))
        self.assertEqual((whole, [w["kind"] for w in writes]), (True, ["close"]))
        # A review on the timeline is placed by when it was submitted, not when it was begun (Astra).
        begun = [{"event": "reviewed", "user": PERSON, "created_at": EARLY, "submitted_at": AT, "id": 3}]
        writes, _, whole = left(Pages({path: [old, close, begun]}, LEFT_ANSWERS))
        self.assertEqual((whole, [w["kind"] for w in writes]), (True, ["close"]))
        # A review submitted before `since` reaches it, by its submitted_at alone (Carbon).
        sent = [{"event": "reviewed", "user": PERSON, "created_at": AT, "submitted_at": EARLY, "id": 4}]
        self.assertIs(left(Pages({path: [old] * 23 + [sent] + [new] * 5 + [close]}, LEFT_ANSWERS))[2], True)
        # One page that names a last page it does not lead to is short; one page alone is kept by kind and id, and an
        # id that cannot be a key on it is short too (Astra).
        one = Pages({path: [close + close]}, LEFT_ANSWERS)
        writes, _, whole = left(one)
        self.assertEqual((whole, [w["kind"] for w in writes]), (True, ["close"]))
        self.assertIs(left(Pages({path: [[dict(close[0], id=[])]]}, LEFT_ANSWERS))[2], False)

        class Lying(Pages):
            def send(self, req):
                answer = super().send(req)
                if req["path"] == path:
                    answer = dict(answer, headers={"link": '<https://api.github.com%s&page=4>; rel="last"' % path})
                return answer
        self.assertIs(left(Lying({path: [close]}, LEFT_ANSWERS))[2], False)
        # An empty page before the end is no page GitHub gives: short (Astra).
        self.assertIs(left(Pages({path: [old, old, [], close]}, LEFT_ANSWERS))[2], False)
        # So is a first page that answers empty and names a next one, joined to the read or not (Muse).
        self.assertIs(left(Pages({path: [[], close]}, LEFT_ANSWERS))[2], False)
        self.assertIs(left(Pages({path: [[]] + [old] * 3 + [close]}, LEFT_ANSWERS))[2], False)
        self.assertIs(left(Pages({path: [new, close]}, LEFT_ANSWERS))[2], True)
        self.assertIs(left(Pages({path: [old] * 4 + [close]}, LEFT_ANSWERS))[2], True)
        # Two commits on the last page are told apart by their sha, though they carry no id or time (Astra).
        commit = lambda sha: {"event": "committed", "sha": sha}
        github = Pages({path: [old] * 27 + [old + new, new, close + [commit("a" * 40)]]}, LEFT_ANSWERS,
                       again={30: (close + [commit("b" * 40)], False)})
        self.assertIs(left(github)[2], False)
        self.assertIs(left(Pages({path: [old] * 27 + [old + new, new, close + [commit("a" * 40)]]}, LEFT_ANSWERS))[2], True)
        # A moment past a first item that has none still reaches `since` (Astra).
        self.assertIs(left(Pages({path: [old] * 23 + [[commit("c" * 40)] + old] + [new] * 5 + [close]}, LEFT_ANSWERS))[2], True)
        # A joined first page is read again though the read reached `since` on the second (Kimi, Muse, Astra).
        first = [{"event": "commented", "actor": PERSON, "created_at": EARLY, "id": 1}]
        github = Pages({path: [first, old + close]}, LEFT_ANSWERS, again={1: (old, True)})
        self.assertIs(left(github)[2], False)
        self.assertIs(left(Pages({path: [first, old + close]}, LEFT_ANSWERS))[2], True)

    def test_a_read_from_the_end_trusts_no_answer_that_contradicts_itself(self):  # issue 1206
        # GitHub's answers can be malformed, or contradict each other between reads: each such read is short.
        new = [{"event": "commented", "actor": PERSON, "created_at": AT}]
        old = [{"event": "commented", "actor": PERSON, "created_at": EARLY}]
        close = [{"event": "closed", "actor": CONTROLLER, "created_at": AT, "id": 1}]
        path = ISSUE + "/timeline?per_page=100"

        class Linked(Pages):
            """Pages whose link header, page by page, is the one given for it: one for every ask, or one for each ask in
            turn, the last for the rest."""

            def __init__(self, lists, links):
                super().__init__(lists, LEFT_ANSWERS)
                self.links = links

            def send(self, req):
                answer = super().send(req)
                n = int(req["path"].partition("&page=")[2] or 1)
                if req["path"].partition("&page=")[0] == path and n in self.links:
                    links = self.links[n] if isinstance(self.links[n], tuple) else (self.links[n],)
                    link = links[min(self.times[path, n], len(links)) - 1]
                    answer = dict(answer, headers={"link": link % {"at": "https://api.github.com" + path}})
                return answer

        def whole(github):
            return seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2]
        # 1. An item whose kind cannot be read never says the read reached `since` (Astra).
        kindless = [{"event": None, "actor": PERSON, "created_at": EARLY}]
        self.assertIs(seen_._tail(Pages({path: [old] + [new] * 12 + [kindless, close]}), path, SINCE)[1], False)
        self.assertIs(seen_._tail(Pages({path: [old] + [new] * 12 + [old, close]}), path, SINCE)[1], True)
        # 2. One page that names a last page by a number that cannot be read is short (Astra).
        self.assertIs(whole(Linked({path: [close]}, {1: '<%(at)s&page=x>; rel="last"'})), False)
        self.assertIs(whole(Linked({path: [close]}, {1: ''})), True)
        # 3. A page read back that names no next one, though a later page was read, is short (Astra).
        self.assertIs(whole(Linked({path: [old, new, new, close]}, {3: '<%(at)s&page=4>; rel="last"'})), False)
        self.assertIs(whole(Linked({path: [old, new, new, close]}, {3: '<%(at)s&page=4>; rel="next", <%(at)s&page=4>; rel="last"'})),
                      True)
        self.assertIs(whole(Pages({path: [old, new, new, close]}, LEFT_ANSWERS)), True)
        # 4. An id read again as a truth value is not the number it was (Astra).
        self.assertIs(whole(Pages({path: [old] * 3 + [close]}, LEFT_ANSWERS, again={4: ([dict(close[0], id=True)], False)})),
                      False)
        # 5. A first page past `since` before a later page from before it is out of order: short (Astra).
        self.assertIs(whole(Pages({path: [new, old, old, close]}, LEFT_ANSWERS)), False)
        self.assertIs(whole(Pages({path: [[dict(new[0], created_at=SINCE)], old, old, close]}, LEFT_ANSWERS)), False)
        self.assertIs(whole(Pages({path: [old, old, old, close]}, LEFT_ANSWERS)), True)
        # 6. A first page that names a next one and a last page before the second is short (Carbon).
        # GitHub's own shape, each page naming the pages about it, reads whole; a page that names another before it,
        # or a first that is not the first, does not (Astra, Claude).
        shape = {1: '<%(at)s&page=2>; rel="next", <%(at)s&page=4>; rel="last"',
                 4: '<%(at)s&page=3>; rel="prev", <%(at)s&page=1>; rel="first"'}
        shape.update({n: '<%%(at)s&page=%d>; rel="prev", <%%(at)s&page=%d>; rel="next", <%%(at)s&page=4>; rel="last", '
                         '<%%(at)s&page=1>; rel="first"' % (n - 1, n + 1) for n in (2, 3)})
        self.assertIs(whole(Linked({path: [old, new, new, close]}, shape)), True)
        for n, wrong in ((4, '<%(at)s&page=9>; rel="prev"'), (4, '<%(at)s&page=2>; rel="first"'), (4, ''),
                         (1, shape[1] + ', <%(at)s&page=1>; rel="first"'), (1, shape[1] + ', <%(at)s&page=0>; rel="prev"')):
            self.assertIs(whole(Linked({path: [old, new, new, close]}, {**shape, n: wrong})), False, (n, wrong))
        named = '<%(at)s&page=2>; rel="next", <%(at)s&page={}>; rel="last"'
        # A link header read in part says nothing of where the list ends: an unquoted relation, a page that is no
        # number, a page in no query or named twice, a relation named twice (Astra, Muse, Kimi); a page before the
        # first (Astra, Claude).
        for link in ('<%(at)s&page=3>; rel=last', '<%(at)s&page=2x>; rel="last"', '<%(at)s&page=2>; rel="prev"'):
            self.assertIs(whole(Linked({path: [close]}, {1: link})), False, link)
        for last in ('#x&page=2', '&page=2&page=2', '&page=x&page=2', '&page=&page=2', '&page=+2', '&page=0000000002',
                     '&page=\t2'):
            link = '<%(at)s&page=2>; rel="next", <%(at)s' + last + '>; rel="last"'
            self.assertIs(whole(Linked({path: [old, close]}, {1: link})), False, link)
        twice = '<%(at)s&page=2>; rel="next", <%(at)s&page=2>; rel="last", <%(at)s&page=2>; rel="last"'
        self.assertIs(whole(Linked({path: [old, close]}, {1: twice})), False)
        # A link to another page size, or an entry that names two relations, is no link to this list (Astra).
        small = {"at": "https://api.github.com" + path.replace("per_page=100", "per_page=1")}
        self.assertIs(whole(Linked({path: [old, close]}, {1: (named.format(2) % small).replace("%", "%%")})), False)
        self.assertIs(whole(Linked({path: [close]}, {1: '<%(at)s&page=2>; rel="deprecation"; rel="next"'})), False)
        # So is a relation that names a paging one among others or in capitals, and a header read whole only in part,
        # its paging links first (Astra, Kimi, Claude).
        for link in ('<%(at)s&page=2>; rel="next last"', '<%(at)s&page=2>; rel="NEXT"'):
            self.assertIs(whole(Linked({path: [close]}, {1: link})), False, link)
        self.assertIs(whole(Linked({path: [old, close]}, {1: named.format(2) + ', unreadable'})), False)
        # A relation that pages nothing, as GitHub's deprecation notice, is passed over, whatever its parameters say,
        # and the first page read again is the same however its links fall (Claude, Astra).
        notice = ', <https://docs.github.com/en/rest/about-the-rest-api/api-versions>; rel="deprecation"; type="text/html"'
        for other in (notice, ', <https://docs.github.com>; rel="latest-version"; title="REST API, version 2"',
                      ', <https://docs.github.com>; rel="deprecation"; title="Use \\"v2\\""'):
            self.assertIs(whole(Linked({path: [close]}, {1: other[2:]})), True, other)
        self.assertIs(whole(Linked({path: [old, close]}, {1: named.format(2) + notice})), True)
        self.assertIs(whole(Linked({path: [old, close]}, {1: (named.format(2), named.format(2) + notice)})), True)
        # The end names no last past itself; each page read back names the one after it, and the same last (Astra).
        past, prev = '<%(at)s&page=1>; rel="prev", <%(at)s&page=3>; rel="last"', '<%(at)s&page=1>; rel="prev"'
        for asks in ((past, prev), (prev, past)):
            self.assertIs(whole(Linked({path: [old, close]}, {2: asks})), False, asks)
        self.assertIs(whole(Linked({path: [old, old, old, close]}, {1: '<%(at)s&page=3>; rel="next", <%(at)s&page=4>; rel="last"'})),
                      False)
        self.assertIs(whole(Linked({path: [old, new, new, close]}, {3: '<%(at)s&page=2>; rel="next", <%(at)s&page=4>; rel="last"'})),
                      False)
        self.assertIs(whole(Linked({path: [old, new, new, close]}, {2: '<%(at)s&page=4>; rel="last"'})), False)
        self.assertIs(whole(Linked({path: [old, new, new, close]}, {3: '<%(at)s&page=4>; rel="next"'})), False)
        self.assertIs(whole(Linked({path: [old, new, new, close]}, {3: '<%(at)s&page=4>; rel="next", <%(at)s&page=5>; rel="last"'})),
                      False)
        # An item of an empty, blank or numbered kind places nothing either (Astra); one GitHub names with a number in
        # it does (Claude, Muse).
        project = [{"event": "added_to_project_v2", "actor": PERSON, "created_at": EARLY}]
        self.assertIs(seen_._tail(Pages({path: [project, new, old, close]}), path, SINCE)[1], True)
        for kind in ("", " ", "42"):
            pages = [old] + [new] * 12 + [[dict(kindless[0], event=kind)], close]
            self.assertIs(seen_._tail(Pages({path: pages}), path, SINCE)[1], False, kind)
        # A write read again as another's, or under another label, is not the same (Astra).
        self.assertIs(whole(Pages({path: [old] * 3 + [close]}, LEFT_ANSWERS, again={4: ([dict(close[0], actor=PERSON)], False)})),
                      False)
        label = [{"event": "labeled", "actor": CONTROLLER, "created_at": AT, "id": 2, "label": {"name": "a"}}]
        relabeled = [dict(label[0], label={"name": "b"})]
        self.assertIs(whole(Pages({path: [old] * 3 + [close + label]}, LEFT_ANSWERS, again={4: (close + relabeled, False)})),
                      False)
        review = [{"event": "reviewed", "user": CONTROLLER, "submitted_at": AT, "id": 3}]
        self.assertIs(whole(Pages({path: [old] * 3 + [close + review]}, LEFT_ANSWERS,
                                  again={4: (close + [dict(review[0], user=PERSON)], False)})), False)
        bot_as_person = dict(CONTROLLER, type="User")
        self.assertIs(whole(Pages({path: [old] * 3 + [close]}, LEFT_ANSWERS, again={4: ([dict(close[0], actor=bot_as_person)], False)})),
                      False)
        dismissal = [{"event": "review_dismissed", "actor": CONTROLLER, "created_at": AT, "id": 6,
                      "dismissed_review": {"review_id": 3, "state": "approved"}}]
        dismissal_again = [dict(dismissal[0], dismissed_review={"review_id": 3, "state": "commented"})]
        for again in (dismissal_again, [dict(dismissal[0], dismissed_review={"review_id": 4, "state": "approved"})]):
            self.assertIs(whole(Pages({path: [old] * 3 + [close + dismissal]}, LEFT_ANSWERS, again={4: (close + again, False)})),
                          False, again)
        # One event read on two pages as two, by its id, its id's type or its node, is a contradiction, a first page
        # left out among them; read the same, it is kept once (Astra, Muse).
        twice = [dict(close[0], actor=PERSON)]
        self.assertIs(seen_._tail(Pages({path: [old + twice, close]}), path, SINCE)[1], False)
        self.assertIs(seen_._tail(Pages({path: [old + [dict(close[0], id="1")], close]}), path, SINCE)[1], False)
        node = [dict(close[0], node_id="CE_n")]
        self.assertIs(seen_._tail(Pages({path: [old + node, [dict(node[0], id=8)]]}), path, SINCE)[1], False)
        # One with no id is kept once by its node; two kinds that share a node are not one event (Astra, Claude).
        bare = [{"event": "closed", "actor": CONTROLLER, "created_at": AT, "node_id": "CE_b"}]
        self.assertEqual(seen_._tail(Pages({path: [old + bare, bare]}), path, SINCE), (old + bare, True))
        review = [{"event": "reviewed", "user": PERSON, "submitted_at": AT, "id": 3, "node_id": "PRR_r"}]
        lines = [{"event": "line-commented", "node_id": "PRR_r"}]
        self.assertIs(seen_._tail(Pages({path: [old + review, lines]}), path, SINCE)[1], True)
        early = [dict(close[0], actor=PERSON, created_at=EARLY)]
        self.assertIs(seen_._tail(Pages({path: [early, new, old, close]}), path, SINCE)[1], False)
        self.assertEqual(seen_._tail(Pages({path: [old + close, close]}), path, SINCE), (old + close, True))
        # Moments out of order anywhere in what was read leave the skipped pages unplaced (Astra, Muse); a first page
        # left out holds every item that could be a write placed, but a commit, which has no moment (Astra, Muse).
        very = [{"event": "commented", "actor": PERSON, "created_at": "2026-10-01T00:00:00Z"}]
        for pages in ([old, close, very, new], [old, close, new + old, new], [old + new, old, old, close], [new + old],
                      [[dict(close[0], created_at=None)], new, old, close], [kindless, new, old, close]):
            self.assertIs(seen_._tail(Pages({path: pages}), path, SINCE)[1], False, pages)
        commit = [{"event": "committed", "sha": "a" * 40}]
        self.assertIs(seen_._tail(Pages({path: [commit, new, old, close]}), path, SINCE)[1], True)
        self.assertIs(seen_._tail(Linked({path: [old, old]}, {1: named.format(0), 0: ''}), path, SINCE)[1], False)
        self.assertIs(seen_._tail(Linked({path: [old, old]}, {1: (named.format(1), '')}), path, SINCE)[1], False)
        self.assertIs(seen_._tail(Linked({path: [old, old]}, {1: named.format(2)}), path, SINCE)[1], True)

    def test_an_event_that_lands_while_the_end_is_read_leaves_it_short(self):  # issue 1009, the Builder's ruling
        # An event that lands while the pages are read back moves the pages: one read could fall between them. So the
        # last page is read again at the end, and one whose items or number changed leaves the read not whole.
        new = [{"event": "commented", "actor": PERSON, "created_at": AT}]
        old = [{"event": "commented", "actor": PERSON, "created_at": EARLY}]
        close = [{"event": "closed", "actor": CONTROLLER, "created_at": AT, "id": 9}]
        moved = close + [{"event": "commented", "actor": PERSON, "created_at": AT, "id": 10}]
        swapped = [{"event": "commented", "actor": PERSON, "created_at": AT, "id": 10}]
        for later, more in ((moved, False), (close, True), (swapped, False)):
            github = Pages({ISSUE + "/timeline?per_page=100": [old] * 27 + [old + new, new, close]}, LEFT_ANSWERS,
                           again={30: (later, more)})
            self.assertIs(seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], False, (later, more))
        steady = Pages({ISSUE + "/timeline?per_page=100": [old] * 27 + [old + new, new, close]}, LEFT_ANSWERS,
                       again={30: (close, False)})
        self.assertIs(seen_.read(steady, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], True)
        # An item deleted from a joined first page moves the pages the other way: the first page, read again, must
        # read the same (Claude); one that does not leaves the read short.
        first = [{"event": "commented", "actor": PERSON, "created_at": AT, "id": 1}]
        for later, whole in (([], False), (new, False), (first, True)):
            github = Pages({ISSUE + "/timeline?per_page=100": [first, new, close]}, LEFT_ANSWERS, again={1: (later, True)})
            self.assertIs(seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], whole, later)
        # One that lands before the first page is read again names a new last page there: short too (Astra).

        class Grown(Pages):
            def send(self, req):
                answer = super().send(req)
                if req["path"] == ISSUE + "/timeline?per_page=100" and self.times[req["path"], 1] > 1:
                    answer = dict(answer, headers={"link": answer["headers"]["link"].replace("page=3", "page=4")})
                return answer
        github = Grown({ISSUE + "/timeline?per_page=100": [first, new, close]}, LEFT_ANSWERS)
        self.assertIs(seen_.read(github, ITEM, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], False)

    def test_a_timeline_the_snapshot_cut_is_read_again_from_its_end(self):  # issue 1009, decision 0234
        # An open pull request whose timeline the snapshot cut at its bound: the writes since `since` are at its end,
        # so the seen port reads it again from there; one not cut is never read again.
        old = [{"event": "commented", "actor": PERSON, "created_at": EARLY}]
        review = [{"event": "reviewed", "user": APPROVER, "state": "approved", "id": 7, "submitted_at": AT,
                   "node_id": "PRR_t"}]
        label = [{"event": "labeled", "actor": CONTROLLER, "created_at": AT, "id": 5, "label": {"name": "factory:ready"}}]
        github = Pages({ISSUE + "/timeline?per_page=100": [old] * 28 + [review + label]})
        parts = kept(events=([], False))
        parts["cut"] = {"events": True, "reviews": False}
        writes, _, whole = seen_.read(github, ITEM, parts, IDENTITIES, APPS, SINCE)
        self.assertIs(whole, True)
        self.assertIn("label", [w["kind"] for w in writes])
        path = ISSUE + "/timeline?per_page=100"
        self.assertEqual([p for _, p in github.asked if "/timeline" in p],
                         [path] + [path + "&page=%d" % n for n in (29, 28, 29)])
        # A list whose first page names a next one but no last cannot be read from its end: short.
        github = Pages({ISSUE + "/timeline?per_page=100": [old] * 28 + [review]}, last=False)
        self.assertIs(seen_.read(github, ITEM, parts, IDENTITIES, APPS, SINCE)[2], False)
        github = Pages({})
        parts = kept(events=([], False))
        parts["cut"] = {"events": False, "reviews": False}
        self.assertIs(seen_.read(github, ITEM, parts, IDENTITIES, APPS, SINCE)[2], False)
        self.assertEqual([p for _, p in github.asked if "/timeline" in p], [])
        # A reviews list cut alone reads no timeline again, and what was seen stays short (Astra).
        parts = kept(reviews=([], False))
        parts["cut"] = {"events": False, "reviews": True}
        self.assertIs(seen_.read(github, ITEM, parts, IDENTITIES, APPS, SINCE)[2], False)
        self.assertEqual([p for _, p in github.asked if "/timeline" in p], [])

    def test_what_a_later_page_holds_is_seen_and_a_cut_snapshot_is_short(self):  # issue 1009, decision 0234 (Astra)
        # A write on the second page, past a first of a hundred, is seen.
        other = {"id": 77, "type": "User", "login": "someone"}
        first = [{"user": other, "node_id": "IC_%d" % n, "created_at": AT} for n in range(100)]
        github = Pages({COMMENTS[1]: [first, [{"user": CONTROLLER, "node_id": "IC_c", "created_at": AT}]]})
        writes, _, whole = seen_.read(github, ITEM, kept(), IDENTITIES, APPS, SINCE)
        self.assertEqual(([(w["by"], w["kind"]) for w in writes], whole), ([("controller", "comment")], True))
        # Reviews the snapshot cut at their bound leave what was seen of the pull request short.
        self.assertIs(port(kept(reviews=([], False)))[2], False)

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
        # A person's resolution of a thread a Role opened is a hand's write; of any other, none; an identity's is its own.
        def thread(ident, by=PERSON, opened=ROLE, **first):
            comment = dict({"replyTo": None, "author": opened and {
                "__typename": opened["type"], "login": opened["login"], "databaseId": opened["id"]}}, **first)
            return {"id": ident, "isResolved": True, "resolvedBy": by and {"login": by["login"], "databaseId": by["id"]},
                    "comments": {"nodes": [comment]}}

        queue = {"id": 5000009, "type": "Bot", "login": "combsmith-sf-queue[bot]"}
        threads_ = [thread("PRRT_h"), thread("PRRT_p", opened=PERSON), thread("PRRT_a", opened=APPROVER),
                    thread("PRRT_c", opened=CONTROLLER), thread("PRRT_g", opened=None), thread("PRRT_q", opened=queue),
                    thread("PRRT_m", author={"__typename": "Mannequin", "login": "gone"}),
                    thread("PRRT_r", by=ROLE), thread("PRRT_n", by=None),
                    dict(thread("PRRT_o"), isResolved=False, resolvedBy=None)]
        writes, _, whole = seen_.read(GitHub(), ITEM, kept(threads=threads_), {**IDENTITIES, (5000009, "Bot"): "queue"},
                                      APPS, SINCE)
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
                         ("an author not said", dict(thread("PRRT_h"), comments={"nodes": [{"replyTo": None}]})),
                         ("an account of no id", thread("PRRT_h", author={"__typename": "Bot", "login": "x", "databaseId": None})),
                         ("an account whose type is not said", thread("PRRT_h", author={"login": "x", "databaseId": 5000002})),
                         ("an account whose type is no word", thread("PRRT_h", author={"__typename": 7, "databaseId": 5000002})),
                         # A resolver whose account cannot be read is nobody that can be told, a person least of all.
                         ("a resolver of no id", dict(thread("PRRT_h"), resolvedBy={"login": "don-petry"})),
                         ("an account whose id is no number", thread("PRRT_h", author={"__typename": "Bot", "databaseId": True}))):
            writes, _, whole = port(kept(threads=[odd]))
            self.assertEqual((writes, whole), ([], False), why)
        # The opener is the first comment's author, however many follow it (issue 887).
        role_first, person_next = (thread("PRRT_h")["comments"]["nodes"][0],
                                   dict(thread("PRRT_h", opened=PERSON)["comments"]["nodes"][0], replyTo={"id": "PRRC_1"}))
        for nodes, read_ in (([role_first, person_next], [("hand", "PRRT_h")]), ([dict(person_next, replyTo=None),
                                                                                  dict(role_first, replyTo={"id": "PRRC_1"})], [])):
            writes, _, whole = port(kept(threads=[dict(thread("PRRT_h"), comments={"nodes": nodes})]))
            self.assertEqual(([(w["by"], w["key"]) for w in writes], whole), (read_, True), nodes)
        # Only a person's resolution asks who opened the thread: an identity's is read whoever did, as before.
        writes, _, whole = port(kept(threads=[dict(thread("PRRT_r", by=ROLE), comments=None)]))
        self.assertEqual(([(w["by"], w["key"]) for w in writes], whole), ([("pr-review", "PRRT_r")], True))

    def test_an_approval_carries_the_commit_it_approved_and_null_where_none_can_be_read(self):  # issue 1026
        reviews = [{"user": APPROVER, "state": "APPROVED", "node_id": "PRR_a", "submitted_at": AT, "commit_id": HEAD},
                   {"user": APPROVER, "state": "APPROVED", "node_id": "PRR_b", "submitted_at": AT, "commit_id": "abc"},
                   {"user": APPROVER, "state": "APPROVED", "node_id": "PRR_c", "submitted_at": AT},
                   {"user": APPROVER, "state": "APPROVED", "node_id": "PRR_g", "submitted_at": AT, "commit_id": "g" * 40},
                   {"user": APPROVER, "state": "APPROVED", "node_id": "PRR_h", "submitted_at": AT, "commit_id": False},
                   {"user": APPROVER, "state": "APPROVED", "node_id": "PRR_i", "submitted_at": AT, "commit_id": HEAD + "x"},
                   {"user": APPROVER, "state": "DISMISSED", "node_id": "PRR_d", "id": 4, "submitted_at": AT,
                    "commit_id": OTHER_HEAD},
                   {"user": ROLE, "state": "COMMENTED", "node_id": "PRR_e", "submitted_at": AT, "commit_id": HEAD},
                   {"user": APPROVER, "state": "DISMISSED", "node_id": "PRR_f", "id": 6, "submitted_at": AT,
                    "commit_id": HEAD}]
        events = [{"event": "review_dismissed", "actor": APPROVER, "created_at": AT,
                   "dismissed_review": {"review_id": 4, "state": "approved"}}]
        writes, _, whole = port(kept(reviews=reviews, events=events))
        # A dismissed review whose state before cannot be read is read as an approval, leaves what was seen short, and
        # carries no commit: what cannot be read is never a hand approval (issue 1026).
        self.assertFalse(whole)
        said = [(w["key"], w["kind"], w.get("commit", "absent")) for w in writes if w["key"] and w["key"].startswith("PRR")]
        self.assertEqual(said, [("PRR_a", "approval", HEAD), ("PRR_b", "approval", None), ("PRR_c", "approval", None),
                                ("PRR_g", "approval", None), ("PRR_h", "approval", None), ("PRR_i", "approval", None),
                                ("PRR_d", "approval", OTHER_HEAD), ("PRR_e", "review", "absent"),
                                ("PRR_f", "approval", None)])
        out = seen_.seen([(writes, [], whole)], SINCE)
        self.assertEqual(validate(out, SCHEMAS["seen"], schemas=SCHEMAS), [])
        # The seen message carries each as read, nulls among them, and the schema refuses a commit that is no commit.
        self.assertEqual([(w["key"], w["kind"], w.get("commit", "absent")) for w in out["writes"]
                          if w["key"] and w["key"].startswith("PRR")], said)
        bad = dict(out, writes=[dict(out["writes"][0], commit="abc")])
        self.assertTrue(validate(bad, SCHEMAS["seen"], schemas=SCHEMAS))

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

    def test_an_issue_that_left_is_read_with_its_close(self):  # issue 916, decision 0235
        # An issue the pass before served that has left is read first by its state. Closed, it is read as a pull request
        # that left is: whole only with its close, in the window, or any for one a pass before read as gone. A merge is
        # no issue's close. The Controller's close, label and comment on it are writes, and a comments read that fails
        # leaves it short whatever its close.
        issue = dict(ITEM, type="issue")
        COMMENTS_ = ("GET", ISSUE + "/comments?since=%s&per_page=100" % SINCE)
        state = lambda value: {"number": ITEM["number"], "state": value}

        def read(events, kept, answer=state("closed"), comments=(), **kw):
            github = GitHub({("GET", ISSUE + "/timeline?per_page=100"): events, ("GET", ISSUE): answer,
                             COMMENTS_: list(comments) if comments is not None else None})
            return seen_.read(github, issue, kept, IDENTITIES, APPS, SINCE, **kw)
        closed = [{"event": "labeled", "actor": CONTROLLER, "created_at": AT},
                  {"event": "closed", "actor": CONTROLLER, "created_at": AT}]
        said = [{"user": CONTROLLER, "node_id": "IC_c", "created_at": AT}]
        writes, _, whole = read(closed, seen_.LEFT, comments=said)
        self.assertEqual(([(w["by"], w["kind"]) for w in writes], whole),
                         ([("controller", "comment"), ("controller", "label"), ("controller", "close")], True))
        self.assertIs(read(closed, seen_.LEFT, comments=None)[2], False)
        old = [{"event": "closed", "actor": PERSON, "created_at": EARLY}]
        self.assertEqual((read(old, seen_.LEFT)[2], read(old, seen_.GONE)[2]), (False, True))
        for none in ([], [{"event": "merged", "actor": PERSON, "created_at": AT}]):
            self.assertEqual((read(none, seen_.LEFT)[2], read(none, seen_.GONE)[2]), (False, False), none)
        # An open issue, served, needs no close and is asked no state; one that left the issues served while open is
        # read as it is, by its state, with no close.
        self.assertIs(read([], None, answer=None)[2], True)
        for kept in (seen_.LEFT, seen_.GONE):
            writes, _, whole = read(closed[:1], kept, answer=state("open"))
            self.assertEqual(([(w["by"], w["kind"]) for w in writes], whole), ([("controller", "label")], True), kept)
            self.assertIs(read(closed[:1], kept, answer=state("open"), comments=None)[2], False, kept)
        # Not found or deleted, it is whole with nothing more read only where the same token read its repo in this pass,
        # and is told with its answer; else access may be what was lost, and it is short. With nowhere to tell it, it is
        # short too.
        for code in (404, 410):
            for kept in (seen_.LEFT, seen_.GONE):
                for repo in (True, False):
                    told = []
                    self.assertEqual(read(closed, kept, {"status": code, "body": {}}, repo_read=repo, told=told),
                                     ([], [], repo), (code, kept, repo))
                    self.assertEqual(told, [{"item": issue, "answer": code}] if repo else [], (code, kept, repo))
                self.assertEqual(read(closed, kept, {"status": code, "body": {}}, repo_read=True), ([], [], False))
        # Any other answer is short: a 403, a 429 or a 5xx, whatever its body says, none at all (as a transfer's 301
        # reaches the port, the transport keeping no redirect's code), a body of another issue, of a pull request, or with
        # no state.
        for answer in ({"status": 403, "body": state("closed")}, {"status": 429, "body": {}}, {"status": 500, "body": state("open")},
                       None, {"number": 7, "state": "closed"}, dict(state("closed"), pull_request={}), {"number": ITEM["number"]},
                       {"number": ITEM["number"], "state": "all"}):
            self.assertEqual(read(closed, seen_.LEFT, answer, repo_read=True, told=[]), ([], [], False), answer)
        # A number that is no integer is none, though Python takes true for 1 (Astra).
        first = dict(issue, number=1)
        github = GitHub({("GET", "/repos/%s/issues/1" % ITEM["repo"]): {"number": True, "state": "open"}})
        self.assertIs(seen_.read(github, first, seen_.LEFT, IDENTITIES, APPS, SINCE)[2], False)

    def test_the_repo_is_read_by_its_full_name(self):  # decision 0235
        repo = ITEM["repo"]
        on = {"has_issues": True}
        for answer, read in (({"full_name": repo, **on}, True), ({"full_name": repo.upper(), **on}, True),
                             ({"full_name": "a/b", **on}, False), (on, False), ({"full_name": repo, "has_issues": False}, False),
                             ({"full_name": repo}, False), ({"status": 404, "body": {"full_name": repo, **on}}, False), (None, False)):
            self.assertIs(seen_.repo_read(GitHub({("GET", "/repos/" + repo): answer}), repo), read, answer)

    def test_the_issues_read_whole_by_their_end_are_carried_in_what_was_seen(self):  # decision 1145
        gone = [{"item": dict(ITEM, type="issue"), "answer": 410}]
        self.assertEqual(seen_.seen([([], [], True)], SINCE, gone)["gone"], gone)
        self.assertNotIn("gone", seen_.seen([([], [], True)], SINCE))
        self.assertNotIn("gone", seen_.seen([([], [], True)], SINCE, []))

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


class Tracking(unittest.TestCase):
    def test_the_tracking_issues_number_is_what_the_passes_recorded_and_none_while_their_records_are_not_whole(self):  # issue 901
        # Each landed write of the tracking issue is keyed by its number: those read this pass, and those the last
        # record carried. A write that did not land, and another type's key, name no tracking issue.
        done = written(("tracking_issue", None, None, "8", "already_applied"), ("tracking_issue", None, None, "9", "failed"),
                       ("status_on_item", ITEM, None, "77", "applied"), ("tracking_issue", None, None, "4", "failed"),
                       ("status_on_item", ITEM, None, "78", "failed"))
        # But one written open with its assignee dropped is there, under its number, 4: it is left out too, and carried.
        done["writes"][3]["reason"] = done["writes"][4]["reason"] = "assignee_dropped"
        read = {"written": [done], "whole": True}
        self.assertEqual(reconcile.tracking(read, []), [4, 8])
        kept = reconcile.carried([], dict(read, applied=[], read={}, at={}), seen(), Carried.NOW)["keys"]
        self.assertEqual(sorted((k["type"], k["key"]) for k in kept),
                         [("status_on_item", "77"), ("tracking_issue", "4"), ("tracking_issue", "8")])
        done["writes"][3]["reason"] = None
        held = dict(Carried.NONE, keys=[{"where": "written", "type": "tracking_issue", "key": "6", "at": Carried.NOW},
                                        {"where": "applied", "type": "tracking_issue", "key": "5", "at": Carried.NOW}])
        before = [{"now": Carried.NOW, "pull_requests": [], "reconciled": held}]
        self.assertEqual(reconcile.tracking(read, before), [6, 8])
        self.assertEqual((reconcile.tracking(read, None), reconcile.tracking(dict(read, written=[]), [])), ([8], []))
        # A key of anything but ASCII digits names no tracking issue, and is no crash: '²' is a digit `int` refuses, and
        # '٣' one it reads as 3 (Carbon).
        odd = written(*[("tracking_issue", None, None, k, "applied") for k in ("8", "I_kw8", "²", "٣")])
        self.assertEqual(reconcile.tracking({"written": [odd], "whole": True}, []), [8])
        # Not read whole, or not read: the number may be one not read, and there is none to give.
        for unread in (dict(read, whole=False), None):
            self.assertIsNone(reconcile.tracking(unread, before))


class Carried(unittest.TestCase):
    """What a pass carries of what it read, so that the next reads only what is new (decisions 0061, 0112)."""
    NOW = "2026-10-11T13:00:00Z"
    NEXT = "2026-10-11T13:20:00Z"
    MADE = "2026-10-11T12:00:00Z"
    RUN = "r_01JA7Q"
    NONE = {"runs": [], "passes": [], "keys": [], "items": [], "dispatched": [], "owed": [], "left": [], "hands": []}

    def effects(self, *a, written_=(), runs=(), passes=(), whole=True, at=None):
        return dict(recorded(a, written_, whole), read={"runs": list(runs), "passes": list(passes)}, at=at or {})

    def test_the_issues_owed_and_left_are_carried_as_the_pull_requests_are(self):  # issue 916, decision 0235
        # The issues a pass owes are carried as such, and read again; those it read as left are stamped with now, and a
        # stamp a record before made is kept while the window holds it, so the next pass reads them as gone.
        held = reconcile.carried([], self.effects(), seen(), self.NOW, unread_issues=[9, 9], gone_issues=[41])
        self.assertEqual((held["owed_issues"], held["left_issues"]), ([9], [{"number": 41, "at": self.NOW}]))
        before = [{"now": self.NOW, "pull_requests": [], "reconciled": held}]
        self.assertEqual((reconcile.owed_issues(before), reconcile.left_issues(before), reconcile.left_issues(before, SINCE)),
                         ([9], [41], [41]))
        # The next pass keeps the stamp inside the window and pays the debt it read; past the window the stamp is dropped.
        again = reconcile.carried(before, self.effects(), seen(), self.NEXT)
        self.assertEqual((again["left_issues"], "owed_issues" in again), ([{"number": 41, "at": self.NOW}], False))
        # One that leaves again is stamped anew, once (Muse).
        anew = reconcile.carried(before, self.effects(), seen(), self.NEXT, gone_issues=[41])
        self.assertEqual(anew["left_issues"], [{"number": 41, "at": self.NEXT}])
        # Two owed and two left in one pass are each carried, and read back (Astra).
        two = reconcile.carried([], self.effects(), seen(), self.NOW, unread_issues=[10, 9], gone_issues=[42, 41])
        self.assertEqual((two["owed_issues"], two["left_issues"]), ([9, 10], [{"number": 41, "at": self.NOW}, {"number": 42, "at": self.NOW}]))
        self.assertEqual(reconcile.left_issues([{"now": self.NOW, "pull_requests": [], "reconciled": two}]), [41, 42])
        # Another that leaves keeps the first one's stamp beside its own (Astra).
        other = reconcile.carried(before, self.effects(), seen(), self.NEXT, gone_issues=[42])
        self.assertEqual(other["left_issues"], [{"number": 41, "at": self.NOW}, {"number": 42, "at": self.NEXT}])
        # One served again keeps no stamp of its leaving, and another's stays (Kimi, Astra).
        served = reconcile.carried([{"now": self.NOW, "pull_requests": [], "reconciled": two}], self.effects(), seen(),
                                   self.NEXT, served_issues=[41])
        self.assertEqual(served["left_issues"], [{"number": 42, "at": self.NOW}])
        # So too in a pass where another leaves (Astra).
        both = reconcile.carried(before, self.effects(), seen(), self.NEXT, served_issues=[41], gone_issues=[42])
        self.assertEqual(both["left_issues"], [{"number": 42, "at": self.NEXT}])
        # And one that leaves again where another is served is stamped anew, once (Carbon).
        again = reconcile.carried(before, self.effects(), seen(), self.NEXT, served_issues=[42], gone_issues=[41])
        self.assertEqual(again["left_issues"], [{"number": 41, "at": self.NEXT}])
        late = reconcile.carried(before, self.effects(), dict(seen(), since="2026-10-11T14:00:00Z"), self.NEXT)
        self.assertNotIn("left_issues", late)
        self.assertEqual(reconcile.left_issues(before, "2026-10-11T14:00:00Z"), [])
        # A record with neither carries neither, as one written before them.
        self.assertEqual(set(reconcile.carried([], self.effects(), seen(), self.NOW)) & {"owed_issues", "left_issues"}, set())
        self.assertEqual((reconcile.owed_issues([]), reconcile.left_issues([])), ([], []))
        # Nor does a record that carries neither, read back (Astra).
        bare = [{"now": self.NOW, "pull_requests": [], "reconciled": reconcile.carried([], self.effects(), seen(), self.NOW)}]
        self.assertEqual((reconcile.owed_issues(bare), reconcile.left_issues(bare), reconcile.left_issues(bare, SINCE)),
                         ([], [], []))

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
        # applied/1's key is wider than what a pass record carries, and written/1 refuses a repo a pass record cannot keep
        # (issue 913). One record's key or repo that does not fit is not carried, so it never refuses a pass; it can match
        # nothing GitHub says, and reconciliation says so.
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
