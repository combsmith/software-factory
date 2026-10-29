"""The Controller's pass, as a function of what it read (issue 193, PR 1): the context from the reads, the Kernel asked
through its two entry points, the pass record, the Runs named, the view, health, the alerts and the successor.

Each case gives the pass recorded facts and run records, as the ports give them and as `examples/` and the trials hold
them, and a fake mint, and holds what comes back. Nothing here reaches the network or reads a clock.
"""
from __future__ import annotations

import ast
import contextlib
import copy
import io
import json
import os
import pathlib
import tempfile
import unittest
import unittest.mock

from adapters import acceptance, github, records
import controller.__main__ as entry
from controller import pass_, shared
from kernel.decide import decide
from tests import support
from tests import test_apply, test_issue
from tests.test_adapters import DISPATCHER, NAME, WORKFLOW, canary, exchanges, listing, outcome_of, outcome_zip, stored

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOW = support.NOW                       # 2026-10-11T13:00:00Z
REPO = support.ITEM["repo"]
OTHER_REPO = "combsmith/markets"
CONTROLLER = json.loads((ROOT / "config" / "controller.json").read_text())
TOKEN = {"id": 41898282, "type": "Bot"}       # the workflow's own token's account, as a configuration would hold it
RELAY = {"id": 900001, "type": "User"}        # a relay's account, as one would be held once the relay exists
APP_ACCOUNT = {"id": 5000001, "type": "Bot", "login": "combsmith-sf-controller[bot]"}  # the Controller App's, as a trial would record it
ROLE_ACCOUNT = {"id": 5000002, "type": "Bot", "login": "combsmith-sf-pr-review[bot]"}   # a Role App's


def config(**controller) -> dict:
    """What a pass is given: the Kernel's configuration, with issues served, each Work item's Lifecycle, the feed's
    table, the Controller's own, here with both accounts known, and the Release."""
    c = dict(copy.deepcopy(CONTROLLER), accounts=dict(CONTROLLER["accounts"], workflow_token=dict(TOKEN), relay=dict(RELAY),
                                                      controller=dict(APP_ACCOUNT),
                                                      roles={name: dict(ROLE_ACCOUNT) for name in CONTROLLER["accounts"]["roles"]}))
    c.update(controller)
    kernel = {k: v for k, v in copy.deepcopy(support.CONFIG).items() if k != "lifecycle"}
    kernel["issues"] = test_issue.config()["issues"]
    return {"kernel": kernel, "release": "factory/v0.3.1", "controller": c,
            "feed": json.loads((ROOT / "config" / "feed.json").read_text()),
            "lifecycles": {"pull_request": json.loads((ROOT / "lifecycle" / "pull_request.json").read_text()),
                           "issue": json.loads((ROOT / "lifecycle" / "issue.json").read_text())}}


class Mint:
    """A fake mint: each id in turn, in the forms the schemas hold."""

    def __init__(self):
        self.count = 0

    def __call__(self, prefix: str) -> str:
        self.count += 1
        return "%s_%06dA" % (prefix, self.count)


def run(name="r_01JA6Z", number=42, intent="review-change", role="pr-review", status="completed",
        conclusion="success", outcome=None, at="2026-10-11T12:10:00Z", content="sha256:aaaa") -> dict:
    """A run record as the records port gives one."""
    return {"run": name, "item": dict(support.ITEM, number=number), "role": role, "intent": intent,
            "content_id": content, "status": status, "conclusion": None if status != "completed" else conclusion,
            "outcome": outcome, "started_at": at}


def unnamed(run_id: str, created: str = "2026-10-11T12:59:58Z", status: str = "in_progress") -> dict:
    """A run the records port lists before its name: its id, when its record was created and its status (issue 270)."""
    return {"run": run_id, "created_at": created, "status": status}


def listed(runs=(), unidentified=(), complete=True) -> dict:
    """What the records port returns. An unnamed Run given by its id alone is one in flight, created two seconds before
    the pass."""
    return {"runs": [copy.deepcopy(r) for r in runs],
            "unidentified": [unnamed(u) if isinstance(u, str) else dict(u) for u in unidentified], "complete": complete,
            "reads": [{"read": "runs", "date": "2026-10-11T12:59:58Z", "age": 0}]}


def pr(number=42, title="A title", **over) -> dict:
    facts = support.facts(item=dict(support.ITEM, number=number), **over)
    return {"facts": facts, "title": title}


def an_issue(number=7, repo=REPO, title="An issue", **over) -> dict:
    return {"facts": test_issue.facts(item=dict(test_issue.ITEM, number=number, repo=repo), **over), "title": title}


# Every Factory identity's writes since the pass, read whole, and the Effects recorded, read whole: a reconciliation
# with nothing to match and nothing short (decision 0061).
# Its window opens after every run these tests list, so none is read as a dispatch no pass recorded.
SEEN = {"schema": "seen/1", "since": "2026-10-12T00:00:00Z", "whole": True, "writes": [], "merged": []}
RECORDED = {"applied": [], "written": [], "whole": True}


def reads(pulls=None, runs=(), unidentified=(), complete=True, pause=None, event="schedule", actor=None,
          attempt=1, issues=None, usage=None, records_=True, seen=SEEN, effects=RECORDED) -> dict:
    """What one pass read. By default: a scheduled run, no Pause anywhere, one pull request waiting for its review,
    the records port's list read whole, and a reconciliation that found nothing."""
    out = {"started": {"event": event, "actor": actor, "attempt": attempt},
           "pause": {"org": None, "repos": {REPO: None, OTHER_REPO: None}} if pause is None else pause,
           "records": listed(runs, unidentified, complete) if records_ else None,
           "pull_requests": [pr()] if pulls is None else pulls,
           "issues": [] if issues is None else issues,
           "facts_reads": [{"date": "2026-10-11T12:59:59Z", "age": 0}],
           "seen": copy.deepcopy(seen), "effects": copy.deepcopy(effects)}
    if usage is not None:
        out["usage"] = usage
    return out


def passed(r=None, cfg=None, now=NOW, previous=(), mint=None) -> dict:
    return pass_.run(reads() if r is None else r, config() if cfg is None else cfg, now,
                     list(previous) if previous is not None else None, mint or Mint())


def decisions(out: dict) -> list:
    return [e["decision"] for e in out["record"]["pull_requests"] + out["record"]["issues"]]


def earlier(now: str, since=None, started_by="schedule", read_at=None, pulls=None, runs=()) -> dict:
    """A pass record from an earlier pass at `now`, its chain begun at `since`."""
    out = passed(reads(pulls=[] if pulls is None else pulls, runs=runs), now=now, mint=Mint())
    record = out["record"]
    record["context"]["passes_since"] = now if since is None else since
    record["started_by"] = started_by
    if read_at is not None:
        record["reads"] = [{"read": "runs", "date": when, "age": 0} for when in read_at]
    return record


class Record(unittest.TestCase):
    def test_the_pass_record_holds_what_the_kernel_was_given_and_replays_it(self):  # decisions 0002, 0039
        # Every key of the context, every run record, each read's date and age, and each item's facts and Decision,
        # with the Run id minted beside the admission: replayed on a laptop, the Kernel gives the same Decision.
        out = passed(reads(pulls=[pr(7), pr(42)], runs=[run(number=42)]))
        record = out["record"]
        self.assertEqual(shared.errors(record, "pass"), [])
        self.assertEqual(sorted(record["context"]), ["active_runs", "model_deferred_until", "passes_since", "paused",
                                                     "unidentified_runs"])
        self.assertEqual(record["runs"], [run(number=42)])
        self.assertEqual([r["read"] for r in record["reads"]], ["runs", "facts"])
        self.assertEqual((record["pass"], record["started_by"], record["release"]), ("p_000001A", "schedule",
                                                                                   "factory/v0.3.1"))
        got = [(e["decision"]["outcome"], e["decision"].get("action"), e["run"]) for e in record["pull_requests"]]
        self.assertEqual(got, [("admit", None, "r_000002A"), ("act", "issue_approval", "r_000003A")])
        kernel = dict(config()["kernel"], lifecycle=config()["lifecycles"]["pull_request"])
        for entry in record["pull_requests"]:
            self.assertEqual(decide(entry["facts"], record["runs"], record["context"], kernel, record["now"]),
                             entry["decision"])
        self.assertNotIn("A title", json.dumps(record))

    def test_an_issue_is_asked_of_the_issues_kernel_with_its_own_lifecycle(self):  # decision 0028
        out = passed(reads(pulls=[], issues=[an_issue(7), an_issue(8, repo=OTHER_REPO)]))
        got = [(d["schema"], d["state"], d["outcome"], d.get("action")) for d in decisions(out)]
        self.assertEqual(got, [("issue-decision/1", "new", "act", "accept")] * 2)
        self.assertEqual([i["url"] for i in out["view"]["items"]["items"]],
                         ["https://github.com/%s/issues/7" % REPO, "https://github.com/%s/issues/8" % OTHER_REPO])
        self.assertEqual(out["view"]["items"]["items"][0]["untrusted"], {"title": "An issue"})
        # The issue's own Lifecycle: under the pull request's, every wait reads as past its limit.
        stale = config()
        stale["lifecycles"]["issue"] = stale["lifecycles"]["pull_request"]
        waiting = an_issue(9, label_events=test_issue.READIED_BY_A_PERSON)
        right = passed(reads(pulls=[], issues=[waiting]))
        wrong = passed(reads(pulls=[], issues=[waiting]), cfg=stale)
        self.assertNotEqual(decisions(right)[0]["attention"], "stale")
        self.assertEqual(decisions(wrong)[0]["attention"], "stale")
        # An issue's repo is a scope even when no read of the Pause names it: then it was not read (the follow-on).
        unread = passed(reads(pulls=[], issues=[an_issue(8, repo=OTHER_REPO)], pause={"org": None, "repos": {REPO: None}}))
        self.assertIsNone(unread["record"]["context"]["paused"])
        # An issue's repo has a Pause of its own, and it is read.
        held = passed(reads(pulls=[], issues=[an_issue(8, repo=OTHER_REPO)],
                            pause={"org": None, "repos": {REPO: None, OTHER_REPO: "true"}}))
        self.assertEqual(decisions(held)[0]["reason"], "paused")

    def test_only_an_admission_or_an_approval_gets_a_run_id(self):  # decision 0039
        out = passed(reads(pulls=[pr(1), pr(2, reviews=[support.review()]), pr(3, state="closed")],
                           runs=[run(number=2)]))
        got = [(e["decision"]["outcome"], e["decision"].get("action"), e["run"]) for e in out["record"]["pull_requests"]]
        self.assertEqual(got, [("admit", None, "r_000002A"), ("act", "enqueue", None), ("nothing", None, None)])
        approval = passed(reads(runs=[run()]))["record"]["pull_requests"][0]
        self.assertEqual((approval["decision"].get("action"), approval["run"]), ("issue_approval", "r_000002A"))

    def test_the_runs_to_dispatch_are_named_by_their_run_names(self):  # section 3.10
        out = passed(reads(pulls=[pr(1), pr(2)], runs=[run(number=2)]))
        self.assertEqual(out["dispatch"], [
            {"run": "r_000002A", "name": "sf %s#1 review-change pr-review sha256:aaaa r_000002A" % REPO},
            {"run": "r_000003A", "name": "sf %s#2 issue-approval pr-review sha256:aaaa r_000003A" % REPO}])
        for sent in out["dispatch"]:
            back = records.named(sent["name"])
            self.assertEqual(back["run"], sent["run"])
        self.assertEqual(records.named(out["dispatch"][1]["name"])["intent"], "issue-approval")

    def test_a_record_that_cannot_validate_is_refused_and_nothing_is_dispatched(self):
        with self.assertRaises(pass_.Refused):
            passed(mint=lambda prefix: "%s_bad" % prefix)
        with self.assertRaises(pass_.Refused):
            passed(reads(pulls=[pr(1), pr(2)]), mint=lambda prefix: "%s_000001A" % prefix)
        for facts_reads in ([{"date": "yesterday", "age": 0}], [{}], ["x"], [{"date": NOW, "age": 0, "by": "x"}]):
            undated = reads()
            undated["facts_reads"] = facts_reads
            with self.assertRaises(pass_.Refused, msg=facts_reads):
                passed(undated)
        # A list of items that could not be read is no empty list (Codex's read).
        for change in ({"pull_requests": None}, {"issues": "x"}):
            with self.assertRaises(pass_.Refused, msg=change):
                passed(dict(reads(), **change))
        # A pass told nothing it can read of what started it or when to wait is no pass.
        for broken in ({"read_gap_seconds": 0},
                       {"accounts": dict(CONTROLLER["accounts"], workflow_token={"id": None, "type": None}, relay=None)},
                       {"schema": "controller/2"}):
            with self.assertRaises(pass_.Refused, msg=broken):
                passed(cfg=config(**broken))

    def test_an_item_whose_facts_are_not_facts_is_left_out_and_raises_one_alert(self):  # issue 193, security pass
        # A path git allows and the schema does not, such as one ending in a newline, from anyone's pull request: the
        # item is left out, and every other item is decided as it would be without it.
        bad = pr(43, changed_paths=[support.changed("evil\n")])
        worse = pr(44)
        del worse["facts"]["checks"]
        out = passed(reads(pulls=[pr(42, reviews=[support.review()]), bad, worse], runs=[run()]))
        alone = passed(reads(pulls=[pr(42, reviews=[support.review()])], runs=[run()]))
        self.assertEqual(decisions(out), decisions(alone))
        self.assertEqual(out["left_out"], [dict(support.ITEM, number=43), dict(support.ITEM, number=44)])
        self.assertEqual((out["alerts"], alone["alerts"]), (["facts_unreadable"], []))
        self.assertEqual(passed(reads(pulls=[{"facts": None, "title": "x"}]))["left_out"], [None])
        self.assertEqual(passed(reads(pulls=[{"facts": {}}, "x"]))["left_out"], [None, None])
        # A good copy and a bad copy of one item: neither is decided (Argon's read of the merged pass).
        copies = passed(reads(pulls=[pr(42), {"facts": {"item": dict(support.ITEM, number=42)}, "title": "x"}]))
        self.assertEqual((decisions(copies), copies["dispatch"]), ([], []))
        self.assertEqual(copies["left_out"], [dict(support.ITEM, number=42)] * 2)
        # An item listed twice is decided neither time: one pass never dispatches two Runs on one item (Muse's read).
        twice = passed(reads(pulls=[pr(42), pr(42), pr(7)], issues=[an_issue(7), an_issue(7)]))
        self.assertEqual([d["item"]["number"] for d in decisions(twice)], [7])
        self.assertEqual(len(twice["dispatch"]), 1)
        self.assertEqual(twice["left_out"], [dict(support.ITEM, number=42)] * 2 + [dict(test_issue.ITEM, number=7)] * 2)

    def test_the_pass_asks_the_kernel_through_its_entry_points_alone(self):  # issue 193, ruling 8, amended for 270
        # The entry, `__main__.py`, is the one place that reads the clock and the environment (Entry, below).
        for module in sorted(m for m in (ROOT / "controller").glob("*.py") if m.name != "__main__.py"):
            tree = ast.parse(module.read_text())
            kernel = {a.asname or a.name: node.module + "." + a.name for node in ast.walk(tree)
                      if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "kernel"
                      for a in node.names}
            self.assertLessEqual(set(kernel.values()), {"kernel.decide", "kernel.issue", "kernel.terms"}, module)
            self.assertFalse([a.name for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names
                              if a.name.split(".")[0] in ("kernel", "time", "random", "os", "subprocess", "socket",
                                                          "urllib", "http")], module)
            used = {(n.value.id, n.attr) for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                    and isinstance(n.value, ast.Name) and n.value.id in kernel}
            # Each Lifecycle's decide, and the scope's reading of the unnamed Runs (issue 270).
            self.assertLessEqual({attr for name, attr in used if kernel[name] != "kernel.terms"},
                                 {"decide", "unnamed_scope"}, module)
            self.assertNotIn("now()", module.read_text(), module)
            self.assertNotIn("today()", module.read_text(), module)


class Context(unittest.TestCase):
    def test_a_pause_on_the_org_or_the_repo_is_a_pause_and_any_other_value_is_unreadable(self):  # L-58
        def paused(org, repo=None, repos=None):
            pause = {"org": org, "repos": {REPO: repo} if repos is None else repos}
            return passed(reads(pause=pause))["record"]["context"]["paused"]
        self.assertIs(paused(None), False)
        self.assertIs(paused("false", "false"), False)
        self.assertIs(paused("true"), True)
        self.assertIs(paused(None, "true"), True)
        self.assertIs(paused("TRUE", "true"), True)       # a Pause that can be read is a Pause
        for value in ("True", "TRUE", "1", "yes", " true", "true ", "", True, False, 1, "False"):
            self.assertIsNone(paused(value), value)
            self.assertIsNone(paused(None, value), value)
        self.assertIsNone(paused(None, repos={}))         # the item's repo was not read
        # A repo read is a scope whether or not an item of it is decided: a paused repo with nothing open pauses the
        # pass, and so does one that cannot be read (Argon's read of the merged pass).
        for repos, want in (({REPO: "true"}, True), ({REPO: "maybe"}, None), ({REPO: None, OTHER_REPO: "true"}, True)):
            out = passed(reads(pulls=[], pause={"org": None, "repos": repos}))
            self.assertIs(out["record"]["context"]["paused"], want, repos)
        elsewhere = {"facts": support.facts(item=dict(support.ITEM, repo=OTHER_REPO, number=1)), "title": "x"}
        held = passed(reads(pulls=[elsewhere], pause={"org": None, "repos": {REPO: "true", OTHER_REPO: None}}))
        self.assertEqual((held["dispatch"], decisions(held)[0]["reason"]), ([], "paused"))
        self.assertIsNone(passed(reads(pause={"repos": {REPO: None}}))["record"]["context"]["paused"])
        self.assertIsNone(passed(reads(pause={}))["record"]["context"]["paused"])

    def test_the_count_of_active_runs_and_the_unidentified_are_read_from_the_records(self):  # decision 0036
        out = passed(reads(runs=[run("r_00000A", number=7, status="in_progress"),
                                 run("r_00000B", number=8, status="queued"), run("r_00000C")],
                           unidentified=["39086879694"]))
        context = out["record"]["context"]
        self.assertEqual((context["active_runs"], context["unidentified_runs"]), (2, [unnamed("39086879694")]))
        self.assertEqual(decisions(out)[0]["reason"], "run_unidentified")
        # Past the window a completed one defers nothing, and is one alert in the view, by its run id; past
        # max_unnamed_runs of them every Run defers, the scope raises runs_unnamed, and no successor starts (issue 270).
        old = [unnamed(str(i), created="2026-10-11T12:00:00Z", status="completed") for i in (1, 2)]
        one = passed(reads(runs=[], unidentified=old[:1]))
        self.assertEqual((decisions(one)[0]["outcome"], one["view"]["meta"]["alerts"], one["alerts"]),
                         ("admit", [{"alert": "run_unnamed", "run": "1"}], []))
        two = passed(reads(runs=[], unidentified=old))
        self.assertEqual((decisions(two)[0]["reason"], two["alerts"], len(two["view"]["meta"]["alerts"])),
                         ("runs_unnamed", ["runs_unnamed"], 2))
        # The bound holds the whole scope, so it is raised with no item to defer as well.
        self.assertEqual(passed(reads(pulls=[], runs=[], unidentified=old))["alerts"], ["runs_unnamed"])
        self.assertEqual(passed()["view"]["meta"]["alerts"], [])
        # An enqueue goes ahead past the bound, as it does beside a Run inside the window, and starts no successor.
        bound = passed(reads(pulls=[pr(reviews=[support.review()])], runs=[run()], unidentified=old))
        self.assertEqual(([d.get("action") for d in bound["acts"]], bound["successor"]), (["enqueue"], False))

    def test_a_list_of_runs_read_short_or_not_at_all_admits_nothing(self):  # L-53
        short = passed(reads(complete=False))
        self.assertEqual((short["record"]["context"]["active_runs"], decisions(short)[0]["outcome"]), (None, "defer"))
        self.assertIs(short["record"]["pull_requests"][0]["facts"]["complete"]["runs"], False)
        gone = passed(reads(records_=False))
        context = gone["record"]["context"]
        self.assertEqual((context["active_runs"], context["unidentified_runs"], gone["record"]["runs"]), (None, None, []))
        self.assertEqual(decisions(gone)[0]["outcome"], "defer")
        self.assertEqual([r["read"] for r in gone["record"]["reads"]], ["facts"])
        unread = reads()
        unread["pull_requests"][0]["facts"]["complete"]["runs"] = False
        self.assertEqual(decisions(passed(unread))[0]["outcome"], "defer")
        # A list that holds what is not a run record, an id that is not GitHub's or a read with no date is not a list,
        # nor is one with no read of the list itself: an outcome read alone is not one (#285).
        for change in ({"runs": [{}]}, {"runs": [dict(run(), status="done")]}, {"unidentified": ["39086879694"]},
                       {"unidentified": [unnamed("abc")]}, {"unidentified": [unnamed("")]},
                       {"unidentified": [dict(unnamed("7"), status="done")]},
                       {"unidentified": [dict(unnamed("7"), created_at="soon")]},
                       {"unidentified": [dict(unnamed("7"), more=1)]}, {"unidentified": [39086879694]},
                       {"unidentified": [dict(unnamed("7"), run=["7"])]}, {"unidentified": [dict(unnamed("7"), run=7)]},
                       {"reads": [{"read": "runs", "date": "yesterday", "age": 0}]},
                       {"reads": [{"read": "runs", "date": NOW, "age": -1}]}, {"reads": [{"read": "facts", "date": NOW, "age": 0}]},
                       {"reads": [{"read": "runs", "date": NOW, "age": True}]},
                       {"reads": [{"read": "runs", "date": NOW, "age": 0}, {"read": "facts", "date": NOW, "age": 0}]},
                       {"reads": [{"read": "outcome", "date": NOW, "age": 0}]}, {"reads": []}):
            odd = reads()
            odd["records"].update(change)
            out = passed(odd)
            self.assertEqual((out["record"]["runs"], out["record"]["context"]["unidentified_runs"]), ([], None), change)
            self.assertEqual(decisions(out)[0]["outcome"], "defer", change)

    def test_a_capacity_fault_defers_model_runs_for_its_window(self):  # section 3.10
        fault = run("r_00000F", number=9, conclusion="failure", outcome="capacity", at="2026-10-11T10:00:00Z")
        out = passed(reads(runs=[fault]))
        self.assertEqual(out["record"]["context"]["model_deferred_until"], "2026-10-11T15:00:00Z")
        self.assertEqual((decisions(out)[0]["reason"], out["alerts"]), ("capacity", ["capacity"]))
        self.assertEqual(out["view"]["health"]["faults"], [{"run": "r_00000F", "item": dict(support.ITEM, number=9),
                                                            "outcome": "capacity", "at": "2026-10-11T10:00:00Z"}])
        older = dict(fault, run="r_00000E", started_at="2026-10-11T08:30:00Z")
        newest = passed(reads(runs=[fault, older]))["record"]["context"]["model_deferred_until"]
        self.assertEqual(newest, "2026-10-11T15:00:00Z")
        later = passed(reads(runs=[fault]), now="2026-10-11T15:00:00Z")
        self.assertIsNone(later["record"]["context"]["model_deferred_until"])
        self.assertEqual(len(later["view"]["health"]["faults"]), 1)
        self.assertEqual(passed(reads(runs=[fault]), now="2026-10-11T15:00:01Z")["view"]["health"]["faults"], [])
        # A fault said to start after the pass defers nothing (Argon's read of the merged pass).
        ahead = passed(reads(runs=[dict(fault, started_at="2026-10-11T13:00:01Z")]))
        self.assertEqual((ahead["record"]["context"]["model_deferred_until"], ahead["alerts"]), (None, []))
        other = passed(reads(runs=[dict(fault, outcome="item")]))
        self.assertIsNone(other["record"]["context"]["model_deferred_until"])

    def test_an_automatic_pause_needs_agreeing_faults_from_runs_on_different_items_in_a_recent_window(self):  # L-59
        def faults(*numbers, outcome="environment", at="2026-10-11T12:30:00Z"):
            return [run("r_0000%02d" % i, number=n, conclusion="failure", outcome=outcome, at=at)
                    for i, n in enumerate(numbers)]

        def held(runs) -> bool:
            return "environment" in passed(reads(runs=runs))["alerts"]
        out = passed(reads(runs=faults(7, 8, 7)))
        context = out["record"]["context"]
        self.assertEqual((context["paused"], context["model_deferred_until"]), (False, "2026-10-11T13:30:00Z"))
        self.assertEqual(decisions(out)[0]["outcome"], "defer")
        self.assertEqual(out["view"]["health"]["pause"], {"state": "paused", "by": ["environment"]})
        self.assertEqual(out["alerts"], ["environment"])            # one cause, though it defers as capacity does
        for runs in (faults(7, 7, 7), faults(7, 8), faults(7, 8, 9, outcome="capacity"),
                     faults(7, 8, 9, at="2026-10-11T11:59:59Z"), faults(7, 8, 9, at="2026-10-11T13:00:01Z"),
                     faults(7, 8, 9) + [run("r_SUCCES", number=9, at="2026-10-11T12:31:00Z")],
                     [run("r_SUCCES", number=9, at="2026-10-11T12:31:00Z")] + faults(7, 8, 9),
                     faults(7, 8, 9, outcome="item")):
            self.assertFalse(held(runs), runs)
        # A success before the streak ends nothing. A streak an hour old has ended, as its hold has; a second younger
        # still holds.
        streak = [run("r_SUCCES", number=9, at="2026-10-11T12:00:00Z")] + faults(7, 8, 9, at="2026-10-11T12:00:01Z")
        self.assertTrue(held(streak))
        self.assertFalse(held(faults(7, 8, 9, at="2026-10-11T12:00:00Z")))
        # It stops no act: a dequeue goes ahead, so that only a person's Pause keeps a merge from being stopped.
        queued = pr(42, queue=True, reviews=[support.review()], author="donpetry-bot")
        out = passed(reads(pulls=[queued], runs=[run()] + faults(7, 8, 9)))
        self.assertEqual([d.get("action") for d in out["acts"]], ["dequeue"])
        both = passed(reads(runs=faults(7, 8, 9), pause={"org": "maybe", "repos": {REPO: None}}))
        self.assertEqual(both["view"]["health"]["pause"], {"state": "paused", "by": ["org", "environment"]})
        self.assertEqual(both["alerts"], ["environment", "pause_unreadable"])
        both = passed(reads(runs=faults(7, 8, 9) + [run("r_00000F", number=9, conclusion="failure", outcome="capacity")]))
        self.assertEqual(both["alerts"], ["capacity", "environment"])


class Chain(unittest.TestCase):
    def test_passes_since_restarts_only_after_a_gap_of_the_second_reading(self):  # decision 0043
        def since(*records, previous=True):
            return passed(previous=list(records) if previous else None)["record"]["context"]["passes_since"]
        self.assertEqual(since(earlier("2026-10-11T07:00:00Z", "2026-10-10T00:00:00Z")), "2026-10-10T00:00:00Z")
        self.assertEqual(since(earlier("2026-10-11T06:59:59Z", "2026-10-10T00:00:00Z")), NOW)
        self.assertEqual(since(), NOW)
        self.assertIsNone(since(previous=False))
        # A gap further back: the chain begins with the pass after it.
        chain = [earlier("2026-10-10T20:00:00Z", "2026-10-10T00:00:00Z"), earlier("2026-10-11T02:00:01Z"),
                 earlier("2026-10-11T08:00:00Z")]
        self.assertEqual(since(*chain), "2026-10-11T02:00:01Z")
        self.assertEqual(since(*reversed(chain)), "2026-10-11T02:00:01Z")
        unread = earlier("2026-10-11T08:00:00Z")
        unread["context"]["passes_since"] = None
        self.assertIsNone(since(unread))
        self.assertIsNone(since(earlier("2026-10-11T14:00:00Z")))
        self.assertIsNone(since(earlier("2026-10-11T12:00:00Z"), earlier("2026-10-11T14:00:00Z")))
        self.assertIsNone(since(earlier("2026-10-11T12:00:00Z"), earlier(NOW)))
        # A record that is not a pass record makes the records unreadable.
        broken = earlier("2026-10-11T08:00:00Z")
        del broken["context"]
        self.assertIsNone(since(broken))

    def test_the_first_pass_after_six_hours_with_none_raises_the_not_run_alert_and_the_next_clears_it(self):  # 0043
        before = earlier("2026-10-11T06:59:59Z")
        first = passed(previous=[before])
        self.assertEqual((first["alerts"], first["cleared"]), (["not_run"], []))
        self.assertEqual(first["view"]["health"]["previous_pass_at"], "2026-10-11T06:59:59Z")
        after = dict(copy.deepcopy(first["record"]), now=NOW)
        nxt = passed(previous=[before, after], now="2026-10-11T13:03:00Z")
        self.assertEqual((nxt["alerts"], nxt["cleared"]), ([], ["not_run"]))
        self.assertEqual(passed(previous=[after, before], now="2026-10-11T13:03:00Z")["cleared"], ["not_run"])
        again = passed(previous=[before, after], now="2026-10-11T19:00:01Z")
        self.assertEqual((again["alerts"], again["cleared"]), (["not_run"], []))
        for previous in ([earlier("2026-10-11T07:00:00Z")], []):
            out = passed(previous=previous)
            self.assertEqual((out["alerts"], out["cleared"]), ([], []))
        far = [earlier("2026-10-10T00:00:00Z"), earlier("2026-10-11T12:00:00Z"), earlier("2026-10-11T12:57:00Z")]
        self.assertEqual(passed(previous=far)["cleared"], [])

    def test_a_pass_reads_no_sooner_than_three_minutes_after_the_last_pass_began_to_read(self):  # decision 0043
        cfg = config()
        last = earlier("2026-10-11T12:59:30Z", read_at=["2026-10-11T12:59:10Z", "2026-10-11T12:59:00Z"])
        self.assertEqual(pass_.wait_before_reading([last], NOW, cfg), 120)
        self.assertEqual(pass_.wait_before_reading([earlier("2026-10-11T12:00:00Z"), last], NOW, cfg), 120)
        self.assertEqual(pass_.wait_before_reading([last, earlier("2026-10-11T12:00:00Z")], NOW, cfg), 120)
        self.assertEqual(pass_.wait_before_reading([last], "2026-10-11T13:02:00Z", cfg), 0)
        self.assertEqual(pass_.wait_before_reading([last], "2026-10-11T13:01:59Z", cfg), 1)
        self.assertEqual(pass_.wait_before_reading([last], "2026-10-11T13:10:00Z", cfg), 0)
        self.assertEqual(pass_.wait_before_reading(None, NOW, cfg), 180)
        self.assertEqual(pass_.wait_before_reading([], NOW, cfg), 0)
        unread = copy.deepcopy(last)
        unread["now"] = "2026-02-30T12:00:00Z"
        self.assertEqual(pass_.wait_before_reading([unread], NOW, cfg), 180)
        broken = copy.deepcopy(last)
        del broken["runs"]
        self.assertEqual(pass_.wait_before_reading([broken], NOW, cfg), 180)
        # A record that cannot be placed before this pass makes the records unreadable, even beside one that can
        # (Argon's read of the merged pass).
        for odd in (unread, earlier(NOW), earlier("2026-10-11T13:00:01Z")):
            self.assertEqual(pass_.wait_before_reading([earlier("2026-10-11T12:00:00Z"), odd], NOW, cfg), 180, odd["now"])
        # A record with no read waits from its time.
        quiet = dict(copy.deepcopy(last), reads=[])
        self.assertEqual(pass_.wait_before_reading([quiet], NOW, cfg), 150)
        self.assertEqual((CONTROLLER["read_gap_seconds"], CONTROLLER["not_run_seconds"]), (180, 6 * 3600))

    def test_a_successor_starts_only_for_an_item_due_at_the_end(self):  # decisions 0036, 0043
        enqueued = reads(pulls=[pr(reviews=[support.review()])], runs=[run()])
        self.assertEqual([d.get("action") for d in passed(enqueued)["acts"]], ["enqueue"])
        self.assertIs(passed(enqueued)["successor"], True)
        self.assertIs(passed(reads(pulls=[], issues=[an_issue()]))["successor"], True)
        self.assertIs(passed(reads())["successor"], False)                       # an admission ends in a Run's end
        self.assertIs(passed(reads(runs=[run()]))["successor"], False)           # so does an approval
        self.assertIs(passed(reads(pulls=[]))["successor"], False)
        blind = reads(pulls=[pr(reviews=[support.review()])], runs=[run()], unidentified=["39086879694"])
        self.assertEqual([d.get("action") for d in passed(blind)["acts"]], ["enqueue"])
        self.assertIs(passed(blind)["successor"], False)
        unread = reads(pulls=[pr(reviews=[support.review()])], runs=[run()])
        unread["records"]["unidentified"] = "39086879694"
        self.assertIs(passed(unread)["successor"], False)
        # An act the pass before made too did not take: it is not due again at once, so the chain ends.
        last = earlier("2026-10-11T12:57:00Z", pulls=[pr(reviews=[support.review()])], runs=[run()])
        self.assertIs(passed(enqueued, previous=[last])["successor"], False)
        moved = reads(pulls=[pr(reviews=[support.review(content="sha256:bbbb")], content_id="sha256:bbbb")],
                      runs=[run(content="sha256:bbbb")])
        self.assertIs(passed(moved, previous=[last])["successor"], True)
        self.assertIs(passed(enqueued, previous=[earlier("2026-10-11T12:57:00Z"), earlier("2026-10-11T12:50:00Z",
                      pulls=[pr(reviews=[support.review()])], runs=[run()])])["successor"], True)

    def test_started_by_is_read_from_the_run_and_an_account_by_its_type_and_id(self):  # decision 0043
        def start(event, actor=None, attempt=1, cfg=None):
            return passed(reads(event=event, actor=actor, attempt=attempt), cfg=cfg)["record"]["started_by"]
        self.assertEqual(start("schedule", RELAY), "schedule")
        self.assertEqual(start("workflow_run", TOKEN), "own_repo")
        self.assertEqual(start("workflow_dispatch", TOKEN), "successor")
        self.assertEqual(start("workflow_dispatch", {"id": 36422719, "type": "User"}), "dispatch")
        self.assertEqual(start("workflow_dispatch", dict(TOKEN, type="User")), "dispatch")
        self.assertEqual(start("workflow_dispatch", dict(TOKEN, id=1)), "dispatch")
        self.assertEqual(start("workflow_dispatch", None), "dispatch")
        self.assertEqual(start("watch", RELAY), "relay")
        self.assertEqual(start("watch", TOKEN), "public")
        self.assertEqual(start("watch", None), "public")
        for attempt in (2, 0, True, None, "1"):
            self.assertEqual(start("schedule", attempt=attempt), "dispatch", attempt)
        # An account the configuration holds as null is no one's: until a trial records it, none is named.
        held = config(accounts=dict(CONTROLLER["accounts"], workflow_token=None, relay=None))
        self.assertEqual(start("watch", RELAY, cfg=held), "public")
        self.assertEqual(start("workflow_dispatch", TOKEN, cfg=held), "dispatch")
        self.assertEqual({k: CONTROLLER["accounts"][k] for k in ("workflow_token", "relay", "controller", "maintainer")},
                         {"workflow_token": {"id": 41898282, "type": "Bot"}, "relay": None, "controller": None,
                          "maintainer": {"login": "don-petry", "id": 36422719}})
        self.assertEqual(passed(dict(reads(), started=None))["record"]["started_by"], "dispatch")


class Feed(unittest.TestCase):
    def test_one_cause_raises_one_alert(self):  # L-48, section 4.6
        paused = passed(reads(pulls=[pr(1), pr(2), pr(3)], pause={"org": "true", "repos": {REPO: None}}))
        self.assertEqual([d["reason"] for d in decisions(paused)], ["paused"] * 3)
        self.assertEqual((paused["alerts"], paused["view"]["health"]["alerts"]), (["paused"], ["paused"]))
        blind = passed(reads(pulls=[pr(1), pr(2)], unidentified=["1", "2"]))
        self.assertEqual(blind["alerts"], ["run_unidentified"])
        quiet = passed(reads(pulls=[], pause={"org": "maybe", "repos": {}}))
        self.assertEqual(quiet["alerts"], ["pause_unreadable"])
        self.assertEqual(quiet["view"]["health"]["pause"], {"state": "unreadable", "by": ["org"]})
        self.assertEqual(passed()["alerts"], [])
        # A cause that holds the whole scope is raised with no item to defer (Codex's read).
        fault = run("r_00000F", number=9, conclusion="failure", outcome="capacity", at="2026-10-11T12:00:00Z")
        for read, raised in ((reads(pulls=[], pause={"org": "true", "repos": {}}), ["paused"]),
                             (reads(pulls=[], pause={"org": "maybe", "repos": {}}), ["pause_unreadable"]),
                             (reads(pulls=[], runs=[fault]), ["capacity"]),
                             (reads(pulls=[], unidentified=["1"]), ["run_unidentified"]),
                             (reads(pulls=[], complete=False), ["capacity_unreadable", "reconciliation_unreadable"]),
                             (reads(pulls=[], records_=False), ["capacity_unreadable", "reconciliation_unreadable",
                                                                 "run_unidentified"])):
            self.assertEqual(passed(read)["alerts"], raised, raised)

    def test_a_write_no_effect_recorded_raises_one_alert_and_is_named_in_the_view(self):  # I-33, decision 0061
        # The pass reconciles what each Factory identity wrote with what the Factory recorded: one alert however many
        # writes, each named in the view by ids and codes, kept in the pass record so a rebuilt view says the same.
        approvals = [{"by": "approver", "kind": "approval", "item": support.ITEM, "key": "PRR_%d" % i,
                      "at": "2026-10-11T12:30:00Z"} for i in range(3)]
        out = passed(reads(seen=dict(SEEN, writes=approvals)))
        self.assertEqual((out["alerts"], out["record"]["alerts"], out["view"]["health"]["alerts"]),
                         (["write_unmatched"], ["write_unmatched"], ["write_unmatched"]))
        named = out["view"]["meta"]["reconciliation"]
        self.assertEqual([(a["alert"], a["key"]) for a in named], [("write_unmatched", "PRR_%d" % i) for i in range(3)])
        self.assertEqual((out["record"]["reconciliation"], out["view"]["meta"]["alerts"]), (named, []))
        rebuilt = pass_.rebuild([out["record"]], {}, config())
        self.assertEqual(rebuilt[0]["meta"]["reconciliation"], named)
        # Two writes GitHub gives no key for, a label added and taken off, are named once, and the pass is not refused.
        labels = [{"by": "controller", "kind": "label", "item": support.ITEM, "key": None, "at": at}
                  for at in ("2026-10-12T00:10:00Z", "2026-10-12T00:20:00Z")]
        out = passed(reads(seen=dict(SEEN, writes=labels)))
        self.assertEqual((out["alerts"], len(out["record"]["reconciliation"])), (["write_unmatched"], 1))
        # What reconciliation found is held to pass/1 with the record, before anything is dispatched: an entry the
        # record cannot hold refuses the pass whole (CodeRabbit's read).
        odd = [dict(labels[0], item=dict(support.ITEM, repo="combsmith/software factory"))]
        with self.assertRaises(pass_.Refused):
            passed(reads(seen=dict(SEEN, writes=odd)))
        # Matched, nothing is raised; what was seen or recorded that cannot be read raises the one alert that says so.
        done = {"schema": "applied/1", "run": "r_01JA7Q", "release": "factory/v0.3.1", "findings": [], "rulings": [],
                "effects": [{"id": "e1", "type": "approve", "state": "applied", "key": "PRR_0", "reason": None}]}
        self.assertEqual(passed(reads(seen=dict(SEEN, writes=approvals[:1]),
                                      effects=dict(RECORDED, applied=[done])))["alerts"], [])
        for read in (reads(seen=None), reads(effects=None), reads(seen=dict(SEEN, whole=False))):
            self.assertEqual(passed(read)["alerts"], ["reconciliation_unreadable"])
        # Until every Factory identity's account is known, reconciliation cannot tell their writes: it is short.
        unknown = config(accounts=dict(config()["controller"]["accounts"], controller=None))
        self.assertEqual(passed(cfg=unknown)["alerts"], ["reconciliation_unreadable"])

    def test_next_actor_and_the_decision_required_are_read_from_the_feed_table_alone(self):  # decision 0039
        held = pr(1, acts_since_writer=support.CONFIG["limits"]["max_acts_per_item"], reviews=[support.review()])
        asked = pr(5, threads=[support.thread(tid="PRRT_1", kind="human", name="a-colleague", severity=None)])
        out = passed(reads(pulls=[pr(2), held, pr(3, state="closed"), asked],
                           runs=[run(number=1), run("r_00000B", number=5, at="2026-10-11T12:05:00Z")]))
        items = out["view"]["items"]
        self.assertEqual((items["pass"], out["view"]["meta"]["pass"]), (out["record"]["pass"],) * 2)
        self.assertEqual([i["item"]["number"] for i in items["items"]], [2, 1, 5])
        self.assertEqual([(i["next_actor"], i["reason"]) for i in items["items"]],
                         [("factory", "awaiting_review"), ("maintainer", "act_ceiling"), ("factory", "human_finding")])
        self.assertEqual(items["items"][1]["decision_required"],
                         {"question": "allowance_spent", "choices": ["renew_allowance", "close"], "evidence": []})
        self.assertEqual(items["items"][2]["decision_required"],
                         {"question": "a_person_is_asked", "choices": ["resolve_thread", "close"], "evidence": ["PRRT_1"]})
        self.assertIsNone(items["items"][0]["decision_required"])
        self.assertEqual(items["items"][0]["untrusted"], {"title": "A title"})
        self.assertEqual(items["items"][1]["url"], "https://github.com/%s/pull/1" % REPO)
        self.assertEqual((items["items"][1]["runs"], items["items"][1]["sources"]), (1, ["r_01JA6Z"]))
        self.assertEqual(out["view"]["meta"]["reaches_back_to"], "2026-10-11T12:05:00Z")
        # Attempts are counted as the brakes count them: completed Runs that failed by a fault of the item, or ran and
        # left no outcome (decision 0049), since a person with write access last acted (Codex's read). Every Run is
        # among `runs`.
        tried = [run("r_00000A", number=6, intent="fix-findings", role="dev-lead", conclusion="failure", outcome="item"),
                 run("r_00000B", number=6, intent="fix-findings", role="dev-lead", conclusion="failure",
                     outcome="environment"),
                 run("r_00000C", number=6, intent="fix-findings", role="dev-lead", conclusion="failure", outcome="item",
                     at="2026-10-11T11:00:00Z"),
                 run("r_00000D", number=6, at="2026-10-11T12:20:00Z"),
                 run("r_00000E", number=6, intent="fix-findings", role="dev-lead", status="in_progress"),
                 run("r_00000F", number=6, intent="fix-findings", role="dev-lead", conclusion="timed_out", outcome=None),
                 run("r_00000G", number=6, intent="fix-findings", role="dev-lead", conclusion="cancelled", outcome=None)]
        sixth = passed(reads(pulls=[pr(6)], runs=tried))["view"]["items"]["items"][0]
        self.assertEqual((sixth["attempts"], sixth["runs"]),
                         ([{"intent": "fix-findings", "count": 2}, {"intent": "review-change", "count": 0}], 7))
        # The table, changed, changes the feed: nothing else says who acts next or what is asked.
        cfg = config()
        cfg["feed"]["next_actor"]["by_outcome"][0]["actor"] = "lens"
        cfg["feed"]["next_actor"]["by_attention"][0]["actor"] = "author"
        cfg["feed"]["decision_required"] = [dict(row, question="something_else") if row["reason"] == "act_ceiling"
                                            else row for row in cfg["feed"]["decision_required"]]
        changed = passed(reads(pulls=[pr(2), held], runs=[run(number=1)]), cfg=cfg)["view"]["items"]["items"]
        self.assertEqual([i["next_actor"] for i in changed], ["lens", "author"])
        self.assertEqual(changed[1]["decision_required"]["question"], "something_else")
        paused = passed(reads(pause={"org": "true", "repos": {REPO: None}}))["view"]["items"]["items"][0]
        self.assertEqual((paused["reason"], paused["attention"], paused["decision_required"]), ("paused", "review", None))
        self.assertEqual(paused["next_actor"], "lens")          # by its State, as the table says for a review
        working = passed(reads(runs=[run(status="in_progress")]))["view"]["items"]["items"][0]
        self.assertEqual((working["attention"], working["next_actor"]), ("working", "factory"))

    def test_a_view_rebuilt_from_the_records_equals_the_view_written_pass_by_pass(self):  # decision 0002
        cfg, mint, written, kept = config(), Mint(), [], []
        steps = [("2026-10-11T13:00:00Z", reads(pulls=[pr(1), pr(2)])),
                 ("2026-10-11T13:05:00Z", reads(pulls=[pr(1), pr(2)], runs=[run(number=1, status="in_progress")])),
                 ("2026-10-11T13:10:00Z", reads(pulls=[pr(1)], runs=[run(number=1, status="in_progress")])),
                 ("2026-10-11T13:15:00Z", reads(pulls=[pr(1), pr(2)], runs=[run(number=1)])),
                 ("2026-10-11T13:20:00Z", reads(pulls=[pr(1), pr(2, state="closed")], runs=[run(number=1)])),
                 # A run unnamed past the window is an alert of that pass, and of the rebuild (issue 270).
                 ("2026-10-11T13:25:00Z", reads(pulls=[pr(1)], runs=[run(number=1)],
                                                unidentified=[unnamed("9", created="2026-10-11T13:00:00Z",
                                                                      status="completed")]))]
        for now, read in steps:
            out = pass_.run(read, cfg, now, list(kept), mint)
            kept.append(out["record"])
            written.append({"meta": out["view"]["meta"], "items": out["view"]["items"]})
        titles = {"https://github.com/%s/pull/%d" % (REPO, n): "A title" for n in (1, 2)}
        self.assertEqual(pass_.rebuild(list(reversed(kept)), titles, cfg), written)
        self.assertEqual([w["meta"]["alerts"] for w in written][-2:], [[], [{"alert": "run_unnamed", "run": "9"}]])

        def ages(n):
            return [[i["age_hours"] for i in w["items"]["items"] if i["item"]["number"] == n] for w in written]
        self.assertEqual(ages(1), [[0.0], [0.08], [0.17], [0.0], [0.08], [0.17]])
        # Read in a pass, missed by the next and read again: its time in its State starts again.
        self.assertEqual(ages(2), [[0.0], [0.08], [], [0.0], [], []])

    def test_the_three_thresholds_of_decision_0011_are_computed_and_shown(self):  # decision 0011
        thresholds = passed()["view"]["health"]["thresholds"]
        self.assertEqual(thresholds, {"job_minutes_share": {"value": None, "limit": 0.1, "met": None},
                                      "graphql_points_per_hour": {"value": None, "limit": 3000, "met": None},
                                      "decision_delay_p95_minutes": {"value": None, "limit": 15, "met": None}})
        usage = {"factory_job_minutes": 300, "org_job_minutes": 6000, "graphql_points_peak_hour": 3001}
        shown = passed(reads(usage=usage))["view"]["health"]["thresholds"]
        self.assertEqual(shown["job_minutes_share"], {"value": 0.05, "limit": 0.1, "met": True})
        self.assertEqual(shown["graphql_points_per_hour"], {"value": 3001, "limit": 3000, "met": False})
        level = passed(reads(usage={"graphql_points_peak_hour": 3000}))["view"]["health"]["thresholds"]
        self.assertEqual(level["graphql_points_per_hour"]["met"], True)
        # A share just over its limit is shown rounded, and is not met (Muse's read).
        over = passed(reads(usage={"factory_job_minutes": 10004, "org_job_minutes": 100000}))["view"]["health"]
        self.assertEqual(over["thresholds"]["job_minutes_share"], {"value": 0.1, "limit": 0.1, "met": False})
        for bad in ({"factory_job_minutes": 1, "org_job_minutes": 0}, {"factory_job_minutes": True, "org_job_minutes": 2},
                    {"factory_job_minutes": -1, "org_job_minutes": 2},
                    {"graphql_points_peak_hour": -1}, {"graphql_points_peak_hour": float("nan")}):
            shown = passed(reads(usage=bad))["view"]["health"]["thresholds"]
            self.assertEqual({k: v["value"] for k, v in shown.items()},
                             {"job_minutes_share": None, "graphql_points_per_hour": None,
                              "decision_delay_p95_minutes": None}, bad)
        # A push after the pass before is read at the next pass: the delay is from the push to that pass. Twenty
        # delays, of 2 to 19 minutes and two just under 20: the 95th percentile is the 19th, not the largest.
        before = earlier("2026-10-11T12:40:00Z", pulls=[pr(1, last_push_at="2026-10-11T12:00:00Z")])
        quick = [pr(n, last_push_at="2026-10-11T12:%02d:00Z" % (59 - n)) for n in range(1, 19)]
        slow = [pr(19, last_push_at="2026-10-11T12:40:02Z"), pr(20, last_push_at="2026-10-11T12:40:01Z")]
        shown = passed(reads(pulls=quick + slow), previous=[before])["view"]["health"]["thresholds"]
        self.assertEqual(shown["decision_delay_p95_minutes"], {"value": 19.97, "limit": 15, "met": False})
        old = passed(reads(pulls=[pr(1, last_push_at="2026-10-11T12:40:00Z")]), previous=[before])
        self.assertIsNone(old["view"]["health"]["thresholds"]["decision_delay_p95_minutes"]["value"])
        now = passed(reads(pulls=[pr(1, last_push_at=NOW)]), previous=[before])
        self.assertEqual(now["view"]["health"]["thresholds"]["decision_delay_p95_minutes"]["value"], 0.0)
        # A change a pass in between missed is read late by the first pass that read it (Codex's read).
        missed = earlier("2026-10-11T12:50:00Z")
        late = passed(reads(pulls=[pr(1, last_push_at="2026-10-11T12:45:00Z")]), previous=[before, missed])
        self.assertEqual(late["view"]["health"]["thresholds"]["decision_delay_p95_minutes"]["value"], 15.0)
        again = dict(copy.deepcopy(late["record"]), now="2026-10-11T12:55:00Z")
        once = passed(reads(pulls=[pr(1, last_push_at="2026-10-11T12:45:00Z")]), previous=[before, missed, again])
        self.assertEqual(once["view"]["health"]["thresholds"]["decision_delay_p95_minutes"]["value"], 10.0)
        # A change dated after the pass that read it is read late by the first pass after it (Argon's read).
        early = earlier("2026-10-11T12:50:00Z", pulls=[pr(1, last_push_at="2026-10-11T12:50:01Z")])
        later = passed(reads(pulls=[pr(1, last_push_at="2026-10-11T12:50:01Z")]), previous=[before, early])
        self.assertEqual(later["view"]["health"]["thresholds"]["decision_delay_p95_minutes"]["value"], 9.98)
        changed = an_issue(7, content_changed_at="2026-10-11T12:50:00Z")
        issue = passed(reads(pulls=[], issues=[changed]), previous=[before])
        self.assertEqual(issue["view"]["health"]["thresholds"]["decision_delay_p95_minutes"]["value"], 10.0)
        # Only the window's passes count: a change read two weeks and more ago is not.
        stale = earlier("2026-09-27T12:59:59Z", pulls=[pr(1)])
        late = dict(copy.deepcopy(before), now="2026-09-27T13:30:00Z")
        late["pull_requests"] = [{"facts": pr(1, last_push_at="2026-09-27T13:10:00Z")["facts"],
                                  "decision": before["pull_requests"][0]["decision"], "run": None}]
        far = passed(reads(pulls=[]), previous=[stale, late])["view"]["health"]
        self.assertEqual(far["thresholds"]["decision_delay_p95_minutes"]["value"], None)
        self.assertEqual(far["starts"]["schedule"], 2)

    def test_health_carries_the_last_pass_the_chain_and_what_started_the_passes(self):  # decision 0043
        chain = [earlier("2026-10-11T12:50:00Z", started_by="successor"),
                 earlier("2026-10-11T12:54:00Z", started_by="schedule"),
                 earlier("2026-10-11T12:57:00Z", started_by="successor")]
        health = passed(reads(event="workflow_dispatch", actor=TOKEN), previous=chain)["view"]["health"]
        self.assertEqual((health["last_pass_at"], health["previous_pass_at"], health["relay_started_at"]),
                         (NOW, "2026-10-11T12:57:00Z", None))
        self.assertEqual(health["chain"], {"since": "2026-10-11T12:50:00Z", "started_by": "successor", "successors": 2})
        self.assertEqual(health["starts"], {"schedule": 1, "relay": 0, "public": 0, "own_repo": 0, "successor": 3,
                                            "dispatch": 0})
        self.assertEqual(passed(previous=chain)["view"]["health"]["chain"]["successors"], 0)
        future = run("r_00000F", number=9, conclusion="failure", outcome="environment", at="2026-10-11T13:00:01Z")
        self.assertEqual(passed(reads(runs=[future]))["view"]["health"]["faults"], [])


class Ports(unittest.TestCase):
    def test_the_pass_record_keeps_its_alerts_for_the_tracking_issue(self):  # issue 193
        out = passed(reads(pulls=[pr(7)], records_=False))
        self.assertEqual(out["record"]["alerts"], sorted(out["alerts"]))
        self.assertTrue(out["record"]["alerts"])

    def test_the_pass_reads_what_the_records_port_gives(self):  # issue 192
        got = records.runs(github.Replay([listing("P-17", 3, rows={"name": NAME})]), canary(), "main", [WORKFLOW],
                           DISPATCHER, per_page=10, sleep=lambda s: None)
        out = passed(dict(reads(pulls=[pr(264)]), records=got))
        self.assertEqual(out["record"]["runs"], got["runs"])
        self.assertEqual(out["record"]["reads"][:-1], got["reads"])
        # A failed Run's outcome the port read is a read the pass keeps, stamped as one (#285), not a list it refuses.
        rows = listing("P-17", 3, rows={"name": NAME, "status": "completed", "conclusion": "failure"})
        github_id = rows["response"]["body"]["workflow_runs"][0]["id"]
        got = records.runs(github.Replay([rows] + stored(canary(), github_id, outcome_zip(outcome_of("r_01JA6Z", "item")))),
                           canary(), "main", [WORKFLOW], DISPATCHER, per_page=10, sleep=lambda s: None)
        out = passed(dict(reads(pulls=[pr(264)]), records=got))
        self.assertEqual(([r["outcome"] for r in out["record"]["runs"]], [r["read"] for r in out["record"]["reads"]]),
                         (["item"], ["runs", "outcome", "facts"]))


class Hub:
    """GitHub as the entry meets it: each request answered by its method and path from the table given, any number of
    times, each recorded with the credential that sent it. A request the table does not hold is refused."""

    def __init__(self, table: dict):
        self.table, self.sent = dict(table), []

    def connect(self, credential: str):
        hub = self

        class Sent:
            def send(self, req):
                hub.sent.append((credential, req))
                key = (req["method"], req["path"])
                if key not in hub.table:
                    raise github.Unanswered("asked %s %s" % key)
                return copy.deepcopy(hub.table[key])
        return Sent()


class Entry(unittest.TestCase):
    HOME = CONTROLLER["home"]["repo"]
    RUN = "777"
    TOKEN = "ghs_entrytoken"
    CLOCK = 1_791_806_400     # 2026-10-12T12:00:00Z

    @classmethod
    def setUpClass(cls):
        cls.key = test_apply.throwaway_key().decode()

    def table(self, numbers=(), total=None, pause=404, minted=201, repo_pause=None):
        from tests.test_adapters import open_page, passes_listed
        config = entry.configuration(ROOT, "factory/v0.3.1")
        runs = copy.deepcopy(exchanges("P-17")[4]["response"])
        runs["body"] = {"total_count": 0, "workflow_runs": []}
        started = copy.deepcopy(exchanges("P-9")[10]["response"])
        started["body"].update(id=int(self.RUN), event="schedule", repository={"full_name": self.HOME})
        listed_runs = "/repos/%s/actions/workflows/%%s/runs?branch=main&event=workflow_dispatch&per_page=100" % self.HOME
        return {
            ("GET", "/repos/%s/installation" % self.HOME):
                {"status": 200, "headers": {}, "body": {"id": 172571064, "app_id": config["app"]["app_id"]}},
            ("POST", "/app/installations/172571064/access_tokens"):
                {"status": minted, "headers": {}, "body": {
                    "token": self.TOKEN, "permissions": dict(entry.wanted(config), metadata="read"),
                    "repository_selection": "selected", "repositories": [{"full_name": self.HOME}]}},
            ("GET", passes_listed([])["request"]["call"].split()[1]): passes_listed([])["response"],
            ("GET", listed_runs % "run.yml"): runs,
            ("GET", listed_runs % "approve.yml"): runs,
            ("POST", "/graphql"): open_page(list(numbers), total)["response"],
            ("GET", "/repos/%s/actions/runs/%s" % (self.HOME, self.RUN)): started,
            # The org's Pause, read from the home repo's list of the org's variables (issue 362): one GitHub holds as
            # none is a list read whole that does not name it.
            ("GET", "/repos/%s/actions/organization-variables?per_page=100" % self.HOME):
                {"status": 200, "headers": {}, "body": {"total_count": 0, "variables": []}} if pause == 404
                else {"status": pause, "headers": {}, "body": None},
            ("GET", "/repos/%s/actions/variables/FACTORY_PAUSED" % self.HOME):
                {"status": pause if repo_pause is None else repo_pause, "headers": {}, "body": None},
            ("GET", "/repos/%s/pulls/7" % self.HOME): {"status": 502, "headers": {}, "body": None},
            ("DELETE", "/installation/token"): {"status": 204, "headers": {}, "body": None},
        }

    def run_entry(self, hub, **environ):
        env = {"RELEASE": "factory/v0.3.1", "GITHUB_RUN_ID": self.RUN, entry.KEY: self.key}
        env.update(environ)
        slept, printed = [], io.StringIO()
        sleep = lambda seconds: slept.append((seconds, len(hub.sent)))
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(printed), support.releasing(env):
            code = entry.main(["out"] if os.makedirs(os.path.join(d, "out")) is None else [], {k: v for k, v in env.items()
                                                                                              if v is not None},
                              base=d, clock=lambda: self.CLOCK, sleep=sleep, connect=hub.connect)
            named = ["pass.json", "writes.json"] + ["view/%s.json" % v for v in entry.VIEW]
            files = {n: json.loads(pathlib.Path(d, "out", n).read_text()) for n in named
                     if pathlib.Path(d, "out", n).is_file()}
            self.modes = {n: pathlib.Path(d, "out", n).stat().st_mode & 0o777 for n in files}
        return code, printed.getvalue(), files, slept

    def test_the_entry_reads_through_the_ports_and_hands_the_pass_nothing_else(self):  # #193 ruling 10, #196 PR 2
        hub = Hub(self.table(numbers=[7]))
        code, printed, files, slept = self.run_entry(hub)
        self.assertEqual((code, printed), (0, "passed\n"))
        self.assertEqual(sorted(files), ["pass.json", "view/health.json", "view/items.json", "view/meta.json",
                                         "writes.json"])
        record = files["pass.json"]
        self.assertEqual(shared.errors(record, "pass"), [])
        self.assertEqual(shared.errors(files["writes.json"], "writes"), [])
        self.assertEqual((record["now"], record["release"], record["started_by"]),
                         ("2026-10-12T12:00:00Z", "factory/v0.3.1", "schedule"))
        # The pull request whose snapshot could not be read is left out, as one alert; no pass record before this one
        # is no wait.
        self.assertEqual((record["pull_requests"], record["issues"]), ([], []))
        self.assertIn("facts_unreadable", record["alerts"])
        self.assertEqual([s for s, _ in slept], [0])
        # The App's JWT asks for the token alone, with every read its grant allows and no write; every read after goes
        # through that token, and the last request revokes it.
        through = [(c == self.TOKEN, r["method"], r["path"]) for c, r in hub.sent]
        self.assertEqual([t for t, _, _ in through[:2]], [False, False])
        self.assertTrue(all(t for t, _, _ in through[2:]))
        self.assertEqual(through[-1], (True, "DELETE", "/installation/token"))
        asked = hub.sent[1][1]["body"]["permissions"]
        self.assertEqual(asked, {"actions": "read", "actions_variables": "read", "checks": "read", "contents": "read",
                                 "issues": "read", "metadata": "read", "pull_requests": "read"})
        self.assertEqual({m for _, m, p in through[2:] if m != "GET"}, {"POST", "DELETE"})
        self.assertEqual({p for _, m, p in through[2:] if m == "POST"}, {"/graphql"})
        # Each file it writes is its own user's alone to read.
        self.assertEqual(set(self.modes.values()), {0o600})
        # Nothing it prints is a key, a token or GitHub's.
        self.assertNotIn(self.TOKEN, printed)
        # A Pause that cannot be read is unreadable; one GitHub holds as none is no Pause.
        self.assertIs(record["context"]["paused"], False)
        for org, repo in ((403, 404), (404, 403)):
            _, _, files, _ = self.run_entry(Hub(self.table(pause=org, repo_pause=repo)))
            self.assertIsNone(files["pass.json"]["context"]["paused"], (org, repo))

    def test_each_snapshot_is_read_with_the_configured_accounts_and_kept(self):  # decisions 0005, 0060
        handed = []

        whos = []

        def snapshot(transport, repo, number, identities, who, runs_whole, clock, opener, *, recorded):
            handed.append((repo, number, identities, who.approver, who.lenses, who.factory, runs_whole, clock(), opener,
                           recorded))
            whos.append(who)
            return support.facts(item=dict(support.ITEM, number=number)), "A title"
        from tests.test_steps import recorded_spy
        asked = []
        with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), recorded_spy(entry, asked):
            code, _, files, _ = self.run_entry(Hub(self.table(numbers=[7])))
        # What each open pull request's model Lenses recorded is read once a pass, held to the authority table.
        authority = json.loads((ROOT / "config" / "authority.json").read_text())
        self.assertEqual(asked, [{"repo": self.HOME, "numbers": [7], "lenses": {"pr-review"}, "authority": authority}])
        self.assertEqual(code, 0)
        self.assertEqual([e["facts"]["item"]["number"] for e in files["pass.json"]["pull_requests"]], [7])
        self.assertEqual(files["view/items.json"]["items"][0]["untrusted"]["title"], "A title")
        self.assertEqual(handed, [(self.HOME, 7, {"agent": set(), "maintainer": {(36422719, "User")},
                                                  "dependency": {(49699333, "Bot")}},
                                   (281750570, "User"), {}, set(), True, "2026-10-12T12:00:00Z", None, ({}, True, []))])
        # The queue App's account, as the configuration holds it, is told to the account reader (issue 389).
        self.assertIsNone(whos[0].queue)
        with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                unittest.mock.patch.object(entry, "queue_of", lambda controller: (5000009, "Bot")):
            self.run_entry(Hub(self.table(numbers=[7])))
        self.assertEqual(whos[-1].queue, (5000009, "Bot"))
        # The App that opens pull requests, as the configuration names it, is said to each snapshot (issue 295).
        handed.clear()
        with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                unittest.mock.patch.object(entry, "opener", lambda *told: (12, "Bot")):
            self.run_entry(Hub(self.table(numbers=[7])))
        self.assertEqual(handed[0][8], (12, "Bot"))
        # A list of runs read short is said to each snapshot.
        table = self.table(numbers=[7])
        path = "/repos/%s/actions/workflows/run.yml/runs?branch=main&event=workflow_dispatch&per_page=100" % self.HOME
        table[("GET", path)]["body"]["total_count"] = 1
        handed.clear()
        with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot):
            self.run_entry(Hub(table))
        self.assertIs(handed[0][6], False)
        # And holds its threads to nothing recorded, not whole: a Lens Run the list missed may have recorded one.
        self.assertEqual(handed[0][9], ({}, False, []))
        # The accounts as controller/1 holds them, each by id and type; the dispatcher is the pass's token's alone.
        held = copy.deepcopy(CONTROLLER)
        held["accounts"].update(lenses=[{"lens": "pr-review", "login": "combsmith-sf-pr-review[bot]", "id": 11}],
                                agents=[{"login": "combsmith-sf-dev-lead[bot]", "id": 12}],
                                controller={"id": 13, "type": "Bot", "login": "combsmith-sf-controller[bot]"},
                                maintainer=None, approver=None, dependencies=[])
        self.assertEqual(entry.accounts(held), ({"agent": {(12, "Bot")}, "maintainer": set(), "dependency": set()},
                                                (0, "User"), {(11, "Bot"): "pr-review"},
                                                {(11, "Bot"), (12, "Bot"), (13, "Bot")}))
        self.assertEqual(entry.dispatcher(dict(CONTROLLER, accounts=dict(CONTROLLER["accounts"], workflow_token=None))),
                         (0, "Bot"))
        self.assertEqual(entry.dispatcher(config()["controller"]), (41898282, "Bot"))

    def test_the_app_that_opens_pull_requests_is_read_from_the_configuration_by_its_role(self):  # issue 295
        # In slice 1 no Role opens a pull request, so none is bound to an issue by its branch.
        loaded = entry.configuration(ROOT, "factory/v0.3.1")
        self.assertIsNone(entry.opener(loaded["controller"], loaded["kernel"], loaded["apps"]))
        # The App of the Role named for open-pull-request, by the account controller/1 holds for that Role.
        kernel = copy.deepcopy(loaded["kernel"])
        kernel["issues"]["intents"]["open-pull-request"] = {"role": "dev-lead", "app": "combsmith-sf-dev-lead"}
        apps = dict(loaded["apps"], **{"dev-lead": dict(loaded["apps"]["pr-review"], name="combsmith-sf-dev-lead")})
        held = copy.deepcopy(loaded["controller"])
        held["accounts"]["roles"]["dev-lead"] = {"id": 12, "type": "Bot", "login": "combsmith-sf-dev-lead[bot]"}
        self.assertEqual(entry.opener(held, kernel, apps), (12, "Bot"))
        # A Role named whose App, or whose App's account, cannot be told is untold, never nobody.
        unheld = copy.deepcopy(held)
        unheld["accounts"]["roles"]["dev-lead"] = None
        other = copy.deepcopy(held)
        other["accounts"]["roles"]["dev-lead"]["login"] = "combsmith-sf-pr-review[bot]"
        renamed = copy.deepcopy(held)
        renamed["accounts"]["roles"]["dev-lead"]["login"] = "another[bot]"
        for told, app_list in ((unheld, apps), (other, apps), (held, loaded["apps"]),
                               (held, dict(apps, **{"dev-lead": dict(apps["dev-lead"], name="another")})),
                               (renamed, dict(apps, **{"dev-lead": dict(apps["dev-lead"], name="another")}))):
            self.assertEqual(entry.opener(told, kernel, app_list), acceptance.UNTOLD)

    def test_the_entry_waits_out_the_read_gap_before_it_reads(self):  # decision 0043
        from tests.test_adapters import a_pass, a_record, pass_stored, pass_zip, passes_listed
        before = dict(a_record("2026-10-12T11:59:00Z"), reads=[])
        table = self.table()
        listed = passes_listed([a_pass(int(self.RUN)), a_pass(30)])
        table[("GET", listed["request"]["call"].split()[1])] = listed["response"]
        found = pass_stored(30, pass_zip(before))
        table[("GET", found[0]["request"]["call"].split()[1])] = found[0]["response"]
        table[("GET", found[1]["request"]["call"].split()[1])] = found[2]["response"]
        hub = Hub(table)
        code, _, files, slept = self.run_entry(hub)
        self.assertEqual(code, 0)
        # The last pass's read began a minute ago: two minutes more, waited before anything but the records is read.
        self.assertEqual(slept, [(120, 5)])
        self.assertEqual([r["path"].split("?")[0].rsplit("/", 1)[-1] for _, r in hub.sent[2:5]],
                         ["runs", "artifacts", "zip"])
        self.assertEqual(files["view/health.json"]["previous_pass_at"], "2026-10-12T11:59:00Z")
        # Records that cannot be read wait the whole gap, and the pass knows no chain.
        table[("GET", listed["request"]["call"].split()[1])] = {"status": 502, "headers": {}, "body": None}
        code, _, files, slept = self.run_entry(Hub(table))
        self.assertEqual((code, [s for s, _ in slept]), (0, [CONTROLLER["read_gap_seconds"]]))
        self.assertIsNone(files["pass.json"]["context"]["passes_since"])

    def test_what_the_entry_cannot_read_writes_nothing(self):
        for environ, want in (({"RELEASE": None}, "release_untagged"), ({"RELEASE": "v1"}, "release_untagged"),
                              ({"GITHUB_RUN_ID": "1/2"}, "run_unreadable"), ({"GITHUB_RUN_ID": None}, "run_unreadable"),
                              ({entry.KEY: None}, "key_unreadable"), ({entry.KEY: ""}, "key_unreadable")):
            hub = Hub(self.table())
            code, printed, files, _ = self.run_entry(hub, **environ)
            self.assertEqual((code, printed, files, hub.sent), (1, want + "\n", {}, []), environ)
        # A token GitHub would not give: nothing read, nothing to revoke.
        hub = Hub(self.table(minted=403))
        self.assertEqual(self.run_entry(hub)[:3], (1, "token_refused\n", {}))
        self.assertEqual(len(hub.sent), 2)
        # A list of open pull requests read short: nothing written, and the token revoked.
        hub = Hub(self.table(numbers=[7], total=2))
        self.assertEqual(self.run_entry(hub)[:3], (1, "pull_requests_unreadable\n", {}))
        self.assertEqual((hub.sent[-1][0], hub.sent[-1][1]["path"]), (self.TOKEN, "/installation/token"))
        # A token GitHub did not revoke fails the step, after the pass is written.
        table = self.table()
        table[("DELETE", "/installation/token")] = {"status": 500, "headers": {}, "body": None}
        code, printed, files, _ = self.run_entry(Hub(table))
        self.assertEqual((code, printed, "pass.json" in files), (1, "token_not_revoked\n", True))
        # A folder outside the directory it runs in, or one not empty, is refused before anything is read.
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            os.makedirs(os.path.join(d, "inside"))
            os.makedirs(os.path.join(d, "elsewhere"))
            hub = Hub(self.table())
            env = {"RELEASE": "factory/v0.3.1", "GITHUB_RUN_ID": self.RUN, entry.KEY: self.key}
            self.assertEqual(entry.main(["../elsewhere"], env, base=os.path.join(d, "inside"), connect=hub.connect), 2)
            os.makedirs(os.path.join(d, entry.FOLDER))
            self.assertEqual(entry.main([], env, base=d, connect=hub.connect), 2)     # its folder already there
            self.assertEqual(entry.main(["."], env, base=d, connect=hub.connect), 2)
            self.assertEqual(hub.sent, [])
        # The workflow's form, with no argument: the pass is written into a new folder of its own, `pass/`.
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()), support.releasing(env):
            self.assertEqual(entry.main([], env, base=d, clock=lambda: self.CLOCK, sleep=lambda s: None,
                                        connect=Hub(self.table()).connect), 0)
            self.assertTrue(pathlib.Path(d, entry.FOLDER, "pass.json").is_file())
            self.assertEqual(os.stat(os.path.join(d, entry.FOLDER)).st_mode & 0o777, 0o700)

    def test_only_the_entry_reads_the_clock_or_the_environment(self):
        # Every other module of controller/ is a function of what it is given (the test above it); the entry takes the
        # clock, the environment, the sleep and the transport as arguments, so that a test gives each.
        reaching = {"os", "time", "random", "sys"}
        for module in sorted(m for m in (ROOT / "controller").glob("*.py") if m.name != "__main__.py"):
            tree = ast.parse(module.read_text())
            imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
                {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
            self.assertFalse(imported & reaching, module.name)
            self.assertFalse([n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in ("now", "utcnow")],
                             module.name)
        main = ast.parse((ROOT / "controller" / "__main__.py").read_text())
        self.assertLessEqual({"os", "time"}, {a.name for n in ast.walk(main) if isinstance(n, ast.Import)
                                                         for a in n.names})
        hub = Hub(self.table())
        _, _, files, _ = self.run_entry(hub)
        self.assertEqual(files["pass.json"]["now"], "2026-10-12T12:00:00Z")
        self.assertRegex(files["pass.json"]["pass"], r"^p_[0-9A-Z]{20}$")
        minted = {entry.mint_id("r") for _ in range(100)}
        self.assertEqual(len(minted), 100)


if __name__ == "__main__":
    unittest.main()
