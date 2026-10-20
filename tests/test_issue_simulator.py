"""Seeded simulation of an issue. The seeds are fixed, so this check cannot fail at random."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from kernel import issue
from kernel import terms
from sim import issues, world
from sim.issues import IssueWorld
from tests import test_transitions

# Fixed seeds: the required check cannot fail at random. SIM_SEEDS shortens a local run.
SEEDS = range(1, 1 + int(os.environ.get("SIM_SEEDS", "300")))
# The seeds every fault is reached on, whatever SIM_SEEDS says.
FIRST = range(1, 41)
STEPS = 250
# Changes of State the world makes that the exploration of every change in tests/test_transitions.py does not find:
# each is declared in lifecycle/issue.json (I-12 holds that after every step), and each is a move the exploration
# lacks, a person's close or merge among them. One that leaves this list is a gap closed; one not on it is a new change
# to look at.
UNEXPLORED = {
    ("held", "declined", "human"), ("in_progress", "declined", "human"), ("in_progress", "done", "human"),
    ("in_progress", "in_review", "factory"), ("in_progress", "triage", "human"), ("in_review", "declined", "human"),
    ("in_review", "done", "platform"), ("in_review", "in_progress", "human"), ("new", "declined", "human"),
    ("new", "done", "human"), ("new", "held", "factory"), ("new", "in_progress", "human"),
    ("new", "in_review", "human"),
    ("ready", "declined", "human"), ("ready", "held", "factory"), ("ready", "in_progress", "human"),
    ("triage", "declined", "human"), ("triage", "in_progress", "human"), ("triage", "in_review", "human"),
}


def run(seed: int, steps: int = STEPS, **kw) -> IssueWorld:
    w = IssueWorld(seed, **kw)
    for _ in range(steps):
        w.step()
    return w


def agents_draft(w: IssueWorld) -> dict:
    """The Factory's draft pull request, linked to the issue."""
    return {"number": 100, "class": "agent", "opener": dict(issues.AUTHOR_APP), "open": True, "draft": True,
            "opened_at": w.now(), "merged_at": None, "closed_at": None, "empty": False, "label_events": []}


def after(trace: list, first: str, then: str) -> bool:
    """Whether a line holding `then` follows the first line holding `first`."""
    starts = [i for i, line in enumerate(trace) if first in line]
    return bool(starts) and any(then in line for line in trace[starts[0] + 1:])


class IssueSimulation(unittest.TestCase):
    def test_invariants_hold_under_faults(self):
        made, authors, admitted, readings, stopped = set(), set(), set(), set(), set()
        for seed in SEEDS:
            w = run(seed)
            made |= w.made
            authors.add(w.is_person(w.author))
            if not w.is_person(w.author):
                admitted.add(any(ev["label"] == terms.LABEL_ADMIT and w.is_person(ev["by"]) for ev in w.events))
            if w.paused_passes:
                readings.add(w.pause_reading)
            stopped |= set(w.stopped)
        # The seeds serve a writer's issue and an outsider's, admitted and not; some pause for a span, or cannot read
        # the Pause for one, and in those passes a Run and an act were each held back (decision 0003).
        self.assertEqual(authors, {True, False})
        self.assertEqual(admitted, {True, False})
        self.assertEqual(readings, {True, None})
        self.assertTrue(stopped)
        # On a writer's issue paused from the start, the first pass holds back the Controller's accept; accepted
        # before the Pause, it holds back the investigating Run.
        for held_back, label in ((issue.ACCEPT, None), (terms.ADMIT, issue.LABEL_TRIAGE)):
            w = IssueWorld(2, faults=False, people=False)
            w.minute, w.pause_from, w.pause_reading = 1, 2, True
            if label:
                w.label(label, issues.CONTROLLER)
            w.minute = 2
            w.poll()
            self.assertEqual((w.paused_passes, w.stopped), (1, [held_back]))
        # Every change of State the seeds make, with who made it, is declared (I-12); what the exploration of every
        # change does not find is listed above, and nothing else.
        self.assertEqual(sorted(made - issues.DECLARED), [])
        explored, _ = test_transitions.explore(test_transitions.ISSUE_BASES, test_transitions.ISSUE_MOVES,
                                               test_transitions.issue_kernel, depth=4)
        self.assertEqual(sorted(made - set(explored) - UNEXPLORED), [])

    def test_a_seed_replays_exactly(self):
        traces = [run(7, steps=200).trace for _ in range(2)]
        self.assertEqual(traces[0], traces[1])
        self.assertTrue(traces[0])

    def test_the_seeds_reach_each_fault(self):
        worlds = {seed: run(seed) for seed in FIRST}
        on = {n: [seed for seed, w in worlds.items() if n in w.reached] for n in range(1, 6)}
        chosen = {
            1: lambda s: s % issues.EDITS_EVERY == issues.EDITS,
            2: lambda s: s % issues.STRANGER_PR_EVERY == issues.STRANGER_PR,
            3: lambda s: s % issues.REOPENS_EVERY == issues.REOPENS,
            4: lambda s: s % issues.REMOVES_EVERY == issues.REMOVES,
            5: lambda s: s % issues.EXPIRES_EVERY == issues.EXPIRES,
        }
        for n, seeds in on.items():
            with self.subTest(fault=n):
                # Each fault is reached in the first seeds, and only on the seeds its constant chooses.
                self.assertTrue(seeds, "fault %d reached on no seed in %s" % (n, FIRST))
                self.assertTrue(all(chosen[n](seed) for seed in seeds), seeds)
        # 1. An outsider's edit after admission: the admission stops counting, and the next pass that reads the
        # issue whole needs a person (I-42, decision 0037).
        for seed in on[1]:
            w = worlds[seed]
            edited = "%s edited the content" % world.STRANGER["name"]
            self.assertTrue(after(w.trace, edited, "pass: new / acceptance_lapsed")
                            or after(w.trace, edited, "pass: new / not_accepted"), "\n".join(w.trace))
        # 2. A stranger's pull request names the issue: it is linked, unadmitted, and the State with it is the State
        # without it (I-39, checked on every pass).
        for seed in on[2]:
            w = worlds[seed]
            strangers = [p for p in w.linked if p["class"] == "outside"]
            self.assertTrue(strangers and not any(issue.admitted_once(p) for p in strangers))
            self.assertIn("a stranger's pull request names the issue", "\n".join(w.trace))
        # 3. A reopening by someone without write access: the issue stays declined (I-41).
        for seed in on[3]:
            w = worlds[seed]
            self.assertTrue(after(w.trace, "reopened the issue, which stays declined", "pass: declined / reopened_by_other"),
                            "\n".join(w.trace))
        # 4. A label removed while a Run is in flight: the Run's apply writes nothing (I-38), unless the Run was
        # killed first; either way nothing of the Run's reaches the issue.
        for seed in on[4]:
            w = worlds[seed]
            self.assertTrue(after(w.trace, "while a Run was in flight", "apply refused, the issue changed")
                            or after(w.trace, "while a Run was in flight", "killed"), "\n".join(w.trace))
        # 5. Run records expire: a pass read fewer records than Runs, and what the Apps wrote stood in (decision 0031).
        for seed in on[5]:
            w = worlds[seed]
            self.assertIn("a run record expired", "\n".join(w.trace))

    def test_a_stale_wait_shows_by_the_worlds_own_count(self):  # I-1, issue 165's ruling 8
        # The Factory's draft waits for its author, and nobody else moves. The world counts the wait itself, from the
        # moment the issue last moved and no earlier than the chain of passes began, and each pass holds the Kernel
        # to that count: a lost tick starts the count again.
        w = IssueWorld(2, faults=False, people=False)
        w.linked.append(agents_draft(w))
        w.starts()
        self.assertEqual(w.true_state, "in_progress")
        limit = issues.LIFECYCLE["stale_after_minutes"]["in_progress"]
        gap = limit + 10
        seen = {}
        for minute in range(1, gap + limit + 2):
            w.minute = minute
            if minute == gap:
                w.gap = True        # the poller missed a pass: the next one starts a new chain
            w.poll()
            seen[minute] = issue.decide(w.facts(), w.records(), w.context(), issues.CONFIG, w.now())["attention"]
        for start in (0, gap):
            self.assertEqual((seen[start + limit], seen[start + limit + 1]), (terms.READY, terms.STALE), start)

    def test_a_quiet_world_ends_at_rest(self):
        for seed in FIRST:
            w = IssueWorld(seed, faults=False, people=False)
            last = w.settle(steps=400)
            resting = (last["state"] in (issue.DONE, issue.DECLINED, "held")
                       or (last["state"] == "new" and last["reason"] in ("acceptance_lapsed", "not_accepted"))
                       or last["attention"] == terms.NEEDS_YOU)
            self.assertTrue(resting, "seed %d rests in %s (%s)\n%s" % (
                seed, last["state"], last["reason"], "\n".join(w.trace[-15:])))

    def test_every_change_of_state_is_checked_with_who_made_it(self):  # I-12
        # The Controller accepts a writer's issue: the world records the transition as the Factory's, and checks it is
        # declared so.
        w = IssueWorld(2, faults=False, people=False)
        self.assertEqual((w.true_state, w.made), ("new", set()))
        w.minute = 1        # a label in the second the life began does not count (decision 0028)
        w.label(issue.LABEL_TRIAGE, issues.CONTROLLER)
        w.caused("factory")
        self.assertEqual(w.made, {("new", "triage", "factory")})
        # Had the Lifecycle declared it as anyone else's, the invariant breaks.
        w = IssueWorld(2, faults=False, people=False)
        w.minute = 1
        w.label(issue.LABEL_TRIAGE, issues.CONTROLLER)
        with mock.patch.object(issues, "DECLARED", issues.DECLARED - {("new", "triage", "factory")}):
            self.assertRaises(world.Broken, w.caused, "factory")
        # The queue merges the Factory's pull request: the platform's change.
        w = IssueWorld(2, faults=False, people=False)
        w.minute = 1
        w.linked.append(dict(agents_draft(w), draft=False))
        w.starts()
        self.assertEqual(w.true_state, "in_review")
        w.linked[0].update(open=False, merged_at=w.now(), closed_at=w.now())
        w.caused("platform")
        self.assertEqual(w.made, {("in_review", "done", "platform")})
        # Someone with no write access is nobody the Lifecycle names but as one whose change goes back to new: a
        # comment of theirs changes nothing, and any other change of State put down to them breaks the invariant.
        w = IssueWorld(2, faults=False, people=False)
        w.minute = 1
        self.assertEqual(w.by_of(world.STRANGER), "stranger")
        w.caused("stranger")
        self.assertEqual(w.made, set())
        w.label(issue.LABEL_TRIAGE, issues.CONTROLLER)
        self.assertRaises(world.Broken, w.caused, "stranger")

    def test_a_broken_invariant_names_its_seed(self):
        # Another App adds factory:ready: nobody the world lets add it (I-40). The failure names the seed and the
        # invariant, and the seed replays.
        w = IssueWorld(3, faults=False, people=False)
        w.label(issue.LABEL_READY, issues.OTHER_APP)
        with self.assertRaises(world.Broken) as caught:
            w.invariants()
        self.assertIn("seed 3 broke I-40 factory:ready added by %s" % issues.OTHER_APP["name"], str(caught.exception))
        # An invariant not held yet is noted, until it is held.
        w = IssueWorld(3, faults=False, people=False)
        with mock.patch.object(issues, "NOT_YET_HELD", ("test_later",)):
            w.check_unheld(False, "test_later", "a rule")
        self.assertEqual(w.unheld, ["test_later"])
        self.assertRaises(world.Broken, w.check_unheld, False, "test_later", "a rule")


if __name__ == "__main__":
    unittest.main()
