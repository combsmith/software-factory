"""Seeded simulation. The seeds are fixed, so this check cannot fail at random."""
from __future__ import annotations

import os
import pathlib
import re
import unittest
from unittest import mock

from sim import world
from sim.world import World

# Fixed seeds: the required check cannot fail at random. SIM_SEEDS shortens a local run.
SEEDS = range(1, 1 + int(os.environ.get("SIM_SEEDS", "300")))


class Simulation(unittest.TestCase):
    def test_invariants_hold_under_faults(self):
        for seed in SEEDS:
            world = World(seed)
            for _ in range(250):
                world.step()

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
                                  "severity": None, "resolved_by": None, "opened_at": w.now()})
            before = w.last_writer
            w.person()
            self.assertEqual((w.acts == 0, w.last_writer != before), (renewed, renewed), human_thread)

    def test_a_merge_over_a_request_for_changes_is_noted_until_it_is_held(self):
        # The Maintainer asks for changes after the item entered the queue, and the queue merges it (#33).
        class Roll:
            def random(self):
                return 0.0

        name = "test_a_request_for_changes_made_while_queued_takes_it_out_of_the_queue"
        w = World(2, faults=False, people=False)
        w.queue, w.rng = True, Roll()
        w.review("changes_requested")
        w.platform()
        self.assertEqual((w.pr_state, w.unheld), ("merged", [name]))
        # Once the rule is held, the same merge breaks the invariant.
        w = World(2, faults=False, people=False)
        w.queue, w.rng = True, Roll()
        w.review("changes_requested")
        with mock.patch.object(world, "NOT_YET_HELD", ()):
            self.assertRaises(world.Broken, w.platform)

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
