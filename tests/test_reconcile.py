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
from tests.support import ROOT, pending, run
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
    return {"schema": "applied/1", "run": "r_01JA7Q", "release": "factory/v0.3.1", "findings": [],
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
                                       ("comment", "K", "applied"), ("resolve_thread", "K", "applied"))])
        for write in (wrote("approver", "push", "K"), wrote("approver", "review", "K"), wrote("approver", "comment", "K"),
                      wrote("approver", "resolution", "K"), wrote("pr-review", "label"), wrote("pr-review", "merge"),
                      wrote("pr-review", "approval", "K"), wrote("pr-review", "resolution", "K"),
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
        refused = written(("dispatch_run", ITEM, "r_01JA7Q", None, "refused"))
        self.assertEqual(kinds(check(seen(), recorded(written_=[refused]), records(r), accounts=TOKEN)),
                         [("workflow_token", "dispatch")])
        # Until the pass job's token's account is set, no dispatch is reconciled, and run records not read leave
        # nothing short (ruling 2).
        self.assertEqual(check(seen(), recorded(), records(r))["unmatched"], [])
        self.assertIs(check(seen(), recorded(), None)["short"], False)


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
                      check(seen(), accounts=ACCOUNTS), check(seen(), accounts=dict(KNOWN, approver=None)),
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
                         [{"alert": "merged_by_override", "item": URL}])


APPROVER = {"id": 281750570, "type": "User", "login": "donpetry-bot"}
CONTROLLER = {"id": 5000001, "type": "Bot", "login": "combsmith-sf-controller[bot]"}
ROLE = {"id": 5000002, "type": "Bot", "login": "combsmith-sf-pr-review[bot]"}
PERSON = {"id": 36422719, "type": "User", "login": "don-petry"}
IDENTITIES = {(281750570, "User"): "approver", (5000001, "Bot"): "controller", (5000002, "Bot"): "pr-review"}
APPS = {5364130: "controller", 5364144: "pr-review"}
ISSUE = "/repos/%s/issues/%d" % (ITEM["repo"], ITEM["number"])
COMMENTS = ("GET", ISSUE + "/comments?since=%s&per_page=100" % SINCE)
ACTIVITY = ("GET", "/repos/%s/activity?actor=donpetry-bot&time_period=week&per_page=100" % ITEM["repo"])
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
                   {"user": APPROVER, "state": "DISMISSED", "node_id": "PRR_d", "submitted_at": AT},
                   {"user": APPROVER, "state": "PENDING", "node_id": "PRR_q"},
                   {"user": ROLE, "state": "COMMENTED", "node_id": "PRR_r", "submitted_at": SINCE},
                   {"user": dict(PERSON, login="donpetry-bot"), "state": "APPROVED", "node_id": "PRR_p", "submitted_at": AT},
                   {"user": dict(APPROVER, type="Bot"), "state": "APPROVED", "node_id": "PRR_x", "submitted_at": AT},
                   {"user": APPROVER, "state": "APPROVED", "node_id": "PRR_old", "submitted_at": EARLY}]
        comments = [{"user": CONTROLLER, "node_id": "IC_c", "created_at": AT}, {"user": PERSON, "node_id": "IC_p",
                                                                                "created_at": AT}]
        events = [{"event": "labeled", "actor": CONTROLLER, "created_at": AT},
                  {"event": "removed_from_merge_queue", "actor": CONTROLLER, "created_at": AT},
                  {"event": "review_dismissed", "actor": APPROVER, "created_at": AT},
                  {"event": "closed", "actor": ROLE, "created_at": AT},
                  {"event": "merged", "actor": PERSON, "created_at": AT},
                  {"event": "commented", "actor": CONTROLLER, "created_at": AT},
                  {"event": "labeled", "actor": PERSON, "created_at": AT}]
        threads_ = [{"id": "PRRT_n", "isResolved": True, "resolvedBy": None},
                    {"id": "PRRT_a", "isResolved": True, "resolvedBy": {"login": "donpetry-bot", "databaseId": 281750570}},
                    {"id": "PRRT_p", "isResolved": True, "resolvedBy": {"login": "don-petry", "databaseId": 36422719}},
                    {"id": "PRRT_o", "isResolved": False, "resolvedBy": None}]
        runs = [check_run(5364144, "CR_r"), check_run(5364130, "CR_c"), check_run(15368, "CR_x")]
        writes, merged, whole = port(kept(reviews=reviews, events=events, threads=threads_, check_runs=runs),
                                     {COMMENTS: comments})
        self.assertTrue(whole)
        self.assertEqual([(w["by"], w["kind"], w["key"]) for w in writes],
                         [("approver", "approval", "PRR_a"), ("approver", "review", "PRR_b"),
                          ("approver", "approval", "PRR_d"), ("pr-review", "review", "PRR_r"),
                          ("controller", "comment", "IC_c"), ("controller", "label", None),
                          ("controller", "dequeue", None), ("approver", "dismissal", None),
                          ("pr-review", "close", None), ("unattributed", "resolution", "PRRT_n"),
                          ("approver", "resolution", "PRRT_a"), ("pr-review", "check_run", "CR_r"),
                          ("controller", "check_run", "CR_c")])
        # A merge by anyone is read for an Override; and what was seen is seen/1.
        self.assertEqual(merged, [{"item": ITEM, "at": AT}])
        out = seen_.seen([(writes, merged, whole)], SINCE)
        self.assertEqual(validate(out, SCHEMAS["seen"], schemas=SCHEMAS), [])

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
                      kept(threads=[{"id": "PRRT_u", "isResolved": True, "resolvedBy": {"login": "x"}}])] \
                + [kept(**{name: value}) for name, value in bad.items()] \
                + [kept(**{name: value}) for name, value in keyless.items()]:
            self.assertIs(port(parts)[2], False, parts)
        for answer in ({"status": 403, "body": {}}, None, [{"user": CONTROLLER, "node_id": "IC", "created_at": "x"}],
                       [{"user": CONTROLLER, "node_id": None, "created_at": AT}]):
            self.assertIs(port(over={COMMENTS: answer})[2], False, answer)
        # A pull request whose snapshot kept nothing is short, and its comments are still read.
        writes, _, whole = port(None, {COMMENTS: [{"user": CONTROLLER, "node_id": "IC_c", "created_at": AT}]})
        self.assertEqual(([(w["by"], w["kind"]) for w in writes], whole), ([("controller", "comment")], False))

    def test_the_machine_users_pushes_are_read_from_the_repos_activity(self):  # decision 0005
        entries = [{"id": 7, "actor": APPROVER, "timestamp": AT}, {"id": 8, "actor": PERSON, "timestamp": AT},
                   {"id": 9, "actor": APPROVER, "timestamp": EARLY}, {"id": 10, "actor": APPROVER, "timestamp": SINCE}]
        writes, whole = seen_.pushes(GitHub({ACTIVITY: entries}), ITEM["repo"], APPROVER, SINCE)
        self.assertEqual(([(w["by"], w["kind"], w["key"], w["item"]) for w in writes], whole),
                         ([("approver", "push", "7", None), ("approver", "push", "10", None)], True))
        for answer in ({"status": 500, "body": {}}, None, [{"id": 7, "actor": APPROVER, "timestamp": "x"}],
                       [{"id": None, "actor": APPROVER, "timestamp": AT}], [{"id": True, "actor": APPROVER,
                                                                             "timestamp": AT}],
                       [{"id": i + 1, "actor": PERSON, "timestamp": AT} for i in range(100)]):
            self.assertIs(seen_.pushes(GitHub({ACTIVITY: answer}), ITEM["repo"], APPROVER, SINCE)[1], False, answer)

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
        for accounts in (ACCOUNTS, dict(KNOWN, approver=None), dict(KNOWN, roles={"pr-review": None})):
            self.assertIs(seen_.identities(accounts)[1], False)
        # The configuration holds the machine user as trials/P-7.json records it and the approver config/defaults.json
        # names, and a Role App's account for each Role App config/apps.json holds.
        defaults = json.loads((ROOT / "config" / "defaults.json").read_text())
        apps = json.loads((ROOT / "config" / "apps.json").read_text())["apps"]
        self.assertEqual((ACCOUNTS["approver"]["login"], ACCOUNTS["approver"]["id"]), (defaults["approver"], 281750570))
        self.assertEqual(set(ACCOUNTS["roles"]), set(apps) - {"controller", "reader"})


class CommentsGrant(unittest.TestCase):
    @pending
    def test_the_comments_on_a_pull_request_are_read_with_pull_requests_read(self):
        # Whether the Controller's token, narrowed to metadata and pull_requests: read, reads a pull request's comments
        # is a trial of the second token window (2026-10-23 to 10-30); until its fixture lands, this test is expected
        # to fail, and the comments read's need stays where ruling 3 put it.
        said = "pull_requests: read serves a pull request's comments"
        found = [p for p in sorted((ROOT / "trials").glob("*.json")) if said in p.read_text()]
        self.assertEqual(len(found), 1)
        self.assertIs(json.loads(found[0].read_text())["exchanges"][-1]["response"]["body"][said], True)


if __name__ == "__main__":
    unittest.main()
