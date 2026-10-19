"""Exhaustive checks on every declared Lifecycle. Each is small, so nothing is sampled."""
from __future__ import annotations

import json
import pathlib

from tools.jsonschema_lite import SchemaError, validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schemas" / "lifecycle.schema.json"
# The limits the Kernel counts for one Work item, and so the only ones that can bound its cycles.
# A limit on size or on the whole org is not among them. A new counter in the Kernel is added here.
PER_ITEM = ("max_runs_per_item", "max_attempts", "max_rounds", "max_acts_per_item", "max_unmerged_closes")
# The bound that is no counter: only a person ends what the transition starts. A Hold a label holds stands until a
# person removes it, whoever placed it, so a transition into `held` that no person makes may name it, and so may a
# stranger's change, below; nothing else.
PERSON = "person"
# Someone with no write access: an outsider who edits the issue they opened. Only a person admits it again, so a
# change a stranger makes is bound by a person, and it may leave a State only a person leaves, since the issue then
# waits on a person (decision 0037).
STRANGER = "stranger"


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


def _a_cycle(nodes: list, edges) -> list:
    """One cycle among `edges`, as the States it passes through and back to the first; [] if none."""
    out = {n: [b for a, b in edges if a == n] for n in nodes}
    colour = dict.fromkeys(nodes, 0)
    path = []

    def visit(n) -> list:
        colour[n] = 1
        path.append(n)
        for m in out[n]:
            if colour[m] == 1:
                return path[path.index(m):] + [m]
            found = visit(m) if colour[m] == 0 else []
            if found:
                return found
        colour[n] = 2
        path.pop()
        return []

    for n in nodes:
        found = visit(n) if colour[n] == 0 else []
        if found:
            return found
    return []


def _shape(lc, schema: dict) -> list:
    """Why `lc` cannot be checked at all: it does not match the Lifecycle schema."""
    try:
        return validate(lc, schema)
    except SchemaError as err:
        return ["the Lifecycle schema cannot be used: %s" % err]


def check(lc: dict, limits: dict = None, schema: dict = None) -> list:
    """The problems of one Lifecycle. A bound is counted for each item, and is one of `limits` when they are given."""
    wrong = _shape(lc, json.loads(SCHEMA.read_text()) if schema is None else schema)
    if wrong:
        return ["does not match the Lifecycle schema: %s" % w for w in wrong]
    states, terminal = set(lc["states"]), set(lc["terminal"])
    gated = set(lc["person_only_exits"])
    problems = []
    for s in sorted(gated - states):
        problems.append("person_only_exits names an undeclared state: %s" % s)
    edges = []
    for tr in lc["transitions"]:
        for end in (tr["from"], tr["to"]):
            if end not in states:
                problems.append("transition names an undeclared state: %s" % end)
        if tr["from"] in terminal:
            problems.append("a terminal state has a way out: %s" % tr["from"])
        if tr["from"] == "held" and tr["by"] == "factory":     # L-02
            problems.append("the Factory makes no transition out of a Hold: held -> %s is by factory" % tr["to"])
        if tr["from"] in gated and tr["by"] not in ("human", STRANGER):
            problems.append("%s is left by %s; only a person takes a Work item out of %s, or a stranger's change that"
                            " leaves it to a person" % (tr["from"], tr["by"], tr["from"]))
        if tr["by"] == STRANGER and tr["bound"] != PERSON:
            problems.append("%s -> %s by stranger names the bound %s; what a stranger starts only a person ends, so"
                            " its bound is person" % (tr["from"], tr["to"], tr["bound"]))
        if tr["bound"] == PERSON:
            if (tr["to"] != "held" or tr["by"] == "human") and tr["by"] != STRANGER:
                problems.append("the bound person is only for a Hold that no person makes, or a stranger's change,"
                                " not %s -> %s by %s" % (tr["from"], tr["to"], tr["by"]))
        elif tr["bound"] is not None and tr["bound"] not in PER_ITEM:
            problems.append("the bound %s is not a limit the Kernel counts for each item; a bound is one of %s"
                            % (tr["bound"], ", ".join(PER_ITEM)))
        elif limits is not None and tr["bound"] is not None and tr["bound"] not in limits:
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
    # Termination (I-14, L-04): take away what a person does, and no cycle is left without a bound,
    # whoever makes its transitions: the Factory, a Lens or the platform.
    unbounded = [(tr["from"], tr["to"]) for tr in lc["transitions"]
                 if tr["by"] != "human" and tr["bound"] is None and {tr["from"], tr["to"]} <= states]
    cycle = _a_cycle([s for s in lc["states"] if s in states], unbounded)
    if cycle:
        problems.append("a cycle with no person in it has no bound: %s" % " -> ".join(cycle))
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
    """Every transition `lifecycle` declares, as (from, to, by)."""
    return {(tr["from"], tr["to"], tr["by"]) for tr in lifecycle["transitions"]}


def undeclared(lifecycle: dict, made) -> list:
    """Each transition in `made`, as (from, to, by), that `lifecycle` does not declare. Any Lifecycle."""
    return sorted(set(made) - declared(lifecycle))
