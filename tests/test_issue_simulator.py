"""Seeded simulation of an issue. The seeds are fixed, so this check cannot fail at random."""
from __future__ import annotations

import pathlib
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
# Changes of State the exploration of every change in tests/test_transitions.py finds and the world never makes on
# its seeds, each with why: the Lifecycle declares each, and the exploration is the proof that the Kernel makes it.
# One the world starts to make is a row taken off; a change the world makes that the exploration does not find fails
# the test by name.
UNMADE = {
    # The outsider's edit lapses acceptance from a Hold of the brakes, from a draft in flight or from a review: the
    # seeds' six outsider edits land elsewhere, and one from a label's Hold leaves the issue held.
    ("held", "new", "stranger"), ("in_progress", "new", "stranger"), ("in_review", "new", "stranger"),
    # The world places a Hold or hands-off while the issue carries neither, never one on top of the other.
    ("held", "not_served", "human"), ("not_served", "held", "human"),
    # The brakes hold from in_progress or from new: the seeds reach the Run ceiling and the act ceiling in triage and
    # from ready, and the unmerged closes that hold a new issue need two closes a writer makes in one life.
    ("in_progress", "held", "factory"), ("new", "held", "factory"),
    # Another App's stray Hold lands while the issue is new, in triage, in progress or in review on the seeds, never
    # while ready.
    ("ready", "held", "platform"),
    # A person's own pull request opened while the issue is ready: on the seeds each of the six is a draft.
    ("ready", "in_review", "human"),
}


def run(seed: int, steps: int = STEPS, **kw) -> IssueWorld:
    w = IssueWorld(seed, **kw)
    for _ in range(steps):
        w.step()
    return w


def agents_draft(w: IssueWorld) -> dict:
    """The Factory's draft pull request, linked to the issue."""
    return {"number": 100, "class": "agent", "opener": dict(issues.AUTHOR_APP), "open": True, "draft": True,
            "opened_at": w.now(), "merged_at": None, "closed_at": None, "empty": False, "label_events": [],
            "closed_issue_at": None}


def after(trace: list, first: str, then: str) -> bool:
    """Whether a line holding `then` follows the first line holding `first`."""
    starts = [i for i, line in enumerate(trace) if first in line]
    return bool(starts) and any(then in line for line in trace[starts[0] + 1:])


class IssueSimulation(unittest.TestCase):
    def test_invariants_hold_under_faults(self):
        made, authors, admitted, readings, stopped = set(), set(), set(), set(), set()
        began = set()
        for seed in SEEDS:
            w = run(seed)
            made |= w.made
            began |= w.began
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
        # A writer's reopening begins a new life in new, or where a Hold, hands-off or an open link that outlasts it
        # puts it (section 4.1); the Lifecycle's initial names new alone, which the design records (section 4.5).
        self.assertIn("new", began)
        self.assertLessEqual(began, {"new", "held", "not_served", "in_progress", "in_review"})
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
        # Every change of State the seeds make, with who made it, is declared (I-12), and is one the exploration of
        # every change finds too: what the world reaches and the exploration does not is a gap in the exploration.
        # What the exploration finds and the world never makes is named above, with why.
        self.assertEqual(sorted(made - issues.DECLARED), [])
        explored, _ = test_transitions.issue_explored()
        self.assertEqual(sorted(made - set(explored)), [])
        unmade = set(explored) - made
        if len(SEEDS) >= 300:
            self.assertEqual(sorted(unmade ^ UNMADE), [], "a change the world now makes, or one it no longer makes")
        else:
            self.assertEqual(sorted(UNMADE - unmade), [], "a change the world now makes on fewer seeds")

    def test_an_authors_write_access_is_read_from_the_permission(self):  # decision 0048
        # The world serves each person's permission on the repo, as the collaborator permission endpoint answers it, and
        # builds an author's write access from it as the port will: admin, maintain and write are write access, and
        # triage, read and none are not.
        # The port holds the ruling's rule (adapters/timeline.py, #272), and the fake answers as GitHub does and builds the
        # facts with its own copy, never the port's: a wrong constant in either is caught here against the ruling's words.
        from adapters import timeline
        self.assertEqual(timeline.WRITE, {"admin", "maintain", "write"})
        self.assertEqual(set(issues.WRITE_ACCESS), timeline.WRITE)
        self.assertEqual(set(issues.PERMISSIONS.values()) - timeline.PERMISSIONS, set())
        self.assertNotIn("adapters", (pathlib.Path(issues.__file__)).read_text())
        for seed in (2, 1):
            w = IssueWorld(seed, faults=False, people=False)
            author = w.facts()["author"]
            self.assertEqual(author["can_write"], issues.PERMISSIONS[author["name"]] in ("admin", "maintain", "write"), seed)
        w = IssueWorld(1, faults=False, people=False)
        name = w.facts()["author"]["name"]
        for permission, writes in (("admin", True), ("maintain", True), ("write", True), ("triage", False), ("read", False),
                                   ("none", False)):
            with mock.patch.dict(issues.PERMISSIONS, {name: permission}):
                self.assertEqual(w.facts()["author"]["can_write"], writes, permission)

    def test_a_seed_replays_exactly(self):
        traces = [run(7, steps=200).trace for _ in range(2)]
        self.assertEqual(traces[0], traces[1])
        self.assertTrue(traces[0])

    def test_the_seeds_reach_each_fault(self):
        worlds = {seed: run(seed) for seed in FIRST}
        on = {n: [seed for seed, w in worlds.items() if n in w.reached] for n in range(1, 7)}
        chosen = {
            1: lambda s: s % issues.EDITS_EVERY == issues.EDITS,
            2: lambda s: s % issues.STRANGER_PR_EVERY == issues.STRANGER_PR,
            3: lambda s: s % issues.REOPENS_EVERY == issues.REOPENS,
            4: lambda s: s % issues.REMOVES_EVERY == issues.REMOVES,
            5: lambda s: s % issues.EXPIRES_EVERY == issues.EXPIRES,
            6: lambda s: s % issues.LATE_EVERY == issues.LATE,
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
        # 4. A label removed while a Run is in flight: the Run's apply asks the Kernel again and writes nothing (I-38).
        for seed in on[4]:
            w = worlds[seed]
            self.assertTrue(after(w.trace, "while a Run was in flight", "apply refused, the issue changed"),
                            "\n".join(w.trace))
        # 6. An edit after a merge makes a merged pull request name the issue (P-46): it closed nothing, so the issue is
        # never done by it; within max_close_lag_seconds of the merge the Kernel waits, quietly, and after it reads
        # the issue as if the reference were not there, checked after every step (issue 267).
        for seed in on[6]:
            w = worlds[seed]
            self.assertTrue(w.late and all(p["closed_issue_at"] is None for p in w.linked if p["number"] in w.late))
            self.assertTrue(after(w.trace, "an edit after its merge made", "pass: "), "\n".join(w.trace))
        # 5. Run records expire: a pass read fewer records than Runs, and what the Apps wrote stood in (decision 0031).
        for seed in on[5]:
            w = worlds[seed]
            self.assertIn("a run record expired", "\n".join(w.trace))
        # Once every record of the investigation has expired, the analyst's comment stands in for it: the Kernel admits
        # no second investigation, and the world's own reading agrees.
        w = IssueWorld(on[5][0], faults=False, people=False)
        for _ in range(400):
            w.step()
            if any(r["intent"] == issue.INVESTIGATE and r["conclusion"] == "success" for r in w.runs):
                break
        self.assertTrue(w.comments)
        w.minute += issues.RETENTION + 1
        self.assertEqual((len(w.records()), w.investigation_due()), (0, False))
        d = issue.decide(w.facts(), w.records(), w.context(), issues.CONFIG, w.now())
        self.assertNotEqual((d["outcome"], d.get("admit", {}).get("intent")), (terms.ADMIT, issue.INVESTIGATE))

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
        w.linked[0].update(open=False, merged_at=w.now(), closed_at=w.now(), closed_issue_at=w.closes_the_issue())
        w.caused("platform")
        self.assertEqual(w.made, {("in_review", "done", "platform")})
        # The brakes hold a new issue whose linked pull requests closed unmerged past the bound (I-43, seed 137).
        w = IssueWorld(1, faults=False, people=False)
        for number in range(issues.LIMITS["max_unmerged_closes"] + 1):
            w.minute += 1
            w.linked.append(dict(agents_draft(w), number=300 + number, **{"class": "maintainer"}, open=False,
                                 closed_at=w.now()))
        w.minute += 1
        w.poll()
        self.assertEqual((w.labels, w.made), ({"factory:hold"}, {("new", "held", "factory")}))
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
