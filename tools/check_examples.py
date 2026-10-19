"""Every golden example validates; every counter-example is rejected."""
from __future__ import annotations

import json
import pathlib

from kernel.coverage import covered
from tools.jsonschema_lite import ANNOTATIONS, FILE, SchemaError, _resolve, validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Data files that are the real thing, not illustrations, and their schema.
LIVE = {"lifecycle/pull_request.json": "lifecycle", "lifecycle/issue.json": "lifecycle",
        "config/authority.json": "authority",
        "config/defaults.json": "config", "config/rubric-pr-review.json": "rubric", "config/apps.json": "apps",
        "config/hooks.json": "hooks"}
# What a coverage example is judged against beyond its schema (decision 0029): the review's rubric, the Finding of
# examples/finding.json, and the paths examples/facts.json changes. No schema can say every criterion that applies is
# reported on; kernel/coverage.py does.
COVERAGE_AGAINST = ("config/rubric-pr-review.json", "examples/finding.json", "examples/facts.json")
# What one Run carries holds codes, never text: a string in these schemas is held by an enum, a const or a pattern
# anchored at both ends, unless it is a property named `body`. A body goes out to GitHub or in to the model as data, and
# nothing reads one back into a decision.
CODES_ONLY = ("task", "result", "effect", "disposition", "run-name")
TEXT_FIELD = "body"


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


def _anchored(pattern) -> bool:
    """Whether `pattern` holds the whole string: it opens with ^, closes with an unescaped $, and no alternative at
    its top level escapes those anchors. An escaped $ or a top-level | is a way of writing ^...$ that holds nothing."""
    if not isinstance(pattern, str) or not pattern.startswith("^") or not pattern.endswith("$"):
        return False
    depth, in_class, i = 0, False, 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            if i == len(pattern) - 2:
                return False        # the closing $ is escaped: a literal, not an anchor
            i += 2
            continue
        if in_class:
            in_class = c != "]"
        elif c == "[":
            in_class = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "|" and depth == 0:
            return False
        i += 1
    return True


def _free(schema, schemas: dict, root, kind: str, path: str, seen: set, active: tuple = ()) -> list:
    """What is wrong with `schema`, of the kind named, as the schema of what one Run carries: where it admits a string
    that no enum, const or anchored pattern holds, and a reference it makes that cannot be followed, has a keyword
    beside it, or comes round to itself. validate() reads a reference only where a value reaches it, so a branch no
    example takes is held here. `active` is the chain of references followed at this path."""
    if not isinstance(schema, dict):
        return []
    ref = schema.get("$ref")
    if isinstance(ref, str):
        beside = set(schema) - ANNOTATIONS - {"$ref"}
        if beside:
            return ["schema %s has %s beside a $ref at %s; a $ref stands alone" % (kind, sorted(beside), path)]
        try:
            target, target_root = _resolve(ref, root, schemas)
        except SchemaError as err:
            return ["schema %s cannot be followed at %s: %s" % (kind, path, err)]
        if id(target) in active:
            return ["schema %s comes round to itself at %s" % (kind, path)]
        named = FILE.match(ref)
        return _free(target, schemas, target_root, named.group(1) if named else kind, path, seen, active + (id(target),))
    if (kind, id(schema)) in seen:
        return []
    seen.add((kind, id(schema)))
    out = []
    kinds = schema.get("type")
    kinds = kinds if isinstance(kinds, list) else [kinds]
    strings = "string" in kinds or (kinds == [None] and not ("enum" in schema or "const" in schema))
    if strings and not ("enum" in schema or "const" in schema or _anchored(schema.get("pattern"))):
        out.append("schema %s admits text at %s; a string a Run carries is a code, unless it is named %s"
                   % (kind, path, TEXT_FIELD))
    for name, prop in schema.get("properties", {}).items():
        if name != TEXT_FIELD:
            out += _free(prop, schemas, root, kind, "%s.%s" % (path, name), seen)
    if isinstance(schema.get("items"), dict):
        out += _free(schema["items"], schemas, root, kind, path + "[]", seen)
    if isinstance(schema.get("additionalProperties"), dict):
        out += _free(schema["additionalProperties"], schemas, root, kind, path + ".*", seen)
    return out


def _uncovered(value, root: pathlib.Path) -> list:
    """What kernel/coverage.py says is wrong with `value`, a coverage example valid to its schema: nothing, or one
    problem naming what it left uncovered, or why it could not be judged."""
    missing = [rel for rel in COVERAGE_AGAINST if not (root / rel).exists()]
    if missing:
        return ["cannot be judged: %s is missing" % ", ".join(missing)]
    try:
        rubric, finding, facts = (_load(root / rel) for rel in COVERAGE_AGAINST)
    except ValueError as err:
        return ["cannot be judged: %s" % err]
    said, ids = covered(rubric, value, [finding], facts.get("changed_paths") if isinstance(facts, dict) else None)
    return [] if said == "covered" else ["$: %s %s" % (said, ", ".join(ids) or "against what it is judged by")]


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
    for kind in CODES_ONLY:
        if kind not in schemas:
            problems.append("schema %s is missing, and what one Run carries is held to codes" % kind)
            continue
        problems += _free(schemas[kind], schemas, schemas[kind], kind, "$", set())
    for path in sorted((root / "examples").glob("*.json")):
        kind = path.name.split(".")[0]
        if kind not in schemas:
            problems.append("%s: no schema named %s" % (path.name, kind))
            continue
        value = load(path)
        errors = validate(value, schemas[kind], schemas=schemas)
        if kind == "coverage" and not errors:
            errors = _uncovered(value, root)
        for err in errors:
            problems.append("%s: %s" % (path.name, err))
    for path in sorted((root / "examples" / "invalid").glob("*.json")):
        kind = path.name.split(".")[0]
        if kind not in schemas:
            problems.append("invalid/%s: no schema named %s" % (path.name, kind))
            continue
        value = load(path)
        errors = validate(value, schemas[kind], schemas=schemas)
        if kind == "coverage" and not errors:
            errors = _uncovered(value, root)
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
        for err in validate(load(root / rel), schemas[kind], schemas=schemas):
            problems.append("%s: %s" % (rel, err))
    for folder in ("config", "lifecycle"):
        for path in sorted((root / folder).glob("*.json")):
            if "%s/%s" % (folder, path.name) not in LIVE:
                problems.append("%s/%s is validated against no schema; add it to LIVE" % (folder, path.name))
    covered = {p.name.split(".")[0] for p in (root / "examples").glob("*.json")} | set(LIVE.values())
    for kind in sorted(set(schemas) - covered):
        problems.append("schema %s has no example" % kind)
    return problems
