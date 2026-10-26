"""The Release's rules beyond a schema (#197's rulings 4 and 6). Run by `make verify`.

The ring file, `release/rings.json`, validates as `rings/1` in `tools/check_examples.py`; what no schema can say is
held here: no repo and Intent family is served by two Channels (decision 0010, on the Factory's side), and both
Channels name one major. The rules that cut and move, `release/cut.py`, and that name a commit's Release,
`release/current.py`, are pure: they import nothing but each other, and name nothing that reads, writes or runs.
"""
from __future__ import annotations

import ast
import json
import pathlib

from tools.check_purity import FORBIDDEN_NAMES

ROOT = pathlib.Path(__file__).resolve().parent.parent
RINGS = "release/rings.json"
PURE = ("release/cut.py", "release/current.py")
ALLOWED_IMPORTS = {"__future__", "release"}


def ring_problems(value) -> list:
    """What is wrong with a ring file that its schema let through: nothing, or each sentence."""
    problems, served = [], {}
    for line in value.get("serves", []):
        key = (line.get("repo"), line.get("family"))
        if key in served and served[key] != line.get("channel"):
            problems.append("serves: %s, family %s, is served by two Channels, %s and %s"
                            % (key[0], key[1], served[key], line.get("channel")))
        served.setdefault(key, line.get("channel"))
    majors = {tag.split("/v", 1)[1].split("-")[0] for tag in
              (c.get("tag", "") for c in value.get("channels", {}).values()) if "/v" in tag}
    if len(majors) > 1:
        problems.append("channels: name majors %s; both Channels are of one major" % ", ".join(sorted(majors)))
    return problems


def _impure(path: pathlib.Path, rel: str) -> list:
    tree = ast.parse(path.read_text(), filename=rel)
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or "."] if node.level == 0 else ["."]
        else:
            mods = []
        for mod in mods:
            if mod.split(".")[0] not in ALLOWED_IMPORTS:
                problems.append("%s:%d imports %s; the Release's rules import nothing but each other"
                                % (rel, node.lineno, mod))
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            problems.append("%s:%d names %s; the Release's rules read, write and run nothing" % (rel, node.lineno, node.id))
    return problems


def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    rings = root / RINGS
    if not rings.is_file():
        return ["%s is missing; both Channels and the ring file exist from the first commit" % RINGS]
    try:
        value = json.loads(rings.read_text())
    except ValueError as err:
        return ["%s is not JSON: %s" % (RINGS, err)]
    if isinstance(value, dict):
        problems += ["%s: %s" % (RINGS, p) for p in ring_problems(value)]
    for rel in PURE:
        path = root / rel
        problems += _impure(path, rel) if path.is_file() else ["%s is missing" % rel]
    return problems


if __name__ == "__main__":
    import sys
    found = run()
    for p in found:
        print(p)
    sys.exit(1 if found else 0)
