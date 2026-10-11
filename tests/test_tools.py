"""The checks themselves must catch what they claim to catch."""
from __future__ import annotations

import copy
import unittest

from tools import check_authority, check_lifecycle
from tools.jsonschema_lite import SchemaError, validate


class Validator(unittest.TestCase):
    def test_rejects_a_schema_it_cannot_enforce(self):
        with self.assertRaises(SchemaError):
            validate({}, {"type": "object", "patternProperties": {}})

    def test_a_boolean_is_not_an_integer(self):
        self.assertTrue(validate(True, {"type": "integer"}))

    def test_unexpected_property_is_an_error(self):
        schema = {"type": "object", "additionalProperties": False, "properties": {"a": {"type": "string"}}}
        self.assertEqual(validate({"a": "x", "b": 1}, schema), ["$: unexpected b"])


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


class Authority(unittest.TestCase):
    def test_security_may_never_be_declined(self):
        import json
        a = json.loads((check_authority.ROOT / "config" / "authority.json").read_text())
        a["categories"]["security"]["may_accept"].append("declined")
        self.assertTrue(any("security" in p for p in check_authority.run(a)))

    def test_the_author_may_not_own_a_category(self):
        import json
        a = json.loads((check_authority.ROOT / "config" / "authority.json").read_text())
        a["categories"]["functional"]["owner"] = "dev-lead"
        self.assertTrue(any("author Role" in p for p in check_authority.run(a)))
