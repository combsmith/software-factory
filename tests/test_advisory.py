"""The second transport, `adapters/azure.py`: what an advisory Lens's reader is asked through (decision 0224).

Nothing here reaches the network: the live transport is held by what it refuses before it sends anything, and by what a
stand-in opener was handed."""
from __future__ import annotations

import io
import os
import unittest
from unittest import mock

from adapters import azure

HOST = "factory-readers.openai.azure.com"
KEY = "k" * 32
ID = "resp_0123456789abcdef"
ASKED = {"model": "a-deployment", "input": "the prompt", "background": True, "store": True}


class Framed(io.BytesIO):
    """An answer's body, framed as Azure frames one: by the frame its headers say, or else by the length of the body."""
    headers = {}

    def __init__(self, body: bytes = b""):
        super().__init__(body)
        said = type(self).headers
        framed = {k.lower() for k in said.keys()} & {"content-length", "transfer-encoding"}
        self.headers = said if framed else dict(said, **{"Content-Length": str(len(body))})


class Answer(Framed):
    status = 200
    headers = {"Content-Type": "application/json; charset=utf-8", "Retry-After": "7", "Set-Cookie": "c=1"}
    asked = []

    def read(self, size=-1):
        self.asked.append(size)
        return super().read(size)


class Capture:
    """An opener that keeps what it was handed and answers one body."""

    def __init__(self, body: bytes = b'{"status": "queued"}', answer=Answer):
        self.sent, self._body, self._answer = [], body, answer

    def open(self, request, timeout=None):
        self.sent.append((request, timeout))
        return self._answer(self._body)


class Real:
    """An opener that answers by http.client's own reader over raw bytes, which stay readable once it closes them."""

    def __init__(self, raw: bytes):
        self.wire = io.BytesIO(raw)
        self.wire.close = lambda: None

    def makefile(self, mode):
        return self.wire

    def open(self, request, timeout=None):
        got = azure.http.client.HTTPResponse(self)
        got.begin()
        if got.status >= 400:
            raise azure.urllib.error.HTTPError(request.full_url, got.status, "x", got.headers, got)
        return got


def live(opener=None, host: str = HOST, key: str = KEY, seconds: int = 30) -> azure.Live:
    transport = azure.Live(host, key, seconds)
    if opener is not None:
        transport.opener = opener
    return transport


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

        class Lying(dict):      # a kind of dict that says it is not empty, and one that says it is
            def __bool__(self):
                return True

        class Hostile:          # an act whose own comparison raises
            def __eq__(self, other):
                raise RuntimeError("compared")
        for act, body in (("create", Lying()), ("chat", Lying()), (Hostile(), ASKED), (Hostile(), None)):
            with self.assertRaises(azure.Unanswered, msg=(act, body)):
                azure.request(act, ID if body is None else None, body)
        # Each named request is held as `request` holds one, and a request built by hand with a part too few is refused.
        for made, given in ((azure.create, {}), (azure.chat, {}), (azure.create, Lying()), (azure.read, "../x"),
                            (azure.cancel, "../x"), (azure.cancel, Text(ID))):
            with self.assertRaises(azure.Unanswered, msg=(made.__name__, given)):
                made(given)
        with self.assertRaises(azure.Unanswered):
            azure.wire({"act": "read", "id": ID})
        # A request built by hand is held to the same rules before it is written as a method and a path.
        for req in ({"act": "read", "id": "../files", "body": None}, {"act": "upload", "id": None, "body": ASKED},
                    {"act": "create", "id": None, "body": ASKED, "path": "/openai/v1/files"},
                    {"act": "create", "id": None, "body": ASKED, "host": "example.com"},
                    {"method": "POST", "path": "/openai/v1/files", "body": ASKED, "accept": "x"}, None):
            with self.assertRaises(azure.Unanswered, msg=req):
                azure.wire(req)

    def test_the_azure_transport_reaches_one_host_and_two_apis(self):
        # One host, of the forms Azure serves a model's API under, written as the configuration names it: no port, no
        # user, no path, no other case, and no host that only ends as one does.
        for host in (HOST, "f.openai.azure.com", "factory-readers.services.ai.azure.com",
                     "factory-readers.cognitiveservices.azure.com"):
            opener = Capture()
            live(opener, host).send(azure.read(ID))
            self.assertEqual(opener.sent[0][0].full_url, "https://%s/openai/v1/responses/%s" % (host, ID))
        azure.Live("f" * 63 + ".openai.azure.com", KEY, 30)

        class Text(str):
            def __str__(self):
                return "example.com"
        with self.assertRaises(azure.Unanswered):
            azure.Live(Text(HOST), KEY, 30)
        for host in ("openai.azure.com", ".openai.azure.com", "a.b.openai.azure.com", "Factory.openai.azure.com",
                     "factory.openai.azure.com:8443", "u@factory.openai.azure.com", "factory.openai.azure.com/x",
                     "factory.openai.azure.com.example.com", "factory.openai.azure.com\n", "-f.openai.azure.com",
                     "f-.openai.azure.com", "example.com", "api.github.com", "factory.azure.com", "", None,
                     "factory.openai.azure.com#x", "factory.openai.azure.com?x", "f" * 64 + ".openai.azure.com",
                     "https://factory.openai.azure.com"):
            with self.assertRaises(azure.Unanswered, msg=repr(host)):
                azure.Live(host, KEY, 30)
        # What it sends: HTTPS to that host, the path asked, the body as JSON, and its caller's key under Azure's header.
        opener = Capture()
        answer = live(opener).send(azure.create(ASKED))
        self.assertEqual(answer, {"status": 200, "headers": {"content-type": "application/json; charset=utf-8", "retry-after": "7"},
                                  "body": {"status": "queued"}})
        sent, timeout = opener.sent[0]
        self.assertEqual((sent.full_url, sent.get_method(), sent.get_header("Api-key"), timeout),
                         ("https://%s/openai/v1/responses" % HOST, "POST", KEY, 30))
        self.assertEqual((azure.json.loads(sent.data), sent.get_header("Content-type")), (ASKED, "application/json"))
        self.assertIsNone(sent.get_header("Authorization"))
        # A request built by hand is held to the same rules before anything is opened.
        opener = Capture()
        for req in ({"act": "read", "id": "../files", "body": None}, {"act": "upload", "id": None, "body": ASKED},
                    {"act": "create", "id": None, "body": ASKED, "path": "/openai/v1/files"},
                    {"act": "create", "id": None, "body": ASKED, "host": "example.com"},
                    {"method": "POST", "path": "/openai/v1/files", "body": ASKED, "accept": "x"}, None):
            with self.assertRaises(azure.Unanswered, msg=req):
                live(opener).send(req)
        self.assertEqual(opener.sent, [])

    def test_the_azure_transport_takes_its_key_from_its_caller_and_sends_it_nowhere_else(self):
        # The key is one word of printable ASCII, given by the caller; nothing is read from the environment.
        class Text(str):        # text of another class, which could write itself as another key
            pass
        for key in ("", " ", "a b", "a\nb", "a\rb", "kéy", None, 7, b"key", Text(KEY)):
            with self.assertRaises(azure.Unanswered, msg=repr(key)):
                azure.Live(HOST, key, 30)
        with mock.patch.dict(os.environ, {"ADVISORY_AZURE_KEY": "e" * 32, "AZURE_OPENAI_API_KEY": "e" * 32}):
            for key in ("", None):
                with self.assertRaises(azure.Unanswered, msg=repr(key)):
                    azure.Live(HOST, key, 30)
            opener = Capture()
            live(opener).send(azure.read(ID))
            self.assertEqual(opener.sent[0][0].get_header("Api-key"), KEY)
        with mock.patch.dict(os.environ, {"https_proxy": "http://proxy.invalid:1", "HTTPS_PROXY": "http://proxy.invalid:1"}):
            handlers = live().opener.handlers
        # It follows no redirect, so the key goes to the host named and to no other, and takes no proxy.
        self.assertTrue(any(isinstance(h, azure._NoRedirect) for h in handlers))
        self.assertFalse(any(type(h) is azure.urllib.request.HTTPRedirectHandler for h in handlers))
        self.assertFalse(any(isinstance(h, azure.urllib.request.ProxyHandler) and h.proxies for h in handlers))
        sent = azure.urllib.request.Request("https://%s/openai/v1/responses" % HOST)
        with self.assertRaises(azure.Unanswered):
            azure._NoRedirect().redirect_request(sent, None, 302, "Found", {}, "https://example.com/")
        for code in (301, 302, 303, 307, 308):
            class Moved:
                def open(self, request, timeout=None, code=code):
                    raise azure.urllib.error.HTTPError(request.full_url, code, "x", {"Location": "https://example.com/"},
                                                       io.BytesIO(b""))
            with self.assertRaises(azure.Unanswered, msg=code) as refused:
                live(Moved()).send(azure.create(ASKED))
            self.assertIn("redirect", str(refused.exception))
            self.assertIsNone(refused.exception.__context__)
        # No refusal names the key, the host or the address, and none is chained to an error that does.
        secret = "s3cr3t-" + "k" * 20

        class Down:
            def open(self, request, timeout=None):
                raise azure.urllib.error.URLError("no route to %s with %s" % (request.full_url, secret))
        with self.assertRaises(azure.Unanswered) as refused:
            live(Down(), key=secret).send(azure.create(ASKED))
        for text in (str(refused.exception), repr(refused.exception.__cause__), repr(refused.exception.__context__)):
            self.assertNotIn(secret, text)
            self.assertNotIn(HOST, text)
        self.assertNotIn(secret, repr(live(key=secret)))
        # It verifies the host's certificate by a context of its own, so a default context replaced elsewhere in the
        # process, as one that verifies nothing, does not turn that off.
        with mock.patch.object(azure.ssl, "_create_default_https_context", azure.ssl._create_unverified_context):
            handlers = live().opener.handlers
        made = [getattr(h, "_context", None) for h in handlers if isinstance(h, azure.urllib.request.HTTPSHandler)]
        self.assertEqual([(getattr(c, "verify_mode", None), getattr(c, "check_hostname", None)) for c in made],
                         [(azure.ssl.CERT_REQUIRED, True)])
        self.assertGreaterEqual(made[0].minimum_version, azure.ssl.TLSVersion.TLSv1_2)
        # It logs no session key where SSLKEYLOGFILE says: the default context, which would, is never made.
        with mock.patch.dict(os.environ, {"SSLKEYLOGFILE": os.devnull}), \
                mock.patch.object(azure.ssl, "create_default_context", side_effect=AssertionError("made")):
            made = [h._context for h in live().opener.handlers if isinstance(h, azure.urllib.request.HTTPSHandler)]
        self.assertEqual([getattr(c, "keylog_filename", None) for c in made], [None])

    def test_the_azure_transport_reads_only_an_answer_framed_as_azure_frames_one(self):
        # Azure frames each of its answers, chunked or with one length of digits alone. Any other answer, a body's or
        # an error's, could be read otherwise by another reader, or end only where its connection does, so that one
        # cut short is not told from one whole: it is refused before any of it is read.
        def headers(lines: bytes):
            return azure.http.client.parse_headers(io.BytesIO(b"Content-Type: application/json\r\n" + lines + b"\r\n"))

        class Got(Answer):     # an answer with the headers as they were sent, and no frame of the fake's own
            asked = []

            def __init__(self, body: bytes = b""):
                super().__init__(body)
                self.headers = type(self).headers
        refused = (b"", b"Content-Length: 2\r\nContent-Length: 2\r\n", b"Content-Length: 2\r\ncontent-length: 3\r\n",
                   b"Content-Length: +2\r\n", b"Content-Length: 2x\r\n", b"Content-Length: 1_0\r\n",
                   b"Content-Length: \xb2\r\n", b"Content-Length: -1\r\n", b"Transfer-Encoding: gzip\r\n",
                   b"Transfer-Encoding: gzip, chunked\r\n", b"Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n",
                   b"Content-Length: 999\r\nTransfer-Encoding: chunked\r\n", b"Content-Length: 2\r\nTransfer-Encoding: gzip\r\n",
                   b"Content-Length: 2\r\nTransfer-Encoding: gzip, chunked\r\n", b"Content-Length: 00000000002\r\n",
                   b"Content-Length: %d\r\n" % (azure.LARGEST + 1), b"Content-Length: %s\r\n" % (b"9" * 5000))
        for lines in refused:
            Got.headers = headers(lines)
            with self.assertRaisesRegex(azure.Unanswered, "refused, not read", msg=lines):
                live(Capture(b"{}", Got)).send(azure.read(ID))

            class Error:
                def open(self, request, timeout=None, lines=lines):
                    raise azure.urllib.error.HTTPError(request.full_url, 500, "x", headers(lines), Got(b"{}"))
            with self.assertRaisesRegex(azure.Unanswered, "refused, not read", msg=lines):
                live(Error()).send(azure.read(ID))
        self.assertEqual(Got.asked, [])
        for lines in (b"Content-Length: 2\r\n", b"content-length: 2\r\n", b"Transfer-Encoding: chunked\r\n",
                      b"Transfer-Encoding: Chunked\r\n", b"Content-Length: 0000000002\r\n"):
            Got.headers = headers(lines)
            self.assertEqual(live(Capture(b"{}", Got)).send(azure.read(ID))["body"], {}, lines)

            class Fault:
                def open(self, request, timeout=None, lines=lines):
                    raise azure.urllib.error.HTTPError(request.full_url, 500, "x", headers(lines), Got(b"{}"))
            self.assertEqual(live(Fault()).send(azure.read(ID))["status"], 500, lines)
        # So too through http.client's own reader.
        for status in (b"200 OK", b"500 x"):
            for lines in refused[-6:]:
                with self.assertRaisesRegex(azure.Unanswered, "refused, not read", msg=lines):
                    live(Real(b"HTTP/1.1 %s\r\n%s\r\n2\r\n{}\r\n0\r\n\r\n" % (status, lines))).send(azure.read(ID))
            for lines, body in ((b"Content-Length: 2\r\n", b"{}"), (b"Transfer-Encoding: chunked\r\n", b"2\r\n{}\r\n0\r\n\r\n")):
                got = live(Real(b"HTTP/1.1 %s\r\nContent-Type: application/json\r\n%s\r\n%s" % (status, lines, body)))
                self.assertEqual(got.send(azure.read(ID))["body"], {}, lines)

    def test_the_azure_transport_bounds_every_answer_in_size_and_time(self):
        # The seconds are its caller's, a whole number from one to the longest a step may wait on one request.
        self.assertEqual(azure.LONGEST, 20 * 60)
        live(seconds=1)
        for seconds in (0, -1, azure.LONGEST + 1, 1.5, "30", None, True):
            with self.assertRaises(azure.Unanswered, msg=repr(seconds)):
                azure.Live(HOST, KEY, seconds)
        opener = Capture()
        self.assertEqual(live(opener, seconds=azure.LONGEST).send(azure.read(ID))["status"], 200)
        self.assertEqual((opener.sent[0][0].get_method(), opener.sent[0][0].data, opener.sent[0][1]), ("GET", None, azure.LONGEST))
        # An answer at the bound, four mebibytes, is kept; one byte over is refused, never cut short.
        self.assertEqual((azure.LARGEST, azure.HEADER), (4 * 1024 * 1024, 100))
        at = b'"' + b"a" * (azure.LARGEST - 2) + b'"'
        self.assertEqual(len(live(Capture(at)).send(azure.read(ID))["body"]), azure.LARGEST - 2)
        class Chunked(Answer):
            headers = dict(Answer.headers, **{"Transfer-Encoding": "chunked"})
        for answer in (Answer, Chunked):
            with self.assertRaises(azure.Unanswered):
                live(Capture(at + b" ", answer)).send(azure.read(ID))
        self.assertEqual(set(Answer.asked), {azure.CHUNK})      # never the whole of what is sent, read to be refused
        # Azure out of reach, or an answer cut short while it is read, a body's or an error's, is refused and never
        # another exception.
        class Short:
            def open(self, *a, **k):
                raise azure.http.client.IncompleteRead(b"")

        class Broken(io.BytesIO):
            def read(self, *a):
                raise azure.http.client.IncompleteRead(b"")

        class Error:
            def open(self, request, timeout=None):
                raise azure.urllib.error.HTTPError(request.full_url, 500, "x", {"Content-Length": "10"}, Broken())

        class Slow:
            def open(self, *a, **k):
                raise TimeoutError("timed out")
        for opener in (Short(), Error(), Slow()):
            with self.assertRaises(azure.Unanswered, msg=type(opener).__name__):
                live(opener).send(azure.create(ASKED))
        # An answer of more or fewer bytes than the length it said, a body's or an error's, is refused: they are counted
        # as read, never taken from the stream, which an error may not forward.
        def said(frame):
            class Said(Answer):
                headers = dict(Answer.headers, **frame)
            return Said

        class Cut:
            def __init__(self, length, body):
                self.length, self.body = length, body

            def open(self, request, timeout=None):
                raise azure.urllib.error.HTTPError(request.full_url, 500, "x", {"Content-Length": self.length},
                                                   io.BytesIO(self.body))
        for length, body in (("47", b'{"a"'), ("2", b"{} ")):
            for opener in (Capture(body, said({"Content-Length": length})), Cut(length, body)):
                with self.assertRaisesRegex(azure.Unanswered, "the length it said", msg=(length, body)):
                    live(opener).send(azure.read(ID))
        for frame in ({"Content-Length": "2"}, {"Transfer-Encoding": "chunked"}):
            self.assertEqual(live(Capture(b"{}", said(frame))).send(azure.read(ID))["body"], {})
        # An error Azure answers is an answer, with its status, bounded as any other: a rate limit says how long to wait.
        class Limited:
            def open(self, request, timeout=None):
                raise azure.urllib.error.HTTPError(request.full_url, 429, "x", {"Content-Type": "application/json",
                                                                               "Retry-After": "20", "Content-Length": "42"},
                                                   io.BytesIO(b'{"error": {"code": "rate_limit_exceeded"}}'))
        self.assertEqual(live(Limited()).send(azure.create(ASKED)),
                         {"status": 429, "headers": {"content-type": "application/json", "retry-after": "20"},
                          "body": {"error": {"code": "rate_limit_exceeded"}}})

        class Large:
            def open(self, request, timeout=None):
                raise azure.urllib.error.HTTPError(request.full_url, 500, "x", {"Transfer-Encoding": "chunked"},
                                                   io.BytesIO(b"x" * (azure.LARGEST + 1)))
        with self.assertRaises(azure.Unanswered) as refused:
            live(Large()).send(azure.create(ASKED))
        self.assertIsNone(refused.exception.__context__)
        # What cannot be sent as JSON, or read as it however deep, is refused or text, and never another exception.
        deep = {}
        for _ in range(100000):
            deep = {"a": deep}
        for body in ({"a": {1}}, {"a": float("nan")}, deep):
            with self.assertRaises(azure.Unanswered):
                live(Capture()).send(azure.create(body))
        self.assertEqual(len(live(Capture(b"[" * 200000)).send(azure.read(ID))["body"]), 200000)
        self.assertIsNone(live(Capture(b"")).send(azure.read(ID))["body"])
        # A whole number of more digits than any count is text, never read: Python 3.9 reads one of any length, and
        # one of four mebibytes takes most of a minute.
        self.assertEqual(azure.DIGITS, 64)
        self.assertEqual(live(Capture(b'{"n": %s}' % (b"9" * 63))).send(azure.read(ID))["body"], {"n": int("9" * 63)})
        for many in (b"9" * 64, b"-" + b"9" * 63, b"1" * 100000):
            self.assertEqual(live(Capture(b'{"n": %s}' % many)).send(azure.read(ID))["body"], '{"n": %s}' % many.decode())
        # A body that is not JSON, or says it is and is not, is text, and no header is kept but the ones named.
        class Plain(Framed):
            status = 502
            headers = {"Content-Type": "text/html", "X-Other": "1"}
        self.assertEqual(live(Capture(b"<html>", Plain)).send(azure.read(ID)),
                         {"status": 502, "headers": {"content-type": "text/html"}, "body": "<html>"})
        self.assertEqual(live(Capture(b"{}", Plain)).send(azure.read(ID))["body"], "{}")

        class Shouted(Framed):
            status = 200
            headers = {"Content-Type": "Application/JSON"}
        self.assertEqual(live(Capture(b"{}", Shouted)).send(azure.read(ID))["body"], {})
        self.assertEqual(live(Capture(b"{not json")).send(azure.read(ID))["body"], "{not json")
        for text in (b'{"a": NaN}', b"[Infinity]", b"-Infinity", b'{"a": 1e999}', b"[-1E999]", b"1e400"):
            self.assertEqual(live(Capture(text)).send(azure.read(ID))["body"], text.decode())
        self.assertEqual(live(Capture(b'{"a": 1.5e3, "b": -2.5}')).send(azure.read(ID))["body"], {"a": 1500.0, "b": -2.5})
        # Bytes that are not UTF-8 are text with each one marked, and never read as JSON: nothing is changed unseen.
        self.assertEqual(live(Capture(b'{"a": "\xff"}')).send(azure.read(ID))["body"], '{"a": "\ufffd"}')
        # A header a caller reads is kept only when it is short, printable ASCII: a caller acts on no more than that.
        class Odd(Framed):
            status = 429
            headers = {"Content-Type": "application/json"}
        for value in ("1" * 101, "1\r\n2", "\u00b2", "1\x00"):
            Odd.headers = {"Content-Type": "application/json", "Retry-After": value}
            self.assertEqual(live(Capture(b"{}", Odd)).send(azure.read(ID))["headers"], {"content-type": "application/json"}, value)
        Odd.headers = {"Retry-After": "1" * 100}
        self.assertEqual(live(Capture(b"{}", Odd)).send(azure.read(ID))["headers"], {"retry-after": "1" * 100})
        # Of a header given twice the last value is kept, or none where the last is refused, never one before it.
        for last, kept in ((b"2", {"content-type": "application/json", "retry-after": "2"}), (b"\xb2", {}), (b"1" * 101, {})):
            Odd.headers = azure.http.client.parse_headers(io.BytesIO(
                b"Content-Type: application/json\r\nRetry-After: 1\r\nContent-Length: 2\r\nContent-Type: %s\r\n"
                b"Retry-After: %s\r\n\r\n" % (b"application/json" if kept else last, last)))
            self.assertEqual(live(Capture(b"{}", Odd)).send(azure.read(ID))["headers"], kept, last)


if __name__ == "__main__":
    unittest.main()
