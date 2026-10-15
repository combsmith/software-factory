"""Every golden example validates; every counter-example is rejected."""
from __future__ import annotations

import json
import pathlib

from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Data files that are the real thing, not illustrations, and their schema.
LIVE = {"lifecycle/pull_request.json": "lifecycle", "lifecycle/issue.json": "lifecycle",
        "config/authority.json": "authority",
        "config/defaults.json": "config", "config/rubric-pr-review.json": "rubric"}


def _once(pairs: list) -> dict:
    seen, twice = set(), set()
    for key, _ in pairs:
        (twice if key in seen else seen).add(key)
    twice = sorted(twice)
    if twice:
        raise ValueError("a key is written twice: %s" % ", ".join(twice))
    return dict(pairs)


def _load(path: pathlib.Path):
    return json.loads(path.read_text(), object_pairs_hook=_once)


def _open(schema, path: str = "$") -> list:
    """Where an object schema leaves unknown fields unchecked."""
    out = []
    if isinstance(schema, dict):
        extra = schema.get("additionalProperties", True)
        kinds = schema.get("type")
        if ("object" in (kinds if isinstance(kinds, list) else [kinds]) or "properties" in schema) and \
                not (extra is False or (isinstance(extra, dict) and extra)):
            out.append(path)
        for key, value in schema.items():
            out += _open(value, "%s.%s" % (path, key))
    return out


def run(root: pathlib.Path = ROOT) -> list:
    problems = []

    def load(path: pathlib.Path):
        """The JSON in `path`, or None with the reason recorded: a check reports, it does not crash."""
        try:
            return _load(path)
        except ValueError as err:
            problems.append("%s cannot be read: %s" % (path.relative_to(root), err))
            return None

    schemas = {p.name[: -len(".schema.json")]: load(p) for p in sorted((root / "schemas").glob("*.schema.json"))}
    schemas = {kind: schema for kind, schema in schemas.items() if schema is not None}
    if not schemas:
        return problems + ["there are no schemas to check"]
    for kind, schema in sorted(schemas.items()):
        for where in _open(schema):
            problems.append("schema %s accepts unknown fields at %s" % (kind, where))
    for path in sorted((root / "examples").glob("*.json")):
        kind = path.name.split(".")[0]
        if kind not in schemas:
            problems.append("%s: no schema named %s" % (path.name, kind))
            continue
        for err in validate(load(path), schemas[kind]):
            problems.append("%s: %s" % (path.name, err))
    for path in sorted((root / "examples" / "invalid").glob("*.json")):
        kind = path.name.split(".")[0]
        if kind not in schemas:
            problems.append("invalid/%s: no schema named %s" % (path.name, kind))
            continue
        errors = validate(load(path), schemas[kind])
        if not errors:
            problems.append("invalid/%s: was accepted, and must be rejected" % path.name)
        elif len(errors) > 1:
            problems.append("invalid/%s: is wrong in %d ways; a counter-example is wrong in one, named in its file name"
                            % (path.name, len(errors)))
    for rel, kind in sorted(LIVE.items()):
        if not (root / rel).exists():
            problems.append("%s is missing" % rel)
            continue
        if kind not in schemas:
            problems.append("%s: no schema named %s" % (rel, kind))
            continue
        for err in validate(load(root / rel), schemas[kind]):
            problems.append("%s: %s" % (rel, err))
    for folder in ("config", "lifecycle"):
        for path in sorted((root / folder).glob("*.json")):
            if "%s/%s" % (folder, path.name) not in LIVE:
                problems.append("%s/%s is validated against no schema; add it to LIVE" % (folder, path.name))
    covered = {p.name.split(".")[0] for p in (root / "examples").glob("*.json")} | set(LIVE.values())
    for kind in sorted(set(schemas) - covered):
        problems.append("schema %s has no example" % kind)
    return problems
