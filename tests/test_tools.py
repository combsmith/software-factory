"""The checks themselves must catch what they claim to catch."""
from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

from tools import (check_authority, check_context, check_examples, check_lifecycle, check_purity,
                   check_repo, check_workflows, verify)
from tools.jsonschema_lite import SchemaError, validate

ROOT = check_authority.ROOT


def tree(files: dict) -> pathlib.Path:
    """A throwaway repo holding `files`, for a check to be run against."""
    root = pathlib.Path(tempfile.mkdtemp())
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def caught(problems: list, words: str) -> bool:
    return any(words in p for p in problems)


class Validator(unittest.TestCase):
    def test_rejects_a_schema_it_cannot_enforce(self):
        with self.assertRaises(SchemaError):
            validate({}, {"type": "object", "patternProperties": {}})

    def test_a_boolean_is_not_an_integer(self):
        self.assertTrue(validate(True, {"type": "integer"}))

    def test_unexpected_property_is_an_error(self):
        schema = {"type": "object", "additionalProperties": False, "properties": {"a": {"type": "string"}}}
        self.assertEqual(validate({"a": "x", "b": 1}, schema), ["$: unexpected b"])

    def test_a_schema_that_accepts_unknown_fields_is_caught(self):
        self.assertEqual(check_examples._open({"type": "object", "properties": {"a": {"type": "object"}}}),
                         ["$", "$.properties.a"])
        self.assertEqual(check_examples._open({"type": "object", "additionalProperties": {"type": "string"}}), [])

    def test_a_key_written_twice_is_refused(self):
        path = tree({"x.json": '{"limit": 3, "limit": 30}'}) / "x.json"
        with self.assertRaises(ValueError):
            check_examples._load(path)


class Lifecycle(unittest.TestCase):
    def test_an_unbounded_factory_cycle_is_caught(self):
        lc = copy.deepcopy(check_lifecycle.load())
        for tr in lc["transitions"]:
            if (tr["from"], tr["to"]) in (("adjudicating", "addressing"), ("addressing", "adjudicating")):
                tr["bound"] = None
        self.assertIn("the Factory can cycle with no bound and no person involved", check_lifecycle.run(lc))

    def test_a_dead_end_is_caught(self):
        lc = copy.deepcopy(check_lifecycle.load())
        lc["transitions"] = [tr for tr in lc["transitions"] if tr["from"] != "queued"]
        self.assertIn("no terminal state can be reached from: queued", check_lifecycle.run(lc))

    def test_a_hold_the_factory_could_end_is_caught(self):
        lc = copy.deepcopy(check_lifecycle.load())
        lc["transitions"].append({"from": "held", "to": "verifying", "by": "factory", "bound": "max_attempts"})
        self.assertTrue(caught(check_lifecycle.run(lc), "only a person ends a Hold"))


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


class Purity(unittest.TestCase):
    def test_io_in_the_kernel_is_caught(self):
        root = tree({"kernel/x.py": "import os\n\ndef f():\n    return open('x')\n"})
        problems = check_purity.run(root)
        self.assertTrue(caught(problems, "imports os") and caught(problems, "uses open"))

    def test_a_limit_written_into_the_kernel_is_caught(self):
        root = tree({"kernel/x.py": "def f(runs):\n    return len(runs) >= 3 or runs[0] == 1\n"})
        self.assertEqual(len(check_purity.run(root)), 1)

    def test_state_kept_between_calls_is_caught(self):
        root = tree({"kernel/x.py": "SEEN = {}\nKIND = 'held'\nNAMES = frozenset({'a'})\n"})
        self.assertEqual(check_purity.run(root), ["x.py:1 holds a value that can change; State is never stored"])


class Repo(unittest.TestCase):
    def test_third_party_code_is_caught(self):
        root = tree({"a.py": "import requests\n", "requirements.txt": "requests\n"})
        problems = check_repo.run(root)
        self.assertTrue(caught(problems, "imports requests") and caught(problems, "dependency manifest"))

    def test_something_shaped_like_a_credential_is_caught(self):
        root = tree({"notes.md": "token: " + "ghp_" + "a1B2" * 9 + "\n"})
        self.assertTrue(caught(check_repo.run(root), "shaped like a credential"))

    def test_a_second_definition_is_caught(self):
        root = tree({"a.py": "class T:\n    def test_x(self):\n        pass\n\n    def test_x(self):\n        pass\n"})
        self.assertTrue(caught(check_repo.run(root), "defines test_x a second time"))

    def test_syntax_newer_than_the_oldest_python_is_caught(self):
        root = tree({"a.py": "match 1:\n    case 1:\n        pass\n"})
        self.assertTrue(caught(check_repo.run(root), "is not Python 3.9"))

    def test_a_draw_that_differs_between_python_versions_is_caught(self):
        root = tree({"sim/x.py": "import random\n\ndef f(rng):\n    return rng.choice([1, 2])\n"})
        self.assertTrue(caught(check_repo.run(root), "calls choice"))

    def test_reaching_into_the_proof_of_concept_is_caught(self):
        root = tree({"a.json": json.dumps({"repo": "petry-projects/" + check_repo.FOREIGN})})
        self.assertTrue(caught(check_repo.run(root), "proof-of-concept repo"))


class Workflows(unittest.TestCase):
    def test_the_example_passes_and_every_rule_has_been_tripped(self):
        self.assertEqual(check_workflows.run(), [])

    def test_a_rule_with_no_counter_example_is_caught(self):
        good = (ROOT / "examples" / "workflows" / "verify.yml").read_text()
        problems = check_workflows.run(tree({"examples/workflows/verify.yml": good}))
        self.assertEqual(len(problems), len(check_workflows.RULES))

    def test_an_example_in_the_standard_that_has_drifted_is_caught(self):
        good = (ROOT / "examples" / "workflows" / "verify.yml").read_text()
        root = tree({"examples/workflows/verify.yml": good,
                     "docs/standards/workflows.md": "```yaml\n" + good.replace("15", "90") + "```\n"})
        self.assertTrue(caught(check_workflows.run(root), "word for word"))

    def test_the_required_check_that_has_drifted_from_its_example_is_caught(self):
        good = (ROOT / "examples" / "workflows" / "verify.yml").read_text()
        root = tree({"examples/workflows/verify.yml": good, ".github/workflows/verify.yml": good.replace("15", "45")})
        self.assertTrue(caught(check_workflows.run(root), "change both together"))

    def test_a_live_workflow_is_held_to_the_rules(self):
        bad = (ROOT / "examples" / "workflows" / "invalid" / "pin.a-tag-can-move.yml").read_text()
        problems = check_workflows.run(tree({".github/workflows/x.yml": bad}))
        self.assertTrue(caught(problems, ".github/workflows/x.yml: [pin]"))


class Context(unittest.TestCase):
    def test_a_rule_with_no_check_is_caught(self):
        root = tree({"tools/check_x.py": ""})
        self.assertEqual(check_context._held("Reviewers look for it", "rule", root, root), ["rule: names no check"])
        self.assertEqual(check_context._held("`tools/check_x.py`", "rule", root, root), [])

    def test_a_rule_whose_wait_is_over_is_caught(self):
        root = tree({"harness/apply.py": ""})
        self.assertEqual(check_context._held("waiting on `roles/`", "rule", root, root), [])
        self.assertTrue(caught(check_context._held("waiting on `harness/`", "rule", root, root), "exists now"))

    def test_a_wait_on_a_name_nothing_will_ever_have_is_caught(self):
        root = tree({"x": ""})
        self.assertTrue(caught(check_context._held("waiting on `someday/`", "rule", root, root), "not a planned"))

    def test_a_path_or_a_test_that_does_not_exist_is_caught(self):
        root = tree({"docs/a.md": "See `tools/gone.py` and `tools/here.py::test_missing`.\n",
                     "tools/here.py": "def test_present():\n    pass\n"})
        problems = check_context._references(root / "docs" / "a.md", (root / "docs" / "a.md").read_text(), root)
        self.assertEqual(len(problems), 2)

    def test_only_the_design_record_is_exempt(self):
        root = tree({"docs/architecture/review.md": "See `scripts/gone.sh`.\n", "docs/notes/a.md": "See `tools/gone.py`.\n"})
        self.assertEqual([p.name for p in check_context._markdown(root)], ["a.md"])

    def test_a_number_without_its_title_is_caught(self):
        root = tree({"docs/a.md": "Fixed in #2225.\n\nSee pull request 2225.\n\n"
                                  "See \"docs: factory MVP\" (pull request 2225).\n"})
        problems = check_context._references(root / "docs" / "a.md", (root / "docs" / "a.md").read_text(), root)
        self.assertEqual(len(problems), 2)

    def test_a_root_file_too_long_to_read_in_full_is_caught(self):
        root = tree({"AGENTS.md": "line\n" * (check_context.ROOT_LINES + 1)})
        self.assertTrue(caught(check_context._agents_files(root), "the limit is"))

    def test_a_rule_in_any_agents_file_must_name_its_check(self):
        root = tree({"AGENTS.md": "| Rule | Held by |\n|---|---|\n| Be kind | `tools/x.py` |\n", "tools/x.py": "",
                     "tools/AGENTS.md": "| Rule | Held by |\n|---|---|\n| Be careful | reviewers |\n"})
        problems = [p for p in check_context._agents_files(root) if "names no check" in p]
        self.assertEqual(problems, ["tools/AGENTS.md, rule 'Be careful': names no check"])

    def test_a_date_in_what_is_always_read_is_caught(self):
        root = tree({"AGENTS.md": "Decided on 2026-10-11.\n", "CLAUDE.md": "See AGENTS.md, and also these rules.\n"})
        problems = check_context._agents_files(root)
        self.assertTrue(caught(problems, "holds a date") and caught(problems, "CLAUDE.md must hold the one line"))

    def test_a_directory_with_no_rules_of_its_own_is_caught(self):
        root = tree({"AGENTS.md": "x\n", "kernel/decide.py": ""})
        self.assertTrue(caught(check_context._agents_files(root), "kernel/ has no AGENTS.md"))

    def test_a_decision_with_no_boundary_is_caught(self):
        root = tree({"docs/decisions/0001-x.md": "# 0001. X\n\n## Decision\n\nY.\n\n## Why\n\nZ.\n"})
        self.assertTrue(caught(check_context._decisions(root), "names no boundary"))

    def test_a_lesson_with_no_check_is_caught(self):
        root = tree({"docs/lessons.md": "### L-01 A thing broke\n\n**Failure.** It broke.\n\n**Rule.** Do not.\n"})
        self.assertTrue(caught(check_context._lessons(root), "L-01 has no Check"))

    def test_a_standard_with_prose_and_no_example_is_caught(self):
        root = tree({"docs/standards/code.md": "# Code\n\n## Be careful\n\nPlease.\n\nHeld by: `docs/`\n"})
        self.assertTrue(caught(check_context._standards(root), "the example comes before the prose"))

    def test_a_second_copy_of_the_review_standard_is_caught(self):
        root = tree({"docs/standards/review.md": "# Review\n"})
        self.assertTrue(caught(check_context._standards(root), "the review standard is"))


class Verify(unittest.TestCase):
    def test_every_check_is_run_by_verify(self):
        on_disk = {p.stem for p in (ROOT / "tools").glob("check_*.py")}
        run = {check.__module__.split(".")[-1] for _, check in verify.CHECKS}
        self.assertEqual(on_disk, run)

    def test_every_check_has_a_test_in_which_it_fails(self):
        tests = pathlib.Path(__file__).read_text()
        for path in sorted((ROOT / "tools").glob("check_*.py")):
            self.assertIn("%s." % path.stem, tests, "%s is never made to fail" % path.name)
