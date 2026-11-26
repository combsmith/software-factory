"""The Controller's pass, as a function of what it read (issue 193, PR 1): the context from the reads, the Kernel asked
through its two entry points, the pass record, the Runs named, the view, health, the alerts and the successor.

Each case gives the pass recorded facts and run records, as the ports give them and as `examples/` and the trials hold
them, and a fake mint, and holds what comes back. Nothing here reaches the network or reads a clock.
"""
from __future__ import annotations

import ast
import contextlib
import concurrent.futures
import copy
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
import unittest.mock

from adapters import acceptance, effects, github, keyword_spans, records
import controller.__main__ as entry
from controller import configuration, pass_, shared
from controller import credentials as credentials_
from kernel.decide import decide
from tests import support
from tests import test_apply, test_decide, test_issue
from tools.hooks import protected
from tests.test_adapters import DISPATCHER, NAME, WORKFLOW, canary, exchanges, listing, outcome_of, outcome_zip, stored

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOW = support.NOW                       # 2026-10-11T13:00:00Z
REPO = support.ITEM["repo"]
OTHER_REPO = "combsmith/markets"
CONTROLLER = json.loads((ROOT / "config" / "controller.json").read_text())
# The account of the App that opens the Factory's pull requests, as a test hands it to the issues port (issue 1059).
OPENS = (77, "Bot")
# Each stored credential's dates, as a table would hold them with none near its limit at NOW (issue 305).
CREDENTIALS = json.loads((ROOT / "examples" / "credential-ages.json").read_text())
TOKEN = {"id": 41898282, "type": "Bot"}       # the workflow's own token's account, as a configuration would hold it
RELAY = {"id": 900001, "type": "User"}        # a relay's account, as one would be held once the relay exists
APP_ACCOUNT = {"id": 5000001, "type": "Bot", "login": "combsmith-sf-controller[bot]"}  # the Controller App's, as a trial would record it
ROLE_ACCOUNT = {"id": 5000002, "type": "Bot", "login": "combsmith-sf-pr-review[bot]"}   # a Role App's


def written(issues: dict) -> dict:
    """`issues` as config/defaults.json writes it: each App by the name config/apps.json gives it, with no `[bot]`,
    which the pass adds as the issues port names an App (`pass_.issue_config`)."""
    plain = lambda name: name[:-len("[bot]")] if isinstance(name, str) and name.endswith("[bot]") else name
    return dict(issues, label_apps={k: plain(v) for k, v in issues["label_apps"].items()},
                intents={k: dict(v, app=plain(v["app"])) if v else v for k, v in issues["intents"].items()})


def config(**controller) -> dict:
    """What a pass is given: the Kernel's configuration, with issues served, each Work item's Lifecycle, the feed's
    table, the Controller's own, here with both accounts known, the Release, and the credentials' dates."""
    c = dict(copy.deepcopy(CONTROLLER), accounts=dict(CONTROLLER["accounts"], workflow_token=dict(TOKEN), relay=dict(RELAY),
                                                      controller=dict(APP_ACCOUNT),
                                                      roles={name: dict(ROLE_ACCOUNT) for name in CONTROLLER["accounts"]["roles"]},
                                                      # each Lens's App is its Role's account (decision 0223)
                                                      lenses=[dict(lens, id=ROLE_ACCOUNT["id"]) for lens in CONTROLLER["accounts"]["lenses"]]))
    c.update(controller)
    kernel = {k: v for k, v in copy.deepcopy(support.CONFIG).items() if k != "lifecycle"}
    kernel["issues"] = written(test_issue.config()["issues"])
    return {"kernel": kernel, "release": "factory/v0.3.1", "controller": c,
            "feed": json.loads((ROOT / "config" / "feed.json").read_text()),
            "lifecycles": {"pull_request": json.loads((ROOT / "lifecycle" / "pull_request.json").read_text()),
                           "issue": json.loads((ROOT / "lifecycle" / "issue.json").read_text())},
            "credentials": copy.deepcopy(CREDENTIALS)}


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
        self.assertEqual(sorted(record["context"]), ["active_runs", "github_deferred", "model_deferred_until",
                                                     "passes_since", "paused", "unidentified_runs"])
        self.assertEqual(record["runs"], [run(number=42)])
        self.assertEqual([r["read"] for r in record["reads"]], ["runs", "facts"])
        self.assertEqual((record["pass"], record["started_by"], record["release"]), ("p_000001A", "schedule",
                                                                                   "factory/v0.3.1"))
        got = [(e["decision"]["outcome"], e["decision"].get("action"), e["run"]) for e in record["pull_requests"]]
        self.assertEqual(got, [("admit", None, "r_000002A"), ("act", "issue_approval", "r_000003A")])
        kernel = dict(config()["kernel"], lifecycle=config()["lifecycles"]["pull_request"])
        for entry in record["pull_requests"]:
            self.assertEqual(decide(entry["facts"], record["runs"], pass_.given(record, entry), kernel, record["now"]),
                             entry["decision"])
        self.assertNotIn("A title", json.dumps(record))

    def test_a_pass_admits_no_more_runs_than_the_orgs_concurrency_leaves_room_for(self):  # decision 0003
        # Each Run the pass mints is counted active for every admission asked after it, so no Run, asked again at its
        # apply, finds as many others beside it as the limit. Each entry holds the count it was asked with, and
        # replays by it.
        from kernel import issue
        limit = config()["kernel"]["limits"]["org_max_active_runs"]
        self.assertGreaterEqual(limit, 3)       # the mixed case below has three issues to admit
        kernel = dict(config()["kernel"], lifecycle=config()["lifecycles"]["pull_request"])
        issues_kernel = dict(pass_.issue_config(config()["kernel"]), lifecycle=config()["lifecycles"]["issue"])

        def triaged(n):
            return an_issue(n, label_events=[test_issue.labelled(test_issue.TRIAGE, by=test_issue.CONTROLLER)])

        def replays(record):
            for entry in record["pull_requests"]:
                self.assertEqual(decide(entry["facts"], record["runs"], pass_.given(record, entry), kernel,
                                        record["now"]), entry["decision"])
            for entry in record["issues"]:
                self.assertEqual(issue.decide(entry["facts"], record["runs"], pass_.given(record, entry), issues_kernel,
                                              record["now"]), entry["decision"])

        def got(out):
            return [(e["decision"]["outcome"], e["decision"]["reason"], e["active_runs"])
                    for e in out["record"]["pull_requests"] + out["record"]["issues"]]
        # From no Run in flight: the limit's worth admitted, each at the count before it, and every one after deferred
        # at it, a deferral taking no slot.
        idle = passed(reads(pulls=[pr(n) for n in range(1, limit + 3)], runs=[]))
        self.assertEqual(shared.errors(idle["record"], "pass"), [])
        self.assertEqual(got(idle), [("admit", "awaiting_review", n) for n in range(limit)]
                         + [("defer", "concurrency", limit)] * 2)
        self.assertEqual([d["run"] for d in idle["dispatch"]],
                         [e["run"] for e in idle["record"]["pull_requests"] if e["run"] is not None])
        replays(idle["record"])
        # The issues are counted after the pull requests, and each issue admitted takes a slot too.
        seen = []
        real_issue = pass_.issue.decide
        with unittest.mock.patch.object(pass_.issue, "decide",
                                        lambda f, r, c, k, n: seen.append(r) or real_issue(f, r, c, k, n)):
            mixed = passed(reads(pulls=[pr(1)], issues=[triaged(7), triaged(8), triaged(9)],
                                 runs=[run(number=80)] + [run(number=90 + n, status="in_progress")
                                                          for n in range(limit - 3)]))
        # Each ask, the first and the second, is given the run records the record holds.
        self.assertTrue(seen and mixed["record"]["runs"] and all(r == mixed["record"]["runs"] for r in seen))
        self.assertEqual([(o, n) for o, _, n in got(mixed)],
                         [("admit", limit - 3), ("admit", limit - 2), ("admit", limit - 1), ("defer", limit)])
        replays(mixed["record"])
        # An approval's Run takes its slot whatever its place: it is counted before every admission, which the count
        # can defer and it cannot.
        approving = passed(reads(pulls=[pr(n) for n in range(1, limit)] + [pr(42)],
                                 runs=[run(number=42), run(number=90, status="in_progress")]))
        decided = [(e["decision"]["outcome"], e["decision"].get("action"), e["active_runs"])
                   for e in approving["record"]["pull_requests"]]
        self.assertEqual(decided, [("admit", None, n) for n in range(2, limit)] + [("defer", None, limit),
                                                                                 ("act", "issue_approval", 1)])
        self.assertEqual(len(approving["dispatch"]), limit - 1)
        replays(approving["record"])
        # Two approvals take two slots.
        two = passed(reads(pulls=[pr(1), pr(42), pr(43)],
                           runs=[run(number=42), run(name="r_01JA6Y", number=43)]
                           + [run(number=90 + n, status="in_progress") for n in range(limit - 2)]))
        self.assertEqual([(d["outcome"], d.get("action")) for d in decisions(two)],
                         [("defer", None), ("act", "issue_approval"), ("act", "issue_approval")])
        # At the limit and past it an approval still acts, and its Run is dispatched: the count bounds admissions alone.
        over = passed(reads(pulls=[pr(42)], runs=[run(number=42)] + [run(number=90 + n, status="in_progress")
                                                                       for n in range(limit + 1)]))
        self.assertEqual(([(d["outcome"], d.get("action")) for d in decisions(over)], len(over["dispatch"])),
                         ([("act", "issue_approval")], 1))
        # A queue act's Run, once its workflow is named, takes its slot so too; unnamed, it is an act and takes none.
        account = {"id": 349593770, "type": "Bot", "login": "combsmith-sf-queue[bot]"}
        queued = config(workflows=dict(CONTROLLER["workflows"], queue="queue.yml"))
        queued["controller"]["accounts"] = dict(queued["controller"]["accounts"], queue=account)
        busy = [run(number=2)] + [run(number=90 + n, status="in_progress") for n in range(limit - 1)]
        enqueue = reads(pulls=[pr(1), pr(2, reviews=[support.review()])], runs=busy)
        self.assertEqual([(d["outcome"], d.get("action")) for d in decisions(passed(enqueue, cfg=queued))],
                         [("defer", None), ("act", "enqueue")])
        self.assertEqual([(d["outcome"], d.get("action")) for d in decisions(passed(enqueue))],
                         [("admit", None), ("act", "enqueue")])
        # A count that is not whole is given to the Kernel as read, and every item defers on it; one below zero too.
        self.assertEqual([pass_.counted(c, 2) for c in (0, 3, -1, None, True)], [2, 5, -1, None, True])
        told = []
        real = pass_.pull_request.decide
        with unittest.mock.patch.object(pass_.pull_request, "decide",
                                        lambda f, r, c, k, n: told.append(c["active_runs"]) or real(f, r, c, k, n)):
            short = passed(reads(pulls=[pr(1), pr(2)], complete=False))
        self.assertEqual((told, [e["active_runs"] for e in short["record"]["pull_requests"]], short["dispatch"]),
                         ([None, None], [None, None], []))
        # A record written before an entry held its count, of either kind, is valid, and replays by the context's.
        old = passed(reads(pulls=[pr(1)], issues=[triaged(7)], runs=[]))["record"]
        for kind in ("pull_requests", "issues"):
            old[kind] = [{k: v for k, v in e.items() if k != "active_runs"} for e in old[kind]]
        self.assertEqual(shared.errors(old, "pass"), [])
        self.assertEqual([pass_.given(old, e) for e in old["pull_requests"] + old["issues"]], [old["context"]] * 2)
        replays(old)
        # One whose context's count stood at the limit replays its deferral by that count.
        full = passed(reads(pulls=[pr(1)], runs=[run(number=90 + n, status="in_progress") for n in range(limit)]))["record"]
        full["pull_requests"] = [{k: v for k, v in e.items() if k != "active_runs"} for e in full["pull_requests"]]
        self.assertEqual(decisions({"record": full})[0]["reason"], "concurrency")
        replays(full)

    def test_a_hand_approval_merged_between_passes_stays_information(self):
        # decision 0241: information until the window passes its leaving; a reopened one keeps it.
        from tests import test_decide
        facts = test_decide.changing(changed_paths=["docs/notes.md", "harness/run.py"], **test_decide.DEPENDENCY)
        facts["item"] = dict(support.ITEM, number=42)
        head, url = "a" * 40, "https://github.com/%s/pull/42" % REPO
        pull = {"facts": facts, "title": "t", "head": head}
        first = passed(reads(pulls=[pull], runs=[run(number=42)]), now="2026-10-11T12:00:00Z")["record"]
        approval = {"by": "approver", "kind": "approval", "item": dict(support.ITEM, number=42), "key": "PRR_h",
                    "at": "2026-10-11T12:30:00Z", "commit": head}
        seen = dict(SEEN, since="2026-10-11T00:00:00Z", writes=[approval])
        entry = {"alert": "hand_approval", "by": "approver", "write": "approval", "item": url, "key": "PRR_h"}
        records = [first]
        for now in ("2026-10-11T13:00:00Z", "2026-10-11T14:00:00Z", "2026-10-12T06:00:00Z"):
            r = dict(reads(pulls=[], seen=seen), gone=[42] if len(records) == 1 else [])
            out = passed(r, now=now, previous=records[-2:])["record"]
            self.assertEqual(shared.errors(out, "pass"), [], now)
            self.assertIn(entry, out["reconciliation"], now)
            self.assertNotIn("write_unmatched", out["alerts"], now)
            self.assertEqual(out["reconciled"]["hand"], [{"key": "PRR_h", "item": url, "head": head, "at": approval["at"]}], now)
            self.assertEqual(out["reconciled"]["left"], [{"number": 42, "at": "2026-10-11T13:00:00Z"}], now)
            records.append(out)
        # On another head it is unmatched, and its head alone is carried, as taken.
        other = passed(reads(pulls=[], seen=dict(seen, writes=[dict(approval, commit="b" * 40)])), previous=[first])["record"]
        self.assertEqual(("write_unmatched" in other["alerts"], "hand" in other["reconciled"], other["reconciled"]["taken"]),
                         (True, False, [{"key": "PRR_h", "item": url, "head": "b" * 40}]))
        # The pass whose window passes its leaving drops it; one that reads it open again keeps it.
        window = dict(SEEN, since="2026-10-11T14:00:00Z")
        gone = passed(reads(pulls=[], seen=window), now="2026-10-12T20:00:00Z", previous=records[-2:])["record"]
        self.assertEqual(("hand" in gone["reconciled"], gone["reconciled"]["left"]), (False, []))
        # Another repository's row of that number is not dropped by this one's leaving (issue 1190).
        far = dict(records[-1]["reconciled"]["hand"][0], item=url.replace(REPO, REPO + "-elsewhere"))
        theirs = dict(records[-1], reconciled=dict(records[-1]["reconciled"], hand=records[-1]["reconciled"]["hand"] + [far]))
        kept = passed(reads(pulls=[], seen=window), now="2026-10-12T20:00:00Z", previous=[records[-2], theirs])["record"]
        self.assertEqual(kept["reconciled"]["hand"], [far])
        back = passed(reads(pulls=[pull], seen=window, runs=[run(number=42)]), now="2026-10-12T20:00:00Z",
                      previous=records[-2:])["record"]
        self.assertEqual((back["reconciled"]["hand"], back["reconciled"]["left"]), (records[-1]["reconciled"]["hand"], []))
        # So does one it leaves out, read open though its facts could not be read.
        moved = {"facts": {"item": dict(support.ITEM, number=42)}, "title": None, "unread": "facts_unanswered"}
        out = passed(reads(pulls=[moved], seen=window), now="2026-10-12T20:00:00Z", previous=records[-2:])["record"]
        self.assertEqual(out["reconciled"]["hand"], records[-1]["reconciled"]["hand"])
        # Left, read open inside the window, approved, left out and closed: the old stamp drops nothing (issue 1191).
        late = dict(approval, at="2026-10-11T14:30:00Z")
        chain = [first]
        for now, pulls, gone_, writes in (("2026-10-11T13:00:00Z", [], [42], []), ("2026-10-11T14:00:00Z", [pull], [], []),
                                          ("2026-10-11T15:00:00Z", [moved], [], [late]), ("2026-10-12T20:00:00Z", [], [], []),
                                          ("2026-10-12T21:00:00Z", [pull], [], [late])):
            r = dict(reads(pulls=pulls, seen=dict(seen if now < "2026-10-12" else window, writes=writes),
                           runs=[run(number=42)] if pulls == [pull] else []),
                     gone=gone_)
            chain.append(passed(r, now=now, previous=chain[-2:])["record"])
        carried_ = [{"key": "PRR_h", "item": url, "head": head, "at": late["at"]}]
        self.assertEqual((chain[1]["reconciled"]["left"], chain[2]["reconciled"]["left"]),
                         ([{"number": 42, "at": "2026-10-11T13:00:00Z"}], []))
        left_out = passed(reads(pulls=[moved], seen=seen), now="2026-10-11T14:00:00Z", previous=chain[:2])["record"]
        self.assertEqual(left_out["reconciled"]["left"], [])
        unseen = passed(reads(pulls=[pull], seen=None, runs=[run(number=42)]), now="2026-10-11T14:00:00Z", previous=chain[:2])
        self.assertEqual(unseen["record"]["reconciled"]["left"], [])
        # One decided and one left out in the same pass both drop their stamps; one newly left is stamped.
        both = dict(chain[1], reconciled=dict(chain[1]["reconciled"], left=[{"number": n, "at": "2026-10-11T13:00:00Z"}
                                                                            for n in (42, 43)]))
        other_moved = {"facts": {"item": dict(support.ITEM, number=43)}, "title": None, "unread": "facts_unanswered"}
        mixed = dict(reads(pulls=[pull, other_moved], seen=seen, runs=[run(number=42)]), gone=[44])
        self.assertEqual(passed(mixed, now="2026-10-11T14:00:00Z", previous=[first, both])["record"]["reconciled"]["left"],
                         [{"number": 44, "at": "2026-10-11T14:00:00Z"}])
        self.assertEqual(chain[-2]["reconciled"].get("hand"), carried_)
        self.assertEqual(("write_unmatched" in chain[-1]["alerts"], chain[-1]["reconciled"].get("hand")), (False, carried_))

    def test_an_issue_decision_replays_through_the_issues_kernel_configuration(self):  # decisions 0002, 0218
        # Replayed through `pass_.issue_config`, as the pass asked it, the Controller's factory:triage counts.
        from kernel import issue
        from controller import __main__ as main
        triaged = an_issue(7, label_events=[test_issue.labelled(test_issue.TRIAGE, by=test_issue.CONTROLLER)])
        record = passed(reads(pulls=[], issues=[triaged]))["record"]
        (entry,) = record["issues"]
        self.assertEqual((entry["decision"]["state"], entry["decision"]["admit"]["intent"]), ("triage", "investigate-issue"))
        kernel = dict(pass_.issue_config(config()["kernel"]), lifecycle=config()["lifecycles"]["issue"])
        self.assertEqual(issue.decide(entry["facts"], record["runs"], pass_.given(record, entry), kernel, record["now"]),
                         entry["decision"])
        # As written, without the suffix, the App's label would not count.
        written_ = dict(config()["kernel"], lifecycle=config()["lifecycles"]["issue"])
        self.assertEqual(issue.decide(entry["facts"], record["runs"], record["context"], written_, record["now"])["reason"],
                         "label_not_counted")
        # The entry asks the same configuration first, for the names it reserves, and the pass asks it again: it is left
        # as written, so the Kernel is told each App's name with one suffix, and the label counts (issue 963).
        held = dict(config(), apps=json.loads((ROOT / "config" / "apps.json").read_text())["apps"])
        kept = copy.deepcopy(held["kernel"])
        main.reader(github.Replay([]), held)
        self.assertEqual(held["kernel"], kept)
        self.assertEqual(passed(reads(pulls=[], issues=[triaged]), cfg=held)["record"]["issues"][0]["decision"],
                         entry["decision"])
        # A name written with its suffix would be told with two, and no App's label or comment would count: the
        # configuration refuses it, an Intent's App as a label's, and its counter-example says so (issue 963).
        defaults = json.loads((ROOT / "config" / "defaults.json").read_text())
        self.assertEqual(shared.errors(defaults, "config"), [])
        suffixed = copy.deepcopy(defaults)
        suffixed["issues"]["label_apps"]["factory:ready"] = "combsmith-sf-readiness[bot]"
        self.assertTrue(shared.errors(suffixed, "config"))
        for intent in ("investigate-issue", "judge-readiness", "open-pull-request"):
            suffixed = copy.deepcopy(defaults)
            suffixed["issues"]["intents"][intent] = {"role": "readiness", "app": "combsmith-sf-readiness[bot]"}
            self.assertTrue(shared.errors(suffixed, "config"), intent)
            plain = copy.deepcopy(suffixed)
            plain["issues"]["intents"][intent]["app"] = "combsmith-sf-readiness"
            self.assertEqual(shared.errors(plain, "config"), [], intent)
        counter = json.loads((ROOT / "examples" / "invalid" / "config.an-issues-app-named-with-its-bot-suffix.json").read_text())
        self.assertTrue(shared.errors(counter, "config"))

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

    def test_a_queue_act_gets_a_run_id_and_a_dispatch_once_its_workflow_is_named(self):  # issue 381
        # The queue App's acts, an enqueue, a dequeue and a resolution, are each a dispatched Run of the queue workflow,
        # named by run-name/1 with an Intent of its own, so the records port counts each. Until the configuration names
        # that workflow, each stays an act no write serves.
        account = {"id": 349593770, "type": "Bot", "login": "combsmith-sf-queue[bot]"}
        queued = config(workflows=dict(CONTROLLER["workflows"], queue="queue.yml"))
        queued["controller"]["accounts"] = dict(queued["controller"]["accounts"], queue=account)
        approved = reads(pulls=[pr(1), pr(2, reviews=[support.review()])], runs=[run(number=2)])
        out = passed(approved, cfg=queued)
        got = [(e["decision"].get("action"), e["run"]) for e in out["record"]["pull_requests"]]
        self.assertEqual(got, [(None, "r_000002A"), ("enqueue", "r_000003A")])
        self.assertEqual(out["dispatch"][1], {"run": "r_000003A", "name": "sf %s#2 enqueue-merge pr-review sha256:aaaa r_000003A" % REPO})
        self.assertEqual((records.named(out["dispatch"][1]["name"])["intent"], records.named(out["dispatch"][1]["name"])["item"]["type"]),
                         ("enqueue-merge", "pull_request"))
        self.assertEqual(out["acts"], [])
        # Named with no queue App's account beside it, a landed enqueue or dequeue would be counted nowhere: nothing is sent.
        alone = config(workflows=dict(CONTROLLER["workflows"], queue="queue.yml"))
        self.assertEqual([(e["decision"].get("action"), e["run"]) for e in passed(approved, cfg=alone)["record"]["pull_requests"]],
                         [(None, "r_000002A"), ("enqueue", None)])
        before = passed(approved)
        self.assertEqual([(e["decision"].get("action"), e["run"]) for e in before["record"]["pull_requests"]],
                         [(None, "r_000002A"), ("enqueue", None)])
        self.assertEqual([a["action"] for a in before["acts"]], ["enqueue"])
        # Each act by its own Intent.
        accepted = reads(pulls=[pr(2, threads=[support.thread(ruling="accepted")])], runs=[run(number=2)])
        person = support.thread(kind="human", name="don-petry", severity=None)
        gated = reads(pulls=[pr(2, queue=True, reviews=[support.review()], threads=[person])], runs=[run(number=2)])
        for given, intent in ((accepted, "resolve-thread"), (gated, "dequeue-merge")):
            out = passed(given, cfg=queued)
            self.assertEqual([records.named(d["name"])["intent"] for d in out["dispatch"]], [intent], intent)
            self.assertEqual(out["acts"], [], intent)
        # An act the queue App does not make stays one no write serves.
        out = passed(reads(pulls=[], issues=[an_issue(7)]), cfg=queued)
        self.assertEqual(([a["action"] for a in out["acts"]], out["dispatch"]), (["accept"], []))

    def test_the_queue_workflows_runs_are_read_once_it_is_named(self):  # issue 381
        self.assertEqual(entry.run_files(CONTROLLER), ["run.yml", "approve.yml"])
        named = dict(CONTROLLER, workflows=dict(CONTROLLER["workflows"], queue="queue.yml"))
        self.assertEqual(entry.run_files(named), ["run.yml", "approve.yml"])
        named["accounts"] = dict(CONTROLLER["accounts"], queue={"id": 349593770, "type": "Bot", "login": "combsmith-sf-queue[bot]"})
        self.assertEqual(entry.run_files(named), ["run.yml", "approve.yml", "queue.yml"])

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
        # An item whose repo is no repo's name is recorded as no item, and the pass record is still one (issue 913).
        for repo in ("o/r x", "o/r\u200b", "\u00f6/r", "o/r/s", "o/", "/r"):
            odd = passed(reads(pulls=[{"facts": {"item": dict(support.ITEM, repo=repo)}, "title": "x"}]))
            self.assertEqual([e["item"] for e in odd["record"]["left_out"]], [None], repo)
            self.assertEqual(shared.errors(odd["record"], "pass"), [], repo)
        # A good copy and a bad copy of one item: neither is decided (Argon's read of the merged pass).
        copies = passed(reads(pulls=[pr(42), {"facts": {"item": dict(support.ITEM, number=42)}, "title": "x"}]))
        self.assertEqual((decisions(copies), copies["dispatch"]), ([], []))
        self.assertEqual(copies["left_out"], [dict(support.ITEM, number=42)] * 2)
        # An item listed twice is decided neither time: one pass never dispatches two Runs on one item (Muse's read).
        twice = passed(reads(pulls=[pr(42), pr(42), pr(7)], issues=[an_issue(7), an_issue(7)]))
        self.assertEqual([d["item"]["number"] for d in decisions(twice)], [7])
        self.assertEqual(len(twice["dispatch"]), 1)
        self.assertEqual(twice["left_out"], [dict(support.ITEM, number=42)] * 2 + [dict(test_issue.ITEM, number=7)] * 2)

    def test_a_pull_request_that_moved_while_read_is_deferred_once_with_no_alert(self):  # issue 658
        # Moved while it was read, and not in the last pass: deferred, no facts and no act, with no alert, and the record
        # keeps why. Moved again in the next pass, it is the alert; read clean after a move, it is decided.
        item = dict(support.ITEM, number=43)

        def left(code="pull_moved"):
            return {"facts": {"item": dict(item)}, "title": None, "unread": code}
        clean = earlier("2026-10-11T12:50:00Z")
        once = passed(reads(pulls=[pr(42), left()], runs=[run()]), previous=[clean])
        alone = passed(reads(pulls=[pr(42)], runs=[run()]), previous=[clean])
        self.assertEqual((decisions(once), once["dispatch"]), (decisions(alone), alone["dispatch"]))
        self.assertEqual(once["alerts"], [])
        self.assertEqual(once["record"]["left_out"], [{"item": item, "code": "pull_moved"}])
        self.assertEqual(shared.errors(once["record"], "pass"), [])
        moved = dict(once["record"], now="2026-10-11T12:55:00Z")
        twice = passed(reads(pulls=[pr(42), left()], runs=[run()]), previous=[clean, moved])
        self.assertEqual(twice["alerts"], ["facts_unreadable"])
        # What the last record left out for another reason, or another item it left out as moved, or one it could not
        # name, makes this move a first (the Claude review).
        for held in ([{"item": item, "code": "facts_unanswered"}], [{"item": dict(item, number=44), "code": "pull_moved"}],
                     [{"item": None, "code": "pull_moved"}]):
            last = dict(clean, now="2026-10-11T12:55:00Z", left_out=held)
            out = passed(reads(pulls=[pr(42), left()], runs=[run()]), previous=[clean, last])
            self.assertEqual(out["alerts"], [], held)
        settled = passed(reads(pulls=[pr(42), pr(43)], runs=[run()]), previous=[clean, moved])
        self.assertEqual(([d["item"]["number"] for d in decisions(settled)], settled["alerts"]), ([42, 43], []))
        # An issue that moved once is graced as a pull request is, and one that moved twice in a row is the alert
        # (decision 0229, issue 839). The move is the item's own: an issue and a pull request of one number are two.
        theirs = dict(test_issue.ITEM, number=43)
        older_than_left_out = {k: v for k, v in clean.items() if k != "left_out"}
        issue_moved = {"facts": {"item": dict(theirs)}, "title": None, "unread": "pull_moved"}
        first = passed(reads(pulls=[pr(42)], issues=[issue_moved], runs=[run()]), previous=[clean])
        self.assertEqual((first["alerts"], decisions(first), first["record"]["left_out"]),
                         ([], decisions(alone), [{"item": theirs, "code": "pull_moved"}]))
        self.assertEqual(shared.errors(first["record"], "pass"), [])
        again = dict(first["record"], now="2026-10-11T12:55:00Z")
        second = passed(reads(pulls=[pr(42)], issues=[issue_moved], runs=[run()]), previous=[clean, again])
        self.assertEqual(second["alerts"], ["facts_unreadable"])
        for last, entries in ((moved, {"issues": [issue_moved]}), (again, {"pulls": [pr(42), left()]})):
            out = passed(reads(**dict({"pulls": [pr(42)], "runs": [run()]}, **entries)), previous=[clean, last])
            self.assertEqual(out["alerts"], [], entries)
        both = passed(reads(pulls=[pr(42), left()], issues=[issue_moved], runs=[run()]), previous=[clean, again])
        self.assertEqual(both["alerts"], ["facts_unreadable"])
        # So is an issue's move after a last record that cannot say it is a first.
        for previous in (None, (), [older_than_left_out], [dict(clean, now="2026-10-11T12:50:00")]):
            out = passed(reads(pulls=[pr(42)], issues=[issue_moved], runs=[run()]), previous=previous)
            self.assertEqual(out["alerts"], ["facts_unreadable"], previous)
        # Any other code on an issue is the alert at once, as on a pull request.
        out = passed(reads(pulls=[pr(42)], issues=[dict(issue_moved, unread="facts_unanswered")], runs=[run()]), previous=[clean])
        self.assertEqual(out["alerts"], ["facts_unreadable"])
        # Any other read left out is the alert at once: one GitHub did not answer, or facts that are not facts.
        for entry in (left("facts_unanswered"), {"facts": {"item": dict(item)}, "title": None}, left("anything")):
            out = passed(reads(pulls=[pr(42), entry], runs=[run()]), previous=[clean])
            self.assertEqual(out["alerts"], ["facts_unreadable"], entry)
        self.assertEqual(out["record"]["left_out"], [{"item": item, "code": "not_facts"}])
        # A last record that cannot be read, none at all, or one written before it kept what it left out, cannot say the
        # move is a first: it is the alert.
        older = dict(clean)
        del older["left_out"]
        for previous in (None, (), [older], [dict(clean, now="2026-10-11T12:50:00")]):
            out = passed(reads(pulls=[pr(42), left()], runs=[run()]), previous=previous)
            self.assertEqual(out["alerts"], ["facts_unreadable"], previous)
        # An item listed twice is so whatever its read says; an item that names none is kept as null.
        twin = passed(reads(pulls=[left(), left()], runs=[run()]), previous=[clean])
        self.assertEqual((twin["alerts"], [e["code"] for e in twin["record"]["left_out"]]),
                         (["facts_unreadable"], ["listed_twice"] * 2))
        nameless = passed(reads(pulls=[{"facts": {"item": {"number": 0}}, "unread": "pull_moved"}]), previous=[clean])
        self.assertEqual((nameless["alerts"], nameless["record"]["left_out"]),
                         (["facts_unreadable"], [{"item": None, "code": "pull_moved"}]))

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
            # Each Lifecycle's decide, the scope's reading of the unnamed Runs (issue 270), and how an issue stands for
            # the pull request the Factory opened for it (decision 0232).
            self.assertLessEqual({attr for name, attr in used if kernel[name] != "kernel.terms"},
                                 {"decide", "left_alone", "unnamed_scope", "stands"}, module)
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

    def test_a_github_limit_defers_a_pushing_roles_runs_in_its_installation_until_its_reset(self):  # decision 9999
        rule = CONTROLLER["github_capacity"]
        def epoch(at: str) -> int:
            return int((shared.moment(at) - shared.moment("1970-01-01T00:00:00Z")).total_seconds())
        def limited(reset="none", ended="2026-10-11T12:59:30Z", **over) -> dict:
            r = dict(run("r_00000G", conclusion="failure", outcome="github_capacity", at="2026-10-11T12:40:00Z"),
                     ended_at=ended, **over)
            return r if reset == "none" else dict(r, github_reset=reset)
        def until(*runs_, now=NOW):
            return pass_.github_deferred(list(runs_), now, rule)
        least, most = "2026-10-11T13:00:30Z", "2026-10-11T13:59:30Z"
        self.assertEqual((rule["least_seconds"], rule["most_seconds"]), (60, 3600))
        # GitHub's reset, held between the least and the most wait after the Run ended: past the cap it is the cap, in
        # the past the least wait, and a value that is no whole number, or none, the cap.
        self.assertEqual(until(limited(epoch("2026-10-11T13:30:00Z"))),
                         [{"role": "pr-review", "owner": "combsmith", "until": "2026-10-11T13:30:00Z"}])
        for reset, want in ((epoch("2026-10-11T15:00:00Z"), most), (10 ** 30, most), (epoch(least) + 1, "2026-10-11T13:00:31Z"),
                            (epoch("2026-10-11T12:00:00Z"), least), (-1, least), ("1760190000", most), (True, most),
                            (1760190000.5, most), (None, most), ("none", most)):
            self.assertEqual([w["until"] for w in until(limited(reset))], [want], reset)
        # The Run's start stands in for an end GitHub gave none of; once the wait is past, or for a Run said to end after
        # the pass, nothing waits. The latest of a scope's waits holds, each owner and Role apart; no other outcome waits.
        self.assertEqual([w["until"] for w in until(limited(ended=None))], ["2026-10-11T13:40:00Z"])
        self.assertEqual(until(limited(), now=most), [])
        self.assertEqual(until(limited(ended="2026-10-11T13:00:01Z")), [])
        elsewhere = dict(limited(), item=dict(support.ITEM, repo="combsmith-labs/x"))
        other = dict(limited(epoch("2026-10-11T13:10:00Z")), role="dev-lead")
        self.assertEqual(until(limited(epoch("2026-10-11T13:10:00Z")), limited(), elsewhere, other),
                         [{"role": "dev-lead", "owner": "combsmith", "until": "2026-10-11T13:10:00Z"},
                          {"role": "pr-review", "owner": "combsmith", "until": most},
                          {"role": "pr-review", "owner": "combsmith-labs", "until": most}])
        self.assertEqual(until(dict(limited(), outcome="capacity"), dict(limited(), status="in_progress")), [])
        # The pass gives the Kernel the waits and never the model's deferral, so a Role that pushes waits alone; it is
        # no attempt, and raises no alert.
        cfg = config()
        cfg["kernel"]["pushers"] = ["pr-review"]
        for r in (limited(), dict(limited(), ended_at="2026-10-11T12:59:30Z")):
            out = passed(reads(runs=[r]), cfg=cfg)
            context = out["record"]["context"]
            self.assertEqual((context["github_deferred"], context["model_deferred_until"]),
                             ([{"role": "pr-review", "owner": "combsmith", "until": most}], None))
            self.assertEqual((decisions(out)[0]["reason"], out["alerts"]), ("github_capacity", []))
        self.assertEqual(decisions(passed(reads(runs=[limited()])))[0]["outcome"], "admit")
        short = passed(reads(runs=[limited()], complete=False), cfg=cfg)["record"]["context"]
        self.assertEqual((short["github_deferred"], short["active_runs"]), (None, None))

    def test_runs_that_never_ran_pause_admission_and_are_named_as_themselves(self):  # decision 0116
        # A Run GitHub started no job of writes no outcome, so one cause doing it to every dispatch would run each open
        # item to a Hold naming nothing. It counts toward the automatic pause, by the same rule, under its own name.
        def never(*numbers, at="2026-10-11T12:30:00Z", word="skipped"):
            return [dict(run("r_0000%02d" % i, number=n, conclusion="cancelled", at=at), never_ran=word)
                    for i, n in enumerate(numbers)]
        out = passed(reads(runs=never(7, 8, 7)))
        self.assertEqual(out["record"]["context"]["model_deferred_until"], "2026-10-11T13:30:00Z")
        self.assertEqual(decisions(out)[0]["outcome"], "defer")
        self.assertEqual(out["alerts"], ["runs_never_started"])
        self.assertEqual(out["view"]["health"]["pause"], {"state": "paused", "by": ["runs_never_started"]})
        # Each Run behind it is shown by GitHub's word, since a shim's `if:` and a broken Release have different remedies.
        shown = passed(reads(runs=never(7, 8, 9, word="startup_failure")))["view"]["health"]["faults"]
        self.assertEqual({(f["item"]["number"], f["outcome"]) for f in shown},
                         {(7, "startup_failure"), (8, "startup_failure"), (9, "startup_failure")})
        # The pause lapses within the hour, but the cause is still named, until a Run succeeds: a lasting cause runs each
        # item to a Hold that dispatches nothing more, and the name must not lapse before the person reads it.
        aged = never(7, 8, 9, at="2026-10-11T09:00:00Z")
        out = passed(reads(runs=aged))
        self.assertIsNone(out["record"]["context"]["model_deferred_until"])
        self.assertEqual(out["alerts"], ["runs_never_started"])
        self.assertEqual(out["view"]["health"]["pause"], {"state": "none", "by": []})
        cleared = aged + [run("r_SUCCES", number=9, at="2026-10-11T10:00:00Z")]
        self.assertEqual(passed(reads(runs=cleared))["alerts"], [])
        # A Run said to start after the pass counts for neither side, as the pause reads it.
        ahead = "2026-10-11T13:00:01Z"
        self.assertEqual(passed(reads(runs=aged + [run("r_SUCCES", number=9, at=ahead)]))["alerts"], ["runs_never_started"])
        self.assertEqual(passed(reads(runs=never(7, 8, 9, at=ahead)))["alerts"], [])
        # In the second of the pass it counts, as the pause reads it; and a time that is no moment counts for neither.
        self.assertEqual(passed(reads(runs=aged + [run("r_SUCCES", number=9, at="2026-10-11T13:00:00Z")]))["alerts"], [])
        impossible = never(7, 8, at="2026-10-11T09:00:00Z") + [dict(never(9)[0], run="r_NOTIME", started_at="2026-02-31T00:00:00Z")]
        self.assertEqual(passed(reads(runs=impossible))["alerts"], [])
        # In any order, since GitHub lists the newest first.
        self.assertEqual(passed(reads(runs=cleared[::-1]))["alerts"], [])
        self.assertEqual(passed(reads(runs=[cleared[-1]] + never(7, 8, 9, at="2026-10-11T11:00:00Z")))["alerts"],
                         ["runs_never_started"])
        self.assertEqual(passed(reads(runs=never(7, 8, at="2026-10-11T09:00:00Z")))["alerts"], [])
        self.assertEqual(passed(reads(runs=never(7, 7, 7, at="2026-10-11T09:00:00Z")))["alerts"], [])
        # A list not read whole names nothing from what it read.
        self.assertNotIn("runs_never_started", passed(reads(runs=aged, complete=False))["alerts"])
        # A word beside an outcome is the outcome's: an earlier attempt's `item` pauses nothing, and an `environment` is
        # named as one.
        items = [dict(r, outcome="item") for r in never(7, 8, 9)]
        self.assertIsNone(passed(reads(runs=items))["record"]["context"]["model_deferred_until"])
        self.assertEqual(passed(reads(runs=items))["alerts"], [])
        self.assertEqual(passed(reads(runs=items))["view"]["health"]["faults"], [])
        outage = [dict(r, outcome="environment") for r in never(7, 8, 9)]
        self.assertEqual(passed(reads(runs=outage))["alerts"], ["environment"])
        self.assertEqual({f["outcome"] for f in passed(reads(runs=outage))["view"]["health"]["faults"]}, {"environment"})
        # An outage a success ended is not named beside a streak after it.
        ended = [run("r_FAULT1", number=9, conclusion="failure", outcome="environment", at="2026-10-11T12:30:00Z"),
                 run("r_SUCCES", number=9, at="2026-10-11T12:31:00Z")] + never(7, 8, 9, at="2026-10-11T12:40:00Z")
        self.assertEqual(passed(reads(runs=ended))["alerts"], ["runs_never_started"])
        # By the same rule: too few, one item's alone, or a success after them holds nothing.
        for runs in (never(7, 8), never(7, 7, 7), never(7, 8, 9) + [run("r_SUCCES", number=9, at="2026-10-11T12:31:00Z")]):
            self.assertIsNone(passed(reads(runs=runs))["record"]["context"]["model_deferred_until"], runs)
            self.assertNotIn("runs_never_started", passed(reads(runs=runs))["alerts"], runs)
        # A person's cancel, or a concurrency group's, reads the same conclusion with no flag, and trips nothing.
        cancels = [run("r_0000%02d" % i, number=n, conclusion="cancelled", at="2026-10-11T12:30:00Z")
                   for i, n in enumerate((7, 8, 9, 10))]
        self.assertEqual(passed(reads(runs=cancels))["alerts"], [])
        self.assertIsNone(passed(reads(runs=cancels))["record"]["context"]["model_deferred_until"])
        # With an outage in the streak, each is named; alone, an outage stays `environment`.
        fault = run("r_FAULT0", number=9, conclusion="failure", outcome="environment", at="2026-10-11T12:30:00Z")
        both = passed(reads(runs=never(7, 8) + [fault]))
        self.assertEqual(both["alerts"], ["environment", "runs_never_started"])
        self.assertEqual(both["view"]["health"]["pause"]["by"], ["environment", "runs_never_started"])
        # It stops no act, so that only a person's Pause keeps a merge from being stopped.
        queued = pr(42, queue=True, reviews=[support.review()], author="donpetry-bot")
        self.assertEqual([d.get("action") for d in passed(reads(pulls=[queued], runs=[run()] + never(7, 8, 9)))["acts"]],
                         ["dequeue"])

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

    def test_a_pass_its_own_token_started_reads_no_sooner_than_it_can_read_the_run_as_ended(self):  # decision 0115
        cfg = config()
        token = CONTROLLER["accounts"]["workflow_token"]
        started = {"event": "workflow_dispatch", "attempt": 1, "actor": {"id": token["id"], "type": token["type"]}}
        last = earlier("2026-10-11T12:59:30Z", read_at=["2026-10-11T12:59:00Z"])
        # At least the wait, none on a pass with no earlier record, and the gap where it is longer.
        self.assertEqual(pass_.wait_before_reading([], NOW, cfg, started), pass_.SUCCESSOR_WAIT)
        self.assertEqual(pass_.wait_before_reading([last], "2026-10-11T13:10:00Z", cfg, started), pass_.SUCCESSOR_WAIT)
        self.assertEqual(pass_.wait_before_reading([last], NOW, cfg, started), 120)
        self.assertEqual(pass_.wait_before_reading(None, NOW, cfg, started), 180)
        # Anything else started it, or what did cannot be read: no such wait.
        for other in (None, {"event": "schedule", "attempt": 1, "actor": None}, dict(started, attempt=2), dict(started, event="schedule"),
                      dict(started, actor={"id": 1, "type": "User"})):
            self.assertEqual(pass_.wait_before_reading([], NOW, cfg, other), 0, other)

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
                         {"workflow_token": {"id": 41898282, "type": "Bot"}, "relay": None,
                          "controller": {"login": "combsmith-sf-controller[bot]", "id": 344165726, "type": "Bot"},
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

    def test_a_credential_near_its_limit_raises_one_alert(self):  # L-37, issue 305
        # A credential's limit is the earlier of its expiry and its last rotation plus its period, at the start of that
        # day in UTC; within due_within_days of it, it is due, and with neither it never is (the Maintainer's choice:
        # expiry alone). However many are due, the alert is one, and the pass record and the health view name each by
        # its secret's name; the first pass after the row is updated clears it.
        def table(*rows, within=14):
            return {"schema": "credential-ages/1", "due_within_days": within, "credentials": [dict(r) if isinstance(r, dict) else r for r in rows]}

        def row(name="APPROVER_TOKEN", kind="write", rotated="2026-10-01", expires=None, every=90, expiring="given"):
            return {"name": name, "kind": kind, "stored": "environment", "environment": "factory-approve",
                    "workflows": ["approve-job.yml"], "rotated_on": rotated,
                    "expires": expires is not None if expiring == "given" else expiring, "expires_on": expires,
                    "rotate_every_days": every}

        due = credentials_.due
        # The edge: 2026-10-25 is fourteen days after midnight on the 11th, and a second more is not.
        self.assertEqual(due(table(row(expires="2026-10-25", every=None)), "2026-10-11T00:00:00Z"), (True, ["APPROVER_TOKEN"]))
        self.assertEqual(due(table(row(expires="2026-10-25", every=None)), "2026-10-10T23:59:59Z"), (False, []))
        self.assertEqual(due(table(row(rotated="2026-09-25", every=30)), "2026-10-11T00:00:00Z"), (True, ["APPROVER_TOKEN"]))
        self.assertEqual(due(table(row(rotated="2026-09-25", every=30)), "2026-10-10T23:59:59Z"), (False, []))
        self.assertEqual(due(table(row(rotated="2026-09-25", every=30), within=13), "2026-10-11T00:00:00Z"), (False, []))
        # A rotation at the very start of the day the pass reads is no rotation after it (the Claude review on #427).
        self.assertEqual(due(table(row(rotated="2026-10-11", every=90)), "2026-10-11T00:00:00Z"), (False, []))
        # The earlier limit governs, whichever it is.
        self.assertEqual(due(table(row(rotated="2026-10-01", expires="2026-10-20", every=90)), NOW), (True, ["APPROVER_TOKEN"]))
        self.assertEqual(due(table(row(rotated="2026-07-20", expires="2027-10-20", every=90)), NOW), (True, ["APPROVER_TOKEN"]))
        self.assertEqual(due(table(row(rotated="2026-10-01", expires="2027-10-20", every=90)), NOW), (False, []))
        # With neither an expiry nor a period, a credential never falls due by age, and its last rotation, a record
        # alone, is not read: a date is read only where it can bring the credential due.
        self.assertEqual(due(table(row(rotated="2016-10-01", every=None)), NOW), (False, []))
        self.assertEqual(due(table(row(rotated="2016-10-01", every=None)), "9999-12-31T23:59:59Z"), (False, []))
        for rotated in (None, "2026-10-12", "2026-02-30", "1 October 2026"):
            self.assertEqual(due(table(row(rotated=rotated, every=None)), NOW), (False, []), rotated)
            self.assertEqual(due(table(row(rotated=rotated, expires="2027-10-20", every=None)), NOW), (False, []), rotated)
        # A coordinate has no age; one given a date is a credential mislabelled, and due.
        coordinate = row("HELDOUT_OWNER", "coordinate", None, None, None)
        self.assertEqual(due(table(coordinate), NOW), (False, []))
        for field, value in (("rotated_on", "2026-10-01"), ("expires_on", "2027-01-01"), ("rotate_every_days", 90),
                             ("expires", True), ("expires", None)):
            self.assertEqual(due(table(dict(coordinate, **{field: value})), NOW), (True, ["HELDOUT_OWNER"]), field)
        self.assertEqual(due(table({k: v for k, v in coordinate.items() if k != "expires_on"}), NOW), (True, ["HELDOUT_OWNER"]))
        for kind in ("admin", None):     # a row with no dates is skipped only as a coordinate (the Claude review on #427)
            self.assertEqual(due(table(dict(coordinate, kind=kind)), NOW), (True, ["HELDOUT_OWNER"]), kind)
        # A row that cannot be read is due, by its name where it has one.
        # One that expires and whose expiry is not given is such a row: it is due until the Maintainer gives the day.
        for bad in (row(rotated=None), row(rotated="2026-10-12"), row(rotated="2026-02-30"), row(rotated="1 October 2026"),
                    row(expires="2027-13-01"), row(expires=20271001), row(every=0), row(every=True), row(every=90.0),
                    row(every="90"), row(kind="admin"), row(kind=None), row(expiring=True), row(expiring=True, every=None),
                    row(expires="2027-10-20", expiring=False), row(expiring=None), row(expiring="yes"),
                    row(expires="2027-1-5"), row(rotated="2026-1-5"),
                    {k: v for k, v in row().items() if k != "expires"}):
            self.assertEqual(due(table(bad, row("CONTROLLER_APP_KEY")), NOW), (True, ["APPROVER_TOKEN"]), bad)
        self.assertEqual(due(table(row(), row()), NOW), (True, ["APPROVER_TOKEN"]))
        # A period or a nearness past the calendar's end is unreadable, never a fault that stops the pass (the security
        # pass on #427).
        self.assertEqual(due(table(row(every=3000000), row("CONTROLLER_APP_KEY")), NOW), (True, ["APPROVER_TOKEN"]))
        self.assertEqual(due(table(row(), within=1000000000), NOW), (True, []))
        for nameless in (row(name=None), row(name="approver_token"), row(name="APPROVER TOKEN"), "APPROVER_TOKEN", None):
            self.assertEqual(due(table(nameless, row("CONTROLLER_APP_KEY")), NOW), (True, []), nameless)
        # A table that cannot be read is due whole; so is a moment that is none.
        for bad in (None, [], "credential-ages/1", table(), dict(table(row()), schema="credentials/2"),
                    dict(table(row()), due_within_days=0), dict(table(row()), due_within_days=True),
                    dict(table(row()), due_within_days="14"), {"schema": "credential-ages/1", "due_within_days": 14},
                    dict(table(row()), credentials={"APPROVER_TOKEN": row()})):
            self.assertEqual(due(bad, NOW), (True, []), bad)
        self.assertEqual(due(table(row()), "2026-10-11"), (True, []))
        # Through the pass: one alert however many are due, each named, in the record and the view; cleared after.
        cfg = config()
        cfg["credentials"] = table(row(rotated="2026-07-20"), row("CONTROLLER_APP_KEY", rotated=None),
                                   row("READER_APP_KEY"))
        out = passed(cfg=cfg)
        self.assertEqual((out["alerts"], out["record"]["alerts"], out["view"]["health"]["alerts"]),
                         (["credential_due"], ["credential_due"], ["credential_due"]))
        self.assertEqual((out["record"]["credentials_due"], out["view"]["health"]["credentials_due"]),
                         (["APPROVER_TOKEN", "CONTROLLER_APP_KEY"], ["APPROVER_TOKEN", "CONTROLLER_APP_KEY"]))
        self.assertEqual(passed(cfg=dict(cfg, credentials=None))["alerts"], ["credential_due"])
        cleared = passed(cfg=config(), previous=[out["record"]])
        self.assertEqual((cleared["alerts"], cleared["record"]["credentials_due"], cleared["view"]["health"]["credentials_due"]),
                         ([], [], []))
        self.assertEqual(passed(cfg={k: v for k, v in config().items() if k != "credentials"})["alerts"], ["credential_due"])
        # The table the Release holds is read, and one that cannot be read is read as none.
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "config").mkdir()
            self.assertIsNone(configuration._readable(pathlib.Path(d), "config", "credential-ages.json"))
            (pathlib.Path(d) / "config" / "credential-ages.json").write_text("{not json")
            self.assertIsNone(configuration._readable(pathlib.Path(d), "config", "credential-ages.json"))
        self.assertEqual(configuration.load(ROOT, "factory/v0.3.1", "controller")["credentials"],
                         json.loads((ROOT / "config" / "credential-ages.json").read_text()))

    def test_the_kernel_is_given_the_paths_only_a_person_decides_from_the_releases_own_list(self):  # decision 0207
        hooks = json.loads((ROOT / "config" / "hooks.json").read_text())
        want = [e["path"] for e in hooks["person_only"]]
        held = configuration.kernel(ROOT)
        self.assertEqual((want, held["person_only_paths"]), (["release/decision-points.json"], want))
        self.assertEqual(held["person_only_paths"], support.CONFIG["person_only_paths"])
        self.assertEqual(held["model_lens_inputs"], support.CONFIG["model_lens_inputs"])
        self.assertEqual(configuration.load(ROOT, "factory/v0.3.1", "controller")["kernel"]["person_only_paths"], want)
        # The list is the checkout's the Controller runs from, each path once as it is written, and a path a model
        # Lens of that checkout's defaults reads is left off. One with no such list names none, which the Kernel
        # reads as a list.
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "config").mkdir()
            (pathlib.Path(d) / "config" / "defaults.json").write_text((ROOT / "config" / "defaults.json").read_text())
            more, both = [{"path": "release/rings.json", "is": "x"}], [{"path": "harness/", "is": "x"}]
            other = dict(hooks, protected=hooks["protected"] + more + both,
                         person_only=hooks["person_only"] + more + both + more)
            (pathlib.Path(d) / "config" / "hooks.json").write_text(json.dumps(other))
            self.assertEqual(configuration.kernel(pathlib.Path(d))["person_only_paths"], want + ["release/rings.json"])
            (pathlib.Path(d) / "config" / "hooks.json").write_text(
                json.dumps({key: value for key, value in hooks.items() if key != "person_only"}))
            self.assertEqual(configuration.kernel(pathlib.Path(d))["person_only_paths"], [])

    def test_the_kernel_is_given_the_roles_granted_the_push_from_their_manifests(self):  # decision 9999
        # One list: a Role whose Intent permits push_commits, the grant tools/check_authority.py holds; none yet.
        self.assertEqual((configuration.kernel(ROOT)["pushers"], support.CONFIG["pushers"]), ([], []))
        with unittest.mock.patch.object(configuration, "pushers", lambda root: ["dev-lead"] if root == ROOT else None):
            self.assertEqual(configuration.kernel(ROOT)["pushers"], ["dev-lead"])
        manifest = json.loads((ROOT / "roles" / "pr-review.json").read_text())
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "roles").mkdir()
            for name, effects in (("dev-lead", ["comment"]), ("pr-review", ["submit_review"]), ("qa-lead", [])):
                pushing = dict(manifest["intents"][0], permitted_effects=effects + ["push_commits"])
                intents = [dict(manifest["intents"][0], permitted_effects=effects)] + ([pushing] if name != "qa-lead" else [])
                (pathlib.Path(d) / "roles" / ("%s.json" % name)).write_text(json.dumps(dict(manifest, name=name,
                                                                                         intents=intents)))
            self.assertEqual(configuration.pushers(pathlib.Path(d)), ["dev-lead", "pr-review"])

    def test_a_path_a_model_lens_reads_is_never_given_as_a_persons_alone(self):  # decision 0207
        # No path is on both lists today. Were one, a model Lens's input is the stricter name and is not masked: the
        # path is left off what the Kernel is given as a person's, so its change waits as a Lens's input does.
        hooks = json.loads((ROOT / "config" / "hooks.json").read_text())
        models = support.CONFIG["required_lenses"]["model"]
        own = [e["path"] for e in hooks["lens_inputs"] if e["lens"] in models]
        persons = [e["path"] for e in hooks["person_only"]]
        self.assertEqual([path for path in persons if path in own], [])
        both = [{"path": "harness/", "is": "x"}]
        held = protected.parse(json.dumps(dict(hooks, protected=hooks["protected"] + both,
                                               person_only=both + hooks["person_only"] + both)))
        self.assertEqual(configuration.person_only(held, models), persons)
        # Only a model Lens's own input is left off: with no model Lens named, the path is a person's alone.
        self.assertEqual(configuration.person_only(held, []), ["harness/"] + persons)
        kernel = support.config(model_lens_inputs=protected.model_inputs_of(held, models),
                                person_only_paths=configuration.person_only(held, models))
        self.assertEqual(kernel["model_lens_inputs"], support.CONFIG["model_lens_inputs"])
        for paths, reason, evidence in ((["harness/task.py"], "model_lens_input_needs_person", ["harness/"]),
                                        (["harness/task.py"] + persons, "model_lens_input_needs_person", ["harness/"] + persons),
                                        (persons, "path_needs_person", persons)):
            d = test_decide.go(test_decide.changing(**test_decide.AGENT, changed_paths=paths), test_decide.REVIEWED, cfg=kernel)
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("verifying", reason, evidence), paths)

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
                         [("factory", "awaiting_review"), ("maintainer", "act_ceiling"), ("maintainer", "human_finding")])
        # The last is a person's own pull request with a person's Finding: no fix is admitted on it (decision 0216), so
        # the feed names the person asked, by its attention, where it named the Factory by the admission.
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


# The Controller's and the investigating Role's Bots, by ids the configuration holds, under logins they no longer show.
TRIAGE_BOT = ("an-old-login[bot]", 41, "Bot")
ANALYST_BOT = ("another-old-login[bot]", 42, "Bot")


def held_roles(**roles) -> dict:
    """The entry's configuration with the Controller's account TRIAGE_BOT's and the investigating Role's, ANALYST_BOT's,
    held under `roles` alone, as controller/1 holds a Role's App that is no Lens's; `roles` holds more, or other."""
    cfg = config()
    held = dict({"business-analyst": {"id": ANALYST_BOT[1], "type": "Bot", "login": "combsmith-sf-business-analyst[bot]"}}, **roles)
    cfg["controller"]["accounts"].update(controller=dict(APP_ACCOUNT, id=TRIAGE_BOT[1]),
                                         roles=dict(cfg["controller"]["accounts"]["roles"], **held))
    apps = json.loads((ROOT / "config" / "apps.json").read_text())["apps"]
    return dict(cfg, apps=dict(apps, **{"business-analyst": {"name": test_issue.ANALYST["name"][:-len("[bot]")]}}))


def issue_through_the_port(events=(), repo="o/r", exchanges=None, users=None) -> dict:
    """An issue's pass entry as the issues port reads it, its linked pull requests read by `adapters/linked.py`: by
    default issue 41 of `issue_read` in tests/test_adapters.py, with `events` on its timeline and no pull request."""
    from adapters import issues
    from tests.test_adapters import IDENTITIES, Router, issue_read
    found = issue_read(list(events)) if exchanges is None else exchanges
    router = Router(github.Replay(found), dict({"don-petry": "admin"}, **(users or {})))
    # The account reader is the entry's own, from the configuration: no set of accounts is built here (issue 901).
    _, accounts, _ = entry.reader(router, held_roles())
    accounts.repo = repo
    number = found[0]["response"]["body"]["number"]
    facts, title = issues.read(router, repo, number, accounts, lambda: "2026-10-11T12:00:00Z", identities=IDENTITIES, earlier=[])
    return {"facts": facts, "title": title}


def issue_passed(entry: dict, issues_config=None, repo="o/r", now="2026-10-11T12:30:00Z") -> dict:
    """The one Decision a pass makes on `entry`, its issues configured as config/defaults.json writes them."""
    cfg = config()
    cfg["kernel"]["issues"] = written(test_issue.config()["issues"] if issues_config is None else issues_config)
    out = passed(reads(pulls=[], issues=[entry], pause={"org": None, "repos": {repo: None}}), cfg=cfg, now=now)
    (decision,) = decisions(out)
    return decision


class Issues(unittest.TestCase):
    """The issues port's facts reach `kernel/issue.py` through the pass (S3)."""

    def test_with_no_app_declared_for_factory_triage_an_accepted_served_issue_gets_no_acceptance_act(self):  # row 10
        # The narrow turn-on: issues served, no App declared for a label, no triage Intent. Row 10 then adds nothing.
        narrow = dict(test_issue.SERVED, label_apps={"factory:triage": None, "factory:ready": None},
                      intents=dict(test_issue.INTENTS, **{test_issue.INVESTIGATE: None, test_issue.JUDGE: None}))
        entry = an_issue(7, repo="o/r", complete={"timeline": True, "linked": True, "runs": True})
        d = issue_passed(entry, narrow)
        self.assertEqual((d["state"], d["outcome"], d["reason"], d.get("action")), ("new", "nothing", "acceptance_due", None))
        # Declared, the same issue is accepted.
        declared = issue_passed(entry)
        self.assertEqual((declared["outcome"], declared.get("action")), ("act", "accept"))
        # A name that is no name stays none: the Kernel cannot read it, and defers.
        unnamed = dict(test_issue.SERVED, label_apps={"factory:triage": "", "factory:ready": None})
        self.assertEqual(issue_passed(entry, unnamed)["reason"], "issues_unreadable")

    def test_an_app_is_named_by_the_id_the_configuration_holds_so_its_label_and_comment_count(self):  # ruling A
        # The Controller's label and the investigating App's comment count by the App's id: the verdict is wanted next.
        # The investigating Role's App is held under `roles` alone, and its comment is still that Role's (issue 901).
        self.assertNotIn(ANALYST_BOT[1:], entry.accounts(held_roles()["controller"])[3])
        from tests.test_adapters import issue_event
        labelled = issue_event("labeled", 1, actor=TRIAGE_BOT, label={"name": "factory:triage"})
        said = issue_event("commented", 2, actor=ANALYST_BOT)
        d = issue_passed(issue_through_the_port([labelled, said]))
        self.assertEqual((d["state"], d["outcome"], d["admit"]["intent"]), ("triage", "admit", "judge-readiness"))
        # With no comment, the investigation is wanted: the label counted on its own.
        alone = issue_passed(issue_through_the_port([labelled]))
        self.assertEqual((alone["state"], alone["admit"]["intent"]), ("triage", "investigate-issue"))

    def test_issues_whose_apps_cannot_be_told_are_not_decided_and_the_pull_requests_are(self):  # issue 901
        # The entry's word that the issues' Apps cannot be told: no issue is decided, whatever was read, one alert says
        # so, and the pull request is decided as it is without the word.
        told = dict(reads(issues=[an_issue(7)]), issue_apps_unreadable=True)
        out, plain = passed(told), passed(reads(issues=[an_issue(7)]))
        self.assertEqual(([d["item"]["type"] for d in decisions(out)], out["record"]["left_out"]), (["pull_request"], []))
        self.assertEqual(out["record"]["pull_requests"], plain["record"]["pull_requests"])
        self.assertEqual(set(out["alerts"]) - set(plain["alerts"]), {"issue_apps_unreadable"})
        self.assertEqual(out["record"]["alerts"], sorted(out["alerts"]))
        self.assertEqual([d["item"]["type"] for d in decisions(plain)], ["pull_request", "issue"])
        # Anything but exact true is no such word.
        self.assertEqual(len(decisions(passed(dict(told, issue_apps_unreadable="yes")))), 2)

    def test_an_issue_left_unread_by_the_budget_raises_its_own_alert_and_no_other(self):  # decision 0234
        # Two issues the budget left unread: each kept in the record by its code, the budget's alert once, and no alert
        # of facts unread; the pull request is decided.
        home = support.ITEM["repo"]
        budget = lambda n: {"facts": {"item": {"repo": home, "type": "issue", "number": n}}, "title": None, "unread": "issue_budget"}
        out, plain = passed(reads(issues=[an_issue(7), budget(8), budget(9)])), passed(reads(issues=[an_issue(7)]))
        self.assertEqual(out["record"]["left_out"], [{"item": {"repo": home, "type": "issue", "number": n}, "code": "issue_budget"}
                                                     for n in (8, 9)])
        self.assertEqual(set(out["alerts"]) ^ set(plain["alerts"]), {"issue_budget_spent"})
        self.assertEqual(out["record"]["alerts"], sorted(out["alerts"]))
        self.assertEqual([d["item"]["type"] for d in decisions(out)], ["pull_request", "issue"])
        # Beside a fault of the facts, that alert is raised too, by the fault alone.
        unread = {"facts": {"item": {"repo": home, "type": "issue", "number": 10}}, "title": None, "unread": "facts_unanswered"}
        self.assertLessEqual({"facts_unreadable", "issue_budget_spent"}, set(passed(reads(issues=[budget(8), unread]))["alerts"]))
        self.assertNotIn("facts_unreadable", passed(reads(issues=[budget(8)]))["alerts"])
        # The issues' codes are theirs alone: a pull request's entry with either is facts that are not facts.
        pull = {"facts": {"item": dict(support.ITEM, number=11)}, "title": None, "unread": "issue_budget"}
        for code in ("issue_budget", "issue_list_unreadable"):
            out = passed(reads(pulls=[dict(pull, unread=code)]))
            self.assertEqual(out["record"]["left_out"], [{"item": dict(support.ITEM, number=11), "code": "not_facts"}], code)
            self.assertIn("facts_unreadable", out["alerts"], code)
            self.assertFalse({"issue_budget_spent", "issue_list_unreadable"} & set(out["alerts"]), code)

    def test_an_issue_left_unread_by_the_budget_or_the_list_is_shown_as_the_pass_before_decided_it(self):  # decision 1167
        # Issue 7 decided, then left out by the budget, then by a list read short, then read again. The view shows it as
        # the record before decided it, one pass deep, and its time in its State passes over the passes that left it
        # unread; a rebuild from the records shows the same.
        cfg, mint, kept, written = config(), Mint(), [], []
        home = support.ITEM["repo"]
        budget = {"facts": {"item": {"repo": home, "type": "issue", "number": 7}}, "title": None, "unread": "issue_budget"}
        unlisted = {"facts": {"item": None}, "title": None, "unread": "issue_list_unreadable"}
        steps = [("2026-10-11T13:00:00Z", [an_issue(7)]), ("2026-10-11T13:05:00Z", [budget]),
                 ("2026-10-11T13:10:00Z", [unlisted]), ("2026-10-11T13:15:00Z", [an_issue(7)])]
        for now, issues in steps:
            out = pass_.run(reads(issues=issues), cfg, now, list(kept), mint)
            kept.append(out["record"])
            written.append(out["view"]["items"])
        shown = [[(i["reason"], i["age_hours"]) for i in w["items"] if i["item"]["type"] == "issue"] for w in written]
        first = shown[0][0][0]
        self.assertEqual(shown, [[(first, 0.0)], [(first, 0.08)], [], [(first, 0.25)]])
        bare = lambda views: [[dict(i, untrusted=None) for i in v["items"]] for v in views]
        self.assertEqual(bare(w["items"] for w in pass_.rebuild(list(kept), {}, cfg)), bare(written))
        # A list read short carries every issue the pass before decided (Kimi).
        first = pass_.run(reads(issues=[an_issue(7)]), cfg, "2026-10-11T14:00:00Z", [], mint)["record"]
        short = pass_.run(reads(issues=[unlisted]), cfg, "2026-10-11T14:05:00Z", [first], mint)
        self.assertEqual([(i["item"]["number"], i["age_hours"]) for i in short["view"]["items"]["items"]
                          if i["item"]["type"] == "issue"], [(7, 0.08)])
        self.assertEqual(bare(w["items"] for w in pass_.rebuild([first, short["record"]], {}, cfg))[-1],
                         bare([short["view"]["items"]])[0])        # a rebuild carries it the same (Carbon)
        # A carried issue's age walks back over every pass that read it in its State, not the last alone (Carbon).
        again = pass_.run(reads(issues=[an_issue(7)]), cfg, "2026-10-11T14:05:00Z", [first], mint)["record"]
        out = pass_.run(reads(issues=[budget]), cfg, "2026-10-11T14:10:00Z", [first, again], mint)
        self.assertEqual([(i["item"]["number"], i["age_hours"]) for i in out["view"]["items"]["items"]
                          if i["item"]["type"] == "issue"], [(7, 0.17)])
        # An issue left out for any other reason is not carried.
        moved = {"facts": {"item": {"repo": home, "type": "issue", "number": 7}}, "title": None, "unread": "facts_unanswered"}
        out = pass_.run(reads(issues=[moved]), cfg, "2026-10-11T13:20:00Z", list(kept), mint)
        self.assertEqual([i for i in out["view"]["items"]["items"] if i["item"]["type"] == "issue"], [])
        # Only the issue the budget left out is carried: one beside it left out for another reason is not (Carbon).
        both = pass_.run(reads(issues=[an_issue(7), an_issue(8)]), cfg, "2026-10-11T15:00:00Z", [], mint)["record"]
        eight = dict(moved, facts={"item": dict(moved["facts"]["item"], number=8)})
        out = pass_.run(reads(issues=[budget, eight]), cfg, "2026-10-11T15:05:00Z", [both], mint)
        self.assertEqual([i["item"]["number"] for i in out["view"]["items"]["items"] if i["item"]["type"] == "issue"], [7])
        # Each issue is carried on its own: one the pass decided, or left out by name, keeps no other out (Carbon).
        # And one no longer listed, beside one the budget left out, is not carried: the list was read whole (Carbon).
        for issues, shown in (([an_issue(8), budget], [8, 7]), ([an_issue(8), unlisted], [8, 7]), ([moved, unlisted], [8]),
                              ([budget], [7])):
            out = pass_.run(reads(issues=issues), cfg, "2026-10-11T15:05:00Z", [both], mint)
            self.assertEqual([i["item"]["number"] for i in out["view"]["items"]["items"] if i["item"]["type"] == "issue"],
                             shown)
        # A pull request a pass missed beside a list read short starts its age again: the list is the issues' (Carbon).
        out = pass_.run(reads(pulls=[], issues=[unlisted]), cfg, "2026-10-11T15:10:00Z", [both], mint)
        missed = out["record"]
        self.assertEqual(sorted((i["item"]["type"], i["item"]["number"]) for i in out["view"]["items"]["items"]),
                         [("issue", 7), ("issue", 8)])     # both issues carried, no pull request (Astra)
        again = pass_.run(reads(issues=[an_issue(7), an_issue(8)]), cfg, "2026-10-11T15:15:00Z", [both, missed], mint)
        self.assertEqual([i["age_hours"] for i in again["view"]["items"]["items"] if i["item"]["type"] == "pull_request"],
                         [0.0])
        # A short list carries no issue the pass decided, or left out by name for another reason (Astra).
        issues_of = lambda out: [(i["item"]["number"], i["age_hours"]) for i in out["view"]["items"]["items"]
                                 if i["item"]["type"] == "issue"]
        one = pass_.run(reads(issues=[an_issue(7)]), cfg, "2026-10-11T16:00:00Z", [], mint)["record"]
        for issues, shown in (([moved, unlisted], []), ([an_issue(7), unlisted], [(7, 0.08)])):
            self.assertEqual(issues_of(pass_.run(reads(issues=issues), cfg, "2026-10-11T16:05:00Z", [one], mint)), shown)
        # An issue's age counts only passes that read it in its State: a short list before its first read, or a pass
        # that left it out by name for another reason, starts it again (Astra).
        gap = pass_.run(reads(issues=[unlisted]), cfg, "2026-10-11T15:55:00Z", [], mint)["record"]
        self.assertEqual(issues_of(pass_.run(reads(issues=[an_issue(7)]), cfg, "2026-10-11T16:00:00Z", [gap], mint)),
                         [(7, 0.0)])
        for issues in ([moved], [moved, unlisted]):     # beside a short list too (Carbon)
            gone = pass_.run(reads(issues=issues), cfg, "2026-10-11T16:05:00Z", [one], mint)["record"]
            self.assertEqual(issues_of(pass_.run(reads(issues=[an_issue(7)]), cfg, "2026-10-11T16:10:00Z", [one, gone],
                                                 mint)), [(7, 0.0)])

    def test_an_issue_list_read_short_raises_its_own_alert_and_no_other(self):  # decision 0252
        # The list read short names no item: it is kept in the record by its code, raises its alert once and no alert of
        # facts unread, and the pull request is decided. Beside an issue the budget left unread, each raises its own.
        home = support.ITEM["repo"]
        unlisted = {"facts": {"item": None}, "title": None, "unread": "issue_list_unreadable"}
        out, plain = passed(reads(issues=[an_issue(7), unlisted])), passed(reads(issues=[an_issue(7)]))
        self.assertEqual(out["record"]["left_out"], [{"item": None, "code": "issue_list_unreadable"}])
        self.assertEqual(set(out["alerts"]) ^ set(plain["alerts"]), {"issue_list_unreadable"})
        self.assertEqual([d["item"]["type"] for d in decisions(out)], ["pull_request", "issue"])
        pulls = lambda passed_: [d for d in decisions(passed_) if d["item"]["type"] == "pull_request"]
        self.assertEqual(pulls(out), pulls(plain))      # the pull request is decided as with the list whole (Carbon)
        budget = {"facts": {"item": {"repo": home, "type": "issue", "number": 8}}, "title": None, "unread": "issue_budget"}
        both = passed(reads(issues=[an_issue(7), budget, unlisted]))
        self.assertEqual(set(both["alerts"]) ^ set(plain["alerts"]), {"issue_budget_spent", "issue_list_unreadable"})

    def test_the_pass_carries_the_issues_its_reads_owe_and_read_as_left(self):  # issue 916, decision 0235
        read = dict(reads(), unread_issues=[9], gone_issues=[41])
        out = passed(read)
        self.assertEqual((out["record"]["reconciled"]["owed_issues"], out["record"]["reconciled"]["left_issues"]),
                         ([9], [{"number": 41, "at": NOW}]))
        self.assertEqual(set(passed()["record"]["reconciled"]) & {"owed_issues", "left_issues"}, set())

    def test_a_person_whose_login_is_an_apps_name_without_its_suffix_is_not_that_app(self):  # ruling A
        # A User named as config/defaults.json writes the Controller's App is not it, with its token or through an App.
        from tests.test_adapters import issue_event
        name = written(test_issue.SERVED)["label_apps"]["factory:triage"]
        person = (name, 77, "User")
        for via in (None, {"id": 9, "slug": "some-app"}):
            labelled = issue_event("labeled", 1, actor=person, via=via, label={"name": "factory:triage"})
            d = issue_passed(issue_through_the_port([labelled], users={name: "read"}))
            self.assertEqual((d["state"], d["outcome"], d["reason"], d.get("label")),
                             ("new", "act", "label_not_counted", "factory:triage"), via)

    def test_p34s_issue_read_by_the_port_is_deferred_on_its_linked_pull_requests(self):  # P-34, S3
        # The canary's issue through the port and the pass defers on its linked pull requests, read short. Its GraphQL
        # answer is P-34's lastEditedAt in the port's own query, built here; trial P-72 recorded that query, and
        # tests.test_adapters replays it through read() (issue 831).
        from adapters import issues
        from tests.test_adapters import body, canary, exchanges as recorded, linked_read
        repo = canary()
        rest = recorded("P-34.rest")
        own = rest[1]["response"]["body"]
        owner, name = repo.split("/")
        edited = {"number": 42, "updatedAt": own["updated_at"],
                  "lastEditedAt": body("P-34", 0)["data"]["repository"]["issue"]["lastEditedAt"],
                  "timelineItems": {"pageInfo": {"hasNextPage": False}, "nodes": []}}
        asked = {"query": issues.QUERY, "variables": {"owner": owner, "name": name, "number": 42}}
        graphql = {"request": {"via": "graphql", "call": "POST /graphql", "headers": {}, "body": asked},
                   "response": {"status": 200, "headers": {},
                                "body": {"data": {"repository": {"nameWithOwner": repo, "issue": edited}}}}}
        # The port's own word on its linked pull requests reaches the pass (Carbon).
        named = linked_read(total=1, updated=own["updated_at"], repo=repo, number=42)
        entry = issue_through_the_port(repo=repo, exchanges=[rest[1], rest[0], graphql, named, rest[1]])
        self.assertEqual((entry["facts"]["linked"], entry["facts"]["complete"]["linked"]), ([], False))
        d = issue_passed(entry, repo=repo, now="2026-11-13T09:00:00Z")
        self.assertEqual((d["state"], d["outcome"], d["reason"], d["evidence"]), (None, "defer", "facts_incomplete", ["linked"]))
        self.assertEqual(entry["title"], own["title"])
        # Read whole, the Maintainer's closed issue is declined, and nothing is done.
        none = linked_read(updated=own["updated_at"], repo=repo, number=42)
        entry = issue_through_the_port(repo=repo, exchanges=[rest[1], rest[0], graphql, none, rest[1]])
        whole = issue_passed(entry, repo=repo, now="2026-11-13T09:00:00Z")
        self.assertEqual((whole["state"], whole["outcome"], whole["reason"]), ("declined", "nothing", "closed"))


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


def ticking():
    """A timer a second on at each read of it."""
    told = iter(range(10 ** 6))
    return lambda: next(told)


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
            # The org's Pause, read from the home repo's list of the org's variables (issue 362): by default one that
            # names it, set to false; otherwise GitHub's refusal.
            ("GET", "/repos/%s/actions/organization-variables?per_page=100" % self.HOME):
                {"status": 200, "headers": {}, "body": {"total_count": 1, "variables": [
                    {"name": "FACTORY_PAUSED", "value": "false"}]}} if pause == 404
                else {"status": pause, "headers": {}, "body": None},
            ("GET", "/repos/%s/actions/variables/FACTORY_PAUSED" % self.HOME):
                {"status": pause if repo_pause is None else repo_pause, "headers": {}, "body": None},
            ("GET", "/repos/%s/pulls/7" % self.HOME): {"status": 502, "headers": {}, "body": None},
            ("DELETE", "/installation/token"): {"status": 204, "headers": {}, "body": None},
        }

    def run_entry(self, hub, timer=None, err=None, quiet=False, pool=1, **environ):
        # None reads by the entry's own pool (decision 1138).
        env = {"RELEASE": "factory/v0.3.1", "GITHUB_RUN_ID": self.RUN, entry.KEY: self.key}
        env.update(environ)
        slept, printed = [], io.StringIO()
        sleep = lambda seconds: slept.append((seconds, len(hub.sent)))
        self.said = io.StringIO() if err is None else err
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(printed), support.releasing(env):
            code = entry.main(["out"] if os.makedirs(os.path.join(d, "out")) is None else [], {k: v for k, v in env.items()
                                                                                              if v is not None},
                              base=d, clock=lambda: self.CLOCK, sleep=sleep, connect=hub.connect,
                              timer=None if quiet else timer if timer is not None else ticking(), err=self.said,
                              **({} if pool is None else {"pool": pool}))
            named = ["pass.json", "writes.json"] + ["view/%s.json" % v for v in entry.VIEW]
            files = {n: json.loads(pathlib.Path(d, "out", n).read_text()) for n in named
                     if pathlib.Path(d, "out", n).is_file()}
            self.modes = {n: pathlib.Path(d, "out", n).stat().st_mode & 0o777 for n in files}
        return code, printed.getvalue(), files, slept

    def test_the_entry_writes_no_number_that_is_not_finite(self):  # issue 922
        # json.dumps writes NaN as the token NaN, which is no JSON: a value that slipped past its schema fails at the
        # write, and never leaves a file another reader cannot parse.
        views = {name: {} for name in entry.VIEW}
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.object(entry.writes_, "plan", lambda out: {}):
            os.mkdir(os.path.join(d, "a"))
            os.mkdir(os.path.join(d, "b"))
            with self.assertRaises(ValueError):
                entry.write({"record": {"cost": float("nan")}, "view": views}, os.path.join(d, "a"))
            self.assertEqual(os.listdir(os.path.join(d, "a")), [])       # no file is made, an empty one least of all
            # Nor when the number is in a document written after others: every text is made before any file (Astra).
            os.mkdir(os.path.join(d, "c"))
            with self.assertRaises(ValueError):
                entry.write({"record": {"cost": 1.5}, "view": dict(views, **{entry.VIEW[-1]: {"cost": float("inf")}})},
                            os.path.join(d, "c"))
            self.assertEqual(os.listdir(os.path.join(d, "c")), [])
            entry.write({"record": {"cost": 1.5}, "view": views}, os.path.join(d, "b"))
            self.assertEqual(json.loads(pathlib.Path(d, "b", "pass.json").read_text()), {"cost": 1.5})

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

    def test_a_merged_pull_requests_unmatched_write_alarms_inside_the_window_and_not_past_it(self):  # issue 787
        # A pull request a pass before read as left is read again on every pass inside the window, as one that left, so
        # the machine user's write on it that nobody matched keeps raising write_unmatched, after its merge too (decision
        # 0198); once the window passes when it was first read gone, it is read no more, and nothing alarms for it. One
        # read short is owed, and read again as gone with its first stamp; owed past the window, it is read no more.
        inside, past = "2026-10-12T09:00:00Z", "2026-10-11T05:00:00Z"
        spied = []

        def snapshot(transport, repo, number, identities, who, runs_whole, clock, *, kept, with_head, opener, recorded, opened):
            transport.send({"method": "GET", "path": "/repos/%s/pulls/%d" % (repo, number)})
            transport.send({"method": "GET", "path": "/repos/%s/pulls/%d/later" % (repo, number)})
            return support.facts(item=dict(support.ITEM, number=number)), "A title", "a" * 40

        def read(transport, item, kept, identities, apps, since):
            spied.append((item["number"], kept))
            hand = [{"by": "approver", "kind": "approval", "item": item, "key": "PRR_hand%d" % item["number"],
                     "at": "2026-10-12T10:00:00Z"}]
            return (hand if kept == entry.seen_.GONE else [], [], True)

        before = json.loads((ROOT / "examples" / "pass.json").read_text())
        before.update(now="2026-10-12T11:00:00Z", pull_requests=[])
        before["reconciled"] = {"runs": [], "passes": [], "keys": [], "items": [], "dispatched": [], "owed": [13, 14],
                                "left": [{"number": 13, "at": inside}, {"number": 14, "at": past}]}
        table = self.table(numbers=[7])
        pull = copy.deepcopy(exchanges("P-17")[4]["response"])
        pull["headers"] = {"date": "Mon, 12 Oct 2026 11:59:30 GMT", "age": "2"}
        table[("GET", "/repos/%s/pulls/7" % self.HOME)] = table[("GET", "/repos/%s/pulls/7/later" % self.HOME)] = pull
        with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                unittest.mock.patch.object(entry.passes, "records", lambda *a: [before]), \
                unittest.mock.patch.object(entry.seen_, "read", read), \
                unittest.mock.patch.object(entry.seen_, "pushes", lambda *a, **k: ([], True)), \
                unittest.mock.patch.object(entry.applied, "effects", lambda *a, **k: {"applied": [], "read": [], "at": {}, "whole": True}), \
                unittest.mock.patch.object(entry.passes, "written", lambda *a, **k: {"written": [], "read": [], "at": {}, "whole": True}):
            code, _, files, _ = self.run_entry(Hub(table))
        self.assertEqual(code, 0)
        self.assertEqual(spied, [(7, {}), (13, entry.seen_.GONE)])
        record = files["pass.json"]
        self.assertIn("write_unmatched", record["alerts"])
        self.assertEqual([e["item"] for e in record["reconciliation"] if e["alert"] == "write_unmatched"],
                         ["https://github.com/%s/pull/13" % self.HOME])
        self.assertEqual(record["reconciled"]["left"], [{"number": 13, "at": inside}])
        self.assertEqual(record["reconciled"]["owed"], [])
        self.assertEqual(shared.errors(record, "pass"), [])

    def test_each_pull_request_opened_for_an_issue_is_told_how_its_issue_stands(self):  # decision 0232
        # For each open pull request whose facts name the issue it was opened for, the entry reads that issue once,
        # however many name it, open or closed, and the Kernel's `stands` fills the fact before the pass decides. One it
        # cannot read, or that moved while it was read, leaves the fact unread; a pull request opened for no issue, or
        # left out unread, asks nothing.
        person = {"kind": "human", "name": "don-petry", "can_write": True}
        hold = {"label": "factory:hold", "action": "labeled", "by": person, "at": "2026-10-12T10:00:00Z"}
        stood = {41: {"state": "open", "label_events": [hold], "complete": {"timeline": True}},
                 43: {"state": "closed", "label_events": [], "complete": {"timeline": False}},
                 45: {"state": "open", "label_events": [], "complete": {"timeline": True}}}
        names = {7: 41, 8: 41, 9: 42, 10: None, 11: 43, 12: 44, 13: 45, 14: 46}
        asked, readers = [], []

        def snapshot(transport, repo, number, identities, who, runs_whole, clock, *, kept, with_head, opener, recorded, opened):
            if number == 14:
                raise github.Unanswered("no")
            # The facts port gives no word of how an issue stands (decision 0232).
            found = support.facts(item=dict(support.ITEM, number=number), opened_for=names[number])
            del found["issue_stands"]
            return found, "A title", "a" * 40

        def read(transport, repo, number, accounts):
            # The pass's own account reader, which knows the machine user, the Lenses, the queue App and the Factory's
            # Apps, tells who placed or removed each label (decision 0232).
            asked.append((repo, number, accounts is readers[-1]))
            if number == 42:
                raise github.Unanswered("no")
            if number == 44:
                raise entry.facts_.Moved("moved")
            return copy.deepcopy(stood[number])

        def passed(refused=False, whole=True):
            asked.clear()
            plain = entry.reader

            def told(transport, config):
                identities, who, _ = plain(transport, config)
                readers.append(who)
                return identities, who, refused
            with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                    unittest.mock.patch.object(entry.issues_, "stood", read), \
                    unittest.mock.patch.object(entry, "reader", told), \
                    unittest.mock.patch.object(entry.seen_, "read", lambda *a: ([], [], True)), \
                    unittest.mock.patch.object(entry.seen_, "pushes", lambda *a, **k: ([], True)), \
                    unittest.mock.patch.object(entry.applied, "effects", lambda *a, **k: {"applied": [], "read": [], "at": {}, "whole": True}), \
                    unittest.mock.patch.object(entry.passes, "written", lambda *a, **k: {"written": [], "read": [], "at": {}, "whole": whole}):
                code, _, files, _ = self.run_entry(Hub(self.table(numbers=sorted(names))))
            self.assertEqual(code, 0)
            record = files["pass.json"]
            self.assertEqual(shared.errors(record, "pass"), [])
            return {e["facts"]["item"]["number"]: (e["facts"].get("issue_stands", "not given"), e["decision"]["reason"])
                    for e in record["pull_requests"]}

        got = passed()
        self.assertEqual(asked, [(self.HOME, n, True) for n in (41, 42, 43, 44, 45)])
        self.assertEqual({n: got[n][0] for n in got}, {7: "held", 8: "held", 9: None, 10: "not given", 11: "closed",
                                                        12: None, 13: "open"})
        for n in (7, 8, 11):
            self.assertEqual(got[n][1], "issue_stopped", n)
        for n in (9, 12):
            self.assertEqual(got[n][1], "issue_stands_unreadable", n)
        for n in (10, 13):
            self.assertNotIn(got[n][1], ("issue_stopped", "issue_stands_unreadable"), n)
        # While the issues' Apps cannot be told (issue_apps_unreadable), or the tracking issue's number was not read, no
        # issue is read, and each pull request opened for one defers as unread, as the issues do (issue 901).
        for unread in ({"refused": True}, {"whole": False}):
            got = passed(**unread)
            self.assertEqual(asked, [], unread)
            self.assertEqual({n: got[n] for n in got if n != 10},
                             {n: (None, "issue_stands_unreadable") for n in (7, 8, 9, 11, 12, 13)}, unread)
            self.assertEqual(got[10][0], "not given", unread)

    def test_the_entry_gathers_what_reconciliation_reads(self):  # decisions 0061, 0112
        # What each snapshot kept is handed to the seen port, each item once; the machine user's pushes are read; a pull
        # request the pass before served and that has left is read as left; and the Effects are read by what no record
        # before read. The window is a day and `not_run_seconds` back from the read.
        spied, efforts = [], {}

        def snapshot(transport, repo, number, identities, who, runs_whole, clock, *, kept, with_head, opener, recorded, opened):
            kept["reviews"] = "kept of %d" % number     # what a snapshot had read before it failed is not handed on
            if number == 8:
                raise github.Unanswered("no")
            transport.send({"method": "GET", "path": "/repos/%s/pulls/%d" % (repo, number)})
            transport.send({"method": "GET", "path": "/repos/%s/pulls/%d/later" % (repo, number)})
            return support.facts(item=dict(support.ITEM, number=number)), "A title", "a" * 40

        def read(transport, item, kept, identities, apps, since):
            spied.append((item, kept, identities, apps, since))
            return ([], [], item["number"] != 8)

        def pushes(transport, repo, approver, since, clock):
            spied.append(("pushes", repo, approver["id"], since, clock()))
            return ([], True)

        def applied_read(transport, repo, runs, since, known, sleep):
            efforts["runs"], efforts["sleeps"] = (repo, since, known), efforts.get("sleeps", []) + [sleep]
            return {"applied": [], "read": ["r_01JA7Q"], "at": {}, "whole": True}

        def written_read(transport, repo, branch, poller, own, since, known, sleep):
            efforts["passes"], efforts["sleeps"] = (repo, branch, poller, own, since, known), efforts.get("sleeps", []) + [sleep]
            return {"written": [], "read": [{"id": 41, "attempt": 1}], "at": {}, "whole": True}

        before = json.loads((ROOT / "examples" / "pass.json").read_text())
        before["now"] = "2026-10-12T11:00:00Z"
        served = [dict(before["pull_requests"][0], facts=dict(before["pull_requests"][0]["facts"], item=dict(
            before["pull_requests"][0]["facts"]["item"], number=n))) for n in (7, 9)]
        before["pull_requests"] = served
        # When a Run began, as the records before read it from its jobs, is handed to the records port (decision 0193):
        # the last record's word, and the one before's for a Run the last does not list.
        before["runs"][0]["began_at"] = "2026-10-11T12:05:04Z"
        # So is whether each failed Run's Engine step started, as the records before read it with its outcome (issue 757).
        before["runs"][0].update(conclusion="failure", outcome="environment", engine_started=False)
        listed = entry.records.runs

        def runs(*args, **kw):
            efforts["began"], efforts["engines"], efforts["of"] = kw["began"], kw["engines"], kw["of"]
            efforts["sleeps"] = efforts.get("sleeps", []) + [kw["sleep"]]
            return listed(*args, **kw)
        before["reconciled"] = {"runs": [{"id": "r_01JA00", "at": "2026-10-12T11:00:00Z"}],
                                "passes": [{"id": 40, "attempt": 1, "at": "2026-10-12T11:00:00Z"}], "keys": [], "items": [],
                                "dispatched": [], "owed": [11]}
        # The last of two records says what has left: the one before it names another that has not been served since.
        older = dict(before, now="2026-10-12T10:00:00Z", reconciled=dict(before["reconciled"], owed=[], runs=[]),
                     pull_requests=[dict(served[0], facts=dict(served[0]["facts"], item=dict(served[0]["facts"]["item"], number=12)))],
                     runs=[dict(before["runs"][0], began_at="2026-10-11T12:05:01Z", engine_started=True),
                           dict(before["runs"][0], run="r_01JA5Y", began_at="2026-10-11T12:05:09Z", engine_started=True)])
        table = self.table(numbers=[7, 8])
        pull = copy.deepcopy(exchanges("P-17")[4]["response"])
        pull["headers"] = {"date": "Mon, 12 Oct 2026 11:59:30 GMT", "age": "2"}
        table[("GET", "/repos/%s/pulls/7" % self.HOME)] = pull
        table[("GET", "/repos/%s/pulls/7/later" % self.HOME)] = dict(pull, headers={"date": "Mon, 12 Oct 2026 11:59:40 GMT", "age": "0"})
        with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                unittest.mock.patch.object(entry.passes, "records", lambda *a: [older, before]), \
                unittest.mock.patch.object(entry.seen_, "read", read), unittest.mock.patch.object(entry.seen_, "pushes", pushes), \
                unittest.mock.patch.object(entry.applied, "effects", applied_read), \
                unittest.mock.patch.object(entry.records, "runs", runs), \
                unittest.mock.patch.object(entry.passes, "written", written_read):
            code, _, files, slept = self.run_entry(Hub(table))
        self.assertEqual(code, 0)
        # Each port that waits waits by the entry's own sleep, never the clock's (issue 709): the records port, then the
        # applied and written reads.
        self.assertEqual(len(efforts["sleeps"]), 3)
        for k, waited in enumerate(efforts["sleeps"]):
            waited(k + 0.5)
        self.assertEqual([s[0] for s in slept[-3:]], [0.5, 1.5, 2.5])
        self.assertEqual(efforts["began"], {("r_01JA6Z", "2026-10-11T12:05:00Z"): "2026-10-11T12:05:04Z",
                                            ("r_01JA5Y", "2026-10-11T12:05:00Z"): "2026-10-11T12:05:09Z"})
        self.assertEqual(efforts["engines"], {("r_01JA6Z", "2026-10-11T12:05:00Z"): {"engine_started": False}})
        # The port asks when a Run began only of the open pull requests' Runs, which are listed first (decision 0196).
        self.assertEqual(efforts["of"], [{"repo": self.HOME, "type": "pull_request", "number": n} for n in (7, 8)])
        since = "2026-10-11T06:00:00Z"
        item = lambda n: {"repo": self.HOME, "type": "pull_request", "number": n}
        identities, apps = spied[0][2], spied[0][3]
        self.assertEqual([s[:2] for s in spied[:4]],
                         [(item(7), {"reviews": "kept of 7"}), (item(8), None), (item(9), entry.seen_.LEFT), (item(11), entry.seen_.LEFT)])
        self.assertTrue(all(s[4] == since for s in spied[:4]))
        self.assertEqual(identities[(344165726, "Bot")], "controller")
        self.assertEqual(identities[(344166014, "Bot")], "pr-review")
        catalogue = json.loads((ROOT / "config" / "apps.json").read_text())["apps"]
        self.assertEqual(apps, {catalogue["controller"]["app_id"]: "controller", catalogue["pr-review"]["app_id"]: "pr-review"})
        self.assertEqual(spied[4], ("pushes", self.HOME, CONTROLLER["accounts"]["approver"]["id"], since, "2026-10-12T12:00:00Z"))
        self.assertEqual(efforts["runs"], (self.HOME, since, {"r_01JA00"}))
        self.assertEqual(efforts["passes"], (self.HOME, "main", "poller.yml", int(self.RUN), since, {(40, 1)}))
        record = files["pass.json"]
        # The head read beside the facts is kept, for the status on the item.
        self.assertEqual([e["head"] for e in record["pull_requests"]], ["a" * 40])
        # The read that began each snapshot is kept; one whose snapshot could not be read has none.
        self.assertEqual([r for r in record["reads"] if r["read"] == "facts"], [{"read": "facts", "date": "2026-10-12T11:59:30Z", "age": 2}])
        # What it read goes into its record, for the next pass, after what the last one carried.
        self.assertEqual(record["reconciled"]["runs"], before["reconciled"]["runs"] + [{"id": "r_01JA7Q", "at": record["now"]}])
        self.assertEqual(record["reconciled"]["passes"], before["reconciled"]["passes"] + [{"id": 41, "attempt": 1, "at": record["now"]}])
        # What it could not read is owed, read again though it leaves, and not what it did read.
        self.assertEqual(record["reconciled"]["owed"], [8])
        # Each pull request read as left for the first time, of those served or owed, is stamped with now (issue 787).
        self.assertEqual(record["reconciled"]["left"], [{"number": n, "at": record["now"]} for n in (9, 11)])
        self.assertEqual(shared.errors(record, "pass"), [])
        # A seen read not answered, and the machine user's pushes not answered, are short, never a pass that fails.
        def refused(*a, **k):
            raise github.Unanswered("no")

        def whole(transport, item, kept, identities, apps, since):
            return ([], [], True)
        for reads_, pushes_ in ((refused, pushes), (whole, refused)):
            with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                    unittest.mock.patch.object(entry.seen_, "read", reads_), unittest.mock.patch.object(entry.seen_, "pushes", pushes_), \
                    unittest.mock.patch.object(entry.applied, "effects", applied_read), \
                    unittest.mock.patch.object(entry.passes, "written", written_read):
                code, _, files, _ = self.run_entry(Hub(self.table(numbers=[7])))
            self.assertEqual(code, 0)
            self.assertIn("reconciliation_unreadable", files["pass.json"]["alerts"])
        self.assertEqual(files["pass.json"]["reconciled"]["owed"], [])
        dated_table = self.table(numbers=[7])
        dated_table[("GET", "/repos/%s/pulls/7" % self.HOME)] = pull
        dated_table[("GET", "/repos/%s/pulls/7/later" % self.HOME)] = pull
        with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                unittest.mock.patch.object(entry.seen_, "read", whole), unittest.mock.patch.object(entry.seen_, "pushes", pushes), \
                unittest.mock.patch.object(entry.applied, "effects", lambda *a, **k: {"applied": [], "read": [], "at": {}, "whole": True}), \
                unittest.mock.patch.object(entry.passes, "written", lambda *a, **k: {"written": [], "read": [], "at": {}, "whole": True}):
            _, _, files, _ = self.run_entry(Hub(dated_table))
        self.assertNotIn("reconciliation_unreadable", files["pass.json"]["alerts"])
        # What was recorded and could not be read whole is short, whichever half it was.
        for runs_whole, passes_whole in ((False, True), (True, False)):
            with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                    unittest.mock.patch.object(entry.seen_, "read", whole), unittest.mock.patch.object(entry.seen_, "pushes", pushes), \
                    unittest.mock.patch.object(entry.applied, "effects", lambda *a, **k: {"applied": [], "read": [], "at": {}, "whole": runs_whole}), \
                    unittest.mock.patch.object(entry.passes, "written", lambda *a, **k: {"written": [], "read": [], "at": {}, "whole": passes_whole}):
                _, _, files, _ = self.run_entry(Hub(dated_table))
            self.assertIn("reconciliation_unreadable", files["pass.json"]["alerts"], (runs_whole, passes_whole))
        # An answer with no date, or an age that is no count, gives a facts read no stamp, and fails nothing.
        for headers in ({}, {"date": "Mon, 12 Oct 2026 11:59:30 GMT", "age": "x"}):
            undated = self.table(numbers=[7])
            undated[("GET", "/repos/%s/pulls/7" % self.HOME)] = dict(pull, headers=headers)
            undated[("GET", "/repos/%s/pulls/7/later" % self.HOME)] = dict(pull, headers=headers)
            with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                    unittest.mock.patch.object(entry.seen_, "read", whole), unittest.mock.patch.object(entry.seen_, "pushes", pushes), \
                    unittest.mock.patch.object(entry.applied, "effects", applied_read), \
                    unittest.mock.patch.object(entry.passes, "written", written_read):
                code, _, files, _ = self.run_entry(Hub(undated))
            self.assertEqual(code, 0, headers)
            self.assertEqual([r for r in files["pass.json"]["reads"] if r["read"] == "facts"], [], headers)
            self.assertEqual([e["facts"]["item"]["number"] for e in files["pass.json"]["pull_requests"]], [7], headers)
        # Beginnings are kept from pass records alone, each from before this pass. With one that is neither, or with
        # none, the port is still asked, with nothing kept: every Run's jobs are read afresh.
        for held in ([older, dict(before, now="2026-10-12T12:00:00Z")], [older, dict(before, release=7)], None):
            del efforts["began"], efforts["engines"]
            with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                    unittest.mock.patch.object(entry.passes, "records", lambda *a: held), \
                    unittest.mock.patch.object(entry.seen_, "read", whole), unittest.mock.patch.object(entry.seen_, "pushes", pushes), \
                    unittest.mock.patch.object(entry.applied, "effects", applied_read), \
                    unittest.mock.patch.object(entry.records, "runs", runs), \
                    unittest.mock.patch.object(entry.passes, "written", written_read):
                self.run_entry(Hub(self.table(numbers=[7])))
            self.assertEqual(efforts["began"], {}, held and held[1]["now"])
            self.assertEqual(efforts["engines"], {}, held and held[1]["now"])
        # With no record before it, nothing is known, so everything in the window is read.
        with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                unittest.mock.patch.object(entry.passes, "records", lambda *a: None), \
                unittest.mock.patch.object(entry.seen_, "read", read), unittest.mock.patch.object(entry.seen_, "pushes", pushes), \
                unittest.mock.patch.object(entry.applied, "effects", applied_read), \
                unittest.mock.patch.object(entry.passes, "written", written_read):
            _, _, files, _ = self.run_entry(Hub(self.table(numbers=[7])))
        self.assertEqual((efforts["runs"][2], efforts["passes"][5]), (set(), set()))
        # And it cannot say what has left, so what it saw is short, though each read of it was whole.
        self.assertIn("reconciliation_unreadable", files["pass.json"]["alerts"])

    def test_a_snapshot_that_moved_is_kept_by_its_code_and_its_writes_are_owed_once(self):  # issue 658
        # A snapshot that moved while it was read is kept in the record as `pull_moved`, one GitHub did not answer as
        # `facts_unanswered`. Moved for the first time, its writes are not read: they are owed to the next pass, and this
        # reconciliation is whole. Moved again, or after a record that cannot say, it is read short, as any is.
        spied = []

        def snapshot(raised):
            def read(transport, repo, number, identities, who, runs_whole, clock, *, kept, with_head, opener, recorded,
                     opened):
                if number == 8:
                    raise raised
                return support.facts(item=dict(support.ITEM, number=number)), "A title", "a" * 40
            return read

        def read(transport, item, kept, identities, apps, since):
            spied.append(item["number"])
            return ([], [], kept is not None)

        def entry_with(raised, records):
            del spied[:]
            with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot(raised)), \
                    unittest.mock.patch.object(entry.passes, "records", lambda *a: records), \
                    unittest.mock.patch.object(entry.seen_, "read", read), \
                    unittest.mock.patch.object(entry.seen_, "pushes", lambda *a, **k: ([], True)), \
                    unittest.mock.patch.object(entry.applied, "effects",
                                               lambda *a, **k: {"applied": [], "read": [], "at": {}, "whole": True}), \
                    unittest.mock.patch.object(entry.passes, "written",
                                               lambda *a, **k: {"written": [], "read": [], "at": {}, "whole": True}):
                code, _, files, _ = self.run_entry(Hub(self.table(numbers=[7, 8])))
            self.assertEqual(code, 0)
            return files["pass.json"]

        before = json.loads((ROOT / "examples" / "pass.json").read_text())
        # No issue served before, so none is owed while issues are not served (issue 916).
        before.update(now="2026-10-12T11:58:00Z", left_out=[], issues=[])
        item = {"repo": self.HOME, "type": "pull_request", "number": 8}
        once = entry_with(entry.facts_.Moved("moved"), [before])
        self.assertEqual(once["left_out"], [{"item": item, "code": "pull_moved"}])
        self.assertEqual((7 in spied, 8 in spied, once["reconciled"]["owed"]), (True, False, [8]))
        self.assertFalse({"facts_unreadable", "reconciliation_unreadable"} & set(once["alerts"]))
        older = dict(before)
        del older["left_out"]
        for previous in ([dict(before, left_out=once["left_out"])], [older]):
            again = entry_with(entry.facts_.Moved("moved"), previous)
            self.assertEqual((8 in spied, again["reconciled"]["owed"]), (True, [8]))
            self.assertLessEqual({"facts_unreadable", "reconciliation_unreadable"}, set(again["alerts"]))
        unanswered = entry_with(github.Unanswered("no"), [before])
        self.assertEqual(unanswered["left_out"], [{"item": item, "code": "facts_unanswered"}])
        self.assertLessEqual({"facts_unreadable", "reconciliation_unreadable"}, set(unanswered["alerts"]))

    def test_each_snapshot_is_read_with_the_configured_accounts_and_kept(self):  # decisions 0005, 0060
        handed = []

        whos = []

        def snapshot(transport, repo, number, identities, who, runs_whole, clock, *, kept, with_head, opener, recorded, opened):
            handed.append((repo, number, identities, who.approver, who.lenses, who.factory, runs_whole, clock(), opener,
                           recorded))
            whos.append(who)
            self.assertIs(with_head, True)
            return support.facts(item=dict(support.ITEM, number=number)), "A title", "a" * 40
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
                                   (281750570, "User"), {(344166014, "Bot"): "pr-review"},
                                   {(344165726, "Bot"), (344166014, "Bot")}, True, "2026-10-12T12:00:00Z", None,
                                   ({}, True, []))])
        # What the opening Runs recorded is read once a pass, for the Role the configuration names, and handed to each
        # snapshot as it was read (issue 342).
        made, seen, got = {"named": {26: [("r_01JA7Q", 36)]}, "unreadable": set(), "whole": True}, [], []

        def read_opened(transport, repo, runs, role):
            seen.append((repo, role))
            return made
        with unittest.mock.patch.object(entry.facts_, "snapshot",
                                        lambda *a, **k: got.append(k["opened"]) or snapshot(*a, **k)), \
                unittest.mock.patch.object(entry.applied, "opened", read_opened), \
                unittest.mock.patch.object(entry.facts_, "opener_role", lambda kernel: "dev-lead"):
            self.run_entry(Hub(self.table(numbers=[7])))
        self.assertEqual((seen, got), ([(self.HOME, "dev-lead")], [made]))
        self.assertIs(got[0], made)
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
        self.assertEqual(slept, [(120, 6)])
        self.assertEqual([r["path"].split("?")[0].rsplit("/", 1)[-1] for _, r in hub.sent[2:5]],
                         ["runs", "artifacts", "zip"])
        self.assertEqual(files["view/health.json"]["previous_pass_at"], "2026-10-12T11:59:00Z")
        # Records that cannot be read wait the whole gap, and the pass knows no chain.
        table[("GET", listed["request"]["call"].split()[1])] = {"status": 502, "headers": {}, "body": None}
        code, _, files, slept = self.run_entry(Hub(table))
        self.assertEqual((code, [s for s, _ in slept]), (0, [CONTROLLER["read_gap_seconds"]]))
        self.assertIsNone(files["pass.json"]["context"]["passes_since"])

    def test_a_pass_its_own_token_started_waits_for_the_run_that_woke_it_to_end(self):  # decision 0115
        # The entry reads what started it before it waits: a pass the workflow's own token dispatched waits, one a
        # schedule started does not.
        token = CONTROLLER["accounts"]["workflow_token"]
        table = self.table()
        started = table[("GET", "/repos/%s/actions/runs/%s" % (self.HOME, self.RUN))]
        _, _, _, slept = self.run_entry(Hub(table))
        self.assertEqual([s for s, _ in slept], [0])
        started["body"].update(event="workflow_dispatch", actor={"id": token["id"], "type": token["type"], "login": "github-actions[bot]"})
        _, _, _, slept = self.run_entry(Hub(table))
        self.assertEqual([s for s, _ in slept], [pass_.SUCCESSOR_WAIT])
        self.assertEqual(pass_.SUCCESSOR_WAIT, 30)

    def test_the_open_issues_are_listed_from_served_from_and_each_read_as_a_pull_request_is(self):  # S3
        # Listed from `issues.served_from`, each issue is read with the pull requests' account reader and dated as they
        # are; one not read is left out by its code, and a list read short stops the pass.
        since, spied = "2026-10-01T00:00:00Z", {"listed": [], "read": [], "who": [], "identities": [], "controller": [],
                                                "heads": [], "repo": []}
        real, head = entry.configuration, "3b8e5d1c0a9f7e6d5c4b3a291807f6e5d4c3b2a1"

        def served(root, release):
            found = real(root, release)
            found["kernel"]["issues"]["served_from"] = since
            # One App declared by its id, the Controller's, and one the configuration holds no account of.
            found["kernel"]["issues"]["label_apps"] = {"factory:triage": found["apps"]["controller"]["name"],
                                                       "factory:ready": "combsmith-sf-readiness"}
            found["kernel"]["issues"]["intents"] = dict(found["kernel"]["issues"]["intents"], **{
                "investigate-issue": {"role": "business-analyst", "app": "combsmith-sf-business-analyst"}})
            return found

        def snapshot(transport, repo, number, identities, who, runs_whole, clock, *, kept, with_head, opener, recorded, opened):
            spied["who"].append(who)
            return support.facts(item=dict(support.ITEM, number=number)), "A title", "a" * 40

        records_runs = entry.records.runs

        def answered(*a, **k):
            # The records port's own answer, kept by identity: each issue read is handed this very list (head match).
            found = records_runs(*a, **k)
            spied.setdefault("runs", []).append(found)
            return found

        listed_by_the_port = entry.items.open_issues

        def listing(listed, whole=True):
            # What GitHub lists is `listed`; the port itself leaves out what it is handed, so a number it could not be
            # handed fails as it would (Carbon).
            def open_issues(transport, repo, after, *, apart):
                spied["listed"].append((repo, after, apart))
                if listed is None:
                    return listed_by_the_port(transport, repo, after, apart=apart)
                if whole is None:
                    raise github.Unanswered("no")
                with unittest.mock.patch.object(entry.items, "_listed", lambda *a: (list(listed), whole)):
                    return listed_by_the_port(transport, repo, after, apart=apart)
            return open_issues

        def read(transport, repo, number, accounts, clock, *, identities, earlier, kernel, controller, base_head, opener,
                     runs, role):
            spied["read"].append((repo, number, accounts))
            spied.setdefault("openers", []).append(opener)
            # The records port's list and the Role that opens pull requests, whose Runs' pushes tell a head (head match).
            spied.setdefault("pushes", []).append((runs, role))
            spied["heads"].append(base_head)
            spied["identities"].append((identities, earlier))
            spied["controller"].append(controller)
            # Issue 3 is the Controller's tracking issue, as the port tells it by the App it is handed (decision 0233).
            if number == 3 and controller == (CONTROLLER["accounts"]["controller"]["id"], "Bot"):
                raise entry.issues_.Tracking("ours")
            spied.setdefault("kernel", []).append(kernel)
            if number == 6:
                raise entry.facts_.Moved("moved")
            if number == 9:
                raise github.Unanswered("no")
            transport.send({"method": "GET", "path": "/repos/%s/issues/%d" % (repo, number)})
            return test_issue.facts(item=dict(test_issue.ITEM, repo=repo, number=number), read_at=clock()), "Issue five"

        def entry_with(listed, whole=True, configured=served, recorded=True, tracked=True, previous=None, based=False):
            for found in spied.values():
                del found[:]
            # The passes before recorded their tracking issue's write under its number, 8, unless none is `tracked`.
            wrote = {"id": "w1", "type": "tracking_issue", "item": None, "run": None, "state": "already_applied", "key": "8",
                     "reason": None}
            written = {"written": [{"schema": "written/1", "pass": "p_01JA7Q", "release": "factory/v0.3.1",
                                    "writes": [wrote] if tracked else []}],
                       "read": [{"id": 41, "attempt": 1}], "at": {}, "whole": recorded}
            held = entry.passes.records if previous is None else (lambda *a: previous)
            table = self.table(numbers=[7])
            for number in (3, 5):
                table[("GET", "/repos/%s/issues/%d" % (self.HOME, number))] = {
                    "status": 200, "headers": {"date": "Mon, 12 Oct 2026 11:59:30 GMT", "age": "2"}, "body": {}}
            table[("GET", "/repos/%s/issues/10" % self.HOME)] = {
                "status": 200, "headers": {"date": "Mon, 12 Oct 2026 11:59:00 GMT", "age": "0"}, "body": {}}
            if based:   # the default branch and its ref, as GitHub answers them; "repo", the branch's name alone
                table[("GET", "/repos/%s" % self.HOME)] = {
                    "status": 200, "headers": {"date": "Mon, 12 Oct 2026 11:59:40 GMT", "age": "5"}, "body": {"default_branch": "main"}}
            if based is True:
                table[("GET", "/repos/%s/git/ref/heads/main" % self.HOME)] = {
                    "status": 200, "headers": {"date": "Mon, 12 Oct 2026 10:00:00 GMT", "age": "7200"},
                    "body": {"ref": "refs/heads/main", "object": {"type": "commit", "sha": head}}}
            hub = Hub(table)
            with unittest.mock.patch.object(entry, "configuration", configured), \
                    unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                    unittest.mock.patch.object(entry.items, "open_issues", listing(listed, whole)), \
                    unittest.mock.patch.object(entry.passes, "written", lambda *a, **k: written), \
                    unittest.mock.patch.object(entry.passes, "records", held), \
                    unittest.mock.patch.object(entry.issues_, "read", read), \
                    unittest.mock.patch.object(entry, "opener", lambda *a: OPENS), \
                    unittest.mock.patch.object(entry.facts_, "opener_role", lambda kernel: "dev-lead"), \
                    unittest.mock.patch.object(entry.records, "runs", answered):
                code, printed, files, _ = self.run_entry(hub)
            spied["graphql"] = [r for _, r in hub.sent if r["path"] == "/graphql"]
            spied["repo"] = [r for _, r in hub.sent if r["path"] in ("/repos/%s" % self.HOME, "/repos/%s/git/ref/heads/main" % self.HOME)]
            return code, printed, files

        code, printed, files = entry_with([5, 6, 9])
        self.assertEqual((code, printed), (0, "passed\n"))
        record = files["pass.json"]
        # The listing is handed the number the passes recorded their tracking issue under, to leave it out (issue 901).
        self.assertEqual(spied["listed"], [(self.HOME, since, [8])])
        self.assertEqual([n for _, n, _ in spied["read"]], [5, 6, 9])
        # Each by a copy of the reader the pull requests were read with, its answers shared (decision 1138), whose
        # requests the issues' budget counts (decision 0234).
        self.assertTrue(all(who.answers is spied["who"][0].answers and vars(who).keys() == vars(spied["who"][0]).keys()
                            and isinstance(who.transport, entry.Counted) for _, _, who in spied["read"]))
        # Each is handed the account of the App that opens the Factory's pull requests, which names its work branch (#1059).
        self.assertEqual(spied["openers"], [OPENS] * 3)
        # And the one run list the pass read, with the Role that opens pull requests, whose opening Runs' records tell
        # whether a work branch's head is one the Factory pushed (the head match).
        handed = spied["pushes"]
        self.assertEqual(len(handed), 3)
        self.assertTrue(all(runs is spied["runs"][-1] for runs, _ in handed))
        self.assertEqual({role for _, role in handed}, {"dev-lead"})
        # Each is read with the pull requests' class accounts, and the pass records before this pass, here none.
        self.assertEqual(spied["identities"], [(entry.facts_.accounts_of(CONTROLLER)[0], [])] * 3)
        # And the Kernel's configuration, which says whether a draft's checks are read (decision 0217, issue 878).
        self.assertEqual([k["author_role"] for k in spied["kernel"]], [None] * 3)
        self.assertTrue(all("required_lenses" in k for k in spied["kernel"]))
        # The reader names each App the configuration holds by its account's id, as REST spells its Bot's login.
        catalogue = json.loads((ROOT / "config" / "apps.json").read_text())["apps"]
        self.assertEqual(spied["who"][0].apps, {(CONTROLLER["accounts"]["controller"]["id"], "Bot"):
                                                catalogue["controller"]["name"] + "[bot]",
                                                (CONTROLLER["accounts"]["roles"]["pr-review"]["id"], "Bot"):
                                                catalogue["pr-review"]["name"] + "[bot]"})
        # Each name the issues' Kernel is told is an App's is reserved, held by an id or not (Carbon).
        self.assertEqual(spied["who"][0].reserved, {catalogue["controller"]["name"] + "[bot]", "combsmith-sf-readiness[bot]",
                                                    "combsmith-sf-business-analyst[bot]"})
        item = lambda n: {"repo": self.HOME, "type": "issue", "number": n}
        self.assertEqual([e["decision"]["item"] for e in record["issues"]], [item(5)])
        self.assertEqual(record["left_out"], [{"item": item(6), "code": "pull_moved"}, {"item": item(9), "code": "facts_unanswered"}])
        self.assertIn("facts_unreadable", record["alerts"])
        self.assertEqual([r for r in record["reads"] if r["read"] == "facts"], [{"read": "facts", "date": "2026-10-12T11:59:30Z", "age": 2}])
        shown = [i for i in files["view/items.json"]["items"] if i["url"].endswith("/issues/5")]
        self.assertEqual([i["untrusted"] for i in shown], [{"title": "Issue five"}])
        # Two issues read whole: each read is dated by its own first answer, so the older is never stamped as fresh as
        # the other (issue 963).
        code, _, files = entry_with([5, 10])
        self.assertEqual((code, [r for r in files["pass.json"]["reads"] if r["read"] == "facts"]),
                         (0, [{"read": "facts", "date": "2026-10-12T11:59:30Z", "age": 2},
                              {"read": "facts", "date": "2026-10-12T11:59:00Z", "age": 0}]))
        # The default branch's head is read once for the pass and handed to each issue as its `base_head`, dated as a facts
        # read; unread, each is handed none and no read of it is dated; with no issue to read it is not asked (0226, 0242).
        code, _, files = entry_with([5, 10], based=True)
        self.assertEqual((code, spied["heads"], len(spied["repo"])), (0, [head, head], 2))
        self.assertEqual([r for r in files["pass.json"]["reads"] if r["read"] == "facts"][:2],      # the repo's and the ref's
                         [{"read": "facts", "date": "2026-10-12T11:59:40Z", "age": 5},
                          {"read": "facts", "date": "2026-10-12T10:00:00Z", "age": 7200}])
        self.assertEqual((entry_with([5, 10])[0], spied["heads"], len(spied["repo"])), (0, [None, None], 1))
        code, _, files = entry_with([5, 10], based="repo")        # the repo answered, its ref not: nothing is dated for it
        self.assertEqual((code, spied["heads"], [r["date"] for r in files["pass.json"]["reads"] if r["read"] == "facts"]),
                         (0, [None, None], ["2026-10-12T11:59:30Z", "2026-10-12T11:59:00Z"]))
        for listed, whole, recorded in (([], True, True), ([5], False, True), ([5], True, False)):
            entry_with(listed, whole, recorded=recorded, based=True)
            self.assertEqual(spied["repo"], [], (listed, whole, recorded))
        # A list read short, or not answered, reads no issue; the pull requests are decided as ever, and the pass leaves
        # out one entry naming no item, by the list's code, with its alert and no other for it (decision 0252).
        for whole in (False, None):
            code, printed, files = entry_with([5], whole)
            record = files["pass.json"]
            self.assertEqual((code, printed, spied["read"], record["issues"]), (0, "passed\n", [], []), whole)
            self.assertEqual(record["left_out"], [{"item": None, "code": "issue_list_unreadable"}])
            self.assertEqual(len(record["pull_requests"]), 1)
            self.assertIn("issue_list_unreadable", record["alerts"])
            self.assertNotIn("facts_unreadable", record["alerts"])
            self.assertEqual(keyword_spans.UNLISTED, entry.reads_.UNLISTED)
        # The passes' records not read whole: the tracking issue's number may be one not read, so no issue is read, and
        # each listed is left out as unread; the pull requests are decided as ever (issue 901).
        code, printed, files = entry_with([5, 8], recorded=False)
        self.assertEqual((code, spied["read"], files["pass.json"]["issues"]), (0, [], []))
        self.assertEqual(files["pass.json"]["left_out"], [{"item": item(n), "code": "facts_unanswered"} for n in (5, 8)])
        self.assertEqual(len(files["pass.json"]["pull_requests"]), 1)
        # They were handed to the port as none to leave out, never as unread: it cannot take that (Carbon, Kimi).
        self.assertEqual(spied["listed"], [(self.HOME, since, ())])
        # Read whole with no tracking issue written: none is known, and each listed is read and decided (Muse, Kimi).
        code, _, files = entry_with([5], tracked=False)
        self.assertEqual((code, spied["listed"], [n for _, n, _ in spied["read"]]), (0, [(self.HOME, since, ())], [5]))
        self.assertEqual(([e["decision"]["item"] for e in files["pass.json"]["issues"]], files["pass.json"]["left_out"]),
                         ([item(5)], []))
        # This pass read no write of it, but the last record carried its number, 8: it is left out by that (Astra, Muse).
        last = json.loads((ROOT / "examples" / "pass.json").read_text())
        last.update(now="2026-10-12T11:00:00Z", pull_requests=[], reconciled={
            "runs": [], "passes": [], "items": [], "dispatched": [], "owed": [],
            "keys": [{"where": "written", "type": "tracking_issue", "key": "8", "at": "2026-10-12T11:00:00Z"}]})
        code, _, files = entry_with([8, 5], tracked=False, previous=[last])
        # Each issue is read with every record the entry read, oldest first.
        self.assertEqual([earlier for _, earlier in spied["identities"]], [[last]])
        older = dict(last, now="2026-10-12T10:57:00Z")
        entry_with([8, 5], tracked=False, previous=[last, older])
        self.assertEqual([earlier for _, earlier in spied["identities"]], [[older, last]])
        self.assertEqual((code, spied["listed"], [n for _, n, _ in spied["read"]]), (0, [(self.HOME, since, [8])], [5]))
        self.assertEqual([e["decision"]["item"] for e in files["pass.json"]["issues"]], [item(5)])
        # No record numbers the tracking issue, 3, as when its write left the records' window or its opening went
        # unanswered: it is listed, told at its own read by the App the entry hands the port, and is neither decided nor
        # left out; the others are read on (decision 0233).
        code, _, files = entry_with([3, 5, 9], tracked=False)
        self.assertEqual((code, [n for _, n, _ in spied["read"]]), (0, [3, 5, 9]))
        self.assertEqual(spied["controller"], [(CONTROLLER["accounts"]["controller"]["id"], "Bot")] * 3)
        self.assertEqual(([e["decision"]["item"] for e in files["pass.json"]["issues"]], files["pass.json"]["left_out"]),
                         ([item(5)], [{"item": item(9), "code": "facts_unanswered"}]))
        # With no Controller App named the port is handed none, and nothing is told as its tracking issue.
        def unnamed(root, release):
            found = served(root, release)
            found["controller"]["accounts"]["controller"] = None
            return found
        code, _, files = entry_with([3, 5], tracked=False, configured=unnamed)
        self.assertEqual((code, spied["controller"], [e["decision"]["item"] for e in files["pass.json"]["issues"]]),
                         (0, [None, None], [item(3), item(5)]))
        # No date: nothing is listed, asked or read; the one GraphQL read is the pull requests' list.
        code, _, files = entry_with(None, configured=real)
        self.assertEqual((code, spied["listed"], spied["read"], files["pass.json"]["issues"]), (0, [(self.HOME, None, [8])], [], []))
        self.assertEqual(len(spied["graphql"]), 1)

    def test_the_issue_reads_stop_at_the_passs_budget_and_those_left_out_by_it_are_read_first_by_the_next(self):  # 0234
        # Seven issues listed, every pass the same. Each read sends `cost` requests through the transport the entry
        # hands the port, counted as sent, answered or not; once `max_issue_requests` are spent no further read starts.
        since, read, real = "2026-10-01T00:00:00Z", [], entry.configuration
        written = {"written": [], "read": [], "at": {}, "whole": True}

        def run(budget, cost, previous, listed=(1, 2, 3, 4, 5, 6, 7)):
            def served(root, release):
                found = real(root, release)
                found["kernel"]["issues"]["served_from"] = since
                found["controller"]["max_issue_requests"] = budget
                return found

            def snapshot(transport, repo, number, identities, who, runs_whole, clock, **k):
                return support.facts(item=dict(support.ITEM, number=number)), "A title", "a" * 40

            def issue(transport, repo, number, accounts, clock, *, identities, earlier, **_):
                read.append(number)
                for at in range(cost):
                    # Every other request is the account reader's permission read, which is counted too (Claude).
                    through = accounts.transport if at % 2 else transport
                    try:
                        through.send({"method": "GET", "path": "/repos/%s/issues/%d" % (repo, number)})
                    except github.Unanswered:
                        pass
                return test_issue.facts(item=dict(test_issue.ITEM, repo=repo, number=number), read_at=clock()), "An issue"
            del read[:]
            with unittest.mock.patch.object(entry, "configuration", served), \
                    unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                    unittest.mock.patch.object(entry.items, "open_issues", lambda *a, **k: (list(listed), True)), \
                    unittest.mock.patch.object(entry.passes, "written", lambda *a, **k: written), \
                    unittest.mock.patch.object(entry.passes, "records", lambda *a: previous), \
                    unittest.mock.patch.object(entry.issues_, "read", issue):
                code, _, files, _ = self.run_entry(Hub(self.table(numbers=[7])))
            self.assertEqual(code, 0)
            record = files["pass.json"]
            # The next pass reads it as the record before it, an hour on.
            return list(read), dict(record, now="2026-10-12T11:00:00Z")
        item = lambda n: {"repo": self.HOME, "type": "issue", "number": n}
        # A budget of three, a request an issue: three read, the rest left out by the budget, each named, with the
        # budget's alert once and no alert of facts unread for them.
        first, record = run(3, 1, None)
        self.assertEqual(first, [1, 2, 3])
        self.assertEqual(record["left_out"], [{"item": item(n), "code": "issue_budget"} for n in (4, 5, 6, 7)])
        self.assertEqual(([e["decision"]["item"]["number"] for e in record["issues"]], record["alerts"].count("issue_budget_spent")),
                         ([1, 2, 3], 1))
        self.assertNotIn("facts_unreadable", record["alerts"])
        # Those the record before left out by the budget are read first, in the order it left them out, then the rest in
        # the listing's: so, the list unchanged, every issue is read within ceil(7 / 3) = 3 passes, and in every three in
        # a row after. In the listing's order among them, 7 would be passed over for good from the third pass on.
        passes = [first]
        for _ in range(5):
            got, record = run(3, 1, [record])
            passes.append(got)
        self.assertEqual(passes, [[1, 2, 3], [4, 5, 6], [7, 1, 2], [3, 4, 5], [6, 1, 2], [7, 3, 4]])
        for at in range(len(passes) - 2):
            self.assertEqual(sorted(set(sum(passes[at:at + 3], []))), [1, 2, 3, 4, 5, 6, 7], at)
        # A read already begun finishes: at two requests an issue, the second starts at two of three and ends at four;
        # the third does not start. And every pass reads one issue at least, however dear.
        self.assertEqual(run(3, 2, None)[0], [1, 2])
        self.assertEqual(run(1, 5, None)[0], [1])
        # With the budget never spent, every issue is read, and no budget's alert is raised.
        got, record = run(100, 1, None)
        self.assertEqual((got, record["left_out"], "issue_budget_spent" in record["alerts"]), ([1, 2, 3, 4, 5, 6, 7], [], False))
        # A last record that holds no left out entries, or none by the budget, gives the listing's order.
        self.assertEqual(run(3, 1, [dict(record, left_out=[{"item": item(6), "code": "facts_unanswered"}])])[0], [1, 2, 3])
        bare = dict(record)
        del bare["left_out"]
        self.assertEqual(run(3, 1, [bare])[0], [1, 2, 3])
        # Only the last record's debts are read first, never an older one's (Astra).
        owing = lambda numbers, now: dict(record, now=now, left_out=[{"item": item(n), "code": "issue_budget"} for n in numbers])
        self.assertEqual(run(1, 1, [owing([2, 3], "2026-10-12T10:00:00Z"), owing([3, 1], "2026-10-12T11:00:00Z")], listed=(1, 2, 3))[0], [3])
        # An issue the record before left out by the budget that is no longer listed is passed over; one left out twice
        # is read once; a pull request left out is no issue.
        self.assertEqual(run(3, 1, [dict(record, left_out=[{"item": item(9), "code": "issue_budget"},
                                                           {"item": item(6), "code": "issue_budget"},
                                                           {"item": item(6), "code": "issue_budget"},
                                                           {"item": dict(item(2), type="pull_request"), "code": "issue_budget"},
                                                           {"item": item(5), "code": "issue_budget"}])])[0], [6, 5, 1])
        # A last record whose list was read short is passed over: the queue is the newest one's that read the issues.
        short = dict(record, now="2026-10-12T11:00:00Z", issues=[], left_out=[{"item": None, "code": "issue_list_unreadable"}])
        self.assertEqual(run(1, 1, [owing([3, 1], "2026-10-12T10:00:00Z"), short], listed=(1, 2, 3))[0], [3])
        self.assertEqual(run(1, 1, [short], listed=(1, 2, 3))[0], [1])
        # A number listed twice is read twice, owed or not, and both are left out as listed twice, never decided (Kimi).
        got, record = run(100, 1, [dict(record, left_out=[{"item": item(6), "code": "issue_budget"}])], listed=(5, 6, 6))
        self.assertEqual((got, [e["code"] for e in record["left_out"] if e["item"] == item(6)]), ([6, 6, 5], ["listed_twice"] * 2))
        self.assertEqual([e["decision"]["item"]["number"] for e in record["issues"]], [5])

    def test_a_queues_or_a_lenss_name_declared_as_an_issues_app_refuses_the_issues_alone_and_the_pull_requests_are_decided(self):
        # The reader tells the queue App and a Lens's App by their ids, as a queue and a Lens, never as an App by its
        # name: one named for a label or an Intent could have no act read as that App's. No issue is listed, read or
        # decided, and the pass says `issue_apps_unreadable`; the pull requests are read and decided as ever (issue 901).
        real = entry.configuration
        queue = {"id": 5000009, "type": "Bot", "login": "combsmith-sf-queue[bot]"}
        renamed = {"lens": "pr-review", "login": "an-old-login[bot]", "id": CONTROLLER["accounts"]["roles"]["pr-review"]["id"]}
        other = {"lens": "coderabbit", "login": "coderabbitai[bot]", "id": 136622811}
        intent = lambda app: {"label_apps": {"factory:triage": "combsmith-sf-controller", "factory:ready": None},
                              "intents": {"investigate-issue": {"role": "business-analyst", "app": app},
                                          "judge-readiness": None, "open-pull-request": None}}
        whos, asked = [], []

        def snapshot(transport, repo, number, identities, who, *a, **k):
            whos.append(who)
            return support.facts(item=dict(support.ITEM, number=number)), "A title", "a" * 40

        def entry_with(issues, **accounts):
            def told(root, release):
                found = real(root, release)
                found["kernel"]["issues"] = dict(found["kernel"]["issues"], served_from="2026-10-01T00:00:00Z", **issues)
                found["controller"]["accounts"].update(accounts)
                return found
            hub = Hub(self.table(numbers=[7]))
            with unittest.mock.patch.object(entry, "configuration", told), \
                    unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                    unittest.mock.patch.object(entry.items, "open_issues", lambda t, repo, since, **k: asked.append(since) or ([], since is None)):
                code, printed, files, _ = self.run_entry(hub)
            record = files.get("pass.json", {})
            return (code, printed, "issue_apps_unreadable" in record.get("alerts", ()),
                    [e["decision"]["item"]["number"] for e in record.get("pull_requests", ())], record.get("issues"),
                    record.get("left_out"), asked[-1])
        ready = lambda name: {"label_apps": {"factory:triage": "combsmith-sf-controller", "factory:ready": name}}
        # The issues are listed as with no date, so none is; pull request 7 is decided, and nothing is written for an issue.
        # The listing is asked with no date (decision 0252: a list read short no longer stops the pass to show it).
        refused = (0, "passed\n", True, [7], [], [], None)
        # The pull requests' reader does not reserve the name that collides, whichever App's it is and wherever it is
        # declared, so no snapshot is refused for it; a name that does not collide stays reserved.
        unreserved = lambda issues, **accounts: (entry_with(issues, **accounts), whos[-1].reserved)
        refused = (refused, {"combsmith-sf-controller[bot]"})
        self.assertEqual(unreserved(ready("combsmith-sf-pr-review")), refused)
        self.assertEqual(unreserved(intent("combsmith-sf-pr-review")), refused)
        self.assertEqual(unreserved(ready("combsmith-sf-queue"), queue=queue), refused)
        self.assertEqual(unreserved(intent("combsmith-sf-queue"), queue=queue), refused)
        self.assertEqual(unreserved(ready("bors"), queue=dict(queue, login="bors[bot]")), refused)
        # A Lens is told by the login the configuration holds for it, and by the name its id is configured under.
        self.assertEqual(unreserved(ready("coderabbitai"), lenses=[other]), refused)
        self.assertEqual(unreserved(intent("coderabbitai"), lenses=[other]), refused)
        self.assertEqual(unreserved(ready("combsmith-sf-pr-review"), lenses=[renamed]), refused)
        self.assertEqual(unreserved(ready("combsmith-sf-pr-review"), lenses=[dict(renamed, lens="coderabbit")]), refused)
        # The queue, and a Lens held under no Role, are told too by the name config/apps.json gives their code, though
        # the login held for each is another.
        self.assertEqual(unreserved(ready("combsmith-sf-queue"), queue=dict(queue, login="an-old-login[bot]")), refused)
        self.assertEqual(unreserved(ready("combsmith-sf-pr-review"), lenses=[dict(renamed, id=5000010)]), refused)
        # The queue's name with no queue App held, and any other App's, are no queue's and no Lens's: the issues are
        # listed from their date, here by a listing that is whole only with no date, so no issue is read and the pull
        # requests are decided, with one entry naming no item (decision 0252).
        for issues, accounts in ((ready("combsmith-sf-queue"), {}), (ready("combsmith-sf-readiness"), {"queue": queue}),
                                 (intent("combsmith-sf-business-analyst"), {})):
            self.assertEqual(entry_with(issues, **accounts),
                             (0, "passed\n", False, [7], [], [{"item": None, "code": "issue_list_unreadable"}],
                              "2026-10-01T00:00:00Z"), issues)

    def test_the_served_issues_writes_are_read_for_reconciliation(self):  # issue 837
        # Each served issue's writes are read by the seen port as an open pull request's are, with nothing kept by a
        # snapshot, whether its facts were read or not. One whose writes cannot be read whole, or not at all, leaves
        # reconciliation short, which says so; it is not owed as a pull request is, since what is owed is read as a pull
        # request that left.
        real, spied, order = entry.configuration, [], []

        def served(root, release):
            found = real(root, release)
            found["kernel"]["issues"]["served_from"] = "2026-10-01T00:00:00Z"
            return found

        def snapshot(transport, repo, number, identities, who, runs_whole, clock, *, kept, with_head, opener, recorded, opened):
            return support.facts(item=dict(support.ITEM, number=number)), "A title", "a" * 40

        def issue_read(transport, repo, number, accounts, clock, *, identities, earlier, kernel, controller, base_head, opener,
                           runs, role):
            if number == 6:
                raise entry.facts_.Moved("moved")
            # Issue 8 is the Controller's tracking issue, told at its own read: it is no served issue, and its writes
            # are not read (decision 0233, as decision 0230 leaves to it).
            if number == 8:
                raise entry.issues_.Tracking("ours")
            return test_issue.facts(item=dict(test_issue.ITEM, repo=repo, number=number), read_at=clock()), "An issue"
        before = json.loads((ROOT / "examples" / "pass.json").read_text())
        before["now"] = "2026-10-12T11:00:00Z"
        before["pull_requests"] = [dict(before["pull_requests"][0], facts=dict(before["pull_requests"][0]["facts"], item=dict(
            before["pull_requests"][0]["facts"]["item"], number=7)))]
        before["reconciled"] = {"runs": [], "passes": [], "keys": [], "items": [], "dispatched": [], "owed": []}
        before["issues"] = []   # none served before: no issue has left (issue 916)

        def entry_with(short=(), unanswered=(), wrote=(), recorded=True):
            del spied[:], order[:]

            def read(transport, item, kept, identities, apps, since):
                spied.append((item, kept, since, identities, apps))
                order.append("seen")
                if item["number"] in unanswered:
                    raise github.Unanswered("no")
                # What a Factory identity wrote on the issue, where the port is handed the identities to tell it by.
                writes = [{"by": by, "kind": "label", "item": dict(item), "key": None, "at": "2026-10-12T11:30:00Z"}
                          for by in set(identities.values()) & set(wrote)] if item["type"] == "issue" else []
                return (writes, [], item["number"] not in short)
            with unittest.mock.patch.object(entry, "configuration", served), \
                    unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                    unittest.mock.patch.object(entry.items, "open_issues", lambda transport, repo, after, **k: (
                        order.append("listed") or [5, 6, 8], True)), \
                    unittest.mock.patch.object(entry.issues_, "read", issue_read), \
                    unittest.mock.patch.object(entry.passes, "records", lambda *a: [before]), \
                    unittest.mock.patch.object(entry.seen_, "read", read), \
                    unittest.mock.patch.object(entry.seen_, "pushes", lambda *a, **k: ([], True)), \
                    unittest.mock.patch.object(entry.applied, "effects", lambda *a, **k: order.append("applied") or {
                        "applied": [], "read": [], "at": {}, "whole": True}), \
                    unittest.mock.patch.object(entry.passes, "written", lambda *a, **k: order.append("passes") or {
                        "written": [], "read": [], "at": {}, "whole": recorded}):
                code, _, files, _ = self.run_entry(Hub(self.table(numbers=[7])))
            self.assertEqual(code, 0)
            return files["pass.json"]
        item = lambda kind, n: {"repo": self.HOME, "type": kind, "number": n}
        record = entry_with()
        self.assertEqual([s[:2] for s in spied], [(item("pull_request", 7), {}), (item("issue", 5), None), (item("issue", 6), None)])
        # The passes' records are read before the issues are listed, for the tracking issue's numbers; the Runs' Effects
        # after every write is seen, as a Run still running may record what it wrote in between (security read).
        self.assertEqual(order, ["passes", "listed", "seen", "seen", "seen", "applied"])
        self.assertEqual({s[2] for s in spied}, {"2026-10-11T06:00:00Z"})
        self.assertNotIn("reconciliation_unreadable", record["alerts"])
        self.assertNotIn("write_unmatched", record["alerts"])
        # An issue's writes are told by the identities and the Apps a pull request's are, and what the port gives of
        # them reaches reconciliation: the Controller's label on a served issue, which no Effect recorded, is the alert,
        # named by the issue's page.
        self.assertEqual([s[3:] for s in spied[1:]], [spied[0][3:]] * 2)
        self.assertEqual(spied[0][3][(CONTROLLER["accounts"]["controller"]["id"], "Bot")], "controller")
        record = entry_with(wrote=("controller",))
        self.assertIn("write_unmatched", record["alerts"])
        self.assertEqual([(e["by"], e["write"], e["item"]) for e in record["reconciliation"]],
                         [("controller", "label", "https://github.com/%s/issues/%d" % (self.HOME, n)) for n in (5, 6)])
        for missed in ({"short": (5,)}, {"unanswered": (5,)}, {"short": (6,)}):
            record = entry_with(**missed)
            self.assertIn("reconciliation_unreadable", record["alerts"], missed)
            self.assertEqual(record["reconciled"]["owed"], [], missed)
        # What an issue read short gives still reaches reconciliation: the Controller's label read before the read fell
        # short is the alert, beside the shortness (Astra).
        record = entry_with(short=(5,), wrote=("controller",))
        self.assertTrue({"write_unmatched", "reconciliation_unreadable"} <= set(record["alerts"]))
        self.assertEqual([e["item"] for e in record["reconciliation"]],
                         ["https://github.com/%s/issues/%d" % (self.HOME, n) for n in (5, 6)])
        # A pull request read short is owed still, and an issue beside it changes nothing of that, read whole, short or
        # unanswered (Astra).
        self.assertEqual(entry_with(short=(7,))["reconciled"]["owed"], [7])
        for missed in ({"short": (7, 5)}, {"short": (7,), "unanswered": (5,)}):
            record = entry_with(**missed)
            self.assertIn("reconciliation_unreadable", record["alerts"], missed)
            self.assertEqual(record["reconciled"]["owed"], [7], missed)
        # While the passes' records are not read whole, the tracking issue's number is not read, and that issue could be
        # among those listed: no issue's writes are read, and reconciliation is short by the records alone (issue 901).
        record = entry_with(recorded=False)
        self.assertEqual([s[0] for s in spied], [item("pull_request", 7)])
        self.assertIn("reconciliation_unreadable", record["alerts"])

    def test_an_issue_that_left_is_read_with_its_close_and_one_read_short_is_owed(self):  # issue 916, decision 0235
        # Issue 41 was served by the pass before and is no longer listed: it has left, closed between the passes, and
        # its writes are read as a pull request's that left are, with its close. A Factory label on it, or its close,
        # that no Effect recorded is the alert. Read whole, it is kept as left, stamped, and read as gone while the
        # window holds it; read short, it is owed to the next pass. Where the issues were not listed, every issue served
        # or owed before is owed again, and reconciliation is short.
        real, spied = entry.configuration, []

        def served(root, release):
            found = real(root, release)
            found["kernel"]["issues"]["served_from"] = "2026-10-01T00:00:00Z"
            return found

        def off(root, release):
            found = real(root, release)
            found["kernel"]["issues"]["served_from"] = None
            return found

        def snapshot(transport, repo, number, identities, who, runs_whole, clock, *, kept, with_head, opener, recorded, opened):
            return support.facts(item=dict(support.ITEM, number=number)), "A title", "a" * 40

        failing = []
        told = []

        def issue_read(transport, repo, number, accounts, clock, *, identities, **_):
            if number in failing:
                raise github.Unanswered("no")
            if number in told:
                raise entry.issues_.Tracking("told at its own read")
            return test_issue.facts(item=dict(test_issue.ITEM, repo=repo, number=number), read_at=clock()), "An issue"
        example = json.loads((ROOT / "examples" / "pass.json").read_text())
        example["pull_requests"] = [dict(example["pull_requests"][0], facts=dict(example["pull_requests"][0]["facts"],
                                                                                 item=dict(example["pull_requests"][0]["facts"]["item"], number=7)))]
        held, handed, probes = {"runs": [], "passes": [], "keys": [], "items": [], "dispatched": [], "owed": []}, [], []

        def entry_with(before, short=(), wrote=(), recorded=True, serving="2026-10-01T00:00:00Z", listing=(5,), tracked=(),
                       unanswered=(), ended=(), repo=True, whole=True):
            del spied[:], handed[:], probes[:]
            answers = list(repo) if isinstance(repo, tuple) else None

            def probe(transport, home):
                probes.append(home)
                return answers.pop(0) if answers is not None else repo
            tracking = [{"schema": "written/1", "pass": "p_01JA7Q", "release": "factory/v0.3.1",
                         "writes": [{"id": "w%d" % n, "type": "tracking_issue", "item": None, "run": None,
                                     "state": "already_applied", "key": str(n), "reason": None} for n in tracked]}]
            dated = lambda root, release: dict(served(root, release)) if serving else off(root, release)

            def read(transport, item, kept, identities, apps, since, **kw):
                spied.append((item["type"], item["number"], kept))
                handed.append((item["number"], dict(kw, told="told") if "told" in kw else kw))
                if item["number"] in unanswered:
                    raise github.Unanswered("no")
                if item["number"] in ended:
                    # As the port does: whole only where the repo was read, and then told with its answer.
                    if kw["repo_read"]:
                        kw["told"].append({"item": dict(item), "answer": 404})
                    return ([], [], kw["repo_read"])
                writes = [{"by": by, "kind": kind, "item": dict(item), "key": None, "at": "2026-10-12T11:30:00Z"}
                          for by in set(identities.values()) & set(wrote) for kind in ("label", "close")] \
                    if item["type"] == "issue" and kept is not None else []
                return (writes, [], item["number"] not in short)
            with unittest.mock.patch.object(entry, "configuration", dated), \
                    unittest.mock.patch.object(entry.seen_, "repo_read", probe), \
                    unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                    unittest.mock.patch.object(entry.items, "open_issues", lambda transport, repo, after, **k: ([n for n in listing if n not in k.get("apart", ())] if after else [], whole)), \
                    unittest.mock.patch.object(entry.issues_, "read", issue_read), \
                    unittest.mock.patch.object(entry.passes, "records", lambda *a: [before]), \
                    unittest.mock.patch.object(entry.seen_, "read", read), \
                    unittest.mock.patch.object(entry.seen_, "pushes", lambda *a, **k: ([], True)), \
                    unittest.mock.patch.object(entry.applied, "effects",
                                               lambda *a, **k: {"applied": [], "read": [], "at": {}, "whole": True}), \
                    unittest.mock.patch.object(entry.passes, "written",
                                               lambda *a, **k: {"written": tracking if tracked else [], "read": [], "at": {},
                                                                "whole": recorded}):
                code, _, files, _ = self.run_entry(Hub(self.table(numbers=[7])))
            self.assertEqual(code, 0)
            return files["pass.json"]
        issue = lambda n: dict(example["issues"][0], facts=dict(example["issues"][0]["facts"],
                                                                item=dict(example["issues"][0]["facts"]["item"], number=n)))
        before = dict(example, now="2026-10-12T11:00:00Z", issues=[issue(5), issue(41)], left_out=[], reconciled=dict(held))
        record = entry_with(before)
        self.assertEqual([s for s in spied if s[0] == "issue"], [("issue", 5, None), ("issue", 41, entry.seen_.LEFT)])
        self.assertEqual((record["reconciled"]["left_issues"], "owed_issues" in record["reconciled"]),
                         ([{"number": 41, "at": record["now"]}], False))
        self.assertNotIn("reconciliation_unreadable", record["alerts"])
        # The Controller's label on it, and its close, which no Effect recorded, are the alert.
        record = entry_with(before, wrote=("controller",))
        self.assertIn("write_unmatched", record["alerts"])
        self.assertEqual(sorted({e["write"] for e in record["reconciliation"]}), ["close", "label"])
        # One a pass before left out unread is served by it, and is read as left too.
        unread = dict(before, issues=[issue(5)], left_out=[{"item": issue(41)["facts"]["item"], "code": "facts_unanswered"}])
        entry_with(unread)
        self.assertIn(("issue", 41, entry.seen_.LEFT), spied)
        # Read short, it is owed as well as kept as left, as a pull request is, and reconciliation is short; the next pass
        # reads it again, as gone while the window holds its stamp, or as left where only owed.
        record = entry_with(before, short=(41,))
        self.assertEqual((record["reconciled"]["owed_issues"], record["reconciled"]["left_issues"]),
                         ([41], [{"number": 41, "at": record["now"]}]))
        self.assertIn("reconciliation_unreadable", record["alerts"])
        owing = dict(before, issues=[issue(5)], reconciled=dict(held, owed_issues=[41]))
        entry_with(owing)
        self.assertIn(("issue", 41, entry.seen_.LEFT), spied)
        # Kept as left inside the window, it is read as gone; past the window it is read no more.
        kept = dict(before, issues=[issue(5)], reconciled=dict(held, left_issues=[{"number": 41, "at": "2026-10-12T10:00:00Z"}]))
        record = entry_with(kept)
        self.assertIn(("issue", 41, entry.seen_.GONE), spied)
        self.assertEqual(record["reconciled"]["left_issues"], [{"number": 41, "at": "2026-10-12T10:00:00Z"}])
        old = dict(kept, reconciled=dict(held, left_issues=[{"number": 41, "at": "2026-10-01T10:00:00Z"}]))
        record = entry_with(old)
        self.assertEqual([s for s in spied if s[1] == 41], [])
        self.assertNotIn("left_issues", record["reconciled"])
        # The issues not listed, for want of the tracking issue's number: every issue served, owed or kept as left before
        # is owed again, none is read, and reconciliation is short.
        both = dict(before, reconciled=dict(held, owed_issues=[9], left_issues=[{"number": 12, "at": "2026-10-12T10:00:00Z"}]))
        record = entry_with(both, recorded=False)
        self.assertEqual([s for s in spied if s[0] == "issue"], [])
        self.assertEqual(record["reconciled"]["owed_issues"], [5, 9, 12, 41])
        self.assertIn("reconciliation_unreadable", record["alerts"])
        # So with issues served no more, its records read whole: the issues served before are owed, and it is short.
        record = entry_with(before, serving=None)
        self.assertEqual((record["reconciled"]["owed_issues"], [s for s in spied if s[0] == "issue"]), ([5, 41], []))
        self.assertIn("reconciliation_unreadable", record["alerts"])
        # And with nothing served before or owed there is nothing to owe, and nothing short.
        record = entry_with(dict(before, issues=[]), serving=None)
        self.assertNotIn("owed_issues", record["reconciled"])
        self.assertNotIn("reconciliation_unreadable", record["alerts"])
        # So with the issue list read short: no issue that left can be told, and one it listed is no tracking issue, so
        # every issue served before is owed, none is read, and reconciliation is short (decision 0252).
        record = entry_with(before, listing=(41,), whole=False)
        self.assertEqual((record["reconciled"]["owed_issues"], [s for s in spied if s[0] == "issue"]), ([5, 41], []))
        self.assertIn("reconciliation_unreadable", record["alerts"])
        # The tracking issue, left out unread by a pass that could not tell it, is never read as one that left (Claude).
        record = entry_with(dict(before, left_out=[{"item": issue(9)["facts"]["item"], "code": "facts_unanswered"}]),
                            tracked=(9,), listing=(5, 9))
        self.assertEqual([s for s in spied if s[1] == 9], [])
        self.assertNotIn("owed_issues", record["reconciled"])
        # Nor where no record numbers it and its own read tells it, listed again (codex).
        told.append(9)
        record = entry_with(dict(before, left_out=[{"item": issue(9)["facts"]["item"], "code": "facts_unanswered"}]),
                            listing=(5, 9))
        del told[:]
        self.assertEqual(([s for s in spied if s[1] == 9], "owed_issues" in record["reconciled"]), ([], False))
        # Owed, or kept as left, by a pass that could not tell it, it is never read as left either (Muse).
        for held_ in (dict(held, owed_issues=[9]), dict(held, left_issues=[{"number": 9, "at": "2026-10-12T10:00:00Z"}])):
            record = entry_with(dict(before, reconciled=held_), tracked=(9,), listing=(5, 9))
            self.assertEqual(([s for s in spied if s[1] == 9], "owed_issues" in record["reconciled"]), ([], False), held_)
        # Owed and listed again, it is read once, as served (Muse).
        entry_with(dict(before, issues=[issue(5)], reconciled=dict(held, owed_issues=[41])), listing=(5, 41))
        self.assertEqual([s for s in spied if s[1] == 41], [("issue", 41, None)])
        # Owed and stamped inside the window, it is read once, as gone: read short it stays owed, read whole the debt is
        # paid and the stamp kept; a write on it then is still the alert (Claude, Astra).
        both = dict(before, issues=[issue(5)], reconciled=dict(held, owed_issues=[41],
                                                               left_issues=[{"number": 41, "at": "2026-10-12T10:00:00Z"}]))
        record = entry_with(both, short=(41,))
        self.assertEqual([s for s in spied if s[1] == 41], [("issue", 41, entry.seen_.GONE)])
        self.assertEqual(record["reconciled"]["owed_issues"], [41])
        record = entry_with(both, wrote=("controller",))
        self.assertEqual((record["reconciled"]["left_issues"], "owed_issues" in record["reconciled"]),
                         ([{"number": 41, "at": "2026-10-12T10:00:00Z"}], False))
        self.assertIn("write_unmatched", record["alerts"])
        # Owed with its stamp past the window, it is read as left again and stamped anew, never dropped unread (Kimi).
        stale = dict(both, reconciled=dict(held, owed_issues=[41], left_issues=[{"number": 41, "at": "2026-10-01T10:00:00Z"}]))
        record = entry_with(stale)
        self.assertEqual([s for s in spied if s[1] == 41], [("issue", 41, entry.seen_.LEFT)])
        self.assertEqual(record["reconciled"]["left_issues"], [{"number": 41, "at": record["now"]}])
        # Served again after its stamp, reopened, and closed once more, it is read as left with its new close and stamped
        # anew (security); listed again, it is read once, as served (Claude).
        reopened = dict(before, reconciled=dict(held, left_issues=[{"number": 41, "at": "2026-10-12T10:00:00Z"}]))
        record = entry_with(reopened)
        self.assertEqual([s for s in spied if s[1] == 41], [("issue", 41, entry.seen_.LEFT)])
        self.assertEqual(record["reconciled"]["left_issues"], [{"number": 41, "at": record["now"]}])
        served_again = entry_with(reopened, listing=(5, 41))
        self.assertEqual([s for s in spied if s[1] == 41], [("issue", 41, None)])
        # Served again, it keeps no stamp, so a pass between that cannot list the issues owes it, and the next reads it as
        # left with its new close, stamped anew (Kimi, Astra).
        self.assertNotIn("left_issues", served_again["reconciled"])
        unlisted = entry_with(dict(served_again, now="2026-10-12T11:00:00Z"), serving=None)
        record = entry_with(dict(unlisted, now="2026-10-12T11:00:00Z"))
        self.assertEqual([s for s in spied if s[1] == 41], [("issue", 41, entry.seen_.LEFT)])
        self.assertEqual(record["reconciled"]["left_issues"], [{"number": 41, "at": record["now"]}])
        # So too where it was listed but its own read failed, and it was left out unread (Claude).
        failing.append(41)
        left_unread = entry_with(reopened, listing=(5, 41))
        del failing[:]
        self.assertEqual(([e["code"] for e in left_unread["left_out"]], "left_issues" in left_unread["reconciled"]),
                         (["facts_unanswered"], False))
        # Not listed, a stamp past the window is owed no more (Claude).
        record = entry_with(dict(before, issues=[], reconciled=dict(held, left_issues=[{"number": 41, "at": "2026-10-01T10:00:00Z"}])),
                            serving=None)
        self.assertNotIn("owed_issues", record["reconciled"])
        # An open issue served now and read short is not owed: the next pass reads it as served, or as left.
        record = entry_with(before, short=(5,))
        self.assertEqual(("owed_issues" in record["reconciled"], "reconciliation_unreadable" in record["alerts"]), (False, True))
        # One served before and one owed, both gone from the listing, are each read as left in the same pass (Astra).
        record = entry_with(dict(before, reconciled=dict(held, owed_issues=[9])))
        self.assertEqual([s for s in spied if s[0] == "issue"], [("issue", 5, None), ("issue", 9, entry.seen_.LEFT),
                                                                  ("issue", 41, entry.seen_.LEFT)])
        # Read short with a write on it, the write still reaches reconciliation, and the issue is owed (Astra).
        record = entry_with(before, short=(41,), wrote=("controller",))
        self.assertEqual((record["reconciled"]["owed_issues"], "write_unmatched" in record["alerts"]), ([41], True))
        self.assertEqual(sorted(e["write"] for e in record["reconciliation"] if e["item"].endswith("/issues/41")), ["close", "label"])
        # Its read not answered, as left or as gone, it is owed, and reconciliation is short (Kimi).
        for start in (before, kept):
            record = entry_with(start, unanswered=(41,))
            self.assertEqual((record["reconciled"]["owed_issues"], "reconciliation_unreadable" in record["alerts"]), ([41], True))
        # A second pass with the issues still not listed keeps owing it, and stays short (Astra).
        first = entry_with(before, serving=None)
        record = entry_with(dict(first, now=before["now"], issues=[], left_out=[]), serving=None)
        self.assertEqual((record["reconciled"]["owed_issues"], "reconciliation_unreadable" in record["alerts"]), ([5, 41], True))
        # The repo is read once for the issues that left, before their reads, and handed to each of them, never to an open
        # one's; one not found ends whole where the repo was read, named once as information, the repo read once more
        # after them; it is owed where the repo was not read, before or after (decision 1145).
        gone = lambda n: {"alert": "issue_gone", "by": None, "write": "other", "key": "404",
                          "item": "https://github.com/%s/issues/%d" % (self.HOME, n)}
        record = entry_with(before)
        self.assertEqual((probes, handed), ([self.HOME], [(7, {}), (5, {}), (41, {"repo_read": True, "told": "told"})]))
        record = entry_with(before, ended=(41,))
        self.assertEqual((probes, handed), ([self.HOME] * 2, [(7, {}), (5, {}), (41, {"repo_read": True, "told": "told"})]))
        self.assertEqual(("owed_issues" in record["reconciled"], record["alerts"], record["reconciliation"]), (False, [], [gone(41)]))
        record = entry_with(kept, ended=(41,))
        self.assertEqual(("owed_issues" in record["reconciled"], record["reconciliation"], len(probes)), (False, [gone(41)], 2))
        two = dict(before, reconciled=dict(held, owed_issues=[9]))
        record = entry_with(two, ended=(9, 41))
        self.assertEqual((record["reconciliation"], len(probes)), ([gone(9), gone(41)], 2))
        for start in (before, kept):
            # Not read before the reads, the issue is owed whatever a later read of the repo answers (Carbon).
            for repo in (False, (True, False), (False, True)):
                record = entry_with(start, ended=(41,), repo=repo)
                self.assertEqual((record["reconciled"]["owed_issues"], "reconciliation_unreadable" in record["alerts"],
                                  record["reconciliation"]), ([41], True, []), repo)
        # Nothing left, nothing kept as left: the repo is not read.
        entry_with(dict(before, issues=[issue(5)]))
        self.assertEqual(probes, [])

    def test_an_issue_whose_linked_pull_requests_were_not_read_defers_through_the_entry(self):  # S3, Astra
        # Through the real port: an issue that read whole would be accepted defers while its linked pull requests are read
        # short.
        from tests.test_adapters import issue_read, linked_read, passes_listed
        reads_ = issue_read()
        own, events, edits = (r["response"] for r in reads_[:3])
        edits["body"]["data"]["repository"]["nameWithOwner"] = self.HOME
        named = [linked_read(total=1, repo=self.HOME)["response"]]
        # The Controller's tracking issue, 8, is open and updated since `served_from`, so GitHub lists it: it is left out
        # by the number the pass before recorded writing it under, never read, and the list is still whole (issue 901).
        listed = {"data": {"repository": {"nameWithOwner": self.HOME, "issues": {
            "totalCount": 2, "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [{"number": 8}, {"number": 41}]}}}}
        wrote = {"id": "w1", "type": "tracking_issue", "item": None, "run": None, "state": "applied", "key": "8", "reason": None}
        written = {"written": [{"schema": "written/1", "pass": "p_01JA7Q", "release": "factory/v0.3.1", "writes": [wrote]}],
                   "read": [{"id": 41, "attempt": 1}], "at": {}, "whole": True}
        real = entry.configuration

        def served(root, release):
            found = real(root, release)
            found["kernel"]["issues"] = dict(found["kernel"]["issues"], served_from="2026-10-01T00:00:00Z",
                                             label_apps={"factory:triage": found["apps"]["controller"]["name"], "factory:ready": None})
            return found

        table = self.table(numbers=[])
        table.update({("GET", "/repos/%s/issues/41" % self.HOME): own,
                      ("GET", "/repos/%s/issues/41/timeline?per_page=100" % self.HOME): events,
                      ("GET", "/repos/%s/collaborators/don-petry/permission" % self.HOME):
                          {"status": 200, "headers": {}, "body": {"permission": "admin"}}})
        hub = Hub(table)
        connect = hub.connect

        def routed(credential):
            through = connect(credential)

            class Routed:
                def send(self, req):
                    query = (req.get("body") or {}).get("query", "") if req["path"] == "/graphql" else ""
                    if query.startswith(("query OpenIssues", "query IssueEdits", "query IssueLinked")):
                        hub.sent.append((credential, req))
                        if "IssueLinked" in query:
                            return copy.deepcopy(named[0])
                        return copy.deepcopy({"status": 200, "headers": {}, "body": listed} if "OpenIssues" in query else edits)
                    return through.send(req)
            return Routed()
        hub.connect = routed
        with unittest.mock.patch.object(entry, "configuration", served), \
                unittest.mock.patch.object(entry.passes, "written", lambda *a, **k: written):
            code, printed, files, _ = self.run_entry(hub)
        self.assertEqual((code, printed), (0, "passed\n"))
        self.assertEqual((files["pass.json"]["left_out"], [r["path"] for _, r in hub.sent if r["path"].endswith("/issues/8")]), ([], []))
        (decided,) = files["pass.json"]["issues"]
        d = decided["decision"]
        self.assertEqual((d["item"]["number"], d["outcome"], d["reason"], d["evidence"]), (41, "defer", "facts_incomplete", ["linked"]))
        # Nothing is written for the issue: the one write is the tracking issue's, which reports the pass's alerts.
        self.assertEqual([w["type"] for w in files["writes.json"]["writes"]], ["tracking_issue"])
        # Read whole, with records holding nothing of it: whole, and accepted.
        named[0] = linked_read(repo=self.HOME)["response"]
        hub.sent.clear()
        with unittest.mock.patch.object(entry, "configuration", served), \
                unittest.mock.patch.object(entry.passes, "written", lambda *a, **k: written):
            code, _, files, _ = self.run_entry(hub)
        (decided,) = files["pass.json"]["issues"]
        self.assertEqual((code, decided["decision"]["outcome"], decided["decision"].get("action")), (0, "act", "accept"))
        # No record in the window numbers it, as for a tracking issue open longer than the window: the real port reads
        # issue 8 once, sees the Controller's App opened it with the body the write step writes, and asks nothing more
        # of it. It is neither decided nor left out, and the issue beside it is (decision 0233).
        app = CONTROLLER["accounts"]["controller"]
        body = effects.rendered({"pass": "p_01JA7Q", "now": "2026-10-12T11:00:00Z", "release": "factory/v0.3.1"},
                                 ["write_failed"])
        hub.table[("GET", "/repos/%s/issues/8" % self.HOME)] = dict(own, body=dict(
            own["body"], number=8, body=body, user={"login": app["login"], "id": app["id"], "type": app["type"]}))
        hub.sent.clear()
        with unittest.mock.patch.object(entry, "configuration", served), \
                unittest.mock.patch.object(entry.passes, "written", lambda *a, **k: dict(written, written=[])):
            code, _, files, _ = self.run_entry(hub)
        self.assertEqual((code, files["pass.json"]["left_out"], [d["decision"]["item"]["number"] for d in files["pass.json"]["issues"]]),
                         (0, [], [41]))
        self.assertEqual([r["path"] for _, r in hub.sent if "/issues/8" in r["path"]], ["/repos/%s/issues/8" % self.HOME])
        # With the records not read, the list short, it defers (issue 734).
        hub.table[("GET", passes_listed([])["request"]["call"].split()[1])] = passes_listed([], total=1)["response"]
        with unittest.mock.patch.object(entry, "configuration", served), \
                unittest.mock.patch.object(entry.passes, "written", lambda *a, **k: written):
            code, _, files, _ = self.run_entry(hub)
        (decided,) = files["pass.json"]["issues"]
        d = decided["decision"]
        self.assertEqual((code, d["outcome"], d["reason"], d["evidence"]), (0, "defer", "facts_incomplete", ["linked"]))

    def test_no_served_issues_runs_are_asked_when_they_began(self):  # issue 836, decision 0231
        # With issues served, the entry still hands the records port the open pull requests alone: no issue rule reads
        # when a Run began, so an issue's Runs spend none of the port's bound. The passes' records are read whole and
        # name no tracking issue, so every issue listed is read (issue 901).
        real, handed, listed = entry.configuration, [], entry.records.runs

        def served(root, release):
            found = real(root, release)
            found["kernel"]["issues"]["served_from"] = "2026-10-01T00:00:00Z"
            return found

        def snapshot(transport, repo, number, identities, who, runs_whole, clock, *, kept, with_head, opener, recorded, opened):
            return support.facts(item=dict(support.ITEM, number=number)), "A title", "a" * 40

        def issue_read(transport, repo, number, accounts, clock, *, identities, earlier, kernel, controller, base_head, opener,
                           runs, role):
            return test_issue.facts(item=dict(test_issue.ITEM, repo=repo, number=number), read_at=clock()), "An issue"

        def runs(*args, **kw):
            handed.append(kw["of"])
            return listed(*args, **kw)
        with unittest.mock.patch.object(entry, "configuration", served), \
                unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                unittest.mock.patch.object(entry.items, "open_issues", lambda transport, repo, after, **k: ([5, 6], True)), \
                unittest.mock.patch.object(entry.issues_, "read", issue_read), \
                unittest.mock.patch.object(entry.passes, "written", lambda *a, **k: {"written": [], "read": [], "at": {}, "whole": True}), \
                unittest.mock.patch.object(entry.records, "runs", runs):
            code, _, files, _ = self.run_entry(Hub(self.table(numbers=[7])))
        self.assertEqual((code, handed), (0, [[{"repo": self.HOME, "type": "pull_request", "number": 7}]]))
        self.assertEqual([e["decision"]["item"]["number"] for e in files["pass.json"]["issues"]], [5, 6])

    def test_nothing_is_owed_for_an_issue_that_moved(self):  # issue 839, decision 0229
        # A pull request that moved once has its writes owed to the next pass. An issue that moved is graced too, and
        # owes nothing: the entry reads no writes by an issue's facts. So a moved issue of a served pull request's
        # number leaves that pull request's writes read, and nothing owed.
        real, spied = entry.configuration, []

        def served(root, release):
            found = real(root, release)
            found["kernel"]["issues"]["served_from"] = "2026-10-01T00:00:00Z"
            return found

        def snapshot(transport, repo, number, identities, who, runs_whole, clock, *, kept, with_head, opener, recorded, opened):
            return support.facts(item=dict(support.ITEM, number=number)), "A title", "a" * 40

        def moved(transport, repo, number, accounts, clock, *, identities, earlier, kernel, controller, base_head, opener,
                      runs, role):
            raise entry.facts_.Moved("moved")

        def read(transport, item, kept, identities, apps, since, **_):
            spied.append(item)
            return ([], [], True)
        before = json.loads((ROOT / "examples" / "pass.json").read_text())
        before["now"] = "2026-10-12T11:00:00Z"
        before["pull_requests"] = [dict(before["pull_requests"][0], facts=dict(before["pull_requests"][0]["facts"], item=dict(
            before["pull_requests"][0]["facts"]["item"], number=7)))]
        before["reconciled"] = {"runs": [], "passes": [], "keys": [], "items": [], "dispatched": [], "owed": []}
        before["left_out"] = []
        with unittest.mock.patch.object(entry, "configuration", served), \
                unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                unittest.mock.patch.object(entry.items, "open_issues", lambda transport, repo, after, **k: ([7], True)), \
                unittest.mock.patch.object(entry.issues_, "read", moved), \
                unittest.mock.patch.object(entry.passes, "records", lambda *a: [before]), \
                unittest.mock.patch.object(entry.seen_, "read", read), \
                unittest.mock.patch.object(entry.seen_, "pushes", lambda *a, **k: ([], True)), \
                unittest.mock.patch.object(entry.applied, "effects",
                                           lambda *a, **k: {"applied": [], "read": [], "at": {}, "whole": True}), \
                unittest.mock.patch.object(entry.passes, "written",
                                           lambda *a, **k: {"written": [], "read": [], "at": {}, "whole": True}):
            code, _, files, _ = self.run_entry(Hub(self.table(numbers=[7])))
        record = files["pass.json"]
        self.assertEqual((code, record["alerts"]), (0, []))
        self.assertEqual(record["left_out"], [{"item": {"repo": self.HOME, "type": "issue", "number": 7}, "code": "pull_moved"}])
        self.assertIn({"repo": self.HOME, "type": "pull_request", "number": 7}, spied)
        self.assertEqual(record["reconciled"]["owed"], [])

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
        # The run records are read after that list, for the port is handed its items: here they are not read at all.
        self.assertEqual([r["path"] for _, r in hub.sent if "/actions/workflows/run.yml/runs" in r["path"]], [])
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

    def test_each_stage_of_a_pass_is_timed_in_the_log_alone_and_times_no_read_differently(self):  # issue 1025
        # The Solution Architect's ruling: one JSON line a stage on standard error, its name, seconds and whole-number
        # counts, and nothing in the pass record. The wait is timed apart from the reads, and the poller's list apart
        # from its artifacts, the gone pull requests' reads from the open ones', the carry and the record's check apart.
        def entered(**given):
            hub = Hub(self.table(numbers=[7]))
            with unittest.mock.patch.object(entry, "mint_id", lambda prefix: prefix + "_" + "A" * 20):
                code, printed, files, slept = self.run_entry(hub, **given)
            return code, printed, files, [(c, r["method"], r["path"]) for c, r in hub.sent], self.said
        code, printed, files, sent, said = entered()
        self.assertEqual((code, printed), (0, "passed\n"))
        lines = [json.loads(line) for line in said.getvalue().splitlines()]
        stages = [line["stage"] for line in lines]
        self.assertLessEqual({"records_before", "wait", "pull_request_list", "runs", "lens_records", "open_pull_requests",
                              "seen_open", "seen_pushes", "poller_list", "issue_list", "pause", "decide", "write"}, set(stages))
        self.assertLess(stages.index("wait"), stages.index("pull_request_list"))
        self.assertEqual(stages.count("decide"), 1)
        self.assertEqual(len(stages), len(set(stages)))
        # The wait is timed as it was, the timer read once at each end of it: a second on.
        self.assertEqual(lines[stages.index("wait")]["seconds"], 1.0)
        # The pass times nothing itself: its carry's rebuild and record's check are in "decide", the carry's size beside.
        carried = ("hand", "taken", "runs", "passes", "keys", "items", "dispatched", "owed", "left", "owed_issues",
                   "left_issues", "hands")
        decided, held = lines[stages.index("decide")], files["pass.json"]["reconciled"]
        self.assertEqual({k: decided[k] for k in carried if k in decided}, {k: len(held[k]) for k in carried if k in held})
        # Each by its name, the issues' and the hands' among them.
        full = {k: [{"number": 1}] * (n + 1) for n, k in enumerate(carried)}
        self.assertEqual(entry.Stages().carried({"reconciled": dict(full, other=[1])}), {k: len(full[k]) for k in carried})
        for line in lines:
            # Its name, its seconds and its counts, each a number this module made: nothing from outside.
            self.assertTrue(set(line) <= {"stage", "seconds", "count"} | set(carried), line)
            self.assertTrue(all(type(v) is int for k, v in line.items() if k not in ("stage", "seconds")), line)
            self.assertEqual(type(line["seconds"]), float, line)
        self.assertEqual(dict((l["stage"], l.get("count")) for l in lines)["pull_request_list"], 1)
        # Not in the record: the pass record and the plan are those of a pass with no timer, read for read, in order,
        # and that pass says nothing; one whose timer gives no number says each stage with no seconds.
        quiet = entered(quiet=True)
        self.assertEqual(quiet[:4], (code, printed, files, sent))
        self.assertEqual(quiet[4].getvalue(), "")
        for odd in (None, 10 ** 400, float("inf"), float("nan"), "1"):
            numbered = entered(timer=lambda odd=odd: odd)
            self.assertEqual(numbered[:4], (code, printed, files, sent), odd)
            self.assertEqual({json.loads(line)["seconds"] for line in numbered[4].getvalue().splitlines()}, {None}, odd)
        # A timer that fails, or a stream that does, says less and fails nothing.
        def broken():
            raise OSError("no clock")

        class Closed:
            def write(self, text):
                raise OSError("closed")

            def flush(self):
                raise OSError("closed")
        failing = entered(timer=broken)
        self.assertEqual(failing[:4], (code, printed, files, sent))
        self.assertEqual({json.loads(line)["seconds"] for line in failing[4].getvalue().splitlines()}, {None})
        self.assertEqual(entered(err=Closed())[:4], (code, printed, files, sent))

    def test_the_open_pull_requests_are_read_four_at_once_and_kept_in_the_listed_order(self):  # decision 1138
        # By default four snapshots at once and no more, the record the one read one at a time writes, in the listed
        # order though the first listed ends last; one login asked once. Threads wait on each other; the one bounded
        # wait is for a fifth that never comes.
        numbers, login, rate = [3, 5, 7, 9, 11, 13], "alice", {"status": 403, "headers": {"x-ratelimit-remaining": "0"}}
        pulls = {n: "/repos/%s/pulls/%d" % (self.HOME, n) for n in numbers}
        permission = "/repos/%s/collaborators/%s/permission" % (self.HOME, login)

        def in_pass():
            frame = sys._getframe()     # the pass's thread alone has run_entry on its stack
            while frame is not None and frame.f_code.co_name != "run_entry":
                frame = frame.f_back
            return frame is not None

        def once(future):
            with contextlib.suppress(concurrent.futures.InvalidStateError):
                future.set_result(None)

        def entered(pool, limited=None):
            table = self.table(numbers=numbers)
            for n in numbers:
                table[("GET", pulls[n])] = dict(rate, body=None) if limited == pulls[n] else {"status": 200, "headers": {},
                                                                                             "body": {}}
            table[("GET", permission)] = dict(rate, body=None) if limited == permission else {
                "status": 200, "headers": {}, "body": {"permission": "read", "user": {"login": login, "id": 1001,
                                                                                    "type": "User"}}}
            hub, live, ended, read = Hub(table), [], [], {}
            four, five, nine, rest = (concurrent.futures.Future() for _ in range(4))

            def snapshot(transport, repo, number, identities, who, runs_whole, clock, *, kept, with_head, opener, recorded,
                         opened):
                live.append(number)
                at, worker = live.index(number) + 1, not in_pass()     # how many live before it, and it
                read.setdefault(number, []).append((at, not worker))
                try:
                    once(five) if at >= 5 else None
                    if worker and not four.done():
                        once(four) if at >= 4 else None
                        four.result(timeout=10)
                        with contextlib.suppress(concurrent.futures.TimeoutError):
                            five.result(timeout=0.3)    # a fifth thread, were there one, begins
                    if worker and number != 9:
                        nine.result(timeout=10)         # the fourth listed reads first
                    if worker and number == 3 and limited is None:
                        rest.result(timeout=10)         # the first listed ends last
                    transport.send({"method": "GET", "path": pulls[number], "accept": "application/json", "body": None})
                    who.typed(login, 1001)              # reads on past a failed ask
                    return support.facts(item=dict(support.ITEM, number=number)), "A title", "a" * 40
                finally:
                    live.remove(number)
                    ended.append(number)
                    once(nine) if number == 9 else None
                    once(rest) if len(ended) == 5 else None
            minted = iter(range(10 ** 6))
            with unittest.mock.patch.object(entry.facts_, "snapshot", snapshot), \
                    unittest.mock.patch.object(entry, "mint_id", lambda prefix: "%s_%020d" % (prefix, next(minted))):
                code, _, files, _ = self.run_entry(hub, pool=pool)
            self.assertEqual(code, 0)
            asked = {path: [r["path"] for _, r in hub.sent].count(path) for path in (permission, pulls[9])}
            return files["pass.json"], read, asked
        one, read, asked = entered(1)
        self.assertEqual((read, asked[permission]), ({n: [(1, True)] for n in numbers}, 1))
        four, read, asked = entered(None)
        self.assertEqual((four, asked[permission]), (one, 1))
        self.assertEqual([e["facts"]["item"]["number"] for e in four["pull_requests"]], numbers)
        self.assertEqual((max(at for n in numbers for at, _ in read[n]), {here for n in numbers for _, here in read[n]}),
                         (4, {False}))
        # A rate limit to a snapshot's read or its account reader's, even read on, leaves that one alone out, sent once;
        # the two not begun then are read after, one at a time, in the pass's own thread.
        for limited in (pulls[9], permission):
            out, read, asked = entered(None, limited)
            self.assertEqual([e for e in out["left_out"] if e.get("code") == "facts_unanswered"],
                             [{"item": dict(support.ITEM, number=9), "code": "facts_unanswered"}], limited)
            self.assertEqual([e["facts"]["item"]["number"] for e in out["pull_requests"]], [3, 5, 7, 11, 13], limited)
            self.assertEqual(asked[limited], 1, limited)
            self.assertEqual(sorted(read[n][0][0] for n in (3, 5, 7, 9)), [1, 2, 3, 4], limited)
            self.assertEqual({n: read[n] for n in (11, 13)}, {11: [(1, True)], 13: [(1, True)]}, limited)

    def test_a_rate_limit_is_a_429_or_a_403_with_no_request_left_or_a_time_to_wait(self):  # decision 1138
        def answer(status, **headers):
            return {"status": status, "headers": headers, "body": None}
        for limited in (answer(429), answer(403, **{"x-ratelimit-remaining": "0"}), answer(403, **{"retry-after": "60"})):
            self.assertTrue(entry.rate_limited(limited), limited)
        for other in (answer(403), answer(403, **{"x-ratelimit-remaining": "1"}), answer(200, **{"retry-after": "60"}),
                      answer(404, **{"x-ratelimit-remaining": "0"}), {"status": 403, "headers": None}, None, "403"):
            self.assertFalse(entry.rate_limited(other), other)

    def test_the_writes_seen_and_the_recorded_effects_are_timed_by_what_they_read(self):  # issue 1025
        # Open, newly left and gone pull requests, each apart; each port's list apart from its artifacts, and each port
        # whole, its wait included, said as it ends.
        config = entry.configuration(ROOT, "factory/v0.3.1")
        now = "2026-10-12T12:00:00Z"
        before = [{"pull_requests": [{"facts": {"item": {"number": 5}}}, {"facts": {"item": {"number": 7}}}],
                   "reconciled": {"runs": [], "passes": [], "keys": [], "items": [], "dispatched": [], "owed": [],
                                  "left": [{"number": 9, "at": now}, {"number": 11, "at": now}]}}]
        said = io.StringIO()
        stages = entry.Stages(ticking(), said)
        with unittest.mock.patch.object(entry.seen_, "read", lambda *a: ([], [], True)), \
                unittest.mock.patch.object(entry.seen_, "pushes", lambda *a, **k: ([], True)):
            entry.writes_seen(None, config, [7, 8], {}, before, "2026-10-11T06:00:00Z", lambda: self.CLOCK, (), stages,
                              [3])
        lines = [json.loads(line) for line in said.getvalue().splitlines()]
        # Each read is a second, by the ticking timer: two open, one newly left, two gone, one served issue (issue 837).
        self.assertEqual([(l["stage"], l.get("count"), l["seconds"]) for l in lines],
                         [("seen_open", 2, 2.0), ("seen_left", 1, 1.0), ("seen_gone", 2, 2.0), ("seen_issues", 1, 1.0),
                          ("seen_pushes", None, 1.0)])

        listed = "/repos/o/r/actions/workflows/poller.yml/runs?per_page=100"
        artifact = "/repos/o/r/actions/runs/1/artifacts"

        class Answers:
            def send(self, req):
                return {"status": 200, "headers": {}, "body": {}}

        def effects(transport, *args, **kwargs):
            for path in (listed, artifact, artifact):
                transport.send({"method": "GET", "path": path})
            return {"applied": [], "read": [], "at": {}, "whole": True}

        def written(transport, *args, **kwargs):
            for path in (listed, listed, artifact):
                transport.send({"method": "GET", "path": path})
            return {"written": [], "read": [], "at": {}, "whole": True}
        said = io.StringIO()
        with unittest.mock.patch.object(entry.applied, "effects", effects), \
                unittest.mock.patch.object(entry.passes, "written", written):
            # The passes' records are read before the issues are listed, the Runs' after the writes are seen (issue 837).
            from_passes = entry.recorded_passes(Answers(), config, 777, [], "2026-10-11T06:00:00Z", lambda s: None,
                                                entry.Stages(ticking(), said))
            entry.recorded_effects(Answers(), config, None, [], "2026-10-11T06:00:00Z", from_passes, lambda s: None,
                                   entry.Stages(ticking(), said))
        lines = [json.loads(line) for line in said.getvalue().splitlines()]
        self.assertEqual([(l["stage"], l.get("count")) for l in lines],
                         [("poller", None), ("poller_list", 2), ("poller_artifacts", 1),
                          ("applied", None), ("applied_list", 1), ("applied_artifacts", 2)])

    def test_a_pull_request_left_out_and_closed_before_the_next_pass_is_read_as_left(self):  # issue 1194
        # The last pass left out 42, its facts unanswered, 43, moved twice, and 46, not facts, and owed none: closed
        # before this pass, each is read as left and stamped, by its type whatever its code. One still listed is read
        # open; an issue of a number, or an entry naming no item, is no pull request that left; nor is one an older
        # record alone left out (Astra, Muse).
        config = entry.configuration(ROOT, "factory/v0.3.1")
        home = config["controller"]["home"]["repo"]
        pull = lambda n: {"repo": home, "type": "pull_request", "number": n}
        reconciled = {"runs": [], "passes": [], "keys": [], "items": [], "dispatched": [], "owed": []}
        older = {"pull_requests": [], "left_out": [{"item": pull(41), "code": "facts_unanswered"}], "reconciled": reconciled}
        before = [older, {"pull_requests": [{"facts": {"item": pull(7)}}],
                          "left_out": [{"item": pull(42), "code": "facts_unanswered"},
                                       {"item": pull(43), "code": "pull_moved"},
                                       {"item": pull(45), "code": "facts_unanswered"},
                                       {"item": {"repo": home, "type": "issue", "number": 44}, "code": "facts_unanswered"},
                                       {"item": pull(46), "code": "not_facts"}, {"item": None, "code": "not_facts"}],
                          "reconciled": reconciled}]
        spied = []

        def read(transport, item, held, *rest, **told):
            spied.append((item["type"], item["number"], held))
            return [], [], True
        with unittest.mock.patch.object(entry.seen_, "read", read), \
                unittest.mock.patch.object(entry.seen_, "repo_read", lambda *a: True), \
                unittest.mock.patch.object(entry.seen_, "pushes", lambda *a, **k: ([], True)):
            seen, unread, newly, _, _ = entry.writes_seen(None, config, [7, 45], {}, before, "2026-10-11T06:00:00Z",
                                                          lambda: self.CLOCK)
        self.assertEqual([s for s in spied if s[0] == "pull_request"],
                         [("pull_request", 7, None), ("pull_request", 45, None),
                          ("pull_request", 42, entry.seen_.LEFT), ("pull_request", 43, entry.seen_.LEFT),
                          ("pull_request", 46, entry.seen_.LEFT)])
        self.assertEqual((newly, unread), ([42, 43, 46], []))
        self.assertIn(("issue", 44, entry.seen_.LEFT), spied)
        now = "2026-10-12T12:00:00Z"
        self.assertEqual(entry.reconcile.carried(before, None, seen, now, unread, newly)["left"],
                         [{"number": n, "at": now} for n in (42, 43, 46)])

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
