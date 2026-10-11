"""Seeded simulation. The seeds are fixed, so this check cannot fail at random."""
from __future__ import annotations

import os
import unittest

from sim.world import World

# Fixed seeds: the required check cannot fail at random. SIM_SEEDS shortens a local run.
SEEDS = range(1, 1 + int(os.environ.get("SIM_SEEDS", "300")))


class Simulation(unittest.TestCase):
    def test_invariants_hold_under_faults(self):
        for seed in SEEDS:
            world = World(seed)
            for _ in range(250):
                world.step()

    def test_work_is_never_lost_once_faults_stop(self):  # I-1
        for seed in SEEDS:
            world = World(seed)
            for _ in range(150):
                world.step()
            last = world.settle()
            resting = last["state"] in ("merged", "held")
            self.assertTrue(resting, "seed %d rests in %s (%s)\n%s" % (
                seed, last["state"], last["reason"], "\n".join(world.trace[-15:])))

    def test_a_quiet_world_merges_or_stops_on_a_ceiling(self):
        for seed in SEEDS:
            world = World(seed, faults=False, people=False)
            for _ in range(400):
                world.step()
            last = world.settle()
            self.assertIn(last["state"], ("merged", "held"), "seed %d: %s %s" % (seed, last["state"], last["reason"]))


if __name__ == "__main__":
    unittest.main()
