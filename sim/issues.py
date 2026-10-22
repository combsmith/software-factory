"""One issue, a fake GitHub around it, and things that go wrong (issue 43).

The issue world beside the pull request's in `world.py`. It drives the real issue Kernel, plays the
poller, the Controller's acts, the three issue Runs and the people, picks what happens next from a
seeded generator, injects five faults on fixed seeds, and checks I-39 to I-44 after every step. It
decides nothing: every decision comes from `kernel/issue.py`. A failure prints its seed.
"""
from __future__ import annotations

import copy
import json
import pathlib
import random

from kernel import issue
from kernel import terms as t
from sim.world import COLLEAGUE, MAINTAINER, STRANGER, Broken, World, queue_in_lane
from tools import check_lifecycle
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
ITEM = {"repo": "combsmith/software-factory", "type": "issue", "number": 7}
FACTS_SCHEMA = json.loads((ROOT / "schemas" / "issue-facts.schema.json").read_text())
DECISION_SCHEMA = json.loads((ROOT / "schemas" / "issue-decision.schema.json").read_text())
LIFECYCLE = check_lifecycle.load("issue")
DECLARED = check_lifecycle.declared(LIFECYCLE)
# The Apps the configuration names for an issue: the Controller's, which accepts and holds; the readiness Role's, which
# adds factory:ready; the investigating Role's, which comments; and the author's, which opens the pull request.
CONTROLLER = {"kind": "app", "name": "combsmith-sf-controller[bot]", "can_write": True}
READINESS = {"kind": "app", "name": "combsmith-sf-readiness[bot]", "can_write": True}
ANALYST = {"kind": "app", "name": "combsmith-sf-business-analyst[bot]", "can_write": True}
AUTHOR_APP = {"kind": "app", "name": "combsmith-sf-dev-lead[bot]", "can_write": True}
OTHER_APP = {"kind": "app", "name": "some-other-app[bot]", "can_write": True}
# The configuration the world gives the Kernel: the defaults, the issue's own Lifecycle, and issues served, which the
# data file leaves off until the Maintainer turns them on (decisions 0028, 0031). A world that serves nothing tests
# nothing.
SERVED = {"served_from": "2026-01-01T00:00:00Z", "left_out_labels": ["epic", "idea"], "left_out_types": ["Epic"],
          "label_apps": {issue.LABEL_TRIAGE: CONTROLLER["name"], issue.LABEL_READY: READINESS["name"]},
          "intents": {issue.INVESTIGATE: {"role": "business-analyst", "app": ANALYST["name"]},
                      issue.JUDGE_READINESS: {"role": "readiness", "app": READINESS["name"]},
                      issue.OPENING: {"role": "dev-lead", "app": AUTHOR_APP["name"]}}}
CONFIG = dict(json.loads((ROOT / "config" / "defaults.json").read_text()), lifecycle=LIFECYCLE, issues=SERVED)
LIMITS = CONFIG["limits"]
# Each person's permission on the repo, as the collaborator permission endpoint answers it, and the permissions that
# are write access (issue 222, decision 0048): the port reads the one and gives the facts the other.
PERMISSIONS = {MAINTAINER["name"]: "admin", COLLEAGUE["name"]: "write", STRANGER["name"]: "read"}
WRITE_ACCESS = ("admin", "maintain", "write")
# The invariants the Kernel does not hold yet, each the name of a test marked @pending in tests/test_issue.py.
NOT_YET_HELD = ()
# On an even seed a person with write access opened the issue; on an odd seed an outsider did, whom the Maintainer
# admits on one odd seed in two (ADMITTED) and never on the other. By the seed alone.
ADMITTED = 1
# The Pause, as the pull request's world draws it: on a span of minutes, on one seed in five; on another in five the
# Pause cannot be read for that span.
PAUSES = {0: True, 3: None}
PAUSE_FOR = 80
# The six faults, each on seeds chosen by a constant, so that every other seed stays as it was, and each is reached
# within the first 40 seeds (tests/test_issue_simulator.py holds that).
# 1. An outsider edits the issue after the Maintainer admitted it: the admission stops counting (I-42).
EDITS_EVERY, EDITS = 7, 1
# 2. A stranger's pull request names the issue: it is in `linked`, unadmitted, and moves nothing (I-39).
STRANGER_PR_EVERY, STRANGER_PR = 6, 2
# 3. Someone without write access reopens the closed issue: it stays declined (row 2, I-41).
REOPENS_EVERY, REOPENS = 8, 3
# 4. A person removes a label while a Run is in flight: the Run's apply writes nothing (I-38).
REMOVES_EVERY, REMOVES = 5, 0
# 5. Run records expire: records older than the retention vanish from what a pass reads, and the investigating App's
# comment, or the readiness App's label or comment, stands in (decision 0031).
EXPIRES_EVERY, EXPIRES = 9, 3
RETENTION = 60      # minutes, the world's own; GitHub keeps a run record 90 days (P-16)
# 6. An edit to a once-merged pull request's description names the issue after the merge (P-46, issue 267): it is in
# `linked`, merged, and closed nothing, and the State with it is the State without it.
LATE_EVERY, LATE = 10, 5     # odd: the outsider's seeds
# The three Runs: who runs each, and how one ends.
ROLES = {issue.INVESTIGATE: "business-analyst", issue.JUDGE_READINESS: "readiness", issue.OPENING: "dev-lead"}
MOVE_LABELS = (t.LABEL_HOLD, t.LABEL_HANDS_OFF, t.LABEL_ADMIT, issue.LABEL_TRIAGE, issue.LABEL_READY)
# Who the Lifecycle says makes a change of State: a person with write access, the Factory, the platform, or a stranger.
HUMAN, FACTORY, PLATFORM, STRANGER_BY = "human", "factory", "platform", "stranger"


class IssueWorld:
    def __init__(self, seed: int, faults: bool = True, people: bool = True):
        self.rng = random.Random(seed)
        self.seed, self.faults, self.people = seed, faults, people
        self.minute = 0
        self.author = dict(MAINTAINER if seed % 2 == 0 else STRANGER)
        self.admits = seed % 2 == 1 and seed % 4 == ADMITTED
        self.state = "open"            # as GitHub holds it
        self.life_started = 0          # when the present life began: opened, or last reopened by a writer
        self.reopened_last_by = "never"
        self.closed = None             # when the present life was first closed, from its timeline; None while not
        self.reopened_last = None      # when the issue was last reopened, by anyone; None while never
        self.content = 1
        self.content_changed = 0
        self.type = None
        self.label_names = []
        self.labels = set()            # the control labels on the issue, as GitHub shows them
        self.events = []               # the timeline's labeled and unlabeled events
        self.hold, self.hands_off = False, None
        self.linked = []               # every pull request that names the issue, as the port lists them
        self.comments = []             # the Factory Apps' comments: who and when
        self.last_writer = None if seed % 3 == 0 else self.now()
        self.last_writer_comment = None
        self.acts = 0
        self.last_act = None
        self.runs = []                 # every Run ever, with the minute it started, for the retention
        self.branch_head = None
        self.pause_from = 10 + seed * 37 % 200 if seed % 5 in PAUSES else None
        self.pause_reading = PAUSES.get(seed % 5)
        self.paused_passes = 0
        self.stopped = []
        self.moved = self.chain = self.minute
        self.gap = False
        self.stale = None
        self.read = None
        self.made = set()
        self.reached = []              # the faults this seed reached, by number
        self.late = []                 # the pull requests an edit after their merge made name the issue (fault 6)
        self.unheld = []
        self.began = set()             # the States each life began in: the opening's, and a writer's reopenings'
        self.removal_in_flight = None  # the Run a label was taken from under (fault 4), which no kill then hides
        self.trace = []
        self.model_runs = 0
        self.true_state = None
        self.starts()

    # ---- the world's own words
    def starts(self):
        self.true_state = issue.decide(self.facts(), self.records(), self.unpaused(), CONFIG, self.now())["state"]

    def pick(self, options):
        """Choose with random() only, whose sequence is the same on every Python version."""
        options = list(options)
        return options[int(self.rng.random() * len(options))]

    def now(self) -> str:
        return World.at(self.minute)

    def cid(self) -> str:
        return "sha256:%04x" % self.content

    def note(self, what: str):
        self.trace.append("%s %s" % (self.now(), what))

    def check(self, ok: bool, invariant: str):
        if not ok:
            raise Broken("seed %d broke %s\n%s" % (self.seed, invariant, "\n".join(self.trace[-25:])))

    def check_unheld(self, ok: bool, test: str, invariant: str):
        if test not in NOT_YET_HELD:
            self.check(ok, invariant)
        elif not ok:
            self.unheld.append(test)
            self.note("not held yet: %s" % invariant)

    @staticmethod
    def is_person(by: dict) -> bool:
        return by["kind"] == "human" and by["can_write"] is True

    @classmethod
    def by_of(cls, actor: dict) -> str:
        """Who makes what `actor` does, in the Lifecycle's words: a person with write access, the Factory's own Apps,
        any other App, or a stranger, whom the Lifecycle names only as one whose change goes back to `new`."""
        if cls.is_person(actor):
            return HUMAN
        if actor["name"] in (CONTROLLER["name"], READINESS["name"], ANALYST["name"], AUTHOR_APP["name"]):
            return FACTORY
        return PLATFORM if actor["kind"] == t.APP else STRANGER_BY

    def moves(self):
        self.moved = self.minute

    def writer_acted(self):
        """A person with write access acted: a fresh allowance of attempts and of acts (I-28), and the issue moved."""
        self.last_writer = self.now()
        self.acts = 0
        self.moves()

    def held(self) -> bool:
        return self.hold or self.hands_off is not None

    # ---- the facts, as the port would give them
    def facts(self) -> dict:
        return {
            "schema": "issue-facts/1", "item": dict(ITEM), "state": self.state,
            # GitHub: an_issues_close_and_reopening_say_when
            "closed_first_at": None if self.closed is None else World.at(self.closed),
            # GitHub: a_logins_permission_is_read_from_the_collaborator_endpoint
            "author": dict(self.author, can_write=PERMISSIONS[self.author["name"]] in WRITE_ACCESS),
            "type": self.type, "label_names": list(self.label_names),
            "assignees": [],
            # GitHub: a_reopening_names_its_actor
            "life_started_at": World.at(self.life_started), "reopened_last_by": self.reopened_last_by,
            "reopened_last_at": None if self.reopened_last is None else World.at(self.reopened_last),
            # GitHub: an_issues_content_time_is_read_apart
            "content_id": self.cid(), "content_changed_at": World.at(self.content_changed),
            # GitHub: a_label_event_names_its_actor
            "label_events": copy.deepcopy(self.events),
            # GitHub: a_closing_reference_is_read_from_any_pull_request
            # GitHub: who_changed_the_draft_flag_is_read
            # GitHub: a_merge_closes_the_issue_it_names_and_an_edit_after_it_closes_nothing
            "linked": copy.deepcopy(self.linked),
            "role_comments": copy.deepcopy(self.comments),
            "last_writer_action_at": self.last_writer, "last_writer_comment_at": self.last_writer_comment,
            # GitHub: the_timeline_shows_each_act
            "acts_since_writer": self.acts, "branch_head": self.branch_head,
            "complete": {"timeline": True, "linked": True, "runs": True}, "read_at": self.now(),
        }

    def records(self) -> list:
        """What the records port lists: every Run, a queued one among them, but none past the retention on a seed
        whose records expire."""
        kept = self.runs
        if self.seed % EXPIRES_EVERY == EXPIRES:
            # GitHub: an_issues_run_record_expires
            kept = [r for r in self.runs if r["minute"] > self.minute - RETENTION]
            if len(kept) < len(self.runs) and 5 not in self.reached:
                self.reached.append(5)
                self.note("a run record expired")
        return [{k: v for k, v in r.items() if k not in ("minute", "head")} for r in copy.deepcopy(kept)]

    def pausing(self) -> bool:
        return self.pause_from is not None and self.pause_from <= self.minute < self.pause_from + PAUSE_FOR

    def context(self) -> dict:
        active = len([r for r in self.runs if r["status"] != "completed"])
        ctx = {"paused": False, "active_runs": active, "model_deferred_until": None,
               "passes_since": World.at(self.chain), "unidentified_runs": []}
        if self.pausing():
            if self.pause_reading is None:
                del ctx["paused"]
            else:
                ctx["paused"] = self.pause_reading
        return ctx

    def unpaused(self) -> dict:
        return dict(self.context(), paused=False)

    def caused(self, by: str):
        """A change was just made by `by`. If it changed the State the Kernel gives what GitHub holds, the Lifecycle
        declares that transition, made by `by` (I-12)."""
        state = issue.decide(self.facts(), self.records(), self.unpaused(), CONFIG, self.now())["state"]
        if state is None:
            return
        if state != self.true_state:
            self.made.add((self.true_state, state, by))
            self.check((self.true_state, state, by) in DECLARED,
                       "I-12 undeclared transition %s -> %s by %s" % (self.true_state, state, by))
        self.true_state = state

    # ---- labels
    def labelling(self, name: str, action: str, by: dict):
        if self.events and self.events[-1]["at"] >= self.now():
            self.minute += 1
        # GitHub: a_label_event_names_its_actor
        self.events.append({"label": name, "action": action, "by": dict(by), "at": self.now()})

    def label(self, name: str, by: dict):
        self.labels.add(name)
        self.labelling(name, "labeled", by)
        if name == t.LABEL_HOLD:
            self.hold = True
        elif name == t.LABEL_HANDS_OFF and not (self.hands_off == "person" and not self.is_person(by)):
            self.hands_off = "person" if self.is_person(by) else "app"
        if self.is_person(by) or by["name"] in SERVED["label_apps"].values():
            self.moves()

    def unlabel(self, name: str, by: dict):
        self.labels.discard(name)
        self.labelling(name, "unlabeled", by)
        if self.is_person(by):
            if name == t.LABEL_HOLD:
                self.hold = False
            elif name == t.LABEL_HANDS_OFF:
                self.hands_off = None
        if self.is_person(by) or by["name"] in SERVED["label_apps"].values():
            self.moves()

    def release(self):
        for name, binds in ((t.LABEL_HOLD, self.hold), (t.LABEL_HANDS_OFF, self.hands_off is not None)):
            if binds:
                if name not in self.labels:
                    self.label(name, MAINTAINER)
                self.unlabel(name, MAINTAINER)

    # ---- the poller
    def overdue(self, state) -> bool:
        """Whether the wait has run past its State's limit by the world's own count: from when the issue last moved,
        and no earlier than the chain of passes began (#165, ruling 8)."""
        limit = LIFECYCLE["stale_after_minutes"].get(state)
        return limit is not None and self.minute - max(self.moved, self.chain) > limit

    def poll(self):
        if self.gap:
            self.chain, self.gap = self.minute, False
        facts, runs = self.facts(), self.records()
        current = exact = True
        fault = self.rng.random() if self.faults else 1.0
        if fault < 0.08 and self.stale is not None:
            # GitHub: a_read_can_be_stale
            facts, runs = self.stale
            current = exact = False
        elif fault < 0.14:
            # GitHub: a_short_list_says_so
            facts["complete"][self.pick(sorted(facts["complete"]))] = False
        elif fault < 0.20 and runs:
            # GitHub: a_new_run_is_listed_late
            runs = runs[:-1]
            exact = False
        elif fault < 0.25 and runs:
            # GitHub: a_run_list_stops_short
            runs = runs[self.pick(range(1, len(runs) + 1)):]
            facts["complete"]["runs"] = False
        self.stale = (copy.deepcopy(facts), copy.deepcopy(runs))
        wrong = validate(facts, FACTS_SCHEMA)
        self.check(not wrong, "facts are valid: %s" % "; ".join(wrong))
        ctx = self.context()
        d = issue.decide(facts, runs, ctx, CONFIG, self.now())
        wrong = validate(d, DECISION_SCHEMA)
        self.check(not wrong, "the Decision is valid: %s" % "; ".join(wrong))
        self.note("pass: %s / %s -> %s %s%s" % (d["state"], d["reason"], d["outcome"],
                                                 d.get("action") or d.get("admit", {}).get("intent", ""),
                                                 " [%s]" % d["attention"]))
        if self.pausing():
            self.paused(facts, runs, d, ctx)
            return
        self.answers(facts, runs, d, current and exact)
        if d["outcome"] == t.ADMIT:
            self.admit(d, facts)
        elif d["outcome"] == t.ACT:
            self.apply_action(d)
        if current and exact:
            self.read = self.unstamped(facts)

    @staticmethod
    def unstamped(facts: dict) -> dict:
        return {k: v for k, v in facts.items() if k != "read_at"}

    def paused(self, facts: dict, runs: list, d: dict, ctx: dict):
        """Under a Pause, read or not, nothing is admitted and nothing acts, the Hold for unmerged closes included,
        which defers for the Maintainer to see; a Hold the facts establish shows as without one (decision 0003)."""
        self.paused_passes += 1
        self.check(d["outcome"] in (t.DEFER, t.HOLD, t.NOTHING), "I-7 a Pause let %s through" % d["outcome"])
        unpaused = issue.decide(facts, runs, dict(ctx, paused=False), CONFIG, self.now())
        if unpaused["outcome"] in (t.ADMIT, t.ACT):
            self.stopped.append(unpaused.get("action") or t.ADMIT)

    def answers(self, facts: dict, runs: list, d: dict, whole: bool):
        """What the Kernel answered, held to the invariants it can be held to on this read."""
        self.check(d["state"] in DECLARED_STATES or d["state"] is None, "I-44 a State the Lifecycle does not declare")
        if d["outcome"] == t.ADMIT:
            self.check(not whole or self.accepted(), "I-42 a Run admitted on an issue not accepted now")
            self.check(not whole or not self.held(), "I-21 a Run admitted on a held issue")
            # On a list read whole and current, no second Run is admitted beside one queued or in flight; on a list
            # read late, the second supersedes itself as it starts (I-38, a_new_run_is_listed_late).
            self.check(not whole or not any(r["status"] != "completed" for r in self.runs),
                       "I-44 a second Run admitted on the issue")
            # On a list read late, the investigation just completed is not on it, and the Run admitted in its place
            # supersedes itself as it starts (I-38).
            if d["admit"]["intent"] == issue.INVESTIGATE and whole:
                self.check(self.investigation_due(), "I-42 an investigating Run with nothing to investigate")
        if whole and d["attention"] in (t.REVIEW, t.READY, t.STALE) and d["reason"] not in t.SCOPE_DEFERRALS:
            self.check((d["attention"] == t.STALE) == self.overdue(d["state"]),
                       "I-1 the wait shows %s where the world counts %s minutes since it moved"
                       % (d["attention"], self.minute - max(self.moved, self.chain)))
        # I-39: with the stranger's pull request read out, the State is the same.
        strangers = [p for p in facts["linked"] if p["class"] == "outside" and not issue.admitted_once(p)]
        if strangers:
            without = dict(facts, linked=[p for p in facts["linked"] if p not in strangers])
            self.check(issue.derive(without, runs, CONFIG)["state"] == issue.derive(facts, runs, CONFIG)["state"],
                       "I-39 a stranger's pull request moved the issue")

    def accepted(self) -> bool:
        """Accepted now, in the world's own words: served, and opened by a person with write access, or admitted by
        one after the content last changed."""
        if self.is_person(self.author):
            return True
        admitted = [ev for ev in self.events if ev["label"] == t.LABEL_ADMIT and self.is_person(ev["by"])]
        if not admitted or admitted[-1]["action"] != "labeled":
            return False
        return admitted[-1]["at"] > World.at(self.content_changed)

    def investigation_due(self) -> bool:
        """Whether an investigating Run may be admitted, in the world's own words (I-42): the content changed or a
        writer acted since the last that succeeded, or the last ended without investigating and the attempts since a
        writer acted are not spent."""
        kept = [r for r in self.records() if r["intent"] == issue.INVESTIGATE]
        after = lambda when: self.last_writer is None or when > self.last_writer
        if kept:
            current = any(r["conclusion"] == "success" and r["content_id"] == self.cid() and after(r["started_at"])
                          for r in kept)
        else:
            # Every record has expired: the analyst's comment since the edit and the writer's act stands in.
            current = any(c["by"] == ANALYST["name"] and c["at"] > World.at(self.content_changed) and after(c["at"])
                          for c in self.comments)
        if current:
            return False
        failed = [r for r in kept if r["status"] == "completed" and r["outcome"] == "item" and after(r["started_at"])]
        return len(failed) < LIMITS["max_attempts"]

    def admit(self, d: dict, facts: dict):
        intent = d["admit"]["intent"]
        run = {"run": "r%d" % len(self.runs), "item": dict(ITEM), "role": d["admit"]["role"], "intent": intent,
               "content_id": d["admit"]["content_id"], "status": "queued", "conclusion": None, "outcome": None,
               "started_at": self.now(), "minute": self.minute, "head": d["admit"].get("branch_head")}
        # GitHub: a_queued_run_is_listed
        self.enqueue(run)
        self.moves()
        self.note("run %s: admitted %s %s" % (run["run"], run["role"], intent))
        self.caused(FACTORY)

    def apply_action(self, d: dict):
        """The Controller's act, made only if the Kernel, asked again on what GitHub holds now, still wants it."""
        fresh = issue.decide(self.facts(), self.records(), self.context(), CONFIG, self.now())
        same = fresh["outcome"] == t.ACT and fresh["action"] == d["action"] and fresh["content_id"] == d["content_id"]
        if d["content_id"] != self.cid() or not same:
            self.note("apply: refused, the issue changed")
            return
        if d["action"] == issue.ACCEPT:
            self.label(issue.LABEL_TRIAGE, CONTROLLER)
            self.note("apply: accepted")
        elif d["action"] == issue.REMOVE_LABEL:
            self.unlabel(d["label"], CONTROLLER)
            self.note("apply: removed %s" % d["label"])
        elif d["action"] == issue.PLACE_HOLD:
            self.label(t.LABEL_HOLD, CONTROLLER)
            self.note("apply: held (%s)" % d["reason"])
        self.acts += 1
        self.last_act = d["action"]
        self.caused(FACTORY)

    # ---- the lane: one Run at a time, and each asks the Kernel again as it starts
    def enqueue(self, run: dict):
        """Queue a Run in the issue's concurrency group, by the lane the pull request's world keeps (queue_in_lane)."""
        # GitHub: a_run_waits_its_turn
        queue_in_lane(self.runs, run, self.note)

    def start_next(self):
        if any(r["status"] == "in_progress" for r in self.runs):
            return
        waiting = [r for r in self.runs if r["status"] == "queued"]
        if not waiting:
            return
        run = waiting[0]
        others = [r for r in self.records() if r["run"] != run["run"]]
        ctx = dict(self.context(), active_runs=self.context()["active_runs"] - 1)
        again = issue.decide(self.facts(), others, ctx, CONFIG, self.now())
        wanted = {k: run[k] for k in ("role", "intent", "content_id")}
        if again["outcome"] != t.ADMIT or {k: again["admit"].get(k) for k in wanted} != wanted:
            # GitHub: a_superseded_run_fails
            run.update(status="completed", conclusion="failure", outcome="superseded")
            self.note("run %s: superseded before it started" % run["run"])
            self.caused(FACTORY)
            return
        run["status"] = "in_progress"
        self.model_runs += 1
        self.note("run %s: started %s" % (run["run"], run["intent"]))
        self.caused(FACTORY)

    def finish_run(self):
        live = [r for r in self.runs if r["status"] == "in_progress"]
        if not live:
            return
        self.ending(live[0])
        self.caused(FACTORY)

    def ending(self, run: dict):
        run["status"] = "completed"
        if self.faults and self.rng.random() < 0.12 and run["run"] != self.removal_in_flight:
            # GitHub: a_killed_job_times_out
            run.update(conclusion="timed_out", outcome=self.pick(["item", "capacity", "environment"]))
            self.note("run %s: killed (%s)" % (run["run"], run["outcome"]))
            return
        # apply asks the Kernel again with its own Run left out (I-38): a label removed, a Hold added, an edit made or
        # a head moved while the Run was in flight each stop it.
        others = [r for r in self.records() if r["run"] != run["run"]]
        again = issue.decide(self.facts(), others, self.context(), CONFIG, self.now())
        admitted = {"admit": {k: run[k] for k in ("role", "intent", "content_id")}}
        if run["intent"] == issue.OPENING:
            admitted["admit"]["branch_head"] = run["head"]
        if not issue.still_admitted(admitted, again):
            # GitHub: a_superseded_run_fails
            run.update(conclusion="failure", outcome="superseded")
            self.note("run %s: apply refused, the issue changed (%s / %s)" % (run["run"], again["state"], again["reason"]))
            return
        self.check(not self.held(), "I-21 an Effect on a held issue")
        self.check(not self.pausing(), "I-21 an Effect under a Pause")
        self.check(self.accepted(), "I-42 an Effect on an issue not accepted now")
        if self.faults and self.rng.random() < 0.2:
            # The Run ended by a fault of the issue: it investigated nothing, judged nothing, opened nothing.
            run.update(conclusion="failure", outcome="item")
            self.note("run %s: failed for the issue" % run["run"])
            return
        run["conclusion"] = "success"
        if run["intent"] == issue.INVESTIGATE:
            self.comments.append({"by": ANALYST["name"], "at": self.now()})
            self.note("run %s: the analyst commented" % run["run"])
        elif run["intent"] == issue.JUDGE_READINESS:
            if self.rng.random() < 0.7:
                self.check(not self.removed_by_a_person(issue.LABEL_READY),
                           "I-40 factory:ready added again after a person removed it for this content")
                self.label(issue.LABEL_READY, READINESS)
                self.note("run %s: readiness added factory:ready" % run["run"])
            else:
                self.note("run %s: readiness judged, and added nothing" % run["run"])
        elif run["intent"] == issue.OPENING:
            number = 100 + len(self.linked)
            # GitHub: a_closing_reference_is_read_from_any_pull_request
            self.linked.append({"number": number, "class": "agent", "opener": dict(AUTHOR_APP), "open": True,
                                "draft": True, "opened_at": self.now(), "merged_at": None, "closed_at": None,
                                "empty": False, "label_events": [], "closed_issue_at": None})
            self.branch_head = "%040x" % (0xabc0 + number)
            self.moves()
            self.note("run %s: opened the draft #%d" % (run["run"], number))

    def removed_by_a_person(self, name: str) -> bool:
        return any(ev["label"] == name and ev["action"] == "unlabeled" and self.is_person(ev["by"])
                   and ev["at"] >= World.at(self.content_changed) for ev in self.events)

    # ---- the platform and the people
    def platform(self):
        """The pull request the Factory opened moves on its own Lifecycle; the queue merges it; a stranger's names
        the issue; another App labels."""
        mine = [p for p in self.linked if p["open"] and p["class"] == "agent"]
        roll = self.rng.random()
        if mine and roll < 0.3:
            p = mine[0]
            if p["draft"]:
                # GitHub: who_changed_the_draft_flag_is_read
                p["draft"] = False
                self.moves()
                self.note("#%d marked ready by its author" % p["number"])
                self.caused(FACTORY)
            elif roll < 0.2 and self.true_state == "in_review":
                # The merge queue merges the Factory's pull request, after the Factory's approval and enqueue: the
                # change in the facts is the platform's, as the pull request's Lifecycle says of a queued merge. Only
                # while the issue is in review: the Controller dequeues the pull request of an issue a person held or
                # closed (the Maintainer's ruling on issue 227), so no merge lands while the issue is held or
                # declined, nor from new. Were one to land, the Kernel would read it as never done (issue 237).
                p.update(open=False, merged_at=self.now(), closed_at=self.now(), empty=False,
                         closed_issue_at=self.closes_the_issue())
                self.moves()
                self.note("#%d merged by the queue" % p["number"])
                self.caused(PLATFORM)
            return
        if self.faults and self.seed % STRANGER_PR_EVERY == STRANGER_PR and roll < 0.4 \
                and not any(p["class"] == "outside" for p in self.linked):
            self.linked.append({"number": 200 + len(self.linked), "class": "outside", "opener": dict(STRANGER),
                                "open": True, "draft": self.rng.random() < 0.5, "opened_at": self.now(),
                                "merged_at": None, "closed_at": None, "empty": False, "label_events": [], "closed_issue_at": None})
            self.reached.append(2)
            self.note("a stranger's pull request names the issue")
            self.caused(STRANGER_BY)
            return
        if self.faults and 0.44 <= roll < 0.45 and t.LABEL_HOLD not in self.labels:
            # GitHub: an_app_can_label
            self.label(t.LABEL_HOLD, OTHER_APP)
            self.note("another App added factory:hold")
            self.caused(PLATFORM)
        elif self.faults and 0.45 <= roll < 0.46 and issue.LABEL_TRIAGE not in self.labels:
            # An App the configuration does not name adds factory:triage: the Kernel counts it for nothing (I-41).
            self.label(issue.LABEL_TRIAGE, OTHER_APP)
            self.note("another App added factory:triage")
            self.caused(PLATFORM)

    def person(self):
        by = self.acting()
        self.caused(by)

    def acting(self) -> str:
        """The Maintainer, a colleague, or the outsider who opened the issue acts."""
        roll = self.rng.random()
        outsider = not self.is_person(self.author)
        if outsider and roll < 0.25:
            return self.outsider_acts()
        who = MAINTAINER if self.rng.random() < 0.7 else COLLEAGUE
        edited = [p for p in self.linked if p["number"] in self.late]
        if edited and roll < 0.5:
            # GitHub: a_merge_closes_the_issue_it_names_and_an_edit_after_it_closes_nothing
            self.linked.remove(edited[0])
            self.note("%s undid the edit, and #%d names the issue no more" % (who["name"], edited[0]["number"]))
            return HUMAN
        if self.state == "closed":
            if roll < 0.5:
                self.reopen(who)
            return HUMAN
        roll = self.rng.random()
        standing = [name for name in (issue.LABEL_TRIAGE, issue.LABEL_READY) if name in self.labels]
        if (self.seed % REMOVES_EVERY == REMOVES and standing and roll < 0.6
                and any(r["status"] == "in_progress" for r in self.runs)):
            # The fault: a person takes a label off while a Run is in flight, whose apply then writes nothing.
            name = standing[0]
            self.unlabel(name, who)
            self.writer_acted()
            self.reached.append(4)
            self.removal_in_flight = next(r["run"] for r in self.runs if r["status"] == "in_progress")
            self.note("%s removed %s while a Run was in flight" % (who["name"], name))
            return HUMAN
        if self.held() and roll < 0.15:
            # Only a person ends what a label holds, whoever placed it (L-17).
            self.release()
            self.writer_acted()
            self.note("%s released the hold" % who["name"])
        elif not self.held() and roll < 0.06:
            name = t.LABEL_HOLD if self.rng.random() < 0.7 else t.LABEL_HANDS_OFF
            self.label(name, who)
            self.writer_acted()
            self.note("%s added %s" % (who["name"], name))
        elif roll < 0.22:
            self.edit(who)
        elif roll < 0.32:
            self.last_writer_comment = self.now()
            self.writer_acted()
            self.note("%s commented" % who["name"])
        elif roll < 0.42 and outsider and self.admits and t.LABEL_ADMIT not in self.labels:
            self.label(t.LABEL_ADMIT, who)
            self.writer_acted()
            self.note("%s admitted the issue" % who["name"])
        elif roll < 0.52:
            name = self.pick([issue.LABEL_TRIAGE, issue.LABEL_READY])
            if name in self.labels:
                self.unlabel(name, who)
                self.note("%s removed %s" % (who["name"], name))
            else:
                self.label(name, who)
                self.note("%s added %s" % (who["name"], name))
            self.writer_acted()
        elif roll < 0.60:
            self.close(who)
        elif roll < 0.75:
            self.on_the_pull_request(who)
        else:
            # A stranger comments: it changes nothing and renews nothing.
            self.note("a stranger commented")
            return STRANGER_BY
        return HUMAN

    def edit(self, who: dict):
        # GitHub: an_issues_content_time_is_read_apart
        self.content += 1
        self.content_changed = self.minute
        if self.is_person(who):
            self.writer_acted()
        self.note("%s edited the content -> %s" % (who["name"], self.cid()))

    def close(self, who: dict):
        if self.state == "closed":
            return
        self.state = "closed"
        if self.closed is None:
            self.closed = self.minute
        self.writer_acted()
        self.note("%s closed the issue" % who["name"])

    def reopen(self, who: dict):
        """A reopening by a person with write access begins a new life, from the Lifecycle's start, as the issue's
        opening did: `declined` is an end of the life that closed, and the new life's first State is no transition
        from it. A Hold, an admission and hands-off outlast it (section 4.1). By anyone else, the issue stays
        declined."""
        self.state, self.reopened_last = "open", self.minute
        # GitHub: a_reopening_names_its_actor
        if self.is_person(who):
            self.life_started, self.closed = self.minute, None
            self.reopened_last_by = "writer"
            self.writer_acted()
            self.starts()
            self.check(self.true_state in DECLARED_STATES, "I-44 a new life began in an undeclared State")
            self.began.add(self.true_state)
            self.note("%s reopened the issue: a new life, in %s" % (who["name"], self.true_state))
        else:
            self.reopened_last_by = "other"
            self.note("%s reopened the issue, which stays declined" % who["name"])

    def outsider_acts(self) -> str:
        roll = self.rng.random()
        if self.state == "closed" and self.seed % REOPENS_EVERY == REOPENS and roll < 0.6:
            self.reopen(STRANGER)
            self.reached.append(3)
            return STRANGER_BY
        if self.seed % EDITS_EVERY == EDITS and t.LABEL_ADMIT in self.labels and self.accepted() and roll < 0.8:
            # The fault: the admission counted until now, and counts no longer.
            self.edit(STRANGER)
            self.reached.append(1)
            return STRANGER_BY
        lag = LIMITS["max_close_lag_seconds"] // 60 + 1
        if self.faults and self.seed % LATE_EVERY == LATE and roll >= 0.8 and not self.late \
                and self.minute - self.life_started > lag:
            # GitHub: a_merge_closes_the_issue_it_names_and_an_edit_after_it_closes_nothing
            # A pull request of the Factory's that merged at the start of this life, closing nothing here, whose
            # description an edit now makes name the issue, long after the merge, as P-46's edit came a day after.
            number, merged = 400 + len(self.linked), World.at(self.life_started)
            self.linked.append({"number": number, "class": "agent", "opener": dict(AUTHOR_APP), "open": False,
                                "draft": False, "opened_at": merged, "merged_at": merged,
                                "closed_at": merged, "empty": False, "label_events": [], "closed_issue_at": None})
            self.late.append(number)
            self.reached.append(6)
            self.note("an edit after its merge made #%d name the issue" % number)
            return STRANGER_BY
        self.note("the outsider commented")
        return STRANGER_BY

    def closes_the_issue(self):
        """The close a merge makes now: GitHub closes the open issue its references name, and the issue's timeline
        names the pull request the closer (P-33); an issue already closed it cannot close."""
        # GitHub: a_merge_closes_the_issue_it_names_and_an_edit_after_it_closes_nothing
        return self.now() if self.state == "open" else None

    def on_the_pull_request(self, who: dict):
        """A person acts on the linked pull request: marks the draft ready, converts it back, merges it or closes
        it unmerged; or opens one of their own."""
        theirs = [p for p in self.linked if p["open"] and p["class"] == "outside"]
        if theirs and self.rng.random() < 0.25:
            # A person merges or closes the stranger's pull request: it moves the issue no more than it did open.
            p = theirs[0]
            if self.rng.random() < 0.5:
                p.update(open=False, merged_at=self.now(), closed_at=self.now(), closed_issue_at=self.closes_the_issue())
                self.note("%s merged the stranger's #%d" % (who["name"], p["number"]))
            else:
                p.update(open=False, closed_at=self.now())
                self.note("%s closed the stranger's #%d unmerged" % (who["name"], p["number"]))
            self.writer_acted()
            return
        mine = [p for p in self.linked if p["open"] and p["class"] in issue.MOVING_CLASSES]
        if not mine:
            if self.rng.random() < 0.3:
                self.linked.append({"number": 300 + len(self.linked), "class": "maintainer", "opener": dict(who),
                                    "open": True, "draft": self.rng.random() < 0.5, "opened_at": self.now(),
                                    "merged_at": None, "closed_at": None, "empty": False, "label_events": [], "closed_issue_at": None})
                self.writer_acted()
                self.note("%s opened a pull request of their own" % who["name"])
            return
        p, roll = mine[0], self.rng.random()
        if roll < 0.3:
            p["draft"] = not p["draft"]
            self.note("%s %s #%d" % (who["name"], "converted to draft" if p["draft"] else "marked ready", p["number"]))
        elif roll < 0.6 and self.true_state != issue.DECLINED and not p["draft"]:
            # GitHub: a_draft_is_not_merged
            # Not while the issue is declined, closed or reopened by an outsider: the Lifecycle lets nothing out of
            # declined, and the Kernel would read the merge as done (issue 237 builds the Hold for it). A person's
            # merge while the issue is held stands: the Lifecycle declares held -> done by a person.
            p.update(open=False, merged_at=self.now(), closed_at=self.now(), empty=self.rng.random() < 0.1,
                     closed_issue_at=self.closes_the_issue())
            self.note("%s merged #%d" % (who["name"], p["number"]))
        else:
            p.update(open=False, closed_at=self.now())
            self.note("%s closed #%d unmerged" % (who["name"], p["number"]))
        self.writer_acted()

    # ---- steps and invariants
    def step(self):
        self.minute += 1
        if self.true_state in (issue.DONE,):
            return
        roll = self.rng.random()
        if roll < 0.40:
            # GitHub: a_tick_can_be_lost
            if not (self.faults and self.rng.random() < 0.3):
                self.poll()
            else:
                self.gap = True
        elif roll < 0.58:
            self.start_next()
        elif roll < 0.76:
            self.finish_run()
        elif roll < 0.90 or not self.people:
            self.platform()
        else:
            self.person()
        self.invariants()

    def invariants(self):
        self.check(len([r for r in self.runs if r["status"] == "in_progress"]) <= 1, "I-44 two Runs in flight")
        # GitHub: a_run_waits_its_turn
        self.check(len([r for r in self.runs if r["status"] in ("in_progress", "queued")]) <= 2,
                   "the lane holds more than one Run waiting behind the one that holds it")
        # I-40: factory:ready is added by nobody but the readiness App inside its Run, or a person.
        for ev in self.events:
            if ev["label"] == issue.LABEL_READY and ev["action"] == "labeled":
                self.check(self.is_person(ev["by"]) or ev["by"]["name"] == READINESS["name"],
                           "I-40 factory:ready added by %s" % ev["by"]["name"])
        # I-41: a label the Kernel counts was added by a person with write access or by its declared App.
        for state, name, app in (("triage", issue.LABEL_TRIAGE, CONTROLLER), ("ready", issue.LABEL_READY, READINESS)):
            adds = [ev for ev in self.events if ev["label"] == name and ev["action"] == "labeled"]
            if self.true_state == state and adds:
                self.check(self.is_person(adds[-1]["by"]) or adds[-1]["by"]["name"] == app["name"],
                           "I-41 %s counted though %s added it last" % (name, adds[-1]["by"]["name"]))
        # I-41: a Hold a person placed stands until a person removes it; a new life begins only by a writer.
        if self.reopened_last_by == "other":
            self.check(self.true_state in (issue.DECLINED, None),
                       "I-41 a reopening by someone without write access began a new life")
        # I-43: after a linked pull request closes without being done, the Factory opens at most max_unmerged_closes
        # more, until a person removes the Hold or begins a new life; an empty merge is such a close.
        released = [ev["at"] for ev in self.events
                    if ev["label"] == t.LABEL_HOLD and ev["action"] == "unlabeled" and self.is_person(ev["by"])]
        since = max([World.at(self.life_started)] + released)
        closes = [p["closed_at"] for p in self.linked if p["class"] in issue.MOVING_CLASSES and not p["open"]
                  and (p["merged_at"] is None or p["empty"]) and p["closed_at"] >= since]
        opened_after = [p for p in self.linked if p["class"] == "agent" and closes and p["opened_at"] > min(closes)]
        self.check(len(opened_after) <= LIMITS["max_unmerged_closes"], "I-43 the Factory opened past max_unmerged_closes")
        # I-39: with every unadmitted stranger's pull request read out, the State is the same, after every step.
        strangers = [p for p in self.linked if p["class"] == "outside" and not issue.admitted_once(p)]
        if strangers:
            facts = self.facts()
            without = dict(facts, linked=[p for p in facts["linked"] if p not in strangers])
            self.check(issue.derive(without, self.records(), CONFIG)["state"]
                       == issue.derive(facts, self.records(), CONFIG)["state"],
                       "I-39 a stranger's pull request moved the issue")
        # Issue 267: a pull request an edit after its merge made name the issue closed nothing: with it read out the
        # State is the same, or, within max_close_lag_seconds of its merge, the Kernel waits; never done, after every
        # step.
        if [p for p in self.linked if p["number"] in self.late]:
            facts = self.facts()
            without = dict(facts, linked=[p for p in facts["linked"] if p["number"] not in self.late])
            read, past = issue.derive(facts, self.records(), CONFIG), issue.derive(without, self.records(), CONFIG)
            self.check(read["state"] == past["state"] or (read["state"], read["reason"]) == (None, "merge_closing"),
                       "a reference an edit added after a merge moved the issue")
        # I-8: every act since a writer acted is under the ceiling, but the Hold that stops work, by one.
        ceiling = LIMITS["max_acts_per_item"]
        self.check(self.acts <= ceiling or (self.acts == ceiling + 1 and self.last_act == issue.PLACE_HOLD),
                   "I-8 acts since a writer exceed the ceiling")
        since = [r for r in self.runs if (self.last_writer is None or r["started_at"] > self.last_writer)
                 and r["outcome"] != "superseded"]
        self.check(len(since) <= LIMITS["max_runs_per_item"] + 1, "run ceiling per item")

    def settle(self, steps: int = 400):
        """Stop the faults and the people, and let the Factory finish."""
        self.faults = self.people = False
        last = None
        for _ in range(steps):
            self.step()
            if self.true_state in (issue.DONE, issue.DECLINED):
                break
        last = issue.decide(self.facts(), self.records(), self.unpaused(), CONFIG, self.now())
        return last


DECLARED_STATES = set(LIFECYCLE["states"])
