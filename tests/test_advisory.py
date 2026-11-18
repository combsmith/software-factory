"""The second transport, `adapters/azure.py`: what an advisory Lens's reader is asked through (decision 0224).

Nothing here reaches the network: a request is held by what it is refused as before anything could send it."""
from __future__ import annotations

import unittest

from adapters import azure

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


if __name__ == "__main__":
    unittest.main()
