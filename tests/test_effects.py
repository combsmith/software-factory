"""The Controller's writes: the plan a pass makes, `controller/writes.py`, and the effects port that sends it,
`adapters/effects.py` (#193's rulings for PR 2). Each write the port sends is built from the shape a trial recorded:
a dispatch from `trials/P-9.json`, the pass job's own token's, answered 204 (L-50, L-51)."""
from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

from adapters import effects, github
from controller import writes as writes_
from tests import support
from tests.test_controller import config, passed, pr, reads, run

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTROLLER = json.loads((ROOT / "config" / "controller.json").read_text())


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
        got = effects.apply(plan, record or o["record"], {"workflow": effects.Allowed(replay, effects.workflow_permits(cfg))},
                            cfg)
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
        # never sent again in this pass; the next pass decides on the run list.
        got, replay = self.send(*self.dispatches(statuses=(502, 204, 204)))
        self.assertEqual([w["state"] for w in got["writes"]], ["refused", "failed", "sent", "sent"])
        self.assertEqual(got["writes"][1]["reason"], "dispatch_unanswered")
        self.assertEqual(replay._left, [])
        unanswered = self.dispatches()[1:]
        got, replay = self.send(*unanswered)
        self.assertEqual((got["writes"][1]["state"], got["writes"][1]["reason"]), ("failed", "dispatch_unanswered"))
        self.assertEqual([w["state"] for w in got["writes"][2:]], ["sent", "sent"])
        refused = self.dispatches(statuses=(422, 204, 204))
        self.assertEqual(self.send(*refused)[0]["writes"][1]["reason"], "dispatch_refused")

    def test_a_refused_token_ends_every_later_write_on_it(self):
        got, replay = self.send(*self.dispatches(statuses=(401, 204, 204))[:1])
        self.assertEqual([(w["state"], w["reason"]) for w in got["writes"][1:]],
                         [("refused", "token_refused")] * 3)
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
        got = effects.apply(writes_.plan(o), o["record"], {"workflow": None}, controller())
        self.assertEqual({w["reason"] for w in got["writes"][1:]}, {"no_credential"})

    def test_each_write_goes_through_its_one_credential_and_its_allowlist(self):
        cfg = controller()
        self.assertEqual(effects.workflow_permits(cfg),
                         [("POST", "/repos/combsmith/software-factory/actions/workflows/%s/dispatches" % f)
                          for f in ("run.yml", "approve.yml", "poller.yml")])
        class Anything:
            """A transport that answers every request, so only the allowlist can refuse one."""
            def send(self, req):
                return {"status": 204, "headers": {}, "body": None}
        allowed = effects.Allowed(Anything(), effects.workflow_permits(cfg))
        self.assertEqual(allowed.send(github.request("POST", effects.dispatch_path(cfg, "run"), body={}))["status"], 204)
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
            broken(lambda p: p["writes"].insert(2, copy.deepcopy(p["writes"][1])) or [w.update(id="w%d" % (n + 1))
                                                                                    for n, w in enumerate(p["writes"])]),
        ]
        for bad in cases:
            replay = github.Replay(self.dispatches())
            with self.assertRaises(effects.Refused, msg=bad["writes"]):
                effects.apply(bad, o["record"], {"workflow": replay}, controller())
            self.assertEqual(len(replay._left), 3)
        with self.assertRaises(effects.Refused):
            effects.apply(plan, other, {"workflow": github.Replay(self.dispatches())}, controller())

    def test_a_failed_write_is_recorded_and_fails_the_step(self):
        o = out()
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            (folder / "pass.json").write_text(json.dumps(o["record"]))
            (folder / "writes.json").write_text(json.dumps(writes_.plan(o)))
            # No token at all: every write it would carry is refused, and the step fails.
            argv = [str(folder / "pass.json"), str(folder / "writes.json"), str(folder)]
            self.assertEqual(effects.main(argv, environ={}), 1)
            written = json.loads((folder / "written.json").read_text())
        self.assertEqual({w["reason"] for w in written["writes"][1:]}, {"uncounted", "no_credential"})
        # A pass whose only write is an act no write serves fails nothing.
        self.assertFalse(effects.failed({"writes": [{"state": "refused", "reason": "not_built"}]}))
        self.assertTrue(effects.failed({"writes": [{"state": "failed", "reason": "dispatch_unanswered"}]}))
        self.assertTrue(effects.failed({"writes": [{"state": "refused", "reason": "uncounted"}]}))

if __name__ == "__main__":
    unittest.main()
