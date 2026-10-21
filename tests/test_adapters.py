"""The facts port's reads of a pull request, replayed from the trials' fixtures through the one transport.

Each test feeds a part of `adapters/pull.py` the exchanges a fixture recorded, through `adapters.github.Replay`, which
answers nothing a fixture does not hold, and holds the part to what the fixture shows GitHub said. Nothing here reaches
the network: the live transport is held by what it refuses before it sends anything.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import pathlib
import unittest

from adapters import github, pull, records
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


class Diff(unittest.TestCase):
    def test_the_content_is_the_hash_of_the_diff_as_github_served_it(self):
        # trials/P-29.base.json: the hash taken as each diff arrived is the one the port computes.
        hashes = body("P-29.base", 24)
        for at, answer, moment in ((1, 2, "before the base moved"), (12, 13, "after the plain push"),
                                   (21, 22, "after the force push")):
            got = pull.diff(replay("P-29.base", answer), body("P-29.base", at))
            self.assertEqual(got["content_id"], "sha256:" + hashes[moment], moment)
            self.assertIs(got["complete"], True, moment)
            self.assertEqual(got["diff"]["truncated"], False)
        self.assertEqual(pull.diff(replay("P-29.base", 2), body("P-29.base", 1))["diff"],
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
            got = pull.diff(github.Replay([exchange]), data)
            self.assertEqual(got["content_id"], "sha256:" + hashlib.sha256(sent).hexdigest())
            self.assertIs(got["complete"], True)
            ids.append(got["content_id"])
        self.assertNotEqual(*ids)

    def test_a_diff_that_disagrees_with_the_counts_is_a_short_read(self):
        # Decision 0002: the diff is held to the same pull request's counts; a difference is a short read.
        data = body("P-29.base", 1)
        data["additions"] += 1
        self.assertIs(pull.diff(replay("P-29.base", 2), data)["complete"], False)
        data = body("P-29.base", 1)
        data["changed_files"] += 1
        self.assertIs(pull.diff(replay("P-29.base", 2), data)["complete"], False)

    def test_a_diff_github_will_not_serve_is_truncated_and_new_content_at_every_push(self):
        # trials/P-29.truncated.json: 3,001 files, a 406 too_large. Read whole, so the Kernel holds it as too large;
        # its content is the head commit's, so a push is never read as unchanged.
        data = body("P-29.truncated", 2)
        got = pull.diff(replay("P-29.truncated", 4), data)
        self.assertEqual((got["diff"], got["complete"]), ({"files": 3001, "lines": 3001, "truncated": True}, True))
        moved = copy.deepcopy(data)
        moved["head"]["sha"] = "0" * 40
        self.assertNotEqual(pull.diff(replay("P-29.truncated", 4), moved)["content_id"], got["content_id"])
        # A 406 for anything but too_large, and a head that cannot be read, are refused.
        other = copy.deepcopy(exchanges("P-29.truncated")[4])
        other["response"]["body"]["errors"][0]["code"] = "not_acceptable"
        with self.assertRaises(github.Unanswered):
            pull.diff(github.Replay([other]), data)
        no_head = copy.deepcopy(data)
        no_head["head"]["sha"] = ""
        with self.assertRaises(github.Unanswered):
            pull.diff(replay("P-29.truncated", 4), no_head)

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
            pull.diff(github.Replay([broken]), body("P-29.base", 1))


def files_pages(pages: int, last: list) -> list:
    """Pages 1 to `pages` of pull request 27's files, shaped as P-29.truncated's page 30, then that page and `last`."""
    found = exchanges("P-29.truncated")
    page30, page31 = found[10], found[11]
    base = page30["request"]["call"].split()[1].split("&page=")[0]
    out = []
    for n in range(1, pages):
        rows = [dict(row, filename="p29-many-files/f%04d.txt" % ((n - 1) * 100 + i + 1))
                for i, row in enumerate(page30["response"]["body"])]
        call = "GET %s" % (base if n == 1 else "%s&page=%d" % (base, n))
        out.append({"request": dict(page30["request"], call=call), "response": dict(page30["response"], body=rows)})
    return out + [page30, dict(page31, response=dict(page31["response"], body=last))]


class ChangedPaths(unittest.TestCase):
    def test_every_file_is_read_and_the_list_is_whole_when_it_holds_the_count(self):
        got = pull.changed_paths(replay("P-29.truncated", 13), body("P-29.truncated", 12))
        self.assertEqual(got, {"changed_paths": [{"path": "p29-many-lines-2.txt", "previous": None},
                                                 {"path": "p29-many-lines.txt", "previous": None}],
                               "complete": True})

    def test_a_list_github_stops_short_of_the_count_is_never_the_whole(self):
        # trials/P-29.truncated.json: 3,001 files; page 30 is the last GitHub serves, and page 31 is a 200 with none.
        got = pull.changed_paths(github.Replay(files_pages(30, [])), body("P-29.truncated", 2))
        self.assertEqual((len(got["changed_paths"]), got["complete"]), (3000, False))

    def test_a_list_at_an_exact_page_count_asks_for_no_page_past_it(self):
        data = body("P-29.truncated", 2)
        data["changed_files"] = 200
        pages = files_pages(3, [])[:2]
        got = pull.changed_paths(github.Replay(pages), data)
        self.assertEqual((len(got["changed_paths"]), got["complete"]), (200, True))

    def test_a_rename_or_a_copy_gives_both_names_and_one_without_its_old_name_is_short(self):
        data = body("P-29.truncated", 12)
        rows = body("P-29.truncated", 13)
        rows[0].update(status="renamed", previous_filename="old/name.txt")
        rows[1].update(status="copied", previous_filename="p29-many-lines-2.txt")
        answer = dict(exchanges("P-29.truncated")[13], response=dict(exchanges("P-29.truncated")[13]["response"],
                                                                     body=rows))
        got = pull.changed_paths(github.Replay([answer]), data)
        self.assertEqual([p["previous"] for p in got["changed_paths"]], ["old/name.txt", "p29-many-lines-2.txt"])
        self.assertIs(got["complete"], True)
        del rows[0]["previous_filename"]
        self.assertIs(pull.changed_paths(github.Replay([answer]), data)["complete"], False)

    def test_a_list_with_a_name_twice_or_none_is_short(self):
        data = body("P-29.truncated", 12)
        for change in ({"filename": "p29-many-lines.txt"}, {"filename": ""}, {"filename": None}, {"status": "moved"},
                       {"status": None}, {"previous_filename": "was.txt"}):
            rows = body("P-29.truncated", 13)
            rows[0].update(change)
            answer = dict(exchanges("P-29.truncated")[13], response=dict(exchanges("P-29.truncated")[13]["response"],
                                                                         body=rows))
            self.assertIs(pull.changed_paths(github.Replay([answer]), data)["complete"], False, change)

    @pending
    def test_a_renamed_file_is_read_with_its_old_name_from_a_fixture(self):
        # No fixture yet holds a rename: P-43 (issue 250) records one. Until then the rename is held by the synthetic
        # case above, and this test, which reads the fixture, is expected to fail.
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


class Records(unittest.TestCase):
    def read(self, *found, **kw):
        slept = []
        got = records.runs(github.Replay(list(found)), canary(), "main", [WORKFLOW], kw.get("dispatcher", DISPATCHER),
                           per_page=kw.get("per_page", 10), sleep=slept.append)
        return got, slept

    def test_a_run_listed_under_its_workflows_name_is_unidentified_after_one_more_read(self):
        # trials/P-17.json: just after the dispatch the run is listed under its workflow's name, and at the read after
        # it under the trial's own, neither a run-name: it is reported by its GitHub id, never dropped, and the port
        # waited once (decision 0036).
        got, slept = self.read(listing("P-17", 9, total=1), listing("P-17", 10, total=1), per_page=1)
        self.assertEqual(exchanges("P-17")[9]["response"]["body"]["workflow_runs"][0]["name"], "p17-p22-run-records")
        self.assertEqual((got["runs"], got["unidentified"], got["complete"], slept), ([], ["39086879694"], True, [5]))

    def test_a_run_named_by_the_second_read_is_a_record(self):
        second = listing("P-17", 10, total=1, rows={"name": NAME})
        got, slept = self.read(listing("P-17", 9, total=1), second, per_page=1)
        self.assertEqual((got["unidentified"], slept), ([], [5]))
        self.assertEqual(got["runs"], [{"run": "r_01JA6Z", "item": {"repo": "combsmith/software-factory",
                                        "type": "pull_request", "number": 264}, "intent": "review-change",
                                        "role": "pr-review", "content_id": "sha256:5d0c", "status": "queued",
                                        "conclusion": None, "outcome": None,
                                        "started_at": second["response"]["body"]["workflow_runs"][0]["run_started_at"]}])

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

    def test_a_run_that_did_not_succeed_leaves_the_list_not_whole_until_its_outcome_is_read(self):
        # Decision 0029: a failed Run's outcome is read from its artifact, which waits on adapters/artifacts.py. Until
        # then the list holding it is not whole, so that the Kernel defers and never reads it as no attempt.
        done = {"name": NAME, "status": "completed"}
        got, _ = self.read(listing("P-17", 3, rows=dict(done, conclusion="success")))
        self.assertEqual((got["runs"][0]["conclusion"], got["complete"]), ("success", True))
        for conclusion, read in (("startup_failure", "failure"), ("timed_out", "timed_out"), ("cancelled", "cancelled")):
            got, _ = self.read(listing("P-17", 3, rows=dict(done, conclusion=conclusion)))
            self.assertEqual((got["runs"][0]["conclusion"], got["complete"]), (read, False), conclusion)

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
                ids = [str(r["id"]) for r in listed["workflow_runs"]]
                self.assertEqual((got["runs"], got["unidentified"], got["complete"]), ([], ids, True), (name, at))

    @pending
    def test_the_outcome_of_a_run_that_did_not_succeed_is_read(self):
        # Decision 0029: outcome.json is read for a Run that did not succeed. The artifact is downloaded by a redirect
        # off GitHub's API, which the transport follows none of (decision 0044), so this waits on adapters/artifacts.py.
        self.assertTrue(callable(records.outcome))


if __name__ == "__main__":
    unittest.main()
