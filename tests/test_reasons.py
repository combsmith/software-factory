"""Every reason the Kernel gives is in one of two sets in kernel/terms.py (decision 0248).

`REASONS` holds the reasons a pull request's Decision can carry, decision/1's, and `ISSUE_REASONS` those only an
issue's Decision carries, issue-decision/1's. A reason both give is in `REASONS`. Two tests hold them. One reads the
Kernel's source: every reason written where a reason is made, passed on or compared is a literal in the right set, a
choice between two such literals, or a reason read on; anything else cannot be read, and fails. The other is the
binding one: it records every Decision the Kernel's own boundary suites and the simulator's fixed seeds give, and holds
each reason to its kind's set, and each member to a Decision of its kind that gives it.
"""
from __future__ import annotations

import ast
import io
import os
import re
import unittest

import kernel.decide
import kernel.issue
from kernel import terms
from sim.issues import IssueWorld
from sim.world import World
from tests.support import ROOT

KERNEL = ROOT / "kernel"
# The one module whose Decisions are an issue's. A literal reason in any other is a pull request's, or both kinds'.
ISSUE_MODULE = "issue.py"
# The tables a reason is read against by name. `past` is `reading`'s, which `derive` gives QUEUE_WAITS.
TABLES = ("NEEDS_YOU_REASONS", "QUIET_REASONS", "SCOPE_DEFERRALS", "GATE_REASONS", "QUEUE_WAITS", "past")
# What the binding test records: the Kernel's boundary suites, and each world on the fixed seeds, as the simulator's
# own tests run them. SIM_SEEDS shortens a local run.
SUITES = ("tests.test_decide", "tests.test_issue")
SEEDS = range(1, 1 + int(os.environ.get("SIM_SEEDS", "300")))
STEPS = 250


def _name(node):
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None


def _read_on(node) -> bool:
    """Whether `node` is a reason made elsewhere: the name `reason`, or the "reason" of a Decision or a reading."""
    return (isinstance(node, ast.Name) and node.id == "reason") or (
        isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and node.slice.value == "reason")


def _give(node, found: list, unread: list) -> None:
    """Each literal reason `node` gives where a reason goes, into `found`; its line into `unread` if it cannot be read."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        found.append((node.lineno, node.value))
    elif isinstance(node, ast.IfExp):
        _give(node.body, found, unread)
        _give(node.orelse, found, unread)
    elif not _read_on(node):
        unread.append(node.lineno)


def takers(trees: dict) -> dict:
    """`{name: place}` of each Kernel function's parameter `reason`, among its positional ones. A name two functions
    share with the parameter at other places is -1: no call to it can be read."""
    out = {}
    for tree in trees.values():
        for fn in ast.walk(tree):
            names = [a.arg for a in fn.args.posonlyargs + fn.args.args] if isinstance(fn, ast.FunctionDef) else []
            if "reason" in names:
                at = names.index("reason")
                out[fn.name] = at if out.get(fn.name, at) == at else -1
    return out


def written(tree, taken: dict) -> tuple:
    """`(found, unread, calls)` of one module: each literal reason with its line, the lines of reasons that cannot be
    read, and how many calls pass a reason on. A reason is written as a Decision's or a reading's "reason", as the
    argument `reason`, by name or by place, to a function that takes one, as a value given the name `reason`, as a
    literal compared with a reason or a table of them, and as a member of a table."""
    found, unread, calls = [], [], 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "reason":
                    _give(value, found, unread)
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "reason":
                    _give(kw.value, found, unread)
            at = taken.get(_name(node.func))
            if at is not None:
                calls += 1
                ahead = node.args[:at + 1]
                if at < 0 or any(isinstance(a, ast.Starred) for a in ahead):
                    unread.append(node.lineno)
                elif at < len(node.args):
                    _give(node.args[at], found, unread)
        if isinstance(node, ast.Assign):
            names = [_name(target) for target in node.targets]
            if "reason" in names:
                _give(node.value, found, unread)
            if node in tree.body and any(name in TABLES for name in names):
                found += [(n.lineno, n.value) for n in ast.walk(node.value)
                          if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        if isinstance(node, ast.Compare):
            sides = [node.left] + node.comparators
            reads = any(_read_on(side) for side in sides)
            if reads or any(_name(side) in TABLES for side in sides):
                for side in sides:
                    if isinstance(side, (ast.Tuple, ast.List, ast.Set)):
                        for member in side.elts:
                            _give(member, found, unread)
                    elif isinstance(side, ast.Constant) or (reads and _name(side) not in TABLES):
                        _give(side, found, unread)
    return found, unread, calls


def kernel_trees() -> dict:
    return {path.name: ast.parse(path.read_text(), path.name) for path in sorted(KERNEL.glob("*.py"))}


class Written(unittest.TestCase):
    def test_every_reason_the_kernel_writes_is_in_its_set(self):
        trees = kernel_trees()
        taken = takers(trees)
        # The three places a reason is passed on, not written: each is followed to every call.
        self.assertEqual({taken.get("_decision"), taken.get("out"), taken.get("_stop")}, {1, 2})
        seen, passed = set(), 0
        for name, tree in sorted(trees.items()):
            found, unread, calls = written(tree, taken)
            passed += calls
            right = terms.REASONS | terms.ISSUE_REASONS if name == ISSUE_MODULE else terms.REASONS
            with self.subTest(module=name):
                self.assertEqual(unread, [], "kernel/%s gives a reason the test cannot read" % name)
                self.assertEqual([(line, why) for line, why in found if why not in right], [],
                                 "kernel/%s writes a reason in neither set, or an issue's where a pull request's goes"
                                 % name)
            seen |= {why for _, why in found}
        self.assertGreater(passed, 100)
        # No member is written nowhere: each is a literal where a reason is made, passed on or compared.
        self.assertEqual(sorted((terms.REASONS | terms.ISSUE_REASONS) - seen), [])

    def test_the_two_sets_are_apart_and_each_is_codes(self):
        self.assertIsInstance(terms.REASONS, frozenset)
        self.assertIsInstance(terms.ISSUE_REASONS, frozenset)
        self.assertEqual(sorted(terms.REASONS & terms.ISSUE_REASONS), [])
        self.assertEqual([why for why in terms.REASONS | terms.ISSUE_REASONS if not re.fullmatch(r"[a-z_]+", why)], [])

    def test_a_reason_written_any_way_is_read(self):
        taken = {"_decision": 2, "out": 1, "twice": -1}
        cases = (
            ('{"reason": "x"}', ["x"], []),
            ('_decision(f, s, "x", e, o)', ["x"], []),
            ('out(s, "a" if c else "b", [])', ["a", "b"], []),
            ('dict(d, reason="x")', ["x"], []),
            ('reason = "x"', ["x"], []),
            ('reason == "x"', ["x"], []),
            ('d["reason"] in ("a", "b")', ["a", "b"], []),
            ('"x" not in past', ["x"], []),
            ('entry["run"] not in past', [], []),
            ('GATE_REASONS = ("a", "b")', ["a", "b"], []),
            ('def f():\n    past = "a" if c else []', [], []),
            ('_decision(f, s, reason, e, o)', [], []),
            ('_decision(f, s, d["reason"], e, o)', [], []),
            ('_decision(f, s, why(), e, o)', [], [1]),
            ('_decision(*a)', [], [1]),
            ('twice(f, "x")', [], [1]),
            ('{"reason": "a" + b}', [], [1]),
            ('reason in OTHER', [], [1]),
            ('state == "x"', [], []),
        )
        for source, found, unread in cases:
            with self.subTest(source=source):
                got, lines, _ = written(ast.parse(source), taken)
                self.assertEqual(([why for _, why in got], lines), (found, unread))


def given() -> dict:
    """`{"pull_request": reasons, "issue": reasons}` of every Decision the suites and the seeds give."""
    seen = {"pull_request": set(), "issue": set()}
    kept = {}
    for module, kind in ((kernel.decide, "pull_request"), (kernel.issue, "issue")):
        kept[module] = module._decision

        def record(facts, state, reason, *rest, _kind=kind, _made=module._decision, **extra):
            seen[_kind].add(reason)
            return _made(facts, state, reason, *rest, **extra)

        module._decision = record
    try:
        suite = unittest.defaultTestLoader.loadTestsFromNames(SUITES)
        unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        for seed in SEEDS:
            for world in (World(seed), IssueWorld(seed)):
                for _ in range(STEPS):
                    world.step()
    finally:
        for module, made in kept.items():
            module._decision = made
    return seen


class Given(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seen = given()

    def test_every_decision_carries_a_reason_of_its_own_set(self):
        self.assertEqual(sorted(self.seen["pull_request"] - terms.REASONS), [])
        self.assertEqual(sorted(self.seen["issue"] - terms.REASONS - terms.ISSUE_REASONS), [])

    def test_every_member_is_given_by_a_decision_of_its_kind(self):
        self.assertEqual(sorted(terms.REASONS - self.seen["pull_request"]), [])
        self.assertEqual(sorted(terms.ISSUE_REASONS - self.seen["issue"]), [])


if __name__ == "__main__":
    unittest.main()
