"""Every golden example validates; every counter-example is rejected."""
from __future__ import annotations

import json
import pathlib

from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Data files that are the real thing, not illustrations, and their schema.
LIVE = {"lifecycle/pull_request.json": "lifecycle", "config/authority.json": "authority",
        "config/defaults.json": "config", "config/rubric-pr-review.json": "rubric"}


def _once(pairs: list) -> dict:
    keys = [k for k, _ in pairs]
    twice = sorted({k for k in keys if keys.count(k) > 1})
    if twice:
        raise ValueError("a key is written twice: %s" % ", ".join(twice))
    return dict(pairs)


def _load(path: pathlib.Path):
    return json.loads(path.read_text(), object_pairs_hook=_once)


def _open(schema, path: str = "$") -> list:
    """Where an object schema leaves unknown fields unchecked."""
    out = []
    if isinstance(schema, dict):
        if (schema.get("type") == "object" or "properties" in schema) and \
                schema.get("additionalProperties", True) is True:
            out.append(path)
        for key, value in schema.items():
            out += _open(value, "%s.%s" % (path, key))
    return out


def run() -> list:
    problems = []
    schemas = {p.name[: -len(".schema.json")]: _load(p) for p in sorted((ROOT / "schemas").glob("*.schema.json"))}
    for kind, schema in sorted(schemas.items()):
        for where in _open(schema):
            problems.append("schema %s accepts unknown fields at %s" % (kind, where))
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
    for folder in ("config", "lifecycle"):
        for path in sorted((ROOT / folder).glob("*.json")):
            if "%s/%s" % (folder, path.name) not in LIVE:
                problems.append("%s/%s is validated against no schema; add it to LIVE" % (folder, path.name))
    covered = {p.name.split(".")[0] for p in (ROOT / "examples").glob("*.json")} | set(LIVE.values())
    for kind in sorted(set(schemas) - covered):
        problems.append("schema %s has no example" % kind)
    return problems
