"""Every golden example validates; every counter-example is rejected."""
from __future__ import annotations

import json
import pathlib
import re

from kernel import decide, issue
from kernel.coverage import covered
from tools import walk
from tools.jsonschema_lite import ANNOTATIONS, FILE, SchemaError, _resolve, validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Data files that are the real thing, not illustrations, and their schema.
LIVE = {"lifecycle/pull_request.json": "lifecycle", "lifecycle/issue.json": "lifecycle",
        "config/authority.json": "authority",
        "config/defaults.json": "config", "config/rubric-pr-review.json": "rubric", "config/apps.json": "apps",
        "config/hooks.json": "hooks", "config/feed.json": "feed", "config/controller.json": "controller", "config/harness.json": "harness",
        "config/rulesets.json": "rulesets",
        "evals/pr-review/cases.json": "eval-set", "evals/context/task.json": "context-eval"}
# What a coverage example is judged against beyond its schema (decision 0029): the review's rubric, the Finding of
# examples/finding.json, and the paths examples/facts.json changes. No schema can say every criterion that applies is
# reported on; kernel/coverage.py does.
COVERAGE_AGAINST = ("config/rubric-pr-review.json", "examples/finding.json", "examples/facts.json")
# One envelope, on what crosses a boundary whole (decision 0039). Each schema is in one class: a document crosses a
# boundary whole and carries `schema`, its identity and `release`; a record travels inside a document and is also given
# alone to a reader, so it carries `schema` and nothing else of the envelope; a part is only ever inside another, by
# reference, and carries nothing; a data file a person edits carries `schema`, its path being its identity and the commit
# its Release. A document's class names its identity.
ENVELOPE = {"task": ("document", "run"), "result": ("document", "run"), "applied": ("document", "run"),
            "outcome": ("document", "run"), "pass": ("document", "pass"), "view-meta": ("document", "pass"),
            "view-items": ("document", "pass"), "health": ("document", "pass"),
            "eval-report": ("document", "commit"),
            "facts": "record", "issue-facts": "record", "decision": "record", "issue-decision": "record", "finding": "record",
            "effect": "part", "disposition": "part", "coverage": "part", "run-name": "part", "run-record": "part",
            "view-item": "part",
            "config": "data", "hooks": "data", "lifecycle": "data", "authority": "data", "apps": "data", "rubric": "data",
            "acceptance": "data", "trial": "data", "role": "data", "feed": "data", "eval-case": "data",
            "eval-set": "data", "context-eval": "data", "controller": "data", "harness": "data", "rulesets": "data"}
RELEASE = "^factory/v(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$"
# What one Run carries, and what is written from it, holds codes, never text: a string in these schemas is held by an
# enum, a const or a pattern anchored at both ends, unless it is a property named `body`, or sits under one named
# `untrusted`. A body goes out to GitHub or in to the model as data, and nothing reads one back into a decision; what is
# untrusted is marked for whatever reads the feed, and only view-item has it. A reference into a kind outside this set
# is held by that kind's own rules, so the existing records are not swept.
CODES_ONLY = ("task", "result", "effect", "disposition", "run-name", "coverage", "run-record",
              "pass", "applied", "outcome", "view-meta", "view-items", "view-item", "health", "role", "feed",
              "eval-set", "eval-report")
TEXT_FIELD = "body"
UNTRUSTED_FIELD = "untrusted"
UNTRUSTED_KIND = "view-item"
# The reasons the Kernel gives `needs_you` beside its own sets: a Hold deferred under a Pause, or one it cannot read
# (tests/test_decide.py::test_an_approver_who_is_the_author_or_last_pusher_takes_it_out_of_the_queue,
# tests/test_issue.py::test_placing_a_hold_is_stopped_only_by_the_pause_and_not_once_the_hold_is_there,
# tests/test_tools.py::test_every_reason_that_needs_a_person_says_what_is_asked), and an issue's unmerged closes past
# their bound (tests/test_issue.py::test_unmerged_closes_past_the_bound_place_a_hold).
ALSO_NEEDS_YOU = frozenset({"paused", "pause_unreadable", "unmerged_closes"})
# What a held-out case, or a piece of one, looks like: its schema's name, a diff's header, or a diff field.
CASE_MARKS = re.compile(r'eval-case/1|^(---|\+\+\+) [ab]/|^@@ |"diff"', re.M)


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


def _envelope(kind: str, schema) -> list:
    """What is wrong with `schema`'s envelope for its class in ENVELOPE: nothing, or each sentence."""
    out = []
    if kind not in ENVELOPE:
        return ["schema %s is in no class of ENVELOPE; name it a document, a record, a part or a data file" % kind]
    cls = ENVELOPE[kind]
    cls, identity = cls if isinstance(cls, tuple) else (cls, None)
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    required = schema.get("required", []) if isinstance(schema, dict) else []
    if cls == "part":
        if "schema" in props:
            out.append("schema %s is a part, and carries a schema field; only what crosses a boundary whole does" % kind)
        if "release" in props:
            out.append("schema %s is a part, and carries a release; its Release is the document's it is inside" % kind)
        return out
    const = props.get("schema", {}).get("const") if isinstance(props.get("schema"), dict) else None
    if not (isinstance(const, str) and re.fullmatch(r"%s/[1-9][0-9]*" % re.escape(kind), const)):
        out.append("schema %s: its schema field is not a const naming %s and a major version" % (kind, kind))
    if "schema" not in required:
        out.append("schema %s does not require its schema field" % kind)
    if cls == "document":
        for name in (identity, "release"):
            if name not in required:
                out.append("schema %s is a document and does not require %s" % (kind, name))
        if not (isinstance(props.get("release"), dict) and props["release"].get("pattern") == RELEASE
                and props["release"].get("type") == "string"):
            out.append("schema %s: a document's release is a string in the Factory's release pattern" % kind)
        if not (isinstance(props.get(identity), dict) and _anchored(props[identity].get("pattern"))
                and props[identity].get("type") == "string"):
            out.append("schema %s: a document's identity, %s, is a string with a pattern anchored at both ends"
                       % (kind, identity))
    elif "release" in props:
        out.append("schema %s is a %s and carries a release; its Release is its document's, or the commit" % (kind, cls))
    return out


def _string_only(node) -> bool:
    """Whether `node` admits a string, null or nothing else: the shape of a body."""
    if not isinstance(node, dict):
        return False
    kinds = node.get("type")
    kinds = kinds if isinstance(kinds, list) else [kinds]
    return "string" in kinds and not (set(kinds) - {"string", "null"})


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
        if named and named.group(1) not in CODES_ONLY:
            return []       # a record, held by its own rules and counter-examples; the existing records are not swept
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
        # A body is one string, and what is untrusted is marked only on the feed: neither exempts an object of strings
        # under its name in a Task.
        if name == TEXT_FIELD and _string_only(prop):
            continue
        if name == UNTRUSTED_FIELD and kind == UNTRUSTED_KIND:
            continue
        out += _free(prop, schemas, root, kind, "%s.%s" % (path, name), seen)
    if isinstance(schema.get("items"), dict):
        out += _free(schema["items"], schemas, root, kind, path + "[]", seen)
    if isinstance(schema.get("additionalProperties"), dict):
        out += _free(schema["additionalProperties"], schemas, root, kind, path + ".*", seen)
    return out


def _table(feed, decision_schema) -> list:
    """What is wrong with the feed's table, valid to its schema: a reason the Kernel gives needs_you with no row, a row
    for one it never does, a reason with two rows, and an attention class with no rule or with two."""
    needs = set(decide.NEEDS_YOU_REASONS) | set(issue.NEEDS_YOU_REASONS) | ALSO_NEEDS_YOU
    out = []
    reasons = [row["reason"] for row in feed["decision_required"]]
    for reason in sorted(needs - set(reasons)):
        out.append("feed: the reason %s needs a person, and no row says what is asked" % reason)
    for reason in sorted(set(reasons) - needs):
        out.append("feed: a row for %s, a reason the Kernel never gives needs_you" % reason)
    for reason in sorted({r for r in reasons if reasons.count(r) > 1}):
        out.append("feed: the reason %s has two rows" % reason)
    classes = decision_schema["properties"]["attention"]["enum"]
    ruled = [row["attention"] for row in feed["next_actor"]["by_attention"]]
    for name in classes:
        if ruled.count(name) != 1:
            out.append("feed: the attention class %s has %s" % (name, "no rule" if name not in ruled else "two rules"))
    # The rules read first-wins in order, so a key ruled twice would hide its second rule.
    states = [row["state"] for row in feed["next_actor"]["by_state"]["rows"]]
    for name in sorted({name for name in states if states.count(name) > 1}):
        out.append("feed: the State %s has two rules" % name)
    outcomes = [name for row in feed["next_actor"]["by_outcome"] for name in row["outcome"]]
    for name in sorted({name for name in outcomes if outcomes.count(name) > 1}):
        out.append("feed: the outcome %s has two rules" % name)
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
    for kind, schema in sorted(schemas.items()):
        problems += _envelope(kind, schema)
    for kind in sorted(set(ENVELOPE) - set(schemas)):
        problems.append("ENVELOPE names %s, and there is no such schema" % kind)
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
        if kind == "trial" and not errors:
            # A fixture's rules beyond its schema are tools/check_trials.py's: a counter-example of one is refused there.
            from tools import check_trials
            errors = check_trials.fixture_problems(value, root)
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
        value = load(root / rel)
        errors = validate(value, schemas[kind], schemas=schemas)
        if kind == "feed" and not errors and "decision" in schemas:
            errors = _table(value, schemas["decision"])
        for err in errors:
            problems.append("%s: %s" % (rel, err))
    for folder in ("config", "lifecycle", "evals"):
        for path in (walk.files(root, folder) if (root / folder).is_dir() else []):
            rel = path.relative_to(root).as_posix()
            if path.suffix == ".json" and rel not in LIVE:
                problems.append("%s is validated against no schema; add it to LIVE" % rel)
            # A held-out case lives in the private home and never here: evals/ holds manifests in LIVE and its rules,
            # nothing else, and every file there is read for what looks like a case, since a mark can hide in any.
            if folder == "evals" and not (rel in LIVE or path.name == "AGENTS.md"):
                problems.append("%s is neither a manifest in LIVE nor the directory's rules; nothing else lives under "
                                "evals/" % rel)
            if folder == "evals" and CASE_MARKS.search(path.read_text(errors="replace")):
                problems.append("%s holds what looks like a held-out case; only a case's hash and id may be here" % rel)
    covered = {p.name.split(".")[0] for p in (root / "examples").glob("*.json")} | set(LIVE.values())
    for kind in sorted(set(schemas) - covered):
        problems.append("schema %s has no example" % kind)
    return problems
