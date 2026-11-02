"""The Controller's writes: the plan a pass makes, `controller/writes.py`, and the effects port that sends it,
`adapters/effects.py` (#193's rulings for PR 2). Each write the port sends is built from the shape a trial recorded:
a dispatch from `trials/P-9.json`, the pass job's own token's, answered 204 (L-50, L-51)."""
from __future__ import annotations

import copy
import json
import os
import pathlib
import re
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


# A stand-in for the Controller's bot account, so that no test here depends on the one the configuration holds.
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
        # Each status goes after the dispatches, in item order, and before the tracking issue, which can say one failed.
        both = passed(reads(pulls=[dict(pr(7), head="a" * 40), dict(pr(8), head="b" * 40)]))
        self.assertEqual([(w["type"], (w["item"] or {}).get("number")) for w in writes_.plan(both)["writes"]],
                         [("dispatch_run", 7), ("dispatch_run", 8), ("status_on_item", 7), ("status_on_item", 8), ("tracking_issue", None)])


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

    def test_a_plan_not_its_records_is_refused_before_anything_is_read(self):
        # The step holds the plan to its record before it reads the Pause or the open issues with the Controller's
        # token: a plan that is not the record's names no scope to read, and asks nothing of GitHub.
        sent = []

        class Recorded:
            def __init__(self, token, timeout=None):
                self.token = token

            def send(self, req):
                sent.append((self.token, req["method"], req["path"]))
                return {"status": 404, "headers": {}, "body": {"message": "Not Found"}}
        o = out()
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            (folder / "pass.json").write_text(json.dumps(o["record"]))
            plan = writes_.plan(o)
            plan["pass"] = "p_000099A"
            (folder / "writes.json").write_text(json.dumps(plan))
            argv = ["pass.json", "writes.json", "."]
            original = effects.Live
            effects.Live = Recorded
            try:
                self.assertEqual(effects.main(argv, environ={"WORKFLOW_TOKEN": "w"}, base=tmp, mint=lambda environ, config: (Recorded("c"), lambda: True)), 1)
                refused = json.loads((folder / "written.json").read_text())
                self.assertEqual(sent, [])
                # The record's own plan reads the Pause and the open issues, with the Controller's token alone.
                (folder / "writes.json").write_text(json.dumps(writes_.plan(o)))
                self.assertEqual(effects.main(argv, environ={"WORKFLOW_TOKEN": "w"}, base=tmp, mint=lambda environ, config: (Recorded("c"), lambda: True)), 1)
            finally:
                effects.Live = original
        self.assertEqual({(w["state"], w["reason"]) for w in refused["writes"]}, {("refused", "plan_refused")})
        self.assertEqual({token for token, _, _ in sent}, {"c"})
        self.assertEqual(sorted(path for _, method, path in sent if method == "GET"),
                         sorted([pause.listed("combsmith/software-factory"), pause.path("combsmith/software-factory"),
                                 effects.listed("combsmith/software-factory",
                                                json.loads((ROOT / "config" / "controller.json").read_text())["accounts"]["controller"])]))

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
        # With no Controller token the Pause cannot be read, so no dispatch is sent, and no tracking issue is written.
        self.assertEqual({w["reason"] for w in written["writes"][1:]}, {"pause_unreadable", "no_credential"})
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
        quiet = dict(o["record"], alerts=[])
        for change, reason in ((dict(clear_, org="true"), "paused"),
                               (dict(clear_, repos={repos[0]: "true"}), "paused"),
                               (dict(clear_, org="true", repos={repos[0]: None}), "paused"),
                               (dict(clear_, org=None), "pause_unreadable"),
                               (dict(clear_, repos={}), "pause_unreadable"),
                               (dict(clear_, repos={repos[0]: "TRUE"}), "pause_unreadable"),
                               (dict(clear_, org=pause.UNREADABLE), "pause_unreadable"),
                               ({}, "pause_unreadable"), ("false", "pause_unreadable")):
            replay = github.Replay(sending.dispatches())
            got = sending.apply(plan, quiet, effects.Allowed(replay, effects.workflow_permits(controller())),
                                pause=change)
            self.assertEqual({(w["state"], w["reason"]) for w in got["writes"] if w["type"] in effects.DISPATCHES},
                             {("refused", reason)}, change)
            self.assertEqual(len(replay._left), 3, change)
            # A pass with no alert, held by a person's Pause, fails nothing; a Pause unread fails the step.
            self.assertIs(effects.failed(got), reason != "paused", change)
        # The Pause's values are the pass's own.
        self.assertEqual((pause.PAUSED, pause.NOT_PAUSED), (pass_.PAUSED, pass_.NOT_PAUSED))
        # A pass that acts in another repo reads that repo's Pause too.
        far = copy.deepcopy(plan)
        far["writes"][1]["item"] = dict(far["writes"][1]["item"], repo="combsmith/markets")
        self.assertEqual(effects.scopes(far, controller())[1], ["combsmith/markets", "combsmith/software-factory"])
        # And one in another org is stopped: its org's Pause is no one's read.
        away = copy.deepcopy(plan)
        away["writes"][1]["item"] = dict(away["writes"][1]["item"], repo="elsewhere/markets")
        org, repos = effects.scopes(away, controller())
        self.assertEqual(effects.brake({"org": "false", "repos": {r: "false" for r in repos}}, org, repos),
                         "pause_unreadable")

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
            self.assertEqual(pause.read(Clear(), "combsmith", [scope])["repos"], {scope: pause.UNREADABLE}, scope)
        self.assertEqual(asked, [])
        self.assertEqual(pause.read(Clear(), "", ["combsmith/software-factory"])["repos"],
                         {"combsmith/software-factory": "false"})
        self.assertEqual(asked, [pause.path("combsmith/software-factory")])
        # An answer of 200 that is not this variable, by its name and a text value, is unreadable too.
        for body in ({"name": "OTHER", "value": "false"}, {"name": pause.NAME, "value": False}, {"name": pause.NAME},
                     ["false"]):
            class Odd:
                def send(self, req, body=body):
                    return {"status": 200, "headers": {}, "body": body}
            self.assertEqual(pause.read(Odd(), "", ["combsmith/software-factory"])["repos"],
                             {"combsmith/software-factory": pause.UNREADABLE}, body)
        refused = copy.deepcopy(missing)
        refused["response"]["status"] = 403
        self.assertEqual(pause.read(github.Replay([refused]), "x", ["combsmith/software-factory"])["repos"],
                         {"combsmith/software-factory": pause.UNREADABLE})
        self.assertEqual(effects.brake(pause.read(github.Replay([missing]), "x", ["combsmith/software-factory"]), "x",
                                       ["combsmith/software-factory"]), "pause_unreadable")

    def test_the_pause_is_read_as_github_holds_the_variable(self):
        # The Controller's App reads FACTORY_PAUSED on a repo, granted the variables' read (#193's ruling 3), as P-52
        # recorded GitHub's answer on 2026-10-27: the variable's own text.
        recorded = json.loads((ROOT / "trials" / "P-52.json").read_text())
        repo = recorded["repo"]
        answer = next(e for e in recorded["exchanges"]
                      if e["request"]["call"] == "GET /repos/%s/actions/variables/FACTORY_PAUSED" % repo)
        self.assertEqual(answer["response"]["status"], 200)
        self.assertEqual(pause.read(github.Replay([answer]), "", [repo])["repos"], {repo: "false"})

    def test_the_orgs_pause_is_read_through_the_repos_list_of_the_orgs_variables(self):
        # Issue 362: GitHub refuses the Controller's token the org's own variable (P-52's 403), and names it, with its
        # value, in the repo's list of the org's variables, which P-52 read: eight variables, FACTORY_PAUSED false.
        recorded = json.loads((ROOT / "trials" / "P-52.json").read_text())
        repo = recorded["repo"]
        listed = next(e for e in recorded["exchanges"] if "/actions/organization-variables" in e["request"]["call"])
        own = next(e for e in recorded["exchanges"]
                   if e["request"]["call"] == "GET /repos/%s/actions/variables/FACTORY_PAUSED" % repo)
        self.assertEqual(pause.read(github.Replay([listed, own]), "combsmith", [repo]),
                         {"org": "false", "repos": {repo: "false"}})
        home = "combsmith/software-factory"
        entry = lambda name, value="false": {"name": name, "value": value, "created_at": "2026-10-24T14:24:01Z",
                                             "updated_at": "2026-10-24T14:24:01Z"}
        nxt = {"link": '<https://api.github.com/repositories/1/actions/organization-variables?per_page=100&page=2>; '
                       'rel="next"'}

        class Pages:
            """Answers the org's list page by page, as the pages given, the repo's own variable as false once they are
            spent, and records each path asked."""
            def __init__(self, *pages):
                self.pages, self.asked = list(pages), []

            def send(self, req):
                self.asked.append(req["path"])
                if not self.pages:
                    return {"status": 200, "headers": {}, "body": {"name": pause.NAME, "value": "false"}}
                status, body, headers = self.pages.pop(0)
                return {"status": status, "headers": headers, "body": body}
        one = lambda *variables: (200, {"total_count": len(variables), "variables": list(variables)}, {})
        # Read whole and naming it: its value. Over two pages, each named by the last's next link, the first a full page,
        # as many as the count says.
        full = [entry("V%d" % i) for i in range(pause.PAGE)]
        for pages, want in (([one(entry("OTHER"), entry(pause.NAME, "true"))], "true"),
                            ([(200, {"total_count": 101, "variables": full}, nxt),
                              (200, {"total_count": 101, "variables": [entry(pause.NAME)]}, {})], "false")):
            asked = Pages(*pages)
            self.assertEqual(pause.read(asked, "combsmith", [home])["org"], want, pages)
            # Each page by its own path, as GitHub names it, the first with no page number.
            self.assertEqual(asked.asked[:len(pages)], [
                "/repos/combsmith/software-factory/actions/organization-variables?per_page=100",
                "/repos/combsmith/software-factory/actions/organization-variables?per_page=100&page=2"][:len(pages)])
        # A list GitHub never answers, a connection dropped, is unreadable, never a raise.

        class Dropped:
            def send(self, req):
                if "/organization-variables" in req["path"]:
                    raise github.Unanswered("the connection dropped")
                return {"status": 200, "headers": {}, "body": {"name": pause.NAME, "value": "false"}}
        self.assertIs(pause.read(Dropped(), "combsmith", [home])["org"], pause.UNREADABLE)
        # The other side, each unreadable. A list read whole that does not name it, since the list holds only the org's
        # variables shared with the repo (decision 0077); a refusal, or any answer but 200 however it reads; a list
        # short of its count, or past it, or a count that moves between pages; a next page after a page short of a full
        # one, or after every entry the count names; a name twice, whatever its case; an entry that is not one, or a
        # value that is not text; no count, or one that is no whole number.
        for pages in ([one(entry("OTHER"))], [one()],
                      [(403, {"message": "Resource not accessible by integration"}, {})],
                      [(404, {"total_count": 1, "variables": [entry(pause.NAME)]}, {})],
                      [(500, {"total_count": 1, "variables": [entry(pause.NAME)]}, {})],
                      [(200, {"total_count": 2, "variables": [entry(pause.NAME)]}, {})],
                      [(200, {"total_count": 1, "variables": [entry("OTHER"), entry(pause.NAME)]}, {})],
                      [(200, {"total_count": 101, "variables": full}, nxt),
                       (200, {"total_count": 102, "variables": [entry(pause.NAME), entry("THIRD")]}, {})],
                      [(200, {"total_count": 2, "variables": [entry("OTHER")]}, nxt),
                       (200, {"total_count": 2, "variables": [entry(pause.NAME)]}, {})],
                      [(200, {"total_count": 2, "variables": []}, nxt)],
                      [(200, {"total_count": 1, "variables": [entry(pause.NAME)]}, nxt)],
                      [one(entry(pause.NAME), entry(pause.NAME, "true"))],
                      [one(entry(pause.NAME), entry("factory_paused", "true"))],
                      [(200, {"total_count": 1, "variables": [5]}, {})],
                      [(200, {"total_count": 1, "variables": [{"value": "false"}]}, {})],
                      [one(entry(pause.NAME, False))],
                      [(200, {"variables": [entry(pause.NAME)]}, {})],
                      [(200, {"total_count": True, "variables": [entry(pause.NAME)]}, {})],
                      [(200, {"total_count": 1, "variables": "x"}, {})],
                      [(200, ["false"], {})]):
            self.assertIs(pause.read(Pages(*pages), "combsmith", [home])["org"], pause.UNREADABLE, pages)
        # A list that names a next page after a page short of a full one, or after every entry its count names, is not
        # asked again, however many pages it would go on naming.
        for page in ((200, {"total_count": 2, "variables": []}, nxt),
                     (200, {"total_count": pause.PAGE, "variables": full}, nxt)):
            asked = Pages(*[page] * 4)
            self.assertIs(pause.read(asked, "combsmith", [home])["org"], pause.UNREADABLE, page)
            self.assertEqual(sum(p.startswith(pause.listed(home)) for p in asked.asked), 1, page)
        # With no repo to read it through, or a repo of another owner, the org's Pause is unreadable, and nothing is
        # asked; it is read through the first repo, once, however many are given.
        for org, repos in (("combsmith", []), ("other", [home]), ("-x", [home])):
            asked = Pages(one(entry(pause.NAME)), (200, {"name": pause.NAME, "value": "false"}, {}))
            self.assertIs(pause.read(asked, org, repos)["org"], pause.UNREADABLE, (org, repos))
            self.assertNotIn(pause.listed(home), asked.asked)
        asked = Pages(one(entry(pause.NAME)), *[(200, {"name": pause.NAME, "value": "false"}, {})] * 2)
        pause.read(asked, "combsmith", ["combsmith/z", "combsmith/a"])
        self.assertEqual(asked.asked[0], pause.listed("combsmith/a"))


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
        him = [dict(json.loads((ROOT / "trials" / "P-46.json").read_text())["exchanges"][0]["response"]["body"]["user"],
                    login="don-petry", id=36422719, type="User")]
        body = effects.rendered(record, ["not_run", "write_failed"])
        self.assertEqual(effects.causes_of(body), ["not_run", "write_failed"])
        opened = issued(0, "POST /repos/%s/issues" % self.HOME,
                        {"title": effects.TITLE, "body": body, "assignees": ["don-petry"]}, body=body, number=52,
                        assignees=him)
        got, replay = self.track(["not_run", "write_failed"], [], opened)
        self.assertEqual((got, replay._left), (("applied", "52", None), []))
        same, replay = self.track(["not_run", "write_failed"],
                                  [{"number": 52, "causes": ["not_run", "write_failed"], "assigned": True}])
        self.assertEqual(same, ("already_applied", "52", None))
        edited_body = effects.rendered(record, ["not_run"])
        edited = issued(0, "PATCH /repos/%s/issues/52" % self.HOME, {"body": edited_body}, body=edited_body, number=52,
                        assignees=him)
        got, replay = self.track(["not_run"], [{"number": 52, "causes": ["not_run", "write_failed"], "assigned": True}],
                                 edited)
        self.assertEqual((got, replay._left), (("applied", "52", None), []))
        # An assignment GitHub dropped is failed, where he sees it, and the next pass assigns him again, whatever the
        # causes, so that he is notified.
        dropped = issued(0, "POST /repos/%s/issues" % self.HOME,
                         {"title": effects.TITLE, "body": body, "assignees": ["don-petry"]}, body=body, number=52)
        self.assertEqual(self.track(["not_run", "write_failed"], [], dropped)[0], ("failed", "52", "assignee_dropped"))
        again = issued(0, "PATCH /repos/%s/issues/52" % self.HOME, {"body": body, "assignees": ["don-petry"]}, body=body,
                       number=52, assignees=him)
        got, replay = self.track(["not_run", "write_failed"],
                                 [{"number": 52, "causes": ["not_run", "write_failed"], "assigned": False}], again)
        self.assertEqual((got, replay._left), (("applied", "52", None), []))
        still = issued(0, "PATCH /repos/%s/issues/52" % self.HOME, {"body": body, "assignees": ["don-petry"]}, body=body,
                       number=52)
        self.assertEqual(self.track(["not_run", "write_failed"],
                                    [{"number": 52, "causes": ["not_run", "write_failed"], "assigned": False}], still)[0],
                         ("failed", "52", "assignee_dropped"))
        closed = issued(7, "PATCH /repos/%s/issues/52" % self.HOME, {"state": "closed", "state_reason": "completed"},
                        number=52, state_reason="completed")
        got, replay = self.track([], [{"number": 52, "causes": ["not_run"], "assigned": True}], closed)
        self.assertEqual((got, replay._left), (("applied", "52", None), []))
        # Closed for another reason, or none, is not what was asked: sent, never applied.
        for reason in ("not_planned", None):
            other = issued(7, "PATCH /repos/%s/issues/52" % self.HOME, {"state": "closed", "state_reason": "completed"},
                           number=52, state_reason=reason)
            self.assertEqual(self.track([], [{"number": 52, "causes": ["not_run"], "assigned": True}], other)[0][0],
                             "sent", reason)
        self.assertEqual(self.track([], [])[0], ("already_applied", None, None))
        # An answer that does not read back what was asked is sent, never applied: another state or body for the issue
        # opened, and another number for the one edited.
        for answer in ({"state": "closed"}, {"body": "else"}, {"number": "52"}):
            wrong = issued(0, "POST /repos/%s/issues" % self.HOME,
                           {"title": effects.TITLE, "body": body, "assignees": ["don-petry"]}, **dict({"body": body}, **answer))
            got, _ = self.track(["not_run", "write_failed"], [], wrong)
            self.assertEqual(got[0], "sent", answer)
        elsewhere = issued(0, "PATCH /repos/%s/issues/52" % self.HOME, {"body": edited_body}, body=edited_body, number=53)
        got, _ = self.track(["not_run"], [{"number": 52, "causes": ["not_run", "write_failed"], "assigned": True}],
                            elsewhere)
        self.assertEqual(got[0], "sent")
        # A body lists its causes, sorted codes, and nothing from outside: one this port did not write, or one anyone
        # edited by a line, lists none, and is no tracking issue.
        for other in ("anything\n- `not_run`", None, body[:-1], body.replace("\n\n", "\ninjected text\n\n"),
                      body + "more\n", body.replace("- `not_run`", "- `Not run`"), body.replace("Written by pass", "By")):
            self.assertIsNone(effects.causes_of(other), other)
        self.assertEqual(effects.causes_of(effects.rendered(record, [])), [])
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
        # With nothing to report, an App unnamed is no fault: a quiet pass under the shipped configuration fails nothing.
        self.assertEqual(self.track([], [], cfg=controller(controller=None))[0], ("refused", None, "no_account"))
        self.assertFalse(effects.failed({"writes": [{"state": "refused", "reason": "no_account"}]}))
        self.assertEqual(effects.tracking(None, controller(), out()["record"], ["not_run"], []),
                         ("refused", None, "no_credential"))
        for status, want in ((401, ("refused", None, "token_refused")), (502, ("failed", None, "write_unanswered")),
                             (422, ("failed", None, "write_refused")), (404, ("failed", None, "write_refused")),
                             (410, ("failed", None, "write_refused"))):
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
        good = [github.request("GET", pause.listed(self.HOME)), github.request("GET", pause.listed(self.HOME, 2)),
                github.request("GET", pause.listed(self.HOME, 12)), github.request("GET", pause.path(self.HOME)),
                github.request("GET", effects.listed(self.HOME, cfg["accounts"]["controller"])),
                github.request("POST", "/repos/%s/issues" % self.HOME,
                               body={"title": effects.TITLE, "body": "b", "assignees": ["don-petry"]}),
                github.request("PATCH", "/repos/%s/issues/52" % self.HOME, body={"body": "b"}),
                github.request("PATCH", "/repos/%s/issues/52" % self.HOME, body={"body": "b", "assignees": ["don-petry"]}),
                github.request("PATCH", "/repos/%s/issues/52" % self.HOME,
                               body={"state": "closed", "state_reason": "completed"})]
        for req in good:
            self.assertEqual(allowed.send(req)["status"], 200, req)
        # With two repos, the org's list is read through the first, as the port reads it, and no other.
        two, pages = effects.controller_permits(cfg, "combsmith", ["combsmith/b", "combsmith/a"])
        self.assertIn(("GET", pause.listed("combsmith/a")), two)
        self.assertNotIn(("GET", pause.listed("combsmith/b")), two)
        through = effects.Allowed(Anything(), two, pages)
        self.assertEqual(through.send(github.request("GET", pause.listed("combsmith/a", 2)))["status"], 200)
        for path in (pause.listed("combsmith/b", 2), pause.listed(self.HOME, 2)):
            with self.assertRaises(github.Unanswered, msg=path):
                through.send(github.request("GET", path))
        bad = [github.request("GET", pause.path("combsmith/other")),
               # The org's own variable, which GitHub refuses the Controller's token (P-52), is never asked (issue 362).
               github.request("GET", "/orgs/combsmith/actions/variables/FACTORY_PAUSED"),
               github.request("GET", pause.listed("combsmith/other")),
               github.request("GET", pause.listed(self.HOME) + "&page=1"),
               github.request("GET", pause.listed(self.HOME) + "&page=0"),
               github.request("GET", pause.listed(self.HOME) + "&page=2x"),
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
               github.request("POST", effects.dispatch_path(cfg, "run"), body={"ref": "main"}),
               github.request("GET", pause.listed(self.HOME), body={}),
               github.request("POST", "/repos/%s/issues" % self.HOME,
                              body={"title": effects.TITLE, "body": 7, "assignees": ["don-petry"]}),
               github.request("PATCH", "/repos/%s/issues/52" % self.HOME, body={"body": 7}),
               github.request("PATCH", "/repos/%s/issues/52" % self.HOME, body={"body": "b", "assignees": ["someone"]}),
               github.request("PATCH", "/repos/%s/issues/52" % self.HOME, body={"body": 7, "assignees": ["don-petry"]}),
               github.request("PATCH", "/repos/%s/issues/52" % self.HOME, body={"assignees": ["don-petry"]})]
        for req in bad:
            with self.assertRaises(github.Unanswered, msg=req):
                allowed.send(req)
        # With no Maintainer named, no issue may be opened at all.
        unnamed = effects.Allowed(Anything(), *effects.controller_permits(controller(maintainer=None), "combsmith",
                                                                          [self.HOME]))
        with self.assertRaises(github.Unanswered):
            unnamed.send(github.request("POST", "/repos/%s/issues" % self.HOME,
                                        body={"title": effects.TITLE, "body": "b", "assignees": [None]}))

    def test_the_open_issues_are_the_apps_own_told_by_its_account(self):
        # The list is one page of open issues by the App's bot login, each an issue as P-46's answer gives one. Kept are
        # those whose author is the App's account by id and type, never by a title or a login anyone can take, and whose
        # body this port wrote; a pull request among them is no issue; a list that names a next page, or that is no
        # list, cannot all be read.
        cfg = controller()
        recorded = json.loads((ROOT / "trials" / "P-46.json").read_text())["exchanges"][0]["response"]["body"]
        mine = dict(copy.deepcopy(recorded), number=52, body=effects.rendered(out()["record"], ["not_run"]),
                    user=dict(recorded["user"], login=BOT["login"], id=BOT["id"], type="Bot"))
        theirs = dict(copy.deepcopy(recorded), number=53)
        named = dict(copy.deepcopy(mine), number=54, user=dict(mine["user"], id=999))
        pulled = dict(copy.deepcopy(mine), number=55, pull_request={"url": "x"})
        other = dict(copy.deepcopy(mine), number=56, body="An issue the App opened for something else.")

        def listing(rows, status=200, link=""):
            return {"request": {"via": "rest", "call": "GET " + effects.listed(self.HOME, BOT), "headers": {}},
                    "response": {"status": status, "headers": {"link": link}, "body": rows}}
        assignee = dict(recorded["user"], login="don-petry", id=36422719, type="User")
        his = dict(copy.deepcopy(mine), number=57, assignees=[assignee])
        self.assertEqual(effects.open_issues(github.Replay([listing([mine, theirs, named, pulled, other, his])]), cfg),
                         [{"number": 52, "causes": ["not_run"], "assigned": False},
                          {"number": 57, "causes": ["not_run"], "assigned": True}])
        # He is assigned only by his account's id and login together.
        for someone in (dict(assignee, id=1), dict(assignee, login="don-petry-2")):
            self.assertEqual(effects.open_issues(github.Replay([listing([dict(his, assignees=[someone])])]), cfg)[0]["assigned"],
                             False, someone)
        for found in (listing([mine], link='<https://x>; rel="next"'), listing({"message": "x"}), listing([mine], 403),
                      listing([dict(mine, number="52")]), listing(["x"]), listing([dict(mine, assignees=None)])):
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


class Status(unittest.TestCase):
    """The status on the item (#193's ruling 6, P-12): one check run by the Controller's App on each head, edited in place,
    written only when the Decision changed, and never passing or failing."""
    HEAD = "fc6f2b03e078f5d8de03dfaa142afbd00dec35ea"
    APP = 5364130
    STATUS = {"name": "factory", "app_id": APP, "feed": json.loads((ROOT / "config" / "feed.json").read_text()), "run_id": "777"}

    class Asked:
        """Each request held to the Controller's permits and answered in turn, as P-12's answers stand."""

        def __init__(self, cfg, *answers):
            self.answers, self.sent = list(answers), []
            self.allowed = effects.Allowed(self, *effects.controller_permits(cfg, "combsmith", ["combsmith/software-factory"]))

        def send(self, req):
            self.sent.append(req)
            answer = self.answers.pop(0)
            if answer is None:
                raise github.Unanswered("no answer")
            return answer

    def run_on(self, **change):
        """A status check run as P-12 read one, with the node id the port's other writes read back."""
        base = json.loads((ROOT / "trials" / "P-12.json").read_text())["exchanges"][2]["response"]["body"]
        return dict(base, name="factory", head_sha=self.HEAD, app={"id": self.APP, "slug": "combsmith-sf-controller"},
                    node_id="CR_kw", **change)

    def listing(self, *runs, total=None):
        return {"status": 200, "headers": {}, "body": {"total_count": len(runs) if total is None else total, "check_runs": list(runs)}}

    def record(self, **decision):
        o = passed(reads(pulls=[pr(7)]))
        entry = o["record"]["pull_requests"][0]
        entry["head"] = self.HEAD
        entry["decision"] = dict(entry["decision"], **decision)
        return o

    def write(self, o, *answers, cfg=None, status=None):
        cfg = cfg or controller()
        asked = self.Asked(cfg, *answers)
        entry = o["record"]["pull_requests"][0]
        got = effects.write_status(asked.allowed, entry, o["record"], cfg, status or self.STATUS)
        return got, asked.sent

    def test_the_status_is_written_only_when_the_decision_changes(self):
        o = self.record()
        decision = o["record"]["pull_requests"][0]["decision"]
        want = effects.status_id(decision)
        self.assertTrue(re.fullmatch(r"d[0-9a-f]{32}", want))
        # Any change to the Decision, its evidence among it, changes the key; the order of its keys does not.
        for name in decision:
            self.assertNotEqual(effects.status_id(dict(decision, **{name: ["changed"]})), want, name)
        self.assertEqual(effects.status_id(dict(reversed(list(decision.items())))), want)
        # None on the head: one is made, on that head, by name.
        got, sent = self.write(o, self.listing(), {"status": 201, "headers": {}, "body": self.run_on(external_id=want)})
        self.assertEqual(got, ("applied", "CR_kw", None, True))
        self.assertEqual([r["method"] for r in sent], ["GET", "POST"])
        self.assertEqual(sent[0]["path"], "/repos/combsmith/software-factory/commits/%s/check-runs?check_name=factory&app_id=%d&filter=all&per_page=100" % (self.HEAD, self.APP))
        self.assertEqual(sent[1]["path"], "/repos/combsmith/software-factory/check-runs")
        self.assertEqual((sent[1]["body"]["name"], sent[1]["body"]["head_sha"], sent[1]["body"]["external_id"]), ("factory", self.HEAD, want))
        # One carrying this Decision: nothing is written.
        got, sent = self.write(o, self.listing(self.run_on(external_id=want)))
        self.assertEqual(got, ("already_applied", "CR_kw", None, False))
        self.assertEqual(len(sent), 1)
        # One carrying another: it is edited in place, the whole output sent, and it stays one run.
        old = self.run_on(external_id="d" + "a" * 32)
        got, sent = self.write(o, self.listing(old), {"status": 200, "headers": {}, "body": dict(old, external_id=want)})
        self.assertEqual(got, ("applied", "CR_kw", None, True))
        self.assertEqual((sent[1]["method"], sent[1]["path"]), ("PATCH", "/repos/combsmith/software-factory/check-runs/%d" % old["id"]))
        self.assertEqual(sent[1]["body"]["external_id"], want)
        self.assertEqual(set(sent[1]["body"]["output"]), {"title", "summary"})
        # P-12: created twice, the later of the two is what GitHub shows. It alone is edited, and it alone says the Decision
        # is written: an older run carrying this Decision, the later another, is written again.
        newer = dict(old, id=old["id"] + 1)
        _, sent = self.write(o, self.listing(old, newer), {"status": 200, "headers": {}, "body": dict(newer, external_id=want)})
        self.assertEqual(sent[1]["path"], "/repos/combsmith/software-factory/check-runs/%d" % newer["id"])
        self.assertEqual(self.write(o, self.listing(old, dict(newer, external_id=want)))[0][0], "already_applied")
        _, sent = self.write(o, self.listing(dict(old, external_id=want), newer), {"status": 200, "headers": {}, "body": dict(newer, external_id=want)})
        self.assertEqual((sent[1]["method"], sent[1]["path"]), ("PATCH", "/repos/combsmith/software-factory/check-runs/%d" % newer["id"]))
        # One carrying this Decision but not neutral and finished is not the status as written: it is edited back.
        for change in ({"status": "in_progress"}, {"conclusion": "success"}):
            got, sent = self.write(o, self.listing(dict(self.run_on(external_id=want), **change)),
                                   {"status": 200, "headers": {}, "body": self.run_on(external_id=want)})
            self.assertEqual((got[0], sent[1]["method"]), ("applied", "PATCH"), change)
        # Another App's run of the name, or another name, is not the status: one is made.
        for other in (dict(old, app={"id": 9, "slug": "x"}, external_id=want), dict(old, name="other", external_id=want)):
            got, sent = self.write(o, self.listing(other), {"status": 201, "headers": {}, "body": self.run_on(external_id=want)})
            self.assertEqual((got[0], sent[1]["method"]), ("applied", "POST"), other["name"])

    def test_what_is_not_read_back_fails_and_says_so(self):
        o = self.record()
        want = effects.status_id(o["record"]["pull_requests"][0]["decision"])
        made = lambda **c: {"status": 201, "headers": {}, "body": dict(self.run_on(external_id=want), **c)}
        # P-12: GitHub answers a 200 that may not hold what was sent, so each field is read back.
        for change in ({"external_id": "x"}, {"head_sha": "0" * 40}, {"name": "other"}, {"app": {"id": 9}}, {"app": None},
                       {"status": "queued"}, {"conclusion": "success"}, {"node_id": None}, {"node_id": ""}, {"id": "1"},
                       {"node_id": "CR kw"}, {"node_id": "C" * 101}):
            got, _ = self.write(o, self.listing(), made(**change))
            self.assertEqual(got, ("failed", None, "not_read_back", True), change)
        # An edit that answers of another run.
        old = self.run_on(external_id="d" + "a" * 32)
        got, _ = self.write(o, self.listing(old), {"status": 200, "headers": {}, "body": dict(old, id=old["id"] + 1, external_id=want)})
        self.assertEqual(got, ("failed", None, "not_read_back", True))
        # One carrying this Decision with a node id `written/1` cannot hold cannot be matched by reconciliation.
        for node in (None, "CR kw", "C" * 101):
            self.assertEqual(self.write(o, self.listing(dict(self.run_on(external_id=want), node_id=node)))[0], ("failed", None, "not_read_back", False), node)
        # A list that cannot be read writes nothing.
        for bad in (self.listing(total=2), {"status": 500, "headers": {}, "body": None}, {"status": 200, "headers": {}, "body": []},
                    self.listing(*[self.run_on(external_id="x")] * 100)):
            got, sent = self.write(o, bad)
            self.assertEqual((got[0], got[2], len(sent)), ("failed", "checks_unreadable", 1))
        self.assertEqual(self.write(o, None)[0][2], "checks_unreadable")
        # A write GitHub did not take was still sent.
        self.assertEqual(self.write(o, self.listing(), {"status": 422, "headers": {}, "body": {}})[0], ("failed", None, "write_refused", True))
        self.assertEqual(self.write(o, self.listing(), {"status": 500, "headers": {}, "body": {}})[0], ("failed", None, "write_unanswered", True))
        self.assertEqual(self.write(o, self.listing(), None)[0], ("failed", None, "write_unanswered", True))
        # An edit answered as a create was not taken, and the other way about.
        self.assertEqual(self.write(o, self.listing(), {"status": 200, "headers": {}, "body": self.run_on(external_id=want)})[0][0], "failed")
        self.assertEqual(self.write(o, self.listing(self.run_on(external_id="x")), {"status": 201, "headers": {}, "body": self.run_on(external_id=want)})[0][0], "failed")

    def test_the_status_neither_passes_nor_fails(self):
        o = self.record()
        want = effects.status_id(o["record"]["pull_requests"][0]["decision"])
        _, sent = self.write(o, self.listing(), {"status": 201, "headers": {}, "body": self.run_on(external_id=want)})
        self.assertEqual((sent[1]["body"]["status"], sent[1]["body"]["conclusion"]), ("completed", "neutral"))
        old = self.run_on(external_id="x")
        _, sent = self.write(o, self.listing(old), {"status": 200, "headers": {}, "body": dict(old, external_id=want)})
        self.assertEqual((sent[1]["body"]["status"], sent[1]["body"]["conclusion"]), ("completed", "neutral"))
        # The Controller's token may send no other, and no other field: it never reaches GitHub.
        cfg = controller()
        asked = self.Asked(cfg, self.listing())
        for body in (dict(sent[1]["body"], conclusion="success"), dict(sent[1]["body"], status="queued"), dict(sent[1]["body"], annotations=[])):
            with self.assertRaises(github.Unanswered):
                asked.allowed.send({"method": "PATCH", "path": "/repos/combsmith/software-factory/check-runs/1", "body": body})
        for body in ({"status": "completed", "conclusion": "neutral", "external_id": "d", "output": {}},):
            with self.assertRaises(github.Unanswered):
                asked.allowed.send({"method": "POST", "path": "/repos/combsmith/software-factory/check-runs", "body": body})
        # Nor on another repo.
        with self.assertRaises(github.Unanswered):
            asked.allowed.send({"method": "PATCH", "path": "/repos/other/repo/check-runs/1", "body": sent[1]["body"]})
        # Nor anything but the status's own values, whichever the caller hands it: another name would speak for a Lens.
        edit = dict(sent[1]["body"], details_url="https://github.com/combsmith/software-factory/actions/runs/777", external_id=want)
        ok = asked.allowed
        asked.answers[:] = [self.listing(), self.listing()]
        made = dict(edit, name="factory", head_sha=self.HEAD)
        ok.send({"method": "PATCH", "path": "/repos/combsmith/software-factory/check-runs/1", "body": edit})
        ok.send({"method": "POST", "path": "/repos/combsmith/software-factory/check-runs", "body": made})
        wrong = [dict(edit, external_id="anything"), dict(edit, external_id=None), dict(edit, output={"title": "t", "summary": "s", "annotations": []}),
                 dict(edit, output={"title": "t"}), dict(edit, output="t"), dict(edit, output={"title": 1, "summary": "s"}),
                 dict(edit, output={"title": "t", "summary": 1}), dict(edit, output={"title": "t" * 256, "summary": "s"}),
                 dict(edit, output={"title": "t", "summary": "s" * 4097}), dict(edit, details_url="https://example.com/"),
                 dict(edit, details_url="https://github.com/other/repo/actions/runs/777"), dict(edit, details_url=7)]
        for body in wrong:
            with self.assertRaises(github.Unanswered):
                ok.send({"method": "PATCH", "path": "/repos/combsmith/software-factory/check-runs/1", "body": body})
        for body in (dict(made, name="verify"), dict(made, name=None), dict(made, head_sha="not-a-commit"), dict(made, head_sha=None)):
            with self.assertRaises(github.Unanswered):
                ok.send({"method": "POST", "path": "/repos/combsmith/software-factory/check-runs", "body": body})

    def test_the_status_carries_codes_and_identifiers_alone(self):
        o = self.record(evidence=["fine:one", "a title with spaces", "a" * 201, 7, "x\n"])
        d = o["record"]["pull_requests"][0]["decision"]
        output = effects.status_output(d, o["record"], self.STATUS["feed"])
        self.assertEqual(output["title"], "%s: %s" % (d["state"], d["reason"]))
        lines = output["summary"].split("\n")
        for shown in ("attention: %s" % d["attention"], "outcome: %s" % d["outcome"], "action: null",
                      "next_actor: %s" % effects.feed_.next_actor(d, self.STATUS["feed"]), "content_id: null",
                      "pass: %s" % o["record"]["pass"], "release: %s" % o["record"]["release"], "evidence: fine:one", "and 4 not shown"):
            self.assertIn(shown, lines, shown)
        self.assertNotIn("a title with spaces", output["summary"])
        # The Kernel's own forms are shown: a Lens's from a workflow's path, an item, an account.
        for form in ("verify:from_workflow:.github/workflows/x.yml", "repo#7", "a@b"):
            self.assertIn("evidence: %s" % form, effects.status_output(dict(d, evidence=[form]), o["record"], self.STATUS["feed"])["summary"])
        # What a Decision holds as null is shown as the Decision's schema says it, never as Python does.
        empty = effects.status_output(dict(d, state=None, action=None, content_id=None, attention=None, outcome=None, reason=None), o["record"], self.STATUS["feed"])
        self.assertEqual(empty["title"], "null: null")
        self.assertNotIn("None", empty["summary"])
        self.assertIn("action: null", empty["summary"].split("\n"))
        self.assertNotIn("a" * 201, output["summary"])
        # At most twenty evidence items, then how many more; no more than four KiB whatever they are.
        many = effects.status_output(dict(d, evidence=["e%d" % i for i in range(25)]), o["record"], self.STATUS["feed"])["summary"]
        self.assertIn("evidence: e19", many)
        self.assertNotIn("evidence: e20", many)
        self.assertIn("and 5 more", many)
        long_ = effects.status_output(dict(d, evidence=[("%02d" % i) + "e" * 198 for i in range(20)]), o["record"], self.STATUS["feed"])["summary"]
        self.assertLessEqual(len(long_), effects.SUMMARY_MOST)
        self.assertIn("more", long_)
        # Whichever length the evidence stops at, the closing lines still fit.
        for first in range(1, 201):
            evidence = ["e" * first] + ["%02d" % i + "e" * 198 for i in range(30)] + ["not a code"]
            got = effects.status_output(dict(d, evidence=evidence), o["record"], self.STATUS["feed"])["summary"]
            self.assertLessEqual(len(got), effects.SUMMARY_MOST, first)
        # The pass's run is where it points; with none that can be read it names none.
        want = effects.status_id(d)
        _, sent = self.write(o, self.listing(), {"status": 201, "headers": {}, "body": self.run_on(external_id=want)})
        self.assertEqual(sent[1]["body"]["details_url"], "https://github.com/combsmith/software-factory/actions/runs/777")
        _, sent = self.write(o, self.listing(), {"status": 201, "headers": {}, "body": self.run_on(external_id=want)}, status=dict(self.STATUS, run_id=None))
        self.assertNotIn("details_url", sent[1]["body"])

    def test_no_status_is_written_on_an_item_left_alone(self):
        def entry(**facts):
            return passed(reads(pulls=[dict(pr(7, **facts), head=self.HEAD)]))

        def kinds(o):
            return [w["type"] for w in writes_.plan(o)["writes"]]
        base = entry()
        self.assertEqual(kinds(base).count("status_on_item"), 1)
        self.assertEqual(base["record"]["pull_requests"][0]["head"], self.HEAD)
        self.assertEqual([(w["type"], w["item"], w["run"], w["name"], w["action"]) for w in writes_.plan(base)["writes"] if w["type"] != "dispatch_successor"],
                         effects.expected(base["record"], OWNER))
        person = support.labelled("factory:hands-off")
        whole = dict(support.facts()["complete"])
        left = {
            "hands-off": {"label_events": [person]},
            # The Kernel reads a draft, and an incomplete read, before hands-off: a person's label still holds.
            "hands-off on a draft": {"label_events": [person], "is_draft": True},
            "hands-off with the checks not read": {"label_events": [person], "complete": dict(whole, checks=False)},
            "not served": {"targets_protected": False},
            # The Kernel reads an incomplete read before the base, too.
            "not served with the checks not read": {"targets_protected": False, "complete": dict(whole, checks=False)},
            "merged": {"state": "merged"},
            "closed": {"state": "closed"},
            # With the label events not read whole, nothing says a person did not.
            "timeline not read": {"complete": dict(whole, timeline=False)},
            "an event not read": {"label_events": [dict(person, by={"kind": "human", "name": "someone[bot]", "can_write": True})]},
        }
        for name, facts in left.items():
            o = entry(**facts)
            self.assertNotIn("head", o["record"]["pull_requests"][0], name)
            self.assertNotIn("status_on_item", kinds(o), name)
            self.assertEqual(effects.status_entries(o["record"]), [], name)
        # A draft, and an item whose other lists were not read, do get one: it says why nothing moves.
        for name, facts in {"draft": {"is_draft": True}, "checks not read": {"complete": dict(whole, checks=False)}}.items():
            self.assertEqual(kinds(entry(**facts)).count("status_on_item"), 1, name)
        # Hands-off a person did not place is read as a Hold, and a Hold is told.
        o = entry(label_events=[support.labelled("factory:hands-off", by=support.QUEUE_APP)])
        self.assertEqual(o["record"]["pull_requests"][0]["decision"]["reason"], "human_hold")
        self.assertEqual(kinds(o).count("status_on_item"), 1)
        # With no head read, none: nothing says which content it would describe.
        self.assertEqual(effects.status_entries(passed(reads(pulls=[pr(7)]))["record"]), [])
        # An issue has no commit, and the issue Lifecycle's labels are its status.
        self.assertEqual(effects.status_entries({"pull_requests": [], "issues": [{"decision": {}}]}), [])

    def test_a_pass_carries_the_head_read_beside_the_facts_and_only_a_commit(self):
        for head, want in (("a" * 40, "a" * 40), ("A" * 40, None), ("a" * 39, None), ("None", None), (None, None)):
            pull = dict(pr(7), head=head)
            entry = passed(reads(pulls=[pull]))["record"]["pull_requests"][0]
            self.assertEqual(entry.get("head"), want, head)
        self.assertNotIn("head", passed(reads(pulls=[pr(7)]))["record"]["pull_requests"][0])

    def test_the_status_reads_p12s_answers_as_they_stand(self):
        # P-12's trial named its run `status_on_item`, and the configuration names it `factory`; and it recorded no node id, as
        # the fixture's bodies list none, where the port's key is the id reconciliation reads. Both are varied, and no other.
        exchanges = json.loads((ROOT / "trials" / "P-12.json").read_text())["exchanges"]
        made = [e for e in exchanges if e["request"]["call"].startswith("POST") and e["request"]["call"].endswith("/check-runs")][0]
        all_two = [e for e in exchanges if "filter=all" in e["request"]["call"] and (e["response"]["body"] or {}).get("total_count") == 2][0]
        runs = [dict(r, node_id="CR_%d" % r["id"]) for r in all_two["response"]["body"]["check_runs"]]
        later = max(runs, key=lambda r: r["id"])
        runs = [dict(r, name="factory") for r in runs]
        later = max(runs, key=lambda r: r["id"])
        o = self.record()
        want = effects.status_id(o["record"]["pull_requests"][0]["decision"])
        got, sent = self.write(o, self.listing(*runs), {"status": 200, "headers": {}, "body": dict(later, external_id=want)})
        self.assertEqual(got, ("applied", later["node_id"], None, True))
        self.assertEqual(sent[1]["path"], "/repos/combsmith/software-factory/check-runs/%d" % later["id"])
        # What is sent is what the trial sent, and details_url beside it.
        _, sent = self.write(o, self.listing(), {"status": 201, "headers": {}, "body": dict(runs[0], external_id=want)})
        self.assertLessEqual(set(sent[1]["body"]) - {"details_url"}, set(made["request"]["body"]))
        self.assertLessEqual(set(sent[1]["body"]["output"]), set(made["request"]["body"]["output"]))

    def test_the_step_gives_the_status_its_name_its_app_and_its_run(self):
        class Silent:
            def send(self, req):
                raise github.Unanswered("no answer")
        o = self.record()
        given = []
        original = effects.apply

        def spy(writes, record, transports, config, owner, **rest):
            given.append(rest["status"])
            return original(writes, record, transports, config, owner, **rest)
        effects.apply = spy
        try:
            with tempfile.TemporaryDirectory() as tmp:
                (pathlib.Path(tmp) / "pass.json").write_text(json.dumps(o["record"]))
                (pathlib.Path(tmp) / "writes.json").write_text(json.dumps(writes_.plan(o)))
                for run_id in ("777", "7 7", "../x"):
                    effects.main(["pass.json", "writes.json", "."], environ={"GITHUB_RUN_ID": run_id}, base=tmp,
                                 mint=lambda environ, config: (Silent(), lambda: True))
                effects.main(["pass.json", "writes.json", "."], environ={}, base=tmp, mint=lambda environ, config: (Silent(), lambda: True))
        finally:
            effects.apply = original
        self.assertEqual([g["run_id"] for g in given], ["777", None, None, None])
        self.assertEqual(given[0]["name"], "factory")
        self.assertEqual(given[0]["app_id"], 5364130)
        self.assertEqual(given[0]["feed"], self.STATUS["feed"])

    def apply(self, o, cfg, *answers, pause=None, status=None, none=False):
        plan = writes_.plan(o)
        asked = self.Asked(cfg, *answers)
        got = effects.apply(plan, o["record"], {"workflow": None, "controller": None if none else asked.allowed}, cfg, OWNER,
                            pause=clear(plan, cfg) if pause is None else pause, issues=[], status=status or self.STATUS)
        return {w["type"]: w for w in got["writes"]}, asked.sent

    def test_a_status_is_written_under_a_pause_and_a_pass_writes_at_most_its_bound(self):
        cfg = controller()
        o = self.record()
        want = effects.status_id(o["record"]["pull_requests"][0]["decision"])
        made = {"status": 201, "headers": {}, "body": self.run_on(external_id=want)}
        issue = {"status": 201, "headers": {}, "body": {"number": 1, "assignees": [{"login": cfg["accounts"]["maintainer"]["login"]}]}}
        got, sent = self.apply(o, cfg, self.listing(), made, issue)
        self.assertEqual((got["status_on_item"]["state"], got["status_on_item"]["key"]), ("applied", "CR_kw"))
        # A Pause stops an act; a status is how a person sees why nothing moves.
        paused = {"org": "true", "repos": {"combsmith/software-factory": "false"}}
        got, _ = self.apply(o, cfg, self.listing(), made, issue, pause=paused)
        self.assertEqual(got["status_on_item"]["state"], "applied")
        # No Controller's token: refused, and a fault of the pass's.
        got, _ = self.apply(o, cfg, none=True)
        self.assertEqual((got["status_on_item"]["state"], got["status_on_item"]["reason"]), ("refused", "no_credential"))
        self.assertTrue(effects.failed({"writes": [got["status_on_item"]]}))
        # With no account of what to write it with, none.
        plan = writes_.plan(o)
        done = effects.apply(plan, o["record"], {"workflow": None, "controller": self.Asked(cfg, issue).allowed}, cfg, OWNER, pause=clear(plan, cfg), issues=[])
        self.assertEqual([w["reason"] for w in done["writes"] if w["type"] == "status_on_item"], ["no_credential"])
        # At the bound the rest wait for the next pass, which is no fault; a status not written does not count.
        two = passed(reads(pulls=[pr(7), pr(8), pr(9)]))
        for e in two["record"]["pull_requests"]:
            e["head"] = self.HEAD
        wants = [effects.status_id(e["decision"]) for e in two["record"]["pull_requests"]]
        bound = dict(cfg, max_status_writes=1)
        plan = writes_.plan(two)
        asked = self.Asked(bound, self.listing(self.run_on(external_id=wants[0])), self.listing(), {"status": 201, "headers": {}, "body": self.run_on(external_id=wants[1])}, issue)
        done = effects.apply(plan, two["record"], {"workflow": None, "controller": asked.allowed}, bound, OWNER, pause=clear(plan, bound), issues=[], status=self.STATUS)
        statuses = [(w["state"], w["reason"]) for w in done["writes"] if w["type"] == "status_on_item"]
        self.assertEqual(statuses, [("already_applied", None), ("applied", None), ("refused", "status_bounded")])
        self.assertFalse(effects.failed({"writes": [w for w in done["writes"] if w["type"] == "status_on_item"]}))
        self.assertEqual(CONTROLLER["max_status_writes"], 50)
        # A write GitHub limited still counts: the bound is on what is sent.
        asked = self.Asked(bound, self.listing(), {"status": 429, "headers": {}, "body": {}}, issue)
        done = effects.apply(plan, two["record"], {"workflow": None, "controller": asked.allowed}, bound, OWNER, pause=clear(plan, bound), issues=[], status=self.STATUS)
        self.assertEqual([w["reason"] for w in done["writes"] if w["type"] == "status_on_item"][1:], ["status_bounded", "status_bounded"])
        self.assertEqual([r["method"] for r in asked.sent], ["GET", "POST", "POST"])
        # A token GitHub refuses ends the statuses, and sends no more of them. The tracking issue asks for itself: a 403 may
        # be GitHub's limit, and an alert is not lost to one.
        asked = self.Asked(cfg, {"status": 403, "headers": {}, "body": {}}, issue)
        done = effects.apply(plan, two["record"], {"workflow": None, "controller": asked.allowed}, cfg, OWNER, pause=clear(plan, cfg), issues=[], status=self.STATUS)
        statuses = [(w["state"], w["reason"]) for w in done["writes"] if w["type"] == "status_on_item"]
        self.assertEqual(statuses, [("refused", "token_refused")] * 3)
        self.assertEqual(len(asked.sent), 2)
        self.assertEqual([w["state"] for w in done["writes"] if w["type"] == "tracking_issue"], ["sent"])


class StatusFixture(unittest.TestCase):
    def test_the_status_check_run_stands_as_p12_saw_it(self):
        # trials/P-12.json (issue 454): what the status write rests on, with the Controller's own token.
        fixture = json.loads((ROOT / "trials" / "P-12.json").read_text())
        self.assertEqual(fixture["verdict"], "pass")
        calls = [e for e in fixture["exchanges"] if e["request"]["as"].get("name") == "combsmith-sf-controller"]
        self.assertEqual(calls[0]["request"]["body"]["permissions"], {"checks": "write", "metadata": "read"})
        self.assertEqual(calls[-1]["response"]["status"], 204)
        made, read, mine, named, edited, again, one, second, latest, both, long_id, long_read, full, full_read, past, after_past = [e["response"] for e in calls[1:-1]]
        sent = calls[1]["request"]["body"]["external_id"]
        # The external_id reads back exactly; the list by name and App finds this App's alone, and by name alone both.
        self.assertEqual((made["status"], read["body"]["external_id"], read["body"]["id"]), (201, sent, made["body"]["id"]))
        self.assertEqual([c["id"] for c in mine["body"]["check_runs"]], [made["body"]["id"]])
        self.assertEqual({c["app"]["slug"] for c in named["body"]["check_runs"]}, {"combsmith-sf-controller", "github-actions"})
        # An edit keeps the id and reads back what it sent, and it stays one run in the list.
        wanted = calls[5]["request"]["body"]
        self.assertEqual((again["body"]["id"], again["body"]["external_id"], again["body"]["output"]), (made["body"]["id"], wanted["external_id"], wanted["output"]))
        self.assertEqual(one["body"]["total_count"], 1)
        # A second create is a second run: latest lists the later alone, all lists both.
        self.assertNotEqual(second["body"]["id"], made["body"]["id"])
        self.assertEqual([c["id"] for c in latest["body"]["check_runs"]], [second["body"]["id"]])
        self.assertEqual({c["id"] for c in both["body"]["check_runs"]}, {made["body"]["id"], second["body"]["id"]})
        # A long external_id is cut, answered 200; an edit with no output empties the text alone.
        self.assertEqual((long_id["status"], len(long_read["body"]["external_id"])), (200, 255))
        self.assertEqual(long_read["body"]["output"]["text"], None)
        self.assertEqual(long_read["body"]["output"]["title"], wanted["output"]["title"])
        self.assertEqual(long_read["body"]["output"]["summary"], wanted["output"]["summary"])
        # The output is kept at its limits, and one past them is refused, changing nothing.
        self.assertEqual(len(full_read["body"]["output"]["title"]), 255)
        self.assertEqual(full_read["body"]["output"]["summary"], "<65535 characters>")
        self.assertEqual(full_read["body"]["output"]["text"], "<65535 characters>")
        self.assertEqual(past["status"], 422)
        self.assertEqual(after_past["body"]["output"], full_read["body"]["output"])
        # After a push the new head lists none of them, and the old head all three.
        new, old = [e["response"]["body"] for e in fixture["exchanges"][-2:]]
        self.assertEqual((new["total_count"], old["total_count"]), (0, 3))


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
        # P-2 asks the dequeue by the Controller's App, and a trial still to be filed the tracking issue's; the port writes
        # neither as a trial recorded until their fixtures land. P-12's status is held by the class Status.
        self.assertTrue(hasattr(effects, "dequeue") and hasattr(effects, "tracking_issue"))


if __name__ == "__main__":
    unittest.main()
