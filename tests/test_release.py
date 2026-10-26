"""The Release: the cut, the move and the rollback planned by `release/cut.py`, a commit's Release named by
`release/current.py`, the tags read by `adapters/tags.py`, and the skill's commands (#197's rulings 2 to 7, 4′, 4″,
5′ and 10′). No test writes a tag or reads GitHub: the refs are made up, and the port is answered by a replay."""
from __future__ import annotations

import ast
import contextlib
import io
import json
import pathlib
import re
import shlex
import tempfile
import unittest

from adapters import github, tags
from harness import eval as eval_gate
from release import current, cut, move
from tools import check_release

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "cut-a-release" / "SKILL.md"
REPO = "combsmith/software-factory"
A, B, C, D = ("a" * 40, "b" * 40, "c" * 40, "d" * 40)
NEXT, STABLE = "factory/v0-next", "factory/v0-stable"
# Two Releases, `next` on the later; a commit D on main, verified, with the eval gate open.
REFS = {"factory/v0.1.0": A, "factory/v0.2.0": B, NEXT: B}
OPEN = {"commit": D, "on_main": True, "verified": True, "gate": cut.PASS}


def cutting(version="factory/v0.3.0", commit=D, channel=NEXT):
    return {"command": "cut", "version": version, "commit": commit, "channel": channel}


class Cut(unittest.TestCase):
    def test_a_cut_creates_the_release_and_moves_next_to_it_in_one_plan(self):
        self.assertEqual(cut.plan(cutting(), REFS, OPEN),
                         ([("create", "factory/v0.3.0", D), ("move", NEXT, D)], None))

    def test_each_rule_of_a_cut_refuses_with_its_own_code(self):
        for step, facts, code in (
                (cutting(version="factory/v0.2.0"), OPEN, cut.NOT_NEWER),
                (cutting(), dict(OPEN, on_main=False), cut.NOT_ON_MAIN),
                (cutting(), dict(OPEN, on_main=None), cut.NOT_ON_MAIN),
                (cutting(), dict(OPEN, verified=False), cut.NOT_VERIFIED),
                (cutting(), dict(OPEN, verified="true"), cut.NOT_VERIFIED),
                (cutting(commit=A), dict(OPEN, commit=A), cut.ALREADY_RELEASED),
                (cutting(version="factory/v0.1.5"), OPEN, cut.NOT_NEWER),
                (cutting(version="factory/v1.0.0"), OPEN, cut.ANOTHER_MAJOR),
                (cutting(), dict(OPEN, gate="eval_set_empty"), cut.EVAL_GATE_CLOSED),
                (cutting(), dict(OPEN, commit=C), cut.STEP_UNREADABLE),
                (cutting(version="factory/v0.3"), OPEN, cut.STEP_UNREADABLE),
                (cutting(commit=""), dict(OPEN, commit=""), cut.STEP_UNREADABLE)):
            with self.subTest(step=step, facts=facts):
                self.assertEqual(cut.plan(step, REFS, facts), ([], code))

    def test_a_closed_eval_gate_refuses_every_cut_and_move_and_burns_no_version(self):
        # The gate is the eval report's verdict on the commit (ruling 4″): anything but `pass` refuses, and it is read
        # before any write, so the version asked is still free once the gate opens.
        self.assertEqual(cut.PASS, eval_gate.PASS)
        for word in ("eval_set_empty", "case_failed", "another_commit", "report_unreadable", None, True, "PASS"):
            with self.subTest(gate=word):
                self.assertEqual(cut.plan(cutting(), REFS, dict(OPEN, gate=word)), ([], cut.EVAL_GATE_CLOSED))
                moved = cut.plan({"command": "move", "channel": NEXT, "to": "factory/v0.1.0"}, REFS,
                                 dict(OPEN, commit=A, gate=word))
                self.assertEqual(moved, ([], cut.EVAL_GATE_CLOSED))
        self.assertIsNone(cut.plan(cutting(), REFS, OPEN)[1])

    def test_no_step_writes_a_release_tag_and_none_names_anything_but_a_channel(self):
        for command in ("cut", "move", "rollback"):
            for channel, code in (("factory/v0.2.0", cut.RELEASE_IS_IMMUTABLE), ("factory/v0-latest", cut.NOT_A_CHANNEL),
                                  ("main", cut.NOT_A_CHANNEL), (None, cut.NOT_A_CHANNEL)):
                with self.subTest(command=command, channel=channel):
                    step = dict(cutting(channel=channel), command=command, to="factory/v0.1.0")
                    self.assertEqual(cut.plan(step, REFS, OPEN), ([], code))

    def test_stable_is_never_moved_until_promotion_is_built(self):
        for command in ("cut", "move", "rollback"):
            with self.subTest(command=command):
                step = dict(cutting(channel=STABLE), command=command, to="factory/v0.1.0")
                self.assertEqual(cut.plan(step, dict(REFS, **{STABLE: B}), OPEN), ([], cut.PROMOTION_NOT_BUILT))

    def test_a_step_that_cannot_be_read_is_refused(self):
        for step, refs, facts in (("cut", REFS, OPEN), (cutting(), None, OPEN), (cutting(), REFS, None),
                                  (dict(cutting(), command="delete"), REFS, OPEN)):
            with self.subTest(step=step):
                self.assertEqual(cut.plan(step, refs, facts), ([], cut.STEP_UNREADABLE))
        self.assertTrue(set(cut.CODES) <= set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", (ROOT / "release" / "cut.py")
                                                         .read_text())))


class Move(unittest.TestCase):
    def test_next_moves_only_to_an_existing_release_of_its_major_through_the_gate(self):
        step = {"command": "move", "channel": NEXT, "to": "factory/v0.1.0"}
        self.assertEqual(cut.plan(step, REFS, dict(OPEN, commit=A)), ([("move", NEXT, A)], None))
        for to, code in (("factory/v0.9.0", cut.NOT_A_RELEASE), (NEXT, cut.NOT_A_RELEASE), (None, cut.NOT_A_RELEASE),
                         ("factory/v1.0.0", cut.ANOTHER_MAJOR)):
            with self.subTest(to=to):
                refs = dict(REFS, **{"factory/v1.0.0": C})
                self.assertEqual(cut.plan(dict(step, to=to), refs, dict(OPEN, commit=C)), ([], code))
        self.assertEqual(cut.plan(step, REFS, dict(OPEN, commit=A, on_main=False)), ([], cut.NOT_ON_MAIN))
        self.assertEqual(cut.plan(step, REFS, dict(OPEN, commit=A, verified=False)), ([], cut.NOT_VERIFIED))
        self.assertEqual(cut.plan(step, REFS, OPEN), ([], cut.STEP_UNREADABLE))


class Rollback(unittest.TestCase):
    def test_a_rollback_by_default_takes_the_greatest_release_below_the_one_next_is_on(self):
        refs = dict(REFS, **{"factory/v0.1.9": C, "factory/v0.3.0": D, "factory/v1.0.0": "e" * 40})
        self.assertEqual(cut.default_target(NEXT, refs), "factory/v0.1.9")
        self.assertEqual(cut.plan({"command": "rollback", "channel": NEXT}, refs, {}), ([("move", NEXT, C)], None))
        self.assertEqual(cut.default_target(NEXT, {"factory/v0.1.0": A, NEXT: A}), None)
        self.assertEqual(cut.default_target(NEXT, {"factory/v0.1.0": A}), None)

    def test_a_rollback_passes_no_gate_and_never_moves_forward(self):
        # It must work while the Factory is broken (section 9.1), so it reads no facts; and since it passes no gate,
        # a rollback to a later Release, or from a Channel at no Release, is refused: that is the admin login's.
        step = {"command": "rollback", "channel": NEXT, "to": "factory/v0.1.0"}
        self.assertEqual(cut.plan(step, REFS, {"gate": "case_failed", "verified": False}), ([("move", NEXT, A)], None))
        later = dict(REFS, **{"factory/v0.3.0": D})
        self.assertEqual(cut.plan(dict(step, to="factory/v0.3.0"), later, {}), ([], cut.NOT_EARLIER))
        self.assertEqual(cut.plan(dict(step, to="factory/v0.2.0"), REFS, {}), ([], cut.NOT_EARLIER))
        self.assertEqual(cut.plan(step, dict(REFS, **{NEXT: C}), {}), ([], cut.NOT_EARLIER))
        self.assertEqual(cut.plan({"command": "rollback", "channel": NEXT}, {"factory/v0.1.0": A, NEXT: A}, {}),
                         ([], cut.NO_EARLIER_RELEASE))
        self.assertEqual(cut.plan(dict(step, to="factory/v0.0.9"), REFS, {}), ([], cut.NOT_A_RELEASE))


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
        self.assertEqual(imported, {"__future__", "re", "adapters.github"})
        self.assertEqual(check_release.run(), [])

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
        for repo in ("combsmith", "combsmith/..", "combsmith/x/y", "../x"):
            with self.subTest(repo=repo):
                self.assertIsNone(tags.read(answered([]), repo))


class Plan(unittest.TestCase):
    def planned(self, *values):
        with tempfile.TemporaryDirectory() as scratch:
            paths = []
            for n, value in enumerate(values):
                path = pathlib.Path(scratch) / ("%d.json" % n)
                path.write_text(value if isinstance(value, str) else json.dumps(value))
                paths.append(str(path))
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = move.main(["plan"] + paths)
        return code, out.getvalue()

    def test_the_plan_is_printed_from_what_was_read_and_nothing_is_written(self):
        self.assertEqual(self.planned(cutting(), REFS, OPEN),
                         (0, json.dumps({"writes": [["create", "factory/v0.3.0", D], ["move", NEXT, D]]}) + "\n"))
        self.assertEqual(self.planned(cutting(), REFS, dict(OPEN, gate="eval_set_empty")),
                         (1, json.dumps({"refused": cut.EVAL_GATE_CLOSED}) + "\n"))
        self.assertEqual(self.planned(cutting(), "{", OPEN), (1, json.dumps({"refused": cut.STEP_UNREADABLE}) + "\n"))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(move.main(["cut", "a", "b", "c"]), 2)
            self.assertEqual(move.main(["plan", "a"]), 2)


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
        other = dict(rings, serves=rings["serves"] + [dict(rings["serves"][0], family="other-family", channel="stable")])
        self.assertEqual(check_release.ring_problems(other), [])
        majors = dict(rings, channels=dict(rings["channels"], stable={"tag": "factory/v1-stable"}))
        self.assertEqual(len(check_release.ring_problems(majors)), 1)

    def test_the_release_rules_import_nothing_but_each_other(self):
        for planted in ("import os\n", "from adapters import tags\n", "from . import x\n", "x = open\n"):
            with self.subTest(planted=planted), tempfile.TemporaryDirectory() as scratch:
                root = pathlib.Path(scratch)
                for rel in (check_release.RINGS,) + check_release.PURE:
                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
                    (root / rel).write_text((ROOT / rel).read_text())
                (root / "release" / "cut.py").write_text(planted)
                self.assertEqual(len(check_release.run(root)), 1)


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
                self.assertEqual((words[3], len(words[4:])), ("plan", 3))
        for command in dispatches:
            with self.subTest(command=command):
                words = shlex.split(command)
                self.assertEqual(words[:4], ["gh", "workflow", "run", "release.yml"])
                fields = dict(w.split("=", 1) for w in words[4:] if "=" in w)
                self.assertEqual([w for w in words[4:] if w not in ("-f", "-R", REPO) and "=" not in w], [])
                self.assertIn(fields.get("command"), ("cut", "rollback"))
                for name in ("version", "to"):
                    if name in fields:
                        self.assertTrue(current.version(fields[name]) or re.fullmatch(r"factory/v0\.X\.Y", fields[name]),
                                        fields[name])
        # Nothing else is printed to run: no write but the dispatch, and nothing that mints or shows a credential.
        self.assertEqual(sorted(commands), sorted(plans + dispatches))
        for command in commands:
            self.assertNotRegex(command, r"auth token|--show-token|\.pem|git (tag|push)|-X |--method")


if __name__ == "__main__":
    unittest.main()
