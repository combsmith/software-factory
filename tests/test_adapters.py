"""The facts port's reads of a pull request, replayed from the trials' fixtures through the one transport.

Each test feeds a part of `adapters/pull.py` the exchanges a fixture recorded, through `adapters.github.Replay`, which
answers nothing a fixture does not hold, and holds the part to what the fixture shows GitHub said. Nothing here reaches
the network: the live transport is held by what it refuses before it sends anything.
"""
from __future__ import annotations

import copy
import io
import json
import pathlib
import unittest

from adapters import github, pull
from tests.support import pending

ROOT = pathlib.Path(__file__).resolve().parent.parent


def exchanges(name: str) -> list:
    return json.loads((ROOT / "trials" / ("%s.json" % name)).read_text())["exchanges"]


def body(name: str, at: int):
    return copy.deepcopy(exchanges(name)[at]["response"]["body"])


def replay(name: str, *at: int) -> github.Replay:
    found = exchanges(name)
    return github.Replay([found[i] for i in at])


def person(login: str) -> dict:
    return {"maintainer": {(login, "User")}}


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
        # A step taken by git or the command line is no request the transport sends, and is never an answer.
        self.assertEqual(github.Replay(exchanges("P-29.base")[:1])._left, [])

    def test_a_request_stays_on_githubs_api(self):
        for path in ("https://example.com/x", "//example.com/x", "example.com/x", "/x\\..\\y", "http://api.github.com/x"):
            with self.assertRaises(github.Unanswered, msg=path):
                github.request("GET", path)
        with self.assertRaises(github.Unanswered):
            github.request("TRACE", "/x")
        self.assertEqual(github.request("GET", "/repos/o/r")["accept"], github.JSON)

    def test_the_live_transport_takes_its_token_from_its_caller_and_follows_no_redirect(self):
        for token in ("", " ", "a b", None):
            with self.assertRaises(github.Unanswered, msg=repr(token)):
                github.Live(token)
        with self.assertRaises(github.Unanswered):
            github._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://example.com/")
        # The answer it builds keeps the headers and reads JSON as JSON, and anything else as text.
        answer = github._answer(200, {"Content-Type": "application/json; charset=utf-8"}, b'{"a": 1}')
        self.assertEqual(answer, {"status": 200, "headers": {"content-type": "application/json; charset=utf-8"},
                                  "body": {"a": 1}})
        self.assertEqual(github._answer(200, {"Content-Type": github.DIFF}, b"diff --git")["body"], "diff --git")
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
        part, title = pull.own(data, person("don-petry"))
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
        self.assertEqual(pull.own(data, {"maintainer": {("don-petry", "Bot")}})[0]["class"], "outside")
        self.assertEqual(pull.own(data, {"agent": {("don-petry", "User")}})[0]["class"], "agent")
        self.assertEqual(pull.own(data, {"dependency": {("don-petry", "User")}})[0]["class"], "dependency")
        fork = copy.deepcopy(data)
        fork["head"]["repo"]["full_name"] = "someone/fork"
        self.assertEqual(pull.own(fork, person("don-petry"))[0]["class"], "outside")
        gone = copy.deepcopy(data)
        gone["head"]["repo"] = None
        self.assertEqual(pull.own(gone, person("don-petry"))[0]["class"], "outside")

    def test_a_merge_a_state_and_an_unknown_mergeable_are_read_as_github_gives_them(self):
        data = body("P-29.base", 1)
        data["state"], data["merged_at"] = "closed", "2026-10-18T02:00:00Z"
        self.assertEqual(pull.own(data, {})[0]["state"], "merged")
        data["merged_at"], data["mergeable"] = None, None
        self.assertEqual(pull.own(data, {})[0]["state"], "closed")
        self.assertIsNone(pull.own(data, {})[0]["mergeable"])
        for broken in ({"state": "reopened"}, {"draft": None}, {"user": None}, {"user": {"login": "x", "type": "Org"}}):
            bad = dict(copy.deepcopy(data), **broken)
            with self.assertRaises(github.Unanswered, msg=broken):
                pull.own(bad, {})

    def test_the_base_branchs_protection_is_read_from_the_branch(self):
        self.assertIs(pull.targets_protected(replay("P-29.base", 9), body("P-29.base", 1)), False)
        unread = copy.deepcopy(exchanges("P-29.base")[9])
        del unread["response"]["body"]["protected"]
        with self.assertRaises(github.Unanswered):
            pull.targets_protected(github.Replay([unread]), body("P-29.base", 1))


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

    def test_a_fork_is_read_as_no_one_and_its_activity_is_never_asked(self):
        fork = body("P-28", 10)
        fork["head"]["repo"]["full_name"] = "someone/fork"
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
        for change in ({"filename": "p29-many-lines.txt"}, {"filename": ""}, {"filename": None}):
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


if __name__ == "__main__":
    unittest.main()
