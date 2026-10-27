"""Seeded simulation. The seeds are fixed, so this check cannot fail at random."""
from __future__ import annotations

import os
import pathlib
import re
import unittest
from unittest import mock

from kernel import terms
from kernel.decide import decide
from sim import world
from sim.world import World
from tests import test_transitions
from tools.hooks import protected

# Fixed seeds: the required check cannot fail at random. SIM_SEEDS shortens a local run.
SEEDS = range(1, 1 + int(os.environ.get("SIM_SEEDS", "300")))
# The first seed whose Hold takes a queued item out, and the first whose lost approval does since a killed Run may leave
# no outcome (issue 286) (test_the_seeds_take_a_pull_request_out_of_the_queue_for_each_cause), and the first of each
# world on which a newer Run cancels the one waiting (a_run_waits_its_turn).
HOLD_SEED, LOST_SEED, LANE_SEED, ISSUE_LANE_SEED = 109, 69, 2, 54
# Seeds on which the item is a dependency update with no acceptance contract: to a workflow's pin, and to neither list.
DEPENDENCY_ON_THE_LIST, DEPENDENCY_OFF_THE_LIST = 4, 34


class Roll:
    """A generator that always draws 0.0: every chance taken, in a fixed order."""
    def random(self):
        return 0.0


class Never:
    """A generator that always draws 1.0: no chance taken."""
    def random(self):
        return 1.0


def queued() -> World:
    """An agent's pull request in the merge queue, approved, reviewed and with every check passing."""
    w = World(2, faults=False, people=False)
    w.checks = dict.fromkeys(w.checks, "success")
    w.runs.append({"run": "r0", "item": dict(world.ITEM), "role": "pr-review", "intent": "review-change",
                   "content_id": w.cid(), "status": "completed", "conclusion": "success", "outcome": None,
                   "started_at": w.now()})
    w.reviews.append({"by": dict(world.MACHINE),
                      "state": "approved", "commit": "c1", "content_id": w.cid(), "submitted_at": w.now(),
                      "dismissed_by": None, "dismissed_from": None})
    w.queue, w.rng = True, Roll()
    w.minute += 1
    w.starts()
    return w


def reviewed(w: World) -> World:
    """The world with every check passing and every model Lens's review of this content succeeded."""
    w.checks = dict.fromkeys(w.checks, "success")
    for lens in world.CONFIG["required_lenses"]["model"]:
        w.runs.append({"run": "r%d" % len(w.runs), "item": dict(world.ITEM), "role": lens, "intent": "review-change",
                       "content_id": w.cid(), "status": "completed", "conclusion": "success", "outcome": None,
                       "started_at": w.now()})
    w.minute += 1
    w.starts()
    return w


class Simulation(unittest.TestCase):
    def test_invariants_hold_under_faults(self):
        made, stopped, readings, writers = set(), set(), set(), set()
        for seed in SEEDS:
            world = World(seed)
            writers.add(world.last_writer is None)
            for _ in range(250):
                world.step()
            made |= world.made
            stopped |= set(world.stopped)
            if world.paused_passes:
                readings.add(world.pause_reading)
        # Some worlds start with no writer's action, and some pause for a span, or cannot read the Pause for one: in
        # those passes a Run and an approval were each held back (decision 0003).
        self.assertEqual(writers, {True, False})
        self.assertEqual(readings, {True, None})
        self.assertLessEqual({"admit", "issue_approval"}, stopped)
        # Each change of State the seeds make, and who made it, is one the exploration of every change finds too: what
        # the world reaches and the exploration does not is a gap in the exploration.
        # It holds at any number of seeds; that each of a person, a Lens, the Factory and the platform changes a State
        # is held by the exploration, which needs no seeds.
        found, _ = test_transitions.explored()
        self.assertEqual(sorted(made - set(found)), [])

    def test_a_newer_run_cancels_the_one_waiting_in_each_world(self):
        # trials/P-44.json (a_run_waits_its_turn): in the item's concurrency group one Run is in progress and at most one
        # waits; a newer Run cancels the one waiting, which never starts, and never the one running. A cancelled Run is
        # read as superseded, so it is no attempt. The pull request's world and the issue's alike.
        from sim.issues import IssueWorld
        for make in (lambda: World(2, faults=False, people=False), lambda: IssueWorld(2, faults=False, people=False)):
            w = make()
            w.runs.clear()
            base = {"item": dict(world.ITEM), "role": "pr-review", "intent": "review-change", "content_id": "c",
                    "conclusion": None, "outcome": None, "started_at": "2026-10-21T00:00:00Z"}
            w.runs.append(dict(base, run="r0", status="in_progress"))
            for n in (1, 2, 3):
                w.enqueue(dict(base, run="r%d" % n, status="queued"))
            got = [(r["run"], r["status"], r["conclusion"], r["outcome"]) for r in w.runs]
            self.assertEqual(got, [("r0", "in_progress", None, None),
                                   ("r1", "completed", "cancelled", "superseded"),
                                   ("r2", "completed", "cancelled", "superseded"),
                                   ("r3", "queued", None, None)], type(w).__name__)
            # With nothing in progress, the first Run queued holds the group and is never cancelled; only one waiting
            # behind it is, and then it starts first.
            w.runs.clear()
            for n in (0, 1, 2):
                w.enqueue(dict(base, run="r%d" % n, status="queued"))
            got = [(r["run"], r["status"], r["conclusion"]) for r in w.runs]
            self.assertEqual(got, [("r0", "queued", None), ("r1", "completed", "cancelled"), ("r2", "queued", None)],
                             type(w).__name__)
        # Each world queues its Runs through enqueue(): on a pinned seed of each, a newer Run cancels the one waiting.
        for w in (World(LANE_SEED), IssueWorld(ISSUE_LANE_SEED)):
            for _ in range(250):
                w.step()
            self.assertTrue(any("cancelled by its concurrency group" in line for line in w.trace), type(w).__name__)

    def test_a_change_of_state_in_the_first_step_is_checked(self):  # I-12
        # The world starts from the State the Kernel gives it, so the first change is checked like any other.
        w = World(1, faults=False, people=False)
        self.assertEqual((w.true_state, w.made), ("verifying", set()))
        w.label(terms.LABEL_HOLD, world.MAINTAINER)
        w.caused("human")
        self.assertEqual(w.made, {("verifying", "held", "human")})
        w = World(1, faults=False, people=False)
        w.label(terms.LABEL_HOLD, world.AUTHOR_APP)
        with mock.patch.object(world, "DECLARED", world.DECLARED - {("verifying", "held", "factory")}):
            self.assertRaises(world.Broken, w.caused, "factory")
        w = World(1, faults=False, people=False)
        w.pr_state = "closed"
        w.caused("human")
        self.assertEqual(w.made, {("verifying", "closed", "human")})

    def test_each_act_that_settles_the_world_is_checked_on_its_own(self):  # I-12
        # The Maintainer ends a Hold, then resolves their thread: two changes of State, each checked, not the one they
        # make together.
        w = queued()
        w.queue = False
        w.label(terms.LABEL_HOLD, world.MAINTAINER)
        w.open_thread()
        w.starts()
        self.assertEqual(w.true_state, "held")
        w.settle(steps=0)
        self.assertEqual(w.made, {("held", "addressing", "human"), ("addressing", "converged", "human")})

    def test_every_change_of_state_is_checked_with_who_made_it(self):  # I-12
        # The queue merges an item: the world records the transition as the platform's, and checks it is declared so.
        w = queued()
        w.read = w.unstamped(w.facts())
        w.caused("factory")
        w.platform()
        self.assertEqual((w.pr_state, w.made), ("merged", {("queued", "merged", "platform")}))
        # Had the Lifecycle declared it as anyone else's, the invariant breaks.
        w = queued()
        w.read = w.unstamped(w.facts())
        w.caused("factory")
        with mock.patch.object(world, "DECLARED", world.DECLARED - {("queued", "merged", "platform")}):
            self.assertRaises(world.Broken, w.platform)
        # Someone with no write access is nobody the Lifecycle names: a comment of theirs changes nothing, and any
        # change of State put down to them breaks the invariant.
        w = queued()
        w.caused("factory")
        w.stranger_comments()
        w.caused(w.by_of(world.STRANGER))
        self.assertEqual((w.by_of(world.STRANGER), w.made), ("stranger", set()))
        w.queue = False
        self.assertRaises(world.Broken, w.caused, w.by_of(world.STRANGER))

    def test_the_seeds_serve_a_maintainers_and_an_agents_pull_request(self):
        # The Maintainer's own pull request, where their review is refused, an agent's, which they review, and a
        # dependency bot's update.
        classes = {World(seed).facts()["class"] for seed in SEEDS}
        self.assertEqual(classes, {"maintainer", "agent", "dependency"})

    def test_the_seeds_change_the_list_by_a_role_the_dependency_bot_and_the_maintainer(self):  # I-45
        # A Role's fix Run touches a Lens's input, the dependency bot a workflow's pin, the Maintainer the brakes'
        # limits; and the list is read short now and then, or, said to be whole, leaves a path out, which the
        # Maintainer is shown. Every invariant holds, I-45 among them.
        by, short, left = set(), False, False
        for seed in SEEDS:
            w = World(seed)
            for _ in range(250):
                w.step()
            by |= w.listed_by
            short = short or any("the paths were read short" in line for line in w.trace)
            left = left or any("pass: None paths_unreadable -> defer" in line for line in w.trace)
        self.assertEqual(by, {"role", "dependency", "maintainer"})
        self.assertTrue(short and left)
        # The dependency bot's update to a workflow's pin, its checks passed, is reviewed before the machine user
        # approves it; the same update to a path on neither list is approved with no review.
        for seed, listed in ((DEPENDENCY_ON_THE_LIST, True), (DEPENDENCY_OFF_THE_LIST, False)):
            w = World(seed, faults=False, people=False)
            self.assertEqual((w.cls, w.on_the_list(w.changed)), ("dependency", listed), seed)
            w.checks = dict.fromkeys(w.checks, "success")
            w.starts()
            w.poll()
            self.assertEqual([r["intent"] for r in w.runs], ["review-change"] if listed else ["issue-approval"], seed)
            if listed:
                w.runs[-1].update(status="completed", conclusion="success")
                w.caused("lens")
                w.poll()
            self.assertEqual([rv["by"]["kind"] for rv in w.reviews], ["machine_user"], seed)
        # The world's paths on the list are the hooks' too, and those off it are on neither list.
        self.assertEqual([p for p, _ in protected.listed(protected.load(), list(world.ON_THE_LIST.values()))],
                         list(world.ON_THE_LIST.values()))
        for path in world.OFF_THE_LIST.values():
            self.assertFalse(any(protected.entries([(p, "")])[0][3].match(path) for p in world.CONFIG["protected_paths"]),
                             path)
        # Had the Kernel let a dependency update to a workflow pin converge with no review, the invariant breaks.
        w = World(DEPENDENCY_ON_THE_LIST, faults=False, people=False)
        w.checks = dict.fromkeys(w.checks, "success")
        w.starts()
        with mock.patch.dict(world.CONFIG, protected_paths=["lifecycle/"]):
            self.assertRaises(world.Broken, w.poll)

    def test_every_actors_write_access_is_read_from_the_permission(self):  # issue 299, decision 0048
        # The pull request's world serves each person's permission, the machine user's among them, and builds every
        # actor's write access from it, as the port does, with its own copy of the rule: a label event's, a review's and
        # a thread's actor alike, and whoever the world asks is a person.
        from adapters import timeline
        self.assertEqual((set(world.WRITE_ACCESS), set(world.PERMISSIONS.values()) - timeline.PERMISSIONS),
                         (timeline.WRITE, set()))
        self.assertNotIn("adapters", pathlib.Path(world.__file__).read_text())
        w = World(1, faults=False, people=False)
        w.events.append({"label": "factory:hold", "action": "labeled", "by": dict(world.COLLEAGUE), "at": w.now()})
        w.reviews.append({"by": dict(world.MACHINE), "state": "commented", "commit": "c1", "content_id": w.cid(),
                          "submitted_at": w.now(), "dismissed_by": None, "dismissed_from": None})
        for permission, writes in (("admin", True), ("maintain", True), ("write", True), ("triage", False),
                                   ("read", False), ("none", False)):
            with mock.patch.dict(world.PERMISSIONS, {world.COLLEAGUE["name"]: permission,
                                                     world.MACHINE["name"]: permission}):
                facts = w.facts()
                self.assertEqual((facts["label_events"][-1]["by"]["can_write"], facts["reviews"][-1]["by"]["can_write"],
                                  w.is_person(world.COLLEAGUE)), (writes,) * 3, permission)
        # A login the world serves no permission for writes nothing; an App's is left as the world made it.
        w.events.append({"label": "factory:hold", "action": "labeled", "by": dict(world.COLLEAGUE, name="someone"),
                         "at": w.now()})
        w.events.append({"label": "factory:hold", "action": "labeled", "by": dict(world.IMPOSTOR), "at": w.now()})
        self.assertEqual([e["by"]["can_write"] for e in w.facts()["label_events"][-2:]], [False, True])

    def test_a_seed_replays_exactly(self):
        traces = []
        for _ in range(2):
            world = World(7)
            for _ in range(200):
                world.step()
            traces.append(world.trace)
        self.assertEqual(traces[0], traces[1])
        self.assertTrue(traces[0])

    def test_a_stall_shows_whoever_comments_and_only_while_passes_run(self):  # I-1, I-28
        # A required check never reports, and a stranger comments every ten minutes. The world counts the wait itself,
        # and each pass checks the Kernel against that count: a comment does not hide the stall, and a lost tick
        # starts the count again.
        w = World(2, faults=False, people=False)
        silent = sorted(w.checks)[0]
        for lens in w.checks:
            if lens != silent:
                w.checks[lens], w.completed[lens] = "success", w.now()
        seen = {}
        for minute in range(1, 101):
            w.minute = minute
            if minute % 10 == 0:
                w.stranger_comments()
            if minute == 60:
                w.gap = True       # the poller missed a pass: the next one starts a new chain
            w.poll()
            seen[minute] = decide(w.facts(), w.records(), w.context(), world.CONFIG, w.now())["attention"]
        limit = world.CONFIG["lifecycle"]["stale_after_minutes"]["verifying"]
        for start in (0, 60):
            self.assertEqual((seen[start + limit], seen[start + limit + 1]), ("review", "stale"), start)

    def test_work_is_never_lost_once_faults_stop(self):  # I-1
        for seed in SEEDS:
            world = World(seed)
            for _ in range(150):
                world.step()
            last = world.settle()
            # A check with no verdict that a person has not run again waits for that person, and says so.
            stuck = last["reason"] == "check_unreadable" and last["attention"] == "needs_you"
            resting = last["state"] in ("merged", "held") or stuck
            self.assertTrue(resting, "seed %d rests in %s (%s)\n%s" % (
                seed, last["state"], last["reason"], "\n".join(world.trace[-15:])))

    def test_an_approval_that_never_lands_is_bounded(self):  # I-8
        self.rests_on_its_bound(dict(approval_fails="item"), "attempts_exhausted")

    def test_an_approval_that_keeps_failing_for_the_environment_is_bounded(self):  # I-8
        # Not an attempt and never an act: the Run ceiling bounds it.
        self.rests_on_its_bound(dict(approval_fails="environment"), "run_ceiling")

    def test_a_queue_that_ejects_every_time_is_bounded(self):  # I-8
        self.rests_on_its_bound(dict(queue_merges=False), "act_ceiling")

    def rests_on_its_bound(self, world: dict, reason: str):
        """A world that never ends on its own stops on its bound, or earlier on the Run ceiling."""
        reasons = []
        for seed in SEEDS:
            w = World(seed, **world)
            for _ in range(250):
                w.step()
            last = w.settle()
            self.assertEqual((w.pr_state, last["state"]), ("open", "held"), "seed %d: %s\n%s" % (
                seed, last["reason"], "\n".join(w.trace[-15:])))
            self.assertIn(last["reason"], (reason, "run_ceiling"), "seed %d" % seed)
            reasons.append(last["reason"])
        self.assertIn(reason, reasons)

    def test_only_a_writers_action_renews_the_allowance(self):  # I-28
        # The person's last choice resolves the writer's own threads. With none open, nobody acted.
        class Roll:
            def random(self):
                return 0.99

        for human_thread, renewed in ((False, False), (True, True)):
            w = World(1)
            w.minute, w.acts, w.rng = 30, 3, Roll()
            if human_thread:
                w.threads.append({"id": "T0", "resolved": False,
                                  "opened_by": {"kind": "human", "name": "don-petry", "can_write": True},
                                  "category": "human", "severity": None, "resolved_by": None, "opened_at": w.now()})
            before = w.last_writer
            w.person()
            self.assertEqual((w.acts == 0, w.last_writer != before), (renewed, renewed), human_thread)

    def test_an_invariant_not_yet_held_is_noted_until_it_is_held(self):
        w = World(1)
        with mock.patch.object(world, "NOT_YET_HELD", ("test_later",)):
            w.check_unheld(False, "test_later", "a rule")
        self.assertEqual(w.unheld, ["test_later"])
        # Once the rule is held, the same breach raises.
        self.assertRaises(world.Broken, w.check_unheld, False, "test_later", "a rule")

    def test_what_happens_while_queued_takes_the_item_out_before_it_merges(self):  # L-19
        # The Maintainer asks for changes, opens a thread, dismisses the approval or adds a Hold after the item
        # entered the queue. The queue waits for a pass, and the pass takes it out.
        # Each is made here by hand, so each says who made it. A check that passed fails on this content only on a run a
        # person started again, so its verdict is that person's (the ruling on #38).
        acts = {"changes": lambda w: w.review("changes_requested") or "human",
                "thread": lambda w: w.while_queued("thread") or "human",
                "dismiss": lambda w: w.while_queued("dismiss") or "human",
                "hold": lambda w: w.while_queued("hold") or "human",
                "check": lambda w: w.checks.update({sorted(w.checks)[0]: "failure"}) or "human"}
        for name, act in acts.items():
            w = queued()
            w.caused(act(w))
            w.platform()
            self.assertEqual((w.pr_state, w.queue), ("open", True), name)
            w.poll()
            self.assertEqual((w.pr_state, w.queue), ("open", False), name)
            # Had the queue merged over it once a pass had read it, the invariant breaks.
            w = queued()
            act(w)
            w.read = w.unstamped(w.facts())
            self.assertRaises(world.Broken, w.platform)
        # The other side: with nothing in the way, the queue merges once a pass has read the item.
        w = queued()
        w.platform()
        self.assertEqual(w.pr_state, "open")
        w.poll()
        w.platform()
        self.assertEqual(w.pr_state, "merged")

    def test_a_run_listed_unnamed_admits_nothing(self):  # I-46, decision 0036
        # On a seed that lists a new Run unnamed, the pass after its admission reads it among the unidentified Runs and
        # not among the Runs it can name. It may be the Run in flight here, so that pass admits no second review.
        w = World(11, faults=False, people=False)
        self.assertEqual(w.seed % world.UNNAMED_EVERY, world.UNNAMED)
        w.checks = dict.fromkeys(w.checks, "success")
        w.minute += 1
        w.starts()
        w.poll()
        self.assertEqual([(r["intent"], r["status"]) for r in w.runs], [("review-change", "queued")])
        w.minute += 1
        w.poll()
        self.assertEqual(w.trace[-1].split(" ", 1)[1], "pass: verifying run_unidentified -> defer")
        self.assertEqual((len(w.runs), w.unnamed_passes), (1, 1))
        # The pass after it reads the Run by its name, which keeps the item working.
        w.minute += 1
        w.poll()
        self.assertEqual((w.trace[-1].split(" ", 1)[1], len(w.runs)), ("pass: verifying awaiting_review -> nothing", 1))
        # The other side: a seed that lists every Run by its name never reads one unidentified.
        w = World(2, faults=False, people=False)
        w.checks = dict.fromkeys(w.checks, "success")
        w.minute += 1
        w.starts()
        w.poll()
        w.minute += 1
        w.poll()
        self.assertEqual((w.unnamed_passes, w.trace[-1].split(" ", 1)[1]),
                         (0, "pass: verifying awaiting_review -> nothing"))
        # A Kernel that read an unidentified Run as nobody's would admit a second review: the invariant breaks.
        w = World(11, faults=False, people=False)
        w.checks = dict.fromkeys(w.checks, "success")
        w.minute += 1
        w.starts()
        w.poll()
        w.minute += 1
        with mock.patch.object(world, "decide", lambda f, r, c, cfg, now: decide(f, r, dict(c, unidentified_runs=[]),
                                                                                 cfg, now)):
            self.assertRaisesRegex(world.Broken, "I-46", w.poll)

    def test_an_approval_listed_unnamed_is_not_issued_again(self):  # I-46, decision 0036
        # On the same seed an approval's run is read unnamed at the next pass. One that did not land is not yet counted
        # there, so the item still reads as due an approval: that pass defers it, and the pass after issues it again.
        w = reviewed(World(11, faults=False, people=False, approval_fails="item"))
        w.poll()
        # The approval's run is in flight, as on GitHub seconds later: a record the decision reads unnamed never completed.
        approval = w.runs[-1]
        self.assertEqual((approval["intent"], approval["status"], approval["conclusion"]),
                         (terms.ISSUE_APPROVAL, "in_progress", None))
        w.finish_run()
        self.assertEqual(approval["status"], "in_progress")
        w.minute += 1
        w.poll()
        self.assertEqual(w.trace[-1].split(" ", 1)[1], "pass: converged run_unidentified -> defer")
        self.assertEqual(len([r for r in w.runs if r["intent"] == terms.ISSUE_APPROVAL]), 1)
        # Once that pass has read the list, the run's end is recorded.
        self.assertEqual((approval["status"], approval["conclusion"], approval["outcome"]), ("completed", "failure", "item"))
        w.minute += 1
        w.poll()
        self.assertEqual(len([r for r in w.runs if r["intent"] == terms.ISSUE_APPROVAL]), 2)
        # A Kernel that let the approval through while its run is unnamed breaks the invariant.
        w = reviewed(World(11, faults=False, people=False, approval_fails="item"))
        w.poll()
        w.minute += 1
        with mock.patch.object(world, "decide", lambda f, r, c, cfg, now: decide(f, r, dict(c, unidentified_runs=[]),
                                                                                 cfg, now)):
            self.assertRaisesRegex(world.Broken, "I-46", w.poll)

    def test_the_seeds_list_a_new_run_unnamed(self):  # I-46, decision 0036
        # On one seed in eight a Run is listed unnamed at the pass after its admission, and that pass defers what it
        # would admit or approve; every invariant holds throughout.
        unnamed, deferred = False, False
        for seed in SEEDS:
            w = World(seed)
            for _ in range(250):
                w.step()
            unnamed = unnamed or w.unnamed_passes > 0
            deferred = deferred or any(line.endswith("run_unidentified -> defer") for line in w.trace)
            self.assertTrue(w.unnamed_passes == 0 or seed % world.UNNAMED_EVERY == world.UNNAMED, seed)
        self.assertTrue(unnamed and deferred, (unnamed, deferred))

    def test_the_seeds_list_a_run_that_never_takes_its_name(self):  # issue 270, decision 0036
        # On one seed in eight a run whose name never resolves is listed unnamed from minute NEVER_FROM: inside the
        # window it defers what a pass would admit, and past it the pass admits as usual and names it as one alert, on
        # every pass after; every invariant holds throughout. Every other seed lists no such run.
        reached = False
        for seed in SEEDS:
            w = World(seed)
            for _ in range(250):
                w.step()
            if seed % world.NEVER_NAMED_EVERY != world.NEVER_NAMED:
                self.assertIsNone(w.never, seed)
                continue
            self.assertIsNotNone(w.never, seed)
            reached = reached or bool(w.alerted)
            self.assertTrue(any("never takes its name" in line for line in w.trace), seed)
        self.assertTrue(reached)

    def test_the_seeds_read_a_push_missing_from_the_activity(self):  # I-13, I-26, issue 163
        # On one seed in nine the push that left the head is now and then missing from the branch's activity, and the
        # last pusher reads null: that pass defers for the Maintainer, approves, enqueues and admits nothing, and takes
        # a queued item out; every invariant holds throughout. Every other seed never reads one.
        missing, deferred = False, False
        for seed in SEEDS:
            w = World(seed)
            for _ in range(250):
                w.step()
            missing = missing or w.missing_passes > 0
            deferred = deferred or any(line.endswith("pass: None last_pusher_unreadable -> defer") for line in w.trace)
            self.assertTrue(w.missing_passes == 0 or seed % world.MISSING_PUSH_EVERY == world.MISSING_PUSH, seed)
        self.assertTrue(missing and deferred, (missing, deferred))
        # A queued item read so is taken out: `apply` asks the Kernel again on what GitHub holds now, where the entry is
        # back, so the dequeue is refused and the item stays, as a dequeue on a path left out of the list is.
        w = queued()
        # Faults on, with a generator that takes no chance of its own, so only the activity's draw fires.
        w.faults, w.rng, w.activity = True, Never(), Roll()
        w.poll()
        self.assertEqual(([line.split(" ", 1)[1] for line in w.trace[-2:]], w.queue, w.missing_passes),
                         (["pass: None last_pusher_unreadable -> act", "apply: refused, the item changed"], True, 1))
        w.minute += 1
        w.activity = None
        w.poll()
        self.assertEqual(w.trace[-1].split(" ", 1)[1], "pass: queued in_merge_queue -> nothing")
        # A Kernel that read a null last pusher as the author's own push would approve on it: the invariant breaks.
        w = World(world.MISSING_PUSH)
        self.assertIsNotNone(w.activity)
        with mock.patch.object(world, "decide", lambda f, r, c, cfg, now: decide(
                dict(f, last_pusher=f["author"] if f["last_pusher"] is None else f["last_pusher"]), r, c, cfg, now)):
            with self.assertRaisesRegex(world.Broken, "I-13 .* on a last pusher nobody can name"):
                for _ in range(2000):
                    w.step()

    def test_a_pause_admits_nothing_and_stops_every_act(self):  # decision 0003
        # A Hold added to a queued item would take it out. Under a Pause, or one that cannot be read, the dequeue defers
        # and the item is the Maintainer's to see; the first pass after the Pause takes it out.
        for reading in (True, None):
            w = queued()
            w.pause_from, w.pause_reading = w.minute, reading
            w.caused(w.while_queued("hold") or "human")
            w.poll()
            self.assertEqual((w.queue, w.paused_passes, w.stopped), (True, 1, ["dequeue"]), reading)
            w.minute = w.pause_from + world.PAUSE_FOR
            w.poll()
            self.assertFalse(w.queue, reading)
        # A Kernel that let the dequeue through under the Pause breaks the invariant.
        w = queued()
        w.pause_from, w.pause_reading = w.minute, True
        w.caused(w.while_queued("hold") or "human")
        with mock.patch.object(world, "decide", lambda f, r, c, cfg, now: decide(f, r, dict(c, paused=False), cfg, now)):
            self.assertRaises(world.Broken, w.poll)

    def test_under_a_pause_a_spent_count_shows(self):  # decision 0003, issues 158 and 169
        # Seed 297's Runs: a review superseded, three that failed by a fault of the item, and a fourth waiting or none.
        # A Hold of the brakes is a reading and no act, so a count already spent holds the item under a Pause, or one
        # that cannot be read, as it does without one: the Hold shows through unchanged, with a Run in flight or none.
        def review(name, minute, status="completed", conclusion="failure", outcome="item"):
            return {"run": name, "item": dict(world.ITEM), "role": "pr-review", "intent": "review-change",
                    "content_id": w.cid(), "status": status, "conclusion": conclusion, "outcome": outcome,
                    "started_at": w.at(minute)}

        for reading, status in ((True, "queued"), (None, "in_progress")):
            w = World(2, faults=False, people=False)
            w.checks = dict.fromkeys(w.checks, "success")
            w.minute += 6
            spent = [review("r0", 1, outcome="superseded")] + [review("r%d" % i, 1 + i) for i in (1, 2, 3)]
            waiting = review("r4", 5, status=status, conclusion=None, outcome=None)
            w.pause_from, w.pause_reading = w.minute, reading
            f, ctx = w.facts(), w.context()
            why = "paused" if reading else "pause_unreadable"
            for runs in (spent + [waiting], spent):
                d = decide(f, runs, ctx, world.CONFIG, w.now())
                self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "attempts_exhausted", "hold"),
                                 (reading, len(runs)))
                w.paused(f, runs, d)
                self.assertEqual(w.stopped, [], reading)   # the Pause held nothing back: the count did
                # A Kernel that let the Pause hide the Hold breaks the invariant, with a Run in flight or none.
                self.assertRaises(world.Broken, w.paused, f, runs,
                                  dict(d, state="verifying", outcome="defer", reason=why, evidence=["pr-review"]))
            # One attempt short, the Pause defers the review it would admit, and that is what it held back.
            d = decide(f, spent[:-1], ctx, world.CONFIG, w.now())
            self.assertEqual((d["outcome"], d["reason"]), ("defer", why))
            w.paused(f, spent[:-1], d)
            self.assertEqual(w.stopped, ["admit"], reading)

    def test_the_pause_falls_due_with_an_approval(self):  # I-7, decision 0003
        # On a seed that pauses, a pass before the Pause that would issue the approval, asked with no Pause, starts the
        # Pause there: the approval is what it holds back.
        w = World(20, faults=False, people=False)
        self.assertIn(w.seed % 5, world.PAUSES)
        self.assertTrue(w.pause_reading)
        reviewed(w)
        w.pause_from = w.minute + 10
        w.poll()
        self.assertEqual(w.pause_from, w.minute)
        self.assertEqual(w.trace[-1].split(" ", 1)[1], "pass: converged paused -> defer")
        self.assertEqual((w.stopped, w.reviews), (["issue_approval"], []))
        # The other side: a seed with no Pause gets none, and the approval is issued.
        w = reviewed(World(2, faults=False, people=False))
        w.poll()
        self.assertEqual((w.pause_from, w.stopped), (None, []))
        self.assertEqual([rv["by"]["kind"] for rv in w.reviews], ["machine_user"])
        # Nor does a pass that would admit a Run, enqueue, or hold the item on a Hold the facts establish move the Pause.
        w = World(20, faults=False, people=False)
        w.checks = dict.fromkeys(w.checks, "success")
        w.minute += 1
        w.starts()
        w.pause_from = w.minute + 10
        w.poll()
        self.assertEqual((w.pause_from, w.stopped), (w.minute + 10, []))
        self.assertEqual([r["intent"] for r in w.runs], ["review-change"])
        w = reviewed(World(20, faults=False, people=False))
        w.reviews.append({"by": dict(world.MACHINE), "state": "approved", "commit": "c1", "content_id": w.cid(),
                          "submitted_at": w.now(), "dismissed_by": None, "dismissed_from": None})
        w.starts()
        w.pause_from = w.minute + 10
        w.poll()
        self.assertEqual((w.pause_from, w.stopped, w.queue), (w.minute + 10, [], True))
        w = reviewed(World(20, faults=False, people=False))
        w.label(terms.LABEL_HOLD, world.MAINTAINER)
        w.starts()
        w.pause_from = w.minute + 10
        w.poll()
        self.assertEqual((w.pause_from, w.trace[-1].split(" ", 1)[1]), (w.minute + 10, "pass: held human_hold -> hold"))

    def test_the_pause_falls_due_with_a_spent_count(self):  # decision 0003, issues 158 and 169
        # Three reviews of this content failed by a fault of the item: the count is spent. On a seed that pauses, a pass
        # before the Pause that holds the item on it starts the Pause there, and the Hold shows through it.
        w = World(20, faults=False, people=False)
        w.checks = dict.fromkeys(w.checks, "success")
        for i in (1, 2, 3):
            w.runs.append({"run": "r%d" % i, "item": dict(world.ITEM), "role": "pr-review", "intent": "review-change",
                           "content_id": w.cid(), "status": "completed", "conclusion": "failure", "outcome": "item",
                           "started_at": w.at(i)})
        w.minute += 6
        w.starts()
        w.pause_from = w.minute + 10
        w.poll()
        self.assertEqual(w.pause_from, w.minute)
        self.assertEqual(w.trace[-1].split(" ", 1)[1], "pass: held attempts_exhausted -> hold")
        self.assertEqual((w.paused_passes, w.stopped), (1, []))

    def test_what_a_pause_holds_back_as_it_begins_is_checked(self):  # I-6, I-20
        # A Kernel that would issue the approval on a held item, or on facts read short, and that under the Pause defers
        # as a converged item would: the pass that starts the Pause checks what it holds back, as every Decision is.
        def careless(f, r, c, cfg, now):
            free = decide(f, r, dict(c, paused=False), cfg, now)
            if free["state"] in (terms.HELD, None):
                if c.get("paused") is False:
                    return dict(free, state=terms.CONVERGED, reason="approval_due", outcome=terms.ACT,
                                action="issue_approval", content_id=f["content_id"])
                return dict(free, state=terms.CONVERGED, reason="paused", outcome=terms.DEFER, evidence=[])
            return decide(f, r, c, cfg, now)

        for case, invariant in (("hold", "I-6"), ("short", "I-20")):
            w = reviewed(World(20, faults=False, people=False))
            if case == "hold":
                w.label(terms.LABEL_HOLD, world.MAINTAINER)
            else:
                read = w.facts
                w.facts = lambda: dict(read(), complete=dict(read()["complete"], reviews=False))
            w.pause_from = w.minute + 10
            with mock.patch.object(world, "decide", careless):
                self.assertRaisesRegex(world.Broken, invariant, w.poll)

    def test_the_evidence_expires_as_the_approval_falls_due(self):  # I-31
        # On a seed with a contract, under faults, the reporter's result on this content expires with its artifact once
        # on each content, as the approval falls due: the pass reads the criterion lacking, and waits for it.
        class Never:
            def random(self):
                return 0.99

        def due(faults):
            w = reviewed(World(17, faults=faults, people=False))
            self.assertEqual((w.criteria, w.pause_from), (["AC-1"], None))
            w.rng = w.judge = Never()
            if not w.agreed():
                w.confirm()
            w.results.append({"criterion": "AC-1", "content_id": w.cid(), "result": "passing",
                              "check": dict(world.REPORTER)})
            w.minute += 1
            w.starts()
            return w

        def approved(w):
            return [rv["content_id"] for rv in w.reviews if rv["by"] == world.MACHINE]

        w = due(True)
        w.poll()
        self.assertEqual((w.results, approved(w)), ([], []))
        self.assertEqual(w.trace[-1].split(" ", 1)[1], "pass: verifying acceptance_evidence_missing -> nothing")
        # The reporter gives it again, and on the same content it does not expire twice: the approval is issued.
        self.assertTrue(w.gives_evidence())
        w.poll()
        self.assertEqual((len(w.results), approved(w)), (1, [w.cid()]))
        # The other side: with faults off, nothing expires, and the approval is issued at once.
        w = due(False)
        w.poll()
        self.assertEqual((len(w.results), approved(w)), (1, [w.cid()]))
        # Nor does anything expire where no approval falls due: the review is admitted, and the result stays.
        w = due(True)
        w.runs = []
        w.starts()
        w.poll()
        self.assertEqual((len(w.results), [r["intent"] for r in w.runs]), (1, ["review-change"]))

    def test_a_dequeue_at_the_act_ceiling_is_the_one_act_past_it(self):  # I-8
        # A required check fails after the item entered the queue, with the acts since a writer at the ceiling. The
        # dequeue stops work, so it is made, and takes the count one past the ceiling.
        ceiling = world.CONFIG["limits"]["max_acts_per_item"]
        w = queued()
        w.acts, w.last_act = ceiling, "enqueue"
        w.checks[sorted(w.checks)[0]] = "failure"
        w.caused("human")     # on a run a person started again: a passing check fails on this content no other way
        w.poll()
        self.assertEqual((w.queue, w.acts, w.last_act), (False, ceiling + 1, "dequeue"))
        w.invariants()
        # Nothing moves it on from there: no approval, no enqueue.
        w.poll()
        self.assertEqual((w.queue, w.acts), (False, ceiling + 1))
        w.invariants()
        # The other side: an act past the ceiling that moves work on breaks the invariant, and so does a second
        # act past it.
        w.last_act = "enqueue"
        self.assertRaises(world.Broken, w.invariants)
        w.acts, w.last_act = ceiling + 2, "dequeue"
        self.assertRaises(world.Broken, w.invariants)

    def test_the_seeds_take_a_pull_request_out_of_the_queue_for_each_cause(self):
        # The faults while queued are reached: a dismissed approval, an open gate and a Hold each take one out.
        # So is another App's passing check under the name of a Lens that failed, which no Run or act may follow, and
        # one from another workflow file of the Lens's own App, which the Kernel shows as from that file.
        causes, impostors, workflows, shown = set(), 0, 0, set()

        def recording(f, r, c, cfg, now):
            d = decide(f, r, c, cfg, now)
            if d["reason"] == "check_unreadable":
                shown.update(e.split(":")[1] for e in d["evidence"] if e.count(":") >= 2)
            return d

        # The first seed whose Hold takes an item out lies past a local run of forty seeds since the lane cancels a
        # waiting Run (trials/P-44.json), and so does the first whose approval is lost since a killed Run may leave no
        # outcome (issue 286): each is run as well, so a short run still asks for that cause.
        with mock.patch.object(world, "decide", recording):
            for seed in sorted(set(SEEDS) | {HOLD_SEED, LOST_SEED}):
                w = World(seed)
                for _ in range(250):
                    w.step()
                causes |= {line.split("(")[-1].rstrip(")") for line in w.trace if "apply: dequeued" in line}
                impostors += sum("another App posted" in line for line in w.trace)
                workflows += sum("another workflow posted" in line for line in w.trace)
        self.assertLessEqual({"approval_lost", "gate_open", "human_hold"}, causes)
        self.assertTrue(impostors)
        self.assertTrue(workflows)
        self.assertLessEqual({"from_app", "from_workflow"}, shown)

    def test_the_seeds_serve_items_with_an_acceptance_contract_and_without(self):  # I-29, I-10, I-31
        # Some worlds carry a contract, and its evidence goes missing for a while, fails, is given twice and disagrees,
        # expires, is read short or unreadable and is left behind on content that changed. Its approval is missing, or
        # withdrawn; a push edits or deletes the contract; another App or workflow gives a result, and a check one for a
        # criterion only a person passes. With every invariant holding, some merge once the faults stop. The others
        # carry none.
        reasons, contracts, notes, behind, merged = set(), set(), set(), False, False
        held = ("acceptance_evidence_missing", "acceptance_failed", "acceptance_unreadable", "contract_not_approved",
                "contract_changed")
        happened = ("expired", "a second result", "withdrew the contract's approval", "the push changed the contract",
                    "the push deleted the contract", "another App gave a result", "another workflow gave a result",
                    "the reporter's check gave a result")
        for seed in SEEDS:
            w = World(seed)
            for _ in range(250):
                w.step()
            contracts.add(w.criteria is not None)
            reasons |= {r for line in w.trace if "pass: " in line for r in held if r in line}
            notes |= {n for line in w.trace for n in happened if n in line}
            behind = behind or any(ev["content_id"] != w.cid() for ev in w.results)
            if w.criteria is not None and not merged:
                w.settle()
                merged = w.pr_state == "merged"
        self.assertEqual(contracts, {True, False})
        self.assertEqual(reasons, set(held))
        self.assertEqual(notes, set(happened))
        self.assertTrue(behind and merged)

    def test_the_seeds_serve_a_review_that_left_a_criterion_uncovered(self):  # I-37, decision 0029
        # Now and then a review's Result leaves a criterion of its rubric uncovered: `apply` refuses it, so its Run fails
        # by a fault of the item and opens no thread. The same Lens's review of the same content is admitted again, and
        # at its attempts the item is held with those Runs as evidence; every invariant holds throughout.
        again, exhausted, noted = False, False, False

        def uncovered(r: dict) -> bool:
            return r["intent"] == "review-change" and (r["conclusion"], r["outcome"]) == ("failure", "item")

        def recording(f, r, c, cfg, now):
            nonlocal exhausted
            d = decide(f, r, c, cfg, now)
            if d["reason"] == "attempts_exhausted":
                ran = {x["run"]: x for x in r}
                exhausted = exhausted or any(uncovered(ran[e]) for e in d["evidence"])
            return d

        with mock.patch.object(world, "decide", recording):
            for seed in SEEDS:
                w = World(seed)
                for _ in range(250):
                    w.step()
                noted = noted or any("left a criterion uncovered" in line for line in w.trace)
                again = again or any(uncovered(r) and any(x["intent"] == "review-change" and x["role"] == r["role"]
                                                          and x["content_id"] == r["content_id"] for x in w.runs[i + 1:])
                                     for i, r in enumerate(w.runs))
        self.assertTrue(noted and again and exhausted, (noted, again, exhausted))

    def test_a_queued_item_whose_evidence_is_gone_is_taken_out_before_it_merges(self):  # I-31
        # GitHub's merge queue knows nothing of the contract. The evidence a queued item converged on is gone, as an
        # artifact is after its retention: the queue waits for a pass, and the pass takes it out.
        class Never:
            def random(self):
                return 0.99

        def gone(w):
            w.criteria, w.kinds, w.results, w.judge, w.head = ["AC-1"], {"AC-1": "test"}, [], Never(), w.digest()
            w.reviews.append({"by": dict(world.COLLEAGUE), "state": "approved", "commit": "c0",
                              "content_id": "sha256:c0c0", "submitted_at": w.at(-1), "dismissed_by": None,
                              "dismissed_from": None})
            w.approve_contract(world.COLLEAGUE, "c0")

        w = queued()
        gone(w)
        w.caused("platform")
        w.platform()
        self.assertEqual((w.pr_state, w.queue), ("open", True))
        w.poll()
        self.assertEqual((w.pr_state, w.queue), ("open", False))
        self.assertIn("apply: dequeued (acceptance_evidence_missing)", w.trace[-1])
        # Had the queue merged over it once a pass had read it, the invariant breaks.
        w = queued()
        gone(w)
        w.read = w.unstamped(w.facts())
        self.assertRaises(world.Broken, w.platform)
        # The other side: with the evidence there, on this content, the queue merges once a pass has read it.
        w = queued()
        gone(w)
        w.results = [{"criterion": "AC-1", "content_id": w.cid(), "result": "passing", "check": dict(world.REPORTER)}]
        w.poll()
        w.platform()
        self.assertEqual(w.pr_state, "merged")

    def test_every_label_act_in_the_world_takes_its_own_minute(self):  # I-6
        # The world never leans on how a tie is read: a label placed and released in one step, or put back and taken
        # off again, gives each event its own time, and the Kernel reads what the world holds.
        def kernel(w):
            return decide(w.facts(), w.records(), w.context(), world.CONFIG, w.now())

        for name in (terms.LABEL_HOLD, terms.LABEL_HANDS_OFF):
            w = queued()
            w.label(name, world.MAINTAINER)
            w.release()
            self.assertFalse(w.held(), name)
            self.assertNotEqual(kernel(w)["state"], "held", name)
            w.label(name, world.MAINTAINER)
            w.unlabel(name, world.AUTHOR_APP)
            w.release()
            self.assertFalse(w.held(), name)
            self.assertNotEqual(kernel(w)["state"], "held", name)
        for seed in SEEDS:
            w = World(seed)
            for _ in range(250):
                w.step()
            w.settle(steps=0)
            times = [ev["at"] for ev in w.events]
            self.assertEqual(times, sorted(set(times)), seed)

    def test_anyone_else_putting_back_a_persons_hands_off_leaves_it_theirs(self):  # L-17
        # The Maintainer marks the item hands-off; an App takes the label off and adds it again. In the world's words
        # and the Kernel's, it is still the Maintainer's hands-off: the item stays where it is.
        w = queued()
        w.label(terms.LABEL_HANDS_OFF, world.MAINTAINER)
        w.unlabel(terms.LABEL_HANDS_OFF, world.AUTHOR_APP)
        w.label(terms.LABEL_HANDS_OFF, world.AUTHOR_APP)
        self.assertEqual(w.hands_off, "person")
        self.assertEqual(w.objections(), [])
        w.poll()
        self.assertEqual((w.queue, w.trace[-1].split()[-3:]), (True, ["hands_off", "->", "hold"]))
        # The other side: once a person has removed it, an App's is the App's, and read as a Hold.
        w.release()
        w.label(terms.LABEL_HANDS_OFF, world.AUTHOR_APP)
        self.assertEqual(w.hands_off, "app")
        w.poll()
        self.assertIn("apply: dequeued (human_hold)", w.trace[-1])

    def test_what_an_app_does_in_a_persons_place_ends_nothing(self):  # L-17, I-6
        # An App takes the Maintainer's Hold off, adds hands-off, or resolves the Maintainer's thread. On a queued item,
        # each takes it out of the queue; and the seeds reach each, with every invariant holding.
        def unhold(w):
            w.label(terms.LABEL_HOLD, world.MAINTAINER)
            w.unlabel(terms.LABEL_HOLD, world.AUTHOR_APP)

        def resolve(w):
            w.open_thread()
            w.threads[-1].update(resolved=True, resolved_by=dict(world.AUTHOR_APP))

        # Each says who made the change of State: the person's Hold or thread, or the App's hands-off.
        acts = {"unhold": (unhold, "human_hold", "human"),
                "hands-off": (lambda w: w.label(terms.LABEL_HANDS_OFF, world.AUTHOR_APP), "human_hold", "factory"),
                "resolve": (resolve, "gate_open", "human")}
        for name, (act, reason, by) in acts.items():
            w = queued()
            act(w)
            w.caused(by)
            self.assertTrue(w.objections(), name)
            w.poll()
            self.assertEqual(w.queue, False, name)
            self.assertIn("apply: dequeued (%s)" % reason, w.trace[-1], name)
            # Had the queue merged over it once a pass had read it, the invariant breaks.
            w = queued()
            act(w)
            w.read = w.unstamped(w.facts())
            self.assertRaises(world.Broken, w.platform)
        # The other side: the Maintainer's own hands-off leaves the item where it is, and the Maintainer ends each.
        w = queued()
        w.label(terms.LABEL_HANDS_OFF, world.MAINTAINER)
        w.poll()
        self.assertEqual((w.queue, w.trace[-1].split()[-3:]), (True, ["hands_off", "->", "hold"]))
        w.release()
        self.assertFalse(w.held())
        seen = set()
        for seed in SEEDS:
            w = World(seed)
            for _ in range(250):
                w.step()
            seen |= {line.split(" ", 1)[1].rstrip("T0123456789 ") for line in w.trace if " an App " in line}
        self.assertEqual(seen, {"an App took the Hold off", "an App added hands-off",
                                "an App resolved the Maintainer's thread"})

    def test_every_invariant_not_yet_held_names_a_pending_test(self):
        # When a rule is built and its test loses @pending, its invariant here must start to raise too.
        text = (pathlib.Path(__file__).resolve().parent / "test_decide.py").read_text()
        for name in world.NOT_YET_HELD:
            self.assertRegex(text, r"@pending\s+def %s\(" % re.escape(name), name)

    def test_a_quiet_world_merges_or_stops_on_a_ceiling(self):
        for seed in SEEDS:
            world = World(seed, faults=False, people=False)
            for _ in range(400):
                world.step()
            last = world.settle()
            self.assertIn(last["state"], ("merged", "held"), "seed %d: %s %s" % (seed, last["state"], last["reason"]))


if __name__ == "__main__":
    unittest.main()
