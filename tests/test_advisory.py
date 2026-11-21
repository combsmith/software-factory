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

    def __init__(self, body: bytes = b""):
        super().__init__(body)
        self.asked = []         # what each read of this answer asked, its own and no other's

    def read(self, size=-1):
        self.asked.append(size)
        return super().read(size)


class Capture:
    """An opener that keeps what it was handed and answers one body."""

    def __init__(self, body: bytes = b'{"status": "queued"}', answer=Answer):
        self.sent, self.answers, self._body, self._answer = [], [], body, answer

    def open(self, fullurl, data=None, timeout=None):
        self.sent.append((fullurl, timeout))
        self.answers.append(self._answer(self._body))
        return self.answers[-1]


class Real:
    """An opener that answers by the transport's own response over raw bytes, which stay readable once it closes them;
    or a connection's socket that keeps what is sent it and answers the same."""

    def __init__(self, raw: bytes, response=azure._Response):
        self.wire, self.response, self.sent = io.BytesIO(raw), response, []
        self.wire.close = lambda: None

    def makefile(self, mode):
        return self.wire

    def sendall(self, data):
        self.sent.append(bytes(data))

    def close(self):
        pass

    def open(self, fullurl, data=None, timeout=None):
        got = self.response(self)
        got.begin()
        if got.status >= 400:
            raise azure.urllib.error.HTTPError(fullurl.full_url, got.status, "x", got.headers, got)
        return got


class Refuses:
    """The opener of every transport a test makes and hands no stand-in: it raises, so that no test reaches the network,
    even by mistake."""

    def open(self, fullurl, data=None, timeout=None):
        raise AssertionError("a test reached for the network")


def live(opener=None, host: str = HOST, key: str = KEY, seconds: int = 30) -> azure.Live:
    transport = azure.Live(host, key, seconds)
    transport.opener = Refuses() if opener is None else opener
    return transport


def wired(real: Real):
    """The transport's own opener, handler, connection and response, over a socket that reaches nothing."""
    return mock.patch.object(azure._Connection, "connect", lambda connection: setattr(connection, "sock", real))


class Transport(unittest.TestCase):
    def setUp(self):
        # A connection a test does not answer raises before it connects, so no test reaches the network.
        held = mock.patch.object(azure.http.client.HTTPSConnection, "connect", side_effect=AssertionError("network"))
        held.start()
        self.addCleanup(held.stop)

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
                     "https://factory.openai.azure.com", "f@openai.azure.com", "f.openai-azure.com",
                     "f.openai.azure-com", "f.services-ai.azure.com", "f.services.ai-azure.com", "f.services.ai.azure-com",
                     "f.cognitiveservices-azure.com", "f.cognitiveservices.azure-com"):
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
        # Each of the four is sent with its method, its path and its body, and a cancel's empty object is a body.
        opener = Capture()
        for req in (azure.chat(ASKED), azure.read(ID), azure.cancel(ID)):
            live(opener).send(req)
        self.assertEqual([(s.get_method(), s.full_url, s.data, s.get_header("Content-type"), s.get_header("Api-key"))
                          for s, _ in opener.sent],
                         [("POST", "https://%s/openai/v1/chat/completions" % HOST, azure.json.dumps(ASKED).encode(),
                           "application/json", KEY), ("GET", "https://%s/openai/v1/responses/%s" % (HOST, ID), None, None, KEY),
                          ("POST", "https://%s/openai/v1/responses/%s/cancel" % (HOST, ID), b"{}", "application/json", KEY)])
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
        for key in ("", " ", "a b", "a\nb", "a\rb", "a\tb", "a\x00b", "a\x7fb", "\x1b", "kéy", "k\u00b2", None, 7, b"key",
                    Text(KEY)):
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
            handlers = azure.Live(HOST, KEY, 30).opener.handlers
        # It follows no redirect, so the key goes to the host named and to no other, and takes no proxy.
        self.assertTrue(any(isinstance(h, azure._NoRedirect) for h in handlers))
        self.assertFalse(any(type(h) is azure.urllib.request.HTTPRedirectHandler for h in handlers))
        self.assertFalse(any(isinstance(h, azure.urllib.request.ProxyHandler) and h.proxies for h in handlers))
        sent = azure.urllib.request.Request("https://%s/openai/v1/responses" % HOST)
        with self.assertRaises(azure.Unanswered):
            azure._NoRedirect().redirect_request(sent, None, 302, "Found", {}, "https://example.com/")
        for code in (301, 302, 303, 307, 308):
            class Moved:
                def open(self, fullurl, data=None, timeout=None, code=code):
                    raise azure.urllib.error.HTTPError(fullurl.full_url, code, "x", {"Location": "https://example.com/"},
                                                       io.BytesIO(b""))
            with self.assertRaises(azure.Unanswered, msg=code) as refused:
                live(Moved()).send(azure.create(ASKED))
            self.assertIn("redirect", str(refused.exception))
            self.assertIsNone(refused.exception.__context__)
        # urllib reads a redirect's Location before it asks where to go, so that one malformed raises another error and
        # one absent no refusal: each redirect is refused before any header of it is read, and its answer closed. An
        # opener of urllib's own, with no handler that reaches the network, answers each.
        class Redirected(azure.urllib.request.BaseHandler):
            handler_order = 100         # before the opener's own HTTPS handler, which would reach the network

            def __init__(self, code, location):
                self.code, self.location, self.fp, self.opened = code, location, io.BytesIO(b""), 0

            def https_open(self, req):
                self.opened += 1
                moved = b"" if self.location is None else b"Location: %s\r\n" % self.location
                # Held here, since urllib's answer closes what it wraps once nothing holds it.
                self.got = azure.urllib.response.addinfourl(
                    self.fp, azure.http.client.parse_headers(io.BytesIO(moved + b"Content-Length: 0\r\n\r\n")),
                    req.full_url, self.code)
                self.got.msg = "x"
                return self.got

        def redirected(code, location):
            answers = Redirected(code, location)
            opener = azure.urllib.request.OpenerDirector()
            for handler in (azure._NoRedirect(), azure.urllib.request.HTTPErrorProcessor(),
                            azure.urllib.request.HTTPDefaultErrorHandler(), answers):
                opener.add_handler(handler)
            return opener, answers
        for code in (301, 302, 303, 307, 308):
            for location in (b"http://[::1", b"https://[", None, b"https://example.com/"):
                opener, answers = redirected(code, location)
                with self.assertRaisesRegex(azure.Unanswered, "redirect", msg=(code, location)):
                    opener.open(sent, timeout=30)
                self.assertTrue(answers.fp.closed, (code, location))
                opener, answers = redirected(code, location)
                with self.assertRaisesRegex(azure.Unanswered, "redirect", msg=(code, location)) as refused:
                    live(opener).send(azure.create(ASKED))
                self.assertTrue(answers.fp.closed, (code, location))
                self.assertTrue(refused.exception.__suppress_context__ and refused.exception.__cause__ is None)
            # And through the opener the transport builds, whose handlers are urllib's own: one open, never a second.
            transport, answers = azure.Live(HOST, KEY, 30), Redirected(code, b"http://[::1")
            transport.opener.add_handler(answers)
            with self.assertRaisesRegex(azure.Unanswered, "redirect", msg=code):
                transport.send(azure.create(ASKED))
            self.assertEqual((answers.opened, answers.fp.closed), (1, True), code)
        # No refusal names the key, the host or the address, and none is chained to an error that does.
        secret = "s3cr3t-" + "k" * 20

        class Down:
            def open(self, fullurl, data=None, timeout=None):
                raise azure.urllib.error.URLError("no route to %s with %s" % (fullurl.full_url, secret))
        with self.assertRaises(azure.Unanswered) as refused:
            live(Down(), key=secret).send(azure.create(ASKED))
        for text in (str(refused.exception), repr(refused.exception.__cause__), repr(refused.exception.__context__)):
            self.assertNotIn(secret, text)
            self.assertNotIn(HOST, text)
        self.assertNotIn(secret, repr(live(key=secret)))
        # Every refusal is raised from nothing, so that neither the key nor the host rides along as its context or its
        # cause: of a read of the answer that fails, and of a request that cannot be encoded.
        class Torn(Answer):
            def read(self, size=-1):
                raise ConnectionResetError("reset by %s with %s" % (HOST, secret))
        for opener, req in ((Capture(answer=Torn), azure.read(ID)), (Capture(), azure.create({"a": {1}})),
                            (Capture(), azure.create({"a": float("inf")}))):
            with self.assertRaises(azure.Unanswered, msg=req) as refused:
                live(opener, key=secret).send(req)
            self.assertTrue(refused.exception.__context__ is None or refused.exception.__suppress_context__, req)
            self.assertIsNone(refused.exception.__cause__, req)
        # A request is written inside the path that refuses, and no refusal holds as its context an error its caller was
        # handling when it called, which may hold the key too.
        try:
            raise KeyError(secret)
        except KeyError:
            for opener, req in ((Refuses(), {"act": "read", "id": "../x", "body": None}), (Down(), azure.create(ASKED)),
                                (Capture(), azure.create({"a": {1}}))):
                with self.assertRaises(azure.Unanswered, msg=req) as refused:
                    live(opener, key=secret).send(req)
                self.assertIsNone(refused.exception.__context__, req)
        # It verifies the host's certificate by a context of its own, so a default context replaced elsewhere in the
        # process, as one that verifies nothing, does not turn that off.
        with mock.patch.object(azure.ssl, "_create_default_https_context", azure.ssl._create_unverified_context):
            handlers = azure.Live(HOST, KEY, 30).opener.handlers
        made = [getattr(h, "_context", None) for h in handlers if isinstance(h, azure.urllib.request.HTTPSHandler)]
        self.assertEqual([(getattr(c, "verify_mode", None), getattr(c, "check_hostname", None)) for c in made],
                         [(azure.ssl.CERT_REQUIRED, True)])
        self.assertGreaterEqual(made[0].minimum_version, azure.ssl.TLSVersion.TLSv1_2)
        # It logs no session key where SSLKEYLOGFILE says: the default context, which would, is never made.
        with mock.patch.dict(os.environ, {"SSLKEYLOGFILE": os.devnull}), \
                mock.patch.object(azure.ssl, "create_default_context", side_effect=AssertionError("made")):
            handlers = azure.Live(HOST, KEY, 30).opener.handlers
        made = [h._context for h in handlers if isinstance(h, azure.urllib.request.HTTPSHandler)]
        self.assertEqual([getattr(c, "keylog_filename", None) for c in made], [None])

    def test_the_azure_transport_reads_only_an_answer_framed_as_azure_frames_one(self):
        # Azure frames each of its answers, chunked or with one length of digits alone. Any other answer, a body's or
        # an error's, could be read otherwise by another reader, or end only where its connection does, so that one
        # cut short is not told from one whole: it is refused before any of it is read.
        def headers(lines: bytes):
            return azure.http.client.parse_headers(io.BytesIO(b"Content-Type: application/json\r\n" + lines + b"\r\n"))

        made = []

        class Got(Answer):     # an answer with the headers as they were sent, and no frame of the fake's own
            def __init__(self, body: bytes = b""):
                super().__init__(body)
                self.headers = type(self).headers
                made.append(self)
        refused = (b"", b"Content-Length: 2\r\nContent-Length: 2\r\n", b"Content-Length: 2\r\ncontent-length: 3\r\n",
                   b"Content-Length: +2\r\n", b"Content-Length: 2x\r\n", b"Content-Length: 1_0\r\n",
                   b"Content-Length: \xb2\r\n", b"Content-Length: -1\r\n", b"Transfer-Encoding: gzip\r\n",
                   b"Transfer-Encoding: gzip, chunked\r\n", b"Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n",
                   b"Content-Length: 999\r\nTransfer-Encoding: chunked\r\n", b"Content-Length: 2\r\nTransfer-Encoding: gzip\r\n",
                   b"Content-Length: 2\r\nTransfer-Encoding: gzip, chunked\r\n", b"Content-Length: 00000000002\r\n",
                   b"Content-Length: %d\r\n" % (azure.LARGEST + 1), b"Content-Length: %s\r\n" % (b"9" * 5000),
                   b"Content-Length: 2\r\nno colon\r\nContent-Length: 3\r\n")
        for lines in refused:
            Got.headers = headers(lines)
            with self.assertRaisesRegex(azure.Unanswered, "refused, not read", msg=lines):
                live(Capture(b"{}", Got)).send(azure.read(ID))

            class Error:
                def open(self, fullurl, data=None, timeout=None, lines=lines):
                    raise azure.urllib.error.HTTPError(fullurl.full_url, 500, "x", headers(lines), Got(b"{}"))
            with self.assertRaisesRegex(azure.Unanswered, "refused, not read", msg=lines):
                live(Error()).send(azure.read(ID))
        self.assertEqual(len(made), 2 * len(refused))
        self.assertEqual([got.asked for got in made], [[]] * len(made))
        for lines in (b"Content-Length: 2\r\n", b"content-length: 2\r\n", b"Transfer-Encoding: chunked\r\n",
                      b"Transfer-Encoding: Chunked\r\n", b"Content-Length: 0000000002\r\n"):
            Got.headers = headers(lines)
            self.assertEqual(live(Capture(b"{}", Got)).send(azure.read(ID))["body"], {}, lines)

            class Fault:
                def open(self, fullurl, data=None, timeout=None, lines=lines):
                    raise azure.urllib.error.HTTPError(fullurl.full_url, 500, "x", headers(lines), Got(b"{}"))
            self.assertEqual(live(Fault()).send(azure.read(ID))["status"], 500, lines)
        # So too through http.client's own reader.
        for status in (b"200 OK", b"500 x"):
            for lines in refused[-7:]:
                with self.assertRaisesRegex(azure.Unanswered, "refused, not read", msg=lines):
                    live(Real(b"HTTP/1.1 %s\r\n%s\r\n2\r\n{}\r\n0\r\n\r\n" % (status, lines))).send(azure.read(ID))
            for lines, body in ((b"Content-Length: 2\r\n", b"{}"), (b"Transfer-Encoding: chunked\r\n", b"2\r\n{}\r\n0\r\n\r\n")):
                got = live(Real(b"HTTP/1.1 %s\r\nContent-Type: application/json\r\n%s\r\n%s" % (status, lines, body)))
                self.assertEqual(got.send(azure.read(ID))["body"], {}, lines)

    def test_the_azure_transport_reads_no_more_of_a_connection_than_an_answer_may_hold(self):
        # A chunk's size of -1, or a trailer without end, reads no more than the bound and a frame's allowance.
        cap = azure.LARGEST + azure.FRAMING
        self.assertEqual(azure.FRAMING, 64 * 1024)
        line = b"x: " + b"y" * 60000 + b"\r\n"
        for status in (b"200 OK", b"500 x"):
            for body in (b"-1\r\n" + b"x" * (cap + 10), b"2\r\n{}\r\n0\r\n" + line * (cap // len(line) + 2)):
                head = b"HTTP/1.1 %s\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n" % status
                opener = Real(head + body)
                with self.assertRaises(azure.Unanswered, msg=(status, body[:2])):
                    live(opener).send(azure.read(ID))
                self.assertLessEqual(opener.wire.tell(), len(head) + cap)
        for take in (lambda c: c.read(), lambda c: c.read(azure.CHUNK), lambda c: c.readline(),
                     lambda c: c.readline(70000), lambda c: c.readinto(bytearray(azure.CHUNK))):
            wire = io.BytesIO(b"x" * (cap + 10))
            capped = azure._Capped(wire)
            with self.assertRaises(azure.Unanswered):
                while take(capped):
                    pass
            self.assertEqual(wire.tell(), cap)
        # A chunk's size is hex digits alone, and an answer that ends before the line that closes its last chunk's
        # trailer is cut short: http.client would read both as whole.
        head = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n"
        for body in (b"0x2\r\n{}\r\n0\r\n\r\n", b"+2\r\n{}\r\n0\r\n\r\n", b" 2\r\n{}\r\n0\r\n\r\n", b"2_0\r\n{}\r\n0\r\n\r\n",
                     b"-1\r\n{}\r\n0\r\n\r\n", b"2\r\n{}\r\n0\r\n", b"2\r\n{}\r\n0\r\nx: y", b"2\r\n{}\r\n0"):
            with self.assertRaises(azure.Unanswered, msg=body):
                live(Real(head + body)).send(azure.read(ID))
        for body in (b"2;e=1\r\n{}\r\n0\r\n\r\n", b"02\r\n{}\r\n0\r\n\r\n", b"1\r\n{\r\n1\r\n}\r\n0\r\nx: y\r\n\r\n",
                     b"00000002;e;f=g\r\n{}\r\n0;e\r\n\r\n"):
            self.assertEqual(live(Real(head + body)).send(azure.read(ID))["body"], {}, body)
        # Each chunk's data ends in CRLF, which http.client tosses unread; an extension is a name, or a name and a value,
        # of tokens; a trailer's line is a field; and a size is of eight hex digits at most, as "0_2" is not.
        for body in (b"2\r\n{}XX0\r\n\r\n", b"2\r\n{}\r0\r\n\r\n", b"2;=v\r\n{}\r\n0\r\n\r\n", b"2; e\r\n{}\r\n0\r\n\r\n",
                     b"2\r\n{}\r\n0\r\nno colon\r\n\r\n", b"000000002\r\n{}\r\n0\r\n\r\n", b"0_2\r\n{}\r\n0\r\n\r\n"):
            with self.assertRaises(azure.Unanswered, msg=body):
                live(Real(head + body)).send(azure.read(ID))
        # The cap holds from the first byte, so that an extension's bytes count, and interim answers too, which
        # http.client passes over for as long as they come, here through the transport's own connection.
        interim = b"HTTP/1.1 100 Continue\r\nx: " + b"y" * 60000 + b"\r\n\r\n"
        for raw in (head + (b"1;" + b"e" * 60000 + b"\r\nx\r\n") * 200, interim * (cap // len(interim) + 2) + head):
            real = Real(raw + b"2\r\n{}\r\n0\r\n\r\n")
            with wired(real), self.assertRaises(azure.Unanswered):
                azure.Live(HOST, KEY, 30).send(azure.read(ID))
            self.assertLessEqual(real.wire.tell(), cap)
        real = Real(interim + head + b"2\r\n{}\r\n0\r\n\r\n")
        with wired(real):
            self.assertEqual(azure.Live(HOST, KEY, 30).send(azure.read(ID))["body"], {})
        self.assertTrue(real.sent[0].startswith(b"GET /openai/v1/responses/%s HTTP/1.1\r\n" % ID.encode()))
        # An answer that reaches the cap exactly is read; one byte more is refused.
        at = b"400000\r\n\"" + b"a" * (azure.LARGEST - 2) + b"\"\r\n0\r\n"
        pad = cap - len(head) - len(at) - len(b"x: \r\n" * 2 + b"\r\n")
        for more, read in ((b"", azure.LARGEST - 2), (b"a", None)):
            body = at + b"x: " + b"a" * (pad // 2) + b"\r\nx: " + b"a" * (pad - pad // 2) + more + b"\r\n\r\n"
            if read is None:
                with self.assertRaises(azure.Unanswered):
                    live(Real(head + body)).send(azure.read(ID))
            else:
                self.assertEqual((len(head + body), len(live(Real(head + body)).send(azure.read(ID))["body"])), (cap, read))
        # An answer of http.client's own response, not capped from its first byte, is refused; one of a stand-in is
        # capped as a whole. Headers cut short before the line that closes them, which http.client takes as whole, are
        # refused.
        for status in (b"200 OK", b"500 x"):
            raw = b"HTTP/1.1 %s\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}" % status
            with self.assertRaisesRegex(azure.Unanswered, "own response"):
                live(Real(raw, azure.http.client.HTTPResponse)).send(azure.read(ID))
            with self.assertRaisesRegex(azure.Unanswered, "closes them"):
                live(Real(raw[:-4])).send(azure.read(ID))

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
        # One that says a length over the bound is not read; one chunked is read a chunk at a time, never the whole of
        # what is sent, read to be refused, and capped as a whole, a stand-in's too.
        for answer, asked in ((Answer, []), (Chunked, [azure.CHUNK] * 4 + [azure.FRAMING])):
            opener = Capture(at + b" ", answer)
            with self.assertRaises(azure.Unanswered):
                live(opener).send(azure.read(ID))
            self.assertEqual(opener.answers[0].asked, asked, answer.__name__)
            self.assertTrue(all(0 < n <= 1024 * 1024 for n in opener.answers[0].asked), answer.__name__)
        # Azure out of reach, or an answer cut short while it is read, a body's or an error's, is refused and never
        # another exception.
        class Short:
            def open(self, *a, **k):
                raise azure.http.client.IncompleteRead(b"")

        class Broken(io.BytesIO):
            def read(self, *a):
                raise azure.http.client.IncompleteRead(b"")

        class Error:
            def open(self, fullurl, data=None, timeout=None):
                raise azure.urllib.error.HTTPError(fullurl.full_url, 500, "x", {"Content-Length": "10"}, Broken())

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

            def open(self, fullurl, data=None, timeout=None):
                raise azure.urllib.error.HTTPError(fullurl.full_url, 500, "x", {"Content-Length": self.length},
                                                   io.BytesIO(self.body))
        for length, body in (("47", b'{"a"'), ("2", b"{} ")):
            for opener in (Capture(body, said({"Content-Length": length})), Cut(length, body)):
                with self.assertRaisesRegex(azure.Unanswered, "the length it said", msg=(length, body)):
                    live(opener).send(azure.read(ID))
        for frame in ({"Content-Length": "2"}, {"Transfer-Encoding": "chunked"}):
            self.assertEqual(live(Capture(b"{}", said(frame))).send(azure.read(ID))["body"], {})
        # http.client's own reader reads an answer to the length it said and no byte past it, which is never seen nor
        # kept; one shorter, which it hands over as though whole, is refused by the count of what was read.
        head = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n"
        opener = Real(head + b"{} and more")
        self.assertEqual((live(opener).send(azure.read(ID))["body"], opener.wire.tell()), ({}, len(head) + 2))
        with self.assertRaisesRegex(azure.Unanswered, "the length it said"):
            live(Real(head + b"{")).send(azure.read(ID))
        # An error Azure answers is an answer, with its status, bounded as any other: a rate limit says how long to wait.
        class Limited:
            def open(self, fullurl, data=None, timeout=None):
                raise azure.urllib.error.HTTPError(fullurl.full_url, 429, "x", {"Content-Type": "application/json",
                                                                               "Retry-After": "20", "Content-Length": "42"},
                                                   io.BytesIO(b'{"error": {"code": "rate_limit_exceeded"}}'))
        self.assertEqual(live(Limited()).send(azure.create(ASKED)),
                         {"status": 429, "headers": {"content-type": "application/json", "retry-after": "20"},
                          "body": {"error": {"code": "rate_limit_exceeded"}}})

        class Large:
            def open(self, fullurl, data=None, timeout=None):
                raise azure.urllib.error.HTTPError(fullurl.full_url, 500, "x", {"Transfer-Encoding": "chunked"},
                                                   io.BytesIO(b"x" * (azure.LARGEST + 1)))
        with self.assertRaises(azure.Unanswered) as refused:
            live(Large()).send(azure.create(ASKED))
        self.assertIsNone(refused.exception.__context__)
        # What cannot be sent as JSON, or read as it however deep, is refused or text, and never another exception.
        deep = {}
        for _ in range(100000):
            deep = {"a": deep}
        class Keys(dict):       # a kind of dict whose keys say otherwise than its items
            def __iter__(self):
                return iter(["1"])

        class Items(list):
            pass
        shared, looped, doubled = {"b": 1}, [], ()
        looped.append(looped)
        for _ in range(40):         # one tuple held twice at each of 40 depths: 2 ** 40 values, refused by its count
            doubled = (doubled, doubled)
        for at, body in enumerate(({"a": {1}}, {"a": float("nan")}, deep, {"1": "b", 1: "a"}, {"a": [{"b": {None: 1}}]},
                                   {"a": ({2: 1},)}, {"a": Keys({1: "a", "1": "b"})}, {"a": Items()}, {"a": looped},
                                   {"a": list(range(azure.WALK))}, {"a": doubled})):
            opener = Capture()
            with self.assertRaises(azure.Unanswered, msg=at):
                live(opener).send(azure.create(body))
            self.assertEqual(opener.sent, [])
        opener = Capture()
        live(opener).send(azure.create({"a": [{"b": 1}, {"b": 1}], "c": [shared, (shared["b"],)]}))
        self.assertEqual(azure.json.loads(opener.sent[0][0].data), {"a": [{"b": 1}, {"b": 1}], "c": [{"b": 1}, [1]]})
        # A container held twice is sent: CPython shares the empty tuple, and equal constant tuples, between places.
        for body in ({"a": (), "b": ()}, {"a": (1, 2), "b": (1, 2)}, {"a": [shared, shared]},
                     {"a": list(range(azure.WALK - 2))}):
            opener = Capture()
            live(opener).send(azure.create(body))
            self.assertEqual(len(opener.sent), 1, body if len(str(body)) < 80 else "the longest body")
        self.assertEqual(len(live(Capture(b"[" * 200000)).send(azure.read(ID))["body"]), 200000)
        self.assertIsNone(live(Capture(b"")).send(azure.read(ID))["body"])
        # A whole number of more digits than any count is text, never read: Python 3.9 reads one of any length, and
        # one of four mebibytes takes most of a minute.
        self.assertEqual(azure.DIGITS, 64)
        for most in (b"9" * 63, b"-" + b"9" * 63):
            self.assertEqual(live(Capture(b'{"n": %s}' % most)).send(azure.read(ID))["body"], {"n": int(most)})
        for many in (b"9" * 64, b"-" + b"9" * 64, b"1" * 100000):
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
        # JSON's own type, or one of its structured suffix, is read as JSON; a type that only ends so is text.
        for kind, read in (("application/problem+json; charset=utf-8", {}), ("text/notjson", "{}"),
                           ("application/jsonx", "{}"), ("+json", "{}"), ("problem+json", "{}")):
            Shouted.headers = {"Content-Type": kind}
            self.assertEqual(live(Capture(b"{}", Shouted)).send(azure.read(ID))["body"], read, kind)
        self.assertEqual(live(Capture(b"{not json")).send(azure.read(ID))["body"], "{not json")
        for text in (b'{"a": NaN}', b"[Infinity]", b"-Infinity", b'{"a": 1e999}', b"[-1E999]", b"1e400"):
            self.assertEqual(live(Capture(text)).send(azure.read(ID))["body"], text.decode())
        # A number too large for a float would read as an infinity, so it is text as an infinity is; one finite is read.
        self.assertEqual(live(Capture(b'{"a": 1.5e3, "b": -2.5}')).send(azure.read(ID))["body"], {"a": 1500.0, "b": -2.5})
        # Bytes that are not UTF-8 are text with each one marked, and never read as JSON: nothing is changed unseen.
        self.assertEqual(live(Capture(b'{"a": "\xff"}')).send(azure.read(ID))["body"], '{"a": "\ufffd"}')
        # A header a caller reads is kept only when it is short, printable ASCII: a caller acts on no more than that.
        class Odd(Framed):
            status = 429
            headers = {"Content-Type": "application/json"}
        for value in ("1" * 101, "1\r\n2", "\u00b2", "1\x00", "1\x7f", "\u00e9"):
            Odd.headers = {"Content-Type": "application/json", "Retry-After": value}
            self.assertEqual(live(Capture(b"{}", Odd)).send(azure.read(ID))["headers"], {"content-type": "application/json"}, value)
        # A byte that is not ASCII, which http.client reads as Latin-1, is a printable letter, kept by neither; DEL is ASCII
        # and not printable. A header whose name holds a control character is none of the two.
        for raw in (b"\xe9", b"1\x7f"):
            Odd.headers = azure.http.client.parse_headers(io.BytesIO(
                b"Content-Type: application/json\r\nRetry-After: %s\r\nContent-Length: 2\r\n\r\n" % raw))
            self.assertEqual(live(Capture(b"{}", Odd)).send(azure.read(ID))["headers"], {"content-type": "application/json"}, raw)
        for name in ("Retry-After\x01", "Retry-\x00After", "Retry-After\x7f"):
            Odd.headers = {"Content-Type": "application/json", name: "7"}
            self.assertEqual(live(Capture(b"{}", Odd)).send(azure.read(ID))["headers"], {"content-type": "application/json"}, name)
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
