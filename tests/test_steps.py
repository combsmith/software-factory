"""The steps a Run's jobs run (issue 196, PR 2b-1): the reader's step that reads what the Task is built from, `run`'s
form that takes its folder, `verify`, `apply`'s step and the outcome it always leaves, the approving act's step, and the
Controller's token minted from its key in the effects step. Each step is driven with its ports stood in for, as the
workflow will call it; nothing here reaches the network, and each test reads and writes in a scratch folder alone."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import pathlib
import tempfile
import unittest
import unittest.mock

from adapters import effects, github, identity, passes
from controller import writes as writes_
from harness import apply_step, approve_step, outcome, read, reread, run, steps, verify
from tests import support
from tests import test_controller as tc
from tests.test_adapters import Recording, a_pass, a_record, pass_stored, pass_zip, passes_listed

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOME = "combsmith/software-factory"
DIFF = b"diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"
CONTENT = "sha256:" + hashlib.sha256(DIFF).hexdigest()
HEAD = "9f1c2d3e4b5a69788796a5b4c3d2e1f0a9b8c7d6"
RELEASE = "factory/v0.3.1"


def admitted():
    """A pass record that admitted one Run on pull request 42's content, its run-name and its Run id."""
    out = tc.passed(tc.reads(pulls=[tc.pr(content_id=CONTENT)]))
    return out["record"], out["dispatch"][0]["name"], out["dispatch"][0]["run"]


RECORD, NAME, RUN = admitted()
ITEM = "%s#42" % HOME
PASS = RECORD["pass"]


def ran(step, *given):
    """The step's exit and what it printed."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        code = steps.run(step, *given)
    return code, printed.getvalue()


class Shared(unittest.TestCase):
    def test_a_steps_files_are_new_and_its_own(self):
        with tempfile.TemporaryDirectory() as d:
            folder = steps.new_folder(d, "out")
            steps.write(folder, "a.json", {"a": 1})
            steps.write(folder, "b", b"bytes")
            self.assertEqual(os.stat(os.path.join(folder, "a.json")).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(folder).st_mode & 0o777, 0o700)
            with self.assertRaises(FileExistsError):
                steps.write(folder, "a.json", {})
            for taken in ("out", "../elsewhere", "/tmp"):
                with self.assertRaises(steps.Stop, msg=taken):
                    steps.new_folder(d, taken)
            os.symlink(os.path.join(d, "nowhere"), os.path.join(d, "link"))
            with self.assertRaises(steps.Stop):
                steps.new_folder(d, "link")
        self.assertEqual(ran(lambda: "fine"), (0, "fine\n"))
        self.assertEqual(ran(lambda: (_ for _ in ()).throw(steps.Stop("a_code"))), (1, "a_code\n"))
        self.assertEqual(ran(lambda: (_ for _ in ()).throw(ValueError("GitHub said something"))), (1, "step_failed\n"))


class Reader(unittest.TestCase):
    """The reader's step, its ports stood in for: what it reads, what it holds them to, and its token."""

    def go(self, record=RECORD, head=HEAD, first=HEAD, change=DIFF, revoked=True, argv=None, environ=None):
        calls = {"minted": [], "revoked": 0}

        def from_key(app, repo, wanted, key, now, connect):
            if not key:
                raise identity.Refused("key_unreadable")
            calls["minted"].append((app["name"], repo, wanted, key))

            def revoke():
                calls["revoked"] += 1
                return revoked
            return "the reader's transport", revoke
        facts = support.facts(item=dict(support.ITEM, number=42), content_id=CONTENT)
        pulled = {"head": {"sha": first}, "number": 42}
        with tempfile.TemporaryDirectory() as d, \
                unittest.mock.patch.object(identity, "from_key", from_key), \
                unittest.mock.patch.object(passes, "find", lambda *a: copy.deepcopy(record)), \
                unittest.mock.patch.object(read.facts_, "snapshot", lambda *a, **k: (facts, "title", head)), \
                unittest.mock.patch.object(read.pull, "read", lambda *a: pulled), \
                unittest.mock.patch.object(read.pull, "base", lambda *a: {"head": "b" * 40}), \
                unittest.mock.patch.object(read.pull, "change", lambda *a: change):
            code, printed = ran(read.step, argv or [NAME, ITEM, PASS, "task"],
                                environ if environ is not None else {read.KEY: "the key"}, d)
            folder = pathlib.Path(d, "task")
            files = sorted(p.name for p in folder.iterdir()) if folder.is_dir() else None
            kept = {n: (folder / n).read_bytes() for n in files or ()}
        return code, printed, files, kept, calls

    def test_the_reader_writes_the_tasks_inputs(self):
        code, printed, files, kept, calls = self.go()
        self.assertEqual((code, files), (0, sorted(read.FILES)), printed)
        self.assertEqual(kept["diff"], DIFF)
        self.assertEqual(kept["run"].decode().strip(), RUN)
        self.assertEqual(json.loads(kept["record.json"]), RECORD)
        self.assertEqual((json.loads(kept["texts.json"]), json.loads(kept["findings.json"])), ([], []))
        self.assertEqual(json.loads(kept["role.json"])["name"], "pr-review")
        # Minted once, for the home repo, with reads alone, and revoked once.
        (app, repo, wanted, key), = calls["minted"]
        self.assertEqual((app, repo, key, calls["revoked"]), ("combsmith-sf-reader", HOME, "the key", 1))
        self.assertEqual(set(wanted.values()), {"read"})
        # What `run` takes from the folder is what the reader wrote.
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "task"))
            for name, data in kept.items():
                pathlib.Path(d, "task", name).write_bytes(data)
            self.assertEqual(run.from_folder("task", "result", d)[:2], [os.path.join("task", "record.json"), RUN])
            pathlib.Path(d, "task", "run").write_text("../../x\n")
            with self.assertRaises(run.task.Refused):
                run.from_folder("task", "result", d)

    def test_the_reader_fails_closed(self):
        other = copy.deepcopy(RECORD)
        for e in other["pull_requests"]:
            if e["run"] == RUN:
                e["decision"]["admit"]["intent"] = "fix-findings"
        for change, want in (({"record": None}, "record_not_found"), ({"record": other}, "not_the_decision"),
                             ({"first": "a" * 40}, "head_moved"), ({"change": DIFF + b"+c\n"}, "content_moved"),
                             ({"revoked": False}, "token_not_revoked"), ({"environ": {}}, "key_unreadable")):
            code, printed, files, _, calls = self.go(**change)
            self.assertEqual((code, printed, files), (1, want + "\n", []), change)
            # A key read is always revoked, whatever stopped the reads.
            self.assertEqual(calls["revoked"], 1 if change != {"environ": {}} else 0, change)
        for argv, want in (([NAME, "%s#43" % HOME, PASS, "task"], "item_not_the_run_names"),
                           (["not a run-name", ITEM, PASS, "task"], "run_name_unreadable"),
                           ([NAME, ITEM, "p_bad", "task"], "pass_unreadable"),
                           ([NAME.replace(HOME, "a/fork"), "a/fork#42", PASS, "task"], "item_not_home")):
            code, printed, files, _, calls = self.go(argv=argv)
            self.assertEqual((code, printed, files, calls["minted"]), (1, want + "\n", None, []), argv)


class PassFound(unittest.TestCase):
    def test_a_runs_record_is_found(self):
        record = dict(a_record("2026-10-11T12:57:00Z"), **{"pass": "p_0000AAA"})
        other = dict(a_record("2026-10-11T12:54:00Z"), **{"pass": "p_0000BBB"})
        listed = passes_listed([a_pass(30, status="in_progress"), a_pass(20)])
        listed["request"]["call"] = "GET /repos/%s/actions/workflows/poller.yml/runs?branch=main&per_page=%d" % (
            HOME, passes.PAGE)
        replay = github.Replay([listed] + pass_stored(30, pass_zip(other)) + pass_stored(20, pass_zip(record)))
        self.assertEqual(passes.find(replay, HOME, "main", "poller.yml", "p_0000AAA"), record)
        replay = github.Replay([listed] + pass_stored(30, pass_zip(other)) + pass_stored(20, pass_zip(record)))
        self.assertIsNone(passes.find(replay, HOME, "main", "poller.yml", "p_0000CCC"))
        self.assertIsNone(passes.find(github.Replay([]), HOME, "main", "poller.yml", "p_0000AAA"))
        for bad in ("", "p_x", None, "p_0000AAA/../x"):
            sent = Recording(github.Replay([]))
            self.assertIsNone(passes.find(sent, HOME, "main", "poller.yml", bad), bad)
            self.assertEqual(sent.sent, [], bad)
        # A run of another file or branch is passed over, not read.
        elsewhere = passes_listed([a_pass(30, path=".github/workflows/run.yml"), a_pass(20, head_branch="x")])
        elsewhere["request"]["call"] = listed["request"]["call"]
        sent = Recording(github.Replay([elsewhere]))
        self.assertIsNone(passes.find(sent, HOME, "main", "poller.yml", "p_0000AAA"))
        self.assertEqual(len(sent.sent), 1)


class Verify(unittest.TestCase):
    def test_verify_takes_the_results_digest(self):
        result = json.loads((ROOT / "examples" / "result.json").read_text())
        data = (json.dumps(result) + "\n").encode()
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "result"))
            pathlib.Path(d, "result", "result.json").write_bytes(data)
            self.assertEqual(ran(verify.step, ["result", "verdict"], {"RUN_DIGEST": digest}, d)[0], 0)
            said = json.loads(pathlib.Path(d, "verdict", "verdict.json").read_text())
            self.assertEqual((said["checks"], said["digest"], said["run"]), ("not_run", digest, result["run"]))
            for environ, want in (({"RUN_DIGEST": "sha256:" + "0" * 64}, "result_not_the_runs"),
                                  ({}, "digest_unreadable"), ({"RUN_DIGEST": "abc"}, "digest_unreadable")):
                self.assertEqual(ran(verify.step, ["result", "v2"], environ, d), (1, want + "\n"), environ)
            pathlib.Path(d, "result", "result.json").write_bytes(b"{}")
            self.assertEqual(ran(verify.step, ["result", "v3"], {"RUN_DIGEST": "sha256:" + hashlib.sha256(b"{}").hexdigest()},
                                 d), (1, "result_unreadable\n"))


NEEDS = json.dumps({"run": {"result": "success", "outputs": {}}, "verify": {"result": "success", "outputs": {}}})


class Apply(unittest.TestCase):
    def go(self, environ=None, record=RECORD, job=None, mint_refuses=None, revoked=True):
        calls = {"minted": [], "revoked": 0, "job": []}

        def from_key(app, repo, wanted, key, now, connect):
            calls["minted"].append((app["name"], wanted))
            if mint_refuses:
                raise identity.Refused(mint_refuses)

            def revoke():
                calls["revoked"] += 1
                return revoked
            return "the read transport", revoke

        def a_job(admit, result, read_, write, mint, role, config, now):
            calls["job"].append((admit, result, config))
            return job(admit) if job else apply_step._ended(admit["run"], admit["release"], (None, None))
        env = {"RELEASE": RELEASE, "NEEDS": NEEDS, apply_step.KEY: "k", "RUN_DIGEST": "sha256:" + "0" * 64,
               "GITHUB_RUN_ID": "4242"}
        env.update(environ or {})
        # The pr-review App as the Maintainer expands it for the re-read (decision 0054): every read apply names, at read.
        def granted(app, needs, names, kind):
            return {needs[n]["permission"]: "read" for n in names if "permission" in needs.get(n, {})}
        with tempfile.TemporaryDirectory() as d, \
                unittest.mock.patch.object(identity, "from_key", from_key), \
                unittest.mock.patch.object(identity, "granted", granted), \
                unittest.mock.patch.object(passes, "find", lambda *a: copy.deepcopy(record)), \
                unittest.mock.patch.object(apply_step.apply, "job", a_job):
            code, printed = ran(apply_step.step, [NAME, ITEM, PASS, "result", "applied"],
                                {k: v for k, v in env.items() if v is not None}, d)
            folder = pathlib.Path(d, "applied")
            ended = json.loads((folder / "outcome.json").read_text()) if (folder / "outcome.json").is_file() else None
        return code, printed, ended, calls

    def test_apply_waits_for_its_jobs(self):
        for needs, want in ((json.dumps({"run": {"result": "failure"}, "verify": {"result": "skipped"}}), "run_failed"),
                            (json.dumps({"run": {"result": "success"}, "verify": {"result": "failure"}}),
                             "verify_failed"),
                            ("not json", "needs_unreadable"), (None, "needs_unreadable")):
            code, _, ended, calls = self.go({"NEEDS": needs})
            self.assertEqual((code, ended["outcome"], ended["reason"], calls["minted"]), (0, "environment", want, []),
                             needs)

    def test_apply_reads_with_reads(self):
        code, printed, ended, calls = self.go()
        self.assertEqual((code, ended["outcome"]), (0, None), printed)
        (name, wanted), = calls["minted"]
        self.assertEqual((name, set(wanted.values())), ("combsmith-sf-pr-review", {"read"}))
        (admit, result, config), = calls["job"]
        self.assertEqual((admit["run"], admit["content_id"], result), (RUN, CONTENT, None))
        self.assertEqual((config["github_run"], config["app"]["name"]), ("4242", "combsmith-sf-pr-review"))
        # A read token GitHub did not revoke ends the Run the Factory's; a mint refused ends it so too, nothing read.
        self.assertEqual(self.go(revoked=False)[2]["reason"], "token_not_revoked")
        code, _, ended, calls = self.go(mint_refuses="read_not_granted")
        self.assertEqual((ended["outcome"], ended["reason"], calls["job"]), ("environment", "read_not_granted", []))
        # No Decision for this Run: superseded, and the job is never asked.
        code, _, ended, calls = self.go(record=None)
        self.assertEqual((ended["outcome"], ended["reason"], calls["job"], calls["revoked"]),
                         ("superseded", "no_decision", [], 1))

    def test_the_last_step_leaves_the_outcome(self):
        kept = {"schema": "outcome/1", "run": RUN, "release": RELEASE, "outcome": "item", "reason": "uncovered"}
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "applied"))
            pathlib.Path(d, "applied", "outcome.json").write_text(json.dumps(kept))
            self.assertEqual(ran(outcome.step, [NAME, "applied", "o1"], {"RELEASE": RELEASE}, d)[0], 0)
            self.assertEqual(json.loads(pathlib.Path(d, "o1", "outcome.json").read_text()), kept)
            for folder, release in (("nothing", RELEASE), ("applied", "factory/v0.3.2")):
                out = "o-%s-%s" % (folder, release[-1])
                self.assertEqual(ran(outcome.step, [NAME, folder, out], {"RELEASE": release}, d)[0], 0)
                said = json.loads(pathlib.Path(d, out, "outcome.json").read_text())
                self.assertEqual((said["run"], said["outcome"], said["reason"]), (RUN, "environment", "apply_failed"))
            self.assertEqual(ran(outcome.step, ["not a name", "applied", "o3"], {"RELEASE": RELEASE}, d),
                             (1, "run_unreadable\n"))


class Approve(unittest.TestCase):
    def test_the_approver_holds_to_its_item(self):
        seen = []

        def a_job(record, run_, read_, port, config, now):
            seen.append((record, run_, port, config))
            return approve_step.approve._records(run_, config["release"], "applied", "PRR_x", None)
        with tempfile.TemporaryDirectory() as d, \
                unittest.mock.patch.object(passes, "find", lambda transport, *a: (seen.append(transport), RECORD)[1]), \
                unittest.mock.patch.object(approve_step.approve, "job", a_job):
            code, printed = ran(approve_step.step, [NAME, ITEM, PASS, "approved"],
                                {"RELEASE": RELEASE, approve_step.TOKEN: "t", "GITHUB_RUN_ID": "9"}, d,
                                lambda: 0, lambda token: ("live", token))
            self.assertEqual(code, 0, printed)
            done = json.loads(pathlib.Path(d, "approved", "applied.json").read_text())
        found, (record, run_, port, config) = seen
        self.assertIsInstance(found, effects.Approving)
        self.assertEqual((record, run_, config["approver"], config["github_run"]), (RECORD, RUN, "donpetry-bot", "9"))
        self.assertEqual(done["effects"][0]["state"], "applied")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ran(approve_step.step, [NAME, ITEM, PASS, "o"], {}, d), (1, "release_unreadable\n"))


class Diff(unittest.TestCase):
    def test_the_diff_is_the_bytes_github_sent(self):
        pulled = {"number": 42, "head": {"sha": HEAD, "repo": {"full_name": HOME}},
                  "base": {"repo": {"full_name": HOME}, "sha": "b" * 40}}

        class Answer:
            def __init__(self, status, body):
                self.status, self.body, self.sent = status, body, []

            def send(self, req):
                self.sent.append(req)
                return {"status": self.status, "headers": {}, "body": self.body}
        got = Answer(200, DIFF.decode())
        self.assertEqual(read.pull.change(got, pulled, "b" * 40), DIFF)
        self.assertEqual(got.sent[0]["accept"], github.DIFF)
        for status, body in ((200, ""), (200, None), (404, "x")):
            with self.assertRaises(github.Unanswered, msg=(status, body)):
                read.pull.change(Answer(status, body), pulled, "b" * 40)


class Keys(unittest.TestCase):
    def test_a_token_is_minted_from_a_key_alone(self):
        for key in (None, ""):
            with self.assertRaisesRegex(identity.Refused, "^key_unreadable$"):
                identity.from_key({"app_id": 1}, HOME, {"contents": "read"}, key, 0, lambda t: None)
        # Until the Maintainer expands the pr-review App, apply's reads cannot be minted at all (decision 0054).
        apps = json.loads((ROOT / "config" / "apps.json").read_text())
        with self.assertRaises(identity.Refused):
            identity.granted(apps["apps"]["pr-review"], apps["needs"], apply_step.apply.READS, "read")


class ControllerKey(unittest.TestCase):
    def test_the_controller_mints_from_its_key(self):
        config = json.loads((ROOT / "config" / "controller.json").read_text())
        self.assertEqual(effects.controller_token({}, config, 0), (None, None))
        asked = []
        with unittest.mock.patch.object(identity, "from_key",
                                        lambda app, repo, wanted, key, now, connect: asked.append((app["name"], repo,
                                                                                                   wanted, key)) or
                                        ("t", lambda: True)):
            effects.controller_token({"CONTROLLER_APP_KEY": "k"}, config, 0)
        # The status's checks: write, which the App is granted; the tracking issue's write waits on its grant.
        self.assertEqual(asked, [("combsmith-sf-controller", HOME, {"checks": "write"}, "k")])
        # The step fails when GitHub did not revoke the token, and only then.
        out = tc.passed(tc.reads(pulls=[]))
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "pass.json").write_text(json.dumps(out["record"]))
            pathlib.Path(d, "writes.json").write_text(json.dumps(writes_.plan(out)))

            class Quiet:
                def send(self, req):
                    return {"status": 404, "headers": {}, "body": None}
            for revoked, code in ((True, 0), (False, 1)):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(effects.main(["pass.json", "writes.json", "."], {}, d,
                                                  mint=lambda e, c: (Quiet(), lambda: revoked)), code, revoked)


class Reread(unittest.TestCase):
    def test_the_item_is_read_again(self):
        listed = tc.listed([tc.run(status="in_progress")])
        facts = support.facts()
        whole = []

        def snapshot(transport, repo, number, identities, who, runs_whole, clock, with_head=False):
            whole.append(runs_whole)
            return facts, "t", HEAD
        from controller import configuration
        config = configuration.load(ROOT, RELEASE, "pr-review")
        for short in (dict(listed, complete=False), {"runs": "x"}):
            with unittest.mock.patch.object(reread.records, "runs", lambda *a, **k: copy.deepcopy(short)), \
                    unittest.mock.patch.object(reread.facts_, "snapshot", snapshot), \
                    unittest.mock.patch.object(reread.pause_, "read", lambda *a: {"org": None, "repos": {HOME: None}}):
                if short.get("runs") == "x":
                    with self.assertRaises(github.Unanswered):
                        reread.item("t", config, 42, support.NOW, lambda: support.NOW)
                else:
                    self.assertIsNone(reread.item("t", config, 42, support.NOW, lambda: support.NOW)[3]["active_runs"])
        self.assertEqual(whole, [False, False])
        with unittest.mock.patch.object(reread.records, "runs", lambda *a, **k: copy.deepcopy(listed)), \
                unittest.mock.patch.object(reread.facts_, "snapshot", lambda *a, **k: (facts, "t", HEAD)), \
                unittest.mock.patch.object(reread.pause_, "read",
                                           lambda transport, org, repos: {"org": None, "repos": {HOME: None}}):
            got = reread.item("t", config, 42, support.NOW, lambda: support.NOW)
        self.assertEqual(got[:3], (facts, HEAD, listed["runs"]))
        self.assertEqual((got[3]["paused"], got[3]["active_runs"], got[3]["passes_since"]), (False, 1, None))


if __name__ == "__main__":
    unittest.main()
