"""The Kernel does no I/O. Asserted from its syntax tree, not from trust."""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALLOWED_IMPORTS = {"__future__", "typing", "kernel"}
FORBIDDEN_NAMES = {"open", "print", "input", "exec", "eval", "__import__", "compile", "globals"}


def run() -> list:
    problems = []
    for path in sorted((ROOT / "kernel").glob("*.py")):
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
    return problems
