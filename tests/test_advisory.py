"""The second transport, `adapters/azure.py`: what an advisory Lens's reader is asked through (decision 0224).

Nothing here reaches the network: a request is held by what it is refused as before anything could send it."""
from __future__ import annotations

import json
import pathlib
import unittest

from adapters import azure
from tools import jsonschema_lite

ROOT = pathlib.Path(__file__).resolve().parent.parent

ID = "resp_0123456789abcdef"
ASKED = {"model": "a-deployment", "input": "the prompt", "background": True, "store": True}


class Transport(unittest.TestCase):
    def test_the_azure_transport_asks_four_requests_and_no_other(self):
        # The four requests of the two APIs, and no other. A caller names an act, never a method or a path: the
        # transport alone writes those.
        self.assertEqual([azure.wire(r) for r in (azure.create(ASKED), azure.chat(ASKED), azure.read(ID), azure.cancel(ID))],
                         [("POST", "/openai/v1/responses", ASKED), ("POST", "/openai/v1/chat/completions", ASKED),
                          ("GET", "/openai/v1/responses/" + ID, None), ("POST", "/openai/v1/responses/%s/cancel" % ID, {})])
        self.assertEqual(azure.read(ID), {"act": "read", "id": ID, "body": None})
        refused = [("delete", ID, None), ("list", None, None), ("create", None, None), ("create", None, {}),
                   ("create", None, []), ("chat", None, "text"), ("create", ID, ASKED), ("chat", ID, ASKED),
                   ("read", ID, {}), ("read", ID, ASKED), ("cancel", ID, {}), ("read", None, None), ("cancel", None, None),
                   (None, None, ASKED), (["create"], None, ASKED), ("POST", None, ASKED)]
        for ident in ("", "..", "a/b", "a b", "a?b", "a#b", "a%2Fb", ID + "\n", ID + "/cancel", "a" * 201, 7, b"resp_1"):
            refused += [("read", ident, None), ("cancel", ident, None)]
        for act, ident, body in refused:
            with self.assertRaises(azure.Unanswered, msg=(act, ident, body)):
                azure.request(act, ident, body)
        self.assertEqual(azure.read("a" * 200)["id"], "a" * 200)

        class Any(str):         # text of another class, which says it equals whatever it is compared with
            __hash__ = str.__hash__

            def __eq__(self, other):
                return True

        class Text(str):        # and one that writes itself as another text
            def __str__(self):
                return "../files"
        with self.assertRaises(azure.Unanswered):
            azure.request(Any("delete"), None, ASKED)
        with self.assertRaises(azure.Unanswered):
            azure.read(Text(ID))
        # A request built by hand is held to the same rules before it is written as a method and a path.
        for req in ({"act": "read", "id": "../files", "body": None}, {"act": "upload", "id": None, "body": ASKED},
                    {"act": "create", "id": None, "body": ASKED, "path": "/openai/v1/files"},
                    {"act": "create", "id": None, "body": ASKED, "host": "example.com"},
                    {"method": "POST", "path": "/openai/v1/files", "body": ASKED, "accept": "x"}, None):
            with self.assertRaises(azure.Unanswered, msg=req):
                azure.wire(req)


def loaded(rel: str):
    return json.loads((ROOT / rel).read_text())


SCHEMAS = {name: loaded("schemas/%s.schema.json" % name) for name in ("advice", "advice-answer", "finding")}


def wrong(kind: str, name: str) -> list:
    """Where the counter-example of that name breaks its schema: each error's place, without its sentence."""
    found = jsonschema_lite.validate(loaded("examples/invalid/%s.%s.json" % (kind, name)), SCHEMAS[kind], schemas=SCHEMAS)
    return sorted({error.split(":")[0] for error in found})


class Schemas(unittest.TestCase):
    def test_a_readers_answer_is_one_object_of_findings_and_nothing_beside_them(self):
        # advice-answer/1 is what a reader is asked for. Each counter-example is wrong in one place, the one it names:
        # so the schema refuses it for that, and not for something else the file happens to hold.
        for name in ("advice-answer", "advice-answer.a-clean-read"):
            self.assertEqual(jsonschema_lite.validate(loaded("examples/%s.json" % name), SCHEMAS["advice-answer"]), [], name)
        for name, place in (("a-severity-the-design-does-not-know", "$.findings[0].severity"),
                            ("a-title-of-two-lines", "$.findings[0].title"),
                            ("a-field-the-reader-added", "$.findings[0]"), ("no-findings", "$")):
            self.assertEqual(wrong("advice-answer", name), [place], name)
        whole = loaded("examples/advice-answer.json")
        for field, value in (("file", ""), ("line", 0), ("criterion", "the third criterion"), ("line", 1.5), ("line", True), ("message", ""), ("title", ""), ("severity", None),
                             ("category", "style"), ("criterion", "PR-3\nPR-4"), ("line", 10 ** 9)):
            answer = json.loads(json.dumps(whole))
            answer["findings"][0][field] = value
            self.assertTrue(jsonschema_lite.validate(answer, SCHEMAS["advice-answer"]), (field, value))
        # No more findings than a check run's annotations are read for, and nothing beside the two fields.
        self.assertEqual(jsonschema_lite.validate(dict(whole, findings=whole["findings"][:1] * 100), SCHEMAS["advice-answer"]), [])
        self.assertTrue(jsonschema_lite.validate(dict(whole, findings=whole["findings"][:1] * 101), SCHEMAS["advice-answer"]))
        self.assertTrue(jsonschema_lite.validate(dict(whole, verdict="approve"), SCHEMAS["advice-answer"]))
        self.assertTrue(jsonschema_lite.validate(dict(whole, schema="advice-answer/2"), SCHEMAS["advice-answer"]))
        del whole["findings"][0]["message"]
        self.assertTrue(jsonschema_lite.validate(whole, SCHEMAS["advice-answer"]))

    def test_an_advisory_result_holds_codes_and_findings_that_are_advisory_annotations(self):
        # advice/1 is the file the advise step ends in. Its Findings are each a finding/1, and of one kind alone: an
        # advisory source, on an annotation whose key is the Finding's own id, uncategorised and with no criterion.
        for name in ("advice", "advice.rate-limited", "advice.over-the-days-ceiling"):
            result = loaded("examples/%s.json" % name)
            self.assertEqual(jsonschema_lite.validate(result, SCHEMAS["advice"], schemas=SCHEMAS), [], name)
            for finding in result["findings"]:
                self.assertEqual(jsonschema_lite.validate(finding, SCHEMAS["finding"]), [], name)
        self.assertEqual(len(loaded("examples/advice.json")["findings"]), 1)
        for name, place in (("sentence-as-reason", "$.reason"), ("a-categorised-finding", "$.findings[0].category"),
                            ("a-finding-on-a-thread", "$.findings[0].surface.type"),
                            ("a-finding-of-a-roles", "$.findings[0].source.kind"), ("an-id-made-of-text", "$.findings[0].id"),
                            ("a-finding-that-carries-its-text", "$.findings[0]")):
            self.assertEqual(wrong("advice", name), [place], name)
        # The reasons are the design's ten and no other, and a reader's words lie under `body` alone.
        self.assertEqual(SCHEMAS["advice"]["properties"]["reason"]["enum"],
                         [None, "too_large", "cut_short", "unparsed", "not_the_model", "rate_limited", "refused",
                          "timed_out", "no_key", "transport", "budget"])
        whole = loaded("examples/advice.json")
        for path, value in ((("texts", 0, "id"), "a title"), (("texts", 0, "body"), ""), (("texts", 0, "category"), "style"),
                            (("findings", 0, "surface", "key"), "PRRT_kw7"), (("findings", 0, "content_id"), "5d0c"),
                            (("findings", 0, "source", "actor"), "a person"), (("findings", 0, "severity"), "critical"),
                            (("findings", 0, "location", "start_line"), 0), (("findings", 0, "location", "path"), "a\nb"),
                            (("usage", "api"), "assistants"), (("usage", "cost_usd"), -1), (("usage", "effort"), "most"),
                            (("status",), "refused"), (("findings", 0, "criterion"), "PR-3"), (("usage", "asks"), 3),
                            (("findings", 0, "adopted_from"), {"lens": "kimi", "surface": whole["findings"][0]["surface"]}),
                            (("role",), "pr-review"), (("usage",), None), (("off_change",), -1), (("lens",), "Astra reader"), (("run",), "1"), (("release",), "next")):
            result = json.loads(json.dumps(whole))
            at = result
            for key in path[:-1]:
                at = at[key]
            at[path[-1]] = value
            self.assertTrue(jsonschema_lite.validate(result, SCHEMAS["advice"], schemas=SCHEMAS), (path, value))


if __name__ == "__main__":
    unittest.main()
