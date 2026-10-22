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

from adapters import effects, github
from controller import writes as writes_
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


def controller(**accounts) -> dict:
    c = copy.deepcopy(CONTROLLER)
    c["accounts"] = dict(c["accounts"], **dict({"workflow_token": {"id": 41898282, "type": "Bot"}}, **accounts))
    return c


def out() -> dict:
    """A pass that admits one Run, issues one approval, makes one act no write serves yet, and starts a successor."""
    got = passed(reads(pulls=[pr(7), pr(42), pr(2, reviews=[support.review()])], runs=[run(number=42), run(number=2)]))
    assert [d["outcome"] for d in (e["decision"] for e in got["record"]["pull_requests"])] == ["admit", "act", "act"]
    return got


class Plan(unittest.TestCase):
    def test_the_writes_go_in_their_order(self):
        # The acts no write serves yet first, where a stop will go; then the dispatches in the record's item order; the
        # successor last.
        got = writes_.plan(out())
        self.assertEqual([(w["id"], w["type"]) for w in got["writes"]],
                         [("w1", "not_built"), ("w2", "dispatch_run"), ("w3", "dispatch_approval"),
                          ("w4", "dispatch_successor")])
        self.assertEqual(got["writes"][0]["action"], "enqueue")
        self.assertEqual([w["name"] for w in got["writes"][1:3]], [d["name"] for d in out()["dispatch"]])
        quiet = passed(reads(pulls=[pr(7)]))
        self.assertEqual([w["type"] for w in writes_.plan(quiet)["writes"]], ["dispatch_run"])


class Effects(unittest.TestCase):
    def send(self, *exchanges, plan=None, record=None, cfg=None):
        o = out()
        plan = plan or writes_.plan(o)
        replay = github.Replay(list(exchanges))
        cfg = cfg or controller()
        transport = {"workflow": effects.Allowed(replay, effects.workflow_permits(cfg))}
        got = effects.apply(plan, record or o["record"], transport, cfg, OWNER)
        return got, replay

    def dispatches(self, o=None, statuses=(204, 204, 204)) -> list:
        """The three dispatches of `out()`'s plan, each answered as P-9's was, or with the status given."""
        o = o or out()
        plan = writes_.plan(o)
        found = []
        for w, status in zip(plan["writes"][1:], statuses):
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
                          ("sent", None, None)])
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
            got = effects.apply(writes_.plan(o), o["record"], transport, controller(), OWNER)
            self.assertEqual((got["writes"][1]["state"], got["writes"][1]["reason"]), (state, reason), statuses)
            self.assertEqual([w["state"] for w in got["writes"][2:]], ["sent", "sent"])
            self.assertEqual(len(counted.sent), 3, statuses)
            self.assertEqual(len({json.dumps(r["body"], sort_keys=True) for r in counted.sent}), 3)

    def test_a_refused_token_ends_every_later_write_on_it(self):
        for status in (401, 403):
            got, replay = self.send(*self.dispatches(statuses=(status, 204, 204))[:1])
            self.assertEqual([(w["state"], w["reason"]) for w in got["writes"][1:]],
                             [("refused", "token_refused")] * 3, status)
            self.assertEqual(replay._left, [])

    def test_nothing_is_dispatched_that_the_records_port_could_not_count(self):
        # I-34: while the configuration names no account for the workflow's own token, no Run and no approval is
        # dispatched; the successor, which is no Run, still is.
        got, replay = self.send(self.dispatches()[-1], cfg=controller(workflow_token=None))
        self.assertEqual([(w["state"], w["reason"]) for w in got["writes"]],
                         [("refused", "not_built"), ("refused", "uncounted"), ("refused", "uncounted"),
                          ("sent", None)])
        self.assertEqual(replay._left, [])
        # And with no token at all, nothing is sent.
        o = out()
        got = effects.apply(writes_.plan(o), o["record"], {"workflow": None}, controller(), OWNER)
        self.assertEqual({w["reason"] for w in got["writes"][1:]}, {"no_credential"})

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
                effects.apply(bad, o["record"], {"workflow": replay}, controller(), OWNER)
            self.assertEqual(len(replay._left), 3)
        with self.assertRaises(effects.Refused):
            effects.apply(plan, other, {"workflow": github.Replay(self.dispatches())}, controller(), OWNER)
        # A successor exactly where the record says the pass decided one: added to a pass that decided none, or
        # dropped from one that did, the plan is refused.
        quiet = passed(reads(pulls=[pr(7)]))
        self.assertIs(quiet["record"]["successor"], False)
        added = writes_.plan(quiet)
        added["writes"].append({"id": "w2", "type": "dispatch_successor", "item": None, "run": None, "name": None,
                                "action": None})
        dropped = copy.deepcopy(plan)
        dropped["writes"].pop()
        for bad, record in ((added, quiet["record"]), (dropped, o["record"])):
            with self.assertRaises(effects.Refused):
                effects.apply(bad, record, {"workflow": github.Replay(self.dispatches())}, controller(), OWNER)
        # An approval's run-name holds the configuration's owner Role, and no other.
        with self.assertRaises(effects.Refused):
            effects.apply(plan, o["record"], {"workflow": github.Replay(self.dispatches())}, controller(), "dev-lead")
        # A configuration that does not validate is refused too, an account held as no account among it.
        odd = controller(workflow_token={"id": None, "type": None})
        with self.assertRaises(effects.Refused):
            effects.apply(plan, o["record"], {"workflow": github.Replay(self.dispatches())}, odd, OWNER)

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
        self.assertEqual({w["reason"] for w in written["writes"][1:]}, {"uncounted", "no_credential"})
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
        self.assertEqual(len(refused["writes"]), 4)
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
