"""The one transport: every read and write the Factory makes on GitHub goes through `send`, and nothing else in this
repo reaches the network (tools/check_repo.py). A request is `request(method, path, accept, body)`; an answer is
`{status, headers, body}`, a trial fixture's exchange as `trials/` records one, so the same port code runs on a live
answer and on a recorded one.

`Live` sends HTTPS to api.github.com alone: it follows no redirect, uses no proxy, takes its token from its caller and
never from the environment, sets a timeout on every request, bounds every answer, and keeps no body anywhere but in the
answer it returns. One redirect is followed, and one only (decision 0045, the Maintainer's ruling on #192): an
artifact's download, `download(path)`, from that endpoint alone, to GitHub's artifact storage alone, over HTTPS, with
no token sent there and its body bounded far tighter: 64 KiB, or 1 MiB for a pass record, the one artifact its reader
asks the wider bound for (decision 0045's row of #196). The address it is sent to carries a signature, and is never put
in an error or kept. A body that is not JSON is text decoded without loss, so its bytes are what any hash is taken over. `Replay`
answers from a fixture's exchanges in the order they were recorded, each once, matched by method, path, Accept and the
whole body, a GraphQL query's variables among it, and refuses anything else: it never answers with an empty default
(L-51). It refuses a redirect as `Live` does, and follows an artifact's download as `Live` does, to the storage exchange
recorded next.
"""
from __future__ import annotations

import http.client
import json
import re
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
# The one redirect followed: an artifact's download, to the storage GitHub keeps Actions' artifacts in, its v4 store.
ARTIFACT = re.compile(r"/repos/[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}/actions/artifacts/[1-9][0-9]{0,18}/zip")
# GitHub names twenty such accounts, sa0 to sa19, among the hosts a runner must reach; no other is GitHub's.
STORAGE = re.compile(r"productionresultssa(?:[0-9]|1[0-9])\.blob\.core\.windows\.net")
# The path an artifact's storage serves it under (the Maintainer's answer of 2026-10-21 on #192).
STORED_UNDER = "/actions-results/"
STORED = 64 * 1024              # bytes an artifact's download may hold: an outcome is a few bytes, zipped
PASSED = 1024 * 1024            # bytes a pass record's download may hold, zipped: its facts for every open item
BOUNDS = (STORED, PASSED)       # the only bounds a download is asked under
REDIRECTS = {301, 302, 303, 307, 308}


class Unanswered(Exception):
    """A request the transport will not answer: one off GitHub's API, or one a fixture does not hold."""


class Redirected(Unanswered):
    """A redirect GitHub answered, raised by the opener and caught at once by `Live._open`, which keeps only the
    address: no error the transport raises holds the address, or is chained to one that does."""

    def __init__(self, code: int, location):
        super().__init__("GitHub answered %d, a redirect; the transport follows none" % code)
        self.location = location


# The only headers a caller may add: a read of the run records keeps no cache (decision 0036, ruling 4).
EXTRA = {"Cache-Control", "If-None-Match"}


def request(method: str, path: str, accept: str = JSON, body=None, headers=None, follow: bool = False,
            bound=None) -> dict:
    """A request by its method and its path from the API's root, with its query, its Accept, a JSON body or none, and
    at most the headers `EXTRA` names, each one line. `follow` is an artifact's download alone, and `bound` the bytes it
    may hold, one of `BOUNDS`, `STORED` unless asked: see `download`."""
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        raise Unanswered("a request needs an HTTP method, not %r" % (method,))
    parts = urllib.parse.urlsplit(path)
    if parts.scheme or parts.netloc or not path.startswith("/") or path.startswith("//") or "\\" in path:
        raise Unanswered("a path is from the API's root, on %s alone: %r" % (HOST, path))
    extra = dict(headers or {})
    for name, value in extra.items():
        if name not in EXTRA or not isinstance(value, str) or any(c in value for c in "\r\n\0"):
            raise Unanswered("a request may add %s alone, each one line" % ", ".join(sorted(EXTRA)))
    built = {"method": method, "path": path, "accept": accept, "body": body, "headers": extra}
    if follow is not False:
        if follow is not True or method != "GET" or body is not None or extra or not ARTIFACT.fullmatch(path):
            raise Unanswered("only an artifact's download follows its redirect, a GET of %s alone" % ARTIFACT.pattern)
        bound = STORED if bound is None else bound
        if type(bound) is not int or bound not in BOUNDS:
            raise Unanswered("an artifact's download is bounded at %s bytes alone" % " or ".join(map(str, BOUNDS)))
        built["follow"], built["bound"] = True, bound
    elif bound is not None:
        raise Unanswered("only an artifact's download is asked under a bound of its own")
    return built


def download(path: str, bound: int = STORED) -> dict:
    """The request for an artifact's zip, whose one redirect the transport follows to `storage`, its answers bounded at
    `bound` bytes: `STORED`, or `PASSED` for a pass record's alone."""
    return request("GET", path, follow=True, bound=bound)


def storage(url) -> str:
    """The address an artifact's download redirects to, if it is GitHub's artifact storage over HTTPS on its own port,
    under `/actions-results/`, with no segment that climbs out of it, plain or percent-encoded; refused otherwise. The
    address is never named in the refusal: it carries a signature."""
    parts = None
    if isinstance(url, str) and url.isascii():
        try:
            parts = urllib.parse.urlsplit(url)
        except ValueError:
            pass    # a host GitHub would not give; refused below, outside the handler, so no error names it
    # The whole netloc is the host, so a port, a user or a host's case GitHub would not give is refused with it.
    if parts is None or parts.scheme != "https" or not STORAGE.fullmatch(parts.netloc) or any(c in url for c in " \t\r\n\0\\"):
        raise Unanswered("an artifact's download redirects off GitHub's artifact storage, or not over HTTPS")
    segments = parts.path.split("/")
    if not parts.path.startswith(STORED_UNDER) or "%" in parts.path or any(segment in (".", "..") for segment in segments):
        raise Unanswered("an artifact's download redirects outside %s" % STORED_UNDER)
    return url


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


def _moved(asked: str, location):
    """The address a redirect names, read against the address asked, as the live transport and the replay both read
    it; None where it cannot be read. urllib's own reading, which quotes and joins it first, is never used."""
    try:
        return urllib.parse.urljoin(asked, location) if isinstance(location, str) else None
    except ValueError:
        return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if fp is not None:
            fp.close()
        raise Redirected(code, newurl)

    def http_error_302(self, req, fp, code, msg, headers):
        if fp is not None:
            fp.close()
        raise Redirected(code, _moved(req.full_url, headers.get("Location")))

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


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
        req = request(req["method"], req["path"], req["accept"], req["body"], req.get("headers"),
                      req.get("follow", False), req.get("bound"))
        url = "https://%s%s" % (HOST, req["path"])
        if urllib.parse.urlsplit(url).netloc != HOST:
            raise Unanswered("a request goes to %s alone" % HOST)
        data = None if req["body"] is None else json.dumps(req["body"]).encode()
        headers = {"Accept": req["accept"], "Authorization": "Bearer " + self._token,
                   "X-GitHub-Api-Version": VERSION, "User-Agent": "software-factory"}
        headers.update(req["headers"])
        if data is not None:
            headers["Content-Type"] = "application/json"
        sent = urllib.request.Request(url, data=data, headers=headers, method=req["method"])
        answer, moved = self._open(sent, req["bound"] if req.get("follow") else LARGEST)
        if answer is not None:
            return answer
        if not req.get("follow"):
            raise Unanswered("GitHub answered a redirect; the transport follows none")
        # The artifact at the storage address: no token, no header of the API's, no redirect, its bound at most.
        fetched = urllib.request.Request(storage(moved), headers={"User-Agent": "software-factory"}, method="GET")
        answer, moved = self._open(fetched, req["bound"])
        if answer is None:
            raise Unanswered("the artifact's storage answered a redirect; the transport follows none")
        return answer

    def _open(self, sent, largest: int) -> tuple:
        """`(answer, None)`, or `(None, the address redirected to)`; a connection that fails, or an answer cut short
        while it is read, a body or an error's, is refused. A 308, which Python before 3.11 hands on as an error, is a
        redirect too, and its address is never kept in an answer. A refusal is raised only once every handler has
        ended, so that it is chained to no error of urllib's, whose `filename` is the address asked."""
        try:
            try:
                with self.opener.open(sent, timeout=self._timeout) as got:
                    return _answer(got.status, got.headers, _bounded(got, largest)), None
            except urllib.error.HTTPError as err:
                with err:
                    if err.code in REDIRECTS:
                        return None, _moved(sent.full_url, err.headers.get("Location"))
                    return _answer(err.code, err.headers, _bounded(err, largest)), None
            except Redirected as err:
                return None, err.location
        except Unanswered as err:
            refused = str(err)
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as err:
            refused = "GitHub could not be reached, or its answer was cut short: %s" % type(err).__name__
        raise Unanswered(refused)


def _bounded(stream, largest=None) -> bytes:
    largest = LARGEST if largest is None else largest
    parts, size = [], 0
    while True:
        part = stream.read(min(CHUNK, largest + 1))
        if not part:
            return b"".join(parts)
        size += len(part)
        if size > largest:
            raise Unanswered("an answer over %d bytes; it is refused, not cut short" % largest)
        parts.append(part)


def _body(body) -> str:
    return json.dumps(body, sort_keys=True)


def _recorded(exchange: dict):
    """The method, path, Accept and body a fixture's exchange was asked with, or None for one no transport sends."""
    asked = exchange.get("request") or {}
    if asked.get("via") not in ("rest", "graphql", "storage"):
        return None
    words = str(asked.get("call", "")).split()
    if len(words) < 2:
        return None
    path = words[1].rstrip(",")
    if asked["via"] == "storage":
        return words[0], path, None, _body(None)
    headers = {str(k).lower(): v for k, v in (asked.get("headers") or {}).items()}
    return words[0], path, headers.get("accept", JSON), _body(asked.get("body"))


class Replay:
    """Answers from a fixture's exchanges, each once, in the order they were recorded: a request asked out of that
    order, or one the next exchange does not hold, is refused. A redirect is refused, as `Live` refuses it, but for an
    artifact's download: that is answered by the storage exchange recorded next, if it is of the address redirected
    to."""

    def __init__(self, exchanges: list):
        self._left = [(_recorded(e), e["response"]) for e in exchanges if _recorded(e) is not None]

    def send(self, req: dict) -> dict:
        req = request(req["method"], req["path"], req["accept"], req["body"], req.get("headers"),
                      req.get("follow", False), req.get("bound"))
        want = (req["method"], req["path"], req["accept"], _body(req["body"]))
        if self._left and self._left[0][0] == want:
            asked, answer = self._left.pop(0)
            if answer["status"] in REDIRECTS:
                if not req.get("follow"):
                    raise Unanswered("GitHub answered a redirect; the transport follows none")
                location = {str(k).lower(): v for k, v in (answer.get("headers") or {}).items()}.get("location")
                stored = ("GET", storage(_moved("https://%s%s" % (HOST, req["path"]), location)), None, _body(None))
                if not self._left or self._left[0][0] != stored:
                    raise Unanswered("the fixture holds no answer, next, from the artifact's storage")
                asked, answer = self._left.pop(0)
                if answer["status"] in REDIRECTS:
                    raise Unanswered("the artifact's storage answered a redirect; the transport follows none")
            if req.get("follow") and isinstance(answer.get("body"), str) and len(raw(answer["body"])) > req["bound"]:
                raise Unanswered("an answer over %d bytes; it is refused, not cut short" % req["bound"])
            return {"status": answer["status"], "headers": dict(answer.get("headers") or {}),
                    "body": answer.get("body")}
        raise Unanswered("the fixture holds no answer, next, to %s %s (%s)" % want[:3])
