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
from tools import walk

KERNEL = ROOT / "kernel"
# The one module whose Decisions are an issue's. A literal reason in any other is a pull request's, or both kinds'.
ISSUE_MODULE = "issue.py"
# The sets themselves, which no Kernel rule reads.
SETS = ("REASONS", "ISSUE_REASONS")
# The tables a reason is read against by name, each bound once, at a module's top level, to a display of literals.
TABLES = ("NEEDS_YOU_REASONS", "QUIET_REASONS", "SCOPE_DEFERRALS", "GATE_REASONS", "QUEUE_WAITS")
# A table handed to a function: `reading`'s parameter `past`, which `derive` gives QUEUE_WAITS. It is never bound again.
HANDED = ("reading", "past")
HANDED_AT = 3
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
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" \
            and len(node.args) == 1 and not node.keywords:
        base, key = node.func.value, node.args[0]
    else:
        return False
    return isinstance(key, ast.Constant) and key.value == "reason" and isinstance(base, ast.Name) and base.id in HOLDERS


def _keyed_any(node) -> bool:
    """Whether `node` reads any mapping's "reason", by subscript or by `.get`, a holder's or not."""
    if isinstance(node, ast.Subscript):
        key = node.slice
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args:
        key = node.args[0]
    else:
        return False
    return isinstance(key, ast.Constant) and key.value == "reason"


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
    """`{name: place}` of each Kernel function's parameter `reason`, among its positional ones, or the count of them
    for one it takes by keyword alone, so that no place reaches it. A name two functions share with the parameter at
    other places is -1: no call to it can be read."""
    out = {}
    for tree in trees.values():
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            names = [a.arg for a in fn.args.posonlyargs + fn.args.args]
            if "reason" in names + [a.arg for a in fn.args.kwonlyargs]:
                at = names.index("reason") if "reason" in names else len(names) + 1000
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


def _flows(value, foreign: bool = True) -> bool:
    """Whether `value` hands on a reason read elsewhere, with `foreign` any mapping's "reason" too: as itself, as a
    branch of a choice or an `and` or `or`, or inside a display."""
    if _read_on(value) or (foreign and _keyed_any(value)):
        return True
    if isinstance(value, ast.IfExp):
        return _flows(value.body, foreign) or _flows(value.orelse, foreign)
    parts = value.values if isinstance(value, ast.BoolOp) else value.elts if isinstance(
        value, (ast.Tuple, ast.List, ast.Set)) else [value.value] if isinstance(value, ast.Starred) else [
        part for key, given in zip(value.keys, value.values) for part in (key, given) if part is not None
        and not (isinstance(key, ast.Constant) and key.value == "reason" and part is given)] if isinstance(
        value, ast.Dict) else []
    return any(_flows(part, foreign) for part in parts)


def _binds_reason(node) -> bool:
    """Whether `node` binds the name `reason` by no Name node: an import, a wildcard one among them, an exception
    handler, or a definition."""
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return any((a.asname or a.name.split(".")[0]) in ("reason", "*") for a in node.names)
    return isinstance(node, (ast.ExceptHandler, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
        and node.name == "reason"


def _bound(target, value, found: list, unread: list, read: set) -> None:
    """A binding of `target` to `value`, pair by pair for tuples: a reason given to a reason's slot, and a reason read
    elsewhere bound to any other name, which cannot be read. Each reason's slot bound here goes into `read`."""
    if isinstance(target, (ast.Tuple, ast.List)):
        starred = any(isinstance(e, ast.Starred) for e in target.elts + getattr(value, "elts", []))
        if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts) and not starred:
            for part, given in zip(target.elts, value.elts):
                _bound(part, given, found, unread, read)
        elif any(_reason_slot(n) for n in ast.walk(target)) or _flows(value):
            unread.append(target.lineno)
            read |= {id(n) for n in ast.walk(target)}
    elif _reason_slot(target):
        _give(value, found, unread)
        read.add(id(target))
    elif _flows(value):
        unread.append(target.lineno)


def written(tree, taken: dict) -> tuple:
    """`(found, unread, calls)` of one module: each literal reason with its line, the lines of reasons that cannot be
    read, and how many calls pass a reason on.

    A reason is written as a "reason" in a dict display, as the argument `reason`, by name or by place, to a function
    that takes one, or as its default, as a value bound or stored to the name `reason` or to a mapping's "reason", as a
    literal compared with a reason or a table of them, and as a member of a table. A call that gives no reason by
    place or name, a table bound anywhere but once at the top level, a handed table bound again, and the name `reason`
    bound any other way, by a loop, a comprehension, `:=`, an import, a handler or a definition, is put in `unread`.
    The scan assumes good faith, as the Kernel's other source checks do: it reads the forms the Kernel writes and
    refuses the ones named here, the record's among them (decision 0248's limit row). The runtime test is the binding
    hold.
    """
    found, unread, calls, bound = [], [], 0, set()
    tops = {id(t) for node in tree.body if isinstance(node, ast.Assign) for t in node.targets}
    handed = {id(n) for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) and fn.name == HANDED[0]
              for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == HANDED[1]}

    def table(side) -> bool:
        return _name(side) in TABLES or id(side) in handed

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load) and (
                (node.id in TABLES and id(node) not in tops) or id(node) in handed):
            unread.append(node.lineno)
        if isinstance(node, ast.arg) and (node.arg in TABLES or node.arg == "reason" and not any(
                node is a for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef)
                for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs)):
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
            # A reason handed on goes only to a parameter named `reason`: any other is followed nowhere. A foreign
            # mapping's "reason", such as a reviewing Result's in kernel/coverage.py, is no Decision's.
            slot = taken.get(_name(node.func))
            if _name(node.func) == "setdefault" and node.args and isinstance(node.args[0], ast.Constant) \
                    and node.args[0].value == "reason":
                slot = 1
            unread += [node.lineno for i, a in enumerate(node.args) if _flows(a, False) and i != slot]
            unread += [node.lineno for kw in node.keywords if kw.arg != "reason" and _flows(kw.value, False)]
            named = [kw for kw in node.keywords if kw.arg == "reason"]
            for kw in named:
                _give(kw.value, found, unread)
            if _name(node.func) == "setdefault" and node.args and isinstance(node.args[0], ast.Constant) \
                    and node.args[0].value == "reason":
                (_give(node.args[1], found, unread) if len(node.args) == 2 else unread.append(node.lineno))
            if _name(node.func) == HANDED[0]:
                handed_arg = [kw.value for kw in node.keywords if kw.arg == HANDED[1]] + node.args[HANDED_AT:HANDED_AT + 1]
                if any(isinstance(a, ast.Starred) for a in node.args[:HANDED_AT + 1]):
                    handed_arg = []
                for arg in handed_arg or [node]:
                    if isinstance(arg, (ast.Tuple, ast.List, ast.Set)):
                        _members(arg, found, unread)
                    elif _name(arg) not in TABLES:
                        unread.append(node.lineno)
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
                _bound(target, node.value, found, unread, bound)
                if id(target) in tops and _name(target) in TABLES:
                    _members(node.value, found, unread)
        if isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            if isinstance(node, ast.AugAssign) and _reason_slot(node.target):
                unread.append(node.lineno)
                bound.add(id(node.target))
            else:
                _bound(node.target, node.value, found, unread, bound)
        if isinstance(node, (ast.For, ast.comprehension)) and _flows(node.iter):
            unread.append(node.iter.lineno)
        if isinstance(node, ast.NamedExpr):
            _bound(node.target, node.value, found, unread, bound)
        if isinstance(node, ast.Subscript) and _flows(node.slice):
            unread.append(node.lineno)
        if isinstance(node, ast.ImportFrom) and any(a.name in taken and a.asname for a in node.names):
            unread.append(node.lineno)
        if isinstance(node, ast.Compare):
            sides = [node.left] + node.comparators
            unread += [node.lineno for side in sides if _keyed_any(side) and not _keyed(side)]
            if any(_flows(side, False) or table(side) for side in sides):
                for side in sides:
                    if isinstance(side, (ast.Tuple, ast.List, ast.Set)):
                        for member in side.elts:
                            _give(member, found, unread)
                    elif not table(side):
                        _give(side, found, unread)
    unread += [n.lineno for n in ast.walk(tree) if _reason_slot(n)
               and not isinstance(n.ctx, ast.Load) and id(n) not in bound]
    # The name bound by an import, a handler or a definition is read as it is bound any other way (issue 1179).
    unread += [n.lineno for n in ast.walk(tree) if _binds_reason(n)]
    return found, unread, calls


def read_of_sets(tree) -> list:
    """The lines where a module reads REASONS or ISSUE_REASONS: no Kernel rule may."""
    return [n.lineno for n in ast.walk(tree) if (_name(n) in SETS and isinstance(getattr(n, "ctx", None), ast.Load))
            or (isinstance(n, ast.ImportFrom) and any(a.name in SETS for a in n.names))]


def kernel_trees() -> dict:
    """Every module under kernel/, at any depth, by its path there."""
    return {path.relative_to(KERNEL).as_posix(): ast.parse(path.read_text(), path.name)
            for path in walk.files(ROOT, "kernel") if path.suffix == ".py"}


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
        # `reading` takes the handed table where the scan reads it, and each table is bound once in a module, somewhere.
        reading = [fn for fn in ast.walk(trees["derive.py"]) if isinstance(fn, ast.FunctionDef) and fn.name == HANDED[0]]
        self.assertEqual([[a.arg for a in fn.args.posonlyargs + fn.args.args].index(HANDED[1]) for fn in reading],
                         [HANDED_AT])
        self.assertEqual([fn.args.defaults for fn in reading], [[]])
        bound = [(name, t.id) for name, tree in trees.items() for node in tree.body if isinstance(node, ast.Assign)
                 for t in node.targets if isinstance(t, ast.Name) and t.id in TABLES]
        self.assertEqual(len(bound), len(set(bound)))
        self.assertEqual({table for _, table in bound}, set(TABLES))
        # No member is written nowhere: each is a literal where a reason is made, passed on or compared.
        self.assertEqual(sorted((terms.REASONS | terms.ISSUE_REASONS) - seen), [])

    def test_no_kernel_rule_reads_the_sets(self):
        for name, tree in sorted(kernel_trees().items()):
            with self.subTest(module=name):
                self.assertEqual(read_of_sets(tree), [], "kernel/%s reads REASONS or ISSUE_REASONS: they are data" % name)
        self.assertEqual(read_of_sets(ast.parse("if t.REASONS and c:\n    pass")), [1])
        self.assertEqual(read_of_sets(ast.parse("from kernel.terms import REASONS as CODES")), [1])

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
            ('facts["reason"] == "x"', [], [1]),
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
            ('_decision(f, s, **a)', [], [1]),
            ('for reason in ("x",):\n    pass', [], [1]),
            ('[_decision(f, s, reason, e, o) for reason in ("x",)]', [], [1]),
            ('(reason := "x")', ["x"], []),
            ('def _is_wait(why):\n    return why in ("a",)\n_is_wait(d["reason"])', [], [3]),
            ('state, why = d["state"], d["reason"]', [], [1]),
            ('why: str = reason if c else d["reason"]', [], [1]),
            ('(why := d["reason"])', [], [1]),
            ('ACTIONS.get(reason)', [], [1]),
            ('ACTIONS[d["reason"]]', [], [1]),
            ('from kernel.decide import _decision as make', [], [1]),
            ('f = lambda reason: reason', [], [1]),
            ('_decision(f, s, "x", e, o, extra={"why": reason})', ["x"], [1]),
            ('d = {"reason": reason, "why": d["reason"]}', [], [1]),
            ('d.setdefault("reason", bare["reason"])', [], []),
            ('for why in (d["reason"], bare["reason"]):\n    pass', [], [1]),
            ('"x" in (d["reason"], bare["reason"])', ["x"], []),
            ('_decision(f, s, reason, e, o)\nout(s, d["reason"], [])', [], []),
            ('d.setdefault("reason", "x")', ["x"], []),
            ('d.setdefault("reason")', [], [1]),
            ('def get(x):\n    return get(x) == 1', [], []),
            ('QUEUE_WAITS = ()\nQUEUE_WAITS = ("x",)', ["x"], []),
            ('out(s, other.bare["reason"], [])', [], [1]),
            ('reading(f, r, c, (d["reason"],))', [], [1, 1]),
            ('reading(*a, c, ("x",))', [], [1]),
            ('why = reason', [], [1]),
            ('why: str = d["reason"]', [], [1]),
            ('a, reason, b = (*p, "x", *())', [], [1]),
            ('for d["reason"] in ("x",):\n    pass', [], [1]),
            ('def f(*reason):\n    pass', [], [1]),
            ('def f(QUEUE_WAITS):\n    pass', [], [1]),
            ('relay(s, **kw)', [], [1]),
            ('why = d["reason"]', [], [1]),
            ('facts.get("reason") == "x"', [], [1]),
            ('reading(f, r, c, ("x",))', ["x"], []),
            ('reading(f, r, c, t.QUEUE_WAITS)', [], []),
            ('reading(f, r, c, ())', [], []),
            ('reading(f, r, c, past=make())', [], [1]),
            ('from kernel.terms import X as reason', [], [1]),
            ('from kernel.terms import reason', [], [1]),
            ('import reason', [], [1]),
            ('import kernel.reason', [], []),
            ('import kernel as reason', [], [1]),
            ('import os, reason', [], [1]),
            ('from kernel import terms, derive as reason', [], [1]),
            ('import reason.codes', [], [1]),
            ('from kernel.terms import reason as other', [], []),
            ('from kernel.terms import *', [], [1]),
            ('try:\n    pass\nexcept E as reason:\n    pass', [], [3]),
            ('def reason():\n    pass', [], [1]),
            ('async def reason():\n    pass', [], [1]),
            ('class reason:\n    pass', [], [1]),
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
    # One test, so that CI's legs, which deal tests one by one, record the suites and the seeds once.
    def test_every_decision_and_every_member_keeps_to_its_set(self):
        seen = given()
        # Every Decision has its reason in its kind's set, told by its schema.
        self.assertEqual(sorted(set(seen) - {"decision/1", "issue-decision/1", "suites_passed"}), [])
        self.assertEqual(sorted(seen["decision/1"] - terms.REASONS), [])
        self.assertEqual(sorted(seen["issue-decision/1"] - terms.REASONS - terms.ISSUE_REASONS), [])
        # No dead member: each is given by a Decision of its kind. A suite that failed while it was recorded may have
        # stopped short of a Decision: say so first.
        self.assertTrue(seen["suites_passed"], "%s failed while recorded; run them alone" % ", ".join(SUITES))
        self.assertEqual(sorted(terms.REASONS - seen["decision/1"]), [])
        self.assertEqual(sorted(terms.ISSUE_REASONS - seen["issue-decision/1"]), [])


if __name__ == "__main__":
    unittest.main()
