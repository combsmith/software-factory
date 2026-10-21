"""The one transport: every read and write the Factory makes on GitHub goes through `send`, and nothing else in this
repo reaches the network (tools/check_repo.py). A request is `request(method, path, accept, body)`; an answer is
`{status, headers, body}`, a trial fixture's exchange as `trials/` records one, so the same port code runs on a live
answer and on a recorded one.

`Live` sends HTTPS to api.github.com alone: it follows no redirect, uses no proxy, takes its token from its caller and
never from the environment, sets a timeout on every request, bounds every answer, and keeps no body anywhere but in the
answer it returns. A body that is not JSON is text decoded without loss, so its bytes are what any hash is taken over. `Replay`
answers from a fixture's exchanges, each at most once, matched by method, path, Accept and GraphQL query, and refuses
anything the fixture does not hold: it never answers with an empty default (L-51).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

HOST = "api.github.com"
JSON = "application/vnd.github+json"
DIFF = "application/vnd.github.diff"
VERSION = "2022-11-28"
TIMEOUT = 20      # seconds, for each request
LARGEST = 64 * 1024 * 1024      # bytes an answer may hold; one larger is refused, never cut short silently
CHUNK = 1024 * 1024             # bytes read at a time, so the bound costs no more memory than the answer


class Unanswered(Exception):
    """A request the transport will not answer: one off GitHub's API, or one a fixture does not hold."""


def request(method: str, path: str, accept: str = JSON, body=None) -> dict:
    """A request by its method and its path from the API's root, with its query, its Accept and a JSON body or none."""
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        raise Unanswered("a request needs an HTTP method, not %r" % (method,))
    parts = urllib.parse.urlsplit(path)
    if parts.scheme or parts.netloc or not path.startswith("/") or path.startswith("//") or "\\" in path:
        raise Unanswered("a path is from the API's root, on %s alone: %r" % (HOST, path))
    return {"method": method, "path": path, "accept": accept, "body": body}


def _answer(status: int, headers, raw: bytes) -> dict:
    kept = {k.lower(): v for k, v in headers.items()}
    if kept.get("content-type", "").split(";")[0].strip().endswith("json"):
        try:
            text = raw.decode("utf-8")
            return {"status": status, "headers": kept, "body": json.loads(text) if text else None}
        except ValueError:
            pass
    # surrogateescape is lossless: text.encode("utf-8", "surrogateescape") gives back the bytes GitHub sent.
    return {"status": status, "headers": kept, "body": raw.decode("utf-8", errors="surrogateescape")}


def raw(text: str) -> bytes:
    """The bytes a text body was sent as, the same for a live answer and for a fixture's."""
    return text.encode("utf-8", errors="surrogateescape")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if fp is not None:
            fp.close()
        raise Unanswered("GitHub answered %d, a redirect; the transport follows none" % code)


class Live:
    """HTTPS to api.github.com, with the token its caller gives it."""

    def __init__(self, token: str, timeout: int = TIMEOUT):
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise Unanswered("a token is one word, given by the caller")
        self._token = token
        self._timeout = timeout
        # No proxy from the environment, and no redirect: the request goes to the host named, or nowhere.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect,
                                                  urllib.request.HTTPSHandler)

    def send(self, req: dict) -> dict:
        req = request(req["method"], req["path"], req["accept"], req["body"])
        url = "https://%s%s" % (HOST, req["path"])
        if urllib.parse.urlsplit(url).netloc != HOST:
            raise Unanswered("a request goes to %s alone" % HOST)
        data = None if req["body"] is None else json.dumps(req["body"]).encode()
        headers = {"Accept": req["accept"], "Authorization": "Bearer " + self._token,
                   "X-GitHub-Api-Version": VERSION, "User-Agent": "software-factory"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        sent = urllib.request.Request(url, data=data, headers=headers, method=req["method"])
        try:
            with self.opener.open(sent, timeout=self._timeout) as got:
                return _answer(got.status, got.headers, _bounded(got))
        except urllib.error.HTTPError as err:
            with err:
                return _answer(err.code, err.headers, _bounded(err))
        except (urllib.error.URLError, OSError, ValueError) as err:
            raise Unanswered("GitHub could not be reached: %s" % type(err).__name__) from None


def _bounded(stream) -> bytes:
    parts, size = [], 0
    while True:
        part = stream.read(CHUNK)
        if not part:
            return b"".join(parts)
        size += len(part)
        if size > LARGEST:
            raise Unanswered("an answer over %d bytes; it is refused, not cut short" % LARGEST)
        parts.append(part)


def _recorded(exchange: dict):
    """The method, path, Accept and query a fixture's exchange was asked with, or None for one no transport sends."""
    asked = exchange.get("request") or {}
    if asked.get("via") not in ("rest", "graphql"):
        return None
    words = str(asked.get("call", "")).split()
    if len(words) < 2:
        return None
    path = words[1].rstrip(",")
    headers = {str(k).lower(): v for k, v in (asked.get("headers") or {}).items()}
    body = asked.get("body")
    query = body.get("query") if isinstance(body, dict) else None
    return words[0], path, headers.get("accept", JSON), query


class Replay:
    """Answers from a fixture's exchanges, each once, in the order they were recorded."""

    def __init__(self, exchanges: list):
        self._left = [(_recorded(e), e["response"]) for e in exchanges if _recorded(e) is not None]

    def send(self, req: dict) -> dict:
        query = req["body"].get("query") if isinstance(req["body"], dict) else None
        want = (req["method"], req["path"], req["accept"], query)
        for i, (asked, answer) in enumerate(self._left):
            if asked == want:
                del self._left[i]
                return {"status": answer["status"], "headers": dict(answer.get("headers") or {}),
                        "body": answer.get("body")}
        raise Unanswered("the fixture holds no answer to %s %s (%s)" % want[:3])
