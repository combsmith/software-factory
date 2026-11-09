"""The release step's own exchanges, kept for its run's artifact (issue 531): what `release/exchanges.py` keeps of each,
and what it leaves out, since anyone signed in may download an artifact of a public repo."""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from adapters import github
from release import exchanges, move
from tests.test_release_step import D, NEXT, SET, STORE, VERSION, cut_reads
from tests.test_tools import SHAPED
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = "combsmith/software-factory"


class Answering:
    """A transport that answers each request with the next of `answers`, as `Live` would hand it back."""

    def __init__(self, *answers):
        self.answers, self.asked = list(answers), []

    def send(self, req):
        self.asked.append(req)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def written(recording) -> str:
    return json.dumps(recording.kept(), sort_keys=True)


class Kept(unittest.TestCase):
    def test_the_leak_surface_is_left_out(self):
        # Each of the five things box 1 of #531 names, sent as GitHub could, and none of it kept.
        token = SHAPED["ghs"]
        signed = SHAPED["signed url"]
        recording = exchanges.Recording(Answering(
            # A body's field no list names, beside one that is kept; and a header no fixture keeps, beside one it does.
            {"status": 200, "headers": {"etag": "W/\"1\"", "set-cookie": "user_session=E2F1A08A3", "location": signed},
             "body": [{"ref": "refs/tags/" + NEXT, "object": {"sha": D, "type": "commit"}, "url": signed,
                       "node_id": "MDM6UmVm", "unknown": token}]},
            # An artifact's download, followed to the storage: its address and its bytes are never kept.
            {"status": 200, "headers": {"content-type": "application/zip", "location": STORE},
             "body": "PK\x03\x04 the eval report, which may hold a held-out case"},
            # A file at a commit: its text, base64 in a JSON body, is never kept.
            {"status": 200, "headers": {"content-type": "application/json"},
             "body": {"name": "manifest.json", "content": "c3ludGhldGljLWVhcmx5LXJldHVybg==", "sha": "f" * 40,
                      "download_url": signed}},
            # An error: its message and documentation are kept, redacted; anything else it carries is not.
            {"status": 404, "headers": {}, "body": {"message": "Not Found " + token, "documentation_url": "https://docs",
                                                    "errors": [{"value": "the text of a file at a commit"}]}},
            # A body that is not JSON, at a path no rule names: its text is never kept.
            {"status": 502, "headers": {"content-type": "text/html"}, "body": "<html>a gateway's page, quoting a log</html>"},
        ))
        recording.send(github.request("GET", "/repos/%s/git/matching-refs/tags/factory" % REPO))
        recording.send(github.download("/repos/%s/actions/artifacts/9/zip" % REPO))
        recording.send(github.request("GET", "/repos/%s/contents/evals/manifest.json?ref=%s" % (REPO, D)))
        recording.send(github.request("GET", "/repos/%s/compare/%s...%s" % (REPO, D, "e" * 40)))
        recording.send(github.request("GET", "/repos/%s/git/ref/heads/main" % REPO))
        text = written(recording)
        for left in (token, signed, STORE, "E2F1A08A3", "MDM6UmVm", "held-out", "c3ludGhldGlj", "text of a file",
                     "location", "gateway's page"):
            self.assertNotIn(left, text, left)
        kept = recording.kept()["exchanges"]
        self.assertEqual(kept[0]["response"]["body"], [{"ref": "refs/tags/" + NEXT,
                                                        "object": {"sha": D, "type": "commit"}}])
        self.assertEqual(kept[0]["response"]["headers"], {"etag": "W/\"1\""})
        self.assertEqual(set(kept[1]["response"]), {"status", "headers", "measured"})
        self.assertEqual(set(kept[1]["response"]["measured"]), {"size", "sha256"})
        self.assertEqual(set(kept[2]["response"]["measured"]), {"size", "sha256"})
        self.assertEqual(kept[3]["response"]["body"], {"documentation_url": "https://docs"})
        self.assertEqual(set(kept[4]["response"]["measured"]), {"size", "sha256"})
        self.assertIn("exchanges[3].response.body.message", recording.kept()["removed"])
        self.assertEqual(kept[0]["request"]["as"], {"kind": "app", "name": "release"})
        self.assertNotIn("authorization", json.dumps([e["request"]["headers"] for e in kept]).lower())

    def test_every_counter_example_of_the_trials_redaction_is_left_out_here(self):
        # The Factory Builder's ruling on #531: one set of patterns, held to every case the trials' own tests use.
        for name, value in SHAPED.items():
            recording = exchanges.Recording(Answering(
                {"status": 200, "headers": {"etag": value}, "body": {"message": value, "ref": [value], "name": "x"}}))
            recording.send(github.request("POST", "/repos/%s/git/refs" % REPO, body={"ref": value, "sha": D}))
            self.assertNotIn(value, written(recording), name)

    def test_importing_the_redaction_starts_nothing_and_reads_nothing_but_modules(self):
        # The ruling's first condition: what release/ imports of tools/ is pure at import.
        probe = ("import sys\nseen = []\n"
                 "sys.addaudithook(lambda event, args: seen.append((event, args[0] if args else None)))\n"
                 "import release.exchanges\n"
                 "bad = [e for e in seen if e[0] in ('subprocess.Popen', 'os.system', 'os.exec', 'socket.connect',"
                 " 'os.spawn', 'os.posix_spawn') or (e[0] == 'open' and isinstance(e[1], str)"
                 " and not e[1].endswith(('.py', '.pyc')))]\nprint(bad)\n")
        done = subprocess.run([sys.executable, "-c", probe], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "[]"), done.stderr)

    def test_a_fault_in_keeping_never_changes_what_the_step_is_answered(self):
        answer = {"status": 200, "headers": None, "body": {"ref": object()}}
        recording = exchanges.Recording(Answering(answer, ValueError("refused")))
        self.assertIs(recording.send(github.request("GET", "/repos/%s" % REPO)), answer)
        with self.assertRaises(ValueError):
            recording.send(github.request("GET", "/repos/%s" % REPO))
        self.assertEqual(recording.kept()["exchanges"][-1]["response"], {"raised": "ValueError"})
        broken = exchanges.Recording(Answering("not an answer"))
        self.assertEqual(broken.send(github.request("GET", "/repos/%s" % REPO)), "not an answer")
        self.assertEqual((broken.kept()["exchanges"], broken.kept()["unkept"]), ([], 1))

    def test_it_writes_only_the_one_file_in_the_folder_the_workflow_names(self):
        folder = pathlib.Path(tempfile.mkdtemp())
        recording = exchanges.Recording(Answering())
        for wrong in ("relative", str(folder / "gone")):
            self.assertFalse(recording.write(wrong), wrong)
        self.assertTrue(recording.write(str(folder)))
        self.assertFalse(recording.write(str(folder)))      # never over a file that stands
        self.assertEqual(json.loads((folder / exchanges.NAME).read_text())["schema"], "release-exchanges/1")


class TheStep(unittest.TestCase):
    def run_main(self, environ, connect) -> tuple:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = move.main([], environ=environ, connect=connect)
        return code, out.getvalue()

    def test_a_cut_keeps_each_exchange_and_prints_what_it_printed_before(self):
        folder = pathlib.Path(tempfile.mkdtemp())
        env = {"RELEASE_COMMAND": "cut", "RELEASE_VERSION": VERSION, "RELEASE_CUT_COMMIT": D, "RELEASE_TOKEN": "t"}
        plain = self.run_main(env, lambda token: github.Replay(cut_reads()))
        kept = self.run_main(dict(env, RELEASE_EXCHANGES=str(folder)),
                             lambda token: github.Replay(cut_reads()))
        self.assertEqual(kept, plain)
        self.assertEqual(plain[0], 0)
        data = json.loads((folder / exchanges.NAME).read_text())
        schema = json.loads((ROOT / "schemas" / "release-exchanges.schema.json").read_text())
        self.assertEqual(validate(data, schema), [])
        calls = [e["request"]["call"] for e in data["exchanges"]]
        # The download and its storage's answer, two exchanges of the replay, are one send of the step.
        self.assertEqual(len(calls), len(cut_reads()) - 1)
        self.assertIn("POST /repos/%s/deployments" % REPO, calls)
        text = json.dumps(data)
        for left in (STORE, SET["cases"][0]["id"]):
            self.assertNotIn(left, text)
        self.assertNotIn("release-exchanges", plain[1])

    def test_a_step_that_stops_or_fails_still_keeps_what_it_sent(self):
        folder = pathlib.Path(tempfile.mkdtemp())
        env = {"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": "t", "RELEASE_TO": "factory/v0.1.0",
               "RELEASE_EXCHANGES": str(folder)}
        code, printed = self.run_main(env, lambda token: Answering(RecursionError("what GitHub answered")))
        self.assertEqual((code, json.loads(printed)), (1, {"writes": [], "deployments": [], "refused": "step_failed"}))
        data = json.loads((folder / exchanges.NAME).read_text())
        self.assertEqual([e["response"] for e in data["exchanges"]], [{"raised": "RecursionError"}])
        self.assertNotIn("what GitHub answered", (folder / exchanges.NAME).read_text())

    def test_with_no_file_named_nothing_is_kept(self):
        folder = pathlib.Path(tempfile.mkdtemp())
        env = {"RELEASE_COMMAND": "cut", "RELEASE_VERSION": VERSION, "RELEASE_CUT_COMMIT": D, "RELEASE_TOKEN": "t"}
        seen = []
        self.run_main(env, lambda token: seen.append(1) or github.Replay(cut_reads()))
        self.assertEqual(list(folder.iterdir()), [])
        self.assertEqual(seen, [1])


if __name__ == "__main__":
    unittest.main()
