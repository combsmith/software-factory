"""One pull request, a fake GitHub around it, and things that go wrong.

The simulator drives the real Kernel. It plays the poller, the three jobs of a
Run and the people, picks what happens next from a seeded generator, and
checks the invariants after every step. A failure prints its seed.
"""
from __future__ import annotations

import copy
import datetime
import json
import pathlib
import random

from kernel import terms as t
from kernel.decide import decide
from kernel.derive import derive
from tools import check_lifecycle
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config" / "defaults.json").read_text())
DECISION_SCHEMA = json.loads((ROOT / "schemas" / "decision.schema.json").read_text())
FACTS_SCHEMA = json.loads((ROOT / "schemas" / "facts.schema.json").read_text())
DECLARED = check_lifecycle.declared(check_lifecycle.load())
ITEM = {"repo": "combsmith/software-factory", "type": "pull_request", "number": 1}
START = datetime.datetime(2026, 10, 11, 12, 0, 0)


class Broken(AssertionError):
    """An invariant did not hold."""


class World:
    def __init__(self, seed: int, faults: bool = True, people: bool = True):
        self.rng = random.Random(seed)
        self.seed, self.faults, self.people = seed, faults, people
        self.minute = 0
        self.content = 1
        self.pr_state = "open"
        self.author = self.last_pusher = "don-petry"
        self.labels = set()
        self.threads, self.reviews, self.runs = [], [], []
        self.checks = dict.fromkeys(CONFIG["required_lenses"]["deterministic"], "pending")
        self.queue = False
        self.last_push = self.last_writer = self.now()
        self.stale = None          # an older snapshot, served when facts go stale
        self.prev_state = None
        self.trace = []
        self.model_runs = 0

    def pick(self, options):
        """Choose with random() only, whose sequence is the same on every Python version."""
        options = list(options)
        return options[int(self.rng.random() * len(options))]

    # ---- time and facts
    def now(self) -> str:
        return (START + datetime.timedelta(minutes=self.minute)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def cid(self) -> str:
        return "sha256:%04x" % self.content

    def facts(self) -> dict:
        return {
            "schema": "facts/1", "item": dict(ITEM), "state": self.pr_state, "is_draft": False,
            "class": "maintainer", "author": self.author, "last_pusher": self.last_pusher,
            "targets_protected": True, "mergeable": True, "content_id": self.cid(),
            "diff": {"files": 2, "lines": 40, "truncated": False}, "labels": sorted(self.labels),
            "admitted_at": None, "last_push_at": self.last_push, "last_writer_action_at": self.last_writer,
            "reviews": copy.deepcopy(self.reviews), "threads": copy.deepcopy(self.threads),
            "checks": [{"lens": k, "conclusion": v} for k, v in sorted(self.checks.items())],
            "queue": self.queue,
            "complete": {"reviews": True, "threads": True, "checks": True, "diff": True},
            "read_at": self.now(),
        }

    def records(self) -> list:
        """What the records port lists: every Run, including one still waiting for a runner."""
        return [copy.deepcopy(r) for r in self.runs]

    def context(self) -> dict:
        active = len([r for r in self.runs if r["status"] != "completed"])
        return {"paused": False, "active_runs": active, "model_deferred_until": None}

    def held(self) -> bool:
        return bool(self.labels & {t.LABEL_HOLD, t.LABEL_HANDS_OFF})

    def note(self, what: str):
        self.trace.append("%s %s" % (self.now(), what))

    def check(self, ok: bool, invariant: str):
        if not ok:
            raise Broken("seed %d broke %s\n%s" % (self.seed, invariant, "\n".join(self.trace[-25:])))

    # ---- the poller
    def poll(self):
        facts, runs = self.facts(), self.records()
        fault = self.rng.random() if self.faults else 1.0
        if fault < 0.08 and self.stale is not None:
            facts, runs = self.stale            # a stale read
        elif fault < 0.14:
            facts["complete"][self.pick(sorted(facts["complete"]))] = False
        elif fault < 0.20 and runs:
            runs = runs[:-1]                    # the newest Run is not listed yet
        self.stale = (copy.deepcopy(facts), copy.deepcopy(runs))
        wrong = validate(facts, FACTS_SCHEMA)
        self.check(not wrong, "facts are valid: %s" % "; ".join(wrong))
        d = decide(facts, runs, self.context(), CONFIG, self.now())
        wrong = validate(d, DECISION_SCHEMA)
        self.check(not wrong, "every Decision is valid: %s" % "; ".join(wrong))
        self.note("pass: %s %s -> %s" % (d["state"], d["reason"], d["outcome"]))
        whole = all(facts["complete"].values())
        self.check(whole or d["outcome"] == "defer", "I-20 incomplete facts never admit or converge")
        if whole and d["state"] is not None:
            if self.prev_state is not None and d["state"] != self.prev_state:
                self.check((self.prev_state, d["state"]) in DECLARED,
                           "I-12 undeclared transition %s -> %s" % (self.prev_state, d["state"]))
            self.prev_state = d["state"]
        if d["outcome"] == "admit":
            self.runs.append({"run": "r%d" % len(self.runs), "item": dict(ITEM), "role": d["admit"]["role"],
                              "intent": d["admit"]["intent"], "content_id": d["admit"]["content_id"],
                              "status": "queued", "conclusion": None, "outcome": None, "started_at": self.now()})
        elif d["outcome"] == "act":
            self.apply_action(d)

    # ---- `apply` for a change that needs no model
    def apply_action(self, d: dict):
        fresh = derive(self.facts(), self.records(), CONFIG)     # apply reads the item again
        if self.held() or d["content_id"] != self.cid() or fresh["state"] != t.CONVERGED:
            self.note("apply: refused, the item changed")
            return
        if d["action"] == "issue_approval":
            self.check(CONFIG["approver"] not in (self.author, self.last_pusher), "I-26 approver is author or last pusher")
            self.reviews = [{"actor": CONFIG["approver"], "state": "approved", "commit": "c%d" % self.content,
                             "content_id": self.cid()}]
            self.note("apply: approved %s" % self.cid())
        elif d["action"] == "enqueue" and fresh["reason"] == "approved":
            self.queue = True
            self.note("apply: enqueued")

    # ---- the lane: one Run at a time, and each asks the Kernel again as it starts
    def start_next(self):
        if any(r["status"] == "in_progress" for r in self.runs):
            return
        waiting = [r for r in self.runs if r["status"] == "queued"]
        if not waiting:
            return
        run = waiting[0]
        others = [copy.deepcopy(r) for r in self.runs if r is not run]
        ctx = dict(self.context(), active_runs=self.context()["active_runs"] - 1)
        again = decide(self.facts(), others, ctx, CONFIG, self.now())
        wanted = {"role": run["role"], "intent": run["intent"], "content_id": run["content_id"]}
        if again["outcome"] != "admit" or again["admit"] != wanted:
            run.update(status="completed", conclusion="failure", outcome="superseded")
            self.note("run %s: superseded before it started" % run["run"])
            return
        run["status"] = "in_progress"
        self.model_runs += 1
        self.note("run %s: started %s %s" % (run["run"], run["role"], run["intent"]))
        if run["intent"] == "review-change":
            self.check(all(v == "success" for v in self.checks.values()), "I-27 model review before checks passed")
            done = [r for r in self.runs if r["intent"] == "review-change" and r["conclusion"] == "success"
                    and r["content_id"] == run["content_id"]]
            self.check(not done, "I-11 a second review of unchanged content")

    def finish_run(self):
        live = [r for r in self.runs if r["status"] == "in_progress"]
        if not live:
            return
        run = live[0]
        run["status"] = "completed"
        if self.faults and self.rng.random() < 0.12:
            run.update(conclusion="timed_out", outcome=self.pick(["item", "capacity", "environment"]))
            self.note("run %s: killed (%s)" % (run["run"], run["outcome"]))
            return
        if self.held() or run["content_id"] != self.cid() or self.pr_state != "open":
            run.update(conclusion="failure", outcome="superseded")   # apply read the item again
            self.note("run %s: apply refused, the item changed" % run["run"])
            return
        self.check(not self.held(), "I-21 an Effect on a held item")
        run["conclusion"] = "success"
        if run["intent"] == "review-change":
            if self.rng.random() < 0.5:
                self.threads.append({"id": "T%d" % len(self.threads), "resolved": False,
                                     "opened_by": {"kind": "lens", "name": "pr-review", "can_write": True},
                                     "severity": self.pick(["blocking", "major", "minor"]), "resolved_by": None,
                                     "opened_at": self.now()})
        elif run["intent"] == "fix-findings":
            self.push("combsmith-sf-dev-lead[bot]", writer=False)
        elif run["intent"] == "adjudicate-findings":
            for th in self.threads:
                if not th["resolved"] and th["opened_by"]["kind"] == "lens" and self.rng.random() < 0.7:
                    th.update(resolved=True, resolved_by="combsmith-sf-pr-review[bot]")
        self.note("run %s: applied" % run["run"])

    # ---- the platform and the people
    def push(self, who: str, writer: bool):
        self.content += 1
        self.last_pusher, self.last_push = who, self.now()
        if writer:
            self.last_writer = self.now()
        self.checks = dict.fromkeys(self.checks, "pending")
        self.queue = False
        self.note("push by %s -> %s" % (who, self.cid()))

    def platform(self):
        if self.queue and self.rng.random() < 0.6:
            self.pr_state = "merged"
            self.note("merged")
            return
        pending = [k for k, v in self.checks.items() if v == "pending"]
        if pending:
            self.checks[self.pick(pending)] = "success" if self.rng.random() < 0.85 else "failure"

    def person(self):
        roll = self.rng.random()
        if roll < 0.25:
            self.labels ^= {t.LABEL_HOLD}
            self.last_writer = self.now()
            self.note("maintainer toggled hold -> %s" % sorted(self.labels))
        elif roll < 0.45:
            self.push("don-petry", writer=True)
        elif roll < 0.60:
            self.threads.append({"id": "T%d" % len(self.threads), "resolved": False,
                                 "opened_by": {"kind": "human", "name": "don-petry", "can_write": True},
                                 "severity": None, "resolved_by": None, "opened_at": self.now()})
            self.last_writer = self.now()
            self.note("maintainer opened a thread")
        else:
            for th in self.threads:
                if not th["resolved"] and th["opened_by"]["kind"] == "human":
                    th.update(resolved=True, resolved_by="don-petry")
            self.last_writer = self.now()

    # ---- one step, and the invariants that hold at every step
    def step(self):
        self.minute += 1
        if self.pr_state != "open":
            return
        roll = self.rng.random()
        if roll < 0.40:
            if not (self.faults and self.rng.random() < 0.3):   # a dropped tick
                self.poll()
        elif roll < 0.60:
            self.start_next()
        elif roll < 0.78:
            self.finish_run()
        elif roll < 0.95 or not self.people:
            self.platform()
        else:
            self.person()
        self.invariants()

    def invariants(self):
        self.check(len([r for r in self.runs if r["status"] == "in_progress"]) <= 1, "I-2 one writer per item")
        for rv in self.reviews:
            self.check(rv["actor"] not in (self.author,), "I-26 the approver is the author")
        if self.pr_state == "merged":
            ok = any(rv["state"] == "approved" and rv["content_id"] == self.cid() for rv in self.reviews)
            self.check(ok, "NFR-4 merged without an approval of the merged content")
        since = [r for r in self.runs if r["started_at"] > self.last_writer and r["outcome"] != "superseded"]
        self.check(len(since) <= CONFIG["limits"]["max_runs_per_item"] + 1, "run ceiling per item")

    def settle(self, steps: int = 400):
        """Stop the faults and the people, and let the Factory finish."""
        self.faults = self.people = False
        self.labels.discard(t.LABEL_HOLD)
        for th in self.threads:
            if th["opened_by"]["kind"] == "human":
                th.update(resolved=True, resolved_by="don-petry")
        self.checks = {k: ("pending" if v == "failure" else v) for k, v in self.checks.items()}
        self.last_writer = self.now()
        for _ in range(steps):
            self.step()
        return decide(self.facts(), self.records(), self.context(), CONFIG, self.now())
