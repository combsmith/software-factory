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

# Fixed seeds: the required check cannot fail at random. SIM_SEEDS shortens a local run.
SEEDS = range(1, 1 + int(os.environ.get("SIM_SEEDS", "300")))


class Roll:
    """A generator that always draws 0.0: every chance taken, in a fixed order."""
    def random(self):
        return 0.0


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
    return w


class Simulation(unittest.TestCase):
    def test_invariants_hold_under_faults(self):
        made = set()
        for seed in SEEDS:
            world = World(seed)
            for _ in range(250):
                world.step()
            made |= world.made
        # Each change of State the seeds make, and who made it, is one the exploration of every change finds too: what
        # the world reaches and the exploration does not is a gap in the exploration.
        found, _ = test_transitions.explored()
        self.assertEqual(sorted(made - set(found)), [])
        self.assertEqual({by for _, _, by in made}, {"human", "lens", "factory", "platform"})

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
        # The Maintainer's own pull request, where their review is refused, and an agent's, which they review.
        classes = {World(seed).facts()["class"] for seed in SEEDS}
        self.assertEqual(classes, {"maintainer", "agent"})

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
        acts = {"changes": lambda w: w.review("changes_requested"), "thread": lambda w: w.while_queued("thread"),
                "dismiss": lambda w: w.while_queued("dismiss"), "hold": lambda w: w.while_queued("hold"),
                "check": lambda w: w.checks.update({sorted(w.checks)[0]: "failure"})}
        for name, act in acts.items():
            w = queued()
            act(w)
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

    def test_a_dequeue_at_the_act_ceiling_is_the_one_act_past_it(self):  # I-8
        # A required check fails after the item entered the queue, with the acts since a writer at the ceiling. The
        # dequeue stops work, so it is made, and takes the count one past the ceiling.
        ceiling = world.CONFIG["limits"]["max_acts_per_item"]
        w = queued()
        w.acts, w.last_act = ceiling, "enqueue"
        w.checks[sorted(w.checks)[0]] = "failure"
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
        # So is another App's passing check under the name of a Lens that failed, which no Run or act may follow.
        causes, impostors = set(), 0
        for seed in SEEDS:
            w = World(seed)
            for _ in range(250):
                w.step()
            causes |= {line.split("(")[-1].rstrip(")") for line in w.trace if "apply: dequeued" in line}
            impostors += sum("another App posted" in line for line in w.trace)
        self.assertLessEqual({"approval_lost", "gate_open", "human_hold"}, causes)
        self.assertTrue(impostors)

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

        acts = {"unhold": (unhold, "human_hold"),
                "hands-off": (lambda w: w.label(terms.LABEL_HANDS_OFF, world.AUTHOR_APP), "human_hold"),
                "resolve": (resolve, "gate_open")}
        for name, (act, reason) in acts.items():
            w = queued()
            act(w)
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
