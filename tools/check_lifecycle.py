"""Exhaustive checks on every declared Lifecycle. Each is small, so nothing is sampled."""
from __future__ import annotations

import json
import pathlib

from tools.jsonschema_lite import SchemaError, validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schemas" / "lifecycle.schema.json"


def load(name: str = "pull_request") -> dict:
    return json.loads((ROOT / "lifecycle" / (name + ".json")).read_text())


def _reach(start, edges) -> set:
    seen, todo = {start}, [start]
    while todo:
        here = todo.pop()
        for a, b in edges:
            if a == here and b not in seen:
                seen.add(b)
                todo.append(b)
    return seen


def _has_cycle(nodes, edges) -> bool:
    out = {n: [b for a, b in edges if a == n] for n in nodes}
    colour = dict.fromkeys(nodes, 0)

    def visit(n) -> bool:
        colour[n] = 1
        for m in out[n]:
            if colour[m] == 1 or (colour[m] == 0 and visit(m)):
                return True
        colour[n] = 2
        return False

    return any(colour[n] == 0 and visit(n) for n in nodes)


def _shape(lc, schema: dict) -> list:
    """Why `lc` cannot be checked at all: it does not match the Lifecycle schema."""
    try:
        return validate(lc, schema)
    except SchemaError as err:
        return ["the Lifecycle schema cannot be used: %s" % err]


def check(lc: dict, limits: dict = None, schema: dict = None) -> list:
    """The problems of one Lifecycle. A bound must be one of `limits`, when they are given."""
    wrong = _shape(lc, json.loads(SCHEMA.read_text()) if schema is None else schema)
    if wrong:
        return ["does not match the Lifecycle schema: %s" % w for w in wrong]
    states, terminal = set(lc["states"]), set(lc["terminal"])
    gated = set(lc["person_only_exits"])
    problems = []
    if "held" in states and "held" not in gated:
        problems.append("only a person ends a Hold: list held in person_only_exits")
    for s in sorted(gated - states):
        problems.append("person_only_exits names an undeclared state: %s" % s)
    edges = []
    for tr in lc["transitions"]:
        for end in (tr["from"], tr["to"]):
            if end not in states:
                problems.append("transition names an undeclared state: %s" % end)
        if tr["from"] in terminal:
            problems.append("a terminal state has a way out: %s" % tr["from"])
        if tr["from"] in gated and tr["by"] not in ("human", "platform"):
            problems.append("%s is left by %s; only a person takes a Work item out of %s"
                            % (tr["from"], tr["by"], tr["from"]))
        if limits is not None and tr["bound"] is not None and tr["bound"] not in limits:
            problems.append("the bound %s is not a limit in config/defaults.json; add its number there"
                            % tr["bound"])
        edges.append((tr["from"], tr["to"]))
    for entry in lc["initial"]:
        if entry not in states:
            problems.append("undeclared initial state: %s" % entry)
    reachable = set()
    for entry in lc["initial"]:
        reachable |= _reach(entry, edges)
    for s in sorted(states - reachable):
        problems.append("state can never be reached: %s" % s)
    for s in sorted(states - terminal):
        if not (_reach(s, edges) & terminal):
            problems.append("no terminal state can be reached from: %s" % s)
        if s not in lc["stale_after_minutes"]:
            problems.append("no staleness limit for: %s" % s)
    # Termination: the Factory alone, with no bound, must not be able to go round for ever.
    unbounded = [(tr["from"], tr["to"]) for tr in lc["transitions"]
                 if tr["by"] == "factory" and tr["bound"] is None]
    if _has_cycle(states, unbounded):
        problems.append("the Factory can cycle with no bound and no person involved")
    return list(dict.fromkeys(problems))     # a bound named on many transitions is one problem


def run(root: pathlib.Path = ROOT) -> list:
    """Every Lifecycle under `lifecycle/`, and one for each type of Work item the schema names."""
    problems = []

    def read(path: pathlib.Path):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError) as err:
            problems.append("%s cannot be read: %s" % (path.relative_to(root), err))
            return None

    schema = read(root / "schemas" / "lifecycle.schema.json")
    config = read(root / "config" / "defaults.json")
    try:
        items = schema["properties"]["work_item"]["enum"]
    except (KeyError, TypeError):
        problems.append("schemas/lifecycle.schema.json names no Work items under properties.work_item.enum")
        items = None
    limits = config.get("limits") if isinstance(config, dict) else None
    if config is not None and not isinstance(limits, dict):
        problems.append("config/defaults.json has no object of limits")
    if items is None or not isinstance(limits, dict):
        return problems
    for path in sorted((root / "lifecycle").glob("*.json")):
        lc = read(path)
        if lc is None:
            continue
        rel = "lifecycle/" + path.name
        wrong = _shape(lc, schema)
        if wrong:
            problems += ["%s does not match the Lifecycle schema: %s" % (rel, w) for w in wrong]
            continue
        if lc["work_item"] != path.stem:
            problems.append("%s declares the Work item %s; name the file %s.json"
                            % (rel, lc["work_item"], lc["work_item"]))
        problems += ["%s: %s" % (rel, p) for p in check(lc, limits, schema)]
    for item in items:
        if not (root / "lifecycle" / (item + ".json")).exists():
            problems.append("no Lifecycle for the Work item %s: declare it in lifecycle/%s.json" % (item, item))
    return problems


def declared(lifecycle: dict) -> set:
    return {(tr["from"], tr["to"]) for tr in lifecycle["transitions"]}
