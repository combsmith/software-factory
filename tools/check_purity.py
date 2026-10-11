"""The Kernel does no I/O and keeps nothing between calls. Asserted from its syntax tree, not from trust."""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALLOWED_IMPORTS = {"__future__", "typing", "kernel"}
FORBIDDEN_NAMES = {"open", "print", "input", "exec", "eval", "__import__", "compile", "globals"}
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
    for path in sorted((root / "kernel").glob("*.py")):
        tree = ast.parse(path.read_text(), str(path))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            for mod in mods:
                if mod.split(".")[0] not in ALLOWED_IMPORTS:
                    problems.append("%s:%d imports %s" % (path.name, node.lineno, mod))
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
                problems.append("%s:%d uses %s" % (path.name, node.lineno, node.id))
            if isinstance(node, ast.Constant) and type(node.value) in (int, float) and node.value not in (0, 1):
                problems.append("%s:%d writes the number %s; a limit is data, read from the configuration"
                                % (path.name, node.lineno, node.value))
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                problems.append("%s:%d keeps state between calls" % (path.name, node.lineno))
        # State is derived at every call and never stored: a module holds constants only.
        for node in tree.body:
            value = getattr(node, "value", None) if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
            if value is not None and not _constant(value):
                problems.append("%s:%d holds a value that can change; State is never stored"
                                % (path.name, node.lineno))
    return problems
