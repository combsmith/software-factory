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
# The sets themselves, which no Kernel rule reads.
SETS = ("REASONS", "ISSUE_REASONS")
# The tables a reason is read against by name, each bound once, at a module's top level, to a display of literals.
TABLES = ("NEEDS_YOU_REASONS", "QUIET_REASONS", "SCOPE_DEFERRALS", "GATE_REASONS", "QUEUE_WAITS")
# A table handed to a function: `reading`'s parameter `past`, which `derive` gives QUEUE_WAITS. It is never bound again.
HANDED = ("reading", "past")
# The names a reason is read on from, each bound to a reading or a Decision: `derive`'s and `_decide`'s `d`, and the
# issue's `bare`. The scan trusts what they hold; the runtime test holds what the Kernel gives.
HOLDERS = ("d", "bare")
# What the binding test records: the Kernel's boundary suites, and each world on the fixed seeds, as the simulator's
# own tests run them. SIM_SEEDS shortens a local run.
SUITES = ("tests.test_decide", "tests.test_issue")
SEEDS = range(1, 1 + int(os.environ.get("SIM_SEEDS", "300")))
STEPS = 250


def _name(node):
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None


def _keyed(node) -> bool:
    """Whether `node` reads a holder's "reason": `d["reason"]` or `d.get("reason")`."""
    if isinstance(node, ast.Subscript):
        base, key = node.value, node.slice
    elif isinstance(node, ast.Call) and _name(node.func) == "get" and len(node.args) == 1 and not node.keywords:
        base, key = node.func.value, node.args[0]
    else:
        return False
    return isinstance(key, ast.Constant) and key.value == "reason" and _name(base) in HOLDERS


def _read_on(node) -> bool:
    """Whether `node` is a reason made elsewhere: the name `reason`, or a holder's "reason"."""
    return (isinstance(node, ast.Name) and node.id == "reason") or _keyed(node)


def _give(node, found: list, unread: list) -> None:
    """Each literal reason `node` gives where a reason goes, into `found`; its line into `unread` if it cannot be read."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        found.append((node.lineno, node.value))
    elif isinstance(node, ast.IfExp):
        _give(node.body, found, unread)
        _give(node.orelse, found, unread)
    elif not _read_on(node):
        unread.append(node.lineno)


def _reason_slot(target) -> bool:
    """Whether `target`, bound or stored to, is a reason: the name `reason`, or any mapping's "reason"."""
    return (isinstance(target, ast.Name) and target.id == "reason") or (
        isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) and target.slice.value == "reason")


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


def _members(value, found: list, unread: list) -> None:
    """A table's members: a tuple, list or set display, or `frozenset` of one, each member a literal."""
    if isinstance(value, ast.Call) and _name(value.func) in ("frozenset", "set") and len(value.args) == 1:
        value = value.args[0]
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        for member in value.elts:
            (found.append((member.lineno, member.value)) if isinstance(member, ast.Constant)
             and isinstance(member.value, str) else unread.append(member.lineno))
    else:
        unread.append(value.lineno)


def _bound(target, value, found: list, unread: list) -> None:
    """A binding of `target` to `value`: a reason given to a reason's slot, pair by pair for tuples."""
    if isinstance(target, (ast.Tuple, ast.List)):
        if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts):
            for part, given in zip(target.elts, value.elts):
                _bound(part, given, found, unread)
        elif any(_reason_slot(n) for n in ast.walk(target)):
            unread.append(target.lineno)
    elif _reason_slot(target):
        _give(value, found, unread)


def written(tree, taken: dict) -> tuple:
    """`(found, unread, calls)` of one module: each literal reason with its line, the lines of reasons that cannot be
    read, and how many calls pass a reason on.

    A reason is written as a "reason" in a dict display, as the argument `reason`, by name or by place, to a function
    that takes one, or as its default, as a value bound or stored to the name `reason` or to a mapping's "reason", as a
    literal compared with a reason or a table of them, and as a member of a table. A call that gives no reason by
    place or name, a table bound anywhere but once at the top level, and a handed table bound again, cannot be read.
    """
    found, unread, calls = [], [], 0
    tops = {id(t) for node in tree.body if isinstance(node, ast.Assign) for t in node.targets}
    handed = {id(n) for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) and fn.name == HANDED[0]
              for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == HANDED[1]}

    def table(side) -> bool:
        return _name(side) in TABLES or id(side) in handed

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load) and (
                (node.id in TABLES and id(node) not in tops) or id(node) in handed):
            unread.append(node.lineno)
        if isinstance(node, ast.FunctionDef):
            spots = node.args.posonlyargs + node.args.args
            given = [None] * (len(spots) - len(node.args.defaults)) + node.args.defaults
            given += node.args.kw_defaults
            for arg, default in zip(spots + node.args.kwonlyargs, given):
                if arg.arg == "reason" and default is not None:
                    _give(default, found, unread)
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "reason":
                    _give(value, found, unread)
        if isinstance(node, ast.Call):
            named = [kw for kw in node.keywords if kw.arg == "reason"]
            for kw in named:
                _give(kw.value, found, unread)
            at = taken.get(_name(node.func))
            if at is not None:
                calls += 1
                ahead = node.args[:at + 1]
                if at < 0 or any(isinstance(a, ast.Starred) for a in ahead):
                    unread.append(node.lineno)
                elif at < len(node.args):
                    _give(node.args[at], found, unread)
                elif not named:
                    unread.append(node.lineno)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                _bound(target, node.value, found, unread)
                if id(target) in tops and _name(target) in TABLES:
                    _members(node.value, found, unread)
        if isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            if isinstance(node, ast.AugAssign) and _reason_slot(node.target):
                unread.append(node.lineno)
            else:
                _bound(node.target, node.value, found, unread)
        if isinstance(node, ast.Compare):
            sides = [node.left] + node.comparators
            if any(_read_on(side) or table(side) for side in sides):
                for side in sides:
                    if isinstance(side, (ast.Tuple, ast.List, ast.Set)):
                        for member in side.elts:
                            _give(member, found, unread)
                    elif not table(side):
                        _give(side, found, unread)
    return found, unread, calls


def read_of_sets(tree) -> list:
    """The lines where a module reads REASONS or ISSUE_REASONS: no Kernel rule may."""
    return [n.lineno for n in ast.walk(tree) if _name(n) in SETS and isinstance(getattr(n, "ctx", None), ast.Load)]


def kernel_trees() -> dict:
    """Every module under kernel/, at any depth, by its path there."""
    return {path.relative_to(KERNEL).as_posix(): ast.parse(path.read_text(), path.name)
            for path in sorted(KERNEL.rglob("*.py"))}


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

    def test_no_kernel_rule_reads_the_sets(self):
        for name, tree in sorted(kernel_trees().items()):
            with self.subTest(module=name):
                self.assertEqual(read_of_sets(tree), [], "kernel/%s reads REASONS or ISSUE_REASONS: they are data" % name)
        self.assertEqual(read_of_sets(ast.parse("if t.REASONS and c:\n    pass")), [1])

    def test_the_two_sets_are_apart_and_each_is_codes(self):
        self.assertIsInstance(terms.REASONS, frozenset)
        self.assertIsInstance(terms.ISSUE_REASONS, frozenset)
        self.assertEqual(sorted(terms.REASONS & terms.ISSUE_REASONS), [])
        self.assertEqual([why for why in terms.REASONS | terms.ISSUE_REASONS if not re.fullmatch(r"[a-z_]+", why)], [])

    def test_a_reason_written_any_way_is_read(self):
        taken = {"_decision": 2, "out": 1, "twice": -1, "relay": 1}
        cases = (
            ('{"reason": "x"}', ["x"], []),
            ('_decision(f, s, "x", e, o)', ["x"], []),
            ('out(s, "a" if c else "b", [])', ["a", "b"], []),
            ('dict(d, reason="x")', ["x"], []),
            ('reason = "x"', ["x"], []),
            ('reason == "x"', ["x"], []),
            ('d["reason"] in ("a", "b")', ["a", "b"], []),
            ('def reading(past):\n    return "x" not in past', ["x"], []),
            ('def reading(past):\n    return entry["run"] not in past', [], [2]),
            ('def unnamed_past(past):\n    return entry["run"] not in past', [], []),
            ('def reading(past):\n    past = (*past, "x")\n    return d["reason"] in past', [], [2]),
            ('def f(d, past):\n    past = (*past, "x")\n    return d["reason"] in past', [], [3]),
            ('def f():\n    GATE_REASONS = ("x",)', [], [2]),
            ('GATE_REASONS += ("x",)', [], [1]),
            ('reason += "x"', [], [1]),
            ('"x" not in past', [], []),
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
            ('out(s, {k: "x"}["reason"], [])', [], [1]),
            ('_decision(f, s, facts["reason"], e, o)', [], [1]),
            ('facts["reason"] == "x"', [], []),
            ('def relay(s, reason="x"):\n    return {"reason": reason}', ["x"], []),
            ('relay(s)', [], [1]),
            ('out(s, **kw)', [], [1]),
            ('d["reason"] = "x"', ["x"], []),
            ('reason: str = "x"', ["x"], []),
            ('state, reason = s, "x"', ["x"], []),
            ('state, reason = pair', [], [1]),
            ('GATE_REASONS = ("a" + "b",)', [], [1]),
            ('GATE_REASONS = frozenset({"a"})', ["a"], []),
            ('GATE_REASONS = make()', [], [1]),
            ('("a" if c else "b") in GATE_REASONS', ["a", "b"], []),
            ('d.get("reason") == "x"', ["x"], []),
        )
        for source, found, unread in cases:
            with self.subTest(source=source):
                got, lines, _ = written(ast.parse(source), taken)
                self.assertEqual(([why for _, why in got], lines), (found, unread))


def given() -> dict:
    """`{schema: reasons}` of every Decision the suites and the seeds give, read from what `decide` returns, and whether
    the suites passed while recorded. Each `decide` returns what its `_decide` returns, with its attention alone changed."""
    seen = {"decision/1": set(), "issue-decision/1": set(), "suites_passed": False}
    kept = {kernel.decide: kernel.decide._decide, kernel.issue: kernel.issue._decide}
    try:
        for module, made in kept.items():

            def record(*args, _made=made, **kwargs):
                d = _made(*args, **kwargs)
                seen.setdefault(d.get("schema"), set()).add(d.get("reason"))
                return d

            module._decide = record
        suite = unittest.defaultTestLoader.loadTestsFromNames(SUITES)
        seen["suites_passed"] = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite).wasSuccessful()
        for seed in SEEDS:
            for world in (World(seed), IssueWorld(seed)):
                for _ in range(STEPS):
                    world.step()
    finally:
        for module, made in kept.items():
            module._decide = made
    return seen


class Given(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seen = given()

    def test_every_decision_carries_a_reason_of_its_own_set(self):
        self.assertEqual(sorted(set(self.seen) - {"decision/1", "issue-decision/1", "suites_passed"}), [])
        self.assertEqual(sorted(self.seen["decision/1"] - terms.REASONS), [])
        self.assertEqual(sorted(self.seen["issue-decision/1"] - terms.REASONS - terms.ISSUE_REASONS), [])

    def test_every_member_is_given_by_a_decision_of_its_kind(self):
        # A suite that failed while it was recorded may have stopped short of a Decision: say so first.
        self.assertTrue(self.seen["suites_passed"], "%s failed while recorded; run them alone" % ", ".join(SUITES))
        self.assertEqual(sorted(terms.REASONS - self.seen["decision/1"]), [])
        self.assertEqual(sorted(terms.ISSUE_REASONS - self.seen["issue-decision/1"]), [])


if __name__ == "__main__":
    unittest.main()
