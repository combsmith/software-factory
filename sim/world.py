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
from tools import check_lifecycle
from tools.hooks import protected
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
# The Kernel is given the defaults, the Lifecycle whose staleness limits it reads, and the protected paths and Lenses'
# inputs from config/hooks.json.
CONFIG = dict(json.loads((ROOT / "config" / "defaults.json").read_text()), lifecycle=check_lifecycle.load(),
              protected_paths=protected.protected_paths())
DECISION_SCHEMA = json.loads((ROOT / "schemas" / "decision.schema.json").read_text())
FACTS_SCHEMA = json.loads((ROOT / "schemas" / "facts.schema.json").read_text())
DECLARED = check_lifecycle.declared(check_lifecycle.load())
ITEM = {"repo": "combsmith/software-factory", "type": "pull_request", "number": 1}
# Each required check, by its Lens's name, and the App that reports it: here, always that Lens's own.
APPS = {lens["lens"]: lens["app_id"] for lens in CONFIG["required_lenses"]["deterministic"]}
# The name GitHub gives each required check run, by its Lens's name.
CHECKS = {lens["lens"]: lens["check"] for lens in CONFIG["required_lenses"]["deterministic"]}
# The workflow file that runs each required check, by its Lens's name: null for a Lens no workflow runs.
WORKFLOWS = {lens["lens"]: lens["workflow"] for lens in CONFIG["required_lenses"]["deterministic"]}
# An App no Lens is read from, which can write checks: the Controller's own can post a check under any name.
IMPOSTOR_APP = 1000001
# A workflow file no Lens is read from: GitHub Actions, a Lens's own App, runs any job in the repo under any name, one a
# pull request adds on its own branch among them.
IMPOSTOR_WORKFLOW = ".github/workflows/impostor.yml"
# Who posts it, in the Lifecycle's words: the facts give only its App's id, and no Run or act of the Factory's posts a
# check under a Lens's name, so the change is the platform's (by_of).
IMPOSTOR = {"kind": "app", "name": "another-app[bot]", "can_write": True}
START = datetime.datetime(2026, 10, 11, 12, 0, 0)
# On an even seed the pull request is an agent's, and the Maintainer reviews it as a colleague's (UJ-4). On an odd
# seed it is the Maintainer's own, as the simulator has always served, and GitHub refuses a review by its author.
AUTHOR = "combsmith-sf-dev-lead[bot]"
MAINTAINER = {"kind": "human", "name": "don-petry", "can_write": True}
# The reviewer's App holds pull_requests: write, and GitHub cannot grant it less.
REVIEWER_APP = {"kind": "lens", "name": "pr-review", "can_write": True}
# The author's App: it pushes the agent's fixes, and can label and resolve threads, as any App with write access can.
AUTHOR_APP = {"kind": "app", "name": AUTHOR, "can_write": True}
# Someone with no write access, who can comment and nothing more.
STRANGER = {"kind": "human", "name": "stranger", "can_write": False}
# The machine user, which only approves.
MACHINE = {"kind": "machine_user", "name": CONFIG["approver"], "can_write": True}
# Invariants of rules the Kernel does not hold yet, each named by its test in tests/test_decide.py, which is marked
# @pending there. A breach of one is noted in `unheld`, not raised, until the mark comes off in both places.
NOT_YET_HELD = ()
# A Pause, on a span of minutes, on one seed in five; on another in five the Pause cannot be read for that span. Drawn
# from the seed alone, so the rest of each world stays as it was.
PAUSES = {0: True, 3: None}
PAUSE_FOR = 80
# The Holds the brakes place at a ceiling. Under a Pause they are not reached: the Pause defers first (decision 0003).
CEILINGS = ("attempts_exhausted", "run_ceiling", "max_rounds", "act_ceiling")
# On three seeds in seven the item has an acceptance contract (design §3.13), of this many criteria, by the seed alone.
# Seeds 1 and 2, which the tests set worlds up from by hand, have none. On an agent's pull request the last of two or
# more is of kind human, which only a person passes, by approving the content; every other is of kind test.
CONTRACTS = {0: 3, 3: 1, 5: 2}
# The check that alone reports a criterion of kind test, by the Lens the configuration names for it, and the person who
# approves the contract on the Maintainer's own pull request, which GitHub refuses them a review of.
REPORTER = {"name": CHECKS[CONFIG["acceptance_reporters"]["test"]], "app_id": APPS[CONFIG["acceptance_reporters"]["test"]],
            "workflow": WORKFLOWS[CONFIG["acceptance_reporters"]["test"]]}
COLLEAGUE = {"kind": "human", "name": "a-colleague", "can_write": True}
# On one seed in ten the item is a dependency bot's update, of class `dependency`, that the bot opened and pushed: on
# every other such seed it edits the pin in the workflow file the verify Lens is read from. By the seed alone.
DEPENDENCY_SEED = 4
DEPENDABOT = "dependabot[bot]"
# What each who changes the item may touch, in the world's own words: a path on the list, a protected path or a Lens's
# input, or one on neither. A Role's fix Run touches the tests, the dependency bot a workflow's pin, the Maintainer the
# brakes' limits. What a change touches draws from its own generator, so that the rest of each world stays as it was.
ON_THE_LIST = {"role": "tests/test_decide.py", "dependency": ".github/workflows/verify.yml",
               "maintainer": "config/defaults.json"}
OFF_THE_LIST = {"role": "docs/lessons.md", "dependency": "docs/requirements.txt", "maintainer": "docs/glossary.md"}
# On one seed in six, under faults, a review's Result leaves a criterion of its rubric uncovered half the time, which
# `apply` refuses before any Effect: the Run fails by a fault of the item (decision 0029). The Factory's own behaviour,
# not GitHub's, so it carries no marker. By the seed alone, so every other world stays as it was. The spread is narrowed
# for "Kernel: spent attempts hold the item even while a refused Run is queued" (issue 158): on more seeds, a Run list
# missing its newest Run admits a review past its attempts, and the State leaves the Hold while that Run waits. The fix
# for that issue widens it again.
UNCOVERED_SEEDS, UNCOVERED = 6, 0.5


class Broken(AssertionError):
    """An invariant did not hold."""


class World:
    def __init__(self, seed: int, faults: bool = True, people: bool = True,
                 approval_fails: str = None, queue_merges: bool = True):
        self.rng = random.Random(seed)
        # What an App does out of turn draws from its own generator, so that the rest of a seed's world stays as it was.
        self.meddler = random.Random(-seed)
        self.seed, self.faults, self.people = seed, faults, people
        # Worlds that never end on their own: an approval that never lands, failing every time with the
        # fault `approval_fails` names ("item" or "environment"), and a queue that ejects every time.
        self.approval_fails, self.queue_merges = approval_fails, queue_merges
        self.minute = 0
        self.content = 1
        self.pr_state = "open"
        self.cls = "maintainer" if seed % 2 else "agent"
        self.author = self.last_pusher = AUTHOR if self.cls == "agent" else MAINTAINER["name"]
        # The paths the pull request changes, and who has touched one on the list (ON_THE_LIST), from its own generator.
        self.paths = random.Random("paths %d" % seed)
        self.listed_by = set()
        if seed % 10 == DEPENDENCY_SEED:
            # GitHub: a_dependency_bot_updates_a_workflow_pin
            self.cls, self.author = "dependency", DEPENDABOT
            self.last_pusher = self.author
            self.changed = {self.touched_by("dependency", on=seed // 10 % 2 == 0)}
        else:
            self.changed = {self.touched_by("role" if self.cls == "agent" else "maintainer")}
        self.asked = False         # the Maintainer's request for changes stands, as the world keeps it
        self.unheld = []           # breaches of invariants the Kernel does not hold yet (NOT_YET_HELD)
        self.labels = set()        # the labels on the pull request, as GitHub shows them
        self.events = []           # the timeline's labeled and unlabeled events
        # What binds, in the world's own words: a Hold stands until a person removes it, whoever placed it or took the
        # label off since; hands-off stands as it was placed, by a person or by an App, until a person removes it.
        self.hold, self.hands_off = False, None
        self.threads, self.reviews, self.runs = [], [], []
        self.checks = dict.fromkeys(APPS, "pending")
        self.completed = dict.fromkeys(self.checks)   # when each check completed, or None
        self.impostors = []        # checks another App posted under a required Lens's name, on this head
        self.rerun = set()         # the checks a person ran again on this head, whose verdicts are that person's
        self.queue = False
        self.last_push = self.now()
        # On one seed in three no person with write access has acted on the item yet: GitHub gives no time for it.
        self.last_writer = None if seed % 3 == 0 else self.now()
        # The Pause: on some seeds, from a minute the seed gives, for PAUSE_FOR minutes; True, or None if unreadable.
        self.pause_from = 10 + seed * 37 % 200 if seed % 5 in PAUSES else None
        self.pause_reading = PAUSES.get(seed % 5)
        self.paused_passes = 0     # passes made while paused, or while the Pause could not be read
        self.stopped = []          # what each of those passes would have done with no Pause, when it was to act
        # The world's own clock for staleness, in minutes, kept apart from the facts the Kernel reads: when a writer,
        # a Lens or the Factory last moved the item, and when the current unbroken chain of passes began.
        self.moved = self.chain = self.minute
        self.gap = False                 # a tick was lost since the last pass, which breaks the chain
        self.acts = 0              # acts that landed since a person with write access acted
        self.last_act = None       # the action of the last act that landed: an act that stops work is never refused
        self.stale = None          # an older snapshot, served when facts go stale
        self.read = None           # the facts the last whole, current pass read, as `unstamped` gives them
        self.made = set()          # each transition a change made, as (from, to, by)
        self.trace = []
        self.model_runs = 0
        # The acceptance contract's criteria, or None for an item with none, and every result a Lens has given for one,
        # with the content it was given on. A result stays when the content changes: it is then evidence for other
        # content. What concerns the contract draws from its own generator, so that a world with none stays as it was.
        self.criteria = ["AC-%d" % (i + 1) for i in range(CONTRACTS.get(seed % 7, 0))] or None
        self.kinds = {c: "test" for c in self.criteria or []}
        if self.cls == "agent" and len(self.kinds) > 1:
            self.kinds[self.criteria[-1]] = t.HUMAN_KIND
        self.results = []
        self.judge = random.Random("acceptance %d" % seed)
        # Whether a review's Result covers its rubric draws from its own generator, so the rest of each world stays as it
        # was until a review leaves a criterion uncovered.
        self.coverage = random.Random("coverage %d" % seed)
        # The contract's digest at the head, which a push that edits it or a test it names changes, None once deleted;
        # and the contract a person approved, at the head, or on one seed in three not yet (I-29). Whether there is a
        # contract at all is the linked issue's, and never changes here.
        self.revision = 1
        self.head = self.digest() if self.criteria else None
        self.contract_person = MAINTAINER if self.cls == "agent" else COLLEAGUE
        self.approved = None
        if self.criteria and self.judge.random() >= 0.3:
            # The person approved the contract at the work's first commit, before the head was pushed (§4.8).
            self.reviews.append({"by": dict(self.contract_person), "state": "approved", "commit": "c0",
                                 "content_id": "sha256:c0c0", "submitted_at": self.at(-1), "dismissed_by": None,
                                 "dismissed_from": None})
            self.approve_contract(self.contract_person, "c0")
        self.true_state = None     # the State the Kernel gives what GitHub holds now, after the last change
        self.starts()

    def starts(self):
        """The world as it stands is where it starts: the State the Kernel gives it is no transition, and the next
        change is checked from it. A test that sets a world up by hand says so here."""
        self.true_state = decide(self.facts(), self.records(), self.unpaused(), CONFIG, self.now())["state"]

    def touched_by(self, who: str, on=None) -> str:
        """What a change `who` makes touches: on the list now and then, or as `on` says."""
        if on is None:
            on = self.paths.random() < 0.3
        if on:
            self.listed_by.add(who)
        return (ON_THE_LIST if on else OFF_THE_LIST)[who]

    def on_the_list(self, paths) -> bool:
        """Whether a change to `paths` changes the Factory's own rules or a Lens's input, in the world's own words."""
        return any(p in ON_THE_LIST.values() for p in paths)

    def needs_review(self) -> bool:
        """Whether every model Lens must review the item, in the world's own words: all but a dependency bot's update
        that the bot pushed last and that changes nothing on the list."""
        return not (self.cls == "dependency" and self.last_pusher == self.author and not self.on_the_list(self.changed))

    def reviewed(self, runs: list, content: str) -> bool:
        """Whether every model Lens has reviewed `content`, in the world's own words."""
        return all(any(r["role"] == lens and r["intent"] == "review-change" and r["content_id"] == content
                       and r["status"] == "completed" and r["conclusion"] == "success" for r in runs)
                   for lens in CONFIG["required_lenses"]["model"])

    def pick(self, options):
        """Choose with random() only, whose sequence is the same on every Python version."""
        options = list(options)
        return options[int(self.rng.random() * len(options))]

    # ---- time and facts
    def now(self) -> str:
        return self.at(self.minute)

    @staticmethod
    def at(minute: int) -> str:
        return (START + datetime.timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def moves(self):
        """A writer, a Lens or the Factory moved the item, as the ruling on #36 counts it. A stranger never does."""
        self.moved = self.minute

    def cid(self) -> str:
        return "sha256:%04x" % self.content

    def facts(self) -> dict:
        return {
            "schema": "facts/1", "item": dict(ITEM), "state": self.pr_state, "is_draft": False,
            "class": self.cls, "author": self.author, "last_pusher": self.last_pusher,
            "targets_protected": True, "mergeable": True, "content_id": self.cid(),
            "diff": {"files": len(self.changed), "lines": 40, "truncated": False},
            # GitHub: a_pull_request_lists_the_paths_it_changes
            "changed_paths": [{"path": p, "previous": None} for p in sorted(self.changed)],
            "label_events": copy.deepcopy(self.events),
            "last_push_at": self.last_push, "last_writer_action_at": self.last_writer,
            # GitHub: an_actor_has_a_kind
            "reviews": copy.deepcopy(self.reviews), "threads": copy.deepcopy(self.threads),
            # GitHub: a_check_is_read_by_name_from_every_app
            # GitHub: a_check_names_the_workflow_that_ran_it
            "checks": [{"name": CHECKS[k], "app_id": APPS[k], "workflow": WORKFLOWS[k], "conclusion": v,
                        "completed_at": self.completed.get(k)}
                       for k, v in sorted(self.checks.items())] + copy.deepcopy(self.impostors),
            "queue": self.queue,
            # GitHub: the_timeline_shows_each_act
            "acts_since_writer": self.acts,
            # GitHub: an_acceptance_result_names_its_content
            # GitHub: an_acceptance_result_names_its_reporter
            # GitHub: a_contract_approval_stays_on_its_commit
            "acceptance": self.acceptance(),
            "complete": {"acceptance": True, "reviews": True, "threads": True, "checks": True, "diff": True,
                         "changed_paths": True, "runs": True, "timeline": True},
            "read_at": self.now(),
        }

    def digest(self) -> str:
        """The digest of the contract and every path it protects, at its current revision."""
        return "sha256:%064x" % (0xc0de0000 + self.revision)

    def acceptance(self):
        """The acceptance contract as the facts carry it, or None for an item whose issue asks for none."""
        if self.criteria is None:
            return None
        return {"approved": copy.deepcopy(self.approved), "head": self.head, "results": copy.deepcopy(self.results)}

    def approve_contract(self, by: dict, commit: str = None):
        """`by`, a person, approves the contract at the head with an approving review of the content, which also
        confirms every criterion of kind human there (the Maintainer's ruling of 2026-10-17). None to approve once the
        head carries none."""
        if self.criteria is None or self.head is None:
            return
        self.approved = {"digest": self.head, "commit": commit or "c%d" % self.content, "by": dict(by),
                         "criteria": [{"id": c, "kind": self.kinds[c]} for c in self.criteria]}

    def agreed(self) -> bool:
        """Whether a person approved the contract, and the head still carries what they approved, in the world's own
        words. An item with no contract asks nothing."""
        return self.criteria is None or (self.approved is not None and self.is_person(self.approved["by"])
                                         and self.head == self.approved["digest"])

    def records(self) -> list:
        """What the records port lists: every Run, including one still waiting for a runner."""
        # GitHub: a_queued_run_is_listed
        return [copy.deepcopy(r) for r in self.runs]

    def pausing(self) -> bool:
        """The Pause stands now, or cannot be read."""
        return self.pause_from is not None and self.pause_from <= self.minute < self.pause_from + PAUSE_FOR

    def context(self) -> dict:
        active = len([r for r in self.runs if r["status"] != "completed"])
        ctx = {"paused": False, "active_runs": active, "model_deferred_until": None,
               "passes_since": self.at(self.chain)}
        if self.pausing():
            if self.pause_reading is None:
                del ctx["paused"]       # the Controller could not read whether Admission is paused
            else:
                ctx["paused"] = self.pause_reading
        return ctx

    def unpaused(self) -> dict:
        """The context with no Pause. The State is the item's, and a Pause is the Controller's, not the item's."""
        return dict(self.context(), paused=False)

    def writer_acted(self):
        """A person with write access acted: a fresh allowance of attempts, and of acts (I-28)."""
        self.last_writer = self.now()
        self.acts = 0
        self.moves()

    def held(self) -> bool:
        """A Hold stands, or hands-off, which stops work whoever placed it."""
        return self.hold or self.hands_off is not None

    def labelling(self, name: str, action: str, by: dict):
        """Record a label event. Each takes its own minute, so the world never leans on how a tie is read."""
        if self.events and self.events[-1]["at"] >= self.now():
            self.minute += 1
        # GitHub: a_label_event_names_its_actor
        self.events.append({"label": name, "action": action, "by": dict(by), "at": self.now()})

    @staticmethod
    def is_person(by: dict) -> bool:
        return by["kind"] == "human" and by["can_write"] is True

    def label(self, name: str, by: dict):
        """`by` adds the label. Anyone else adding hands-off again does not replace a person's: it stands as theirs."""
        self.labels.add(name)
        self.labelling(name, "labeled", by)
        if name == t.LABEL_HOLD:
            self.hold = True
        elif name == t.LABEL_HANDS_OFF and not (self.hands_off == "person" and not self.is_person(by)):
            self.hands_off = "person" if self.is_person(by) else "app"

    def unlabel(self, name: str, by: dict):
        """`by` removes the label. Only a person's removal ends what it held: anyone else's leaves it binding."""
        self.labels.discard(name)
        self.labelling(name, "unlabeled", by)
        if self.is_person(by):
            if name == t.LABEL_HOLD:
                self.hold = False
            elif name == t.LABEL_HANDS_OFF:
                self.hands_off = None

    def release(self):
        """The Maintainer ends a Hold and hands-off. A label an App took off is put back to be taken off again."""
        for name, binds in ((t.LABEL_HOLD, self.hold), (t.LABEL_HANDS_OFF, self.hands_off is not None)):
            if binds:
                if name not in self.labels:
                    self.label(name, MAINTAINER)
                self.unlabel(name, MAINTAINER)

    @staticmethod
    def open_for(th: dict) -> bool:
        """A person's thread is open until that person resolves it, whoever else has (L-17)."""
        return th["opened_by"]["kind"] == "human" and th["resolved_by"] != MAINTAINER

    @staticmethod
    def unstamped(facts: dict) -> dict:
        """Facts without the time they were read, so that two reads of an unchanged item compare equal."""
        return {k: v for k, v in facts.items() if k != "read_at"}

    def objections(self) -> list:
        """What a queued item may not merge over, in the world's own words: no approval of its content by the
        approver that stands, a writer's request for changes or open thread, a Hold, or a required check that
        failed or gave no verdict (L-19, FR-23, I-9). A check still pending is a wait, and is no objection."""
        out = []
        if not any(rv["by"]["name"] == CONFIG["approver"] and rv["state"] == "approved" and rv["content_id"] == self.cid()
                   for rv in self.reviews):
            out.append("no standing approval")
        if self.asked:
            out.append("a writer's request for changes")
        if any(self.open_for(th) for th in self.threads):
            out.append("a writer's open thread")
        if self.hold or self.hands_off == "app":
            out.append("a Hold")
        if any(v not in ("success", "pending") for v in self.checks.values()):
            out.append("a required check that failed or gave no verdict")
        if self.impostors:
            out.append("another App's check under a required Lens's name")
        if not self.agreed():
            out.append("a contract no person approved, or one changed since")
        if not self.accepted(self.acceptance(), self.reviews, self.cid()):
            out.append("a criterion with no passing evidence on this content from its reporter")
        return out

    @classmethod
    def accepted(cls, acceptance, reviews: list, content: str) -> bool:
        """Whether a contract counts and every criterion passes on `content`, in the world's own words; an item with no
        contract asks nothing. A person approved the contract, and the head carries what they approved (I-29); each
        result on `content` is for a criterion of kind test, from the reporter's own check, and each such criterion
        has a passing one and none failing (I-10, I-31); and a person's approving review of `content` stands, unless a
        person dismissed it, for each criterion of kind human."""
        if acceptance is None:
            return True
        approved = acceptance["approved"]
        if approved is None or not cls.is_person(approved["by"]) or acceptance["head"] != approved["digest"]:
            return False
        kinds = {c["id"]: c["kind"] for c in approved["criteria"]}
        mine = [ev for ev in acceptance["results"] if ev["content_id"] == content]
        if any(kinds.get(ev["criterion"]) != "test" or ev["check"] != REPORTER for ev in mine):
            return False
        person = cls.confirmed(reviews, content)
        return all(person if kind == t.HUMAN_KIND else {ev["result"] for ev in mine if ev["criterion"] == c} == {"passing"}
                   for c, kind in kinds.items())

    @classmethod
    def confirmed(cls, reviews: list, content: str) -> bool:
        """Whether a person's approving review of `content` stands, unless a person dismissed it, in the world's words."""
        return any(cls.is_person(rv["by"]) and rv["content_id"] == content
                   and (rv["state"] == "approved" or (rv["dismissed_from"] == "approved"
                                                      and not cls.is_person(rv["dismissed_by"])))
                   for rv in reviews)

    def note(self, what: str):
        self.trace.append("%s %s" % (self.now(), what))

    def check(self, ok: bool, invariant: str):
        if not ok:
            raise Broken("seed %d broke %s\n%s" % (self.seed, invariant, "\n".join(self.trace[-25:])))

    def check_unheld(self, ok: bool, test: str, invariant: str):
        """`check`, for a rule whose test is still marked @pending: a breach is noted, and raised once it is held."""
        if test not in NOT_YET_HELD:
            self.check(ok, invariant)
        elif not ok:
            self.unheld.append(test)
            self.note("not held yet: %s" % invariant)

    @classmethod
    def by_of(cls, actor: dict) -> str:
        """Who makes what `actor` does, in the Lifecycle's words. A Role's App, such as the author's, writes only inside
        a Run, with a token minted for it (decision 0005), so what it does is the Factory's, in turn or not. Any other
        App is the platform's. Someone with no write access is nobody the Lifecycle names: nothing they do may change a
        State."""
        if cls.is_person(actor):
            return "human"
        if actor["kind"] == "lens":
            return "lens"
        if actor["kind"] == t.MACHINE_USER or actor == AUTHOR_APP:
            return "factory"
        return "platform" if actor["kind"] == t.APP else "stranger"

    def caused(self, by: str):
        """A change was just made by `by`. If it changed the State the Kernel gives what GitHub holds, the Lifecycle
        declares that transition, made by `by` (I-12)."""
        state = decide(self.facts(), self.records(), self.unpaused(), CONFIG, self.now())["state"]
        if state is None:
            return
        if state != self.true_state:
            self.made.add((self.true_state, state, by))
            self.check((self.true_state, state, by) in DECLARED,
                       "I-12 undeclared transition %s -> %s by %s" % (self.true_state, state, by))
        self.true_state = state

    # ---- the poller
    def poll(self):
        if self.gap:
            # The poller's own records: a pass after a lost tick starts a new chain.
            self.chain, self.gap = self.minute, False
        facts, runs = self.facts(), self.records()
        fault = self.rng.random() if self.faults else 1.0
        current = exact = True
        if fault < 0.08 and self.stale is not None:
            # GitHub: a_read_can_be_stale
            facts, runs = self.stale
            current = exact = False
        elif fault < 0.14:
            # GitHub: a_short_diff_says_so
            # GitHub: a_short_list_says_so
            facts["complete"][self.pick(sorted(k for k in facts["complete"]
                                               if k not in ("runs", "acceptance", "changed_paths")))] = False
            if self.paths.random() < 0.3:
                # The list of paths is read short in the same pass, so the rest of the world stays as it was.
                # GitHub: a_short_path_list_says_so
                facts["complete"]["changed_paths"] = False
                self.note("the paths were read short")
        elif fault < 0.20 and runs:
            # GitHub: a_new_run_is_listed_late
            runs = runs[:-1]
            exact = False
        elif fault < 0.25 and runs:
            # GitHub: a_run_list_stops_short
            runs = runs[self.pick(range(1, len(runs) + 1)):]
            facts["complete"]["runs"] = False
        self.stale = (copy.deepcopy(facts), copy.deepcopy(runs))
        if self.cls == "dependency" and self.faults and self.paths.random() < 0.1:
            # A list said to be whole leaves a path out. Only on a dependency bot's update, so every other world stays as
            # it was. The schema refuses a path that cannot be read, so a list too short is the misread fed here.
            # GitHub: a_path_list_can_leave_out_a_file
            facts["changed_paths"] = facts["changed_paths"][:-1]
            self.note("a path was left out of the list")
        if facts["acceptance"] is not None and self.faults and self.judge.random() < 0.2:
            # The contract was read short, or a result on this content names a criterion it does not.
            if self.judge.random() < 0.3:
                # GitHub: a_short_acceptance_read_says_so
                facts["complete"]["acceptance"] = False
            else:
                # GitHub: a_result_can_name_a_criterion_the_contract_does_not
                facts["acceptance"]["results"].append({"criterion": "AC-%d" % (len(self.criteria) + 1),
                                                        "content_id": facts["content_id"], "result": "passing",
                                                        "check": dict(REPORTER)})
        wrong = validate(facts, FACTS_SCHEMA)
        self.check(not wrong, "facts are valid: %s" % "; ".join(wrong))
        d = decide(facts, runs, self.context(), CONFIG, self.now())
        wrong = validate(d, DECISION_SCHEMA)
        self.check(not wrong, "every Decision is valid: %s" % "; ".join(wrong))
        self.note("pass: %s %s -> %s" % (d["state"], d["reason"], d["outcome"]))
        if d["attention"] == t.STALE:
            # A wait past its limit changes what the Maintainer sees, never what happens, and only on a wait (I-1).
            calm = decide(facts, runs, dict(self.context(), passes_since=self.now()), CONFIG, self.now())
            self.check(dict(d, attention=calm["attention"]) == calm, "I-1 staleness changes what happens")
            self.check(calm["attention"] in t.MAY_GO_STALE, "I-1 a %s item shown as stale" % calm["attention"])
        if exact and d["state"] is not None and d["reason"] not in t.SCOPE_DEFERRALS and \
                d["attention"] in t.MAY_GO_STALE | {t.STALE}:
            # The world's own count: a wait is stale exactly when it ran past its State's limit while passes ran.
            waited = self.minute - max(self.moved, self.chain)
            limit = CONFIG["lifecycle"]["stale_after_minutes"][d["state"]]
            self.check((d["attention"] == t.STALE) == (waited > limit),
                       "I-1 a %s item that waited %d minutes of %d shown as %s" % (d["state"], waited, limit,
                                                                                   d["attention"]))
        acceptance = facts["acceptance"]
        if acceptance is not None:
            # No Run is admitted, and nothing converges or stays in the queue, unless a person approved the contract and
            # the head still carries what they approved (I-29). An item with a contract converges, and stays in the
            # queue, only with every criterion passing on the content it was read at, read in full: from its kind's
            # reporter alone, a person's approval for a criterion of kind human (I-10, I-31). Evidence for other content
            # counts for nothing. A result on this content for a criterion the contract does not name, or from anyone but
            # its reporter, makes it unreadable, which admits nothing and is the Maintainer's to see, as each Hold is
            # (I-13). A read short is incomplete, and checked with the other flags.
            approved = acceptance["approved"]
            agreed = approved is not None and self.is_person(approved["by"]) and acceptance["head"] == approved["digest"]
            self.check(agreed or d["outcome"] != t.ADMIT,
                       "I-29 a Run admitted on a contract no person approved, or one changed since")
            ok = facts["complete"]["acceptance"] and self.accepted(acceptance, facts["reviews"], facts["content_id"])
            self.check(ok or d["state"] not in (t.CONVERGED, t.QUEUED),
                       "I-31 %s with a criterion lacking passing evidence from its reporter" % d["state"])
            self.check(d["reason"] not in ("acceptance_unreadable", "contract_not_approved", "contract_changed")
                       or d["attention"] == t.NEEDS_YOU, "%s is not shown as needing a person" % d["reason"])
        # Nothing that changes the list is approved, enqueued or left in the queue without every model Lens's review
        # of its head, whatever its class (I-45). What it changes is the world's own: what it holds now, or for a
        # stale read, what it held then, which a stale read holds whole. A list read short is incomplete, and checked
        # with the other flags.
        listed = self.on_the_list(self.changed) if current else self.on_the_list(p["path"] for p in facts["changed_paths"])
        moves_on = d["outcome"] == t.ACT and d["action"] in ("issue_approval", "enqueue")
        self.check(not (listed and (moves_on or d["state"] == t.QUEUED)) or self.reviewed(runs, facts["content_id"]),
                   "I-45 %s %s on a change to the list with no review of its head" % (d["state"], d["reason"]))
        # A list of files other than the diff's admits nothing and acts on nothing but a dequeue, and is the
        # Maintainer's to see; read of an item queued now, as it is now, it takes the item out unless the Pause or the
        # Maintainer's hands-off keeps it where it is (I-13).
        short = len(facts["changed_paths"]) != facts["diff"]["files"]
        self.check(not short or not (d["outcome"] == t.ADMIT or (d["outcome"] == t.ACT and d["action"] != "dequeue")),
                   "I-13 %s %s on a list of paths shorter than the diff" % (d["outcome"], d["reason"]))
        if short and current and self.queue and not self.pausing() and self.hands_off != "person":
            self.check((d["outcome"], d.get("action")) == (t.ACT, "dequeue"),
                       "a queued item stays in the queue on a list of paths shorter than the diff")
        self.check(d["reason"] != "paths_unreadable" or d["attention"] == t.NEEDS_YOU,
                   "unreadable paths are not shown as needing a person")
        whole = all(facts["complete"].values())
        # A read that fails stops work: it defers, or takes a queued item out of the merge queue (I-13).
        dequeue = d["outcome"] == t.ACT and d["action"] == "dequeue"
        self.check(whole or d["outcome"] == "defer" or dequeue, "I-20 incomplete facts never admit or converge")
        # A check with no verdict lets no review start and no act be made. A fix Run may still be admitted
        # for what is readable: another check that failed, or a conflict.
        readings = CONFIG["check_conclusions"]
        no_verdict = [c for c in facts["checks"] if readings.get(c["conclusion"], "unreadable") == "unreadable"]
        reviews = d["outcome"] == "admit" and d["admit"]["intent"] == "review-change"
        self.check(not no_verdict or not (reviews or (d["outcome"] == "act" and not dequeue)),
                   "I-13 a review or an act while a check has no verdict")
        # Another App's check, or another workflow file's, under a required Lens's name lets no Run start and no act be
        # made but a dequeue, not even a fix for a check that failed.
        own = {CHECKS[lens]: (APPS[lens], WORKFLOWS[lens]) for lens in APPS}
        foreign = [c for c in facts["checks"] if (c["app_id"], c["workflow"]) != own[c["name"]]]
        self.check(not foreign or not (d["outcome"] == t.ADMIT or (d["outcome"] == t.ACT and not dequeue)),
                   "I-13 something done while another App's or workflow's check stands under a Lens's name")
        waits = d["reason"] == "check_unreadable" and d["outcome"] == t.DEFER
        self.check(not waits or d["attention"] == t.NEEDS_YOU,
                   "a check with no verdict is not shown as needing a person")
        if whole and current:
            # A Hold that only a person may end, or hands-off, admits no Run and makes no act but a dequeue, whoever took
            # the label off since (I-6, I-21).
            self.check(not self.held() or d["outcome"] not in (t.ADMIT, t.ACT) or dequeue,
                       "I-6 a held item moved on: %s %s" % (d["outcome"], d["reason"]))
            # A pass that reads a queued item whole, as it is now, takes it out if it may not merge (L-19). Under a Pause
            # it may not: the dequeue defers (paused), and such a pass reads nothing the queue may merge on.
            stop = self.queue and self.objections()
            if not self.pausing():
                self.check(not stop or (d["outcome"], d.get("action")) == (t.ACT, "dequeue"),
                           "a pass leaves a queued item in the queue over %s" % ", ".join(stop or []))
                self.read = self.unstamped(facts)
        if self.pausing():
            self.paused(facts, runs, d)
        if d["outcome"] == "admit":
            self.moves()
            self.runs.append({"run": "r%d" % len(self.runs), "item": dict(ITEM), "role": d["admit"]["role"],
                              "intent": d["admit"]["intent"], "content_id": d["admit"]["content_id"],
                              "status": "queued", "conclusion": None, "outcome": None, "started_at": self.now()})
            self.caused("factory")
        elif d["outcome"] == "act":
            self.apply_action(d)
            self.caused("factory")

    def paused(self, facts: dict, runs: list, d: dict):
        """Under a Pause, or one that cannot be read, nothing is admitted and nothing acts, not even a dequeue. A Hold
        the facts establish shows first; anything else that would go ahead defers for the Pause, and a dequeue so
        deferred is the Maintainer's to see (decision 0003)."""
        self.paused_passes += 1
        self.check(d["outcome"] not in (t.ADMIT, t.ACT), "a Pause let through %s %s" % (d["outcome"], d["reason"]))
        free = decide(facts, runs, dict(self.context(), paused=False), CONFIG, self.now())
        why = "paused" if self.pause_reading else "pause_unreadable"
        if free["outcome"] in (t.ADMIT, t.ACT) or (free["outcome"] == t.HOLD and free["reason"] in CEILINGS):
            self.stopped.append(free.get("action") or free["outcome"])
            self.check((d["outcome"], d["reason"]) == (t.DEFER, why),
                       "a Pause did not defer %s %s" % (free["outcome"], free["reason"]))
        if free.get("action") == "dequeue":
            self.check(d["attention"] == t.NEEDS_YOU, "a dequeue deferred by a Pause is not the Maintainer's to see")
        if free["outcome"] == t.HOLD and free["reason"] not in CEILINGS:
            self.check(d == free, "a Hold the facts establish is hidden by a Pause")

    # ---- an act: a change that needs no model
    def apply_action(self, d: dict):
        # The act is made only if the Kernel, asked again on what GitHub holds now, still wants it.
        fresh = decide(self.facts(), self.records(), self.context(), CONFIG, self.now())
        same = fresh["outcome"] == t.ACT and fresh["action"] == d["action"] and fresh["content_id"] == d["content_id"]
        # Taking it out of the queue is the one change made to a held item: it stops work (I-21).
        if (self.held() and d["action"] != "dequeue") or d["content_id"] != self.cid() or not same:
            self.note("apply: refused, the item changed")
            return
        if d["action"] == "dequeue":
            # GitHub: an_app_leaves_the_queue
            self.queue = False
            self.acts += 1
            self.last_act = "dequeue"
            self.note("apply: dequeued (%s)" % d["reason"])
            return
        # Only that person's approval, or a writer's dismissal, ends it: never new content or an App (L-17).
        self.check(not self.asked, "a writer's request for changes is passed over")
        if d["action"] == "issue_approval":
            self.approve()
        elif d["action"] == "enqueue":
            self.check(not self.on_the_list(self.changed) or self.reviewed(self.runs, self.cid()),
                       "I-45 a change to the list enqueued with no review of its head")
            # GitHub: an_app_enters_the_queue
            self.queue = True
            self.acts += 1
            self.last_act = "enqueue"
            self.note("apply: enqueued")

    def approve(self):
        """A Run with no Engine: its `apply` alone holds the machine user's token, and its record counts attempts."""
        self.check(CONFIG["approver"] not in (self.author, self.last_pusher), "I-26 approver is author or last pusher")
        self.check(not self.on_the_list(self.changed) or self.reviewed(self.runs, self.cid()),
                   "I-45 a change to the list approved with no review of its head")
        self.check(not self.needs_review() or self.reviewed(self.runs, self.cid()),
                   "I-37 approved with no successful review of its content by every required model Lens")
        self.moves()
        run = {"run": "r%d" % len(self.runs), "item": dict(ITEM), "role": CONFIG["owner_role"],
               "intent": t.ISSUE_APPROVAL, "content_id": self.cid(), "status": "completed",
               "conclusion": "success", "outcome": None, "started_at": self.now()}
        self.runs.append(run)
        fault = self.approval_fails
        if fault is None and self.faults and self.rng.random() < 0.15:
            fault = self.pick(["item", "environment", "capacity"])
        if fault is not None:
            # GitHub: an_approval_can_fail_to_land
            run.update(conclusion="failure", outcome=fault)
            self.note("run %s: the approval did not land" % run["run"])
            return
        # GitHub: the_machine_users_approval_counts
        self.reviews.append({"by": dict(MACHINE), "state": "approved",
                             "commit": "c%d" % self.content, "content_id": self.cid(), "submitted_at": self.now(),
                             "dismissed_by": None, "dismissed_from": None})
        self.acts += 1
        self.last_act = "issue_approval"
        self.note("run %s: approved %s" % (run["run"], self.cid()))

    # ---- the lane: one Run at a time, and each asks the Kernel again as it starts
    def start_next(self):
        # GitHub: a_run_waits_its_turn
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
            # GitHub: a_superseded_run_fails
            run.update(status="completed", conclusion="failure", outcome="superseded")
            self.note("run %s: superseded before it started" % run["run"])
            self.caused("factory")
            return
        run["status"] = "in_progress"
        self.caused("factory")
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
        self.ending(run)
        # A Lens's verdict is the Lens's report; every other end of a Run, a review that gave none among them, is the
        # Factory's.
        self.caused("lens" if run["intent"] == "review-change" and run["conclusion"] == "success" else "factory")

    def ending(self, run: dict):
        run["status"] = "completed"
        if self.faults and self.rng.random() < 0.12:
            # GitHub: a_killed_job_times_out
            run.update(conclusion="timed_out", outcome=self.pick(["item", "capacity", "environment"]))
            self.note("run %s: killed (%s)" % (run["run"], run["outcome"]))
            return
        if self.held() or not self.agreed() or run["content_id"] != self.cid() or self.pr_state != "open":
            # GitHub: a_superseded_run_fails
            run.update(conclusion="failure", outcome="superseded")   # apply read the item again
            self.note("run %s: apply refused, the item changed" % run["run"])
            return
        self.check(not self.held(), "I-21 an Effect on a held item")
        if (run["intent"] == "review-change" and self.faults and self.seed % UNCOVERED_SEEDS == 0
                and self.coverage.random() < UNCOVERED):
            # The Result left a criterion uncovered. `apply` refuses it before any Effect, so no thread opens (I-5).
            run.update(conclusion="failure", outcome="item")
            self.note("run %s: the review left a criterion uncovered" % run["run"])
            return
        run["conclusion"] = "success"
        if run["intent"] == "review-change":
            if self.rng.random() < 0.5:
                # GitHub: a_lens_review_opens_a_thread
                category, severity = self.pick(["functional", "security", "architecture"]), \
                    self.pick(["blocking", "major", "minor"])
                # A Finding that does not gate is an annotation on the Lens's check run, never a thread; a minor
                # security Finding gates as a major one does, so it is one: severity is never how one gets merged.
                if severity != "minor" or category == "security":
                    self.moves()
                    self.threads.append({"id": "T%d" % len(self.threads), "resolved": False,
                                         "opened_by": {"kind": "lens", "name": "pr-review", "can_write": True},
                                         "category": category, "severity": severity, "resolved_by": None,
                                         "opened_at": self.now()})
        elif run["intent"] == "fix-findings":
            # GitHub: an_app_pushes_to_the_head
            self.push("combsmith-sf-dev-lead[bot]", writer=False)
        elif run["intent"] == "adjudicate-findings":
            # GitHub: an_app_resolves_a_lens_thread
            for th in self.threads:
                if not th["resolved"] and th["opened_by"]["kind"] == "lens" and self.rng.random() < 0.7:
                    th.update(resolved=True, resolved_by=dict(REVIEWER_APP))
        self.note("run %s: applied" % run["run"])

    # ---- the platform and the people
    def push(self, who: str, writer: bool):
        # GitHub: a_push_is_new_content
        self.content += 1
        self.changed.add(self.touched_by("role" if who == AUTHOR else "maintainer"))
        # GitHub: the_pusher_is_the_last_pusher
        self.last_pusher, self.last_push = who, self.now()
        self.moves()
        if writer:
            self.writer_acted()
        # GitHub: a_push_restarts_the_checks
        self.checks = dict.fromkeys(self.checks, "pending")
        self.completed = dict.fromkeys(self.checks)
        # A check run cannot be deleted: another App's stays on the head it was posted on, and the new head has none.
        self.impostors = []
        self.rerun = set()
        # GitHub: a_push_leaves_the_queue
        self.queue = False
        if self.head is not None and self.faults and self.judge.random() < 0.15:
            # A push edits the contract or a test it names, or deletes the contract: its digest changes, and a person
            # must approve it again. That `apply` refuses the implementing Role's edit waits on harness/ (I-30).
            # GitHub: a_push_can_change_the_contract
            if self.judge.random() < 0.2:
                self.head = None
                self.note("the push deleted the contract")
            else:
                self.revision += 1
                self.head = self.digest()
                self.note("the push changed the contract -> %s" % self.head)
        # GitHub: an_approval_survives_a_push
        # GitHub: a_request_for_changes_survives_a_push
        self.note("push by %s -> %s" % (who, self.cid()))

    def stranger_comments(self):
        """A review that only comments, by someone with no write access. It moves nothing: else a comment every half
        hour would keep a stall from showing."""
        # GitHub: anyone_can_comment
        self.reviews.append({"by": dict(STRANGER), "state": "commented",
                             "commit": "c%d" % self.content, "content_id": self.cid(), "submitted_at": self.now(),
                             "dismissed_by": None, "dismissed_from": None})
        self.note("a stranger commented")

    def an_app_meddles(self) -> bool:
        """An App with write access does what only a person's act should: it takes a Hold off, adds hands-off, or
        resolves a person's thread. None of it ends anything (L-17), and hands-off it placed stops work as a Hold."""
        acts = []
        if t.LABEL_HOLD in self.labels:
            acts.append("unhold")
        if t.LABEL_HANDS_OFF not in self.labels:
            acts.append("hands-off")
        if any(th["opened_by"]["kind"] == "human" and not th["resolved"] for th in self.threads):
            acts.append("resolve")
        if not acts:
            return False
        act = acts[int(self.meddler.random() * len(acts))]
        if act == "resolve":
            # GitHub: an_app_resolves_any_thread
            th = next(th for th in self.threads if th["opened_by"]["kind"] == "human" and not th["resolved"])
            th.update(resolved=True, resolved_by=dict(AUTHOR_APP))
            self.note("an App resolved the Maintainer's thread %s" % th["id"])
        elif act == "unhold":
            # GitHub: an_app_can_label
            self.unlabel(t.LABEL_HOLD, AUTHOR_APP)
            self.note("an App took the Hold off")
        else:
            self.label(t.LABEL_HANDS_OFF, AUTHOR_APP)
            self.note("an App added hands-off")
        return True

    def gives_evidence(self) -> bool:
        """A Lens gives the result for a criterion of the contract that has none on this content yet: passing, or, while
        faults are on, now and then failing, which sends the content back to its author. While faults are on, a second
        check suite's run can also give a criterion that passed a failing result beside it, and the oldest result can
        expire with its artifact. A result carries no time of its own, so it moves nothing: a wait for evidence counts
        from the check or the Run before it."""
        if self.faults and self.results and self.judge.random() < 0.1:
            # GitHub: a_result_expires_with_its_artifact
            gone = self.results.pop(0)
            self.note("evidence %s on %s expired" % (gone["criterion"], gone["content_id"]))
            self.caused("platform")
            return True
        tested = [c for c in self.criteria if self.kinds[c] == "test"]
        human = [c for c in self.criteria if self.kinds[c] == t.HUMAN_KIND]
        if self.faults and self.judge.random() < (0.15 if human else 0.06):
            # Another App, or another workflow file of the reporter's own App, gives a passing result for a criterion;
            # or the reporter's check gives one for a criterion only a person passes, as if confirming it.
            # GitHub: any_app_gives_a_result_for_any_criterion
            roll = self.judge.random()
            criterion = human[0] if human and roll < 0.5 else self.criteria[int(roll * len(self.criteria))]
            if self.kinds[criterion] == t.HUMAN_KIND:
                check, who, by = dict(REPORTER), "the reporter's check", "lens"
            elif self.judge.random() < 0.5:
                check, who, by = dict(REPORTER, app_id=IMPOSTOR_APP, workflow=None), "another App", "platform"
            else:
                check, who, by = dict(REPORTER, workflow=IMPOSTOR_WORKFLOW), "another workflow", "platform"
            self.results.append({"criterion": criterion, "content_id": self.cid(), "result": "passing", "check": check})
            self.note("evidence %s: %s gave a result on %s" % (criterion, who, self.cid()))
            self.caused(by)
            return True
        given = {ev["criterion"] for ev in self.results if ev["content_id"] == self.cid()}
        passed = [ev["criterion"] for ev in self.results if ev["content_id"] == self.cid() and ev["result"] == "passing"
                  and ev["criterion"] in tested]
        if self.faults and passed and self.judge.random() < 0.1:
            # GitHub: a_criterion_can_have_a_result_from_each_check_suite
            self.results.append({"criterion": passed[0], "content_id": self.cid(), "result": "failing",
                                 "check": dict(REPORTER)})
            self.note("evidence %s: a second result, failing, on %s" % (passed[0], self.cid()))
            self.caused("lens")
            return True
        lacking = [c for c in tested if c not in given]
        if not lacking:
            return False
        criterion = lacking[int(self.judge.random() * len(lacking))]
        result = "failing" if self.faults and self.judge.random() < 0.15 else "passing"
        self.results.append({"criterion": criterion, "content_id": self.cid(), "result": result, "check": dict(REPORTER)})
        self.note("evidence %s: %s on %s" % (criterion, result, self.cid()))
        self.caused("lens")
        return True

    def foreign_results(self) -> bool:
        """Whether a result on this content came from anyone but its criterion's reporter, in the world's own words."""
        return any(ev["content_id"] == self.cid() and (self.kinds.get(ev["criterion"]) != "test"
                                                         or ev["check"] != REPORTER) for ev in self.results)

    def on_the_contract(self) -> bool:
        """A person acts on the contract: approves it at the head, with an approving review of the content, where nobody
        has or it changed since; or, while faults are on, now and then withdraws an approval. False if neither."""
        if self.criteria is None:
            return False
        if not self.agreed() and self.head is not None:
            self.confirm()
            return True
        if self.faults and self.approved is not None and self.judge.random() < 0.2:
            self.approved = None
            self.writer_acted()
            self.note("%s withdrew the contract's approval" % self.contract_person["name"])
            return True
        return False

    def confirm(self):
        """The person who approves the contract approves the content: on an agent's pull request the Maintainer, with a
        review; on the Maintainer's own, a colleague. It approves the contract at the head, and confirms every criterion
        of kind human on this content."""
        if self.contract_person == MAINTAINER:
            self.review("approved")
        else:
            self.reviews.append({"by": dict(COLLEAGUE), "state": "approved", "commit": "c%d" % self.content,
                                 "content_id": self.cid(), "submitted_at": self.now(), "dismissed_by": None,
                                 "dismissed_from": None})
            self.writer_acted()
            self.note("a colleague approved %s" % self.cid())
        self.approve_contract(self.contract_person)

    def awaits_a_person(self) -> bool:
        """Whether a criterion of kind human waits for a person's approval of this content, or the contract for a
        person's approval at the head, in the world's own words."""
        if self.criteria is None or self.pr_state != "open":
            return False
        return not self.agreed() or (t.HUMAN_KIND in self.kinds.values()
                                     and not self.confirmed(self.reviews, self.cid()))

    def platform(self):
        if self.criteria is not None and self.judge.random() < 0.2 and self.gives_evidence():
            return
        if self.faults and self.meddler.random() < 0.03 and self.an_app_meddles():
            self.caused(self.by_of(AUTHOR_APP))
        live = [rv for rv in self.reviews if rv["by"]["name"] == MAINTAINER["name"] and rv["state"] != "dismissed"]
        if self.faults and live and self.rng.random() < 0.1:
            # GitHub: an_app_can_dismiss_a_review
            dismissed = live[-1]
            dismissed.update(state="dismissed", dismissed_from=dismissed["state"], dismissed_by=dict(REVIEWER_APP))
            # A dismissed request still stands; a dismissed approval still answered it; a dismissed comment changes nothing.
            latest = self.verdict()
            self.asked = latest is not None and "changes_requested" in (latest["state"], latest["dismissed_from"])
            self.note("the reviewer's App dismissed the Maintainer's review (%s)" % dismissed["dismissed_from"])
            self.caused(self.by_of(REVIEWER_APP))
            return
        if self.queue and (not self.queue_merges or (self.faults and self.rng.random() < 0.2)):
            # GitHub: the_queue_can_eject
            self.queue = False
            self.note("ejected from the queue")
            self.caused("platform")
            return
        # GitHub: the_queue_merges
        # GitHub: the_merge_group_is_not_checked
        # GitHub: a_pass_comes_before_the_merge
        if self.queue and self.rng.random() < 0.6 and self.read == self.unstamped(self.facts()):
            # Whatever happened while it was queued, a pass has read it since, and would have taken it out.
            objections = self.objections()
            self.check(not objections, "a merge over %s" % ", ".join(objections))
            self.pr_state = "merged"
            self.note("merged")
            self.caused("platform")
            return
        pending = [k for k, v in self.checks.items() if v == "pending"]
        if pending:
            # GitHub: a_check_reports_on_its_own
            lens, roll = self.pick(pending), self.rng.random()
            self.checks[lens] = "success" if roll < 0.85 else "failure"
            self.completed[lens] = self.now()
            self.moves()
            if self.faults and roll >= 0.92:
                # GitHub: a_check_can_time_out_or_give_no_verdict
                self.checks[lens] = self.pick(["timed_out", "neutral", "skipped", "cancelled", "stale"])
                self.note("check %s: %s" % (lens, self.checks[lens]))
            self.caused("human" if lens in self.rerun else "lens")
            self.rerun.discard(lens)
            if self.faults and roll < 0.87 and self.checks[lens] == "failure":
                if WORKFLOWS[lens] is not None and roll < 0.86:
                    # GitHub: actions_runs_a_job_under_any_name
                    self.impostors.append({"name": CHECKS[lens], "app_id": APPS[lens], "workflow": IMPOSTOR_WORKFLOW,
                                           "conclusion": "success", "completed_at": self.now()})
                    self.note("check %s: failure, and another workflow posted a passing one under its name" % lens)
                else:
                    # GitHub: any_app_posts_a_check_under_any_name
                    # Never one from the Lens's own App and file, which the Kernel could not tell from the Lens's: for
                    # code scanning, that would be an upload under CodeQL's tool and category.
                    # GitHub: only_codeql_gives_the_code_scanning_verdict
                    self.impostors.append({"name": CHECKS[lens], "app_id": IMPOSTOR_APP, "workflow": None,
                                           "conclusion": "success", "completed_at": self.now()})
                    self.note("check %s: failure, and another App posted a passing one under its name" % lens)
                # Neither is a Run or an act of the Factory's, nor the Lens's own: the change is the platform's.
                self.caused(self.by_of(IMPOSTOR))

    def person(self):
        """The Maintainer acts, or a stranger comments, and the State the Kernel gives may change."""
        self.caused(self.acting())

    def acting(self) -> str:
        """Who acted: the Maintainer, or a stranger, who is no person with write access."""
        if self.criteria is not None and self.judge.random() < 0.3 and self.on_the_contract():
            return "human"
        # GitHub refuses a review by the pull request's author: on the Maintainer's own, they do as they always did.
        reviews = self.cls == "agent"
        if self.queue and self.faults and self.rng.random() < 0.5:
            self.while_queued(self.pick(["dismiss", "thread", "hold"]))
            return "human"
        roll = self.rng.random()
        if roll < 0.25:
            # The Maintainer ends what holds the item, whoever took a label off since; or places a Hold.
            if self.held():
                self.release()
            else:
                self.label(t.LABEL_HOLD, MAINTAINER)
            self.writer_acted()
            self.note("maintainer toggled hold -> %s" % self.held())
        elif roll < 0.45:
            self.push("don-petry", writer=True)
        elif roll < (0.55 if reviews else 0.60):
            self.open_thread()
        elif reviews and roll < 0.65:
            self.review(self.pick(["changes_requested", "commented", "approved"]))
        else:
            mine = [th for th in self.threads if self.open_for(th)]
            for th in mine:
                th.update(resolved=True, resolved_by=dict(MAINTAINER))
            if mine:     # resolving nothing is no action, and renews nothing (I-28)
                self.writer_acted()
                self.note("maintainer resolved %d threads" % len(mine))
            else:        # and in that time a stranger, who renews nothing either, comments
                self.stranger_comments()
                return self.by_of(STRANGER)
        return "human"

    def open_thread(self):
        self.threads.append({"id": "T%d" % len(self.threads), "resolved": False,
                             "opened_by": {"kind": "human", "name": "don-petry", "can_write": True},
                             "category": "human", "severity": None, "resolved_by": None, "opened_at": self.now()})
        self.writer_acted()
        self.note("maintainer opened a thread")

    def while_queued(self, fault: str):
        """The Maintainer acts after the item entered the merge queue, which read its reviews on the way in only."""
        if fault == "thread":
            self.open_thread()
        elif fault == "hold":
            if t.LABEL_HOLD not in self.labels:
                self.label(t.LABEL_HOLD, MAINTAINER)
            self.hold = True
            self.writer_acted()
            self.note("maintainer added a hold while queued")
        else:
            approvals = [rv for rv in self.reviews if rv["by"]["name"] == CONFIG["approver"] and rv["state"] == "approved"]
            if approvals:
                # GitHub: a_writer_can_dismiss_an_approval
                approvals[-1].update(state="dismissed", dismissed_from="approved", dismissed_by=dict(MAINTAINER))
                self.writer_acted()
                self.note("maintainer dismissed the approval while queued")

    def review(self, state: str):
        """The Maintainer reviews. A request for changes stands until they approve; a comment changes nothing."""
        self.reviews.append({"by": dict(MAINTAINER), "state": state, "commit": "c%d" % self.content,
                             "content_id": self.cid(), "submitted_at": self.now(), "dismissed_by": None,
                             "dismissed_from": None})
        if state != "commented":
            self.asked = state == "changes_requested"
        if state == "approved":
            # One approving review of the content by a person approves the contract at that commit too.
            self.approve_contract(MAINTAINER)
        self.writer_acted()
        self.note("maintainer reviewed: %s" % state)

    def verdict(self):
        """The Maintainer's latest verdict, dismissed or not, or None. A comment is none, dismissed or not.

        A dismissed approval still answered what came before it; a dismissed request still stands.
        """
        mine = [rv for rv in self.reviews if rv["by"]["name"] == MAINTAINER["name"] and rv["state"] != "commented"
                and rv["dismissed_from"] != "commented"]
        return mine[-1] if mine else None

    # ---- one step, and the invariants that hold at every step
    def step(self):
        self.minute += 1
        if self.pr_state != "open":
            return
        roll = self.rng.random()
        if roll < 0.40:
            # GitHub: a_tick_can_be_lost
            if not (self.faults and self.rng.random() < 0.3):
                self.poll()
            else:
                self.gap = True
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
            self.check(rv["by"]["name"] not in (self.author,), "I-26 the approver is the author")
        if self.pr_state == "merged":
            ok = any(rv["by"]["name"] == CONFIG["approver"] and rv["state"] == "approved"
                     and rv["content_id"] == self.cid() for rv in self.reviews)
            self.check(ok, "NFR-4 merged without an approval of the merged content")
            self.check(self.accepted(self.acceptance(), self.reviews, self.cid()),
                       "I-29, I-31 merged without a contract a person approved, unchanged, or with a criterion lacking "
                       "passing evidence from its reporter on the merged content")
            self.check(not self.on_the_list(self.changed) or self.reviewed(self.runs, self.cid()),
                       "I-45 a change to the list merged with no review of the merged content")
            self.check(not self.needs_review() or self.reviewed(self.runs, self.cid()),
                       "I-37 merged with no successful review of the merged content by every required model Lens")
        # A Lens's thread comes only from its review that succeeded: one that left a criterion uncovered applied nothing.
        for th in self.threads:
            if th["opened_by"]["kind"] == "lens":
                self.check(any(r["role"] == th["opened_by"]["name"] and r["intent"] == "review-change"
                               and r["conclusion"] == "success" and r["started_at"] <= th["opened_at"] for r in self.runs),
                           "I-5 a Lens's thread with no review of its that succeeded")
        since = [r for r in self.runs if (self.last_writer is None or r["started_at"] > self.last_writer)
                 and r["outcome"] != "superseded"]
        # A landed approval is an act, counted below; every other Run, a failed approval among them, is spent.
        landed = [r for r in since if r["intent"] == t.ISSUE_APPROVAL and r["conclusion"] == "success"]
        spent = [r for r in since if r not in landed]
        self.check(len(spent) <= CONFIG["limits"]["max_runs_per_item"] + 1, "run ceiling per item")
        # I-8: every automated action is inside a Run, bounded above, or is an act, bounded here.
        # Only a dequeue, an act that stops work, takes the count past the ceiling, and by one: once it is there, an
        # enqueue is refused, so nothing can enter the queue to be taken out again.
        ceiling = CONFIG["limits"]["max_acts_per_item"]
        self.check(self.acts <= ceiling or (self.acts == ceiling + 1 and self.last_act == "dequeue"),
                   "I-8 acts since a writer exceed the ceiling")
        unlanded = [r for r in spent if r["intent"] == t.ISSUE_APPROVAL]
        self.check(len([r for r in unlanded if r["outcome"] == "item"]) <= CONFIG["limits"]["max_attempts"],
                   "I-8 an approval that does not land is issued again")
        self.check(len(unlanded) <= CONFIG["limits"]["max_runs_per_item"],
                   "I-8 an approval that fails for a cause outside the item is issued for ever")
        uncovered = [r for r in spent if r["intent"] == "review-change" and r["conclusion"] == "failure"
                     and r["outcome"] == "item"]
        self.check(len(uncovered) <= CONFIG["limits"]["max_attempts"],
                   "I-8 a review that leaves a criterion uncovered is admitted past its attempts")

    def settle(self, steps: int = 400):
        """Stop the faults and the people, and let the Factory finish."""
        self.faults = self.people = False
        # The Maintainer acts after the last step: a request and an approval in the same second leave the request
        # standing, and so does a label placed and removed in the same second.
        # Each act is the Maintainer's, and each change of State it makes is checked on its own.
        self.minute += 1
        self.release()
        self.caused("human")
        for th in self.threads:
            if self.open_for(th):
                th.update(resolved=True, resolved_by=dict(MAINTAINER))
        self.caused("human")
        # The Maintainer approves what they asked to be changed.
        if self.asked:
            self.review("approved")
            self.caused("human")
        # The Maintainer puts back a contract a push deleted, and the person who approves the contract approves it at
        # the head, where nobody has or it changed since.
        if self.criteria is not None and self.head is None:
            self.push(MAINTAINER["name"], writer=True)
            self.revision += 1
            self.head = self.digest()
            self.note("the push restored the contract -> %s" % self.head)
            self.caused("human")
        if not self.agreed():
            self.confirm()
            self.caused("human")
        # The person runs again every check that did not pass, and the re-run replaces the run it repeats. What each
        # re-run then says is that person's: a Lens reports once for each run (the ruling on #38).
        # GitHub: a_rerun_replaces_only_its_own_run
        self.rerun = {k for k, v in self.checks.items() if v != "success"}
        self.checks = {k: ("pending" if v != "success" else v) for k, v in self.checks.items()}
        self.completed = {k: (self.completed[k] if v == "success" else None) for k, v in self.checks.items()}
        self.writer_acted()
        self.caused("human")
        if self.impostors or self.foreign_results():
            # Another App's check, or a result from anyone but its reporter, cannot be run again or deleted: only a push
            # leaves it behind.
            self.push(MAINTAINER["name"], writer=True)
            self.caused("human")
        for _ in range(steps):
            self.step()
        # The person who approves the contract approves it again at the head, and the content the Factory settled on,
        # which confirms each criterion of kind human, until neither waits for them; a deleted contract stays held.
        for _ in range(3):
            if not self.awaits_a_person():
                break
            self.minute += 1
            self.confirm()
            self.caused("human")
            for _ in range(steps):
                self.step()
        return decide(self.facts(), self.records(), self.context(), CONFIG, self.now())
