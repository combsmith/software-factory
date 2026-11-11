"""The Release: the cut, the move and the rollback planned by `release/cut.py`, a commit's Release named by
`release/current.py`, the tags read by `adapters/tags.py`, and the skill's commands (#197's rulings 2 to 7, 4′, 4″,
5′ and 10′). No test writes a tag or reads GitHub: the refs are made up, and the port is answered by a replay."""
from __future__ import annotations

import ast
import contextlib
import copy
import datetime
import email.utils
import hashlib
import io
import json
import pathlib
import re
import shlex
import tempfile
import unittest

from adapters import effects, github, tags
from harness import eval as eval_gate
from release import current, cut, move
from tools import check_examples, check_release, check_rulesets
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "cut-a-release" / "SKILL.md"
# The skill's section "When the Factory cannot approve", word for word (decision 0194): what it says of who approves,
# and by what, changes only with this line.
CANNOT_APPROVE_SHA256 = "19f1740b27dad5336e4146d94cc2746332f7e7072070d6e8eb6827ca7d03cfe0"
REPO = "combsmith/software-factory"
A, B, C, D = ("a" * 40, "b" * 40, "c" * 40, "d" * 40)
NEXT, STABLE = "factory/v0-next", "factory/v0-stable"
# Two Releases, `next` on the later; a commit D on main, verified, with the eval gate open for the version cut.
REFS = {"factory/v0.1.0": A, "factory/v0.2.0": B, NEXT: B}
OPEN = {"commit": D, "on_main": True, "verified": True, "gate": cut.PASS, "release": "factory/v0.3.0"}
CHANNELS = frozenset({NEXT, STABLE})
TO_A = dict(OPEN, commit=A, release="factory/v0.1.0")


def plan(step, refs, facts, channels=CHANNELS):
    return cut.plan(step, refs, facts, channels)


def cutting(version="factory/v0.3.0", commit=D, channel=NEXT):
    return {"command": "cut", "version": version, "commit": commit, "channel": channel}


class Cut(unittest.TestCase):
    def test_a_cut_creates_the_release_and_moves_next_to_it_in_one_plan(self):
        self.assertEqual(plan(cutting(), REFS, OPEN), ([("create", "factory/v0.3.0", D), ("move", NEXT, D)], None))

    def test_each_rule_of_a_cut_refuses_with_its_own_code(self):
        for step, facts, code in (
                (cutting(version="factory/v0.2.0"), dict(OPEN, release="factory/v0.2.0"), cut.NOT_NEWER),
                (cutting(), dict(OPEN, on_main=False), cut.NOT_ON_MAIN),
                (cutting(), dict(OPEN, on_main=None), cut.NOT_ON_MAIN),
                (cutting(), dict(OPEN, verified=False), cut.NOT_VERIFIED),
                (cutting(), dict(OPEN, verified="true"), cut.NOT_VERIFIED),
                (cutting(commit=A), dict(OPEN, commit=A), cut.ALREADY_RELEASED),
                # Unverified is said before already released, so the first fault read is the one reported.
                (cutting(commit=A), dict(OPEN, commit=A, verified=False), cut.NOT_VERIFIED),
                (cutting(version="factory/v0.1.5"), dict(OPEN, release="factory/v0.1.5"), cut.NOT_NEWER),
                (cutting(version="factory/v1.0.0"), dict(OPEN, release="factory/v1.0.0"), cut.ANOTHER_MAJOR),
                (cutting(), dict(OPEN, gate="eval_set_empty"), cut.EVAL_GATE_CLOSED),
                (cutting(), dict(OPEN, commit=C), cut.STEP_UNREADABLE),
                (cutting(version="factory/v0.3"), OPEN, cut.STEP_UNREADABLE),
                (cutting(commit=""), dict(OPEN, commit=""), cut.STEP_UNREADABLE),
                (cutting(commit="main"), dict(OPEN, commit="main"), cut.STEP_UNREADABLE),
                (cutting(commit=D.upper()), dict(OPEN, commit=D.upper()), cut.STEP_UNREADABLE),
                (cutting(commit=D[:39]), dict(OPEN, commit=D[:39]), cut.STEP_UNREADABLE),
                (cutting(commit=None), dict(OPEN, commit=None), cut.STEP_UNREADABLE)):
            with self.subTest(step=step, facts=facts):
                self.assertEqual(plan(step, REFS, facts), ([], code))

    def test_a_closed_eval_gate_refuses_every_cut_and_move_and_burns_no_version(self):
        # The gate is the eval report's verdict on the commit, for the Release asked (ruling 4″): anything but `pass`
        # refuses, and so does a pass judged for another Release. It is read before any write, so the version asked
        # is still free once the gate opens.
        self.assertEqual(cut.PASS, eval_gate.PASS)
        to = {"command": "move", "channel": NEXT, "to": "factory/v0.1.0"}
        for word in ("eval_set_empty", "case_failed", "another_commit", "report_unreadable", None, True, "PASS"):
            with self.subTest(gate=word):
                self.assertEqual(plan(cutting(), REFS, dict(OPEN, gate=word)), ([], cut.EVAL_GATE_CLOSED))
                self.assertEqual(plan(to, REFS, dict(TO_A, gate=word)), ([], cut.EVAL_GATE_CLOSED))
        for judged in ("factory/v0.3.1", None, "factory/v0.1.0"):
            with self.subTest(release=judged):
                self.assertEqual(plan(cutting(), REFS, dict(OPEN, release=judged)), ([], cut.EVAL_GATE_CLOSED))
                if judged != "factory/v0.1.0":
                    self.assertEqual(plan(to, REFS, dict(TO_A, release=judged)), ([], cut.EVAL_GATE_CLOSED))
        self.assertIsNone(plan(cutting(), REFS, OPEN)[1])

    def test_no_step_writes_a_release_tag_and_none_names_anything_but_a_channel(self):
        for command in ("cut", "move", "rollback"):
            for channel, code in (("factory/v0.2.0", cut.RELEASE_IS_IMMUTABLE), ("factory/v0-latest", cut.NOT_A_CHANNEL),
                                  ("main", cut.NOT_A_CHANNEL), (None, cut.NOT_A_CHANNEL)):
                with self.subTest(command=command, channel=channel):
                    step = dict(cutting(channel=channel), command=command, to="factory/v0.1.0")
                    self.assertEqual(plan(step, REFS, OPEN), ([], code))
                    # A name of no Channel's form is refused even where the ring file is read as naming it.
                    self.assertEqual(plan(step, REFS, OPEN, CHANNELS | {channel}), ([], code))

    def test_only_a_channel_the_ring_file_declares_is_moved(self):
        # A Channel of another major is of the right form, and still refused: once a v1 Release existed it could never
        # be deleted (ruling 3), and every v0 cut after it would be refused as not newer.
        v1 = cutting(version="factory/v1.0.0", channel="factory/v1-next")
        self.assertEqual(plan(v1, REFS, dict(OPEN, release="factory/v1.0.0")), ([], cut.NOT_A_CHANNEL))
        self.assertEqual(plan(cutting(), REFS, OPEN, frozenset()), ([], cut.NOT_A_CHANNEL))
        self.assertEqual(plan(cutting(), REFS, OPEN, [NEXT]), ([], cut.STEP_UNREADABLE))
        rings = json.loads((ROOT / "release" / "rings.json").read_text())
        self.assertEqual(move.channels(rings), CHANNELS)
        for odd in (None, [], {"channels": []}, {"channels": {"next": "factory/v0-next"}}):
            with self.subTest(rings=odd):
                self.assertEqual(move.channels(odd), frozenset())

    def test_stable_is_never_moved_until_promotion_is_built(self):
        for command in ("cut", "move", "rollback"):
            with self.subTest(command=command):
                step = dict(cutting(channel=STABLE), command=command, to="factory/v0.1.0")
                self.assertEqual(plan(step, dict(REFS, **{STABLE: B}), TO_A), ([], cut.PROMOTION_NOT_BUILT))

    def test_a_step_or_refs_that_cannot_be_read_are_refused(self):
        for step, refs, facts in (("cut", REFS, OPEN), (cutting(), None, OPEN), (cutting(), REFS, None),
                                  (dict(cutting(), command="delete"), REFS, OPEN),
                                  (cutting(), dict(REFS, **{"factory/v0.0.1": None}), OPEN),
                                  (cutting(), dict(REFS, **{NEXT: "junk"}), OPEN),
                                  (cutting(), {**REFS, 3: A}, OPEN)):
            with self.subTest(step=step, refs=refs):
                self.assertEqual(plan(step, refs, facts), ([], cut.STEP_UNREADABLE))
        self.assertTrue(set(cut.CODES) <= set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", (ROOT / "release" / "cut.py")
                                                         .read_text())))


class Move(unittest.TestCase):
    def test_next_moves_only_to_an_existing_release_of_its_major_through_the_gate(self):
        step = {"command": "move", "channel": NEXT, "to": "factory/v0.1.0"}
        self.assertEqual(plan(step, REFS, TO_A), ([("move", NEXT, A)], None))
        for to, code in (("factory/v0.9.0", cut.NOT_A_RELEASE), (NEXT, cut.NOT_A_RELEASE), (None, cut.NOT_A_RELEASE),
                         ("factory/v1.0.0", cut.ANOTHER_MAJOR)):
            with self.subTest(to=to):
                refs = dict(REFS, **{"factory/v1.0.0": C})
                self.assertEqual(plan(dict(step, to=to), refs, dict(OPEN, commit=C, release=to)), ([], code))
        self.assertEqual(plan(step, REFS, dict(TO_A, on_main=False)), ([], cut.NOT_ON_MAIN))
        self.assertEqual(plan(step, REFS, dict(TO_A, verified=False)), ([], cut.NOT_VERIFIED))
        self.assertEqual(plan(step, REFS, dict(TO_A, commit=D)), ([], cut.STEP_UNREADABLE))

    def test_a_channel_moves_only_to_a_commit_one_release_names_alone(self):
        # Two Releases on one commit resolve to none, so a Channel moved there would name no Release (ruling 7).
        twice = dict(REFS, **{"factory/v0.1.1": A})
        self.assertEqual(plan({"command": "move", "channel": NEXT, "to": "factory/v0.1.0"}, twice, TO_A),
                         ([], cut.NOT_A_RELEASE))
        self.assertEqual(plan({"command": "rollback", "channel": NEXT, "to": "factory/v0.1.0"}, twice, {}),
                         ([], cut.NOT_A_RELEASE))
        self.assertEqual(cut.default_target(NEXT, twice), None)
        self.assertEqual(cut.default_target(NEXT, dict(twice, **{"factory/v0.0.9": C})), "factory/v0.0.9")


class Rollback(unittest.TestCase):
    def test_a_rollback_by_default_takes_the_greatest_release_below_the_one_next_is_on(self):
        refs = dict(REFS, **{"factory/v0.1.9": C, "factory/v0.3.0": D, "factory/v1.0.0": "e" * 40})
        self.assertEqual(cut.default_target(NEXT, refs), "factory/v0.1.9")
        self.assertEqual(plan({"command": "rollback", "channel": NEXT}, refs, {}), ([("move", NEXT, C)], None))
        self.assertEqual(cut.default_target(NEXT, {"factory/v0.1.0": A, NEXT: A}), None)
        self.assertEqual(cut.default_target(NEXT, {"factory/v0.1.0": A}), None)

    def test_a_rollback_passes_no_gate_and_never_moves_forward(self):
        # It must work while the Factory is broken (section 9.1), so it reads no facts; and since it passes no gate,
        # a rollback to a later Release, or from a Channel at no Release, is refused: that is the admin login's.
        step = {"command": "rollback", "channel": NEXT, "to": "factory/v0.1.0"}
        self.assertEqual(plan(step, REFS, {"gate": "case_failed", "verified": False}), ([("move", NEXT, A)], None))
        later = dict(REFS, **{"factory/v0.3.0": D})
        self.assertEqual(plan(dict(step, to="factory/v0.3.0"), later, {}), ([], cut.NOT_EARLIER))
        self.assertEqual(plan(dict(step, to="factory/v0.2.0"), REFS, {}), ([], cut.NOT_EARLIER))
        self.assertEqual(plan(step, dict(REFS, **{NEXT: C}), {}), ([], cut.NOT_EARLIER))
        self.assertEqual(plan({"command": "rollback", "channel": NEXT}, {"factory/v0.1.0": A, NEXT: A}, {}),
                         ([], cut.NO_EARLIER_RELEASE))
        self.assertEqual(plan(dict(step, to="factory/v0.0.9"), REFS, {}), ([], cut.NOT_A_RELEASE))
        # A target that is named, but is no Release, is refused, never read as no target and the default taken.
        for to in ("", 0, False, []):
            with self.subTest(to=to):
                self.assertEqual(plan(dict(step, to=to), REFS, {}), ([], cut.NOT_A_RELEASE))


class Current(unittest.TestCase):
    def test_a_commit_with_no_release_or_two_resolves_to_none(self):
        self.assertEqual(current.resolve(B, REFS), "factory/v0.2.0")
        self.assertIsNone(current.resolve(C, REFS))
        self.assertIsNone(current.resolve(B, dict(REFS, **{"factory/v0.2.1": B})))
        # A Channel is never a Release, whatever it points at, nor is a name that only looks like one.
        self.assertIsNone(current.resolve(C, {NEXT: C, STABLE: C, "factory/v0.1": C, "factory/v0.01.0": C,
                                              "factory/v0.1.0-rc": C, "factory/v0.1.0.0": C, "v0.1.0": C,
                                              "factory/v0.١.0": C}))
        self.assertIsNone(current.resolve(None, REFS))
        self.assertIsNone(current.resolve(None, {"factory/v0.1.0": None}))

    def test_a_name_is_a_release_or_a_channel_and_never_both(self):
        self.assertEqual(current.version("factory/v10.0.3"), (10, 0, 3))
        self.assertEqual(current.channel("factory/v10-next"), (10, "next"))
        for name in (NEXT, STABLE, "factory/v0-stable-2", "factory/v00-next", "factory/v-next", "factory/v0.1",
                     "factory/v0.1.0.0", "factory/v0..1", None, 3):
            with self.subTest(name=name):
                self.assertEqual(current.version(name), ())
        for name in ("factory/v0.1.0", "factory/v0-beta", "factory/v01-next", "factory/v0-", None):
            with self.subTest(name=name):
                self.assertEqual(current.channel(name), ())


def ref(name, sha=A, kind="commit"):
    return {"ref": "refs/tags/" + name, "node_id": "x", "url": "https://api.github.com/x",
            "object": {"sha": sha, "type": kind, "url": "https://api.github.com/y"}}


def answered(body, status=200, headers=None):
    asked = github.request("GET", tags.path(REPO))
    return github.Replay([{"request": {"via": "rest", "call": "%s %s" % (asked["method"], asked["path"]),
                                       "headers": {"accept": asked["accept"]}, "body": None},
                           "response": {"status": status, "headers": headers or {}, "body": body}}])


class Tags(unittest.TestCase):
    def test_a_move_reads_refs_and_nothing_at_any_tag(self):
        # One read, of the refs alone: no file is read at any tag, so a rollback runs nothing it rolls back (0006).
        self.assertEqual(tags.path(REPO), "/repos/combsmith/software-factory/git/matching-refs/tags/factory")
        read = tags.read(answered([ref("factory/v0.1.0"), ref(NEXT, B), ref("factory-old", C), ref("factory/v0.2.0", B)]),
                         REPO)
        self.assertEqual(read, {"factory/v0.1.0": A, NEXT: B, "factory/v0.2.0": B})
        tree = ast.parse((ROOT / "adapters" / "tags.py").read_text())
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertEqual(imported, {"__future__", "re", "adapters.github", "release"})
        self.assertEqual(check_release.run(), [])

    def test_the_refs_github_answered_are_read_as_the_port_reads_them(self):
        # One read of this repo's factory/ tags, through the Maintainer's login, on 2026-10-26: none exist yet, so the
        # first cut has no Release to be newer than, and no rollback has a target.
        fixture = json.loads((ROOT / "release" / "fixtures" / "refs.read.json").read_text())
        self.assertEqual(tags.read(github.Replay(fixture["exchanges"]), REPO), {})
        self.assertEqual(check_release.fixture_problems(fixture, "refs.read.json"), [])
        for planted in ({"authorization": "token " + "x" * 30}, {"x-github-edge-region": "iad"}):
            with self.subTest(planted=planted):
                held = copy.deepcopy(fixture)
                held["exchanges"][0]["response"]["headers"].update(planted)
                self.assertTrue(check_release.fixture_problems(held, "refs.read.json"))
        held = copy.deepcopy(fixture)
        held["exchanges"][0]["response"]["body"] = [{"ref": "refs/tags/factory/v0.1.0", "note": "ghp_" + "x" * 36}]
        self.assertTrue(check_release.fixture_problems(held, "refs.read.json"))

    def test_each_page_github_links_is_read_and_only_this_lists(self):
        # GitHub may page the list, thirty to a page: each next page is read by its link, held to this list's own.
        def page(path, body, link=None):
            asked = github.request("GET", path)
            return {"request": {"via": "rest", "call": "GET %s" % asked["path"], "headers": {"accept": asked["accept"]},
                                "body": None},
                    "response": {"status": 200, "headers": {"Link": link} if link else {}, "body": body}}
        first = tags.path(REPO)
        nxt = "/repositories/1234/git/matching-refs/tags/factory?page=%d"
        link = lambda n, host="https://api.github.com": '<%s%s>; rel="next", <%s%s>; rel="last"' % (
            host, nxt % n, host, nxt % 3)
        # A link by the repo's id is held to the id GitHub gives for this repo, read once.
        repo_id = {"request": {"via": "rest", "call": "GET /repos/%s" % REPO, "headers": {"accept": github.JSON},
                               "body": None}, "response": {"status": 200, "headers": {}, "body": {"id": 1234}}}
        three = [page(first, [ref("factory/v0.1.0")], link(2)), repo_id,
                 page(nxt % 2, [ref("factory/v0.2.0", B)], link(3)), page(nxt % 3, [ref(NEXT, B)])]
        self.assertEqual(tags.read(github.Replay(three), REPO), {"factory/v0.1.0": A, "factory/v0.2.0": B, NEXT: B})
        named = [page(first, [ref("factory/v0.1.0")], '<https://api.github.com/repos/%s/git/matching-refs/tags/factory'
                                                      '?per_page=30&page=2>; rel="next"' % REPO.upper()),
                 page("/repos/%s/git/matching-refs/tags/factory?per_page=30&page=2" % REPO.upper(), [ref(NEXT, A)])]
        self.assertEqual(tags.read(github.Replay(named), REPO), {"factory/v0.1.0": A, NEXT: A})
        # Each refused next page is one GitHub would answer, so that reading it is what a test would see.
        heads = "/repositories/1234/git/matching-refs/heads/main?page=2"
        for why, link_, then in (("another host", link(2, "https://evil.example"), nxt % 2),
                                 ("another list", '<https://api.github.com%s>; rel="next"' % heads, heads),
                                 ("a page skipped", link(3), nxt % 3),
                                 ("the same page again", '<https://api.github.com%s>; rel="next"' % (nxt % 1), nxt % 1),
                                 ("a next with no link", 'rel="next"', nxt % 2),
                                 ("another repo by its name", '<https://api.github.com/repos/combsmith/other/git/'
                                  'matching-refs/tags/factory?page=2>; rel="next"',
                                  "/repos/combsmith/other/git/matching-refs/tags/factory?page=2")):
            with self.subTest(why=why):
                by_id = [repo_id] if then.startswith("/repositories/") else []
                answered_ = [page(first, [ref("factory/v0.1.0")], link_)] + by_id + [page(then, [ref(NEXT, A)])]
                self.assertIsNone(tags.read(github.Replay(answered_), REPO))
        # Another repo by its id is not this one, and nor is any id when this repo's own cannot be read.
        for answered_id in ({"id": 99}, {"message": "Not Found"}, {"id": 1234.0}, {"id": "1234"}):
            with self.subTest(id=answered_id):
                other = [page(first, [ref("factory/v0.1.0")], link(2)),
                         dict(repo_id, response=dict(repo_id["response"], body=answered_id)), page(nxt % 2, [ref(NEXT, A)])]
                self.assertIsNone(tags.read(github.Replay(other), REPO))
        # A name on two pages is no whole read, and nor is a list longer than MOST_PAGES pages.
        twice = [page(first, [ref("factory/v0.1.0")], link(2)), repo_id, page(nxt % 2, [ref("factory/v0.1.0", B)])]
        self.assertIsNone(tags.read(github.Replay(twice), REPO))
        most = tags.MOST_PAGES
        endless = [page(first, [], link(2)), repo_id] + [page(nxt % n, [], '<https://api.github.com%s>; rel="next"'
                                                          % (nxt % (n + 1))) for n in range(2, most + 1)] + \
            [page(nxt % (most + 1), [])]
        self.assertIsNone(tags.read(github.Replay(endless), REPO))
        self.assertEqual(tags.read(github.Replay(endless[:-1][:-1] + [page(nxt % most, [])]), REPO), {})

    def test_tags_are_read_whole_or_not_at_all(self):
        for body, status, headers in (
                ([ref("factory/v0.1.0", kind="tag")], 200, None),
                ([ref("factory/v0.1.0"), ref("factory/v0.1.0", B)], 200, None),
                ([ref("factory/v0.1.0", sha="A" * 40)], 200, None),
                ([ref("factory/v0.1.0")], 200, {"Link": '<https://api.github.com/x?page=2>; rel="next"'}),
                ([{"ref": "refs/tags/factory/v0.1.0"}], 200, None),
                (["refs/tags/factory/v0.1.0"], 200, None),
                ({"ref": "refs/tags/factory/v0.1.0", "object": {"sha": A, "type": "commit"}}, 200, None),
                ({"message": "Not Found"}, 404, None),
                ([], 500, None)):
            with self.subTest(body=body, status=status):
                self.assertIsNone(tags.read(answered(body, status, headers), REPO))
        self.assertEqual(tags.read(answered([]), REPO), {})
        self.assertIsNone(tags.read(github.Replay([]), REPO))
        self.assertIsNone(tags.read(None, REPO))
        for repo in ("combsmith", "combsmith/..", "combsmith/.", "combsmith/x/y", "../x", None):
            with self.subTest(repo=repo):
                asked = []
                self.assertIsNone(tags.read(type("Sent", (), {"send": lambda _, req: asked.append(req)})(), repo))
                self.assertEqual(asked, [], "a repo that is none, or climbs out, is never asked")


class Fixture(unittest.TestCase):
    """`release/fixtures/gate.v0-1-0.json`: each release.yml run's outcome and what can be read from outside it (#197's
    ruling 9′, as amended on 2026-11-03), read through the Maintainer's login."""
    PATH = ROOT / "release" / "fixtures" / "gate.v0-1-0.json"
    CUT = ROOT / "release" / "fixtures" / "cut.v0-1-0.json"
    NEXT_CUT = ROOT / "release" / "fixtures" / "cut.v0-1-1.json"
    THIRD_CUT = ROOT / "release" / "fixtures" / "cut.v0-1-2.json"
    FOURTH_CUT = ROOT / "release" / "fixtures" / "cut.v0-1-3.json"
    FIFTH_CUT = ROOT / "release" / "fixtures" / "cut.v0-1-4.json"
    SIXTH_CUT = ROOT / "release" / "fixtures" / "cut.v0-1-5.json"
    SEVENTH_CUT = ROOT / "release" / "fixtures" / "cut.v0-1-6.json"
    EIGHTH_CUT = ROOT / "release" / "fixtures" / "cut.v0-1-7.json"
    ROLLBACK = ROOT / "release" / "fixtures" / "rollback.refused.json"
    EVENT = ROOT / "release" / "fixtures" / "event.slice-1.json"

    def item(self, fixture, name):
        found = [item for item in fixture["items"] if item["item"] == name]
        self.assertEqual(len(found), 1, name)
        return found[0]

    def answered(self, item, path, method="GET"):
        found = [e["response"] for e in item["exchanges"] if e["request"]["call"].split(" ")[:2] == [method, path]]
        self.assertEqual(len(found), 1, path)
        return found[0]

    def test_the_first_cut_was_refused_by_the_closed_gate_and_wrote_nothing(self):
        # Run 41201305939 dispatched the cut of factory/v0.1.0 on 2026-10-31, before any eval: the gate refused it,
        # and two days later neither the Release nor `next` existed, and `next` had no Deployment.
        fixture = json.loads(self.PATH.read_text())
        self.assertEqual(check_release.fixture_problems(fixture, "gate.v0-1-0.json"), [])
        first = self.item(fixture, "cut_refused_by_the_closed_gate")
        self.assertEqual((first["asked"]["command"], first["asked"]["version"]), ("cut", fixture["version"]))
        self.assertEqual(first["printed"], {"writes": [], "deployments": [], "refused": cut.EVAL_GATE_CLOSED})
        self.assertEqual(first["conclusion"], "failure")
        for tag in (fixture["version"], move.next_channel(json.loads(move.RINGS.read_text()))):
            with self.subTest(tag=tag):
                self.assertEqual(self.answered(first, "/repos/%s/git/ref/tags/%s" % (REPO, tag))["status"], 404)
        deployed = self.answered(first, "/repos/%s/deployments?environment=factory-next" % REPO)
        self.assertEqual((deployed["status"], deployed["body"]), (200, []))

    def test_the_first_cut_moved_next_and_its_release_is_neither_moved_nor_cut_again(self):
        # Run 42348605675 cut factory/v0.1.0 at the commit its eval passed, moved `next` to it and recorded one Deployment
        # of `next`; run 42348650504 asked the same cut again, was refused, and wrote nothing. The Maintainer's admin
        # PATCH, forcing factory/v0.1.0 to an older commit, was refused, and the tag read after it still names the cut.
        # The tag ruleset keeps every Release tag from being updated or deleted, by anyone (records 0071 and 0120).
        fixture = json.loads(self.CUT.read_text())
        self.assertEqual(check_release.fixture_problems(fixture, "cut.v0-1-0.json"), [])
        made = self.item(fixture, "cut_and_move_of_next")
        commit, channel = made["asked"]["cut_commit"], move.next_channel(json.loads(move.RINGS.read_text()))
        self.assertEqual((made["conclusion"], made["printed"]["writes"]),
                         ("success", [["create", fixture["version"], commit], ["move", channel, commit]]))
        for tag in (fixture["version"], channel):
            with self.subTest(tag=tag):
                ref = self.answered(made, "/repos/%s/git/ref/tags/%s" % (REPO, tag))
                self.assertEqual((ref["status"], ref["body"]["object"]["sha"]), (200, commit))
        # Each read is GitHub's answer, 200 (the Claude read of the follow-on to #627).
        body = lambda item, path: (lambda answer: self.assertEqual(answer["status"], 200, path) or answer["body"])(
            self.answered(item, path))
        deployed = body(made, "/repos/%s/deployments?environment=factory-next" % REPO)
        self.assertEqual([(d["id"], d["sha"], d["description"]) for d in deployed],
                         [(made["printed"]["deployments"][0], commit, fixture["version"])])
        statuses = body(made, "/repos/%s/deployments/%d/statuses" % (REPO, deployed[0]["id"]))
        self.assertEqual([s["state"] for s in statuses], ["success"])
        again = self.item(fixture, "refused_move_of_the_release")
        self.assertEqual((again["conclusion"], again["printed"]),
                         ("failure", {"writes": [], "deployments": [], "refused": cut.ALREADY_RELEASED}))
        self.assertEqual(len(body(again, "/repos/%s/deployments?environment=factory-next" % REPO)), 1)
        calls = [e["request"]["call"].split(" ")[:2] for e in again["exchanges"]]
        forcing = again["exchanges"][calls.index(["PATCH", "/repos/%s/git/refs/tags/%s" % (REPO, fixture["version"])])]
        asked, forced = forcing["request"]["body"], forcing["response"]
        self.assertTrue(asked["force"] is True and asked["sha"] != commit, asked)
        self.assertEqual((forced["status"], forced["body"]["message"].split("\n")[0]),
                         (422, "Repository rule violations found"))
        # Made by the Maintainer, whose admin role the ruleset gives no bypass, and refused as a protected ref.
        maintainer = json.loads((ROOT / "config" / "hooks.json").read_text())["maintainer"]["login"]
        self.assertEqual(forcing["request"]["as"], {"kind": "person", "name": maintainer})
        self.assertIn("the admin role", forcing["request"]["call"])
        self.assertIn("Cannot update this protected ref.", forced["body"]["message"].split("\n"))
        # The exchanges are kept in the order they were made: the reads after the PATCH were made after it.
        made_at = [email.utils.parsedate_to_datetime(e["response"]["headers"]["date"]) for e in again["exchanges"]]
        self.assertEqual(made_at, sorted(made_at))
        read = "/repos/%s/git/ref/tags/%s" % (REPO, fixture["version"])
        self.assertLess(again["exchanges"].index(forcing), calls.index(["GET", read]))
        self.assertEqual(body(again, read)["object"]["sha"], commit)
        rules = body(again, "/repos/%s/rulesets/25996980" % REPO)
        self.assertEqual((rules["target"], rules["enforcement"], rules["bypass_actors"]), ("tag", "active", []))
        # The rules the repo holds this ruleset to, force-pushes among them (tools/check_rulesets.py).
        self.assertLessEqual(check_rulesets.TAG_RULESETS["factory releases are immutable"], {rule["type"] for rule in rules["rules"]})
        self.assertIn("refs/tags/factory/v*.*.*", rules["conditions"]["ref_name"]["include"])
        self.assertEqual(rules["conditions"]["ref_name"]["exclude"], [])

    def a_later_cut_moved_next_on(self, path, eval_run, earlier):
        """The cut `path` records, at the commit eval run `eval_run` had passed, the eval job's own dispatch and its one
        run on that commit, ended before the cut; `next` moved to it with a Deployment of its own, the newest, before
        those of `earlier`, the cuts before it, newest first; the Release before it stayed where its cut left it, and
        that Release's Deployment went inactive."""
        fixture, before = json.loads(path.read_text()), [json.loads(p.read_text()) for p in earlier]
        self.assertEqual(check_release.fixture_problems(fixture, path.name), [])
        made = self.item(fixture, "cut_and_move_of_next")
        commit, channel = made["asked"]["cut_commit"], move.next_channel(json.loads(move.RINGS.read_text()))
        self.assertEqual((made["asked"]["command"], made["asked"]["version"]), ("cut", fixture["version"]))
        self.assertEqual((made["conclusion"], made["printed"]["writes"]),
                         ("success", [["create", fixture["version"], commit], ["move", channel, commit]]))
        body = lambda path: (lambda answer: self.assertEqual(answer["status"], 200, path) or answer["body"])(
            self.answered(made, path))
        run, ran = body("/repos/%s/actions/runs/%d" % (REPO, made["run"])), body("/repos/%s/actions/runs/%d" % (REPO, eval_run))
        self.assertEqual((ran["id"], ran["path"], ran["event"], ran["conclusion"], ran["head_sha"]),
                         (eval_run, ".github/workflows/eval.yml", "workflow_dispatch", "success", commit))
        listed = body("/repos/%s/actions/workflows/%d/runs?head_sha=%s" % (REPO, ran["workflow_id"], commit))
        self.assertEqual((listed["total_count"], [r["id"] for r in listed["workflow_runs"]]), (1, [ran["id"]]))
        self.assertLess(ran["updated_at"], run["created_at"], "the eval had ended before the cut was asked")
        for tag in (fixture["version"], channel):
            with self.subTest(tag=tag):
                self.assertEqual(body("/repos/%s/git/ref/tags/%s" % (REPO, tag))["object"]["sha"], commit)
        cuts = [self.item(f, "cut_and_move_of_next") for f in before]
        self.assertEqual(body("/repos/%s/git/ref/tags/%s" % (REPO, before[0]["version"]))["object"]["sha"],
                         cuts[0]["asked"]["cut_commit"])
        deployed = body("/repos/%s/deployments?environment=factory-next" % REPO)
        self.assertEqual([(d["id"], d["sha"], d["description"]) for d in deployed],
                         [(made["printed"]["deployments"][0], commit, fixture["version"])]
                         + [(c["printed"]["deployments"][0], c["asked"]["cut_commit"], f["version"])
                            for c, f in zip(cuts, before)])
        statuses = body("/repos/%s/deployments/%d/statuses" % (REPO, deployed[0]["id"]))
        self.assertEqual([s["state"] for s in statuses], ["success"])
        # GitHub marks the Deployment `next` moved off inactive, newest first, beside the success it kept.
        statuses = body("/repos/%s/deployments/%d/statuses" % (REPO, deployed[1]["id"]))
        self.assertEqual([s["state"] for s in statuses], ["inactive", "success"])

    def test_the_next_cut_moved_next_on(self):
        # Each cut after the first. Run 42697380276 cut factory/v0.1.1 on 2026-11-09 at the commit eval run 42694638100
        # had passed; run 42741714653 cut factory/v0.1.2 on 2026-11-10 at the commit eval run 42739717534 had passed,
        # #694's merge, after slice 1's first dry run stopped in the reader; run 42755427902 cut factory/v0.1.3 on
        # 2026-11-10 at the commit eval run 42753588971 had passed, #708's merge, after the second; run 42868490093 cut
        # factory/v0.1.4 on 2026-11-10 at the commit eval run 42865325326 had passed, #714's merge, after the third;
        # run 42885151917 cut factory/v0.1.5 on 2026-11-10 at the commit eval run 42882105104 had passed, #720's
        # merge, after the fourth; run 42925869303 cut factory/v0.1.6 on 2026-11-10 at the commit eval run 42923463050
        # had passed, #717's merge, after the fifth and the sixth; run 43026745268 cut factory/v0.1.7 on 2026-11-11 at
        # the commit eval run 43024260112 had passed, #731's merge, after the seventh.
        for path, eval_run, earlier in ((self.NEXT_CUT, 42694638100, [self.CUT]),
                                        (self.THIRD_CUT, 42739717534, [self.NEXT_CUT, self.CUT]),
                                        (self.FOURTH_CUT, 42753588971, [self.THIRD_CUT, self.NEXT_CUT, self.CUT]),
                                        (self.FIFTH_CUT, 42865325326,
                                         [self.FOURTH_CUT, self.THIRD_CUT, self.NEXT_CUT, self.CUT]),
                                        (self.SIXTH_CUT, 42882105104,
                                         [self.FIFTH_CUT, self.FOURTH_CUT, self.THIRD_CUT, self.NEXT_CUT,
                                          self.CUT]),
                                        (self.SEVENTH_CUT, 42923463050,
                                         [self.SIXTH_CUT, self.FIFTH_CUT, self.FOURTH_CUT, self.THIRD_CUT,
                                          self.NEXT_CUT, self.CUT]),
                                        (self.EIGHTH_CUT, 43024260112,
                                         [self.SEVENTH_CUT, self.SIXTH_CUT, self.FIFTH_CUT, self.FOURTH_CUT,
                                          self.THIRD_CUT, self.NEXT_CUT, self.CUT])):
            with self.subTest(cut=path.name):
                self.a_later_cut_moved_next_on(path, eval_run, earlier)

    def test_the_slice_1_event_is_whole(self):  # issue 198's ruling 6
        # Slice 1's event: a pull request the Maintainer opened after `main` began to count an approval (decision
        # 0191), which a Release on `next` reviewed, whose head the Factory's approving act approved as the machine
        # user, and which merged through the queue on that approval. It is the switch's own record, the pull request
        # the rulings name; two others merged on the approval minutes before it, and "first" is no read's to show. The
        # fixture holds what GitHub answered of it afterwards, and each pass whose Decision on the merged head differed
        # from the pass before's. The Maintainer's login enqueued it, as it enqueues every pull request; no enqueue by
        # the Factory's queue step is claimed.
        fixture = json.loads(self.EVENT.read_text())
        self.assertEqual(check_release.fixture_problems(fixture, "event.slice-1.json"), [])
        self.assertEqual(fixture["repo"], REPO)
        event, steps, api = fixture["event"], fixture["steps"], "/repos/%s" % REPO
        body = lambda path, method="GET": (lambda answer: self.assertEqual(answer["status"], 200, path) or answer["body"])(
            self.answered(fixture, path, method))
        defaults = json.loads((ROOT / "config" / "defaults.json").read_text())
        maintainer = json.loads((ROOT / "config" / "hooks.json").read_text())["maintainer"]["login"]
        apps = json.loads((ROOT / "config" / "apps.json").read_text())["apps"]
        pull = body("%s/pulls/%d" % (api, event["pull_request"]))
        self.assertEqual((pull["number"], pull["state"], pull["merged"], pull["base"]["ref"], pull["head"]["sha"],
                          pull["merge_commit_sha"]),
                         (event["pull_request"], "closed", True, "main", event["head"], event["merged"]["commit"]))
        # Opened after `main` began to count an approval: the ruleset, read afterwards, counts one as the repo's record
        # of it says, and was last changed before the pull request was opened.
        ruleset = body("%s/rulesets/%d" % (api, event["ruleset"]))
        recorded = json.loads((ROOT / "config" / "rulesets.json").read_text())["rulesets"]["main"]
        counted, = [r["parameters"] for r in ruleset["rules"] if r["type"] == "pull_request"]
        self.assertEqual((ruleset["id"], ruleset["name"], ruleset["target"], ruleset["enforcement"], ruleset["bypass_actors"]),
                         (recorded["id"], "main", "branch", "active", []))
        # It covers the default branch, which the pull request's base is, and leaves no branch out.
        self.assertEqual(ruleset["conditions"]["ref_name"], {"include": recorded["include"], "exclude": []})
        self.assertEqual(recorded["include"], ["~DEFAULT_BRANCH"])
        self.assertEqual(body(api), {"full_name": REPO, "default_branch": pull["base"]["ref"]})
        self.assertEqual(counted, {k: recorded["rules"]["pull_request"][k] for k in (
            "required_approving_review_count", "require_code_owner_review", "require_last_push_approval",
            "dismiss_stale_reviews_on_push", "required_reviewers")})
        self.assertEqual((counted["required_approving_review_count"], counted["require_code_owner_review"],
                          counted["require_last_push_approval"], counted["dismiss_stale_reviews_on_push"]), (1, True, True, True))
        utc = lambda at: datetime.datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone(datetime.timezone.utc)
        self.assertLess(utc(ruleset["updated_at"]), utc(pull["created_at"]))
        pushed = body("%s/pulls/%d/commits" % (api, event["pull_request"]))
        # Its author is the Maintainer, whose own approval GitHub does not count: the one that counted is the approver's.
        self.assertEqual((pull["user"]["login"], pull["user"]["type"]), (maintainer, "User"))
        reviews = body("%s/pulls/%d/reviews" % (api, event["pull_request"]))
        approved = [r for r in reviews if r["state"] == "APPROVED"]
        self.assertEqual([(r["id"], r["user"]["login"], r["user"]["type"], r["commit_id"], r["submitted_at"]) for r in approved],
                         [(event["approval"]["review"], defaults["approver"], "User", pull["head"]["sha"], event["approval"]["at"])])
        self.assertEqual((event["approval"]["by"], event["approval"]["commit"]), (defaults["approver"], event["head"]))
        # It is of the last push, the last review made, and no review asks for changes or was dismissed.
        self.assertEqual(pushed[-1]["sha"], pull["head"]["sha"])
        self.assertLess(pushed[-1]["commit"]["committer"]["date"], event["approval"]["at"])
        self.assertEqual(max(r["submitted_at"] for r in reviews), event["approval"]["at"])
        self.assertLessEqual({r["state"] for r in reviews}, {"APPROVED", "COMMENTED"})
        # The queue took the head the approval is of, after it, and the merge is the pull request's own.
        asked, = [e["request"]["body"]["variables"] for e in fixture["exchanges"] if e["request"]["call"].startswith("POST /graphql")]
        self.assertEqual(asked, dict(zip(("owner", "name"), REPO.split("/")), n=event["pull_request"]))
        told = body("/graphql", "POST")["data"]["repository"]["pullRequest"]["timelineItems"]["nodes"]
        self.assertEqual([n["__typename"] for n in told],
                         ["AddedToMergeQueueEvent", "MergedEvent", "RemovedFromMergeQueueEvent"])
        queued, merged, left = told
        self.assertEqual((queued["enqueuer"]["login"], queued["actor"]["login"], queued["actor"]["__typename"],
                          queued["createdAt"]), (maintainer, maintainer, "User", event["enqueued"]["at"]))
        self.assertEqual(event["enqueued"]["by"], maintainer)
        self.assertEqual((merged["commit"]["oid"], merged["createdAt"], merged["mergeRefName"], merged["actor"]["login"],
                          left["reason"]), (event["merged"]["commit"], pull["merged_at"], pull["base"]["ref"], maintainer, "merged"))
        self.assertEqual(event["merged"]["at"], pull["merged_at"])
        # One Release, on `next`, at every step, and cut before the change existed (FR-50).
        self.assertEqual({s["release"] for s in steps}, {event["release"]})
        channel = move.next_channel(json.loads(move.RINGS.read_text()))
        for tag in (channel, event["release"]):
            ref = body("%s/git/ref/tags/%s" % (api, tag))
            self.assertEqual((ref["ref"], ref["object"]["type"], ref["object"]["sha"]),
                             ("refs/tags/" + tag, "commit", event["release_commit"]), tag)
        commit = body("%s/git/commits/%s" % (api, event["release_commit"]))
        self.assertEqual(commit["sha"], event["release_commit"])
        # The cut itself, as its own fixture holds it, ended before the first commit, not only the commit it cut at.
        was_cut = json.loads(self.SEVENTH_CUT.read_text())
        made = self.item(was_cut, "cut_and_move_of_next")
        self.assertEqual((was_cut["version"], made["asked"]["cut_commit"]), (event["release"], event["release_commit"]))
        cut_at = self.answered(made, "/repos/%s/actions/runs/%d" % (REPO, made["run"]))["body"]["updated_at"]
        first = min(c["commit"]["committer"]["date"] for c in pushed)
        self.assertLess(commit["committer"]["date"], cut_at)
        self.assertLess(cut_at, first, "the Release was cut before the pull request's first commit")
        # Each step is one pass's Decision, in the order the passes ran, and its record is the artifact GitHub lists.
        self.assertEqual([(s["state"], s["reason"], s["outcome"], s["action"]) for s in steps],
                         [("verifying", "awaiting_checks", "nothing", None), ("verifying", "awaiting_review", "admit", None),
                          ("converged", "approval_due", "act", "issue_approval"), ("queued", "in_merge_queue", "nothing", None)])
        self.assertEqual([s["attention"] for s in steps], ["review", "review", "ready", "ready"])
        # Each a pass of its own, by its id, its run and its record, after the head was pushed and one after another.
        self.assertEqual([s["now"] for s in steps], sorted({s["now"] for s in steps}))
        for key in ("pass", "poller_run", "artifact", "digest"):
            self.assertEqual(len({s[key] for s in steps}), len(steps), key)
        self.assertLess(pushed[-1]["commit"]["committer"]["date"], steps[0]["now"])
        # Each pass read the head that merged: a commit's date is its author's word, the head a pass read is the pass's.
        self.assertEqual({s["head"] for s in steps}, {event["head"]})
        for s in steps:
            with self.subTest(step=s["pass"]):
                ran = body("%s/actions/runs/%d" % (api, s["poller_run"]))
                self.assertEqual((ran["id"], ran["path"], ran["status"], ran["conclusion"], ran["head_branch"]),
                                 (s["poller_run"], ".github/workflows/poller.yml", "completed", "success", "main"))
                self.assertTrue(ran["created_at"] <= s["now"] <= ran["updated_at"], s)
                held = [a for a in body("%s/actions/runs/%d/artifacts" % (api, s["poller_run"]))["artifacts"] if a["name"] == "pass"]
                self.assertEqual([(a["id"], a["digest"], a["expired"]) for a in held], [(s["artifact"], s["digest"], False)])
        # The review Run and the approving act are the Runs those passes admitted, by the name each carries: the item,
        # its Intent, the Role and the Run's id, and for the act the content the Decision approved. Each succeeded.
        admitted, acted = steps[1], steps[2]
        self.assertEqual((event["review_run"]["run"], event["approving_run"]["run"]), (admitted["run"], acted["run"]))
        item = "sf %s#%d" % (fixture["repo"], event["pull_request"])
        for which, step, path, intent in (("review_run", admitted, "run.yml", "review-change"),
                                          ("approving_run", acted, "approve.yml", "issue-approval")):
            with self.subTest(run=which):
                ran = body("%s/actions/runs/%d" % (api, event[which]["github_run"]))
                self.assertEqual((ran["id"], ran["path"], ran["event"], ran["status"], ran["conclusion"], ran["run_attempt"],
                                  ran["head_branch"]), (event[which]["github_run"], ".github/workflows/" + path,
                                                        "workflow_dispatch", "completed", "success", 1, "main"))
                # The name is the item, the Intent, the Role, the content and the Run's id: the review was of the
                # content the act approved.
                self.assertEqual(ran["name"].split(" "),
                                 item.split(" ") + [intent, defaults["owner_role"], acted["content_id"], step["run"]])
                self.assertLessEqual(step["now"], ran["created_at"])
                kept = body("%s/actions/runs/%d/artifacts" % (api, event[which]["github_run"]))["artifacts"]
                self.assertEqual(len([a for a in kept if a["name"] == "applied"]), 1)
                # The Run's own outcome names the Release it ran under, the event's, and no fault.
                ended = event[which]["outcome"]
                self.assertEqual([(a["id"], a["digest"]) for a in kept if a["name"] == "outcome"], [(ended["artifact"], ended["digest"])])
                self.assertEqual((ended["release"], ended["outcome"], ended["reason"]), (event["release"], None, None))
        act = body("%s/actions/runs/%d" % (api, event["approving_run"]["github_run"]))
        self.assertTrue(act["created_at"] <= event["approval"]["at"] <= act["updated_at"])
        review = body("%s/actions/runs/%d" % (api, event["review_run"]["github_run"]))
        self.assertLessEqual(review["updated_at"], acted["now"])
        # The Role's own review, a comment by its App on the head, was posted within its Run.
        posted = [r for r in reviews if r["user"]["login"] == apps[defaults["owner_role"]]["name"] + "[bot]"]
        self.assertEqual([(r["user"]["type"], r["state"], r["commit_id"]) for r in posted], [("Bot", "COMMENTED", event["head"])])
        self.assertTrue(review["created_at"] <= posted[0]["submitted_at"] <= review["updated_at"])
        self.assertLess(event["approval"]["at"], event["enqueued"]["at"])
        self.assertLess(event["enqueued"]["at"], steps[-1]["now"])
        self.assertLess(steps[-1]["now"], event["merged"]["at"])
        # The status on the item, read back after the merge, is the last step's: its State and code, never a sentence.
        status = body("%s/commits/%s/check-runs?check_name=%s" % (api, event["head"], defaults["status_on_item"]))
        self.assertEqual(status["total_count"], 1)
        shown, = status["check_runs"]
        self.assertEqual((shown["name"], shown["app"]["slug"], shown["conclusion"], shown["head_sha"]),
                         (defaults["status_on_item"], apps["controller"]["name"], "neutral", event["head"]))
        # Word for word what the effects port writes for the last step's Decision under this pass and Release, who
        # acts next among it, as `config/feed.json` gives it.
        feed = json.loads((ROOT / "config" / "feed.json").read_text())
        self.assertEqual(shown["output"], effects.status_output(dict(steps[-1], evidence=[]),
                                                                {"pass": steps[-1]["pass"], "release": event["release"]}, feed))

    def test_a_rollback_with_no_earlier_release_was_refused_and_moved_nothing(self):
        # Run 42405016612 asked a rollback on 2026-11-07 while factory/v0.1.0 was the one Release: the step was refused,
        # as the rules refuse it for every tag read after it, and `next` still names the Release, with its one
        # Deployment, the cut's (#197).
        fixture = json.loads(self.ROLLBACK.read_text())
        self.assertEqual(check_release.fixture_problems(fixture, "rollback.refused.json"), [])
        refused = self.item(fixture, "refused_rollback_with_no_earlier_release")
        rings = json.loads(move.RINGS.read_text())
        channel = move.next_channel(rings)
        self.assertEqual((refused["asked"]["command"], refused["asked"]["version"], refused["asked"]["to"]),
                         ("rollback", "", ""))
        self.assertEqual((refused["conclusion"], refused["printed"]),
                         ("failure", {"writes": [], "deployments": [], "refused": cut.NO_EARLIER_RELEASE}))
        # Every factory/ tag, read as the step's port reads them: one Release, and `next` on its commit.
        listed = [e for e in refused["exchanges"] if e["request"]["call"].split(" ")[1] == tags.path(REPO)]
        refs = tags.read(github.Replay(listed), REPO)
        commit = refs[fixture["version"]]
        self.assertEqual(refs, {fixture["version"]: commit, channel: commit})
        for tag in (fixture["version"], channel):
            with self.subTest(tag=tag):
                ref = self.answered(refused, "/repos/%s/git/ref/tags/%s" % (REPO, tag))
                self.assertEqual((ref["status"], ref["body"]["object"]["sha"]), (200, commit))
        step = move.asked({"RELEASE_" + k.upper(): v for k, v in refused["asked"].items()}, channel)
        self.assertEqual(cut.plan(step, refs, {}, move.channels(rings)), ([], cut.NO_EARLIER_RELEASE))
        run = self.answered(refused, "/repos/%s/actions/runs/%d" % (REPO, refused["run"]))["body"]
        made = self.item(json.loads(self.CUT.read_text()), "cut_and_move_of_next")
        # Each read is GitHub's answer, 200: a read it refused would show nothing of what the run left.
        listing = self.answered(refused, "/repos/%s/deployments?environment=factory-next" % REPO)
        self.assertEqual(listing["status"], 200)
        deployed = listing["body"]
        self.assertEqual([(d["id"], d["sha"], d["description"]) for d in deployed],
                         [(made["printed"]["deployments"][0], commit, fixture["version"])])
        answered = self.answered(refused, "/repos/%s/deployments/%d/statuses" % (REPO, deployed[0]["id"]))
        self.assertEqual(answered["status"], 200)
        statuses = answered["body"]
        self.assertEqual([s["state"] for s in statuses], ["success"])
        for made_at in [deployed[0]["created_at"]] + [s["created_at"] for s in statuses]:
            self.assertLess(made_at, run["created_at"])
        # Each read was made after the run had ended: what it shows is what the run left.
        ended = datetime.datetime.strptime(run["updated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        for e in refused["exchanges"]:
            with self.subTest(call=e["request"]["call"]):
                self.assertGreater(email.utils.parsedate_to_datetime(e["response"]["headers"]["date"]), ended)

    def test_an_item_that_says_other_than_its_own_exchanges_is_refused(self):
        fixture = json.loads(self.PATH.read_text())

        def refused(change):
            held = copy.deepcopy(fixture)
            change(held["items"][0])
            return check_release.fixture_problems(held, "gate.v0-1-0.json")

        def exchange(item, part):
            return next(e for e in item["exchanges"] if part in e["request"]["call"])

        changes = {
            "the step printed another code": lambda i: i["printed"].update(refused="not_verified"),
            "the step printed a write": lambda i: i["printed"]["writes"].append(["create", "factory/v0.1.0", A]),
            "another version was asked": lambda i: i["asked"].update(version="factory/v0.2.0"),
            "another commit was asked": lambda i: i["asked"].update(cut_commit=A),
            "another run": lambda i: i.update(run=i["run"] + 1),
            "another conclusion": lambda i: i.update(conclusion="success"),
            "the run's answer names another run": lambda i: exchange(i, "/actions/runs/")["response"]["body"].update(
                id=i["run"] + 1),
            "a second job of the run, its log not read": lambda i: exchange(i, "/jobs")["response"]["body"]["jobs"].append(
                {"id": 1, "run_id": i["run"]}),
            "a line of the log beyond the step's": lambda i: exchange(i, "/logs")["response"].update(body="\n".join(
                (lambda lines: lines[:1] + ["2026-10-31T12:29:15.6000000Z x-oauth-scopes: admin:org"] + lines[1:])(
                    exchange(i, "/logs")["response"]["body"].splitlines()))),
            "an input after the last line": lambda i: exchange(i, "/logs")["response"].update(
                body=exchange(i, "/logs")["response"]["body"] + "\n2026-10-31T12:29:19.0000000Z   RELEASE_TO: "),
            "the run read again and refused": lambda i: i["exchanges"].append(dict(
                copy.deepcopy(exchange(i, "/actions/runs/")), response={"status": 404, "headers": {}, "body": None})),
            "a line of the log with no time": lambda i: exchange(i, "/logs")["response"].update(
                body=exchange(i, "/logs")["response"]["body"] + "\nHTTP/2.0 302 Found"),
            "the step's group not first": lambda i: exchange(i, "/logs")["response"].update(body="\n".join(
                (lambda lines: [lines[1], lines[0]] + lines[2:])(exchange(i, "/logs")["response"]["body"].splitlines()))),
            "two last lines": lambda i: exchange(i, "/logs")["response"].update(
                body=exchange(i, "/logs")["response"]["body"] + '\n2026-10-31T12:29:18.3000000Z {"writes": [], "deployments": []}'),
            "the run of another workflow": lambda i: exchange(i, "/actions/runs/")["response"]["body"].update(
                path=".github/workflows/verify.yml"),
            "the run read twice": lambda i: i["exchanges"].append(copy.deepcopy(exchange(i, "/actions/runs/"))),
            "the run refused": lambda i: exchange(i, "/actions/runs/")["response"].update(status=404),
            "the log of another run's job": lambda i: exchange(i, "/jobs")["response"]["body"]["jobs"][0].update(
                run_id=i["run"] + 1),
            "the log not read": lambda i: i["exchanges"].remove(exchange(i, "/logs")),
            "the log's last line in other words": lambda i: exchange(i, "/logs")["response"].update(
                body=exchange(i, "/logs")["response"]["body"].replace('"eval_gate_closed"', '"not_verified"')),
            "a header a fixture drops": lambda i: i["exchanges"][0]["response"]["headers"].update(
                {"x-github-edge-region": "iad"}),
            "a credential in an answer": lambda i: i["exchanges"][3]["response"]["body"].update(
                note="ghp_" + "x" * 36),
        }
        for name, change in changes.items():
            with self.subTest(name):
                self.assertTrue(refused(change))
        # Every fixture of a Release's runs is held to its schema, whatever its name: nothing kept beside its items.
        for name, change in {"exchanges beside the items": lambda f: f.update(exchanges=[{"request": {"headers": {}},
                                                         "response": {"headers": {"x-oauth-scopes": "admin:org"}}}]),
                             "headers kept under another name": lambda f: f["items"][0]["exchanges"][0]["response"].update(
                                 raw_headers={"x-oauth-scopes": "admin:org"})}.items():
            with self.subTest(name):
                held = copy.deepcopy(fixture)
                change(held)
                self.assertTrue(check_release.fixture_problems(held, "gate.v0-2-0.json"))


class Plan(unittest.TestCase):
    def planned(self, reads, rings=move.RINGS):
        out = io.StringIO()
        text = reads if isinstance(reads, str) else json.dumps(reads)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = move.main(["plan"], io.StringIO(text), rings)
        return code, out.getvalue()

    def test_the_plan_is_printed_from_what_was_read_and_nothing_is_written(self):
        reads = {"step": cutting(), "refs": REFS, "facts": OPEN}
        self.assertEqual(self.planned(reads),
                         (0, json.dumps({"writes": [["create", "factory/v0.3.0", D], ["move", NEXT, D]]}) + "\n"))
        self.assertEqual(self.planned(dict(reads, facts=dict(OPEN, gate="eval_set_empty"))),
                         (1, json.dumps({"refused": cut.EVAL_GATE_CLOSED}) + "\n"))
        for odd in ("{", "[]", dict(reads, refs=None)):
            with self.subTest(reads=odd):
                self.assertEqual(self.planned(odd), (1, json.dumps({"refused": cut.STEP_UNREADABLE}) + "\n"))
        with tempfile.TemporaryDirectory() as scratch:
            self.assertEqual(self.planned(reads, pathlib.Path(scratch) / "none.json"),
                             (1, json.dumps({"refused": cut.NOT_A_CHANNEL}) + "\n"))
        # It is given its reads on standard input, and opens no path it is given (SonarCloud's S2083 and S8707).
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(move.main(["cut"], io.StringIO("{}")), 2)
            self.assertEqual(move.main(["plan", "reads.json"], io.StringIO("{}")), 2)


class Rings(unittest.TestCase):
    def test_next_serves_this_repo_and_stable_serves_nothing(self):
        rings = json.loads((ROOT / "release" / "rings.json").read_text())
        self.assertEqual({k: v["tag"] for k, v in rings["channels"].items()}, {"next": NEXT, "stable": STABLE})
        self.assertEqual({(s["repo"], s["channel"]) for s in rings["serves"]}, {(REPO, "next")})
        role = json.loads((ROOT / "roles" / "pr-review.json").read_text())
        self.assertEqual({s["family"] for s in rings["serves"]}, {i["name"] for i in role["intents"]})

    def test_no_repo_and_family_is_served_by_two_channels_and_both_are_of_one_major(self):
        rings = json.loads((ROOT / "release" / "rings.json").read_text())
        self.assertEqual(check_release.ring_problems(rings), [])
        twice = dict(rings, serves=rings["serves"] + [dict(rings["serves"][0], channel="stable")])
        self.assertEqual(len(check_release.ring_problems(twice)), 1)
        # One repo spelled in another case is the same repo (decision 0080, Muse's read of #340).
        cased = dict(rings, serves=rings["serves"] + [dict(rings["serves"][0], repo=rings["serves"][0]["repo"].upper(),
                                                           channel="stable")])
        self.assertEqual(len(check_release.ring_problems(cased)), 1)
        other = dict(rings, serves=rings["serves"] + [dict(rings["serves"][0], family="other-family", channel="stable")])
        self.assertEqual(check_release.ring_problems(other), [])
        majors = dict(rings, channels=dict(rings["channels"], stable={"tag": "factory/v1-stable"}))
        self.assertEqual(len(check_release.ring_problems(majors)), 1)
        # What the schema refuses is said there; this rule reads it without failing.
        for odd in ({"serves": ["x"], "channels": {"next": "x"}}, {"serves": None, "channels": []}, {}):
            with self.subTest(rings=odd):
                self.assertEqual(check_release.ring_problems(odd), [])

    def test_the_release_rules_import_nothing_but_each_other(self):
        for planted, found in (("import os\n", 1), ("from adapters import tags\n", 1), ("from . import x\n", 1),
                               ("x = open\n", 1), ("from release import move\n", 1), ("import release.move\n", 1),
                               ("from release.move import main\n", 1), ("from release import current, move\n", 1),
                               ("from __future__ import annotations\nfrom release import current\n", 0),
                               ("import release.current\n", 0)):
            with self.subTest(planted=planted), tempfile.TemporaryDirectory() as scratch:
                root = pathlib.Path(scratch)
                for rel in (check_release.RINGS, check_release.POINTS, check_release.HOOKS) + check_release.PURE:
                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
                    (root / rel).write_text((ROOT / rel).read_text())
                (root / "release" / "cut.py").write_text(planted)
                self.assertEqual(len(check_release.run(root)), found)


class Points(unittest.TestCase):
    """The Maintainer's continue or stop, and what he was shown before it (decision 0194)."""
    FIRST = "first_release_on_next"

    def live(self) -> dict:
        return json.loads((ROOT / check_release.POINTS).read_text())

    def test_the_first_decision_point_is_of_slice_1s_event_and_its_count_is_read_against_the_designs_figure(self):
        first, = [p for p in self.live()["points"] if p["point"] == self.FIRST]
        event = json.loads((ROOT / "release" / "fixtures" / "event.slice-1.json").read_text())["event"]
        shown = first["shown"]
        # The Release is the one that reviewed the event's pull request, and what is counted merged before it did.
        self.assertEqual(first["release"], event["release"])
        self.assertEqual(shown["before"], event["merged"]["at"])
        self.assertGreaterEqual(shown["read_on"], event["merged"]["at"][:10])
        design = (ROOT / "docs" / "architecture" / "software-factory-design.md").read_text()
        self.assertIn("against a starting figure of %d |" % shown["starting_figure"], design)
        self.assertEqual([p for p in check_examples.run() if "decision-points" in p], [])

    def test_a_point_is_decided_by_the_maintainer_alone_whole_once_and_on_what_he_was_shown(self):
        who = check_release.maintainer()
        self.assertEqual(who, json.loads((ROOT / check_release.HOOKS).read_text())["maintainer"]["login"])
        open_ = dict(self.live()["points"][0], decided=None, day=None, by=None)
        shown = open_["shown"]
        read = datetime.date.fromisoformat(shown["read_on"])
        decided = dict(open_, decided="continue", day=shown["read_on"], by=who)

        def found(*points, by=who) -> int:
            return len(check_release.point_problems({"schema": "decision-points/1", "points": list(points)}, by))

        # Not yet decided, and decided by him on the day he was shown the counts or after: nothing is wrong.
        self.assertEqual(found(open_), 0)
        self.assertEqual(found(decided), 0)
        self.assertEqual(found(dict(decided, decided="stop", day=(read + datetime.timedelta(days=1)).isoformat())), 0)
        self.assertEqual(found(dict(decided, day=(read - datetime.timedelta(days=1)).isoformat())), 1)
        # Another's decision is none, the machine user's among them; a login is one account whatever its case.
        for other in ("donpetry-bot", who + "x", who[:-1]):
            self.assertEqual(found(dict(decided, by=other)), 1, other)
        self.assertEqual(found(dict(decided, by=who.upper())), 0)
        self.assertEqual(found(dict(decided, by=who.lower()), by=who.upper()), 0)
        self.assertEqual(found(dict(decided, by=7)), 1)
        # With no Maintainer named, nobody's decision counts, and a point not decided is still nothing wrong.
        self.assertEqual(found(decided, by=None), 1)
        self.assertEqual(found(open_, by=None), 0)
        # What he writes is written whole: each one or two of the three alone is one problem, whoever is named.
        early = (read - datetime.timedelta(days=1)).isoformat()
        for kept in (("decided",), ("day",), ("by",), ("decided", "day"), ("decided", "by"), ("day", "by")):
            with self.subTest(kept=kept):
                self.assertEqual(found(dict(open_, **{name: decided[name] for name in kept})), 1)
                half = dict(open_, **{name: dict(decided, by="donpetry-bot", day=early)[name] for name in kept})
                self.assertEqual(found(half), 1)
                self.assertEqual(found(half, by=None), 1)
        # A point is recorded once, decided or not; two points of two names are two points.
        self.assertEqual(found(open_, dict(open_)), 1)
        self.assertEqual(found(decided, dict(decided, decided="stop")), 1)
        self.assertEqual(found(open_, dict(open_, point="first_consumer")), 0)
        self.assertEqual(found(decided, dict(decided, point="first_consumer")), 0)
        # What is counted merged before the event, so it is read on the event's day, in UTC, or after.
        event = datetime.date.fromisoformat(shown["before"][:10])
        self.assertEqual(found(dict(open_, shown=dict(shown, read_on=event.isoformat()))), 0)
        self.assertEqual(found(dict(open_, shown=dict(shown, read_on=(event - datetime.timedelta(days=1)).isoformat()))), 1)
        self.assertEqual(found(dict(open_, shown=dict(shown, read_on=(event + datetime.timedelta(days=1)).isoformat()))), 0)
        # A day is a day of the calendar, wherever one is written: the schema's pattern lets a 31st of November by.
        month = shown["read_on"][:8]
        self.assertEqual(found(dict(decided, day=month + "31")), 1 if month.endswith("-11-") else 0)
        self.assertEqual(found(dict(decided, day="2099-02-30")), 1)
        self.assertEqual(found(dict(open_, shown=dict(shown, read_on="2099-02-30"))), 1)
        self.assertEqual(found(dict(open_, shown=dict(shown, before="2000-02-30T00:00:00Z"))), 1)
        self.assertEqual(found(dict(decided, day="2096-02-29", shown=dict(shown, before="2000-02-29T00:00:00Z"))), 0)
        # A share is at most the count it is of, and a count is a number: true is not one.
        for share in ("the_maintainers", "touched_protected"):
            with self.subTest(share=share):
                self.assertEqual(found(dict(open_, shown=dict(shown, **{share: shown["merged"]}))), 0)
                self.assertEqual(found(dict(open_, shown=dict(shown, **{share: shown["merged"] + 1}))), 1)
        self.assertEqual(found(dict(open_, shown=dict(shown, merged=True, the_maintainers=0, touched_protected=0))), 0)
        self.assertEqual(found(dict(open_, shown=dict(shown, merged=True, the_maintainers=2, touched_protected=0))), 0)
        self.assertEqual(found(dict(open_, shown=dict(shown, merged=0, the_maintainers=True, touched_protected=0))), 0)
        # What the schema refuses is said there; this rule reads it without failing, each odd part alone.
        without = lambda name: {key: value for key, value in shown.items() if key != name}
        nameless = {key: value for key, value in open_.items() if key != "point"}
        for odd in ({}, [], {"points": None}, {"points": ["x"]}, {"points": [{"point": ["x"], "shown": 3}]},
                    {"points": [nameless, dict(nameless)]}, {"points": [dict(open_, point=7), dict(open_, point=7)]},
                    {"points": [dict(decided, shown=None)]}, {"points": [dict(decided, day=3)]},
                    {"points": [dict(decided, shown=without("read_on"))]}, {"points": [dict(open_, shown=without("before"))]},
                    {"points": [dict(decided, shown=dict(shown, read_on=3))]}, {"points": [dict(open_, shown=dict(shown, before=3))]},
                    {"points": [dict(open_, shown={"merged": 5})]}, {"points": [dict(open_, shown=dict(shown, merged="5"))]}):
            with self.subTest(points=odd):
                self.assertEqual(check_release.point_problems(odd, who), [])

    def test_each_counter_example_is_wrong_in_its_one_way(self):
        schema = json.loads((ROOT / "schemas" / "decision-points.schema.json").read_text())
        who = check_release.maintainer()
        self.assertEqual(validate(self.live(), schema), [])
        # A decision another login wrote is one the schema takes, and the check refuses for that alone.
        another = json.loads((ROOT / "examples" / "invalid" / "decision-points.decided-by-another.json").read_text())
        self.assertEqual(validate(another, schema), [])
        self.assertEqual(len(check_release.point_problems(another, who)), 1)
        # Either decision, in his name, is one the schema and the check both take.
        for decided in ("continue", "stop"):
            his = dict(another, points=[dict(another["points"][0], by=who, decided=decided)])
            self.assertEqual(validate(his, schema), [], decided)
            self.assertEqual(check_release.point_problems(his, who), [], decided)
        self.assertEqual(len(validate(dict(his, points=[dict(his["points"][0], decided="pause")]), schema)), 1)
        # A point with no count is refused by the schema, for that alone: the rest is the live file's, and the check's
        # own rule finds nothing in it.
        bare = json.loads((ROOT / "examples" / "invalid" / "decision-points.no-count.json").read_text())
        self.assertEqual(len(validate(bare, schema)), 1)
        self.assertEqual(check_release.point_problems(bare, who), [])
        self.assertEqual(dict(bare["points"][0]["shown"], merged=self.live()["points"][0]["shown"]["merged"]),
                         self.live()["points"][0]["shown"])
        self.assertEqual(validate(dict(bare, points=[dict(bare["points"][0], shown=dict(bare["points"][0]["shown"], merged=387))]),
                                  schema), [])

    def test_the_check_reads_the_points_and_the_maintainer_of_the_tree_it_is_given(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            for rel in (check_release.RINGS, check_release.POINTS, check_release.HOOKS) + check_release.PURE:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text((ROOT / rel).read_text())
            self.assertEqual(check_release.run(root), [])
            live = self.live()
            day = live["points"][0]["shown"]["read_on"]

            def decided_by(login: str) -> list:
                held = dict(live, points=[dict(live["points"][0], decided="continue", day=day, by=login)])
                (root / check_release.POINTS).write_text(json.dumps(held))
                return check_release.run(root)

            # The Maintainer is the one this tree's hooks file names, not the one the check's own tree does.
            (root / check_release.HOOKS).write_text(json.dumps({"maintainer": {"login": "someone-else"}}))
            self.assertEqual(check_release.maintainer(root), "someone-else")
            self.assertEqual(decided_by("someone-else"), [])
            self.assertEqual(len(decided_by(check_release.maintainer())), 1)
            # A hooks file that names nobody, is not JSON, or is not there names no Maintainer, and nobody decides.
            for text in ('{"maintainer": {"login": ""}}', '{"maintainer": {"login": ["someone-else"]}}',
                         '{"maintainer": "someone-else"}', '["someone-else"]', "{", None):
                with self.subTest(hooks=text):
                    if text is None:
                        (root / check_release.HOOKS).unlink()
                    else:
                        (root / check_release.HOOKS).write_text(text)
                    self.assertIsNone(check_release.maintainer(root))
                    self.assertEqual(len(decided_by("someone-else")), 1)
            # Points that are not JSON, or not there, are one problem each, named.
            (root / check_release.POINTS).write_text("{")
            self.assertEqual([p.split(" ")[0] for p in check_release.run(root)], [check_release.POINTS])
            (root / check_release.POINTS).unlink()
            self.assertEqual([p.split(" ")[0] for p in check_release.run(root)], [check_release.POINTS])


class Apps(unittest.TestCase):
    def test_each_of_the_release_apps_needs_is_its_own(self):
        # Ruling 4′: each write its workflow needs, and its read of runs, is the release App's and no other App's, so
        # nothing else can write a tag or move a Channel. The read of the tags is the reader's too, which names a Run's
        # own Release (ruling 8), under the contents read it holds.
        apps = json.loads((ROOT / "config" / "apps.json").read_text())
        # checks: read beside ruling 4′'s grants: adapters/candidate.verified reads verify's check runs (2026-10-26).
        own = {"write:release_tag": ("contents", "write"), "write:move_channel": ("contents", "write"),
               "write:workflow_commit_tag": ("workflows", "write"), "write:deployment": ("deployments", "write"),
               "read:release.runs": ("actions", "read"), "read:release.checks": ("checks", "read"),
               "read:release.repo": ("metadata", "read")}
        release = apps["apps"]["release"]["permissions"]
        for need, (permission, level) in own.items():
            with self.subTest(need=need):
                self.assertEqual(apps["needs"][need], {"permission": permission, "level": level})
                self.assertIn(need, release[permission]["needs"])
        others = {n for name, app in apps["apps"].items() if name != "release" for grant in app["permissions"].values()
                  for n in grant["needs"]}
        self.assertFalse(others & set(own))
        self.assertEqual(apps["needs"]["read:release.refs"], {"permission": "contents", "level": "read"})
        self.assertIn("read:release.refs", release["contents"]["needs"])
        self.assertIn("read:release.refs", apps["apps"]["reader"]["permissions"]["contents"]["needs"])


class Skill(unittest.TestCase):
    def test_every_command_the_skill_prints_is_one_the_tool_accepts(self):
        text = SKILL.read_text()
        commands = [line.strip() for block in re.findall(r"```(?:bash)?\n(.*?)```", text, re.S)
                    for line in block.splitlines() if line.strip() and not line.strip().startswith("#")]
        plans = [c for c in commands if "release.move" in c]
        dispatches = [c for c in commands if c.startswith("gh workflow run")]
        self.assertTrue(plans and dispatches)
        for command in plans:
            with self.subTest(command=command):
                words = shlex.split(command)
                self.assertEqual(words[:3], ["python3", "-m", "release.move"])
                self.assertEqual(words[3:5], ["plan", "<"])
                self.assertEqual(len(words), 6)
        for command in dispatches:
            with self.subTest(command=command):
                words = shlex.split(command)
                self.assertEqual(words[:4], ["gh", "workflow", "run", "release.yml"])
                fields = dict(w.split("=", 1) for w in words[4:] if "=" in w)
                self.assertEqual([w for w in words[4:] if w not in ("-f", "-R", REPO) and "=" not in w], [])
                self.assertIn(fields.get("command"), ("cut", "move", "rollback"))
                for name in ("version", "to"):
                    if name in fields:
                        self.assertTrue(current.version(fields[name]) or re.fullmatch(r"factory/v0\.X\.Y", fields[name]),
                                        fields[name])
        # Nothing else is printed to run: no write but the dispatch, and nothing that mints or shows a credential.
        self.assertEqual(sorted(commands), sorted(plans + dispatches))
        for command in commands:
            self.assertNotRegex(command, r"auth token|--show-token|\.pem|git (tag|push)|-X |--method")

    def test_when_the_factory_cannot_approve_the_skill_leaves_the_approval_to_the_maintainers_hand_and_runs_nothing(self):
        text = SKILL.read_text()
        section = text[text.index("## When the Factory cannot approve"):text.index("## Verify, then hand over")]
        # A Release that cannot approve: the Pause, the rollback, the hand approval last, and no other step or bullet.
        items = re.findall(r"^[ \t]*([0-9]+[.)]|[-*+])[ \t]+(.*)$", section, re.M)
        self.assertEqual([mark for mark, _ in items], ["1.", "2.", "3."])
        self.assertEqual([said.split("**")[1] for _, said in items], ["Pause.", "Roll `next` back.", "The hand approval."])
        self.assertIn("3. **The hand approval.** Only when no Release can serve.", section)
        # The Pause is a person's, the approval is the Maintainer's hand as the machine user, and no token is stored.
        self.assertIn("1. **Pause.** The Maintainer sets the repo variable `FACTORY_PAUSED` to `true`.", section)
        self.assertIn("he approves the head by hand as the machine user, in a browser\nsigned in to that account", section)
        self.assertIn("It needs no Release, no Run and no stored token;", section)
        self.assertIn("A session stops before the hand approval and hands him the steps", section)
        self.assertIn("It approves nothing, signs in to no account, and sets no variable.", section)
        # A change the Factory may not approve is taken out of the queue by the Kernel's own Decision, which nothing
        # carries out while no queue account is named: the day one is, the section's "no Pause is needed" is over.
        self.assertIn("While `accounts.queue` in\n`config/controller.json` is null, nothing carries that Decision out", section)
        self.assertIsNone(json.loads((ROOT / "config" / "controller.json").read_text())["accounts"]["queue"])
        # A hand approval alarms, and the section says so.
        self.assertIn("The next pass raises the alert `write_unmatched` for it", section)
        # It gives nothing to run, in a fence, an indented block or a span; and beyond these, word for word it is the
        # text this file names, so a command put in any other way, or any other change, fails here until it is read.
        self.assertNotRegex(section, r"```|~~~|``")
        self.assertIsNone(re.search(r"^(?: {4}|\t)", section, re.M))
        self.assertEqual([span for span in re.findall(r"`([^`]*)`", section) if re.search(r"\s", span)], [])
        self.assertEqual(hashlib.sha256(section.encode()).hexdigest(), CANNOT_APPROVE_SHA256)


if __name__ == "__main__":
    unittest.main()
