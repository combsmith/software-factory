"""The Controller's writes: the plan a pass makes, `controller/writes.py`, and the effects port that sends it,
`adapters/effects.py` (#193's rulings for PR 2). Each write the port sends is built from the shape a trial recorded:
a dispatch from `trials/P-9.json`, the pass job's own token's, answered 204 (L-50, L-51)."""
from __future__ import annotations

import copy
import json
import os
import pathlib
import tempfile
import unittest

from adapters import effects, github, pause
from controller import pass_, writes as writes_
from tests import support
from tests.support import pending
from tests.test_controller import config, passed, pr, reads, run

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTROLLER = json.loads((ROOT / "config" / "controller.json").read_text())
OWNER = json.loads((ROOT / "config" / "defaults.json").read_text())["owner_role"]


class Counted:
    """A transport that answers each request with the status given in turn, and counts every request sent."""

    def __init__(self, *statuses):
        self.statuses, self.sent = list(statuses), []

    def send(self, req):
        self.sent.append(req)
        status = self.statuses.pop(0)
        if status is None:
            raise github.Unanswered("no answer")
        return {"status": status, "headers": {}, "body": None}


def p9_dispatch() -> dict:
    """The dispatch the pass job's own token made in trials/P-9.json: its request and GitHub's 204."""
    return copy.deepcopy(json.loads((ROOT / "trials" / "P-9.json").read_text())["exchanges"][8])


def answered(path: str, body: dict, status: int = 204) -> dict:
    """P-9's exchange, asked as the port asks a dispatch: the path and body changed, GitHub's answer kept."""
    found = p9_dispatch()
    found["request"].update(via="rest", call="POST %s" % path, body=body)
    found["response"]["status"] = status
    return found


# A stand-in for the Controller's bot account: the trial that records its id is still to run, and until it does the
# configuration holds none and no tracking issue is written (#193's ruling 8).
BOT = {"id": 1000001, "type": "Bot", "login": "combsmith-sf-controller[bot]"}


def controller(**accounts) -> dict:
    c = copy.deepcopy(CONTROLLER)
    c["accounts"] = dict(c["accounts"], **dict({"workflow_token": {"id": 41898282, "type": "Bot"}, "controller": BOT},
                                              **accounts))
    return c


def clear(plan: dict, cfg: dict) -> dict:
    """The Pause read exactly not paused on the org and on every repo the plan acts in."""
    org, repos = effects.scopes(plan, cfg)
    return {"org": "false", "repos": {repo: "false" for repo in repos}}


def out() -> dict:
    """A pass that admits one Run, issues one approval, makes one act no write serves yet, and starts a successor."""
    got = passed(reads(pulls=[pr(7), pr(42), pr(2, reviews=[support.review()])], runs=[run(number=42), run(number=2)]))
    assert [d["outcome"] for d in (e["decision"] for e in got["record"]["pull_requests"])] == ["admit", "act", "act"]
    return got


class Plan(unittest.TestCase):
    def test_the_writes_go_in_their_order(self):
        # The acts no write serves yet first, where a stop will go; then the dispatches in the record's item order; the
        # tracking issue, which every pass keeps, last but one; the successor last.
        got = writes_.plan(out())
        self.assertEqual([(w["id"], w["type"]) for w in got["writes"]],
                         [("w1", "not_built"), ("w2", "dispatch_run"), ("w3", "dispatch_approval"),
                          ("w4", "tracking_issue"), ("w5", "dispatch_successor")])
        self.assertEqual(got["writes"][0]["action"], "enqueue")
        self.assertEqual([w["name"] for w in got["writes"][1:3]], [d["name"] for d in out()["dispatch"]])
        quiet = passed(reads(pulls=[pr(7)]))
        self.assertEqual([w["type"] for w in writes_.plan(quiet)["writes"]], ["dispatch_run", "tracking_issue"])


class Effects(unittest.TestCase):
    def apply(self, plan, record, workflow, cfg=None, owner=OWNER, pause=None, issues=(), own=()):
        """The port's apply, the Pause read clear unless one is given, and no tracking issue open unless some are."""
        cfg = cfg or controller()
        org, repos = effects.scopes(plan, cfg)
        mine = effects.Allowed(github.Replay(list(own)), *effects.controller_permits(cfg, org, repos))
        return effects.apply(plan, record, {"workflow": workflow, "controller": mine}, cfg, owner,
                             pause=clear(plan, cfg) if pause is None else pause,
                             issues=None if issues is None else list(issues))

    def send(self, *exchanges, plan=None, record=None, cfg=None, pause=None):
        o = out()
        plan = plan or writes_.plan(o)
        replay = github.Replay(list(exchanges))
        cfg = cfg or controller()
        got = self.apply(plan, record or o["record"], effects.Allowed(replay, effects.workflow_permits(cfg)), cfg,
                         pause=pause)
        return got, replay

    def dispatches(self, o=None, statuses=(204, 204, 204)) -> list:
        """The three dispatches of `out()`'s plan, each answered as P-9's was, or with the status given."""
        o = o or out()
        plan = writes_.plan(o)
        found = []
        for w, status in zip([w for w in plan["writes"] if w["type"] in effects.DISPATCHES], statuses):
            kind = effects.DISPATCHES[w["type"]]
            body = {"ref": "main"}
            if kind != "poller":
                body["inputs"] = {"name": w["name"], "item": "%s#%d" % (w["item"]["repo"], w["item"]["number"]),
                                  "pass": o["record"]["pass"]}
            found.append(answered(effects.dispatch_path(controller(), kind), body, status))
        return found

    def test_every_write_the_port_sends_has_the_shape_a_trial_recorded(self):
        # L-50: a dispatch is a POST of a workflow's dispatches with a ref and its inputs, answered 204 with no body, as
        # the pass job's own token's was in trials/P-9.json; GitHub names no run in its answer.
        recorded = p9_dispatch()
        self.assertEqual((recorded["request"]["call"].split()[0], recorded["response"]["status"],
                          recorded["response"]["body"], sorted(recorded["request"]["body"])),
                         ("POST", 204, None, ["inputs", "ref"]))
        self.assertTrue(recorded["request"]["call"].endswith("/dispatches"))
        got, replay = self.send(*self.dispatches())
        self.assertEqual(replay._left, [])

    def test_a_claim_is_only_what_was_read_back(self):
        # A dispatch's answer names no run, so it is sent, never applied, and keeps no key; the next pass's records
        # port reads it back by its run-name. An act no write serves is refused, not_built.
        got, _ = self.send(*self.dispatches())
        self.assertEqual([(w["state"], w["key"], w["reason"]) for w in got["writes"]],
                         [("refused", None, "not_built"), ("sent", None, None), ("sent", None, None),
                          ("already_applied", None, None), ("sent", None, None)])
        self.assertFalse(effects.failed(got))
        self.assertEqual(effects.validate(got, effects.SCHEMAS["written"], schemas=effects.SCHEMAS), [])

    def test_a_dispatch_is_sent_once_and_never_retried(self):
        # GitHub answered with a 5xx, or did not answer: the dispatch may still have started a run, so it is failed and
        # never sent again in this pass; the next pass decides on the run list. Every write is sent exactly once.
        o = out()
        for statuses, state, reason in (((502, 204, 204), "failed", "dispatch_unanswered"),
                                        ((None, 204, 204), "failed", "dispatch_unanswered"),
                                        ((422, 204, 204), "failed", "dispatch_refused")):
            counted = Counted(*statuses)
            transport = {"workflow": effects.Allowed(counted, effects.workflow_permits(controller()))}
            got = self.apply(writes_.plan(o), o["record"], transport["workflow"])
            self.assertEqual((got["writes"][1]["state"], got["writes"][1]["reason"]), (state, reason), statuses)
            # A write that failed is a cause the tracking issue reports, in the same pass: here no issue is answered.
            self.assertEqual([w["state"] for w in got["writes"][2:]], ["sent", "failed", "sent"])
            self.assertEqual(len(counted.sent), 3, statuses)
            self.assertEqual(len({json.dumps(r["body"], sort_keys=True) for r in counted.sent}), 3)

    def test_a_refused_token_ends_every_later_write_on_it(self):
        for status in (401, 403):
            got, replay = self.send(*self.dispatches(statuses=(status, 204, 204))[:1])
            self.assertEqual([(w["state"], w["reason"]) for w in got["writes"][1:]],
                             [("refused", "token_refused")] * 2 + [("failed", "write_unanswered"), ("refused", "token_refused")],
                             status)
            self.assertEqual(replay._left, [])

    def test_nothing_is_dispatched_that_the_records_port_could_not_count(self):
        # I-34: while the configuration names no account for the workflow's own token, no Run and no approval is
        # dispatched; the successor, which is no Run, still is.
        got, replay = self.send(self.dispatches()[-1], cfg=controller(workflow_token=None))
        self.assertEqual([(w["state"], w["reason"]) for w in got["writes"]],
                         [("refused", "not_built"), ("refused", "uncounted"), ("refused", "uncounted"),
                          ("failed", "write_unanswered"), ("sent", None)])
        self.assertEqual(replay._left, [])
        # And with no token at all, nothing is sent.
        o = out()
        got = self.apply(writes_.plan(o), o["record"], None)
        self.assertEqual({w["reason"] for w in got["writes"] if w["type"] in effects.DISPATCHES}, {"no_credential"})

    def test_each_write_goes_through_its_one_credential_and_its_allowlist(self):
        cfg = controller()
        self.assertEqual(sorted(effects.workflow_permits(cfg)),
                         sorted(("POST", "/repos/combsmith/software-factory/actions/workflows/%s/dispatches" % f)
                                for f in ("run.yml", "approve.yml", "poller.yml")))
        class Anything:
            """A transport that answers every request, so only the allowlist can refuse one."""
            def send(self, req):
                return {"status": 204, "headers": {}, "body": None}
        allowed = effects.Allowed(Anything(), effects.workflow_permits(cfg))
        inputs = {"name": "n", "item": "i", "pass": "p"}
        self.assertEqual(allowed.send(github.request("POST", effects.dispatch_path(cfg, "run"),
                                                     body={"ref": "main", "inputs": inputs}))["status"], 204)
        self.assertEqual(allowed.send(github.request("POST", effects.dispatch_path(cfg, "poller"),
                                                     body={"ref": "main"}))["status"], 204)
        # Each dispatch's body is held too: on the home branch, a Run's with its three inputs, the successor's with none.
        for path, body in ((effects.dispatch_path(cfg, "run"), {"ref": "other", "inputs": inputs}),
                           (effects.dispatch_path(cfg, "run"), {"ref": "main", "inputs": dict(inputs, extra="x")}),
                           (effects.dispatch_path(cfg, "run"), {"ref": "main", "inputs": dict(inputs, name=7)}),
                           (effects.dispatch_path(cfg, "approval"), {"ref": "main"}),
                           (effects.dispatch_path(cfg, "poller"), {"ref": "main", "inputs": inputs}),
                           (effects.dispatch_path(cfg, "run"), None)):
            with self.assertRaises(github.Unanswered, msg=(path, body)):
                allowed.send(github.request("POST", path, body=body))
        for req in (github.request("GET", "/repos/combsmith/software-factory/actions/workflows/run.yml/dispatches"),
                    github.request("POST", "/repos/combsmith/other/actions/workflows/run.yml/dispatches"),
                    github.request("POST", "/repos/combsmith/software-factory/actions/workflows/ci.yml/dispatches"),
                    github.request("POST", "/repos/combsmith/software-factory/pulls/1/reviews"),
                    github.download("/repos/o/r/actions/artifacts/9/zip")):
            with self.assertRaises(github.Unanswered, msg=req):
                allowed.send(req)

    def test_a_write_list_that_is_not_the_records_is_refused_whole(self):
        # I-22: before anything is sent, the plan is held to its record; one that is not the record's sends nothing.
        o = out()
        plan = writes_.plan(o)

        def broken(change):
            bad = copy.deepcopy(plan)
            change(bad)
            return bad
        other = copy.deepcopy(o["record"])
        other["pass"] = "p_000099A"
        cases = [
            broken(lambda p: p.update(pass_="x") or p.update({"pass": "p_000099A"})),
            broken(lambda p: p.update(release="factory/v9.9.9")),
            broken(lambda p: p["writes"].reverse()),
            broken(lambda p: p["writes"][1].update(run="r_000099A")),
            broken(lambda p: p["writes"][1].update(name=p["writes"][1]["name"].replace("review-change", "fix-findings"))),
            broken(lambda p: p["writes"][1].update(name=p["writes"][1]["name"].replace("pr-review", "dev-lead"))),
            broken(lambda p: p["writes"][1].update(name=p["writes"][1]["name"].replace("#7 ", "#8 "))),
            broken(lambda p: p["writes"][1].update(item=dict(p["writes"][1]["item"], number=8))),
            broken(lambda p: p["writes"][1].update(type="dispatch_approval")),
            broken(lambda p: p["writes"][2].update(type="dispatch_run")),
            broken(lambda p: p["writes"][2].update(name=p["writes"][2]["name"].replace("sha256:", "sha256:f"))),
            broken(lambda p: p["writes"][2].update(run=p["writes"][1]["run"], name=p["writes"][1]["name"])),
            broken(lambda p: p["writes"].insert(0, p["writes"].pop()) or [w.update(id="w%d" % (n + 1))
                                                                        for n, w in enumerate(p["writes"])]),
            broken(lambda p: p["writes"][3].update(item=p["writes"][1]["item"])),
            broken(lambda p: p["writes"][0].update(action=None)),
            broken(lambda p: p["writes"][0].update(type="dequeue")),
            broken(lambda p: p["writes"][1].update(id="w9")),
            broken(lambda p: p["writes"][2].update(name=p["writes"][2]["name"].replace("pr-review", "dev-lead"))),
            broken(lambda p: p["writes"][1].update(action="enqueue")),
            broken(lambda p: p["writes"][1].update(name=p["writes"][1]["name"].replace(p["writes"][1]["run"],
                                                                                       p["writes"][2]["run"]))),
            broken(lambda p: (p["writes"].insert(1, p["writes"].pop(2)), [w.update(id="w%d" % (n + 1))
                                                                          for n, w in enumerate(p["writes"])])),
            broken(lambda p: (p["writes"].pop(1), [w.update(id="w%d" % (n + 1)) for n, w in enumerate(p["writes"])])),
            broken(lambda p: (p["writes"].insert(0, dict(p["writes"][0], action="merge")),
                              [w.update(id="w%d" % (n + 1)) for n, w in enumerate(p["writes"])])),
            broken(lambda p: p["writes"][0].update(item=dict(p["writes"][0]["item"], number=99))),
            broken(lambda p: p["writes"][-1].update(action="enqueue")),
            broken(lambda p: p["writes"].insert(2, copy.deepcopy(p["writes"][1])) or [w.update(id="w%d" % (n + 1))
                                                                                    for n, w in enumerate(p["writes"])]),
        ]
        for bad in cases:
            replay = github.Replay(self.dispatches())
            with self.assertRaises(effects.Refused, msg=bad["writes"]):
                self.apply(bad, o["record"], replay)
            self.assertEqual(len(replay._left), 3)
        with self.assertRaises(effects.Refused):
            self.apply(plan, other, github.Replay(self.dispatches()))
        # A successor exactly where the record says the pass decided one: added to a pass that decided none, or
        # dropped from one that did, the plan is refused.
        quiet = passed(reads(pulls=[pr(7)]))
        self.assertIs(quiet["record"]["successor"], False)
        added = writes_.plan(quiet)
        added["writes"].append({"id": "w%d" % (len(added["writes"]) + 1), "type": "dispatch_successor", "item": None,
                                "run": None, "name": None, "action": None})
        dropped = copy.deepcopy(plan)
        dropped["writes"].pop()
        for bad, record in ((added, quiet["record"]), (dropped, o["record"])):
            with self.assertRaises(effects.Refused):
                self.apply(bad, record, github.Replay(self.dispatches()))
        # An approval's run-name holds the configuration's owner Role, and no other.
        with self.assertRaises(effects.Refused):
            self.apply(plan, o["record"], github.Replay(self.dispatches()), owner="dev-lead")
        # A configuration that does not validate is refused too, an account held as no account among it.
        odd = controller(workflow_token={"id": None, "type": None})
        with self.assertRaises(effects.Refused):
            self.apply(plan, o["record"], github.Replay(self.dispatches()), cfg=odd)

    def test_a_failed_write_is_recorded_and_fails_the_step(self):
        o = out()
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            (folder / "pass.json").write_text(json.dumps(o["record"]))
            (folder / "writes.json").write_text(json.dumps(writes_.plan(o)))
            # No token at all: every write it would carry is refused, and the step fails.
            argv = [str(folder / "pass.json"), str(folder / "writes.json"), str(folder)]
            self.assertEqual(effects.main(argv, environ={}, base=tmp), 1)
            written = json.loads((folder / "written.json").read_text())
        # With no Controller token the Pause cannot be read, so no dispatch is sent; and while the configuration names
        # no account for the Controller's App, no tracking issue is written.
        self.assertEqual({w["reason"] for w in written["writes"][1:]}, {"pause_unreadable", "uncounted"})
        # A token the transport cannot take, or a plan refused whole, still leaves written.json, every write refused.
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            (folder / "pass.json").write_text(json.dumps(o["record"]))
            plan = writes_.plan(o)
            (folder / "writes.json").write_text(json.dumps(plan))
            argv = [str(folder / "pass.json"), str(folder / "writes.json"), str(folder)]
            self.assertEqual(effects.main(argv, environ={"WORKFLOW_TOKEN": "two words"}, base=tmp), 1)
            unreadable = json.loads((folder / "written.json").read_text())
            plan["pass"] = "p_000099A"
            (folder / "writes.json").write_text(json.dumps(plan))
            self.assertEqual(effects.main(argv, environ={}, base=tmp), 1)
            refused = json.loads((folder / "written.json").read_text())
            # A plan that cannot be read at all is refused with no write in it, and still fails the step.
            (folder / "writes.json").write_text(json.dumps({"schema": "writes/1"}))
            self.assertEqual(effects.main(argv, environ={}, base=tmp), 1)
            self.assertEqual(json.loads((folder / "written.json").read_text())["writes"], [])
        self.assertEqual({(w["state"], w["reason"]) for w in unreadable["writes"]}, {("refused", "token_unreadable")})
        self.assertEqual({(w["state"], w["reason"]) for w in refused["writes"]}, {("refused", "plan_refused")})
        self.assertEqual(len(refused["writes"]), 5)
        # A step given no folder it can write to sends nothing, and says so.
        counted = Counted()
        self.assertEqual(effects.main(["pass.json", "writes.json"], environ={}), 2)
        self.assertEqual(effects.main(["pass.json", "writes.json", "/no/such/folder"], environ={}), 2)
        # Nor does one given a path outside the directory it runs in, however the path is spelled.
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as elsewhere:
            (pathlib.Path(tmp) / "pass.json").write_text(json.dumps(o["record"]))
            (pathlib.Path(tmp) / "writes.json").write_text(json.dumps(writes_.plan(o)))
            (pathlib.Path(tmp) / "out").mkdir()
            os.symlink(elsewhere, str(pathlib.Path(tmp) / "link"))
            for argv in (["pass.json", "writes.json", elsewhere], ["../" + pathlib.Path(tmp).name + "/pass.json",
                         "/etc/hosts", "out"], ["pass.json", "writes.json", "link"],
                         ["pass.json", "writes.json", "out/../.."]):
                self.assertEqual(effects.main(argv, environ={}, base=tmp), 2, argv)
            # An OUT inside it that is no folder, or none at all, is refused too, before anything is sent.
            for out_ in ("missing", "pass.json"):
                self.assertEqual(effects.main(["pass.json", "writes.json", out_], environ={"WORKFLOW_TOKEN": "t"},
                                              base=tmp), 2, out_)
            self.assertEqual(counted.sent, [])
            self.assertEqual(effects.main(["pass.json", "writes.json", "out"], environ={}, base=tmp), 1)
            self.assertTrue((pathlib.Path(tmp) / "out" / "written.json").exists())
            self.assertEqual(list(pathlib.Path(elsewhere).iterdir()), [])
        self.assertEqual(counted.sent, [])
        # A pass whose only write is an act no write serves fails nothing.
        self.assertFalse(effects.failed({"writes": [{"state": "refused", "reason": "not_built"}]}))
        self.assertTrue(effects.failed({"writes": [{"state": "failed", "reason": "dispatch_unanswered"}]}))
        self.assertTrue(effects.failed({"writes": [{"state": "refused", "reason": "uncounted"}]}))

def issued(at: int, call: str, asked: dict, **answer) -> dict:
    """P-46's issue written (0, opened; 7, closed), asked as the tracking issue asks it: the path and body changed,
    GitHub's answer kept but for the fields given."""
    found = copy.deepcopy(json.loads((ROOT / "trials" / "P-46.json").read_text())["exchanges"][at])
    found["request"].update(call=call, body=asked)
    found["response"]["body"].update(answer)
    return found


class Pause(unittest.TestCase):
    def test_no_act_or_run_is_sent_unless_the_pause_reads_exactly_not_paused_on_every_scope(self):
        # #193's ruling 7: the Pause read again before any dispatch, the org's and each repo's the pass acts in, outside
        # the Kernel. A scope that pauses stops every dispatch, the successor's too, `paused`, which is no fault; one
        # not set, not read, or read as anything else stops them too, `pause_unreadable`, which is one. Nothing is sent.
        sending = Effects()
        o = out()
        plan = writes_.plan(o)
        org, repos = effects.scopes(plan, controller())
        self.assertEqual((org, repos), ("combsmith", ["combsmith/software-factory"]))
        clear_ = clear(plan, controller())
        for change, reason in ((dict(clear_, org="true"), "paused"),
                               (dict(clear_, repos={repos[0]: "true"}), "paused"),
                               (dict(clear_, org="true", repos={repos[0]: None}), "paused"),
                               (dict(clear_, org=None), "pause_unreadable"),
                               (dict(clear_, repos={}), "pause_unreadable"),
                               (dict(clear_, repos={repos[0]: "TRUE"}), "pause_unreadable"),
                               (dict(clear_, org=pause.UNREADABLE), "pause_unreadable"),
                               ({}, "pause_unreadable"), ("false", "pause_unreadable")):
            replay = github.Replay(sending.dispatches())
            got = sending.apply(plan, o["record"], effects.Allowed(replay, effects.workflow_permits(controller())),
                                pause=change)
            self.assertEqual({(w["state"], w["reason"]) for w in got["writes"] if w["type"] in effects.DISPATCHES},
                             {("refused", reason)}, change)
            self.assertEqual(len(replay._left), 3, change)
            self.assertIs(effects.failed(got), reason != "paused" or got["writes"][3]["state"] == "failed", change)
        # The Pause's values are the pass's own.
        self.assertEqual((pause.PAUSED, pause.NOT_PAUSED), (pass_.PAUSED, pass_.NOT_PAUSED))
        # A pass that acts in another repo reads that repo's Pause too.
        far = copy.deepcopy(plan)
        far["writes"][1]["item"] = dict(far["writes"][1]["item"], repo="combsmith/markets")
        self.assertEqual(effects.scopes(far, controller())[1], ["combsmith/markets", "combsmith/software-factory"])

    def test_a_pause_not_answered_as_a_variable_is_unreadable(self):
        # What the port can say before the trial: a scope that could name another path is not asked; no transport, no
        # answer and an answer that is not a variable's are unreadable; and a variable GitHub does not hold, answered
        # 404 as P-44's missing list was, is none. None is not "exactly not paused", so it stops every dispatch.
        missing = copy.deepcopy(json.loads((ROOT / "trials" / "P-44.json").read_text())["exchanges"][3])
        missing["request"]["call"] = "GET " + pause.path("combsmith/software-factory")
        self.assertEqual(pause.read(github.Replay([missing]), "combsmith/x/..", ["combsmith/software-factory"]),
                         {"org": pause.UNREADABLE, "repos": {"combsmith/software-factory": None}})
        self.assertEqual(pause.read(None, "combsmith", ["b/a", "a/b"]),
                         {"org": pause.UNREADABLE, "repos": {"a/b": pause.UNREADABLE, "b/a": pause.UNREADABLE}})
        asked = []

        class Clear:
            """Answers any request as a variable set to false would be, so only the port can refuse a scope."""
            def send(self, req):
                asked.append(req["path"])
                return {"status": 200, "headers": {}, "body": {"name": pause.NAME, "value": "false"}}
        for scope in ("combsmith/..", "-x", "a/b/c", "", "combsmith/software-factory?x=1", "combsmith/."):
            self.assertEqual(pause.read(Clear(), scope, [])["org"], pause.UNREADABLE, scope)
        self.assertEqual(asked, [])
        self.assertEqual(pause.read(Clear(), "combsmith", [])["org"], "false")
        self.assertEqual(asked, [pause.path("combsmith")])
        # An answer of 200 that is not this variable, by its name and a text value, is unreadable too.
        for body in ({"name": "OTHER", "value": "false"}, {"name": pause.NAME, "value": False}, {"name": pause.NAME},
                     ["false"]):
            class Odd:
                def send(self, req, body=body):
                    return {"status": 200, "headers": {}, "body": body}
            self.assertEqual(pause.read(Odd(), "combsmith", [])["org"], pause.UNREADABLE, body)
        refused = copy.deepcopy(missing)
        refused["response"]["status"] = 403
        self.assertEqual(pause.read(github.Replay([refused]), "x", ["combsmith/software-factory"])["repos"],
                         {"combsmith/software-factory": pause.UNREADABLE})
        self.assertEqual(effects.brake(pause.read(github.Replay([missing]), "x", ["combsmith/software-factory"]), "x",
                                       ["combsmith/software-factory"]), "pause_unreadable")

    @pending
    def test_the_pause_is_read_as_github_holds_the_variable(self):
        # The Controller's App reads FACTORY_PAUSED on the org and on a repo once the Maintainer grants it the
        # variables' read (#193's ruling 3); until the trial records both answers, this test is expected to fail.
        found = [e for path in sorted((ROOT / "trials").glob("P-*.json"))
                 for e in json.loads(path.read_text()).get("exchanges", [])
                 if "/actions/variables/FACTORY_PAUSED" in str((e.get("request") or {}).get("call", ""))]
        self.assertTrue(found)


class Tracking(unittest.TestCase):
    HOME = "combsmith/software-factory"

    def track(self, causes, found, *exchanges, cfg=None):
        cfg = cfg or controller()
        replay = github.Replay(list(exchanges))
        mine = effects.Allowed(replay, *effects.controller_permits(cfg, "combsmith", [self.HOME]))
        return effects.tracking(mine, cfg, out()["record"], causes, found), replay

    def test_one_tracking_issue_is_opened_once_edited_in_place_and_closed_when_clear(self):
        # #193's ruling 8: opened, with the Maintainer assigned, when a cause first stands and none is open; edited in
        # place, its body alone, when the causes change, which notifies no one; closed, completed, when none stands.
        # Each applied only on what GitHub's answer reads back, as P-46's answers give an issue.
        record = out()["record"]
        body = effects.rendered(record, ["not_run", "write_failed"])
        self.assertEqual(effects.causes_of(body), ["not_run", "write_failed"])
        opened = issued(0, "POST /repos/%s/issues" % self.HOME,
                        {"title": effects.TITLE, "body": body, "assignees": ["don-petry"]}, body=body, number=52)
        got, replay = self.track(["not_run", "write_failed"], [], opened)
        self.assertEqual((got, replay._left), (("applied", "52", None), []))
        same, replay = self.track(["not_run", "write_failed"], [{"number": 52, "causes": ["not_run", "write_failed"]}])
        self.assertEqual(same, ("already_applied", "52", None))
        edited_body = effects.rendered(record, ["not_run"])
        edited = issued(0, "PATCH /repos/%s/issues/52" % self.HOME, {"body": edited_body}, body=edited_body, number=52)
        got, replay = self.track(["not_run"], [{"number": 52, "causes": ["not_run", "write_failed"]}], edited)
        self.assertEqual((got, replay._left), (("applied", "52", None), []))
        closed = issued(7, "PATCH /repos/%s/issues/52" % self.HOME, {"state": "closed", "state_reason": "completed"},
                        number=52, state_reason="completed")
        got, replay = self.track([], [{"number": 52, "causes": ["not_run"]}], closed)
        self.assertEqual((got, replay._left), (("applied", "52", None), []))
        self.assertEqual(self.track([], [])[0], ("already_applied", None, None))
        # An answer that does not read back what was asked is sent, never applied: another state or body for the issue
        # opened, and another number for the one edited.
        for answer in ({"state": "closed"}, {"body": "else"}, {"number": "52"}):
            wrong = issued(0, "POST /repos/%s/issues" % self.HOME,
                           {"title": effects.TITLE, "body": body, "assignees": ["don-petry"]}, **dict({"body": body}, **answer))
            got, _ = self.track(["not_run", "write_failed"], [], wrong)
            self.assertEqual(got[0], "sent", answer)
        elsewhere = issued(0, "PATCH /repos/%s/issues/52" % self.HOME, {"body": edited_body}, body=edited_body, number=53)
        got, _ = self.track(["not_run"], [{"number": 52, "causes": ["not_run", "write_failed"]}], elsewhere)
        self.assertEqual(got[0], "sent")
        # A body lists its causes, sorted codes, and nothing from outside: one this port did not write lists none.
        self.assertEqual(effects.causes_of("anything\n- `not_run`"), None)
        self.assertEqual(body.split("\n")[0], effects.FIRST_LINE)
        self.assertIn(record["pass"], body)

    def test_the_persons_own_pause_opens_no_tracking_issue(self):
        # A Pause the Maintainer set is not a fault: it is no cause, and the issue it would open is not opened; a Pause
        # that cannot be read is one.
        o = out()
        record = dict(o["record"], alerts=["paused"])
        plan = writes_.plan(o)
        sending = Effects()
        got = sending.apply(plan, record, effects.Allowed(github.Replay([]), effects.workflow_permits(controller())),
                            pause=dict(clear(plan, controller()), org="true"))
        self.assertEqual(got["writes"][3]["state"], "already_applied")
        self.assertFalse(effects.failed(got))
        unread = dict(o["record"], alerts=["pause_unreadable"])
        got = sending.apply(plan, unread, effects.Allowed(github.Replay([]), effects.workflow_permits(controller())),
                            pause=dict(clear(plan, controller()), org=None))
        self.assertEqual(got["writes"][3]["reason"], "write_unanswered")

    def test_a_second_open_tracking_issue_is_never_written(self):
        # Two open issues of the App's: neither is written, and the step fails, so a person closes one. Open issues
        # that cannot all be read, or an App or a Maintainer the configuration does not name, write nothing either.
        got, replay = self.track(["not_run"], [{"number": 52, "causes": []}, {"number": 54, "causes": []}])
        self.assertEqual(got, ("refused", None, "tracking_issue_twice"))
        self.assertEqual(self.track(["not_run"], None)[0], ("failed", None, "issues_unreadable"))
        self.assertEqual(self.track(["not_run"], [], cfg=controller(controller=None))[0], ("refused", None, "uncounted"))
        self.assertEqual(self.track(["not_run"], [], cfg=controller(maintainer=None))[0], ("refused", None, "uncounted"))
        self.assertEqual(effects.tracking(None, controller(), out()["record"], ["not_run"], []),
                         ("refused", None, "no_credential"))
        for status, want in ((401, ("refused", None, "token_refused")), (502, ("failed", None, "write_unanswered"))):
            refused = issued(0, "POST /repos/%s/issues" % self.HOME,
                             {"title": effects.TITLE, "body": effects.rendered(out()["record"], ["not_run"]),
                              "assignees": ["don-petry"]})
            refused["response"]["status"] = status
            self.assertEqual(self.track(["not_run"], [], refused)[0], want, status)

    def test_the_controllers_token_sends_only_the_pause_and_the_tracking_issue(self):
        cfg = controller()
        permits, patterns = effects.controller_permits(cfg, "combsmith", [self.HOME])

        class Anything:
            def send(self, req):
                return {"status": 200, "headers": {}, "body": None}
        allowed = effects.Allowed(Anything(), permits, patterns)
        good = [github.request("GET", pause.path("combsmith")), github.request("GET", pause.path(self.HOME)),
                github.request("GET", effects.listed(self.HOME, cfg["accounts"]["controller"])),
                github.request("POST", "/repos/%s/issues" % self.HOME,
                               body={"title": effects.TITLE, "body": "b", "assignees": ["don-petry"]}),
                github.request("PATCH", "/repos/%s/issues/52" % self.HOME, body={"body": "b"}),
                github.request("PATCH", "/repos/%s/issues/52" % self.HOME,
                               body={"state": "closed", "state_reason": "completed"})]
        for req in good:
            self.assertEqual(allowed.send(req)["status"], 200, req)
        bad = [github.request("GET", pause.path("combsmith/other")),
               github.request("POST", "/repos/%s/issues" % self.HOME,
                              body={"title": effects.TITLE, "body": "b", "assignees": ["someone"]}),
               github.request("POST", "/repos/%s/issues" % self.HOME,
                              body={"title": "else", "body": "b", "assignees": ["don-petry"]}),
               github.request("PATCH", "/repos/%s/issues/52" % self.HOME, body={"body": "b", "title": "t"}),
               github.request("PATCH", "/repos/%s/issues/52" % self.HOME, body={"state": "closed"}),
               github.request("PATCH", "/repos/%s/issues/0" % self.HOME, body={"body": "b"}),
               github.request("PATCH", "/repos/%s/issues/52/x" % self.HOME, body={"body": "b"}),
               github.request("PATCH", "/repos/combsmith/other/issues/52", body={"body": "b"}),
               github.request("POST", "/repos/%s/issues/52/comments" % self.HOME, body={"body": "b"}),
               github.request("POST", effects.dispatch_path(cfg, "run"), body={"ref": "main"})]
        for req in bad:
            with self.assertRaises(github.Unanswered, msg=req):
                allowed.send(req)

    def test_the_open_issues_are_the_apps_own_told_by_its_account(self):
        # The list is one page of open issues by the App's bot login, each an issue as P-46's answer gives one. Kept are
        # those whose author is the App's account by id and type, never by a title or a login anyone can take; a pull
        # request among them is no issue; a list that names a next page, or that is no list, cannot all be read.
        cfg = controller()
        recorded = json.loads((ROOT / "trials" / "P-46.json").read_text())["exchanges"][0]["response"]["body"]
        mine = dict(copy.deepcopy(recorded), number=52, body=effects.rendered(out()["record"], ["not_run"]),
                    user=dict(recorded["user"], login=BOT["login"], id=BOT["id"], type="Bot"))
        theirs = dict(copy.deepcopy(recorded), number=53)
        named = dict(copy.deepcopy(mine), number=54, user=dict(mine["user"], id=999))
        pulled = dict(copy.deepcopy(mine), number=55, pull_request={"url": "x"})

        def listing(rows, status=200, link=""):
            return {"request": {"via": "rest", "call": "GET " + effects.listed(self.HOME, BOT), "headers": {}},
                    "response": {"status": status, "headers": {"link": link}, "body": rows}}
        self.assertEqual(effects.open_issues(github.Replay([listing([mine, theirs, named, pulled])]), cfg),
                         [{"number": 52, "causes": ["not_run"]}])
        for found in (listing([mine], link='<https://x>; rel="next"'), listing({"message": "x"}), listing([mine], 403),
                      listing([dict(mine, number="52")]), listing(["x"])):
            self.assertIsNone(effects.open_issues(github.Replay([found]), cfg), found["response"])
        self.assertIsNone(effects.open_issues(github.Replay([]), cfg))
        self.assertIsNone(effects.open_issues(None, cfg))
        self.assertIsNone(effects.open_issues(github.Replay([listing([mine])]), controller(controller=None)))

    @pending
    def test_the_open_tracking_issues_are_read_by_their_author(self):
        # The open issues the Controller's App opened, read by its bot login and kept by its account's id and type,
        # once the Maintainer grants it issues: write and a trial records the read (#193's ruling 12); until then this
        # test is expected to fail.
        found = [e for path in sorted((ROOT / "trials").glob("P-*.json"))
                 for e in json.loads(path.read_text()).get("exchanges", [])
                 if "/issues?state=open&creator=" in str((e.get("request") or {}).get("call", ""))]
        self.assertTrue(found)


class Asked(unittest.TestCase):
    @pending
    def test_a_dispatch_of_another_file_and_one_with_no_inputs_are_answered_as_a_trial_recorded(self):
        # P-9's dispatch was of the job's own file, with inputs. A dispatch of another file, as a pass dispatches
        # run.yml, and the successor's, with none, are asked by the workflows' canary trial (rulings on "Workflows: the
        # frozen entry shim, the poller, the Run's three jobs and the nudge, each held to its shape"); until its
        # fixture lands, this test is expected to fail.
        found = [e for path in sorted((ROOT / "trials").glob("P-*.json"))
                 for e in json.loads(path.read_text()).get("exchanges", [])
                 if str((e.get("request") or {}).get("call", "")).endswith("/run.yml/dispatches")]
        self.assertTrue(found)

    @pending
    def test_the_status_the_dequeue_and_the_tracking_issue_are_written_as_trials_recorded(self):
        # P-12 asks the check run's writes, P-2 the dequeue by the Controller's App, and a trial still to be filed the
        # tracking issue's; the port writes none of them until their fixtures land.
        self.assertTrue(hasattr(effects, "status_on_item") and hasattr(effects, "dequeue")
                        and hasattr(effects, "tracking_issue"))


if __name__ == "__main__":
    unittest.main()
