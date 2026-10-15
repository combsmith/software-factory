"""The Kernel does no I/O and keeps nothing between calls. Asserted from its syntax tree, not from trust.

It is strict by allowing little: a Kernel module holds a docstring, imports, constants and
functions, and nothing else. That is narrower than Python, on purpose.
"""
from __future__ import annotations

import ast
import pathlib

from tools import walk

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALLOWED_IMPORTS = {"__future__", "typing", "kernel"}
FORBIDDEN_NAMES = {"open", "print", "input", "exec", "eval", "__import__", "compile", "globals", "locals", "vars",
                   "getattr", "setattr", "delattr", "__builtins__", "breakpoint"}
# What a module may hold at its top level: a value that cannot change after import.
CONSTANT_CALLS = {"frozenset"}
# The calendar, which nobody chooses, and so the only numbers but 0 and 1 the Kernel may write: each a constant of
# kernel/terms.py, under this name, with exactly this value. Any other number is a limit, and a limit is data.
CALENDAR = {"SECONDS_PER_MINUTE": 60, "MINUTES_PER_HOUR": 60, "HOURS_PER_DAY": 24, "DAYS_PER_YEAR": 365,
            "LEAP_YEARS": (4, 100, 400), "FEBRUARY": 2,
            "DAYS_BEFORE_MONTH": (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)}


def _constant(node) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Tuple):
        return all(_constant(e) for e in node.elts)
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in CONSTANT_CALLS


def _pinned(name: str, node) -> bool:
    """Whether `node` is the one form a calendar unit is written in: at the top of terms.py, alone, at its value."""
    if not (name == "terms.py" and isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name) and node.targets[0].id in CALENDAR):
        return False
    try:
        value = ast.literal_eval(node.value)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False
    return repr(value) == repr(CALENDAR[node.targets[0].id])


def _calendar(name: str, tree) -> tuple:
    """(the numbers in `tree` that are the calendar's, as ids of their nodes; the problems with how it is written).

    Each unit is assigned once, in its pinned form. Any other assignment to its name, a second one to 0, 1 or True
    among them, or to an attribute of that name anywhere in the Kernel, is a problem: it would change the unit.
    """
    out, problems, seen = set(), [], set()
    pinned = {id(node) for node in tree.body if _pinned(name, node)}
    for node in ast.walk(tree):
        if id(node) in pinned and node.targets[0].id not in seen:
            seen.add(node.targets[0].id)
            out |= {id(n) for n in ast.walk(node.value)}
            continue
        targets = node.targets if isinstance(node, ast.Assign) else \
            [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr, ast.For)) else []
        for target in targets:
            for part in ast.walk(target):
                unit = part.id if isinstance(part, ast.Name) else part.attr if isinstance(part, ast.Attribute) else None
                if unit in CALENDAR and isinstance(part.ctx, ast.Store):
                    problems.append("%s:%d assigns %s, a unit of the calendar: it is written once, in terms.py, as "
                                    "tools/check_purity.py pins it" % (name, node.lineno, unit))
    return out, problems


def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    files = [p for p in walk.files(root, "kernel") if p.suffix == ".py"]
    if not files:
        return ["there is no kernel/ to check"]
    for path in files:
        name = path.relative_to(root / "kernel").as_posix()
        try:
            tree = ast.parse(path.read_text(errors="replace"), str(path))
        except (SyntaxError, ValueError) as err:
            problems.append("%s cannot be read as Python: %s" % (name, err))
            continue
        calendar, wrong = _calendar(name, tree)
        problems += wrong
        for node in ast.walk(tree):
            line = getattr(node, "lineno", 0)
            mods = []
            if isinstance(node, ast.Import):
                mods = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                mods = [node.module or ""]
            for mod in mods:
                if mod.split(".")[0] not in ALLOWED_IMPORTS:
                    problems.append("%s:%d imports %s" % (name, line, mod))
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
                problems.append("%s:%d uses %s" % (name, line, node.id))
            if (isinstance(node, ast.Constant) and type(node.value) in (int, float) and node.value not in (0, 1)
                    and id(node) not in calendar):
                problems.append("%s:%d writes the number %s; a limit is data, read from the configuration"
                                % (name, line, node.value))
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                problems.append("%s:%d keeps state between calls" % (name, line))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                defaults = node.args.defaults + [d for d in node.args.kw_defaults if d is not None]
                if not all(_constant(d) for d in defaults):
                    problems.append("%s:%d has a default that can change, which is state kept between calls"
                                    % (name, line))
            if isinstance(node, ast.ClassDef):
                problems.append("%s:%d defines a class; the Kernel is functions and constants" % (name, line))
        # State is derived at every call and never stored: a module holds constants only.
        for i, node in enumerate(tree.body):
            docstring = i == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            if docstring or isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)):
                continue
            value = getattr(node, "value", None) if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
            if isinstance(node, ast.AsyncFunctionDef):
                problems.append("%s:%d defines an async function; the Kernel waits on nothing" % (name, node.lineno))
            elif value is None:
                problems.append("%s:%d runs when the module is imported; a module holds constants and functions"
                                % (name, node.lineno))
            elif not _constant(value):
                problems.append("%s:%d holds a value that can change; State is never stored" % (name, node.lineno))
    return problems
