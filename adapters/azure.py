"""The second transport: what an advisory Lens's reader is asked through, and nothing else (decision 0224). With
`adapters/github.py` it is one of the two files in this repo that reach the network, and it may not name GitHub's host
(tools/check_repo.py). A request is one of four acts, built by `create`, `read`, `cancel` or `chat`, and names no
method and no path: the transport alone writes those, so a caller cannot ask for another, and no request of this
file's is one `adapters/github.py` would send. An answer is `{status, headers, body}`.

`Live` sends HTTPS to the one host its caller names, which is the configuration's, held to the forms Azure serves a
model's API under, on its own port. It sends the paths of two APIs alone: Responses, to create a response, read it and
cancel it, and Chat Completions, to create one. It takes its key from its caller and never from the environment, and
sends it under Azure's own header to that host and no other: it follows no redirect and uses no proxy. Each wait on
the connection has its caller's limit in seconds, which bounds neither the finding of the host's address nor an answer
that comes slowly: the whole is bounded by the limit of the step that calls. Every answer is bounded in size and
refused past the bound or short of the length it said, never cut short. An answer is read only when it is framed as
Azure frames each of its own, chunked or with one length of digits alone. One that is not UTF-8 is text and never read
as JSON, and one that holds a whole number of more digits than any count is text too. Of an answer's headers it keeps
the two a caller reads, each only when it is short, printable ASCII. It verifies the host's certificate by a context of
its own, so a default changed elsewhere in the process cannot turn that off. No refusal names the host, the address or
the key, and none is chained to an error of urllib's, which holds the address asked. Nothing is installed: the
standard library does the rest.
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
CHUNK = 1024 * 1024             # bytes read at a time, so the bound costs no more memory than the answer
LONGEST = 1200                  # seconds a caller may give one wait: the advise step's own limit (decision 0224)
REDIRECTS = {301, 302, 303, 307, 308}
KEPT = ("content-type", "retry-after")      # the headers of an answer a caller reads; no other is kept
HEADER = 100                    # characters a kept header may hold: one longer, or not printable ASCII, is not kept
LENGTH = re.compile(r"[0-9]+")  # the one length an answer may say: digits alone, with no sign, space or other numeral
DIGITS = 64                     # a whole number of this many digits no count needs: Python 3.9 reads one of any length


class Unanswered(Exception):
    """A request the transport will not send, or one Azure did not answer whole."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if fp is not None:
            fp.close()
        raise Unanswered("Azure answered %d, a redirect; the transport follows none" % code)


def request(act: str, ident, body) -> dict:
    """One of the four requests, or a refusal: `create` or `chat` with a JSON object that is not empty and no id, or
    `read` or `cancel` with a response's id and no body."""
    made = act in ("create", "chat") and ident is None and isinstance(body, dict) and bool(body)
    named = act in ("read", "cancel") and type(ident) is str and IDENT.fullmatch(ident) is not None and body is None
    if type(act) is not str or not (made or named):
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


def _framed(headers) -> None:
    """An answer framed as Azure frames each of its own, chunked or with one length of digits alone, or a refusal before
    its body is read. Two lengths, or one that is not digits alone, can be read otherwise by another reader, and an
    answer of neither frame ends only where its connection does, so that one cut short cannot be told from one whole."""
    lengths = [v for k, v in headers.items() if k.lower() == "content-length"]
    if len(lengths) > 1 or (lengths and not LENGTH.fullmatch(lengths[0])):
        raise Unanswered("an answer that says more than one length, or one not of digits alone; it is refused, not read")
    coded = [v.lower() for k, v in headers.items() if k.lower() == "transfer-encoding"]
    if not lengths and coded != ["chunked"]:
        raise Unanswered("an answer neither chunked nor of a length it said; it is refused, not read")


def _whole(digits: str) -> int:
    if len(digits) >= DIGITS:
        raise ValueError("a whole number of more digits than a count has")
    return int(digits)


def _answer(status: int, headers, raw: bytes) -> dict:
    # Of a kept header given twice, the last is kept. A type too long to keep is not kept, and the body is then text,
    # which is safe: a body is read as JSON only when its type says so.
    kept = {k.lower(): v for k, v in headers.items()
            if k.lower() in KEPT and len(v) <= HEADER and v.isascii() and v.isprintable()}
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"status": status, "headers": kept, "body": raw.decode("utf-8", errors="replace")}
    if kept.get("content-type", "").split(";")[0].strip().lower().endswith("json"):
        try:
            return {"status": status, "headers": kept, "body": json.loads(text, parse_int=_whole) if text else None}
        except (ValueError, RecursionError):
            pass
    return {"status": status, "headers": kept, "body": text}


def _bounded(stream) -> bytes:
    parts, size = [], 0
    while True:
        part = stream.read(CHUNK)
        if not part:
            # What is left of the length an answer said, where it said one: an answer that ended before it is cut short.
            if type(getattr(stream, "length", None)) is int and stream.length > 0:
                raise Unanswered("an answer shorter than the length it said; it is refused, not kept cut short")
            return b"".join(parts)
        size += len(part)
        if size > LARGEST:
            raise Unanswered("an answer over %d bytes; it is refused, not cut short" % LARGEST)
        parts.append(part)


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
                                                  urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def __repr__(self) -> str:
        return "<azure.Live>"

    def send(self, req: dict) -> dict:
        verb, path, body = wire(req)
        headers = {"api-key": self._key, "Accept": "application/json", "User-Agent": "software-factory"}
        # A refusal is raised only once every handler has ended, so that it is chained to no error of urllib's.
        try:
            data = None
            if body is not None:
                data, headers["Content-Type"] = json.dumps(body, allow_nan=False).encode(), "application/json"
            sent = urllib.request.Request("https://%s%s" % (self._host, path), data=data, headers=headers, method=verb)
            try:
                with self.opener.open(sent, timeout=self._seconds) as got:
                    _framed(got.headers)
                    return _answer(got.status, got.headers, _bounded(got))
            except urllib.error.HTTPError as err:
                with err:
                    if err.code in REDIRECTS:
                        raise Unanswered("Azure answered %d, a redirect; the transport follows none" % err.code)
                    _framed(err.headers)
                    return _answer(err.code, err.headers, _bounded(err))
        except Unanswered as err:
            refused = str(err)
        except (urllib.error.URLError, OSError, ValueError, TypeError, RecursionError,
                http.client.HTTPException) as err:
            refused = "Azure could not be reached, or its answer was cut short: %s" % type(err).__name__
        raise Unanswered(refused)
