"""The second transport: what an advisory Lens's reader is asked through, and nothing else (decision 0224). With
`adapters/github.py` it is one of the two files in this repo that reach the network (tools/check_repo.py). A request is
one of four acts, built by `create`, `read`, `cancel` or `chat`, and names no method and no path: the transport alone
writes those, so a caller cannot ask for another, and no request of this file's is one `adapters/github.py` would send.
An answer is `{status, headers, body}`.

`Live` sends HTTPS to the one host its caller names, which is the configuration's, held to the forms Azure serves a
model's API under, on its own port. It sends the paths of two APIs alone: Responses, to create a response, read it and
cancel it, and Chat Completions, to create one. It takes its key from its caller and never from the environment, and
sends it under Azure's own header to that host and no other: it follows no redirect and uses no proxy. Every request
has its caller's limit in seconds, every answer is bounded and refused past the bound, never cut short, and of an
answer's headers it keeps the two a caller reads. No refusal names the host, the address or the key, and none is chained
to an error of urllib's, which holds the address asked. Nothing is installed: the standard library does the rest.

"""
from __future__ import annotations

import http.client
import json
import re
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
LONGEST = 1200                  # seconds a caller may give one request: the advise step's own limit (decision 0224)
REDIRECTS = {301, 302, 303, 307, 308}
KEPT = ("content-type", "retry-after")      # the headers of an answer a caller reads; no other is kept


class Unanswered(Exception):
    """A request the transport will not send, or one Azure did not answer whole."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if fp is not None:
            fp.close()
        raise Unanswered("Azure answered %d, a redirect; the transport follows none" % code)

    def http_error_302(self, req, fp, code, msg, headers):
        if fp is not None:
            fp.close()
        raise Unanswered("Azure answered %d, a redirect; the transport follows none" % code)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


ACTS = ("create", "read", "cancel", "chat")


def request(act: str, ident, body) -> dict:
    """One of the four requests, or a refusal: `create` or `chat` with a JSON object that is not empty and no id, or
    `read` or `cancel` with a response's id and no body."""
    made = act in ("create", "chat") and ident is None and isinstance(body, dict) and bool(body)
    named = act in ("read", "cancel") and isinstance(ident, str) and IDENT.fullmatch(ident) is not None and body is None
    if not isinstance(act, str) or not (made or named):
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


def _answer(status: int, headers, raw: bytes) -> dict:
    kept = {k.lower(): v for k, v in headers.items() if k.lower() in KEPT}
    text = raw.decode("utf-8", errors="replace")
    if kept.get("content-type", "").split(";")[0].strip().endswith("json"):
        try:
            return {"status": status, "headers": kept, "body": json.loads(text) if text else None}
        except ValueError:
            pass
    return {"status": status, "headers": kept, "body": text}


def _bounded(stream) -> bytes:
    parts, size = [], 0
    while True:
        part = stream.read(min(CHUNK, LARGEST + 1))
        if not part:
            return b"".join(parts)
        size += len(part)
        if size > LARGEST:
            raise Unanswered("an answer over %d bytes; it is refused, not cut short" % LARGEST)
        parts.append(part)


class Live:
    """HTTPS to the one host named, with the key and the seconds its caller gives it."""

    __slots__ = ("host", "opener", "_key", "_seconds")

    def __init__(self, host: str, key: str, seconds: int):
        if not isinstance(host, str) or not HOSTS.fullmatch(host):
            raise Unanswered("the host is one of Azure's, for a model's API, as the configuration names it")
        if not isinstance(key, str) or not key or not key.isascii() or any(not c.isprintable() or c == " " for c in key):
            raise Unanswered("a key is one word, given by the caller")
        if type(seconds) is not int or not 1 <= seconds <= LONGEST:
            raise Unanswered("a request's limit is a whole number of seconds, from 1 to %d" % LONGEST)
        self.host, self._key, self._seconds = host, key, seconds
        # No proxy from the environment, and no redirect: the request and its key go to the host named, or nowhere.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect,
                                                  urllib.request.HTTPSHandler)

    def __repr__(self) -> str:
        return "<azure.Live>"

    def send(self, req: dict) -> dict:
        verb, path, body = wire(req)
        headers = {"api-key": self._key, "Accept": "application/json", "User-Agent": "software-factory"}
        data = None
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        sent = urllib.request.Request("https://%s%s" % (self.host, path), data=data, headers=headers, method=verb)
        # A refusal is raised only once every handler has ended, so that it is chained to no error of urllib's.
        try:
            try:
                with self.opener.open(sent, timeout=self._seconds) as got:
                    return _answer(got.status, got.headers, _bounded(got))
            except urllib.error.HTTPError as err:
                with err:
                    if err.code in REDIRECTS:
                        raise Unanswered("Azure answered %d, a redirect; the transport follows none" % err.code)
                    return _answer(err.code, err.headers, _bounded(err))
        except Unanswered as err:
            refused = str(err)
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as err:
            refused = "Azure could not be reached, or its answer was cut short: %s" % type(err).__name__
        raise Unanswered(refused)

