"""The Controller's pass, as a function of what it read (issue 193, PR 1): the context from the reads, the Kernel asked
through its two entry points, the pass record, the Runs named, the view, health, the alerts and the successor.

Each case gives the pass recorded facts and run records, as the ports give them and as `examples/` and the trials hold
them, and a fake mint, and holds what comes back. Nothing here reaches the network or reads a clock.
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib
import unittest

from adapters import github, records
from controller import pass_
from kernel.decide import decide
from tests import support
from tests.test_adapters import DISPATCHER, NAME, WORKFLOW, canary, listing

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOW = support.NOW                       # 2026-10-11T13:00:00Z
REPO = support.ITEM["repo"]
CONTROLLER = json.loads((ROOT / "config" / "controller.json").read_text())
TOKEN = {"id": 41898282, "type": "Bot"}       # the workflow's own token's account, as a configuration would hold it
RELAY = {"id": 900001, "type": "User"}        # a relay's account, as one would be held once the relay exists


def config(**controller) -> dict:
    """What a pass is given: the Kernel's configuration, each Work item's Lifecycle, the feed's table, the
    Controller's own, here with both accounts known, and the Release."""
    c = dict(copy.deepcopy(CONTROLLER), accounts={"workflow_token": dict(TOKEN), "relay": dict(RELAY)})
    c.update(controller)
    kernel = {k: v for k, v in copy.deepcopy(support.CONFIG).items() if k != "lifecycle"}
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


def listed(runs=(), unidentified=(), complete=True) -> dict:
    """What the records port returns."""
    return {"runs": [copy.deepcopy(r) for r in runs], "unidentified": list(unidentified), "complete": complete,
            "reads": [{"read": "runs", "date": "2026-10-11T12:59:58Z", "age": 0}]}


def pr(number=42, title="A title", **over) -> dict:
    facts = support.facts(item=dict(support.ITEM, number=number), **over)
    return {"facts": facts, "title": title}


def reads(pulls=None, runs=(), unidentified=(), complete=True, pause=None, event="schedule", actor=None,
          attempt=1, issues=None, usage=None, records_=True) -> dict:
    """What one pass read. By default: a scheduled run, no Pause anywhere, one pull request waiting for its review,
    and the records port's list read whole."""
    out = {"started": {"event": event, "actor": actor, "attempt": attempt},
           "pause": {"org": None, "repos": {REPO: None}} if pause is None else pause,
           "records": listed(runs, unidentified, complete) if records_ else None,
           "pull_requests": [pr()] if pulls is None else pulls,
           "issues": [] if issues is None else issues,
           "facts_reads": [{"date": "2026-10-11T12:59:59Z", "age": 0}]}
    if usage is not None:
        out["usage"] = usage
    return out


def passed(r=None, cfg=None, now=NOW, previous=(), mint=None) -> dict:
    return pass_.run(reads() if r is None else r, config() if cfg is None else cfg, now,
                     list(previous) if previous is not None else None, mint or Mint())


def decisions(out: dict) -> list:
    return [e["decision"] for e in out["record"]["pull_requests"] + out["record"]["issues"]]


class Record(unittest.TestCase):
    def test_the_pass_record_holds_what_the_kernel_was_given_and_replays_it(self):  # decisions 0002, 0039
        # Every key of the context, every run record, each read's date and age, and each item's facts and Decision,
        # with the Run id minted beside the admission: replayed on a laptop, the Kernel gives the same Decision.
        out = passed(reads(pulls=[pr(7), pr(42)], runs=[run(number=42)]))
        record = out["record"]
        self.assertEqual(pass_.validate(record, pass_.SCHEMAS["pass"], schemas=pass_.SCHEMAS), [])
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
        undated = reads()
        undated["facts_reads"] = [{"date": "yesterday", "age": 0}]
        with self.assertRaises(pass_.Refused):
            passed(undated)
        broken = reads()
        del broken["pull_requests"][0]["facts"]["checks"]
        with self.assertRaises(pass_.Refused):
            passed(broken)

    def test_the_pass_asks_the_kernel_through_its_two_entry_points_alone(self):  # issue 193, ruling 8
        tree = ast.parse((ROOT / "controller" / "pass_.py").read_text())
        kernel = {a.asname or a.name: node.module + "." + a.name for node in ast.walk(tree)
                  if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "kernel"
                  for a in node.names}
        self.assertFalse([a.name for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names
                          if a.name.split(".")[0] == "kernel"])
        self.assertEqual(sorted(kernel.values()), ["kernel.decide", "kernel.issue", "kernel.terms"])
        used = {(n.value.id, n.attr) for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name) and n.value.id in kernel}
        self.assertEqual({attr for name, attr in used if kernel[name] != "kernel.terms"}, {"decide"})
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                          and any(a.name in ("time", "random", "os", "subprocess", "socket", "urllib")
                                  for a in n.names)])
        self.assertNotIn("now()", (ROOT / "controller" / "pass_.py").read_text())


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
        self.assertIsNone(passed(reads(pause={"repos": {REPO: None}}))["record"]["context"]["paused"])
        self.assertIsNone(passed(reads(pause={}))["record"]["context"]["paused"])

    def test_the_count_of_active_runs_and_the_unidentified_are_read_from_the_records(self):  # decision 0036
        out = passed(reads(runs=[run("r_00000A", number=7, status="in_progress"), run("r_00000B", number=8, status="queued"),
                                 run("r_00000C")], unidentified=["39086879694"]))
        context = out["record"]["context"]
        self.assertEqual((context["active_runs"], context["unidentified_runs"]), (2, ["39086879694"]))
        self.assertEqual(decisions(out)[0]["reason"], "run_unidentified")

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

    def test_a_capacity_fault_defers_model_runs_for_its_window(self):  # section 3.10
        fault = run("r_00000F", number=9, conclusion="failure", outcome="capacity", at="2026-10-11T10:00:00Z")
        out = passed(reads(runs=[fault]))
        self.assertEqual(out["record"]["context"]["model_deferred_until"], "2026-10-11T15:00:00Z")
        self.assertEqual(decisions(out)[0]["reason"], "capacity")
        self.assertEqual(out["view"]["health"]["faults"], [{"run": "r_00000F", "item": dict(support.ITEM, number=9),
                                                            "outcome": "capacity", "at": "2026-10-11T10:00:00Z"}])
        later = passed(reads(runs=[fault]), now="2026-10-11T15:00:00Z")
        self.assertIsNone(later["record"]["context"]["model_deferred_until"])
        other = passed(reads(runs=[dict(fault, outcome="environment")]))
        self.assertIsNone(other["record"]["context"]["model_deferred_until"])

    def test_an_automatic_pause_needs_agreeing_faults_from_runs_on_different_items_in_a_recent_window(self):  # L-59
        def faults(*numbers, outcome="environment", at="2026-10-11T12:30:00Z"):
            return [run("r_0000%02d" % i, number=n, conclusion="failure", outcome=outcome, at=at)
                    for i, n in enumerate(numbers)]
        out = passed(reads(runs=faults(7, 8, 7)))
        self.assertIs(out["record"]["context"]["paused"], True)
        self.assertEqual(out["view"]["health"]["pause"], {"state": "paused", "by": ["environment"]})
        self.assertEqual(out["alerts"], ["environment", "paused"])
        for runs in (faults(7, 7, 7), faults(7, 8), faults(7, 8, 9, outcome="capacity"),
                     faults(7, 8, 9, at="2026-10-11T11:59:59Z"),
                     faults(7, 8, 9) + [run("r_SUCCES", number=9, at="2026-10-11T12:31:00Z")],
                     faults(7, 8, 9, outcome="item")):
            self.assertIs(passed(reads(runs=runs))["record"]["context"]["paused"], False, runs)
        # A success before the streak ends nothing; one inside the hour on the edge still counts.
        streak = [run("r_SUCCES", number=9, at="2026-10-11T12:00:00Z")] + faults(7, 8, 9, at="2026-10-11T12:00:01Z")
        self.assertIs(passed(reads(runs=streak))["record"]["context"]["paused"], True)
        edge = faults(7, 8, 9, at="2026-10-11T12:00:00Z")
        self.assertIs(passed(reads(runs=edge))["record"]["context"]["paused"], True)
        human = passed(reads(runs=faults(7, 8, 9), pause={"org": "true", "repos": {REPO: None}}))
        self.assertEqual(human["view"]["health"]["pause"], {"state": "paused", "by": ["org", "environment"]})


def earlier(now: str, since=None, started_by="schedule", read_at=None, pulls=None) -> dict:
    """A pass record from an earlier pass at `now`, its chain begun at `since`."""
    out = passed(reads(pulls=[] if pulls is None else pulls), now=now, mint=Mint())
    record = out["record"]
    record["context"]["passes_since"] = now if since is None else since
    record["started_by"] = started_by
    if read_at is not None:
        record["reads"] = [{"read": "runs", "date": read_at, "age": 0}]
    return record


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
        later = earlier("2026-10-11T14:00:00Z")
        self.assertIsNone(since(later))

    def test_a_pass_after_six_hours_with_none_clears_the_not_run_alert_once(self):  # decision 0043, L-48
        out = passed(previous=[earlier("2026-10-11T06:59:59Z")])
        self.assertEqual((out["cleared"], out["view"]["health"]["previous_pass_at"]), (["not_run"], "2026-10-11T06:59:59Z"))
        self.assertEqual(passed(previous=[earlier("2026-10-11T07:00:00Z")])["cleared"], [])
        self.assertEqual(passed()["cleared"], [])

    def test_a_pass_reads_no_sooner_than_three_minutes_after_the_last_pass_began_to_read(self):  # decision 0043
        cfg = config()
        last = earlier("2026-10-11T12:59:30Z", read_at="2026-10-11T12:59:00Z")
        self.assertEqual(pass_.wait_before_reading([last], NOW, cfg), 120)
        self.assertEqual(pass_.wait_before_reading([last], "2026-10-11T13:02:00Z", cfg), 0)
        self.assertEqual(pass_.wait_before_reading([last], "2026-10-11T13:01:59Z", cfg), 1)
        self.assertEqual(pass_.wait_before_reading([last], "2026-10-11T13:10:00Z", cfg), 0)
        self.assertEqual(pass_.wait_before_reading(None, NOW, cfg), 180)
        self.assertEqual(pass_.wait_before_reading([], NOW, cfg), 0)
        unread = copy.deepcopy(last)
        unread["now"] = "2026-02-30T12:00:00Z"
        self.assertEqual(pass_.wait_before_reading([unread], NOW, cfg), 180)
        # The read began before the pass's time: a record with no read waits from its time.
        quiet = dict(copy.deepcopy(last), reads=[])
        self.assertEqual(pass_.wait_before_reading([quiet], NOW, cfg), 150)

    def test_a_successor_starts_only_for_an_item_due_at_the_end(self):  # decisions 0036, 0043
        enqueued = reads(pulls=[pr(reviews=[support.review()])], runs=[run()])
        self.assertEqual([d.get("action") for d in passed(enqueued)["acts"]], ["enqueue"])
        self.assertIs(passed(enqueued)["successor"], True)
        self.assertIs(passed(reads())["successor"], False)                       # an admission ends in a Run's end
        self.assertIs(passed(reads(runs=[run()]))["successor"], False)           # so does an approval
        self.assertIs(passed(reads(pulls=[]))["successor"], False)
        blind = reads(pulls=[pr(reviews=[support.review()])], runs=[run()], unidentified=["39086879694"])
        self.assertEqual([d.get("action") for d in passed(blind)["acts"]], ["enqueue"])
        self.assertIs(passed(blind)["successor"], False)
        unread = reads(pulls=[pr(reviews=[support.review()])], runs=[run()])
        unread["records"]["unidentified"] = "39086879694"
        self.assertIs(passed(unread)["successor"], False)

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
        # An account the configuration holds as null is no one's: until the relay exists, its event is public.
        held = config(accounts={"workflow_token": None, "relay": None})
        self.assertEqual(start("watch", RELAY, cfg=held), "public")
        self.assertEqual(start("workflow_dispatch", TOKEN, cfg=held), "dispatch")
        self.assertEqual(CONTROLLER["accounts"], {"workflow_token": None, "relay": None})
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

    def test_next_actor_and_the_decision_required_are_read_from_the_feed_table_alone(self):  # decision 0039
        held = pr(1, acts_since_writer=support.CONFIG["limits"]["max_acts_per_item"], reviews=[support.review()])
        out = passed(reads(pulls=[pr(2), held, pr(3, state="closed")], runs=[run(number=1)]))
        items = out["view"]["items"]
        self.assertEqual((items["pass"], out["view"]["meta"]["pass"]), (out["record"]["pass"],) * 2)
        self.assertEqual([i["item"]["number"] for i in items["items"]], [2, 1])
        self.assertEqual([(i["next_actor"], i["reason"]) for i in items["items"]],
                         [("factory", "awaiting_review"), ("maintainer", "act_ceiling")])
        self.assertEqual(items["items"][1]["decision_required"],
                         {"question": "allowance_spent", "choices": ["renew_allowance", "close"], "evidence": []})
        self.assertIsNone(items["items"][0]["decision_required"])
        self.assertEqual(items["items"][0]["untrusted"], {"title": "A title"})
        self.assertEqual(items["items"][1]["url"], "https://github.com/%s/pull/1" % REPO)
        self.assertEqual((items["items"][1]["runs"], items["items"][1]["sources"]), (1, ["r_01JA6Z"]))
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
        working = passed(reads(runs=[run(status="in_progress")]))["view"]["items"]["items"][0]
        self.assertEqual((working["attention"], working["next_actor"]), ("working", "factory"))

    def test_a_view_rebuilt_from_the_records_equals_the_view_written_pass_by_pass(self):  # decision 0002
        cfg, mint, written, kept = config(), Mint(), [], []
        steps = [("2026-10-11T13:00:00Z", reads(pulls=[pr(1), pr(2)])),
                 ("2026-10-11T13:05:00Z", reads(pulls=[pr(1), pr(2)], runs=[run(number=1, status="in_progress")])),
                 ("2026-10-11T13:10:00Z", reads(pulls=[pr(1), pr(2)], runs=[run(number=1, status="in_progress")])),
                 ("2026-10-11T13:15:00Z", reads(pulls=[pr(1), pr(2)], runs=[run(number=1)])),
                 ("2026-10-11T13:20:00Z", reads(pulls=[pr(1), pr(2, state="closed")], runs=[run(number=1)]))]
        for now, read in steps:
            out = pass_.run(read, cfg, now, list(kept), mint)
            kept.append(out["record"])
            written.append({"meta": out["view"]["meta"], "items": out["view"]["items"]})
        titles = {"https://github.com/%s/pull/%d" % (REPO, n): "A title" for n in (1, 2)}
        self.assertEqual(pass_.rebuild(list(reversed(kept)), titles, cfg), written)
        ages = [[i["age_hours"] for i in w["items"]["items"] if i["item"]["number"] == 1] for w in written]
        self.assertEqual(ages, [[0.0], [0.08], [0.17], [0.0], [0.08]])

    def test_the_three_thresholds_of_decision_0011_are_computed_and_shown(self):  # decision 0011
        thresholds = passed()["view"]["health"]["thresholds"]
        self.assertEqual(thresholds, {"job_minutes_share": {"value": None, "limit": 0.1, "met": None},
                                      "graphql_points_per_hour": {"value": None, "limit": 3000, "met": None},
                                      "decision_delay_p95_minutes": {"value": None, "limit": 15, "met": None}})
        usage = {"factory_job_minutes": 300, "org_job_minutes": 6000, "graphql_points_peak_hour": 3001}
        shown = passed(reads(usage=usage))["view"]["health"]["thresholds"]
        self.assertEqual(shown["job_minutes_share"], {"value": 0.05, "limit": 0.1, "met": True})
        self.assertEqual(shown["graphql_points_per_hour"], {"value": 3001, "limit": 3000, "met": False})
        for bad in ({"factory_job_minutes": 1, "org_job_minutes": 0}, {"factory_job_minutes": True, "org_job_minutes": 2},
                    {"graphql_points_peak_hour": -1}, {"graphql_points_peak_hour": float("nan")}):
            shown = passed(reads(usage=bad))["view"]["health"]["thresholds"]
            self.assertEqual({k: v["value"] for k, v in shown.items()},
                             {"job_minutes_share": None, "graphql_points_per_hour": None,
                              "decision_delay_p95_minutes": None}, bad)
        # A push after the pass before is read at the next pass: the delay is from the push to that pass.
        before = earlier("2026-10-11T12:40:00Z", pulls=[pr(1, last_push_at="2026-10-11T12:00:00Z")])
        # Twenty delays, of 2 to 19 minutes and two just under 20: the 95th percentile is the 19th, not the largest.
        quick = [pr(n, last_push_at="2026-10-11T12:%02d:00Z" % (59 - n)) for n in range(1, 19)]
        slow = [pr(19, last_push_at="2026-10-11T12:40:02Z"), pr(20, last_push_at="2026-10-11T12:40:01Z")]
        shown = passed(reads(pulls=quick + slow), previous=[before])["view"]["health"]["thresholds"]
        self.assertEqual(shown["decision_delay_p95_minutes"], {"value": 19.97, "limit": 15, "met": False})
        old = passed(reads(pulls=[pr(1, last_push_at="2026-10-11T12:40:00Z")]), previous=[before])
        self.assertIsNone(old["view"]["health"]["thresholds"]["decision_delay_p95_minutes"]["value"])

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


class Ports(unittest.TestCase):
    def test_the_pass_reads_what_the_records_port_gives(self):  # issue 192
        got = records.runs(github.Replay([listing("P-17", 3, rows={"name": NAME})]), canary(), "main", [WORKFLOW],
                           DISPATCHER, per_page=10, sleep=lambda s: None)
        out = passed(reads(pulls=[pr(264)], runs=()) | {"records": got})
        self.assertEqual(out["record"]["runs"], got["runs"])
        self.assertEqual(out["record"]["reads"][:-1], got["reads"])


if __name__ == "__main__":
    unittest.main()
