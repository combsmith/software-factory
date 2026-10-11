"""The Kernel does no I/O and keeps nothing between calls. Asserted from its syntax tree, not from trust.

It is strict by allowing little: a Kernel module holds a docstring, imports, constants and
functions, and nothing else. That is narrower than Python, on purpose.
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALLOWED_IMPORTS = {"__future__", "typing", "kernel"}
FORBIDDEN_NAMES = {"open", "print", "input", "exec", "eval", "__import__", "compile", "globals", "locals", "vars",
                   "getattr", "setattr", "delattr", "__builtins__", "breakpoint"}
# What a module may hold at its top level: a value that cannot change after import.
CONSTANT_CALLS = {"frozenset"}


def _constant(node) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Tuple):
        return all(_constant(e) for e in node.elts)
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in CONSTANT_CALLS


def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    files = sorted((root / "kernel").rglob("*.py"))
    if not files:
        return ["there is no kernel/ to check"]
    for path in files:
        name = path.relative_to(root / "kernel").as_posix()
        try:
            tree = ast.parse(path.read_text(errors="replace"), str(path))
        except (SyntaxError, ValueError) as err:
            problems.append("%s cannot be read as Python: %s" % (name, err))
            continue
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
            if isinstance(node, ast.Constant) and type(node.value) in (int, float) and node.value not in (0, 1):
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
            if value is None:
                problems.append("%s:%d runs when the module is imported; a module holds constants and functions"
                                % (name, node.lineno))
            elif not _constant(value):
                problems.append("%s:%d holds a value that can change; State is never stored" % (name, node.lineno))
    return problems
