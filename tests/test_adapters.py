"""The facts port's reads of a pull request, replayed from the trials' fixtures through the one transport.

Each test feeds a part of `adapters/pull.py` the exchanges a fixture recorded, through `adapters.github.Replay`, which
answers nothing a fixture does not hold, and holds the part to what the fixture shows GitHub said. Nothing here reaches
the network: the live transport is held by what it refuses before it sends anything.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import os
import pathlib
import unittest
import zipfile

from adapters import acceptance, artifacts, checks, effects, facts, github, heldout, items, passes, pull, records, threads, \
    timeline
from tests.support import pending

ROOT = pathlib.Path(__file__).resolve().parent.parent


def exchanges(name: str) -> list:
    return json.loads((ROOT / "trials" / ("%s.json" % name)).read_text())["exchanges"]


def body(name: str, at: int):
    return copy.deepcopy(exchanges(name)[at]["response"]["body"])


def replay(name: str, *at: int) -> github.Replay:
    found = exchanges(name)
    return github.Replay([found[i] for i in at])


MAINTAINER = 36422719      # the Maintainer's account id, as the fixtures record it


def person(ident: int = MAINTAINER) -> dict:
    return {"maintainer": {(ident, "User")}}


class Transport(unittest.TestCase):
    def test_a_replay_answers_only_what_the_fixture_holds_and_each_once(self):
        # L-51: the shared stub that answered empty for calls it did not know let real flags go untested.
        repo = json.loads((ROOT / "trials" / "P-29.base.json").read_text())["repo"]
        transport = replay("P-29.base", 9)
        branch = transport.send(github.request("GET", "/repos/%s/branches/main" % repo))
        self.assertEqual((branch["status"], branch["body"]["protected"]), (200, False))
        with self.assertRaises(github.Unanswered):
            transport.send(github.request("GET", "/repos/%s/branches/main" % repo))
        with self.assertRaises(github.Unanswered):
            replay("P-29.base", 9).send(github.request("GET", "/repos/%s/branches/other" % repo))
        # The Accept is part of the request: the diff and the pull request are two answers on one path.
        with self.assertRaises(github.Unanswered):
            replay("P-29.base", 2).send(github.request("GET", "/repos/%s/pulls/26" % repo))
        # A request asked out of the order recorded is refused, and so is one whose body differs in a variable.
        with self.assertRaises(github.Unanswered):
            replay("P-29.base", 1, 9).send(github.request("GET", "/repos/%s/branches/main" % repo))
        asked = exchanges("P-7")[10]["request"]
        path = asked["call"].split()[1]
        accept = asked["headers"]["accept"]
        self.assertEqual(replay("P-7", 10).send(github.request("POST", path, accept, asked["body"]))["status"], 200)
        other = copy.deepcopy(asked["body"])
        other["variables"]["n"] = 999
        with self.assertRaises(github.Unanswered):
            replay("P-7", 10).send(github.request("POST", path, accept, other))
        # A step taken by git or the command line is no request the transport sends, and is never an answer.
        self.assertEqual(github.Replay(exchanges("P-29.base")[:1])._left, [])

    def test_a_request_stays_on_githubs_api(self):
        for path in ("https://example.com/x", "//example.com/x", "example.com/x", "/x\\..\\y", "http://api.github.com/x"):
            with self.assertRaises(github.Unanswered, msg=path):
                github.request("GET", path)
        with self.assertRaises(github.Unanswered):
            github.request("TRACE", "/x")
        self.assertEqual(github.request("GET", "/repos/o/r")["accept"], github.JSON)
        # A caller may add the two headers a read of runs needs, each one line, and nothing else.
        self.assertEqual(github.request("GET", "/x", headers={"Cache-Control": "no-cache"})["headers"],
                         {"Cache-Control": "no-cache"})
        for headers in ({"Authorization": "Bearer x"}, {"Cache-Control": "no-cache\r\nX-Evil: 1"},
                        {"If-None-Match": None}):
            with self.assertRaises(github.Unanswered, msg=headers):
                github.request("GET", "/x", headers=headers)

    def test_only_an_artifacts_download_follows_its_redirect_and_only_to_githubs_storage(self):
        # Decision 0045, the Maintainer's ruling on #192: the one redirect is an artifact's download, to GitHub's
        # artifact storage alone, over HTTPS on its own port.
        self.assertTrue(github.download("/repos/o/r/actions/artifacts/9/zip")["follow"])
        for path in ("/repos/o/r/actions/artifacts/9", "/repos/o/r/actions/runs/9/logs", "/repos/o/r/zipball/main",
                     "/repos/o/r/actions/artifacts/09/zip", "/repos/o/r/actions/artifacts/9/zip?x=1"):
            with self.assertRaises(github.Unanswered, msg=path):
                github.download(path)
        for asked in ({"method": "POST"}, {"body": {}}, {"headers": {"Cache-Control": "no-cache"}}, {"follow": 1}):
            with self.assertRaises(github.Unanswered, msg=asked):
                github.request(**dict({"method": "GET", "path": "/repos/o/r/actions/artifacts/9/zip", "follow": True},
                                      **asked))
        self.assertNotIn("follow", github.request("GET", "/repos/o/r/actions/artifacts/9/zip"))
        self.assertEqual(github.storage(STORE), STORE)
        for url in ("http://productionresultssa7.blob.core.windows.net/actions-results/x", "https://evil.blob.core.windows.net/actions-results/x",
                    "https://productionresultssa7.blob.core.windows.net:8443/actions-results/x",
                    "https://u@productionresultssa7.blob.core.windows.net/actions-results/x",
                    "https://productionresultssa7.blob.core.windows.net.evil.com/actions-results/x",
                    "https://PRODUCTIONRESULTSSA7.blob.core.windows.net/actions-results/x", "https://pipelines.actions.githubusercontent.com/actions-results/x",
                    "https://productionresultssa7.blob.core.windows.net/actions-results/x\r\nHost: e", "https://api.github.com/actions-results/x",
                    "https://productionresultssa7.blob.core.windows.net\\@evil.com/actions-results/x", None, 7,
                    "https://productionresultssa20.blob.core.windows.net/actions-results/x", "https://productionresultssa07.blob.core.windows.net/actions-results/x",
                    # Under /actions-results/ alone, and no segment that climbs out, plain or percent-encoded.
                    "https://productionresultssa7.blob.core.windows.net/other/x?sig=1",
                    "https://productionresultssa7.blob.core.windows.net/actions-resultsx/x",
                    "https://productionresultssa7.blob.core.windows.net/actions-results",
                    "https://productionresultssa7.blob.core.windows.net/actions-results/../x",
                    "https://productionresultssa7.blob.core.windows.net/actions-results/./x",
                    "https://productionresultssa7.blob.core.windows.net/actions-results/%2e%2e/x",
                    "https://productionresultssa7.blob.core.windows.net/actions-results/a%2Fb"):
            with self.assertRaises(github.Unanswered, msg=url):
                github.storage(url)
        # The replay does as the live transport does: a redirect is refused to any other request, and followed for
        # the download only to the storage exchange recorded next, at the address redirected to.
        zipped = outcome_zip("{}")
        found = stored("o/r", 7, zipped)
        with self.assertRaises(github.Unanswered):
            github.Replay(found[1:]).send(github.request("GET", "/repos/o/r/actions/artifacts/9/zip"))
        self.assertEqual(github.raw(github.Replay(found[1:]).send(github.download("/repos/o/r/actions/artifacts/9/zip"))
                                    ["body"]), zipped)
        elsewhere = stored("o/r", 7, zipped, store="https://evil.example/x")
        with self.assertRaises(github.Unanswered):
            github.Replay(elsewhere[1:]).send(github.download("/repos/o/r/actions/artifacts/9/zip"))
        other = stored("o/r", 7, zipped)
        other[2]["request"]["call"] = "GET " + STORE.replace("0a1b", "ffff")
        with self.assertRaises(github.Unanswered):
            github.Replay(other[1:]).send(github.download("/repos/o/r/actions/artifacts/9/zip"))
        # The storage's answer is bounded, and a redirect off it refused, as the live transport does.
        for answer in ({"status": 302, "headers": {"location": STORE}, "body": None},
                       {"status": 200, "headers": {}, "body": "z" * (github.STORED + 1)}):
            off = stored("o/r", 7, zipped)
            off[2]["response"] = answer
            with self.assertRaises(github.Unanswered):
                github.Replay(off[1:]).send(github.download("/repos/o/r/actions/artifacts/9/zip"))
        # No error the replay raises holds the signed address.
        try:
            github.Replay(found[1:]).send(github.request("GET", "/repos/o/r/actions/artifacts/9/zip"))
        except github.Unanswered as err:
            self.assertNotIn("sig=", held(err))

    def test_a_redirects_address_is_read_alike_by_both_transports_and_never_named_when_refused(self):
        # A malformed address is refused, never let through as another error, and the refusal does not name it.
        for url in ("https://[productionresultssa7.blob.core.windows.net&sig=secret]/actions-results/x",
                    "https://[::1/actions-results/x?sig=secret"):
            with self.assertRaises(github.Unanswered) as refused:
                github.storage(url)
            self.assertNotIn("sig=", held(refused.exception))
        # The live transport reads a redirect's address as the replay does, joined to the address asked and never
        # quoted first, as urllib's own handler would: an address with a space is refused by both.
        asked = github.urllib.request.Request("https://api.github.com/repos/o/r/actions/artifacts/9/zip")
        relative = "//productionresultssa7.blob.core.windows.net/actions-results/0a1b/outcome.zip?sig=redacted"
        for location, joined in ((relative, "https:" + relative), (STORE + " b", STORE + " b")):
            with self.assertRaises(github.Redirected) as moved:
                github._NoRedirect().http_error_302(asked, None, 302, "Found", {"Location": location})
            self.assertEqual(moved.exception.location, joined)
        found = stored("o/r", 7, outcome_zip("{}"))
        found[1]["response"]["headers"]["location"] = relative
        found[2]["request"]["call"] = "GET https:" + relative
        self.assertEqual(github.Replay(found[1:]).send(github.download("/repos/o/r/actions/artifacts/9/zip"))["status"],
                         200)
        spaced = stored("o/r", 7, outcome_zip("{}"), store=STORE + "%20b")
        spaced[1]["response"]["headers"]["location"] = STORE + " b"
        with self.assertRaises(github.Unanswered):
            github.Replay(spaced[1:]).send(github.download("/repos/o/r/actions/artifacts/9/zip"))
        # A redirect whose address cannot be read is refused by both, naming nothing: the replay here, the live
        # transport below.
        self.assertIsNone(github._moved("https://api.github.com/x", "https://[::1/actions-results/x?sig=secret"))
        broken = stored("o/r", 7, outcome_zip("{}"))
        broken[1]["response"]["headers"]["location"] = "https://[::1/actions-results/x?sig=secret"
        with self.assertRaises(github.Unanswered) as refused:
            github.Replay(broken[1:]).send(github.download("/repos/o/r/actions/artifacts/9/zip"))
        self.assertNotIn("sig=", held(refused.exception))
        # Dot segments are never resolved away before the storage's path is checked, by either transport.
        climbing = STORE.replace("/actions-results/", "/other/../actions-results/")
        self.assertEqual(github._moved("https://api.github.com/x", climbing), climbing)
        with self.assertRaises(github.Unanswered):
            github.storage(climbing)
        # A download GitHub answers itself, with no redirect, is bounded as the storage's answer is, by both.
        big = {"request": {"via": "rest", "call": "GET /repos/o/r/actions/artifacts/9/zip", "headers": {}},
               "response": {"status": 200, "headers": {}, "body": "z" * (github.STORED + 1)}}
        with self.assertRaises(github.Unanswered):
            github.Replay([big]).send(github.download("/repos/o/r/actions/artifacts/9/zip"))
        # The replay checks a request as the live transport does: one built by hand to follow elsewhere is refused.
        elsewhere = copy.deepcopy(stored("o/r", 7, outcome_zip("{}")))
        elsewhere[1]["request"]["call"] = "GET /repos/o/r/pulls/1"
        with self.assertRaises(github.Unanswered):
            github.Replay(elsewhere[1:]).send({"method": "GET", "path": "/repos/o/r/pulls/1", "accept": github.JSON,
                                               "body": None, "follow": True})

    def test_the_live_transport_sends_no_token_to_the_storage_and_bounds_what_it_holds(self):
        sent = []

        class Zip(io.BytesIO):
            status, headers = 200, {"Content-Type": "application/zip"}

        class Opener:
            def __init__(self, size):
                self.size = size

            def open(self, req, timeout=None):
                sent.append(req)
                if len(sent) % 2:
                    raise github.Redirected(302, STORE)
                return Zip(b"z" * self.size)
        live = github.Live("t")
        live.opener = Opener(github.STORED)
        got = live.send(github.download("/repos/o/r/actions/artifacts/9/zip"))
        self.assertEqual((got["status"], len(github.raw(got["body"]))), (200, github.STORED))
        first, second = sent
        self.assertEqual((first.full_url, first.get_header("Authorization")),
                         ("https://api.github.com/repos/o/r/actions/artifacts/9/zip", "Bearer t"))
        self.assertEqual((second.full_url, second.get_method()), (STORE, "GET"))
        self.assertEqual({k.lower() for k, _ in second.header_items()}, {"user-agent"})
        live.opener = Opener(github.STORED + 1)
        with self.assertRaises(github.Unanswered):
            live.send(github.download("/repos/o/r/actions/artifacts/9/zip"))

        class Direct(Opener):
            def open(self, req, timeout=None):
                sent.append(req)
                return Zip(b"z" * self.size)
        live.opener = Direct(github.STORED + 1)
        with self.assertRaises(github.Unanswered):
            live.send(github.download("/repos/o/r/actions/artifacts/9/zip"))
        # Any other request that GitHub redirects is refused; and so is a redirect off the storage.
        sent.clear()
        live.opener = Opener(1)
        with self.assertRaises(github.Unanswered):
            live.send(github.request("GET", "/repos/o/r/actions/artifacts/9/zip"))
        self.assertEqual(len(sent), 1)

        # A 308, which Python before 3.11 hands on as an error, is followed the same way, and refused the same way.
        class Permanent(Opener):
            def open(self, req, timeout=None):
                sent.append(req)
                if len(sent) % 2:
                    raise github.urllib.error.HTTPError(req.full_url, 308, "Permanent", {"Location": STORE}, io.BytesIO())
                return Zip(b"z")
        sent.clear()
        live.opener = Permanent(1)
        self.assertEqual(live.send(github.download("/repos/o/r/actions/artifacts/9/zip"))["status"], 200)
        self.assertEqual(sent[1].full_url, STORE)

        # ... and its address is read as the 302's is, joined to the address asked.
        class Relative(Opener):
            def open(self, req, timeout=None):
                sent.append(req)
                if len(sent) % 2:
                    raise github.urllib.error.HTTPError(req.full_url, 308, "Permanent",
                                                        {"Location": STORE[len("https:"):]}, io.BytesIO())
                return Zip(b"z")
        sent.clear()
        live.opener = Relative(1)
        self.assertEqual(live.send(github.download("/repos/o/r/actions/artifacts/9/zip"))["status"], 200)
        self.assertEqual(sent[1].full_url, STORE)

        class Unreadable(Opener):
            def open(self, req, timeout=None):
                raise github.urllib.error.HTTPError(req.full_url, 308, "Permanent",
                                                    {"Location": "https://[::1/actions-results/x?sig=secret"}, io.BytesIO())
        live.opener = Unreadable(1)
        with self.assertRaises(github.Unanswered) as refused:
            live.send(github.download("/repos/o/r/actions/artifacts/9/zip"))
        self.assertNotIn("sig=", held(refused.exception))
        with self.assertRaises(github.Unanswered) as refused:
            live.send(github.request("GET", "/repos/o/r/actions/artifacts/9/zip"))
        self.assertNotIn("sig=", held(refused.exception))

        class Elsewhere(Opener):
            def open(self, req, timeout=None):
                sent.append(req)
                if len(sent) % 2:
                    raise github.Redirected(302, "https://evil.example/x")
                return Zip(b"z")
        sent.clear()
        live.opener = Elsewhere(1)
        with self.assertRaises(github.Unanswered) as refused:
            live.send(github.download("/repos/o/r/actions/artifacts/9/zip"))
        self.assertEqual(len(sent), 1)
        self.assertNotIn("evil", held(refused.exception))

        # A redirect off the storage is refused, and no error raised holds the signed address, nor is chained to one.
        class Again(Opener):
            def open(self, req, timeout=None):
                sent.append(req)
                raise github.Redirected(302, STORE)
        sent.clear()
        live.opener = Again(1)
        with self.assertRaises(github.Unanswered) as refused:
            live.send(github.download("/repos/o/r/actions/artifacts/9/zip"))
        self.assertEqual(len(sent), 2)
        self.assertNotIn("sig=", held(refused.exception))
        with self.assertRaises(github.Unanswered) as refused:
            live.send(github.request("GET", "/repos/o/r/actions/artifacts/9/zip"))
        self.assertNotIn("sig=", held(refused.exception))

        # An error the storage answers, cut short or over the bound, raises a refusal chained to no error that holds
        # the address: urllib names it as each error's filename.
        class Cut(io.BytesIO):
            def read(self, *a):
                raise github.http.client.IncompleteRead(b"")

        for answer in (lambda req: Cut(), lambda req: io.BytesIO(b"z" * (github.STORED + 1)),
                       lambda req: (_ for _ in ()).throw(ValueError("unknown url type: %s" % req.full_url))):
            class Failing(Opener):
                def open(self, req, timeout=None, answer=answer):
                    sent.append(req)
                    if len(sent) % 2:
                        raise github.Redirected(302, STORE)
                    found = answer(req)
                    raise github.urllib.error.HTTPError(req.full_url, 500, "x", {}, found)
            sent.clear()
            live.opener = Failing(1)
            with self.assertRaises(github.Unanswered) as refused:
                live.send(github.download("/repos/o/r/actions/artifacts/9/zip"))
            self.assertNotIn("sig=", held(refused.exception))

    def test_the_live_transport_takes_its_token_from_its_caller_and_follows_no_redirect(self):
        for token in ("", " ", "a b", None):
            with self.assertRaises(github.Unanswered, msg=repr(token)):
                github.Live(token)
        sent = github.urllib.request.Request("https://api.github.com/x")
        with self.assertRaises(github.Unanswered):
            github._NoRedirect().redirect_request(sent, None, 302, "Found", {}, "https://example.com/")
        # The opener follows no redirect and takes no proxy from the environment.
        kept = {k: os.environ.get(k) for k in ("https_proxy", "HTTPS_PROXY")}
        try:
            os.environ["https_proxy"] = os.environ["HTTPS_PROXY"] = "http://proxy.invalid:1"
            handlers = github.Live("t").opener.handlers
        finally:
            for k, v in kept.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertTrue(any(isinstance(h, github._NoRedirect) for h in handlers))
        self.assertFalse(any(type(h) is github.urllib.request.HTTPRedirectHandler for h in handlers))
        self.assertFalse(any(isinstance(h, github.urllib.request.ProxyHandler) and h.proxies for h in handlers))
        # GitHub out of reach is an answer refused, never an exception of another kind.
        live = github.Live("t")

        class Down:
            def open(self, *a, **k):
                raise github.urllib.error.URLError("down")
        live.opener = Down()
        with self.assertRaises(github.Unanswered):
            live.send(github.request("GET", "/x"))
        # An answer cut short while it is read, a body's or an error's, is refused, never another exception.
        class Short:
            def open(self, *a, **k):
                raise github.http.client.IncompleteRead(b"")
        live.opener = Short()
        with self.assertRaises(github.Unanswered):
            live.send(github.request("GET", "/x"))

        class Broken(io.BytesIO):
            def read(self, *a):
                raise github.http.client.IncompleteRead(b"")

        class Error:
            def open(self, *a, **k):
                raise github.urllib.error.HTTPError("https://api.github.com/x", 500, "x", {}, Broken())
        live.opener = Error()
        with self.assertRaises(github.Unanswered):
            live.send(github.request("GET", "/x"))
        # What it sends: HTTPS to GitHub's API, the path asked, and the caller's token as the bearer.
        sent = []

        class Answer(io.BytesIO):
            status = 200
            headers = {"Content-Type": "application/json"}

        class Capture:
            def open(self, request, timeout=None):
                sent.append((request, timeout))
                return Answer(b'{"ok": true}')
        live = github.Live("the-token")
        live.opener = Capture()
        self.assertEqual(live.send(github.request("GET", "/repos/o/r", headers={"Cache-Control": "no-cache"}))["body"],
                         {"ok": True})
        request, timeout = sent[0]
        self.assertEqual((request.full_url, request.get_header("Authorization"), timeout),
                         ("https://api.github.com/repos/o/r", "Bearer the-token", github.TIMEOUT))
        self.assertEqual(request.get_header("Cache-control"), "no-cache")
        # A request built by hand is held to the same rules before anything is opened.
        opened = []

        class Record:
            def open(self, *a, **k):
                opened.append(a)
        live.opener = Record()
        for path in ("//example.com/x", "https://example.com/x"):
            with self.assertRaises(github.Unanswered):
                live.send({"method": "GET", "path": path, "accept": github.JSON, "body": None})
        self.assertEqual(opened, [])
        # The answer it builds keeps the headers and reads JSON as JSON, and anything else as text.
        answer = github._answer(200, {"Content-Type": "application/json; charset=utf-8"}, b'{"a": 1}')
        self.assertEqual(answer, {"status": 200, "headers": {"content-type": "application/json; charset=utf-8"},
                                  "body": {"a": 1}})
        self.assertEqual(github._answer(200, {"Content-Type": github.DIFF}, b"diff --git")["body"], "diff --git")
        # A body that is not UTF-8 is kept without loss: two that differ in one byte stay two.
        one, two = (github._answer(200, {"Content-Type": github.DIFF}, b"+caf" + c + b"\n")["body"] for c in (b"\xe9", b"\xe8"))
        self.assertNotEqual(one, two)
        self.assertEqual(github.raw(one), b"+caf\xe9\n")
        # An answer over the bound is refused, never cut short silently.
        largest = github.LARGEST
        try:
            github.LARGEST = 4
            self.assertEqual(github._bounded(io.BytesIO(b"1234")), b"1234")
            with self.assertRaises(github.Unanswered):
                github._bounded(io.BytesIO(b"12345"))
        finally:
            github.LARGEST = largest


class Own(unittest.TestCase):
    def test_the_pull_requests_own_facts_and_the_title_beside_them(self):
        # Decision 0039: the title comes back beside the facts, from the same read, and is never in them.
        data = body("P-29.base", 1)
        part, title = pull.own(data, person())
        self.assertEqual(part, {"item": {"repo": data["base"]["repo"]["full_name"], "type": "pull_request",
                                         "number": 26},
                                "state": "open", "is_draft": False, "author": "don-petry", "class": "maintainer",
                                "mergeable": True})
        self.assertEqual(title, data["title"])
        self.assertNotIn(title, json.dumps(part))

    def test_the_class_is_the_account_named_or_outside(self):
        # Decisions 0005 and 0026: an account is told by its login and its type, never its spelling alone; a fork is
        # always outside; anyone the caller does not name is outside, which asks for a person.
        data = body("P-29.base", 1)
        self.assertEqual(pull.own(data, {})[0]["class"], "outside")
        self.assertEqual(pull.own(data, {"maintainer": {(MAINTAINER, "Bot")}})[0]["class"], "outside")
        self.assertEqual(pull.own(data, person(MAINTAINER + 1))[0]["class"], "outside")
        # An App's class needs a Bot: a person named as the Factory's App or a dependency bot is outside.
        self.assertEqual(pull.own(data, {"agent": {(MAINTAINER, "User")}})[0]["class"], "outside")
        self.assertEqual(pull.own(data, {"dependency": {(MAINTAINER, "User")}})[0]["class"], "outside")
        bot = copy.deepcopy(data)
        bot["user"].update(login="dependabot[bot]", id=49699333, type="Bot")
        self.assertEqual(pull.own(bot, {"dependency": {(49699333, "Bot")}})[0]["class"], "dependency")
        self.assertEqual(pull.own(bot, {"agent": {(49699333, "Bot")}})[0]["class"], "agent")
        # A rename keeps the account's id, and a new account under the old login is someone else.
        renamed = copy.deepcopy(data)
        renamed["user"]["id"] = MAINTAINER + 1
        self.assertEqual(pull.own(renamed, person())[0]["class"], "outside")
        fork = copy.deepcopy(data)
        fork["head"]["repo"]["id"] += 1
        self.assertEqual(pull.own(fork, person())[0]["class"], "outside")
        gone = copy.deepcopy(data)
        gone["head"]["repo"] = None
        self.assertEqual(pull.own(gone, person())[0]["class"], "outside")

    def test_a_merge_a_state_and_an_unknown_mergeable_are_read_as_github_gives_them(self):
        data = body("P-29.base", 1)
        data["state"], data["merged_at"] = "closed", "2026-10-18T02:00:00Z"
        self.assertEqual(pull.own(data, {})[0]["state"], "merged")
        data["merged_at"], data["mergeable"] = None, None
        self.assertEqual(pull.own(data, {})[0]["state"], "closed")
        self.assertIsNone(pull.own(data, {})[0]["mergeable"])
        for broken in ({"state": "reopened"}, {"draft": None}, {"user": None}, {"user": {"login": "x", "type": "Org", "id": 1}},
                       {"user": {"login": "x", "type": "User", "id": "1"}}):
            bad = dict(copy.deepcopy(data), **broken)
            with self.assertRaises(github.Unanswered, msg=broken):
                pull.own(bad, {})

    def test_the_base_branchs_protection_is_read_from_the_branch(self):
        self.assertIs(pull.targets_protected(replay("P-29.base", 9), body("P-29.base", 1)), False)
        unread = copy.deepcopy(exchanges("P-29.base")[9])
        del unread["response"]["body"]["protected"]
        with self.assertRaises(github.Unanswered):
            pull.targets_protected(github.Replay([unread]), body("P-29.base", 1))
        # A branch's name is a name: a # or & in it is never a fragment or a parameter.
        odd = copy.deepcopy(exchanges("P-29.base")[9])
        odd["request"]["call"] = odd["request"]["call"].replace("/branches/main", "/branches/a%23b%26c")
        named = body("P-29.base", 1)
        named["base"]["ref"] = "a#b&c"
        self.assertIs(pull.targets_protected(github.Replay([odd]), named), False)

    def test_the_pull_request_is_read_once_and_must_be_the_one_asked_for(self):
        repo = json.loads((ROOT / "trials" / "P-29.base.json").read_text())["repo"]
        self.assertEqual(pull.read(replay("P-29.base", 1), repo, 26)["head"]["sha"], body("P-29.base", 1)["head"]["sha"])
        other = copy.deepcopy(exchanges("P-29.base")[1])
        other["response"]["body"]["number"] = 27
        with self.assertRaises(github.Unanswered):
            pull.read(github.Replay([other]), repo, 26)
        with self.assertRaises(github.Unanswered):
            pull.read(replay("P-29.base", 1), repo, 27)

    def test_a_head_that_moved_while_it_was_read_is_refused(self):
        # trials/P-29.base.json: read again after the base moved, the head is the same; after the plain push, it is not.
        self.assertIs(pull.same_head(replay("P-29.base", 6), body("P-29.base", 1)), True)
        self.assertIs(pull.same_head(replay("P-29.base", 12), body("P-29.base", 1)), False)
        # A retarget that keeps the head is a different pull request to read.
        retargeted = copy.deepcopy(exchanges("P-29.base")[6])
        retargeted["response"]["body"]["base"]["ref"] = "other"
        self.assertIs(pull.same_head(github.Replay([retargeted]), body("P-29.base", 1)), False)
        moved = copy.deepcopy(exchanges("P-29.base")[6])
        moved["response"]["body"]["base"]["repo"]["id"] += 1
        self.assertIs(pull.same_head(github.Replay([moved]), body("P-29.base", 1)), False)
        no_head = copy.deepcopy(exchanges("P-29.base")[6])
        no_head["response"]["body"]["head"]["sha"] = "1234"
        with self.assertRaises(github.Unanswered):
            pull.same_head(github.Replay([no_head]), body("P-29.base", 1))


class LastPusher(unittest.TestCase):
    def test_the_newest_push_to_the_head_names_its_pusher_a_person_or_an_app(self):
        # Decision 0026, trials/P-28.json and trials/P-28.app.json: the entry's actor when its after is the head.
        self.assertEqual(pull.last_pusher(replay("P-28", 7), body("P-28", 10)), "don-petry")
        self.assertEqual(pull.last_pusher(replay("P-28.app", 1), body("P-28.app", 0)),
                         "combsmith-sf-trial-author[bot]")

    def test_an_activity_that_has_not_caught_up_with_the_head_names_no_one(self):
        # The activity read after the plain push, against the head after the force push: the newest entry is not the
        # head, so the last pusher is unreadable, never the older entry's actor.
        self.assertIsNone(pull.last_pusher(replay("P-28", 3), body("P-28", 10)))
        empty = {"request": exchanges("P-28")[7]["request"], "response": {"status": 200, "headers": {}, "body": []}}
        self.assertIsNone(pull.last_pusher(github.Replay([empty]), body("P-28", 10)))

    def test_only_the_newest_entry_is_read(self):
        # trials/P-28.json, after the force push: the plain push's entry is still listed, second. A head at that
        # commit is not what the newest entry pushed, so no one is read, never the older entry's actor.
        moved = body("P-28", 10)
        moved["head"]["sha"] = exchanges("P-28")[7]["response"]["body"][1]["after"]
        self.assertIsNone(pull.last_pusher(replay("P-28", 7), moved))

    def test_a_fork_is_read_as_no_one_and_its_activity_is_never_asked(self):
        fork = body("P-28", 10)
        fork["head"]["repo"]["id"] += 1
        self.assertIsNone(pull.last_pusher(github.Replay([]), fork))


PINNED_BASE = "b" * 40      # a base branch's head the compare names; a replay matches the call it is given


def as_compare(exchange: dict, data: dict, base: str = PINNED_BASE) -> dict:
    """A recorded answer to the pull request's own diff, or to a page of its files, replayed as the compare of `base`
    with the head of `data`, as the port now asks it (issue 284): P-29 shows the diff's bytes equal the compare's
    (`trials/P-29.base.json`), and a compare lists its files under `files`, as P-29's exchange 10 does."""
    found = copy.deepcopy(exchange)
    call = found["request"]["call"]
    found["request"]["call"] = "GET /repos/%s/compare/%s...%s" % (data["base"]["repo"]["full_name"], base,
                                                                 data["head"]["sha"])
    if "/files" in call:
        found["request"]["headers"] = dict(found["request"]["headers"], accept="application/vnd.github+json")
        found["response"] = dict(found["response"], body={"files": found["response"]["body"]})
    return found


def compared(name: str, at: int, data: dict, base: str = PINNED_BASE) -> github.Replay:
    return github.Replay([as_compare(exchanges(name)[at], data, base)])


class Diff(unittest.TestCase):
    def test_a_diff_read_at_another_commit_cannot_give_the_snapshots_content(self):  # issue 284
        # The diff is read by compare at the head of the pull request's first read, never off the pull request: a head
        # pushed away and back between the reads still gives the content of the first read's head, and an answer for
        # another commit is not one the port asks for.
        data = body("P-29.base", 1)
        at_head = pull.diff(compared("P-29.base", 2, data), data, PINNED_BASE)
        self.assertEqual(at_head["content_id"], "sha256:" + body("P-29.base", 24)["before the base moved"])
        elsewhere = copy.deepcopy(data)
        elsewhere["head"]["sha"] = "c" * 40
        with self.assertRaises(github.Unanswered):
            pull.diff(github.Replay([as_compare(exchanges("P-29.base")[2], elsewhere)]), data, PINNED_BASE)
        with self.assertRaises(github.Unanswered):           # the pull request's own diff is never read
            pull.diff(replay("P-29.base", 2), data, PINNED_BASE)
        # A head no longer there answers 404, and a base head that cannot be read is refused: no snapshot.
        gone = as_compare(exchanges("P-29.base")[2], data)
        gone["response"] = dict(gone["response"], status=404, body={"message": "Not Found"})
        with self.assertRaises(github.Unanswered):
            pull.diff(github.Replay([gone]), data, PINNED_BASE)
        with self.assertRaises(github.Unanswered):
            pull.diff(compared("P-29.base", 2, data, "main"), data, "main")
        # A fork's head is compared in the base repo, which holds both commits, never in the fork (Muse on PR 284).
        fork = copy.deepcopy(data)
        fork["head"]["repo"] = dict(fork["head"]["repo"], full_name="someone/fork", id=1)
        self.assertEqual(pull.diff(compared("P-29.base", 2, fork), fork, PINNED_BASE)["content_id"], at_head["content_id"])

    def test_the_content_is_the_hash_of_the_diff_as_github_served_it(self):
        # trials/P-29.base.json: the hash taken as each diff arrived is the one the port computes.
        hashes = body("P-29.base", 24)
        for at, answer, moment in ((1, 2, "before the base moved"), (12, 13, "after the plain push"),
                                   (21, 22, "after the force push")):
            got = pull.diff(compared("P-29.base", answer, body("P-29.base", at)), body("P-29.base", at), PINNED_BASE)
            self.assertEqual(got["content_id"], "sha256:" + hashes[moment], moment)
            self.assertIs(got["complete"], True, moment)
            self.assertEqual(got["diff"]["truncated"], False)
        data = body("P-29.base", 1)
        self.assertEqual(pull.diff(compared("P-29.base", 2, data), data, PINNED_BASE)["diff"],
                         {"files": 1, "lines": 3, "truncated": False})

    def test_the_content_is_hashed_over_the_bytes_github_sent(self):
        # A diff that is not UTF-8 keeps its bytes: its content id is theirs, so two diffs one byte apart are two.
        data = body("P-29.base", 1)
        data.update(changed_files=1, additions=1, deletions=0)
        ids = []
        for byte in (b"\xe9", b"\xe8"):
            sent = b"diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -0,0 +1 @@\n+caf" + byte + b"\n"
            answer = github._answer(200, {"Content-Type": github.DIFF}, sent)
            exchange = dict(exchanges("P-29.base")[2], response=dict(exchanges("P-29.base")[2]["response"],
                                                                     body=answer["body"]))
            got = pull.diff(github.Replay([as_compare(exchange, data)]), data, PINNED_BASE)
            self.assertEqual(got["content_id"], "sha256:" + hashlib.sha256(sent).hexdigest())
            self.assertIs(got["complete"], True)
            ids.append(got["content_id"])
        self.assertNotEqual(*ids)

    def test_a_diff_that_disagrees_with_the_counts_is_a_short_read(self):
        # Decision 0002: the diff is held to the same pull request's counts; a difference is a short read.
        data = body("P-29.base", 1)
        data["additions"] += 1
        self.assertIs(pull.diff(compared("P-29.base", 2, data), data, PINNED_BASE)["complete"], False)
        data = body("P-29.base", 1)
        data["changed_files"] += 1
        self.assertIs(pull.diff(compared("P-29.base", 2, data), data, PINNED_BASE)["complete"], False)

    def test_a_diff_github_will_not_serve_is_truncated_and_new_content_at_every_push(self):
        # trials/P-29.truncated.json: 3,001 files, a 406 too_large. Read whole, so the Kernel holds it as too large;
        # its content is the head commit's, so a push is never read as unchanged.
        data = body("P-29.truncated", 2)
        got = pull.diff(compared("P-29.truncated", 4, data), data, PINNED_BASE)
        self.assertEqual((got["diff"], got["complete"]), ({"files": 3001, "lines": 3001, "truncated": True}, True))
        moved = copy.deepcopy(data)
        moved["head"]["sha"] = "0" * 40
        self.assertNotEqual(pull.diff(compared("P-29.truncated", 4, moved), moved, PINNED_BASE)["content_id"], got["content_id"])
        # A 406 for anything but too_large, and a head that cannot be read, are refused.
        other = copy.deepcopy(exchanges("P-29.truncated")[4])
        other["response"]["body"]["errors"][0]["code"] = "not_acceptable"
        with self.assertRaises(github.Unanswered):
            pull.diff(github.Replay([as_compare(other, data)]), data, PINNED_BASE)
        no_head = copy.deepcopy(data)
        no_head["head"]["sha"] = ""
        with self.assertRaises(github.Unanswered):
            pull.diff(compared("P-29.truncated", 4, no_head), no_head, PINNED_BASE)

    def test_a_line_of_content_that_looks_like_a_header_is_counted_as_the_line_it_is(self):
        text = ("diff --git a/q.sql b/q.sql\nindex 1..2 100644\n--- a/q.sql\n+++ b/q.sql\n@@ -1,2 +1,2 @@\n"
                " select 1;\n--- old comment\n+++ new comment\n\\ No newline at end of file\n")
        self.assertEqual(pull._counts(text), (1, 1, 1))
        self.assertIsNone(pull._counts(text.replace("@@ -1,2 +1,2 @@", "@@ -1,3 +1,2 @@")))
        self.assertIsNone(pull._counts(text.replace(" select 1;", "?select 1;")))
        # A diff that ends inside a hunk, its header promising more lines than came, is short.
        self.assertIsNone(pull._counts(text.rstrip("\n").replace("@@ -1,2 +1,2 @@", "@@ -1,2 +1,3 @@")))

    def test_an_answer_that_is_not_a_diff_is_refused(self):
        broken = copy.deepcopy(exchanges("P-29.base")[2])
        broken["response"]["status"] = 500
        with self.assertRaises(github.Unanswered):
            pull.diff(github.Replay([as_compare(broken, body("P-29.base", 1))]), body("P-29.base", 1), PINNED_BASE)


def files_rows(count: int) -> list:
    """`count` rows of a list of files, shaped as P-29.truncated's page 30 gives them."""
    row = exchanges("P-29.truncated")[10]["response"]["body"][0]
    return [dict(row, filename="p29-many-files/f%04d.txt" % (i + 1)) for i in range(count)]


def compare_files(rows: list, data: dict) -> dict:
    """A compare at the head of `data` that lists `rows` as its files."""
    found = as_compare(exchanges("P-29.truncated")[13], data)
    found["response"] = dict(found["response"], body={"files": rows})
    return found


class ChangedPaths(unittest.TestCase):
    def test_every_file_is_read_and_the_list_is_whole_when_it_holds_the_count(self):
        got = pull.changed_paths(compared("P-29.truncated", 13, body("P-29.truncated", 12)), body("P-29.truncated", 12), PINNED_BASE)
        self.assertEqual(got, {"changed_paths": [{"path": "p29-many-lines-2.txt", "previous": None},
                                                 {"path": "p29-many-lines.txt", "previous": None}],
                               "complete": True})

    def test_a_list_github_stops_short_of_the_count_is_never_the_whole(self):
        # trials/P-29.truncated.json: 3,001 files. A compare lists at most 300, so a change of more is read short by
        # its count alone: nothing is asked (an empty replay answers nothing), so no answer can refuse the snapshot
        # (issue 284's ruling). 301 rows, which GitHub would not send, are never read whole either.
        data = body("P-29.truncated", 2)
        for count in (3001, 301):
            data["changed_files"] = count
            got = pull.changed_paths(github.Replay([]), data, PINNED_BASE)
            self.assertEqual(got, {"changed_paths": [], "complete": False}, count)

    def test_a_list_of_up_to_three_hundred_files_is_whole(self):
        data = body("P-29.truncated", 2)
        for count in (200, 300):
            data["changed_files"] = count
            got = pull.changed_paths(github.Replay([compare_files(files_rows(count), data)]), data, PINNED_BASE)
            self.assertEqual((len(got["changed_paths"]), got["complete"]), (count, True), count)

    def test_a_file_list_read_at_another_commit_is_not_asked_for(self):  # issue 284
        data = body("P-29.truncated", 12)
        elsewhere = copy.deepcopy(data)
        elsewhere["head"]["sha"] = "c" * 40
        with self.assertRaises(github.Unanswered):
            pull.changed_paths(github.Replay([as_compare(exchanges("P-29.truncated")[13], elsewhere)]), data, PINNED_BASE)
        with self.assertRaises(github.Unanswered):           # the pull request's own list is never read
            pull.changed_paths(replay("P-29.truncated", 13), data, PINNED_BASE)
        # A compare whose files are not a list, or are not there at all, is refused, never read as none (Muse on PR 284).
        for answered in ({"files": "none"}, {}):
            broken = as_compare(exchanges("P-29.truncated")[13], data)
            broken["response"] = dict(broken["response"], body=answered)
            with self.assertRaises(github.Unanswered):
                pull.changed_paths(github.Replay([broken]), data, PINNED_BASE)

    def test_a_rename_or_a_copy_gives_both_names_and_one_without_its_old_name_is_short(self):
        data = body("P-29.truncated", 12)
        rows = body("P-29.truncated", 13)
        rows[0].update(status="renamed", previous_filename="old/name.txt")
        rows[1].update(status="copied", previous_filename="p29-many-lines-2.txt")
        answer = dict(exchanges("P-29.truncated")[13], response=dict(exchanges("P-29.truncated")[13]["response"],
                                                                     body=rows))
        got = pull.changed_paths(github.Replay([as_compare(answer, data)]), data, PINNED_BASE)
        self.assertEqual([p["previous"] for p in got["changed_paths"]], ["old/name.txt", "p29-many-lines-2.txt"])
        self.assertIs(got["complete"], True)
        del rows[0]["previous_filename"]
        self.assertIs(pull.changed_paths(github.Replay([as_compare(answer, data)]), data, PINNED_BASE)["complete"], False)

    def test_a_list_with_a_name_twice_or_none_is_short(self):
        data = body("P-29.truncated", 12)
        for change in ({"filename": "p29-many-lines.txt"}, {"filename": ""}, {"filename": None}, {"status": "moved"},
                       {"status": None}, {"previous_filename": "was.txt"}):
            rows = body("P-29.truncated", 13)
            rows[0].update(change)
            answer = dict(exchanges("P-29.truncated")[13], response=dict(exchanges("P-29.truncated")[13]["response"],
                                                                         body=rows))
            self.assertIs(pull.changed_paths(github.Replay([as_compare(answer, data)]), data, PINNED_BASE)["complete"], False, change)

    def test_a_renamed_file_is_read_with_its_old_name_from_a_fixture(self):
        # trials/P-43.json (issue 250) records a rename: REST names its old path, as the synthetic case above does.
        found = exchanges("P-43")
        self.assertTrue(any(row.get("previous_filename") for e in found if isinstance(e["response"]["body"], list)
                            for row in e["response"]["body"] if isinstance(row, dict)))


WORKFLOW = "p17-p22-run-records.yml"     # the trial's workflow, standing in for a Role's in these tests
DISPATCHER = (MAINTAINER, "User")        # who dispatched the trial's runs, standing in for the Controller's App


class Recording:
    """A transport that remembers each request it is handed, and answers from a replay."""

    def __init__(self, replay):
        self.replay, self.sent = replay, []

    def send(self, req):
        self.sent.append(req)
        return self.replay.send(req)


def asked(found: dict, page: int = 1) -> dict:
    """A fixture's list of runs, asked as the port asks it: the default branch's dispatches, a page at a time."""
    words = found["request"]["call"].split()
    path, _, query = words[1].rstrip(",").partition("?")
    per = query.split("per_page=")[1].split("&")[0]
    call = "%s?branch=main&event=workflow_dispatch&per_page=%s%s" % (path, per, "" if page == 1 else "&page=%d" % page)
    return dict(found, request=dict(found["request"], call=" ".join([words[0], call] + words[2:])))


def listing(name: str, at: int, page: int = 1, **change) -> dict:
    """One list of runs from a fixture, asked as the port asks it, with its rows changed as named: `rows` maps a field
    to a new value on each row."""
    found = copy.deepcopy(exchanges(name)[at])
    body_ = found["response"]["body"]
    for key, value in change.get("rows", {}).items():
        for row in body_["workflow_runs"]:
            row[key] = value
    if "total" in change:
        body_["total_count"] = change["total"]
    if "headers" in change:
        found["response"]["headers"].update(change["headers"])
    return asked(found, page)


def canary() -> str:
    return json.loads((ROOT / "trials" / "P-17.json").read_text())["repo"]


def http_date(sent: str) -> str:
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    _, day, month, year, clock, _ = sent.split()
    return "%s-%02d-%02dT%sZ" % (year, months.index(month) + 1, int(day), clock)


NAME = "sf combsmith/software-factory#264 review-change pr-review sha256:5d0c r_01JA6Z"


def outcome_of(run: str, fault, reason="engine_failed") -> dict:
    """An `outcome/1` as a Run's final step writes it, of the shape examples/outcome.json gives."""
    found = json.loads((ROOT / "examples" / "outcome.json").read_text())
    return dict(found, run=run, outcome=fault, reason=reason)


def outcome_zip(record, member: str = artifacts.MEMBER, more: tuple = ()) -> bytes:
    """A zip as GitHub serves an artifact: the one file, or the files named."""
    held = io.BytesIO()
    with zipfile.ZipFile(held, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, record if isinstance(record, (bytes, str)) else json.dumps(record))
        for name in more:
            archive.writestr(name, "{}")
    return held.getvalue()


def held(err: BaseException) -> str:
    """Every text an error holds, and every error it is chained to: its message and each attribute's value."""
    found = []
    while err is not None:
        found += [str(err)] + [repr(v) for v in vars(err).values()]
        err = err.__cause__ or err.__context__
    return " ".join(found)


STORE = "https://productionresultssa7.blob.core.windows.net/actions-results/0a1b/outcome.zip?sig=redacted"


def stored(repo: str, github_id: int, zipped, ident: int = 9, store: str = STORE, **listed) -> list:
    """A run's artifacts listed, its outcome's download redirected, and the storage's answer, in the shapes GitHub's
    REST reference gives: no trial has recorded an artifact read yet (the pending test below says when one does).
    `zipped` None lists none."""
    artifact = {"id": ident, "name": artifacts.NAME, "expired": False}
    if zipped is not None:
        artifact.update(size_in_bytes=len(zipped), digest="sha256:" + hashlib.sha256(zipped).hexdigest())
    artifact.update(listed)
    listing_ = [artifact] if zipped is not None else []
    found = [{"request": {"via": "rest", "call": "GET /repos/%s/actions/runs/%d/artifacts?name=outcome&per_page=100"
                          % (repo, github_id), "headers": {}},
              "response": {"status": 200, "headers": {"date": "Wed, 21 Oct 2026 02:18:34 GMT"},
                           "body": {"total_count": len(listing_), "artifacts": listing_}}}]
    if zipped is not None:
        found.append({"request": {"via": "rest", "call": "GET /repos/%s/actions/artifacts/%d/zip" % (repo, ident),
                                  "headers": {}},
                      "response": {"status": 302, "headers": {"location": store}, "body": None}})
        found.append({"request": {"via": "storage", "call": "GET %s" % store, "headers": {}},
                      "response": {"status": 200, "headers": {"content-type": "application/zip"},
                                   "body": zipped.decode("utf-8", errors="surrogateescape")}})
    return found


class Records(unittest.TestCase):
    def read(self, *found, **kw):
        slept = []
        got = records.runs(github.Replay(list(found)), canary(), "main", [WORKFLOW], kw.get("dispatcher", DISPATCHER),
                           per_page=kw.get("per_page", 10), sleep=slept.append, kept=kw.get("kept"))
        return got, slept

    def test_a_run_listed_under_its_workflows_name_is_unidentified_after_one_more_read(self):
        # trials/P-17.json: just after the dispatch the run is listed under its workflow's name, and at the read after
        # it under the trial's own, neither a run-name: it is reported by its GitHub id, never dropped, and the port
        # waited once (decision 0036).
        got, slept = self.read(listing("P-17", 9, total=1), listing("P-17", 10, total=1), per_page=1)
        self.assertEqual(exchanges("P-17")[9]["response"]["body"]["workflow_runs"][0]["name"], "p17-p22-run-records")
        created = exchanges("P-17")[10]["response"]["body"]["workflow_runs"][0]["created_at"]
        self.assertEqual((got["runs"], got["unidentified"], got["complete"], slept),
                         ([], [{"run": "39086879694", "created_at": created,
                                "status": "in_progress" if exchanges("P-17")[10]["response"]["body"]["workflow_runs"][0]["status"] == "in_progress" else "queued"}], True, [5]))
        # A run not yet started is listed as queued, whichever word GitHub uses for it (issue 270).
        got, _ = self.read(listing("P-17", 9, total=1), listing("P-17", 10, total=1, rows={"status": "pending"}),
                           per_page=1)
        self.assertEqual([u["status"] for u in got["unidentified"]], ["queued"])
        # A record whose creation cannot be read is a row that cannot be read: the list is not whole (issue 270).
        got, _ = self.read(listing("P-17", 9, total=1), listing("P-17", 10, total=1, rows={"created_at": "soon"}),
                           per_page=1)
        self.assertEqual((got["unidentified"], got["complete"]), ([], False))

    def test_a_run_named_by_the_second_read_is_a_record(self):
        second = listing("P-17", 10, total=1, rows={"name": NAME})
        got, slept = self.read(listing("P-17", 9, total=1), second, per_page=1)
        self.assertEqual((got["unidentified"], slept), ([], [5]))
        self.assertEqual(got["runs"], [{"run": "r_01JA6Z", "item": {"repo": "combsmith/software-factory",
                                        "type": "pull_request", "number": 264}, "intent": "review-change",
                                        "role": "pr-review", "content_id": "sha256:5d0c", "status": "queued",
                                        "conclusion": None, "outcome": None,
                                        "started_at": second["response"]["body"]["workflow_runs"][0]["run_started_at"],
                                        "dispatched_at": second["response"]["body"]["workflow_runs"][0]["created_at"]}])
        # A re-run says whether the pass job's own token, the dispatcher, re-ran it; a first attempt says nothing, and
        # a time of the dispatch GitHub does not give is left out (decision 0063).
        row = second["response"]["body"]["workflow_runs"][0]
        for change, want in (({"run_attempt": 2, "triggering_actor": dict(row["actor"])}, {"rerun_by_dispatcher": True}),
                             ({"run_attempt": 2, "triggering_actor": {"id": row["actor"]["id"] + 1, "type": "User"}},
                              {"rerun_by_dispatcher": False}),
                             ({"run_attempt": 2, "triggering_actor": None}, {"rerun_by_dispatcher": False}),
                             ({"run_attempt": 1, "triggering_actor": dict(row["actor"])}, {}),
                             ({"run_attempt": True}, {}), ({"run_attempt": "2"}, {})):
            again = listing("P-17", 10, total=1, rows=dict({"name": NAME}, **change))
            got, _ = self.read(listing("P-17", 9, total=1), again, per_page=1)
            self.assertEqual({k: v for k, v in got["runs"][0].items() if k == "rerun_by_dispatcher"}, want, change)
        for created in ("yesterday", None):
            again = listing("P-17", 10, total=1, rows={"name": NAME, "created_at": created})
            got, _ = self.read(listing("P-17", 9, total=1), again, per_page=1)
            self.assertNotIn("dispatched_at", got["runs"][0], created)

    def test_only_a_dispatch_of_a_role_workflow_from_the_default_branch_in_this_repo_counts(self):
        # Decision 0003 and I-34: another workflow, event, branch, ref, repo or dispatcher, a fork's pull request and a
        # person's dispatch among them, is never a Run, and never unidentified: no second read waits on it.
        for change in ({"path": ".github/workflows/other.yml"}, {"event": "schedule"}, {"event": "pull_request"},
                       {"head_branch": "trial/x"}, {"path": ".github/workflows/%s@refs/tags/main" % WORKFLOW},
                       {"repository": {"full_name": "someone/fork"}}, {"head_repository": {"full_name": "someone/fork"}},
                       {"actor": {"id": MAINTAINER, "type": "Bot"}}, {"actor": {"id": 1, "type": "User"}}, {"actor": None}):
            got, slept = self.read(listing("P-17", 3, rows=change))
            self.assertEqual((got["runs"], got["unidentified"], slept), ([], [], []), change)
        got, _ = self.read(listing("P-17", 3, rows={"name": NAME, "path": ".github/workflows/%s@refs/heads/main" % WORKFLOW}))
        self.assertEqual(len(got["runs"]), 1)

    def test_every_read_asks_for_the_default_branchs_dispatches_uncached_and_keeps_its_date_and_age(self):
        found = listing("P-17", 3, rows={"name": NAME}, headers={"age": "30"})
        transport = Recording(github.Replay([found]))
        got = records.runs(transport, canary(), "main", [WORKFLOW], DISPATCHER, per_page=10, sleep=lambda s: None)
        self.assertEqual([r["headers"] for r in transport.sent], [{"Cache-Control": "no-cache"}])
        self.assertIn("?branch=main&event=workflow_dispatch&per_page=10", transport.sent[0]["path"])
        self.assertEqual(got["reads"], [{"read": "runs", "date": http_date(found["response"]["headers"]["date"]),
                                         "age": 30}])
        for headers in ({"age": "-1"}, {"age": "x"}, {"age": "3_0"}, {"age": " 30"}, {"date": "yesterday"},
                        {"date": "Sun, 18 Oct 2026 25:29:12 GMT"}, {"date": "Sun, 18 Okt 2026 01:29:12 GMT"}):
            with self.assertRaises(github.Unanswered, msg=headers):
                self.read(listing("P-17", 3, rows={"name": NAME}, headers=headers))

    def test_a_list_read_short_is_not_whole(self):
        # L-53: a count beyond what GitHub serves, pages that end short of the count, or a list that is not one.
        got, _ = self.read(listing("P-17", 3, rows={"name": NAME}, total=1001))
        self.assertIs(got["complete"], False)
        got, _ = self.read(listing("P-17", 3, rows={"name": NAME}, total=2))
        self.assertIs(got["complete"], False)
        broken = listing("P-17", 3)
        broken["response"]["body"]["workflow_runs"] = None
        self.assertIs(self.read(broken)[0]["complete"], False)

    def test_a_list_whose_count_moved_or_that_repeats_a_run_across_pages_is_not_whole(self):
        one = listing("P-17", 10, total=2, rows={"name": NAME})
        two = listing("P-17", 10, page=2, total=2, rows={"name": NAME.replace("#264", "#265"), "id": 1})
        got, _ = self.read(one, two, per_page=1)
        self.assertEqual((len(got["runs"]), got["complete"]), (2, True))
        moved = listing("P-17", 10, page=2, total=3, rows={"name": NAME.replace("#264", "#265"), "id": 1})
        self.assertIs(self.read(one, moved, per_page=1)[0]["complete"], False)
        again = listing("P-17", 10, page=2, total=2, rows={"name": NAME})
        self.assertIs(self.read(one, again, per_page=1)[0]["complete"], False)

    def test_the_outcome_is_read_for_a_run_that_did_not_succeed_and_for_no_other(self):
        # Decisions 0039 and 0049: a failed Run's outcome is read from its artifact; a Run that succeeded has none
        # read, and one whose outcome cannot be read leaves the list not whole, never read as no attempt.
        done = {"name": NAME, "status": "completed"}
        row = listing("P-17", 3, rows=dict(done, conclusion="success"))
        github_id = row["response"]["body"]["workflow_runs"][0]["id"]
        got, _ = self.read(row)
        self.assertEqual((got["runs"][0]["conclusion"], got["runs"][0]["outcome"], got["complete"]), ("success", None, True))
        for conclusion, read in (("startup_failure", "cancelled"), ("timed_out", "timed_out"), ("cancelled", "cancelled")):
            failed = listing("P-17", 3, rows=dict(done, conclusion=conclusion))
            got, _ = self.read(failed, *stored(canary(), github_id, outcome_zip(outcome_of("r_01JA6Z", "item"))))
            self.assertEqual((got["runs"][0]["conclusion"], got["runs"][0]["outcome"], got["complete"]),
                             (read, "item", True), conclusion)
            got, _ = self.read(failed, stored(canary(), github_id, None)[0])
            self.assertEqual((got["runs"][0]["outcome"], got["complete"]), (None, True), conclusion)
            got, _ = self.read(failed, stored(canary(), github_id, outcome_zip(outcome_of("r_01JA6Z", "item")),
                                              expired=True)[0])
            self.assertEqual((got["runs"][0]["outcome"], got["complete"]), (None, True), conclusion)
            got, _ = self.read(failed, *stored(canary(), github_id, outcome_zip(outcome_of("r_01JA6Z", "item")),
                                               expired=None))
            self.assertEqual((got["runs"][0]["outcome"], got["complete"]), (None, False), conclusion)

    def test_an_outcome_is_read_once_and_kept_by_its_run_and_attempt(self):
        # #285's ruling: an outcome is written once by its attempt's final step, so one a pass record read is kept by
        # its Run id and when its attempt started, and not read again; one that is not there is kept as none once two
        # passes in a row read none, each reading its list whole. N failed Runs cost N reads, then only those with
        # none, then none (L-52).
        done = {"status": "completed", "conclusion": "failure"}
        rows = listing("P-17", 3, rows=done)
        template = rows["response"]["body"]["workflow_runs"][0]
        names = [NAME.replace("r_01JA6Z", "r_%06dZ" % n) for n in range(3)]
        rows["response"]["body"].update(total_count=3, workflow_runs=[
            dict(template, id=700 + n, name=names[n], run_started_at="2026-10-21T0%d:00:00Z" % n) for n in range(3)])
        faulted = [outcome_zip(outcome_of("r_%06dZ" % n, "item")) for n in range(2)]

        def outcomes(n):
            return stored(canary(), 700 + n, faulted[n]) if n < 2 else [stored(canary(), 702, None)[0]]

        def stamped(got):
            return len([r for r in got["reads"] if r["read"] == "outcome"])

        def record(got):
            # What the pass record keeps of a read: its runs, and a count of active Runs only when it was whole.
            return {"runs": got["runs"], "context": {"active_runs": 0 if got["complete"] else None}}
        first, _ = self.read(rows, *outcomes(0), *outcomes(1), *outcomes(2))
        self.assertEqual(([r["outcome"] for r in first["runs"]], stamped(first)), (["item", "item", None], 3))
        # The pass after: the two faults kept, the one with none read again.
        second, _ = self.read(rows, *outcomes(2), kept=records.known([record(first)]))
        self.assertEqual(([r["outcome"] for r in second["runs"]], stamped(second), second["complete"]),
                         (["item", "item", None], 1, True))
        # And the pass after that, two in a row having read none: nothing read.
        both = [record(first), record(second)]
        third, _ = self.read(rows, kept=records.known(both))
        self.assertEqual(([r["outcome"] for r in third["runs"]], stamped(third)), (["item", "item", None], 0))
        self.assertEqual(records.known([{"runs": []}] + both), records.known(both))
        # A re-run is another attempt, started at another time: read afresh.
        rerun = copy.deepcopy(rows)
        rerun["response"]["body"]["workflow_runs"][0]["run_started_at"] = "2026-10-21T09:00:00Z"
        fresh, _ = self.read(rerun, *outcomes(0), kept=records.known(both))
        self.assertEqual(stamped(fresh), 1)
        # A row that names no start of its attempt, or a key listed twice, is read afresh whatever is kept, and so is
        # one listed twice once as a fault and once as a Run still running.
        untimed = copy.deepcopy(rows)
        untimed["response"]["body"]["workflow_runs"][0]["run_started_at"] = None
        untimed["response"]["body"]["workflow_runs"][0]["created_at"] = "2026-10-21T00:00:00Z"
        got, _ = self.read(untimed, *outcomes(0), kept=records.known(both))
        self.assertEqual(stamped(got), 1)
        twice = copy.deepcopy(rows)
        twice["response"]["body"]["workflow_runs"][1] = dict(twice["response"]["body"]["workflow_runs"][0], id=799)
        got, _ = self.read(twice, *outcomes(0), *stored(canary(), 799, faulted[0]), kept=records.known(both))
        self.assertEqual(stamped(got), 2)
        running = copy.deepcopy(twice)
        running["response"]["body"]["workflow_runs"][1].update(status="in_progress", conclusion=None)
        got, _ = self.read(running, *outcomes(0), kept=records.known(both))
        self.assertEqual(stamped(got), 1)
        # An outcome list that cannot be read is stamped all the same, and leaves the list not whole: none read short
        # is never kept, however many passes read it so.
        short = copy.deepcopy(outcomes(2))
        short[0]["response"]["body"]["total_count"] = 2
        lost, _ = self.read(rows, *short, kept=records.known(both[:1]))
        self.assertEqual((lost["runs"][2]["outcome"], lost["complete"], stamped(lost)), (None, False, 1))
        again, _ = self.read(rows, *short, kept=records.known([record(lost)]))
        self.assertNotIn(("r_000002Z", "2026-10-21T02:00:00Z"), records.known([record(lost), record(again)]))
        self.assertNotIn(("r_000002Z", "2026-10-21T02:00:00Z"), records.known([record(lost), record(second)]))
        self.assertEqual(records.known([record(second), record(lost)]), records.known([record(lost)]))
        # A fault is kept from one record; none from one record alone, or after a fault, is not.
        self.assertIn(("r_000000Z", "2026-10-21T00:00:00Z"), records.known([record(lost)]))
        faulted_then_none = dict(record(second), runs=[dict(second["runs"][2], outcome="item")])
        self.assertEqual(records.known([faulted_then_none, record(second)]), {
            ("r_000000Z", "2026-10-21T00:00:00Z"): "item", ("r_000001Z", "2026-10-21T01:00:00Z"): "item"})
        # Kept by neither: a key a record holds twice; a Run that succeeded or is not done; a fault no outcome names,
        # or one that is not a name; one that names no Run or no start; and a record that is no pass record's runs.
        doubled = record(first)
        doubled["runs"] = first["runs"] + [dict(first["runs"][0], status="in_progress", conclusion=None, outcome=None)]
        self.assertNotIn(("r_000000Z", "2026-10-21T00:00:00Z"), records.known([doubled]))
        for change in ({"conclusion": "success"}, {"status": "in_progress"}, {"outcome": "late"}, {"outcome": []},
                       {"run": None}, {"started_at": None}):
            self.assertEqual(records.known([dict(record(first), runs=[dict(first["runs"][0], **change)])]), {}, change)
        self.assertEqual((records.known(None), records.known(record(first)), records.known([{"runs": None}]),
                          records.known([{"runs": ["x"]}])), ({}, {}, {}, {}))

    def test_a_status_or_a_conclusion_github_would_not_give_a_run_makes_the_list_short(self):
        self.assertEqual(self.read(listing("P-17", 3, rows={"name": NAME, "status": "waiting"}))[0]["runs"][0]["status"],
                         "queued")
        done = {"name": NAME, "status": "completed"}
        for change in (dict(done, conclusion="neutral"), dict(done, conclusion=None), {"name": NAME, "status": "odd"},
                       {"name": NAME, "conclusion": "success"}, {"name": NAME, "run_started_at": "soon",
                                                                 "created_at": None}, {"id": True}):
            got, _ = self.read(listing("P-17", 3, rows=change))
            self.assertEqual((got["runs"], got["complete"]), ([], False), change)

    def test_a_run_name_is_read_whole_or_not_at_all(self):
        # run-name/1: the example is read into its parts, an issue's Intent runs on an issue, and no counter-example
        # of the schema is a run-name; nor is an Intent no Lifecycle runs, a path of dots, or a number past nine digits.
        example = json.loads((ROOT / "examples" / "run-name.json").read_text())
        self.assertEqual(records.named(example.replace("fix-review-findings", "fix-findings"))["item"],
                         {"repo": "combsmith/markets", "type": "pull_request", "number": 521})
        self.assertEqual(records.named(NAME.replace("review-change", "judge-readiness"))["item"]["type"], "issue")
        for path in sorted((ROOT / "examples" / "invalid").glob("run-name.*.json")):
            self.assertIsNone(records.named(json.loads(path.read_text())), path.name)
        for name in (None, NAME + " ", NAME + "\n", NAME.replace("sf ", "sf  "), NAME.replace("#264", "#0"),
                     NAME.replace("#264", "#1234567890"), NAME.replace("review-change", "triage-issue"),
                     NAME.replace("combsmith/software-factory", "combsmith/.."), example):
            self.assertIsNone(records.named(name), name)

    def test_every_listing_the_trials_recorded_is_read(self):
        # trials/P-17.json and trials/P-22.json: every list of runs they hold, asked as the port asks it, is read with
        # each row recognized; the trial's runs are the Maintainer's dispatches of a Role-shaped workflow, so each is
        # counted, unnamed under the trial's names, and so unidentified once the second read still shows it.
        for name in ("P-17", "P-22"):
            for at, found in enumerate(exchanges(name)):
                if "/runs?" not in found["request"].get("call", "") or found["response"]["status"] != 200:
                    continue
                listed = found["response"]["body"]
                per = int(found["request"]["call"].split("per_page=")[1].split()[0].rstrip(","))
                if listed["total_count"] > per:
                    continue
                got, slept = self.read(asked(found), asked(found), per_page=per)
                ids = [{"run": str(r["id"]), "created_at": r["created_at"],
                        "status": "queued" if r["status"] in records.NOT_STARTED else r["status"]}
                       for r in listed["workflow_runs"]]
                self.assertEqual((got["runs"], got["unidentified"], got["complete"]), ([], ids, True), (name, at))

    @pending
    def test_an_artifact_download_a_trial_recorded_is_read_as_the_port_reads_it(self):
        # The Maintainer's ruling on #192: the download's one redirect goes to GitHub's artifact storage. No trial has
        # recorded one yet, so the host the transport allows is GitHub's documented one, not yet seen; the first trial
        # whose Run uploads an outcome records it, and this test then reads it.
        found = [(name.stem, at) for name in sorted((ROOT / "trials").glob("P-*.json"))
                 for at, e in enumerate(json.loads(name.read_text()).get("exchanges", []))
                 if (e.get("request") or {}).get("via") == "storage"]
        self.assertTrue(found)
        for name, at in found:
            moved = exchanges(name)[at - 1]["response"]["headers"]["location"]
            self.assertEqual(github.storage(moved), moved)


class Artifacts(unittest.TestCase):
    def test_a_runs_applied_record_is_read_whole_or_not_at_all(self):  # decision 0061
        # What a Run recorded of its writes, read as its outcome is: whole for one that uploaded none, and never matched
        # to a write when it cannot be read, is not applied/1 or names another Run.
        def as_applied(found):
            found[0]["request"]["call"] = found[0]["request"]["call"].replace("name=outcome", "name=applied")
            for a in found[0]["response"]["body"]["artifacts"]:
                a["name"] = artifacts.APPLIED
            return found
        done = json.loads((ROOT / "examples" / "applied.approval.json").read_text())
        repo, github_id = canary(), 39100000001

        def read(record, member="applied.json"):
            zipped = outcome_zip(record, member) if record is not None else None
            return artifacts.applied(github.Replay(as_applied(stored(repo, github_id, zipped))), repo, github_id,
                                     done["run"])
        self.assertEqual(read(done), (done, True))
        self.assertEqual(read(None), (None, True))
        for record, member in ((dict(done, run="r_01JA7R"), "applied.json"), (dict(done, effects="none"), "applied.json"),
                               (done, "outcome.json"), ([done], "applied.json")):
            self.assertEqual(read(record, member), (None, False), (member, record if isinstance(record, list) else
                                                                    record.get("run")))
        # A record as large as applied/1 may be is read; one larger is not read at all.
        text = json.dumps(done)
        self.assertEqual(read(text + " " * (artifacts.APPLIED_MOST - len(text))), (done, True))
        self.assertEqual(read(text + " " * (artifacts.APPLIED_MOST - len(text) + 1)), (None, False))
        # The archive is held to an outcome's bound and never downloaded under a pass record's: one listed larger is
        # not downloaded at all (issue 329). The listing alone is answered; a download would find no answer.
        listed = as_applied(stored(repo, github_id, outcome_zip(done, "applied.json"),
                                   size_in_bytes=artifacts.ZIPPED + 1))[:1]
        self.assertEqual(artifacts.applied(github.Replay(listed), repo, github_id, done["run"]), (None, False))

    RUN = "r_01JA6Z"

    def read(self, zipped, **listed):
        return artifacts.outcome(github.Replay(stored("o/r", 7, zipped, **listed)), "o/r", 7, self.RUN)

    def test_a_runs_outcome_is_read_from_its_one_file_and_held_to_outcome_1(self):
        for fault in ("item", "capacity", "environment", "superseded"):
            self.assertEqual(self.read(outcome_zip(outcome_of(self.RUN, fault))), (fault, True), fault)
        # A listing that gives no digest is read by its size alone.
        zipped = outcome_zip(outcome_of(self.RUN, "item"))
        self.assertEqual(self.read(zipped, digest=None), ("item", True))
        # A Run that left no outcome, as a killed one does, is read whole with none, and so is one past its retention,
        # which is never downloaded.
        self.assertEqual(artifacts.outcome(github.Replay(stored("o/r", 7, None)), "o/r", 7, self.RUN), (None, True))
        expired = stored("o/r", 7, zipped, expired=True)[:1]
        self.assertEqual(artifacts.outcome(github.Replay(expired), "o/r", 7, self.RUN), (None, True))

    def test_an_outcome_that_cannot_be_read_whole_is_not_whole(self):
        good = outcome_of(self.RUN, "item")
        zipped = outcome_zip(good)
        for listed in ({"expired": None}, {"expired": "false"}, {"size_in_bytes": 0}, {"size_in_bytes": True}, {"size_in_bytes": len(zipped) + 1},
                       {"digest": "sha256:" + "0" * 64}, {"digest": "md5:x"}, {"id": True}, {"id": 0}):
            transport = github.Replay(stored("o/r", 7, zipped, **listed))
            self.assertEqual(artifacts.outcome(transport, "o/r", 7, self.RUN), (None, False), listed)
        for record in (outcome_zip(good, member="result.json"), outcome_zip(good, more=("other.json",)),
                       outcome_zip(" " * (artifacts.HELD + 1)), outcome_zip(b"\xff\xfe"), outcome_zip("[]"),
                       outcome_zip(dict(good, run="r_OTHER1")), outcome_zip(dict(good, outcome=None)),
                       outcome_zip(dict(good, reason="A sentence.")), b"PK\x03\x04 not a zip"):
            self.assertEqual(self.read(record), (None, False), record[:40])
        # A zip over the bound is not read, though it holds an outcome that could be.
        wide = io.BytesIO()
        with zipfile.ZipFile(wide, "w") as archive:
            archive.writestr(artifacts.MEMBER, json.dumps(good))
            archive.comment = b" " * 65535
        self.assertGreater(len(wide.getvalue()), artifacts.ZIPPED)
        self.assertEqual(self.read(wide.getvalue()), (None, False))
        # A list that is not what its count says, or holds an artifact of another name, is not whole.
        miscounted = stored("o/r", 7, zipped)
        miscounted[0]["response"]["body"]["total_count"] = 2
        self.assertEqual(artifacts.outcome(github.Replay(miscounted), "o/r", 7, self.RUN), (None, False))
        for body in ({"total_count": 1, "artifacts": [{"name": "result"}]},
                     {"total_count": None, "artifacts": []}, {"artifacts": None, "total_count": 0}):
            listing_ = stored("o/r", 7, None)
            listing_[0]["response"]["body"] = body
            self.assertEqual(artifacts.outcome(github.Replay(listing_), "o/r", 7, self.RUN), (None, False), body)
        # Two artifacts of the name, each one that could be read, are not read as one.
        twice = stored("o/r", 7, zipped)
        listed = twice[0]["response"]["body"]
        listed.update(total_count=2, artifacts=listed["artifacts"] * 2)
        self.assertEqual(artifacts.outcome(github.Replay(twice), "o/r", 7, self.RUN), (None, False))
        # An answer that is no answer is refused: the list's, the download's and the storage's.
        for at, status in ((0, 404), (2, 403)):
            found = stored("o/r", 7, zipped)
            found[at]["response"]["status"] = status
            with self.assertRaises(github.Unanswered, msg=at):
                artifacts.outcome(github.Replay(found), "o/r", 7, self.RUN)

    def test_an_outcome_is_held_in_the_bounds_before_it_is_read_out(self):
        # A file the zip says is over the bound is never read.
        wide = io.BytesIO()
        with zipfile.ZipFile(wide, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(artifacts.MEMBER, "{" + " " * (10 * artifacts.HELD) + "}")
        self.assertIsNone(artifacts._member(wide.getvalue()))
        self.assertEqual(artifacts._member(outcome_zip("{}")), b"{}")
        # ... and never opened, so no byte of it is decompressed.
        opened = []
        real = zipfile.ZipFile.open
        try:
            zipfile.ZipFile.open = lambda *a, **k: opened.append(a) or real(*a, **k)
            self.assertIsNone(artifacts._member(wide.getvalue()))
        finally:
            zipfile.ZipFile.open = real
        self.assertEqual(opened, [])
        # An encrypted file, which Python will not open without its password, is not read.
        locked = bytearray(outcome_zip("{}"))
        for header, flag in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            at = bytes(locked).index(header) + flag
            locked[at] |= 0x1
        self.assertIsNone(artifacts._member(bytes(locked)))
        # Only a file stored or deflated is read: bzip2 and LZMA decompress a whole chunk past any bound Python sets.
        for method in (zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA, zipfile.ZIP_STORED):
            packed = io.BytesIO()
            with zipfile.ZipFile(packed, "w", method) as archive:
                archive.writestr(artifacts.MEMBER, "{}")
            self.assertEqual(artifacts._member(packed.getvalue()), b"{}" if method == zipfile.ZIP_STORED else None, method)


APPROVER = "donpetry-bot"        # the machine user, as config/defaults.json names the approver
MACHINE = (281750570, "User")     # its account, as trials/P-7.json records it


class Router:
    """A transport that answers a permission or a compare from a table it is given, and anything else from a replay.
    A compare not in the table is the replay's, as the snapshot's own compares of the diff and the files are (issue
    284), and one the replay does not hold either answers 404. The permission's trial is #222's."""

    def __init__(self, replay, permissions=None, compares=None):
        self.replay, self.permissions, self.compares, self.asked = replay, dict(permissions or {}), dict(compares or {}), []

    def send(self, req):
        path = req["path"]
        if "/collaborators/" in path:
            login = path.split("/collaborators/")[1].split("/")[0]
            self.asked.append(login)
            level = self.permissions.get(login, "none")
            if level == "missing":
                return {"status": 404, "headers": {}, "body": {"message": "Not Found"}}
            return {"status": 200, "headers": {}, "body": {"permission": level}}
        if "/compare/" in path:
            commit = path.split("...")[1]
            if commit in self.compares:
                return {"status": 200, "headers": {}, "body": self.compares[commit]}
            # The snapshot's own compares, of the diff and the files at the head, are the replay's (issue 284).
            try:
                return self.replay.send(req)
            except github.Unanswered:
                return {"status": 404, "headers": {}, "body": {"message": "Not Found"}}
        return self.replay.send(req)


def p7_pull() -> dict:
    """Pull request 34 of trials/P-7.json, as the facts port's first read would give it."""
    found = exchanges("P-7")
    return next(copy.deepcopy(e["response"]["body"]) for e in found
                if e["request"].get("call", "").startswith("GET /repos/") and "/pulls/34" in e["request"]["call"]
                and isinstance(e["response"]["body"], dict) and e["response"]["body"].get("number") == 34)


BASE_HEAD = "a" * 40


def reviews_read(at: int) -> github.Replay:
    """P-7's read of pull request 34's reviews, asked as the port asks it, a full page at a time."""
    found = copy.deepcopy(exchanges("P-7")[at])
    words = found["request"]["call"].split()
    found["request"]["call"] = " ".join([words[0], words[1] + "?per_page=100"] + words[2:])
    return github.Replay([found])


class Timeline(unittest.TestCase):
    def accounts(self, transport, lenses=None, factory=()):
        return timeline.Accounts(transport, canary(), MACHINE, lenses or {}, factory)

    def test_an_actor_is_told_by_its_account_type_and_the_configuration(self):
        # Decision 0005, L-57: the approver is the machine user and no other; a Bot is a Lens only as the caller names
        # its App, read as the Lens's name; any other Bot is an App; any other User is a person, whose write access is
        # the collaborator permission's, admin, maintain or write and never triage, read once a login.
        router = Router(github.Replay([]), {"don-petry": "admin", "writer": "write", "triager": "triage",
                                            APPROVER: "write"})
        accounts = self.accounts(router, {(7, "Bot"): "pr-review"})
        # The machine user is its account, by id: its approval stands only while it can write, so that is read too.
        self.assertEqual(accounts.actor({"login": APPROVER, "id": MACHINE[0], "type": "User"}),
                         {"kind": "machine_user", "name": APPROVER, "can_write": True})
        self.assertEqual(accounts.actor({"login": APPROVER, "id": 1, "type": "User"})["kind"], "human")
        # The machine user without write access is read so: its approval then stands for nothing.
        lost = Router(github.Replay([]), {APPROVER: "read"})
        self.assertIs(self.accounts(lost).actor({"login": APPROVER, "id": MACHINE[0], "type": "User"})["can_write"], False)
        self.assertEqual(accounts.actor({"login": "combsmith-sf-pr-review[bot]", "id": 7, "type": "Bot"}),
                         {"kind": "lens", "name": "pr-review", "can_write": False})
        self.assertEqual(accounts.actor({"login": "coderabbitai[bot]", "id": 8, "type": "Bot"})["kind"], "app")
        for login, write in (("don-petry", True), ("writer", True), ("triager", False), ("stranger", False)):
            self.assertEqual(accounts.actor({"login": login, "id": 9, "type": "User"}),
                             {"kind": "human", "name": login, "can_write": write}, login)
        accounts.actor({"login": "don-petry", "id": 9, "type": "User"})
        self.assertEqual(router.asked.count("don-petry"), 1)
        for broken in (None, {"login": "x[bot]", "id": 1, "type": "User"}, {"login": "x", "id": "1", "type": "User"},
                       {"login": "x", "id": 1, "type": "Organization"}, {"login": "", "id": 1, "type": "User"},
                       {"login": "..", "id": 1, "type": "User"}, {"login": "a/b", "id": 1, "type": "User"}):
            with self.assertRaises(github.Unanswered, msg=broken):
                accounts.actor(broken)
        # A permission GitHub does not give, and a login the endpoint cannot find, are refused, never read as none.
        for level in ("owner", "missing"):
            odd = Router(github.Replay([]), {"x": level})
            with self.assertRaises(github.Unanswered, msg=level):
                self.accounts(odd).actor({"login": "x", "id": 1, "type": "User"})

    def test_reviews_are_read_with_their_commit_content_and_who_dismissed_them(self):
        # trials/P-7.json: the reviewer App's and the machine user's approvals were dismissed, by the Maintainer and by
        # the trial-author App, and the machine user approved again at the new head. The timeline says who dismissed
        # each and what it was before; the content of each review's commit is its diff against the merge base.
        events, whole = timeline.events(replay("P-7", 16), p7_pull())
        self.assertIs(whole, True)
        compares = {"f03b9ecd01f6b1b34631a42b3d73ed3bd8cdfebb": "diff --git a/x b/x\n",
                    "355cb4d9626f8f434dff093d76eb4535a6e7e93e": "diff --git a/y b/y\n"}
        router = Router(reviews_read(22), {"don-petry": "admin", APPROVER: "write"}, compares)
        kept = {}
        got, whole = timeline.reviews(router, p7_pull(), events, self.accounts(router), BASE_HEAD, kept)
        self.assertIs(whole, True)
        # The list is kept as GitHub gave it, for reconciliation (decision 0061).
        self.assertEqual(([r.get("node_id") for r in kept["reviews"][0]], kept["reviews"][1]),
                         ([r.get("node_id") for r in body("P-7", 22)], True))
        self.assertEqual(len(kept["reviews"][0]), len(got))
        content = {c: "sha256:" + hashlib.sha256(b.encode()).hexdigest() for c, b in compares.items()}
        self.assertEqual([(r["by"]["kind"], r["by"]["name"], r["state"], r["content_id"]) for r in got],
                         [("app", "coderabbitai[bot]", "dismissed", content["f03b9ecd01f6b1b34631a42b3d73ed3bd8cdfebb"]),
                          ("machine_user", APPROVER, "dismissed", content["f03b9ecd01f6b1b34631a42b3d73ed3bd8cdfebb"]),
                          ("machine_user", APPROVER, "approved", content["355cb4d9626f8f434dff093d76eb4535a6e7e93e"])])
        self.assertEqual([(r["dismissed_by"] and r["dismissed_by"]["name"], r["dismissed_from"]) for r in got],
                         [("don-petry", "approved"), ("combsmith-sf-trial-author[bot]", "approved"), (None, None)])
        self.assertEqual(got[0]["dismissed_by"], {"kind": "human", "name": "don-petry", "can_write": True})
        # No text of GitHub's is in the facts: the dismissal's message stays on GitHub.
        message = next(e["dismissed_review"]["dismissal_message"] for e in events if e.get("event") == "review_dismissed"
                       and e["dismissed_review"].get("dismissal_message"))
        self.assertNotIn(message, json.dumps(got))
        self.assertNotIn(message[:20], json.dumps(got))

    def test_a_dismissed_review_the_timeline_does_not_explain_is_refused(self):
        router = Router(reviews_read(22), {"don-petry": "admin", APPROVER: "write"}, {"f03b9ecd01f6b1b34631a42b3d73ed3bd8cdfebb": "d",
                                                                    "355cb4d9626f8f434dff093d76eb4535a6e7e93e": "e"})
        with self.assertRaises(github.Unanswered):
            timeline.reviews(router, p7_pull(), [], self.accounts(router), BASE_HEAD)

    def test_a_reviews_commit_too_large_to_diff_or_gone_is_its_own_id(self):
        commit = "f03b9ecd01f6b1b34631a42b3d73ed3bd8cdfebb"
        own = "sha256:" + hashlib.sha256(commit.encode()).hexdigest()
        self.assertEqual(timeline._content(Router(github.Replay([])), canary(), BASE_HEAD, commit), own)
        too_large = copy.deepcopy(exchanges("P-29.truncated")[4])
        too_large["request"]["call"] = "GET /repos/%s/compare/%s...%s" % (canary(), BASE_HEAD, commit)
        self.assertEqual(timeline._content(github.Replay([too_large]), canary(), BASE_HEAD, commit), own)
        other = copy.deepcopy(too_large)
        other["response"]["body"]["errors"][0]["code"] = "not_acceptable"
        with self.assertRaises(github.Unanswered):
            timeline._content(github.Replay([other]), canary(), BASE_HEAD, commit)

    def test_a_reviews_content_is_the_compare_of_its_commit_against_the_bases_head(self):
        # trials/P-29.base.json: the first head compared against the moved main is the pull request's own content.
        found = exchanges("P-29.base")
        base, head = found[17]["request"]["call"].split()[1].split("/compare/")[1].split("...")
        got = timeline._content(replay("P-29.base", 17), json.loads((ROOT / "trials" / "P-29.base.json").read_text())["repo"],
                                base, head)
        self.assertEqual(got, "sha256:" + body("P-29.base", 24)["compare, moved main...first head"])

    def test_who_last_acted_with_write_access_and_the_factorys_acts_since(self):
        # trials/P-7.json's timeline: the Maintainer, a person with write access, dismissed the App's approval; the
        # machine user's approval after that is an act; a mention or a subscription is nobody's act.
        # The machine user approved twice; the first approval was dismissed after it, and is still an act.
        events, _ = timeline.events(replay("P-7", 16), p7_pull())
        router = Router(github.Replay([]), {"don-petry": "admin", APPROVER: "write"})
        got = timeline.since_writer(events, self.accounts(router))
        dismissed = next(e["created_at"] for e in events if e.get("event") == "review_dismissed"
                         and e["actor"]["login"] == "don-petry")
        self.assertEqual(got, {"last_writer_action_at": dismissed, "acts_since_writer": 1})
        nobody = Router(github.Replay([]), {APPROVER: "write"})
        self.assertEqual(timeline.since_writer(events, self.accounts(nobody)),
                         {"last_writer_action_at": None, "acts_since_writer": 2})
        # A mention or a subscription names whom an act touched: nobody's action, and nobody's access is asked for it.
        mentions = [e for e in events if e.get("event") in ("mentioned", "subscribed")]
        quiet = Router(github.Replay([]))
        self.assertEqual(timeline.since_writer(mentions, self.accounts(quiet)),
                         {"last_writer_action_at": None, "acts_since_writer": 0})
        self.assertEqual(quiet.asked, [])
        # An act before the writer's last action is not counted; one after is.
        labeled = {"event": "labeled", "label": {"name": "factory:admit"},
                   "actor": {"login": "combsmith-sf-controller[bot]", "id": 5, "type": "Bot"}}
        before, after = dict(labeled, created_at="2026-10-19T17:00:00Z"), dict(labeled, created_at="2026-10-19T20:00:00Z")
        tie = dict(labeled, created_at=dismissed)
        dequeued = {"event": "removed_from_merge_queue", "created_at": "2026-10-19T20:01:00Z",
                    "actor": {"login": "combsmith-sf-controller[bot]", "id": 5, "type": "Bot"}}
        factory = self.accounts(router, factory={(5, "Bot")})
        self.assertEqual(timeline.since_writer([before] + events + [tie, after, dequeued], factory)["acts_since_writer"], 4)

    def test_label_events_are_read_with_who_made_them_and_when(self):
        # No fixture yet holds a label on a pull request's timeline (P-41, issue 250): an event in the timeline's shape.
        at = "2026-10-19T18:00:00Z"
        events = [{"event": "labeled", "label": {"name": "factory:hold"}, "created_at": at,
                   "actor": {"login": "don-petry", "id": 9, "type": "User"}},
                  {"event": "unlabeled", "label": {"name": "factory:hold"}, "created_at": at,
                   "actor": {"login": "combsmith-sf-controller[bot]", "id": 5, "type": "Bot"}},
                  {"event": "commented", "created_at": at, "actor": {"login": "don-petry", "id": 9, "type": "User"}}]
        router = Router(github.Replay([]), {"don-petry": "write"})
        got = timeline.label_events(events, self.accounts(router))
        self.assertEqual(got, [{"label": "factory:hold", "action": "labeled", "at": at,
                                "by": {"kind": "human", "name": "don-petry", "can_write": True}},
                               {"label": "factory:hold", "action": "unlabeled", "at": at,
                                "by": {"kind": "app", "name": "combsmith-sf-controller[bot]", "can_write": False}}])
        for broken in ({"label": None}, {"label": {"name": ""}}, {"created_at": "soon"}, {"actor": None}):
            event = dict(events[0], **broken)
            with self.assertRaises(github.Unanswered, msg=broken):
                timeline.label_events([event], self.accounts(router))

    def test_a_timeline_is_read_page_by_page_to_a_page_short_of_a_full_one(self):
        # A page is followed only as the link header names a next one, never by its length (section 3.3).
        first = copy.deepcopy(exchanges("P-7")[16])
        first["response"]["body"] = [{"event": "subscribed"}] * 3
        first["response"]["headers"]["link"] = '<https://api.github.com/x?page=2>; rel="next", <https://api.github.com/x?page=2>; rel="last"' 
        second = copy.deepcopy(exchanges("P-7")[16])
        words = second["request"]["call"].split()
        second["request"]["call"] = " ".join([words[0], words[1] + "&page=2"] + words[2:])
        second["response"]["body"] = [{"event": "mentioned"}]
        got, whole = timeline.events(github.Replay([first, second]), p7_pull())
        self.assertEqual((len(got), whole), (4, True))
        # A full page with no next named is the last one.
        full = copy.deepcopy(exchanges("P-7")[16])
        full["response"]["body"] = [{"event": "subscribed"}] * timeline.PAGE
        self.assertEqual(len(timeline.events(github.Replay([full]), p7_pull())[0]), timeline.PAGE)

    def test_a_review_github_would_not_give_is_refused_and_a_pending_one_is_not_read(self):
        compares = {"f03b9ecd01f6b1b34631a42b3d73ed3bd8cdfebb": "d", "355cb4d9626f8f434dff093d76eb4535a6e7e93e": "e"}
        events, _ = timeline.events(replay("P-7", 16), p7_pull())
        perms = {"don-petry": "admin", APPROVER: "write"}

        def with_reviews(change, timeline_change=None):
            read = reviews_read(22)
            listed = read._left[0][1]["body"]
            change(listed)
            router = Router(read, perms, compares)
            told = copy.deepcopy(events)
            if timeline_change:
                timeline_change(told)
            return timeline.reviews(router, p7_pull(), told, self.accounts(router), BASE_HEAD)

        got, _ = with_reviews(lambda listed: listed.append(dict(listed[-1], state="PENDING", id=1)))
        self.assertEqual(len(got), 3)
        with self.assertRaises(github.Unanswered):
            with_reviews(lambda listed: listed[-1].update(state="WEIRD"))
        with self.assertRaises(github.Unanswered):
            with_reviews(lambda listed: None, lambda told: [e["dismissed_review"].update(state="odd") for e in told
                                                            if e.get("event") == "review_dismissed"])
        with self.assertRaises(github.Unanswered):
            with_reviews(lambda listed: listed[-1].update(commit_id="short"))
        with self.assertRaises(github.Unanswered):
            with_reviews(lambda listed: listed.append("not a review"))
        with self.assertRaises(github.Unanswered):
            timeline._content(Router(github.Replay([]), compares=compares), canary(), "x", "f03b9ecd01f6b1b34631a42b3d73ed3bd8cdfebb")

    def test_only_the_factorys_identities_make_acts(self):
        # An App's approval is no act of the Factory's, and nor is a label a person without write access placed.
        at = "2026-10-19T20:00:00Z"
        events = [{"event": "reviewed", "state": "approved", "submitted_at": at,
                   "user": {"login": "coderabbitai[bot]", "id": 8, "type": "Bot"}},
                  {"event": "labeled", "label": {"name": "x"}, "created_at": at,
                   "actor": {"login": "stranger", "id": 3, "type": "User"}},
                  {"event": "added_to_merge_queue", "created_at": at,
                   "actor": {"login": "combsmith-sf-controller[bot]", "id": 5, "type": "Bot"}},
                  {"event": "reviewed", "state": "approved", "submitted_at": at,
                   "user": {"login": "combsmith-sf-controller[bot]", "id": 5, "type": "Bot"}}]
        router = Router(github.Replay([]), {})
        self.assertEqual(timeline.since_writer(events, self.accounts(router, factory={(5, "Bot")})),
                         {"last_writer_action_at": None, "acts_since_writer": 1})
        # An App that is not the Factory's labelling or queueing is no act of the Factory's.
        self.assertEqual(timeline.since_writer(events, self.accounts(router))["acts_since_writer"], 0)
        # An action an App took with a person's token is not that person's.
        via = {"event": "commented", "created_at": at, "performed_via_github_app": {"id": 1},
               "actor": {"login": "don-petry", "id": 9, "type": "User"}}
        writer = Router(github.Replay([]), {"don-petry": "admin"})
        self.assertIsNone(timeline.since_writer([via], self.accounts(writer))["last_writer_action_at"])

    def test_what_each_credential_is_shown_of_a_permission_is_recorded(self):
        # L-57: what each credential is shown is recorded by a trial. trials/P-27.json reads the permission as the
        # Maintainer; trials/P-47.json as the reader App, the credential the port reads it with, narrowed to
        # metadata: read and to contents: read. Each answers the same: the owner admin, the machine user and a
        # collaborator write, and an outsider read. GitHub's permission folds maintain into write, as role_name says,
        # so write access is read the same whichever the role.
        shown, reads = {}, []
        for path in sorted((ROOT / "trials").glob("P-*.json")):
            narrowed = None
            for e in json.loads(path.read_text())["exchanges"]:
                call = e["request"].get("call", "")
                if call.endswith("/access_tokens") and isinstance(e["request"].get("body"), dict):
                    # Each read is made with the token the mint before it narrowed, until it is revoked.
                    narrowed = "%s: read" % next(iter(e["request"]["body"]["permissions"]))
                if "/collaborators/" in call and "/permission" in call and (e["request"].get("as") or {}).get("kind") == "app":
                    reads.append(e)
                    login = call.split("/collaborators/")[1].split("/")[0]
                    shown.setdefault(login, {})[narrowed] = (e["response"]["status"], e["response"]["body"]["permission"],
                                                             e["response"]["body"]["role_name"])
        self.assertTrue(reads)
        self.assertEqual({login: set(by.values()) for login, by in shown.items()},
                         {"don-petry": {(200, "admin", "admin")}, "donpetry-bot": {(200, "write", "maintain")},
                          "Joaolfelicio": {(200, "write", "write")}, "octocat": {(200, "read", "read")}})
        self.assertTrue(all(set(by) == {"metadata: read", "contents: read"} for by in shown.values()))
        # The port reads `permission`, which folds maintain into write: the machine user, whose role_name is maintain,
        # has write access, as the ruling on issue 222 has it.
        self.assertEqual(next(iter(shown["donpetry-bot"].values()))[1:], ("write", "maintain"))
        self.assertIn("write", timeline.WRITE)
        # Each read's least grant is the one GitHub's x-accepted-github-permissions names, and config/apps.json names it
        # so: the canary is public, so a token without the grant read the activity all the same (issue 231).
        needs = json.loads((ROOT / "config" / "apps.json").read_text())["needs"]
        p47 = exchanges("P-47")
        for fragment, need in (("/permission", "read:facts.actor.can_write"), ("/activity?", "read:facts.last_pusher")):
            accepted = {e["response"]["headers"].get("x-accepted-github-permissions") for e in p47
                        if fragment in e["request"]["call"]}
            self.assertEqual(accepted, {"%s=%s" % (needs[need]["permission"], needs[need]["level"])}, need)
        for login, (_, permission, _) in ((l, next(iter(by.values()))) for l, by in shown.items()):
            self.assertEqual(permission in timeline.WRITE, login != "octocat", login)

    def test_a_permission_is_read_as_github_answers_it(self):
        # trials/P-27.json: the permission endpoint, asked of a collaborator with read, answers read: no write access.
        found = next(e for e in exchanges("P-27") if "/permission" in e["request"].get("call", ""))
        login = found["request"]["call"].split("/collaborators/")[1].split("/")[0]
        accounts = timeline.Accounts(github.Replay([found]), canary(), MACHINE, {})
        who = found["response"]["body"]["user"]
        self.assertEqual(accounts.actor({"login": login, "id": who["id"], "type": who["type"]}),
                         {"kind": "human", "name": login, "can_write": False})

    def test_a_timeline_or_a_list_of_reviews_that_is_not_a_list_is_not_whole(self):
        broken = copy.deepcopy(exchanges("P-7")[16])
        broken["response"]["body"] = {"message": "x"}
        self.assertEqual(timeline.events(github.Replay([broken]), p7_pull()), ([], False))
        reviews = reviews_read(22)
        reviews._left[0][1]["body"] = {"message": "x"}
        router = Router(reviews)
        self.assertEqual(timeline.reviews(router, p7_pull(), [], self.accounts(router), BASE_HEAD), ([], False))
        # An item of the timeline that is not an object is refused, never skipped.
        with self.assertRaises(github.Unanswered):
            timeline.label_events(["labeled"], self.accounts(router))
        with self.assertRaises(github.Unanswered):
            timeline.since_writer([None], self.accounts(router))


def p32_pull() -> dict:
    """Pull request 216 of trials/P-32.json, as its GraphQL read records it."""
    return copy.deepcopy(exchanges("P-32")[1]["response"]["body"]["data"]["repository"]["pullRequests"]["nodes"][0])


def checks_answer(node: dict, after=None) -> dict:
    """An exchange of the port's own checks query, answered with P-32's pull request as GitHub gave it."""
    repo = "combsmith/software-factory"
    owner, name = repo.split("/")
    asked = {"query": checks.QUERY, "variables": {"owner": owner, "name": name, "number": node["number"], "after": after}}
    return {"request": {"via": "graphql", "call": "POST /graphql", "headers": {}, "body": asked},
            "response": {"status": 200, "headers": {}, "body": {"data": {"repository": {"pullRequest": node}}}}}


def as_pull(node: dict) -> dict:
    return {"number": node["number"], "head": {"sha": node["headRefOid"]},
            "base": {"repo": {"full_name": "combsmith/software-factory"}}}


class Checks(unittest.TestCase):
    def test_every_check_run_on_the_head_is_read_with_its_name_app_and_workflow(self):
        # trials/P-32.json: pull request 216's 18 checks, as GitHub's rollup gave them; a check no workflow file names,
        # CodeQL's default set-up, has none, and the port passes that on.
        node = p32_pull()
        got = checks.read(github.Replay([checks_answer(node)]), as_pull(node))
        nodes = node["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"]
        self.assertEqual(len(got["checks"]), len([n for n in nodes if n["__typename"] == "CheckRun"]))
        self.assertEqual(got["checks"][0], {"name": "Analyze (actions)", "app_id": 15368, "workflow": None,
                                            "conclusion": "success", "completed_at": "2026-10-20T00:51:22Z"})
        self.assertIn({"name": "checks", "app_id": 15368, "workflow": ".github/workflows/verify.yml",
                       "conclusion": "success", "completed_at": "2026-10-20T01:01:25Z"}, got["checks"])
        self.assertEqual((got["complete"], got["queue"]), (True, True))

    def test_a_check_still_running_gives_its_status_and_no_time(self):
        node = {"__typename": "CheckRun", "name": "verify", "conclusion": None, "status": "IN_PROGRESS",
                "completedAt": None, "checkSuite": {"app": {"databaseId": 15368}, "workflowRun": None}}
        self.assertEqual(checks.check(node)["conclusion"], "in_progress")
        for broken in ({"name": ""}, {"checkSuite": {"app": None}}, {"status": "in progress"},
                       {"conclusion": "SUCCESS"}, {"completedAt": "2026-10-20T00:51:22Z"},
                       {"checkSuite": {"app": {"databaseId": 1}, "workflowRun": {"file": {"path": ""}}}},
                       {"checkSuite": {"app": {"databaseId": 1}, "workflowRun": "verify"}},
                       {"checkSuite": {"app": {"databaseId": 1}, "workflowRun": {"file": "verify.yml"}}}):
            with self.assertRaises(github.Unanswered, msg=broken):
                checks.check(dict(node, **broken))

    def test_a_rollup_of_another_commit_or_cut_short_is_not_read_whole(self):
        node = p32_pull()
        moved = as_pull(node)
        moved["head"]["sha"] = "0" * 40
        with self.assertRaises(github.Unanswered):
            checks.read(github.Replay([checks_answer(node)]), moved)
        # The pull request names the head, but the rollup is another commit's.
        other = p32_pull()
        other["commits"]["nodes"][0]["commit"]["oid"] = "0" * 40
        with self.assertRaises(github.Unanswered):
            checks.read(github.Replay([checks_answer(other)]), as_pull(p32_pull()))
        short = p32_pull()
        short["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["pageInfo"] = {"hasNextPage": None}
        self.assertIs(checks.read(github.Replay([checks_answer(short)]), as_pull(short))["complete"], False)
        # A next page is read by its cursor, and the list is whole when that page has none after it.
        first, second = p32_pull(), p32_pull()
        first["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["pageInfo"] = {"hasNextPage": True,
                                                                                            "endCursor": "c1"}
        for at, page in enumerate((first, second)):
            contexts = page["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]
            contexts["totalCount"] = 36
            for n, node in enumerate(contexts["nodes"]):
                node["id"] = "CR_%d_%d" % (at, n)
        got = checks.read(github.Replay([checks_answer(first), checks_answer(second, "c1")]), as_pull(first))
        runs = [n for n in second["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"]
                if n["__typename"] == "CheckRun"]
        self.assertEqual((len(got["checks"]), got["complete"]), (2 * len(runs), True))
        # Over two pages, a context read twice, or one with no id to tell it by, is a short read: a rollup that moved
        # between pages can repeat a passing check and leave out a failing one.
        for change in ("CR_0_0", None):
            again = copy.deepcopy(second)
            again["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"][0]["id"] = change
            got = checks.read(github.Replay([checks_answer(first), checks_answer(again, "c1")]), as_pull(first))
            self.assertIs(got["complete"], False, change)
        # A cursor that repeats, or a next page past the count, ends the read short rather than looping.
        looping = copy.deepcopy(first)
        looping["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["totalCount"] = 100
        got = checks.read(github.Replay([checks_answer(looping), checks_answer(looping, "c1")]), as_pull(first))
        self.assertIs(got["complete"], False)
        past = copy.deepcopy(first)
        past["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["totalCount"] = 18
        self.assertIs(checks.read(github.Replay([checks_answer(past)]), as_pull(past))["complete"], False)
        # The merge queue's entry is an object or null, and any other shape, or none at all, is refused.
        for entry in (False, "queued", 1, []):
            odd = p32_pull()
            odd["mergeQueueEntry"] = entry
            with self.assertRaises(github.Unanswered, msg=entry):
                checks.read(github.Replay([checks_answer(odd)]), as_pull(odd))
        missing = p32_pull()
        del missing["mergeQueueEntry"]
        with self.assertRaises(github.Unanswered):
            checks.read(github.Replay([checks_answer(missing)]), as_pull(missing))
        # A pull request with no rollup has no checks, read whole; a status context names no App and is no check.
        bare = p32_pull()
        bare["commits"]["nodes"][0]["commit"]["statusCheckRollup"] = None
        self.assertEqual(checks.read(github.Replay([checks_answer(bare)]), as_pull(bare))["checks"], [])
        with self.assertRaises(github.Unanswered):
            odd = p32_pull()
            odd["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"].append({"__typename": "Odd"})
            checks.read(github.Replay([checks_answer(odd)]), as_pull(odd))

    def test_a_rollup_whose_count_is_not_what_was_read_is_not_whole(self):
        # GitHub counts the rollup's contexts: a last page that says no next one, but leaves counted contexts unread,
        # or a count that changed between pages, is a short read.
        for count in (19, None, True):
            node = p32_pull()
            node["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["totalCount"] = count
            self.assertIs(checks.read(github.Replay([checks_answer(node)]), as_pull(node))["complete"], False, count)
        first, second = p32_pull(), p32_pull()
        first["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"].update(
            totalCount=36, pageInfo={"hasNextPage": True, "endCursor": "c1"})
        second["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["totalCount"] = 37
        for at, page in enumerate((first, second)):
            for n, node in enumerate(page["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"]):
                node["id"] = "CR_%d_%d" % (at, n)
        got = checks.read(github.Replay([checks_answer(first), checks_answer(second, "c1")]), as_pull(first))
        self.assertIs(got["complete"], False)

    def test_a_rollup_read_while_the_head_moved_is_refused(self):
        # The rollup is of the head the port asked about, but the pull request names another head by then.
        node = p32_pull()
        asked = as_pull(node)
        node["headRefOid"] = "0" * 40
        with self.assertRaises(github.Unanswered):
            checks.read(github.Replay([checks_answer(node)]), asked)


def p26_files() -> dict:
    """Pull request 26's one file, in the shape P-29.truncated's list of files gives."""
    found = copy.deepcopy(exchanges("P-29.truncated")[13])
    found["request"]["call"] = "GET /repos/%s/pulls/26/files?per_page=100" % canary()
    found["response"]["body"] = [dict(found["response"]["body"][0], filename="p28-p29/content.txt", status="added")]
    return found


def p26_reviews() -> dict:
    found = copy.deepcopy(exchanges("P-7")[22])
    found["request"]["call"] = "GET /repos/%s/pulls/26/reviews?per_page=100" % canary()
    found["response"]["body"] = []
    return found


def p26_checks(head: str) -> dict:
    node = p32_pull()
    node.update(number=26, headRefOid=head, mergeQueueEntry=None)
    node["commits"]["nodes"][0]["commit"]["oid"] = head
    found = checks_answer(node)
    owner, name = canary().split("/")
    found["request"]["body"]["variables"].update(owner=owner, name=name)
    return found


PERSON = ("don-petry", MAINTAINER, "User")        # the Maintainer, as the fixtures record him
LENS = ("coderabbitai", 136622811, "Bot")          # a Lens's App, as GraphQL names a Bot: its login has no [bot]
APP = ("github-actions", 41898282, "Bot")          # an App no Lens is


def closing_answer(repo: str, number: int, issues: list, total=None, elsewhere: str = None, labelled=()) -> dict:
    """An exchange of the port's closing-references query: `totalCount` and each issue's number, in the shape P-33 and
    P-46 recorded, with each issue's repo and labels, which no trial has recorded yet. `labelled` are the issues GitHub
    lists the factory:contract label on."""
    owner, name = repo.split("/")
    asked = {"query": acceptance.QUERY, "variables": {"owner": owner, "name": name, "number": number}}
    nodes = [{"number": n, "repository": {"nameWithOwner": elsewhere or repo},
              "labels": {"totalCount": 1 if n in labelled else 0,
                         "nodes": [{"name": "factory:contract"}] if n in labelled else []}} for n in issues]
    refs = {"totalCount": len(nodes) if total is None else total, "nodes": nodes}
    return {"request": {"via": "graphql", "call": "POST /graphql", "headers": {}, "body": asked},
            "response": {"status": 200, "headers": {},
                         "body": {"data": {"repository": {"pullRequest": {"closingIssuesReferences": refs}}}}}}


def issue_timeline(repo: str, number: int, events, more: bool = False) -> dict:
    """An issue's REST timeline, asked as `adapters/timeline.py` asks a pull request's, in trials/P-28.json's shape."""
    found = copy.deepcopy(exchanges("P-28")[4])
    found["request"]["call"] = "GET /repos/%s/issues/%d/timeline?per_page=100" % (repo, number)
    found["response"]["body"] = events
    found["response"]["headers"] = dict(found["response"]["headers"], link='<https://x>; rel="next"' if more else "")
    return found


def label_event(action: str, actor=PERSON, label: str = "factory:contract", at: str = "2026-10-21T16:00:00Z",
                via=None) -> dict:
    login, account, kind = actor
    return {"event": action, "label": {"name": label}, "actor": {"login": login, "id": account, "type": kind},
            "created_at": at, "performed_via_github_app": via}


class Acceptance(unittest.TestCase):
    PULL = {"number": 26, "base": {"ref": "main", "repo": {"full_name": "o/r", "default_branch": "main"}}}

    def read(self, *found, pull=None):
        router = Router(github.Replay(list(found)), {"don-petry": "admin", "reader": "read"})
        return acceptance.read(router, pull or self.PULL, timeline.Accounts(router, "o/r", MACHINE, {}))

    def asked(self, events, listed=True):
        """What one closing issue with these label events, and the label GitHub lists or not, reads as."""
        return self.read(closing_answer("o/r", 26, [36], labelled=[36] if listed else []),
                         issue_timeline("o/r", 36, events))

    def test_an_issue_asks_for_a_contract_only_by_a_persons_label(self):
        # The Maintainer's rule of 2026-10-21 (decision 0047): a pull request that closes no issue, or one whose issue
        # carries no factory:contract a person placed, asks for none, and acceptance is null and read whole.
        self.assertEqual(self.read(closing_answer("o/r", 26, [])), (None, True))
        self.assertEqual(self.asked([], listed=False), (None, True))
        self.assertEqual(self.asked([label_event("labeled", label="bug")], listed=False), (None, True))
        # A person's label asks: the contract is then read, which adapters/contract.py, not built, holds; not whole.
        self.assertEqual(self.asked([label_event("labeled")]), (None, False))
        # Only a person ends what a person placed (L-17): removed by an App or the machine user, it still asks.
        later = "2026-10-21T16:01:00Z"
        self.assertEqual(self.asked([label_event("labeled"), label_event("unlabeled", at=later)], listed=False),
                         (None, True))
        for actor in (APP, (APPROVER,) + MACHINE):
            self.assertEqual(self.asked([label_event("labeled"), label_event("unlabeled", actor, at=later)],
                                        listed=False), (None, False), actor)
        # Placed by an App, the machine user, a reader, or an App with a person's token, it asks for nothing.
        for event in (label_event("labeled", APP), label_event("labeled", (APPROVER,) + MACHINE),
                      label_event("labeled", ("reader", 8, "User")), label_event("labeled", via={"slug": "x"})):
            self.assertEqual(self.asked([event]), (None, True), event)
        # Placed again by an App over a person's, the person's placement stands; after a person removed it, an App's
        # placement asks for nothing.
        self.assertEqual(self.asked([label_event("labeled"), label_event("labeled", APP, at=later)]), (None, False))
        self.assertEqual(self.asked([label_event("labeled"), label_event("unlabeled", at=later),
                                     label_event("labeled", APP, at="2026-10-21T16:02:00Z")]), (None, True))
        # A person's placement and removal in the same second read as placed, the reading that asks.
        self.assertEqual(self.asked([label_event("labeled"), label_event("unlabeled")], listed=False), (None, False))
        # Of two closing issues, one that asks is enough.
        self.assertEqual(self.read(closing_answer("o/r", 26, [36, 37], labelled=[37]), issue_timeline("o/r", 36, []),
                                   issue_timeline("o/r", 37, [label_event("labeled")])), (None, False))

    def test_a_label_event_that_names_no_label_is_refused(self):
        # It could be the contract label's placement or removal: refused, as timeline.label_events refuses it.
        for label in (None, {}, {"name": ""}, {"name": 7}, "factory:contract"):
            event = dict(label_event("labeled"), label=label)
            with self.assertRaises(github.Unanswered, msg=label):
                self.asked([event], listed=False)

    def test_an_issue_whose_labels_and_timeline_disagree_or_are_short_is_not_whole(self):
        # GitHub lists the label, but no event placed it (renamed into the name, or placed out of sight); or the
        # timeline says it stands and GitHub lists none.
        self.assertEqual(self.asked([], listed=True), (None, False))
        self.assertEqual(self.asked([label_event("labeled", APP)], listed=False), (None, False))
        short = issue_timeline("o/r", 36, {"message": "not a list"})
        short["request"]["call"] = "GET /repos/o/r/issues/36/timeline?per_page=100&page=2"
        self.assertEqual(self.read(closing_answer("o/r", 26, [36]), issue_timeline("o/r", 36, [], more=True), short),
                         (None, False))

    def test_closing_references_are_whole_only_of_this_repo_and_every_one_counted(self):
        self.assertIn("closingIssuesReferences(first: 10)", acceptance.QUERY)
        self.assertEqual(self.read(closing_answer("o/r", 26, [36], total=11)), (None, False))
        self.assertEqual(self.read(closing_answer("o/r", 26, [36], elsewhere="o/other")), (None, False))
        self.assertEqual(self.read(closing_answer("o/r", 26, [36, 36]), issue_timeline("o/r", 36, [])), (None, False))
        many = closing_answer("o/r", 26, [36])
        many["response"]["body"]["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"][0]["labels"] \
            = {"totalCount": 51, "nodes": []}
        self.assertEqual(self.read(many), (None, False))
        # A label count that is no count is not read whole, though True equals one.
        boolean = closing_answer("o/r", 26, [36], labelled=[36])
        boolean["response"]["body"]["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"][0][
            "labels"]["totalCount"] = True
        self.assertEqual(self.read(boolean), (None, False))
        for broken in ({"number": 0}, {"number": True}, {"number": "36"}, "36"):
            found = closing_answer("o/r", 26, [36])
            found["response"]["body"]["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"] = [broken]
            with self.assertRaises(github.Unanswered, msg=broken):
                self.read(found)
        for refs in (None, {"totalCount": None, "nodes": []}, {"totalCount": 0, "nodes": None},
                     {"totalCount": True, "nodes": closing_answer("o/r", 26, [36])["response"]["body"]["data"][
                         "repository"]["pullRequest"]["closingIssuesReferences"]["nodes"]}):
            found = closing_answer("o/r", 26, [])
            found["response"]["body"]["data"]["repository"]["pullRequest"]["closingIssuesReferences"] = refs
            self.assertEqual(self.read(found), (None, False), refs)
        # A shape GitHub does not give is refused, never let through as another error.
        for shape in ({"data": "x"}, {"data": {"repository": []}}, {"data": {"repository": {"pullRequest": "x"}}}):
            odd = closing_answer("o/r", 26, [])
            odd["response"]["body"] = shape
            with self.assertRaises(github.Unanswered, msg=shape):
                self.read(odd)
        stringly = closing_answer("o/r", 26, [36])
        stringly["response"]["body"]["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"][0][
            "repository"] = "o/r"
        self.assertEqual(self.read(stringly), (None, False))
        whole_body = closing_answer("o/r", 26, [])["response"]["body"]
        for status, answer_body in ((502, None), (502, whole_body), (200, {"errors": [{"message": "x"}]})):
            failed = closing_answer("o/r", 26, [])
            failed["response"].update(status=status, body=answer_body)
            with self.assertRaises(github.Unanswered, msg=status):
                self.read(failed)

    def test_a_pull_request_to_another_base_than_the_default_is_not_read_whole_on_its_contract(self):
        # trials/P-33.json: a pull request to a base that is not the default branch carries no closing reference at
        # all, so whether its issue asks cannot be read.
        for base in ({"ref": "release", "repo": {"full_name": "o/r", "default_branch": "main"}},
                     {"ref": "main", "repo": {"full_name": "o/r"}}, {"repo": {"full_name": "o/r"}}):
            self.assertEqual(self.read(pull={"number": 26, "base": base}), (None, False), base)

    def test_every_intent_a_lifecycle_runs_is_ruled_on_whether_it_asks_for_a_contract(self):
        # Decision 0047: an issue asks by its item's Intent only for `fix` or `implement`, which no Lifecycle runs.
        # Every Intent a Lifecycle runs is named here, none of them one that asks: a new one fails here until it is
        # ruled whether it asks, and the port reads it if it does.
        from kernel import issue
        self.assertEqual(set(issue.INTENTS) | set(records.ON_PULL_REQUEST),
                         {"investigate-issue", "judge-readiness", "open-pull-request", "review-change", "fix-findings",
                          "adjudicate-findings", "issue-approval"})


def thread_node(ident: str, opened=PERSON, at: str = "2026-10-21T16:18:57Z", resolved_by=None) -> dict:
    """A review thread as the port's query asks it. No trial has recorded a thread's author, time or resolver yet (P-43
    recorded only its path and state); the pending test below reads the first that does."""
    login, account, kind = opened
    node = {"id": ident, "isResolved": resolved_by is not None,
            "resolvedBy": None if resolved_by is None else {"login": resolved_by[0], "databaseId": resolved_by[1]},
            "comments": {"nodes": [{"createdAt": at, "author": {"__typename": kind, "login": login,
                                                                 "databaseId": account}}]}}
    return node


def threads_answer(repo: str, number: int, nodes: list, total=None, after=None, cursor=None) -> dict:
    """An exchange of the port's threads query, in the page shape P-43 recorded for review threads."""
    owner, name = repo.split("/")
    asked = {"query": threads.QUERY, "variables": {"owner": owner, "name": name, "number": number, "after": after}}
    page = {"hasNextPage": cursor is not None, "endCursor": cursor}
    listed = {"totalCount": len(nodes) if total is None else total, "pageInfo": page, "nodes": nodes}
    return {"request": {"via": "graphql", "call": "POST /graphql", "headers": {}, "body": asked},
            "response": {"status": 200, "headers": {},
                         "body": {"data": {"repository": {"pullRequest": {"reviewThreads": listed}}}}}}


class Threads(unittest.TestCase):
    PULL = {"number": 26, "base": {"repo": {"full_name": "o/r"}}}

    def read(self, *pages, permissions=None, kept=None):
        router = Router(github.Replay(list(pages)), permissions or {"don-petry": "admin", "outsider": "read"})
        accounts = timeline.Accounts(router, "o/r", MACHINE, {LENS[1:]: "coderabbit"})
        return threads.read(router, self.PULL, accounts, kept)

    def test_each_thread_is_read_with_who_opened_and_resolved_it_and_a_persons_is_human(self):
        kept = {}
        got, whole = self.read(threads_answer("o/r", 26, [
            thread_node("PRRT_1"), thread_node("PRRT_2", LENS, resolved_by=("don-petry", MAINTAINER)),
            thread_node("PRRT_3", APP), thread_node("PRRT_4", ("outsider", 7, "User")),
            thread_node("PRRT_5", (APPROVER,) + MACHINE)]), kept=kept)
        self.assertTrue(whole)
        # Each node is kept as GitHub gave it, for reconciliation (decision 0061).
        self.assertEqual(([n["id"] for n in kept["threads"][0]], kept["threads"][1]),
                         (["PRRT_1", "PRRT_2", "PRRT_3", "PRRT_4", "PRRT_5"], True))
        self.assertEqual(got[0], {"id": "PRRT_1", "resolved": False, "category": "human", "severity": None,
                                  "opened_by": {"kind": "human", "name": "don-petry", "can_write": True},
                                  "resolved_by": None, "opened_at": "2026-10-21T16:18:57Z"})
        # A Lens's thread has no category or severity until its Finding record can be joined (decision 0038).
        self.assertEqual((got[1]["opened_by"], got[1]["category"], got[1]["severity"]),
                         ({"kind": "lens", "name": "coderabbit", "can_write": False}, None, None))
        self.assertEqual(got[1]["resolved_by"], {"kind": "human", "name": "don-petry", "can_write": True})
        self.assertEqual((got[2]["opened_by"]["kind"], got[2]["category"]), ("app", None))
        self.assertEqual((got[3]["opened_by"], got[3]["category"]),
                         ({"kind": "human", "name": "outsider", "can_write": False}, "human"))
        # The machine user is no person: its thread, as an App's, has no category.
        self.assertEqual((got[4]["opened_by"]["kind"], got[4]["category"]), ("machine_user", None))
        # A resolved thread GitHub names no resolver for, as when an App resolved it, is read with none: the Kernel
        # defers on that thread alone, never on the whole pull request.
        resolved, _ = self.read(threads_answer("o/r", 26, [dict(thread_node("PRRT_6", LENS), isResolved=True)]))
        self.assertEqual((resolved[0]["resolved"], resolved[0]["resolved_by"]), (True, None))

    def test_a_thread_that_cannot_be_read_is_refused(self):
        good = thread_node("PRRT_1")
        broken = [dict(good, id=""), dict(good, id=None), dict(good, isResolved=None), dict(good, comments={"nodes": []}),
                  dict(good, comments=None), dict(good, resolvedBy={"login": "don-petry", "databaseId": MAINTAINER}),
                  dict(good, isResolved=0),
                  dict(good, isResolved=1, resolvedBy={"login": "don-petry", "databaseId": MAINTAINER}),
                  thread_node("PRRT_1", at="yesterday"),
                  thread_node("PRRT_1", ("ghost", 1, "Mannequin")), thread_node("PRRT_1", ("don-petry", None, "User")),
                  thread_node("PRRT_1", ("x[bot]", 9, "User")), "PRRT_1", thread_node("PRRT_1")]
        broken[-1]["comments"]["nodes"][0]["author"] = None    # a deleted account, which GraphQL gives as null
        reply = thread_node("PRRT_1")
        reply["comments"]["nodes"][0]["replyTo"] = {"id": "PRRC_0"}
        broken.append(reply)
        for node in broken:
            with self.assertRaises(github.Unanswered, msg=node):
                self.read(threads_answer("o/r", 26, [node]))

    def test_threads_are_read_page_by_page_and_whole_only_when_every_one_was_read_once(self):
        one, two = [thread_node("PRRT_1")], [thread_node("PRRT_2")]
        first = threads_answer("o/r", 26, one, total=2, cursor="c1")
        got, whole = self.read(first, threads_answer("o/r", 26, two, total=2, after="c1"))
        self.assertEqual(([t["id"] for t in got], whole), (["PRRT_1", "PRRT_2"], True))
        for second in (threads_answer("o/r", 26, one, total=2, after="c1"),            # a thread read twice
                       threads_answer("o/r", 26, two, total=3, after="c1"),            # the count moved
                       threads_answer("o/r", 26, [], total=2, after="c1")):            # one counted never read
            self.assertIs(self.read(first, second)[1], False)
        # A cursor that repeats, or a next page past the count, ends the read short rather than looping.
        start = threads_answer("o/r", 26, one, total=5, cursor="c1")
        looping = threads_answer("o/r", 26, two, total=5, after="c1", cursor="c1")
        self.assertIs(self.read(start, looping)[1], False)
        self.assertIs(self.read(threads_answer("o/r", 26, one + two, total=2, cursor="c1"))[1], False)
        for change in ({"pageInfo": {"hasNextPage": None}}, {"nodes": None}, {"totalCount": None},
                       {"totalCount": True}, {"pageInfo": {"hasNextPage": True, "endCursor": ""}}):
            page = threads_answer("o/r", 26, one)
            page["response"]["body"]["data"]["repository"]["pullRequest"]["reviewThreads"].update(change)
            self.assertIs(self.read(page)[1], False, change)
        bare = threads_answer("o/r", 26, one)
        bare["response"]["body"]["data"]["repository"]["pullRequest"]["reviewThreads"] = None
        self.assertEqual(self.read(bare), ([], False))
        for status, answer_body in ((502, None), (200, {"errors": [{"message": "x"}]})):
            failed = threads_answer("o/r", 26, one)
            failed["response"].update(status=status, body=answer_body)
            with self.assertRaises(github.Unanswered):
                self.read(failed)

    @pending
    def test_a_thread_a_trial_recorded_is_read_as_the_port_reads_it(self):
        # A thread's author, time and resolver, as GitHub's GraphQL gives them, are not yet recorded: the first trial
        # that records one, asked as the port asks, is read here.
        found = [e for name in sorted((ROOT / "trials").glob("P-*.json"))
                 for e in json.loads(name.read_text()).get("exchanges", [])
                 if (e.get("request") or {}).get("body", {}) and "FactsThreads" in json.dumps(e["request"]["body"])]
        self.assertTrue(found)


def p26_checks_nodes(exchange: dict) -> list:
    """The check runs a checks answer lists."""
    pr = exchange["response"]["body"]["data"]["repository"]["pullRequest"]
    contexts = pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"]
    return [n for n in contexts if n["__typename"] == "CheckRun"]


class Snapshot(unittest.TestCase):
    NOW = "2026-10-18T03:00:00Z"

    def sequence(self, reread: int) -> list:
        """Pull request 26's reads, in the order the snapshot asks them: trials/P-29.base.json for the pull request,
        its branch, its diff and its read again; trials/P-28.json for its activity and its timeline; the shapes of
        P-29.truncated, P-7 and P-32 for its files, reviews and checks, which no fixture holds for this one."""
        found = exchanges("P-29.base")
        head = found[1]["response"]["body"]["head"]["sha"]
        branch = found[9]["response"]["body"]["commit"]["sha"]
        data = found[1]["response"]["body"]
        return [found[1], found[9], exchanges("P-28")[3], as_compare(found[2], data, branch),
                as_compare(p26_files(), data, branch), exchanges("P-28")[4], p26_reviews(), p26_checks(head),
                closing_answer(canary(), 26, []), threads_answer(canary(), 26, []), found[reread]]

    def read(self, reread: int):
        router = Router(github.Replay(self.sequence(reread)), {"don-petry": "admin"})
        accounts = timeline.Accounts(router, canary(), MACHINE, {})
        return facts.snapshot(router, canary(), 26, person(), accounts, True, lambda: self.NOW)

    def test_a_snapshot_holds_every_part_of_the_facts_and_the_title_beside_them(self):
        got, title = self.read(1)
        self.assertEqual(title, body("P-29.base", 1)["title"])
        self.assertEqual((got["item"]["number"], got["class"], got["targets_protected"], got["diff"]["files"]),
                         (26, "maintainer", False, 1))
        self.assertEqual(got["content_id"], "sha256:" + body("P-29.base", 24)["before the base moved"])
        # The activity read is of a later push than the head the pull request was read at: no pusher, and the push's
        # time is the read's, so nothing reads as placed after a push it could not see.
        self.assertEqual((got["last_pusher"], got["last_push_at"]), (None, self.NOW))
        self.assertEqual(got["complete"], {"acceptance": True, "reviews": True, "threads": True, "checks": True,
                                           "diff": True, "changed_paths": True, "runs": True, "timeline": True})
        self.assertIsNone(got["acceptance"])
        self.assertNotIn(title, json.dumps(got))

    def test_a_snapshot_keeps_its_reads_for_reconciliation_only_once_it_is_whole(self):  # decision 0061
        # Reconciliation reads what the snapshot read, as GitHub gave it, so no read is made twice; a snapshot refused
        # keeps nothing, and reconciliation of that pull request is short.
        router = Router(github.Replay(self.sequence(1)), {"don-petry": "admin"})
        kept = {}
        facts.snapshot(router, canary(), 26, person(), timeline.Accounts(router, canary(), MACHINE, {}), True,
                       lambda: self.NOW, kept)
        self.assertEqual(sorted(kept), ["check_runs", "events", "reviews", "threads"])
        self.assertTrue(all(isinstance(v[0], list) and v[1] is True for v in kept.values()))
        self.assertEqual(kept["events"][0], exchanges("P-28")[4]["response"]["body"])
        self.assertEqual(len(kept["check_runs"][0]), len([n for n in p26_checks_nodes(self.sequence(1)[7])]))
        self.assertTrue(kept["check_runs"][0] and all(n["__typename"] == "CheckRun" for n in kept["check_runs"][0]))
        router = Router(github.Replay(self.sequence(12)), {"don-petry": "admin"})
        kept = {}
        with self.assertRaises(facts.Moved):
            facts.snapshot(router, canary(), 26, person(), timeline.Accounts(router, canary(), MACHINE, {}), True,
                           lambda: self.NOW, kept)
        self.assertEqual(kept, {})

    def test_a_snapshot_whose_closing_issue_asks_for_a_contract_is_not_read_whole_on_it(self):
        seq = self.sequence(1)
        at = len(seq) - 3
        seq[at:at + 1] = [closing_answer(canary(), 26, [36]), issue_timeline(canary(), 36, [label_event("labeled")])]
        router = Router(github.Replay(seq), {"don-petry": "admin"})
        got, _ = facts.snapshot(router, canary(), 26, person(), timeline.Accounts(router, canary(), MACHINE, {}), True,
                                lambda: self.NOW)
        self.assertEqual((got["acceptance"], got["complete"]["acceptance"]), (None, False))

    def test_the_bases_head_and_a_pushs_time_are_read_or_refused(self):
        self.assertEqual(pull.base(replay("P-29.base", 9), body("P-29.base", 1))["head"],
                         body("P-29.base", 9)["commit"]["sha"])
        headless = copy.deepcopy(exchanges("P-29.base")[9])
        headless["response"]["body"]["commit"] = None
        with self.assertRaises(github.Unanswered):
            pull.base(github.Replay([headless]), body("P-29.base", 1))
        pushed = pull.last_push(replay("P-28", 7), body("P-28", 10))
        self.assertEqual(pushed, ("don-petry", body("P-28", 7)[0]["timestamp"]))
        odd = copy.deepcopy(exchanges("P-28")[7])
        odd["response"]["body"][0]["timestamp"] = "yesterday"
        self.assertEqual(pull.last_push(github.Replay([odd]), body("P-28", 10)), ("don-petry", None))

    def test_a_snapshot_whose_head_moved_while_it_was_read_is_refused(self):
        # As Moved, which the approving act classes as a change under it, not a read that failed (issue 195).
        with self.assertRaises(facts.Moved):
            self.read(12)

    def test_a_snapshot_of_a_pull_request_that_changed_while_it_was_read_is_refused(self):
        # trials/P-29.base.json: the base moved and the head did not, and GitHub moved the pull request's updated_at.
        # Any change between the first read and the last, a label added after the timeline was read among them, makes
        # the parts of two pull requests.
        self.assertEqual(body("P-29.base", 6)["head"]["sha"], body("P-29.base", 1)["head"]["sha"])
        self.assertNotEqual(body("P-29.base", 6)["updated_at"], body("P-29.base", 1)["updated_at"])
        with self.assertRaises(facts.Moved):
            self.read(6)

    def test_a_push_that_names_its_pusher_and_no_time_is_refused(self):
        seq = self.sequence(1)
        entry = seq[2]["response"]["body"][0]
        entry["after"] = body("P-29.base", 1)["head"]["sha"]
        router = Router(github.Replay(copy.deepcopy(seq)), {"don-petry": "admin"})
        got, _ = facts.snapshot(router, canary(), 26, person(), timeline.Accounts(router, canary(), MACHINE, {}), True,
                                lambda: self.NOW)
        self.assertEqual((got["last_pusher"], got["last_push_at"]), ("don-petry", entry["timestamp"]))
        entry["timestamp"] = "yesterday"
        router = Router(github.Replay(seq), {"don-petry": "admin"})
        with self.assertRaises(github.Unanswered):
            facts.snapshot(router, canary(), 26, person(), timeline.Accounts(router, canary(), MACHINE, {}), True,
                           lambda: self.NOW)

    def test_a_snapshot_holds_every_thread_read_and_says_whether_they_were_read_whole(self):
        seq = self.sequence(1)
        seq[9] = threads_answer(canary(), 26, [thread_node("PRRT_1", PERSON), thread_node("PRRT_2", LENS)])
        router = Router(github.Replay(copy.deepcopy(seq)), {"don-petry": "admin"})
        accounts = timeline.Accounts(router, canary(), MACHINE, {LENS[1:]: "coderabbit"})
        got, _ = facts.snapshot(router, canary(), 26, person(), accounts, False, lambda: self.NOW)
        self.assertEqual([(t["id"], t["category"]) for t in got["threads"]], [("PRRT_1", "human"), ("PRRT_2", None)])
        self.assertEqual((got["complete"]["threads"], got["complete"]["runs"]), (True, False))
        seq[9]["response"]["body"]["data"]["repository"]["pullRequest"]["reviewThreads"]["totalCount"] = 3
        router = Router(github.Replay(seq), {"don-petry": "admin"})
        accounts = timeline.Accounts(router, canary(), MACHINE, {LENS[1:]: "coderabbit"})
        got, _ = facts.snapshot(router, canary(), 26, person(), accounts, True, lambda: self.NOW)
        self.assertIs(got["complete"]["threads"], False)

    def test_only_a_required_lenss_own_apps_open_thread_defers(self):
        # A thread is a Lens thread only when its author is that Lens's own App, by account id and type. An outside
        # reviewer's thread, CodeRabbit's or Codex's, is no required Lens's: with no category it does not defer.
        # Only a required model Lens's own App's open thread with neither defers, until harness/ uploads its record.
        from kernel import derive
        config = json.loads((ROOT / "config" / "defaults.json").read_text())
        role = ("combsmith-sf-pr-review", 99, "Bot")
        seq = self.sequence(1)
        seq[9] = threads_answer(canary(), 26, [thread_node("PRRT_1", LENS), thread_node("PRRT_2", role),
                                               thread_node("PRRT_3", APP), thread_node("PRRT_4", PERSON)])
        router = Router(github.Replay(seq), {"don-petry": "admin"})
        accounts = timeline.Accounts(router, canary(), MACHINE, {LENS[1:]: "coderabbit", role[1:]: "pr-review"})
        got, _ = facts.snapshot(router, canary(), 26, person(), accounts, True, lambda: self.NOW)
        self.assertEqual(config["required_lenses"]["model"], ["pr-review"])
        self.assertEqual(derive.unreadable_threads(got, dict(config, approver=APPROVER)), ["PRRT_2"])

    def test_the_snapshots_time_is_taken_after_its_last_read(self):
        replay = github.Replay(self.sequence(1))
        router = Router(replay, {"don-petry": "admin"})
        left = []
        got, _ = facts.snapshot(router, canary(), 26, person(), timeline.Accounts(router, canary(), MACHINE, {}), True,
                                lambda: left.append(len(replay._left)) or self.NOW)
        self.assertEqual((left, got["read_at"]), ([0], self.NOW))

    def test_a_snapshot_that_does_not_hold_to_the_schema_is_refused(self):
        # A part the reads give that facts/1 does not take, here a time out of its range, refuses the whole.
        router = Router(github.Replay(self.sequence(1)), {"don-petry": "admin"})
        with self.assertRaises(github.Unanswered):
            facts.snapshot(router, canary(), 26, person(), timeline.Accounts(router, canary(), MACHINE, {}), True,
                           lambda: "2026-10-18T24:00:00Z")


class ChecksAsked(unittest.TestCase):
    @pending
    def test_a_required_check_reports_on_every_head_and_a_rerun_replaces_only_its_own(self):
        # Decisions 0015 and 0018: a required check reports on every head and in the merge queue, and only a re-run of
        # the same job in the same check suite replaces an earlier run, so two suites' runs of one name both stand in
        # the rollup the port reads. GitHub's behaviour, which P-42 (issue 250) records, its last exchange saying what
        # was seen; until its fixture lands, this test is expected to fail.
        seen = body("P-42", -1)
        self.assertEqual((seen["reported on every head"], seen["reported in the merge queue"],
                          seen["both suites' runs of one name listed"], seen["a re-run replaced only its own"]),
                         (True, True, True, True))

    @pending
    def test_a_dynamic_workflows_path_is_read_as_github_gives_it(self):
        # Decision 0018: a check GitHub Actions ran from a dynamic workflow, CodeQL's default set-up among them, is given
        # with that path verbatim. The GraphQL rollup names no file for it (trials/P-32.json), so the read that gives
        # it, the check suite's workflow run by REST, is still to be built.
        node = p32_pull()
        got = checks.read(github.Replay([checks_answer(node)]), as_pull(node))
        codeql = next(c for c in got["checks"] if c["name"] == "Analyze (actions)")
        self.assertTrue(str(codeql["workflow"]).startswith("dynamic/"))


def home_file(name: str, data: bytes, path: str = None, **change) -> dict:
    """One case of a stand-in home, `o/home`, as GitHub's contents API answers for a file: its bytes base64 encoded and
    wrapped at 60 characters, as GitHub wraps them. The bytes are no case: nothing of the home is in this repo."""
    path = path or "pr-review/%s.json" % name
    encoded = base64.b64encode(data).decode()
    body = {"type": "file", "encoding": "base64", "size": len(data), "name": path.split("/")[-1], "path": path,
            "content": "\n".join(encoded[i:i + 60] for i in range(0, len(encoded), 60)) + "\n"}
    body.update(change)
    return {"request": {"via": "rest", "call": "GET /repos/o/home/contents/pr-review/%s.json" % name, "headers": {}},
            "response": {"status": 200, "headers": {"content-type": "application/json; charset=utf-8"}, "body": body}}


def home_set(*named) -> dict:
    return {"schema": "eval-set/1", "role": "pr-review", "intent": "review-change", "count": len(named),
            "cases": [{"id": n, "sha256": hashlib.sha256(d).hexdigest()} for n, d in named]}


class Heldout(unittest.TestCase):
    ONE, TWO = b"stand-in one\n" * 9, bytes(range(256))

    def test_a_held_out_case_is_its_hashed_bytes(self):
        # Issue 309: each case the manifest names is asked for by its Role and id, once, in its order, and handed back
        # as exactly the bytes the manifest hashed; GitHub's base64, wrapped, is decoded whole.
        manifest = home_set(("c-1", self.ONE), ("c-2", self.TWO))
        home = github.Replay([home_file("c-1", self.ONE), home_file("c-2", self.TWO)])
        self.assertEqual([heldout.case(home, "o", "home", manifest["role"], e) for e in manifest["cases"]],
                         [(self.ONE, None), (self.TWO, None)])

    def test_a_held_out_case_not_read_whole_says_why(self):
        entry = home_set(("c-1", self.ONE))["cases"][0]

        def read(found, owner="o", name="home", role="pr-review", which=entry):
            return heldout.case(github.Replay(found), owner, name, role, which)
        missing = home_file("c-1", self.ONE)
        missing["response"].update(status=404, body={"message": "Not Found"})
        refused = home_file("c-1", self.ONE)
        refused["response"]["status"] = 500
        large = home_file("c-1", b"", size=heldout.LARGEST + 1, content="", encoding="none")
        for found, code in (([missing], "not_found"), ([refused], "unanswered"), ([], "unanswered"),
                            ([home_file("c-1", self.TWO)], "hash_differs"), ([large], "too_large"),
                            ([home_file("c-1", self.ONE, type="dir")], "not_found"),
                            ([home_file("c-1", self.ONE, path="other/c-1.json")], "not_found"),
                            ([home_file("c-1", self.ONE, size=True)], "not_found"),
                            ([home_file("c-1", self.ONE, size=-1)], "not_found"),
                            ([home_file("c-1", self.ONE, encoding="none")], "unanswered"),
                            ([home_file("c-1", self.ONE, content="not base64!")], "unanswered"),
                            ([home_file("c-1", self.ONE, size=len(self.ONE) - 1)], "unanswered"),
                            ([home_file("c-1", self.ONE, content=None)], "unanswered")):
            self.assertEqual(read(found), (None, code), code)
        refused["response"]["body"] = "not json"
        refused["response"]["status"] = 200
        self.assertEqual(read([refused]), (None, "unanswered"))
        self.assertEqual(read([home_file("c-1", self.ONE, size=heldout.LARGEST)]), (None, "unanswered"))
        # GitHub's base64 holds its alphabet and line breaks alone: anything else is no answer of GitHub's.
        loose = home_file("c-1", self.ONE)
        loose["response"]["body"]["content"] = "*" + loose["response"]["body"]["content"]
        self.assertEqual(read([loose]), (None, "unanswered"))
        # A case or a Role that could name another file, and a home that could name another repo or climb out of one,
        # are refused before anything is asked: the stand-in would answer anything, and is asked nothing.
        asked = []

        class Anything:
            def send(self, req):
                asked.append(req["path"])
                return home_file("c-1", self.ONE)["response"]
        Anything.ONE = self.ONE
        for which, role in ((dict(entry, id="../c-1"), "pr-review"), (dict(entry, id="c-1.json"), "pr-review"),
                            (dict(entry, sha256="x"), "pr-review"), ("c-1", "pr-review"), (entry, "pr-review/.."),
                            (entry, "Pr-Review"), (entry, None), (dict(entry, id=7), "pr-review")):
            self.assertEqual(heldout.case(Anything(), "o", "home", role, which), (None, "not_this_set"), (which, role))
        for owner, name in (("o", ".."), ("o", "."), ("o/x", "home"), ("o", "home/contents"), ("-o", "home"),
                            ("o", "home?ref=x"), (None, "home"), ("o", ""), ("o", None)):
            self.assertEqual(heldout.case(Anything(), owner, name, "pr-review", entry), (None, "unanswered"), (owner, name))
        self.assertEqual(asked, [])
        self.assertEqual(heldout.case(Anything(), "o", "home", "pr-review", entry), (self.ONE, None))
        self.assertEqual(asked, ["/repos/o/home/contents/pr-review/c-1.json"])
def per_hundred(found: dict) -> dict:
    """A fixture's exchange asked as the port asks a list: a full page of a hundred, GitHub's answer kept."""
    found = copy.deepcopy(found)
    words = found["request"]["call"].split()
    found["request"]["call"] = " ".join([words[0], words[1].replace("per_page=1", "per_page=100")] + words[2:])
    return found


def second_page(found: dict, body) -> dict:
    """The page the port asks next, after `found`, answered with `body`."""
    page = copy.deepcopy(found)
    words = page["request"]["call"].split()
    page["request"]["call"] = " ".join([words[0], words[1] + "&page=2"] + words[2:])
    page["response"]["body"] = body
    return page


# Each grounded rule of the fake that the port does not read here, by why: the Controller's, the workflows' or a
# person's, which no port reads (`controller`); the Kernel's, held by its own boundary tests, a race no port can read
# (`kernel`); the issues port's, not built (`issues_port`); or a fixture recorded in another request's shape than the
# port asks, which a trial records again (`shape`).
NOT_READ = {
    # The records port reads what GitHub lists and cannot see a Run it does not list: the race is the Kernel's, held by
    # the unidentified window (decision 0036).
    "a_new_run_is_listed_late": "kernel",
    "a_tick_can_be_lost": "controller",
    "a_pass_starts_its_successor": "controller", "a_public_event_starts_a_pass": "controller",
    # adapters/acceptance.py reads closing references, and adapters/timeline.py the draft flag's events, each in a
    # shape these GraphQL fixtures did not record: P-33 asked no issue's repo, and no REST timeline of a draft change.
    "a_closing_reference_is_read_from_any_pull_request": "shape", "who_changed_the_draft_flag_is_read": "shape",
    "an_issues_content_time_is_read_apart": "issues_port", "a_reopening_names_its_actor": "issues_port",
    "an_issues_close_and_reopening_say_when": "issues_port",
    "a_merge_closes_the_issue_it_names_and_an_edit_after_it_closes_nothing": "issues_port",
    "a_label_event_names_its_actor": "shape",
}
WHY = {"controller", "kernel", "issues_port", "shape"}
# Every response a trial shows GitHub refusing, by fixture and exchange, and whether a port asks it: a port's is read
# as no answer, never as one (FR-56); a refusal recorded later fails here until it is placed.
REFUSALS = {
    ("P-27", 15): "dispatch",          # a dispatch GitHub refused: the effects port reads it as a write that failed
    ("P-8", 1): "graphql",             # a GraphQL read over the resource limits, answered 200 with errors
    ("P-27", 21): None,                # an org membership read, which no port asks
    ("P-29.truncated", 4): "diff",     # the diff too large to serve: read as truncated, never as the whole
    ("P-29.truncated", 14): None,      # the patch form, which no port asks
    ("P-4", 2): None, ("P-4", 3): None, ("P-4", 9): None,   # a trial's own writes and reads of a file
    ("P-43", 3): None,                 # a review written by the trial, which no port writes yet
    ("P-44", 3): "runs",               # a list of runs GitHub did not find
}


class Contract(unittest.TestCase):
    def reads(self) -> dict:
        """Each grounded rule the port reads, from the fixture that grounds it, as the rule states it: the fixtures it
        replays, and whether the port's reading holds the rule."""
        before = pull.diff(compared("P-29.base", 2, body("P-29.base", 1)), body("P-29.base", 1), PINNED_BASE)["content_id"]
        after = pull.diff(compared("P-29.base", 13, body("P-29.base", 12)), body("P-29.base", 12), PINNED_BASE)["content_id"]
        fork = [e for e in exchanges("P-27") if "/runs?" in e["request"].get("call", "") and e["response"]["status"] == 200]
        rows = [r for e in fork for r in e["response"]["body"].get("workflow_runs", [])
                if r["head_repository"]["full_name"] != r["repository"]["full_name"]]
        # A fork's run is a pull request's, and would not count even were it a dispatch of a Role's file.
        recorded, rows = rows, rows + [dict(r, event="workflow_dispatch") for r in rows]
        p43 = exchanges("P-43")
        queued = Records().read(listing("P-17", 3, rows={"name": NAME}))[0]
        # A list GitHub counts past the 1,000 runs it serves, as P-43 counted one, read through the port page by page:
        # the port stops at the 1,000th and reads the list short.
        counted = p43[26]["response"]["body"]["total_count"]
        template = listing("P-17", 3, rows={"name": NAME})
        pages = []
        for page in range(1, records.SERVED // records.PAGE + 1):
            found = asked(copy.deepcopy(template), page)
            found["request"]["call"] = found["request"]["call"].replace("per_page=10", "per_page=100")
            row = found["response"]["body"]["workflow_runs"][0]
            found["response"]["body"].update(total_count=counted, workflow_runs=[
                dict(row, id=page * 1000 + n, name=NAME.replace("r_01JA6Z", "r_%06dA" % (page * 1000 + n)))
                for n in range(records.PAGE)])
            pages.append(found)
        stopped = records.runs(github.Replay(pages), canary(), "main", [WORKFLOW], DISPATCHER)
        # A run GitHub lists as pending, waiting its turn in its lane, is a Run queued (P-44).
        pending = next(r for e in exchanges("P-44") if "/runs?" in e["request"].get("call", "")
                       and isinstance(e["response"]["body"], dict)
                       for r in e["response"]["body"].get("workflow_runs", []) if r.get("status") == "pending")
        path = ".github/workflows/%s" % WORKFLOW
        counted_row = dict(pending, path=path, event="workflow_dispatch", head_branch="main", name=NAME,
                           repository={"full_name": canary()}, head_repository={"full_name": canary()},
                           actor={"id": DISPATCHER[0], "type": DISPATCHER[1]})
        waiting = records._record(counted_row, canary(), "main", {path}, DISPATCHER)
        short_reviews = timeline._pages(github.Replay([per_hundred(p43[11]), second_page(per_hundred(p43[11]), {})]),
                                        p43[11]["request"]["call"].split()[1].replace("per_page=1", "per_page=100"))
        compares = {"f03b9ecd01f6b1b34631a42b3d73ed3bd8cdfebb": "diff --git a/x b/x\n",
                    "355cb4d9626f8f434dff093d76eb4535a6e7e93e": "diff --git a/y b/y\n"}
        router = Router(reviews_read(22), {"don-petry": "admin", APPROVER: "write"}, compares)
        events, _ = timeline.events(replay("P-7", 16), p7_pull())
        reviewed, _ = timeline.reviews(router, p7_pull(), events, timeline.Accounts(router, canary(), MACHINE, {}),
                                       BASE_HEAD)
        short_events = timeline.events(github.Replay([per_hundred(p43[13]), second_page(per_hundred(p43[13]), {})]),
                                       {"number": 48, "base": {"repo": {"full_name": canary()}}})
        files = pull.changed_paths(github.Replay([as_compare(p43[10], body("P-43", 8))]), body("P-43", 8), PINNED_BASE)
        return {
            "a_push_is_new_content": ({"P-29.base"}, before != after),
            "the_pusher_is_the_last_pusher": ({"P-28", "P-28.app"},
                pull.last_pusher(replay("P-28", 7), body("P-28", 10)) == "don-petry"
                and pull.last_pusher(replay("P-28.app", 1), body("P-28.app", 0)) == "combsmith-sf-trial-author[bot]"),
            "a_short_diff_says_so": ({"P-29.truncated"},
                pull.diff(compared("P-29.truncated", 4, body("P-29.truncated", 2)), body("P-29.truncated", 2),
                          PINNED_BASE)["diff"]["truncated"]),
            "a_path_list_can_leave_out_a_file": ({"P-29.truncated"},
                pull.changed_paths(github.Replay([]), body("P-29.truncated", 2), PINNED_BASE)["complete"] is False),
            "a_forks_run_never_counts": ({"P-27"},
                bool(recorded) and all(r["event"] == "pull_request" for r in recorded)
                and all(records._record(r, r["repository"]["full_name"], r.get("head_branch"), {r.get("path")},
                                        (r["actor"]["id"], r["actor"]["type"])) == (None, None) for r in rows)),
            "a_new_run_is_listed_unnamed": ({"P-17"},
                Records().read(listing("P-17", 9, total=1), listing("P-17", 10, total=1),
                               per_page=1)[0]["unidentified"][0]["run"] == "39086879694"),
            "a_logins_permission_is_read_from_the_collaborator_endpoint": ({"P-47"}, all(
                timeline.Accounts(github.Replay([e]), canary(), MACHINE, {}).actor(
                    {"login": e["response"]["body"]["user"]["login"], "id": e["response"]["body"]["user"]["id"],
                     "type": "User"})["can_write"] == (e["response"]["body"]["permission"] in ("admin", "maintain", "write"))
                for e in exchanges("P-47") if "/permission" in e["request"]["call"])),
            # The bot's pull request is dependency only as the account named for it, by id and type, and it pushed the
            # head; the Kernel compares the last pusher with the author as the port reads both, by REST's one spelling.
            "a_dependency_bot_updates_a_workflow_pin": ({"P-45"},
                pull.own(body("P-45", 5), {"dependency": {(49699333, "Bot")}})[0]["class"] == "dependency"
                and pull.own(body("P-45", 5), {})[0]["class"] == "outside"
                and pull.last_pusher(replay("P-45", 7), body("P-45", 5)) == "dependabot[bot]"
                and pull.own(body("P-45", 5), {})[0]["author"] == pull.last_pusher(replay("P-45", 7), body("P-45", 5))),
            # Listed while queued, before its job starts: a record of status queued.
            "a_queued_run_is_listed": ({"P-17"}, [r["status"] for r in queued["runs"]] == ["queued"]),
            # A filtered list stops at the 1,000th run, however many it counts (P-43): the port reads it short.
            "a_run_list_stops_short": ({"P-43"},
                p43[27]["response"]["body"]["workflow_runs"] == [] and counted > records.SERVED
                and stopped["complete"] is False and len(stopped["runs"]) == records.SERVED),
            "a_run_waits_its_turn": ({"P-44"}, waiting is not None and waiting[0]["status"] == "queued"),
            # A list whose page names a next one is read on, and one that then ends in no list is read short: the
            # timeline's and the reviews'.
            "a_short_list_says_so": ({"P-43"}, short_events[1] is False and len(short_events[0]) == 1
                                     and short_reviews[1] is False and len(short_reviews[0]) == 1),
            "a_pull_request_lists_the_paths_it_changes": ({"P-43"},
                files["complete"] is True and len(files["changed_paths"]) == body("P-43", 8)["changed_files"]
                and any(p["previous"] for p in files["changed_paths"])),
            "a_short_path_list_says_so": ({"P-43"},
                pull.changed_paths(github.Replay([as_compare(p43[9], body("P-43", 8))]), body("P-43", 8),
                                   PINNED_BASE)["complete"] is False),
            # The App pushed last, and the machine user's approval of that head still stands, read as its approval.
            "an_app_pushes_to_the_head": ({"P-7"},
                pull.last_pusher(replay("P-7", 11), body("P-7", 7)) == "combsmith-sf-trial-author[bot]"),
            # The App pushed the head last, read after the approval too, and the machine user's approval of that head
            # stands: approved, on that commit, dismissed by no one.
            "the_machine_users_approval_counts": ({"P-7"},
                pull.last_pusher(replay("P-7", 24), body("P-7", 20)) == "combsmith-sf-trial-author[bot]"
                and [(r["state"], r["dismissed_by"] is None) for r in reviewed if r["by"]["kind"] == "machine_user"]
                == [("dismissed", False), ("approved", True)]
                and [r["commit"] for r in reviewed if r["by"]["kind"] == "machine_user"][-1]
                == body("P-7", 20)["head"]["sha"]),
        }

    def test_the_port_reads_each_grounded_rule_as_the_fake_assumes_it(self):
        # L-51 and sim/AGENTS.md: each rule of the fake GitHub a fixture grounds is read by the port from that same
        # fixture as the rule states it, or is named in NOT_READ with why. The fake is not run here: it answers no
        # request, so what it assumes is the rule's statement, which each reading holds.
        from sim import grounding
        grounded = {code: fixture for code, _, _, fixture, _ in grounding.RULES if fixture}
        reads = self.reads()
        self.assertEqual(set(grounded), set(reads) | set(NOT_READ))
        self.assertFalse(set(reads) & set(NOT_READ))
        self.assertLessEqual(set(NOT_READ.values()), WHY)
        for code, (replayed, holds) in reads.items():
            fixtures = grounded[code] if isinstance(grounded[code], tuple) else (grounded[code],)
            self.assertEqual({pathlib.PurePath(f).stem for f in fixtures}, replayed, code)
            self.assertTrue(holds, code)

    def test_a_recorded_refusal_is_no_answer(self):
        # FR-56: every refusal a trial recorded is placed, and each a port asks is read as no answer: a list of runs
        # GitHub did not find refuses the pass's read, and a diff too large to serve is read as truncated.
        found = {(path.stem, at) for path in sorted((ROOT / "trials").glob("P-*.json"))
                 for at, e in enumerate(json.loads(path.read_text()).get("exchanges", []))
                 if (e.get("request") or {}).get("via") in ("rest", "graphql")
                 and isinstance(e.get("response", {}).get("status"), int)
                 and (e["response"]["status"] >= 400
                      or (isinstance(e["response"].get("body"), dict) and e["response"]["body"].get("errors")))}
        self.assertEqual(found, set(REFUSALS))
        self.assertEqual(sorted({p for p in REFUSALS.values() if p}), ["diff", "dispatch", "graphql", "runs"])
        missing = exchanges("P-44")[3]
        call = missing["request"]["call"].split()[1].rstrip(",")
        workflow = call.split("/workflows/")[1].split("/")[0]
        with self.assertRaises(github.Unanswered):
            records.runs(github.Replay([asked(missing)]), canary(), "main", [workflow], DISPATCHER)
        self.assertTrue(pull.diff(compared("P-29.truncated", 4, body("P-29.truncated", 2)), body("P-29.truncated", 2),
                                  PINNED_BASE)["diff"]["truncated"])
        # A dispatch GitHub refuses, as P-27 recorded its 422, is a write that failed, never one sent.
        from tests import test_effects
        sending = test_effects.Effects()
        found = sending.dispatches()
        found[0]["response"] = copy.deepcopy(exchanges("P-27")[15]["response"])
        written, _ = sending.send(*found)
        self.assertEqual([(w["state"], w["reason"]) for w in written["writes"] if w["type"] in effects.DISPATCHES],
                         [("failed", "dispatch_refused"), ("sent", None), ("sent", None)])
        # A GraphQL read GitHub answers 200 with errors, as P-8 recorded over its resource limits, is no answer to any
        # port that reads GraphQL, even where the data it gave beside them would read: the checks, the threads and the
        # closing references.
        refused = exchanges("P-8")[1]["response"]["body"]["errors"]
        node = p32_pull()
        for port, answer, read in (
                ("checks", checks_answer(node), lambda t: checks.read(t, as_pull(node))),
                ("threads", threads_answer("o/r", 26, []),
                 lambda t: threads.read(t, Threads.PULL, timeline.Accounts(t, "o/r", MACHINE, {}))),
                ("acceptance", closing_answer("o/r", 26, []), lambda t: acceptance.closing(t, Acceptance.PULL))):
            read(github.Replay([copy.deepcopy(answer)]))
            answer["response"]["body"]["errors"] = copy.deepcopy(refused)
            with self.assertRaises(github.Unanswered, msg=port):
                read(github.Replay([answer]))


HOME = "combsmith/software-factory"
POLLER = "poller.yml"


def a_pass(ident: int, **change) -> dict:
    """A completed pass, the row `trials/P-17.json` lists a run as, made a run of the poller's file on the home repo."""
    row = copy.deepcopy(exchanges("P-17")[4]["response"]["body"]["workflow_runs"][0])
    row.update(id=ident, path=".github/workflows/%s" % POLLER, event="schedule", status="completed",
               conclusion="success", head_branch="main")
    row["repository"] = dict(row["repository"], full_name=HOME)
    row["head_repository"] = dict(row["head_repository"], full_name=HOME)
    row.update(change)
    return row


def passes_listed(rows: list, total=None) -> dict:
    """The poller's completed runs, newest first, in the answer `trials/P-17.json` recorded for a list of runs."""
    found = copy.deepcopy(exchanges("P-17")[4])
    found["request"] = dict(found["request"], call="GET /repos/%s/actions/workflows/%s/runs?branch=main&status=completed"
                            "&per_page=%d" % (HOME, POLLER, passes.PAGE), headers={"Cache-Control": "no-cache"})
    found["response"]["body"] = {"total_count": len(rows) if total is None else total, "workflow_runs": rows}
    return found


def a_record(now: str) -> dict:
    return dict(json.loads((ROOT / "examples" / "pass.json").read_text()), now=now)


def pass_stored(github_id: int, zipped, ident: int = 9, **listed) -> list:
    """A pass's artifact listed and downloaded, as `stored` gives an outcome's, under the pass's own names."""
    found = stored(HOME, github_id, zipped, ident, **listed)
    found[0]["request"]["call"] = found[0]["request"]["call"].replace("name=outcome", "name=pass")
    for artifact in found[0]["response"]["body"]["artifacts"]:
        artifact["name"] = passes.NAME
    return found


def pass_zip(record) -> bytes:
    return outcome_zip(record, passes.MEMBER)


class PassRecords(unittest.TestCase):
    OWN = 1

    def read(self, *found):
        return passes.records(github.Replay([e for f in found for e in (f if isinstance(f, list) else [f])]),
                              HOME, "main", POLLER, self.OWN)

    def test_the_last_two_pass_records_are_read(self):
        last, before = a_record("2026-10-11T12:57:00Z"), a_record("2026-10-11T12:54:00Z")
        rows = [a_pass(self.OWN), a_pass(30), a_pass(20, conclusion="failure"), a_pass(10), a_pass(5)]
        got = self.read(passes_listed(rows), pass_stored(30, None), pass_stored(20, pass_zip(last)),
                        pass_stored(10, pass_zip(before)))
        self.assertEqual(got, [before, last])
        # Runs that are not passes of the poller, from the default branch, of this repo, completed, are passed over.
        others = [a_pass(40, path=".github/workflows/run.yml"), a_pass(41, head_branch="other"),
                  a_pass(42, status="in_progress"), a_pass(43, event="push"),
                  a_pass(44, repository={"full_name": "a/fork"}), a_pass(45, head_repository={"full_name": "a/fork"}),
                  a_pass(46, repository=HOME), a_pass(47, head_repository=None)]
        got = self.read(passes_listed(others + [a_pass(10)]), pass_stored(10, pass_zip(before)))
        self.assertEqual(got, [before])
        # No pass before this one is none, and a record past its retention ends the reading.
        self.assertEqual(self.read(passes_listed([a_pass(self.OWN)])), [])
        self.assertEqual(self.read(passes_listed([a_pass(20), a_pass(10)]), pass_stored(20, pass_zip(last), expired=True)),
                         [])

    def test_unreadable_pass_records_are_none(self):
        last = pass_zip(a_record("2026-10-11T12:57:00Z"))
        self.assertIsNone(self.read(passes_listed([a_pass(20)]), pass_stored(20, last, size_in_bytes=len(last) + 1)))
        self.assertIsNone(self.read(passes_listed([a_pass(20)]), pass_stored(20, outcome_zip({}, "other.json"))))
        self.assertIsNone(self.read(passes_listed([a_pass(20)]), pass_stored(20, pass_zip(b"not json"))))
        self.assertIsNone(self.read(passes_listed([a_pass(20)], total=0), pass_stored(20, last)))
        self.assertIsNone(self.read(passes_listed([dict(a_pass(20), id=True)])))
        # A page read through with fewer than two found, while GitHub counts more, is not every pass.
        self.assertIsNone(self.read(passes_listed([a_pass(20)], total=passes.PAGE + 1), pass_stored(20, last)))
        unanswered = passes_listed([])
        unanswered["response"]["status"] = 502
        self.assertIsNone(self.read(unanswered))
        self.assertIsNone(passes.records(github.Replay([]), HOME, "main", POLLER, self.OWN))

    def test_a_pass_record_alone_is_downloaded_under_a_wider_bound(self):
        sent = Recording(github.Replay([passes_listed([a_pass(20)])]
                                       + pass_stored(20, pass_zip(a_record("2026-10-11T12:57:00Z")))))
        passes.records(sent, HOME, "main", POLLER, self.OWN)
        self.assertEqual([r.get("bound") for r in sent.sent if r.get("follow")], [github.PASSED])
        self.assertEqual(github.download("/repos/o/r/actions/artifacts/9/zip")["bound"], github.STORED)
        for bound in (github.STORED + 1, github.PASSED + 1, True, "1048576"):
            with self.assertRaises(github.Unanswered, msg=bound):
                github.download("/repos/o/r/actions/artifacts/9/zip", bound)
        with self.assertRaises(github.Unanswered):
            github.request("GET", "/repos/o/r/actions/runs/1", bound=github.PASSED)
        # Over 64 KiB zipped, a record is read under the pass's bound and refused under any other.
        big = {"status": 200, "headers": {}, "body": "z" * (github.STORED + 1)}
        listed = pass_stored(20, b"z" * (github.STORED + 1))
        listed[-1]["response"] = big
        self.assertEqual(github.Replay(listed[1:]).send(
            github.download("/repos/%s/actions/artifacts/9/zip" % HOME, github.PASSED))["status"], 200)
        with self.assertRaises(github.Unanswered):
            github.Replay(listed[1:]).send(github.download("/repos/%s/actions/artifacts/9/zip" % HOME))
        # The zip's file is read out to 8 MiB and no further, whatever the zip says.
        self.assertIsNone(artifacts._member(pass_zip(b"x" * (passes.HELD + 1)), passes.MEMBER, passes.HELD))
        self.assertEqual(len(artifacts._member(pass_zip(b"x" * passes.HELD), passes.MEMBER, passes.HELD)), passes.HELD)

    @pending
    def test_a_pass_record_a_trial_downloaded_is_read_as_the_port_reads_it(self):
        # No trial has recorded a pass's artifact yet: the first pass that uploads one, read back by the next, records it.
        found = [(name.stem, at) for name in sorted((ROOT / "trials").glob("P-*.json"))
                 for at, e in enumerate(json.loads(name.read_text()).get("exchanges", []))
                 if "artifacts?name=pass" in str((e.get("request") or {}).get("call"))]
        self.assertTrue(found)

    def test_a_pass_is_started_by_its_own_run(self):
        recorded = copy.deepcopy(exchanges("P-9")[10])
        repo, ident = recorded["response"]["body"]["repository"]["full_name"], recorded["response"]["body"]["id"]
        got = passes.started(github.Replay([recorded]), repo, str(ident))
        self.assertEqual(got, {"event": "workflow_dispatch", "actor": {"id": MAINTAINER, "type": "User"}, "attempt": 1})
        for change in ({"id": ident + 1}, {"repository": {"full_name": "a/fork"}}, {"repository": repo}, {"run_attempt": 0},
                       {"run_attempt": True}, {"event": None}):
            varied = copy.deepcopy(recorded)
            varied["response"]["body"].update(change)
            self.assertIsNone(passes.started(github.Replay([varied]), repo, str(ident)), change)
        varied = copy.deepcopy(recorded)
        varied["response"]["body"]["actor"] = {"id": "1", "type": "User"}
        self.assertEqual(passes.started(github.Replay([varied]), repo, str(ident))["actor"], None)
        for bad in ("", "0", "1/../2", "1?x=2", 1, None):
            sent = Recording(github.Replay([]))
            self.assertIsNone(passes.started(sent, repo, bad), bad)
            self.assertEqual(sent.sent, [], bad)
        self.assertIsNone(passes.started(github.Replay([]), repo, str(ident)))


def open_page(numbers: list, total=None, more: bool = False, after=None, cursor="Y3Vyc29y", repo=HOME) -> dict:
    """A page of open pull requests, in the answer's shape `trials/P-32.json` recorded, asked as the items port asks."""
    found = copy.deepcopy(exchanges("P-32")[1])
    owner, name = repo.split("/")
    found["request"] = dict(found["request"], call="POST /graphql",
                            body={"query": items.QUERY, "variables": {"owner": owner, "name": name, "after": after}})
    shape = found["response"]["body"]["data"]["repository"]
    found["response"]["body"] = {"data": {"repository": {
        "nameWithOwner": shape["nameWithOwner"],
        "pullRequests": {"totalCount": len(numbers) if total is None else total,
                         "pageInfo": {"hasNextPage": more, "endCursor": cursor},
                         "nodes": [{"number": n} for n in numbers]}}}}
    return found


class Items(unittest.TestCase):
    def read(self, *pages):
        return items.open_pull_requests(github.Replay(list(pages)), HOME)

    def test_open_pull_requests_are_whole_only_if_each_was_read(self):  # L-53
        self.assertEqual(self.read(open_page([216])), ([216], True))
        self.assertEqual(self.read(open_page([])), ([], True))
        self.assertEqual(self.read(open_page([1, 2], total=3, more=True, cursor="c1"), open_page([3], total=3, after="c1")),
                         ([1, 2, 3], True))
        # A count that moved, a pull request read twice, or fewer read than counted is not the whole.
        self.assertEqual(self.read(open_page([1, 2], total=3, more=True, cursor="c1"), open_page([3], total=4, after="c1"))[1],
                         False)
        self.assertEqual(self.read(open_page([1, 2], total=3, more=True, cursor="c1"), open_page([2], total=3, after="c1"))[1],
                         False)
        self.assertEqual(self.read(open_page([1], total=2))[1], False)
        self.assertEqual(self.read(open_page([1], more=True, cursor=None))[1], False)
        self.assertEqual(self.read(open_page([0]))[1], False)
        self.assertEqual(self.read(open_page([True]))[1], False)
        broken = open_page([1])
        broken["response"]["body"]["data"]["repository"]["pullRequests"]["pageInfo"] = {}
        self.assertEqual(self.read(broken)[1], False)
        # A page past the most read is never the whole.
        many = [open_page([n], total=items.PAGES, more=True, after=None if n == 1 else "c%d" % (n - 1), cursor="c%d" % n)
                for n in range(1, items.PAGES + 1)]
        self.assertEqual(self.read(*many)[1], False)

    def test_open_pull_requests_of_another_repo_or_with_errors_are_refused(self):
        other = open_page([1])
        other["response"]["body"]["data"]["repository"]["nameWithOwner"] = "a/fork"
        erred = open_page([1])
        erred["response"]["body"]["errors"] = [{"type": "RATE_LIMITED"}]
        failed = open_page([1])
        failed["response"]["status"] = 502
        for answer in (other, erred, failed):
            with self.assertRaises(github.Unanswered):
                self.read(answer)


if __name__ == "__main__":
    unittest.main()
