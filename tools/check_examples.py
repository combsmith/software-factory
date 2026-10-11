"""Every golden example validates; every counter-example is rejected."""
from __future__ import annotations

import json
import pathlib

from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Data files that are the real thing, not illustrations, and their schema.
LIVE = {"lifecycle/pull_request.json": "lifecycle", "config/authority.json": "authority",
        "config/defaults.json": "config", "config/rubric-pr-review.json": "rubric"}


def _load(path: pathlib.Path):
    return json.loads(path.read_text())


def run() -> list:
    problems = []
    schemas = {p.name[: -len(".schema.json")]: _load(p) for p in sorted((ROOT / "schemas").glob("*.schema.json"))}
    for path in sorted((ROOT / "examples").glob("*.json")):
        kind = path.name.split(".")[0]
        if kind not in schemas:
            problems.append("%s: no schema named %s" % (path.name, kind))
            continue
        for err in validate(_load(path), schemas[kind]):
            problems.append("%s: %s" % (path.name, err))
    for path in sorted((ROOT / "examples" / "invalid").glob("*.json")):
        kind = path.name.split(".")[0]
        if not validate(_load(path), schemas[kind]):
            problems.append("invalid/%s: was accepted, and must be rejected" % path.name)
    for rel, kind in sorted(LIVE.items()):
        for err in validate(_load(ROOT / rel), schemas[kind]):
            problems.append("%s: %s" % (rel, err))
    covered = {p.name.split(".")[0] for p in (ROOT / "examples").glob("*.json")} | set(LIVE.values())
    for kind in sorted(set(schemas) - covered):
        problems.append("schema %s has no example" % kind)
    return problems
