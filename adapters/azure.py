"""The second transport: what an advisory Lens's reader is asked through, and nothing else (decision 0224). With
`adapters/github.py` it is one of the two files in this repo that reach the network, and it may not name GitHub's host
(tools/check_repo.py). A request is one of four acts, built by `create`, `read`, `cancel` or `chat`, and names no
method and no path: the transport alone writes those, so a caller cannot ask for another, and no request of this
file's is one `adapters/github.py` would send. An answer is `{status, headers, body}`.

`Live` sends HTTPS to the one host its caller names, which is the configuration's, held to the forms Azure serves a
model's API under, on its own port. It sends the paths of two APIs alone: Responses, to create a response, read it and
cancel it, and Chat Completions, to create one. It takes its key from its caller and never from the environment, and
sends it under Azure's own header to that host and no other: it follows no redirect, refused before its Location is
read, and uses no proxy. Each wait on
the connection has its caller's limit in seconds, which bounds neither the finding of the host's address nor an answer
that comes slowly: the whole is bounded by the limit of the step that calls. Every answer is bounded in size and
refused past the bound or of other than the length it said, counted as read, never cut short; no read of the
connection under it takes more than the bound and a frame's allowance. An answer is read only when it is framed as
Azure frames each of its own, chunked alone, each chunk's size of hex digits and its data ended by CRLF, or with one
length of at most ten digits, no larger than the bound, under headers read whole to their blank line, all bounded from
the first byte. A body is not sent whose object names a member by other than text, or holds a kind of dict, list or
tuple, or one twice. An answer not of JSON's type or its suffix is text, never read as JSON. One that
is not UTF-8 is text and never read as JSON, and so is one that holds a whole number of more digits than any count, NaN,
an infinity or a number too large for a float. Of an answer's headers it keeps the two a caller reads, each by its last
value and only when that is short, printable ASCII. It verifies the host's certificate by a context of
its own, so a default changed elsewhere in the process cannot turn that off. No refusal names the host, the address or
the key, and each is raised from nothing, chained to no error of urllib's, which holds the address asked. Nothing is
installed: the standard library does the rest.
"""
from __future__ import annotations

import http.client
import json
import re
import ssl
import urllib.error
import urllib.request

# The hosts Azure serves a model's API under: one label, the resource's name, below one of three names of Azure's own.
# The whole of what the configuration gives must be this, so a port, a user, a path or a host that only ends so is none.
HOSTS = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
                   r"\.(?:openai\.azure\.com|services\.ai\.azure\.com|cognitiveservices\.azure\.com)")
RESPONSES = "/openai/v1/responses"
CHAT = "/openai/v1/chat/completions"
# A response's id as a path's one segment: no slash, dot, percent or query, so it names no other path.
IDENT = re.compile(r"[A-Za-z0-9_-]{1,200}")
LARGEST = 4 * 1024 * 1024       # bytes an answer may hold; one larger is refused, never cut short silently
WALK = 100000           # the most values a body is walked for, each counted wherever it is held
CHUNK = 1024 * 1024             # bytes read at a time, so the bound costs no more memory than the answer
LONGEST = 1200                  # seconds a caller may give one wait: the advise step's own limit (decision 0224)
REDIRECTS = {301, 302, 303, 307, 308}
KEPT = ("content-type", "retry-after")      # the headers of an answer a caller reads; no other is kept
HEADER = 100                    # characters a kept header may hold: one longer, or not printable ASCII, is not kept
LENGTH = re.compile(r"[0-9]{1,10}")     # the one length an answer may say: digits alone, no sign, space or other numeral
FRAMING = 64 * 1024             # bytes past the bound a connection may give an answer for its chunks' frame
DIGITS = 64                     # a whole number of this many digits no count needs: Python 3.9 reads one of any length
# The types of an answer read as JSON: JSON's own, or one of its structured suffix, and no type that only ends so.
JSON = re.compile(r"application/json|[a-z0-9][a-z0-9.!#$&^_+-]*/[a-z0-9][a-z0-9.!#$&^_+-]*\+json")
TOKEN = rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
# A chunk's size line: hex digits alone, no sign or prefix, and each extension a name, or a name and a value, of tokens.
SIZE = re.compile(rb"[0-9A-Fa-f]{1,8}(?:;%s(?:=%s)?)*\r\n" % (TOKEN, TOKEN))
TRAILER = re.compile(rb"(?:%s:[^\r\n]*)?\r\n" % TOKEN)     # a trailer's line: a name, a colon and a value, or its end


class Unanswered(Exception):
    """A request the transport will not send, or one Azure did not answer whole."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # urllib parses the Location of a redirect before it asks `redirect_request`, so that one malformed raises another
    # error and leaves the answer open: each redirect is refused here, its answer closed and no header of it read.
    def http_error_302(self, req, fp, code, msg, headers):
        if fp is not None:
            fp.close()
        raise Unanswered("Azure answered %d, a redirect; the transport follows none" % code)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return self.http_error_302(req, fp, code, msg, headers)


def request(act: str, ident, body) -> dict:
    """One of the four requests, or a refusal: `create` or `chat` with a JSON object that is not empty and no id, or
    `read` or `cancel` with a response's id and no body."""
    # The act's type is held before it is compared, and the body is a dict itself, never a kind of one that says
    # otherwise of its own length or truth.
    made = type(act) is str and act in ("create", "chat") and ident is None and type(body) is dict and len(body) > 0
    named = type(act) is str and act in ("read", "cancel") and type(ident) is str and IDENT.fullmatch(ident) is not None \
        and body is None
    if not (made or named):
        raise Unanswered("the transport sends a response's create, read and cancel and a chat completion's create alone")
    return {"act": act, "id": ident, "body": body}


def create(body: dict) -> dict:
    """The request that creates a response (the Responses API)."""
    return request("create", None, body)


def read(ident: str) -> dict:
    """The request that reads a response created before, by its id."""
    return request("read", ident, None)


def cancel(ident: str) -> dict:
    """The request that cancels a response still running, so that it is not left to run on and be billed."""
    return request("cancel", ident, None)


def chat(body: dict) -> dict:
    """The request that creates a chat completion (the Chat Completions API)."""
    return request("chat", None, body)


def wire(req) -> tuple:
    """`(verb, path, body)` as a request is sent: the only verbs and paths this transport writes. A request not built
    as `request` builds one is refused, whoever made it."""
    if not isinstance(req, dict) or set(req) != {"act", "id", "body"}:
        raise Unanswered("a request is its act, its id and its body, as this file builds one")
    req = request(req["act"], req["id"], req["body"])
    if req["act"] == "create":
        return "POST", RESPONSES, req["body"]
    if req["act"] == "chat":
        return "POST", CHAT, req["body"]
    if req["act"] == "read":
        return "GET", "%s/%s" % (RESPONSES, req["id"]), None
    return "POST", "%s/%s/cancel" % (RESPONSES, req["id"]), {}


def _framed(headers):
    """The length an answer said, or None where it is chunked alone, or a refusal before its body is read. Two frames,
    two lengths, or one not of digits alone, can be read otherwise by another reader; http.client may drop a length of
    thousands of digits and read to the end; and an answer of neither frame ends only where its connection does. A
    line of the headers http.client could not read, as one with no colon, hides those after it, a second length too."""
    if getattr(headers, "defects", None):
        raise Unanswered("an answer whose headers could not all be read; it is refused, not read")
    lengths = [v for k, v in headers.items() if k.lower() == "content-length"]
    if len(lengths) > 1 or (lengths and not LENGTH.fullmatch(lengths[0])):
        raise Unanswered("an answer that says more than one length, or one not of digits alone; it is refused, not read")
    coded = [v.lower() for k, v in headers.items() if k.lower() == "transfer-encoding"]
    if (lengths and coded) or (not lengths and coded != ["chunked"]):
        raise Unanswered("an answer of both frames, or not chunked alone nor of a length; it is refused, not read")
    if lengths and int(lengths[0]) > LARGEST:
        raise Unanswered("an answer that says a length over %d bytes; it is refused, not read" % LARGEST)
    return int(lengths[0]) if lengths else None


class _Capped:
    """The connection under an answer, of which no read takes more than the bound and a frame's allowance. Of one
    chunked, each chunk's size is hex digits alone, which http.client would read with a sign, a prefix or a space, and
    each line after the last chunk ends as a line does, so that one cut short there is refused, not taken as whole."""

    __slots__ = ("_fp", "_left", "_chunked", "_trailer", "_due", "_end", "_last")

    def __init__(self, fp):
        self._fp, self._left, self._chunked, self._trailer = fp, LARGEST + FRAMING, False, False
        self._due, self._end, self._last = 0, b"", b""

    def _most(self, asked) -> int:
        most = self._left if asked is None or asked < 0 else min(asked, self._left)
        if most == 0 and asked != 0:
            raise Unanswered("an answer over %d bytes with its frame; it is refused, not cut short" % (LARGEST + FRAMING))
        return most

    def _took(self, got):
        self._left -= len(got)
        if self._chunked:
            # Of a chunk, its data, then the CRLF that ends it, and nothing else.
            data = min(len(got), self._due)
            rest = bytes(got[data:])
            if not self._end.startswith(rest):
                raise Unanswered("an answer whose chunks are not framed as Azure frames them; it is refused, not kept")
            self._due, self._end = self._due - data, self._end[len(rest):]
        return got

    def read(self, size=-1):
        return self._took(self._fp.read(self._most(size)))

    def readline(self, size=-1):
        self._last = line = self._fp.readline(self._most(size))
        self._left -= len(line)
        if self._chunked:
            if not (TRAILER if self._trailer else SIZE).fullmatch(line):
                raise Unanswered("an answer whose chunks are not framed as Azure frames them; it is refused, not kept")
            if not self._trailer:
                size = int(line.split(b";")[0], 16)
                self._trailer, self._due, self._end = size == 0, size, b"\r\n" if size else b""
        return line

    def readinto(self, b):
        view = memoryview(b).cast("B")
        got = self._fp.readinto(view[:self._most(len(view))]) or 0
        self._took(view[:got])
        return got

    def flush(self):
        self._fp.flush()

    def close(self):
        self._fp.close()


class _Response(http.client.HTTPResponse):
    """An answer capped from its first byte, interim answers too, which http.client passes over for as long as they
    come; its headers end with their blank line, not the connection's end."""

    def __init__(self, sock, *args, **kwargs):
        super().__init__(sock, *args, **kwargs)
        self.fp = _Capped(self.fp)

    def begin(self):
        super().begin()
        if self.fp._last != b"\r\n":
            raise Unanswered("an answer whose headers end before the line that closes them; it is refused, not read")
        self.fp._chunked = self.chunked


class _Connection(http.client.HTTPSConnection):
    response_class = _Response


class _Https(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_Connection, req, context=self._context)


def _capped(got):
    """What an answer is read through: http.client's only if capped from its first byte, anything else capped whole."""
    held = got if isinstance(got, http.client.HTTPResponse) else getattr(got, "fp", None)
    if not isinstance(held, http.client.HTTPResponse):
        return _Capped(got)
    if not isinstance(held.fp, _Capped):
        raise Unanswered("an answer not read through the transport's own response; it is refused, not read")
    return got


def _whole(digits: str) -> int:
    if len(digits.lstrip("-")) >= DIGITS:
        raise ValueError("a whole number of more digits than a count has")
    return int(digits)


def _finite(constant: str):
    raise ValueError("NaN and the infinities are no numbers of JSON's")


def _real(digits: str) -> float:
    value = float(digits)
    if abs(value) == float("inf"):
        raise ValueError("a number too large for a float reads as an infinity, which is no number of JSON's")
    return value


def _answer(status: int, headers, raw: bytes) -> dict:
    # Of a kept header given twice, the last is kept, or none where the last is refused. A type too long to keep is not
    # kept, and the body is then text, which is safe: a body is read as JSON only when its type says so.
    given = {k.lower(): v for k, v in headers.items() if k.lower() in KEPT}
    kept = {k: v for k, v in given.items() if len(v) <= HEADER and v.isascii() and v.isprintable()}
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"status": status, "headers": kept, "body": raw.decode("utf-8", errors="replace")}
    if JSON.fullmatch(kept.get("content-type", "").split(";")[0].strip().lower()):
        try:
            body = json.loads(text, parse_int=_whole, parse_float=_real, parse_constant=_finite) if text else None
            return {"status": status, "headers": kept, "body": body}
        except (ValueError, RecursionError):
            pass
    return {"status": status, "headers": kept, "body": text}


def _named(value, left):
    """Each object of a body names its members by text alone: JSON writes a key of another type as text, so that
    `{1: "a", "1": "b"}` would be sent as two members of one name, which readers read otherwise. None is a kind of dict,
    list or tuple, whose keys may say otherwise than its items. Every value is counted wherever it is held, and a body
    of more than WALK is not sent, so that one holding a container many times over, or itself, is refused in bounded
    time and never handed to JSON, which would write it out each time. A container held twice is no fault: CPython
    shares the empty tuple, and equal constant tuples, between places a body holds them."""
    left[0] -= 1
    if left[0] < 0:
        raise Unanswered("a body of more than %d values; it is not sent" % WALK)
    if isinstance(value, (dict, list, tuple)):
        if type(value) not in (dict, list, tuple):
            raise Unanswered("a body that holds a kind of dict, list or tuple; it is not sent")
        if type(value) is dict:
            if any(type(k) is not str for k in value):
                raise Unanswered("a body whose object names a member by other than text; it is not sent")
            value = value.values()
        for each in value:
            _named(each, left)


def _bounded(stream, length) -> bytes:
    parts, size = [], 0
    while True:
        part = stream.read(CHUNK)
        if not part:
            # The bytes read, counted here and never taken from the stream, which an error may not forward, against the
            # length the answer said, where it said one.
            if length is not None and size != length:
                raise Unanswered("an answer of other than the length it said; it is refused, not kept")
            return b"".join(parts)
        size += len(part)
        if size > LARGEST:
            raise Unanswered("an answer over %d bytes; it is refused, not cut short" % LARGEST)
        parts.append(part)


def _context() -> ssl.SSLContext:
    """Certificate and name verified, TLS 1.2 or later, and no session key logged, as the default context would to
    `SSLKEYLOGFILE`."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)      # CERT_REQUIRED and check_hostname, as a client's default
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    return context


class Live:
    """HTTPS to the one host named, with the key and the seconds its caller gives it."""

    __slots__ = ("opener", "_host", "_key", "_seconds")

    def __init__(self, host: str, key: str, seconds: int):
        if type(host) is not str or not HOSTS.fullmatch(host):
            raise Unanswered("the host is one of Azure's, for a model's API, as the configuration names it")
        if type(key) is not str or not key or not key.isascii() or any(not c.isprintable() or c == " " for c in key):
            raise Unanswered("a key is one word, given by the caller")
        if type(seconds) is not int or not 1 <= seconds <= LONGEST:
            raise Unanswered("a wait's limit is a whole number of seconds, from 1 to %d" % LONGEST)
        self._host, self._key, self._seconds = host, key, seconds
        # No proxy from the environment, and no redirect: the request and its key go to the host named, or nowhere. The
        # context is made here, so that a default context replaced elsewhere cannot send the key to a host unverified.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect,
                                                  _Https(context=_context()))

    def __repr__(self) -> str:
        return "<azure.Live>"

    def send(self, req: dict) -> dict:
        headers = {"api-key": self._key, "Accept": "application/json", "User-Agent": "software-factory"}
        try:
            verb, path, body = wire(req)
            data = None
            _named(body, [WALK])
            if body is not None:
                data, headers["Content-Type"] = json.dumps(body, allow_nan=False).encode(), "application/json"
            sent = urllib.request.Request("https://%s%s" % (self._host, path), data=data, headers=headers, method=verb)
            try:
                with self.opener.open(sent, timeout=self._seconds) as got:
                    said = _framed(got.headers)
                    return _answer(got.status, got.headers, _bounded(_capped(got), said))
            except urllib.error.HTTPError as err:
                with err:
                    if err.code in REDIRECTS:
                        raise Unanswered("Azure answered %d, a redirect; the transport follows none" % err.code)
                    said = _framed(err.headers)
                    return _answer(err.code, err.headers, _bounded(_capped(err), said))
        except Unanswered as err:
            refused = str(err)
        except (urllib.error.URLError, OSError, ValueError, TypeError, RecursionError,
                http.client.HTTPException) as err:
            refused = "Azure could not be reached, or its answer was cut short: %s" % type(err).__name__
        # Raised once every handler has ended, from nothing and with no context, so that no error that holds the key or
        # the address rides along as its context or its cause, nor one its caller was handling when it called.
        try:
            raise Unanswered(refused) from None
        except Unanswered as refusal:
            refusal.__context__ = None
            raise
