"""The steps a Run's jobs run (issue 196, PR 2b-1): the reader's step that reads what the Task is built from, `run`'s
form that takes its folder, `verify`, `apply`'s step and the outcome it always leaves, the approving act's step, and the
Controller's token minted from its key in the effects step. Each step is driven with its ports stood in for, as the
workflow will call it; nothing here reaches the network, and each test reads and writes in a scratch folder alone."""
from __future__ import annotations

import base64
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
from harness import apply_step, approve_step, outcome, read, reread, run, shared, steps, verify
from tests import support
from tests import test_controller as tc
from tests.test_adapters import Recording, a_pass, a_record, pass_stored, pass_zip, passes_listed

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOME = "combsmith/software-factory"
DIFF = b"diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"
CONTENT = "sha256:" + hashlib.sha256(DIFF).hexdigest()
HEAD = "9f1c2d3e4b5a69788796a5b4c3d2e1f0a9b8c7d6"
RELEASE = "factory/v0.3.1"
CHECKED_OUT = "c" * 40
# The job's own commit carries the pass record's Release, and `next` points at it.
TAGS = {RELEASE: CHECKED_OUT, "factory/v0.3.0": "e" * 40, "factory/v0-next": CHECKED_OUT}


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
            for taken in ("out", "/tmp"):
                with self.assertRaises(steps.Stop, msg=taken):
                    steps.new_folder(d, taken)
            # A path that climbs out is refused before anything is made, wherever it would land.
            for out in ("../elsewhere", "inner/../../elsewhere", "/etc/passwd"):
                with self.assertRaisesRegex(steps.Stop, "^path_outside$", msg=out):
                    steps.inside(d, out)
            os.symlink(os.path.join(d, "nowhere"), os.path.join(d, "link"))
            with self.assertRaises(steps.Stop):
                steps.new_folder(d, "link")
        self.assertEqual(ran(lambda: "fine"), (0, "fine\n"))
        self.assertEqual(ran(lambda: (_ for _ in ()).throw(steps.Stop("a_code"))), (1, "a_code\n"))
        self.assertEqual(ran(lambda: (_ for _ in ()).throw(ValueError("GitHub said something"))), (1, "step_failed\n"))


class Reader(unittest.TestCase):
    """The reader's step, its ports stood in for: what it reads, what it holds them to, and its token."""

    def go(self, record=RECORD, head=HEAD, first=HEAD, change=DIFF, revoked=True, argv=None, environ=None, refs=TAGS):
        calls = {"minted": [], "revoked": 0, "tags": []}

        def tags_read(transport, repo):
            calls["tags"].append((transport, repo))
            return copy.deepcopy(refs)

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
                unittest.mock.patch.object(read.tags, "read", tags_read), \
                unittest.mock.patch.object(read.facts_, "snapshot", lambda *a, **k: (facts, "title", head)), \
                unittest.mock.patch.object(read.pull, "read", lambda *a: pulled), \
                unittest.mock.patch.object(read.pull, "base", lambda *a: {"head": "b" * 40}), \
                unittest.mock.patch.object(read.pull, "change", lambda *a: change):
            code, printed = ran(read.step, argv or [NAME, ITEM, PASS, "task"],
                                environ if environ is not None else {read.KEY: "the key", read.COMMIT: CHECKED_OUT}, d)
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

    def test_a_run_on_another_release_than_its_pass_builds_no_task(self):
        # `next` moved between the pass and the Run: the commit the job checked out is another Release's. The Run
        # builds no Task, and leaves its outcome under its own Release (#197's ruling 8).
        moved = {"factory/v0.3.2": CHECKED_OUT, RELEASE: "e" * 40, "factory/v0-next": CHECKED_OUT}
        code, printed, files, kept, calls = self.go(refs=moved)
        self.assertEqual((code, printed, files), (1, "release_moved\n", ["outcome.json"]))
        self.assertEqual(json.loads(kept["outcome.json"]), {"schema": "outcome/1", "run": RUN, "release": "factory/v0.3.2",
                                                            "outcome": "superseded", "reason": "release_moved"})
        self.assertEqual(shared.errors(json.loads(kept["outcome.json"]), "outcome"), [])
        # The tags are read with the reader's own token, of the home repo, and the token is revoked.
        self.assertEqual((calls["tags"], calls["revoked"]), ([("the reader's transport", HOME)], 1))
        # A Run id the record does not hold leaves no outcome for it, whatever Release the job is on.
        stranger = NAME.rsplit(" ", 1)[0] + " r_000009Z"
        code, printed, files, _, _ = self.go(refs=moved, argv=[stranger, ITEM, PASS, "task"])
        self.assertEqual((code, printed, files), (1, "not_the_decision\n", []))
        # End to end: `run` failed by that code, so `apply` read nothing and said `run_failed`; the last step keeps
        # the reader's outcome, so the Run ends `superseded`, never the environment's fault.
        with tempfile.TemporaryDirectory() as d:
            for folder, said in (("task", kept["outcome.json"]), ("applied", json.dumps(
                    {"schema": "outcome/1", "run": RUN, "release": "factory/v0.3.2", "outcome": "environment",
                     "reason": "run_failed"}).encode())):
                os.mkdir(os.path.join(d, folder))
                pathlib.Path(d, folder, "outcome.json").write_bytes(said)
            env = {"RELEASE": "factory/v0.3.2"}
            self.assertEqual(ran(outcome.step, [NAME, "applied", "o", "task"], env, d), (1, "release_moved\n"))
            self.assertEqual(json.loads(pathlib.Path(d, "o", "outcome.json").read_bytes()), json.loads(kept["outcome.json"]))
            # Without the reader's folder, or under another Release than the reader's, `apply`'s word stands.
            self.assertEqual(ran(outcome.step, [NAME, "applied", "o2"], env, d), (1, "run_failed\n"))
            moved_elsewhere = dict(json.loads(kept["outcome.json"]), release="factory/v0.3.3")
            for n, other in enumerate((moved_elsewhere, dict(moved_elsewhere, release="factory/v0.3.2", run="r_000009Z"),
                                       dict(moved_elsewhere, release="factory/v0.3.2", reason="head_moved"),
                                       dict(moved_elsewhere, release="factory/v0.3.2", outcome="item"))):
                with self.subTest(other=other):
                    folder = "task%d" % n
                    os.mkdir(os.path.join(d, folder))
                    pathlib.Path(d, folder, "outcome.json").write_text(json.dumps(other))
                    self.assertEqual(ran(outcome.step, [NAME, "applied", "o%d" % (n + 3), folder], env, d),
                                     (1, "run_failed\n"))

    def test_a_run_whose_own_release_cannot_be_named_builds_no_task(self):
        # Never the pass record's Release in its place: with none named, nothing is written but the code.
        for change in ({"refs": None}, {"refs": {"factory/v0-next": CHECKED_OUT}},
                       {"refs": dict(TAGS, **{"factory/v0.3.2": CHECKED_OUT})},
                       {"environ": {read.KEY: "the key"}}, {"environ": {read.KEY: "the key", read.COMMIT: "HEAD"}},
                       {"environ": {read.KEY: "the key", read.COMMIT: CHECKED_OUT.upper()}}):
            with self.subTest(change=change):
                code, printed, files, _, calls = self.go(**change)
                self.assertEqual((code, printed, files, calls["revoked"]), (1, "release_unresolved\n", [], 1))

    def test_the_reader_fails_closed(self):
        def varied(change):
            record = copy.deepcopy(RECORD)
            for e in record["pull_requests"]:
                if e["run"] == RUN:
                    change(e["decision"])
            return record
        other = varied(lambda d: d["admit"].update(intent="fix-findings"))
        elsewhere = varied(lambda d: d["item"].update(number=43))
        moved = varied(lambda d: d["admit"].update(content_id="sha256:" + "0" * 64))
        for change, want in (({"record": None}, "record_not_found"), ({"record": other}, "not_the_decision"),
                             ({"record": elsewhere}, "not_the_decision"), ({"record": moved}, "not_the_decision"),
                             ({"record": {"pass": PASS}}, "record_unreadable"),
                             ({"record": None, "revoked": False}, "token_not_revoked"),
                             ({"first": "a" * 40}, "head_moved"), ({"change": DIFF + b"+c\n"}, "content_moved"),
                             ({"revoked": False}, "token_not_revoked"), ({"environ": {}}, "key_unreadable")):
            code, printed, files, _, calls = self.go(**change)
            self.assertEqual((code, printed, files), (1, want + "\n", []), change)
            # A key read is always revoked, whatever stopped the reads.
            self.assertEqual(calls["revoked"], 0 if change == {"environ": {}} else 1, change)
        # The reader's token is its App's reads alone, whatever else the App were granted.
        apps = json.loads((ROOT / "config" / "apps.json").read_text())
        app = copy.deepcopy(apps["apps"]["reader"])
        app["permissions"]["pull_requests"] = dict(app["permissions"]["pull_requests"], level="write",
                                                   needs=app["permissions"]["pull_requests"]["needs"] + ["effect:comment"])
        self.assertEqual(set(read.wanted({"app": app, "needs": apps["needs"]}).values()), {"read"})
        issue_name = "sf %s#7 investigate-issue dev-lead sha256:aaaa r_000002A" % HOME
        for argv, want in (([NAME, "%s#43" % HOME, PASS, "task"], "item_not_the_run_names"),
                           ([issue_name, "%s#7" % HOME, PASS, "task"], "issue_not_built"),
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
        # A record over 64 KiB zipped is found, under the pass record's own bound (decision 0060).
        big = dict(record, filler=base64.b64encode(os.urandom(90 * 1024)).decode())
        zipped = pass_zip(big)
        self.assertGreater(len(zipped), github.STORED)
        found = github.Replay([dict(listed, response=dict(listed["response"], body={"total_count": 1,
                                                                                   "workflow_runs": [a_pass(20)]}))]
                              + pass_stored(20, zipped))
        self.assertEqual(passes.find(found, HOME, "main", "poller.yml", "p_0000AAA"), big)
        # What cannot be read raises, the environment's, never a Run with no Decision: the list, or a pass's artifact.
        with self.assertRaises(github.Unanswered):
            passes.find(github.Replay([]), HOME, "main", "poller.yml", "p_0000AAA")
        alone = copy.deepcopy(listed)
        alone["response"]["body"] = {"total_count": 1, "workflow_runs": [a_pass(30)]}
        for broken in (pass_stored(30, pass_zip(other), size_in_bytes=1), pass_stored(30, pass_zip(b"not json"))):
            with self.assertRaises(github.Unanswered):
                passes.find(github.Replay([alone] + broken), HOME, "main", "poller.yml", "p_0000AAA")
        for answer in ({"status": 502, "headers": {}, "body": None}, {"status": 200, "headers": {}, "body": {}}):
            with self.assertRaises(github.Unanswered, msg=answer):
                passes.find(github.Replay([dict(listed, response=answer)]), HOME, "main", "poller.yml", "p_0000AAA")
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
    def go(self, environ=None, record=RECORD, job=None, mint_refuses=None, revoked=True, result=None, a_job=None):
        calls = {"minted": [], "revoked": 0, "job": [], "granted": []}

        def from_key(app, repo, wanted, key, now, connect):
            calls["minted"].append((app["name"], wanted))
            if mint_refuses:
                raise identity.Refused(mint_refuses)

            def revoke():
                calls["revoked"] += 1
                return revoked
            return "the read transport", revoke

        def recorded(admit, result, read_, write, mint, role, config, now):
            calls["job"].append((admit, result, config))
            if a_job:
                return a_job(admit, result, read_, write, mint, role, config, now)
            return job(admit) if job else apply_step._ended(admit["run"], admit["release"], (None, None))
        def find(*a):
            if record is github.Unanswered:
                raise github.Unanswered("no answer")
            return copy.deepcopy(record)
        env = {"RELEASE": RELEASE, "NEEDS": NEEDS, apply_step.KEY: "k", "RUN_DIGEST": "sha256:" + "0" * 64,
               "GITHUB_RUN_ID": "4242"}
        env.update(environ or {})
        # The pr-review App as the Maintainer expands it for the re-read (decision 0054): every read apply names, at read.
        def granted(app, needs, names, kind):
            calls["granted"].append((tuple(names), kind))
            return {needs[n]["permission"]: "read" for n in names if "permission" in needs.get(n, {})}
        with tempfile.TemporaryDirectory() as d, \
                unittest.mock.patch.object(identity, "from_key", from_key), \
                unittest.mock.patch.object(identity, "granted", granted), \
                unittest.mock.patch.object(passes, "find", find), \
                unittest.mock.patch.object(apply_step.apply, "job", recorded):
            if result is not None:
                os.mkdir(os.path.join(d, "result"))
                pathlib.Path(d, "result", "result.json").write_bytes(result)
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
        # Its token is asked for apply's reads, as reads, and nothing else.
        self.assertEqual(calls["granted"], [(apply_step.apply.READS, "read")])
        (admit, result, config), = calls["job"]
        self.assertEqual((admit["run"], admit["content_id"], result), (RUN, CONTENT, None))
        self.assertEqual((config["github_run"], config["app"]["name"]), ("4242", "combsmith-sf-pr-review"))
        # A read token GitHub did not revoke ends the Run the Factory's; a mint refused ends it so too, nothing read.
        self.assertEqual(self.go(revoked=False)[2]["reason"], "token_not_revoked")
        code, _, ended, calls = self.go(mint_refuses="read_not_granted")
        self.assertEqual((ended["outcome"], ended["reason"], calls["job"]), ("environment", "read_not_granted", []))
        # The Result is the one `run` reported, by its digest, and none of other bytes.
        data = (json.dumps(json.loads((ROOT / "examples" / "result.json").read_text())) + "\n").encode()
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        _, _, _, calls = self.go({"RUN_DIGEST": digest}, result=data)
        self.assertEqual(calls["job"][0][1], json.loads(data))
        _, _, _, calls = self.go(result=data)
        self.assertIsNone(calls["job"][0][1])
        # A pull request that changed while it was read again is a change under the Run; one that cannot be read, not.
        for raised, want in ((reread.facts_.Moved("moved"), ("superseded", "head_moved")),
                             (github.Unanswered("no answer"), ("environment", "facts_unreadable"))):
            def reading(*a, raised=raised):
                raise raised
            with unittest.mock.patch.object(reread, "item", reading):
                code, _, ended, _ = self.go(a_job=lambda admit, result, read_, *a: read_())
            self.assertEqual((ended["outcome"], ended["reason"]), want, raised)
        # A record that cannot be read is the environment's; a Decision of another item, no Decision of this Run's.
        code, _, ended, calls = self.go(record=github.Unanswered)
        self.assertEqual((ended["outcome"], ended["reason"], calls["job"]), ("environment", "record_unreadable", []))
        elsewhere = copy.deepcopy(RECORD)
        for e in elsewhere["pull_requests"]:
            if e["run"] == RUN:
                e["decision"]["item"]["number"] = 43
        code, _, ended, calls = self.go(record=elsewhere)
        self.assertEqual((ended["outcome"], ended["reason"], calls["job"]), ("superseded", "no_decision", []))
        # A Run of another Release than the pass that admitted it writes nothing.
        code, _, ended, calls = self.go({"RELEASE": "factory/v0.3.2"})
        self.assertEqual((ended["outcome"], ended["reason"], calls["job"]), ("environment", "release_differs", []))
        self.assertEqual(self.go({"RELEASE": "v1"})[:3], (1, "release_unreadable\n", None))
        # No Decision for this Run: superseded, and the job is never asked.
        code, _, ended, calls = self.go(record=None)
        self.assertEqual((ended["outcome"], ended["reason"], calls["job"], calls["revoked"]),
                         ("superseded", "no_decision", [], 1))

    def test_apply_writes_through_its_roles_allowlist_on_the_item_read_again(self):
        # The job's callbacks, as `apply` calls them: the item read again through the read token; a write token minted
        # from the key with what the Effects need; and each write held to the Role's allowlist on the admitted item.
        seen = {"reread": [], "role_write": []}
        facts = dict(support.facts(), threads=[support.thread("T1")])

        def a_job(admit, result, read_, write, mint, role, config, now):
            read_()
            transport, revoke = mint({"pull_requests": "write"})
            write(transport, "comment", {"on": "item"})
            revoke()
            return apply_step._ended(admit["run"], admit["release"], (None, None))

        def item(transport, config, number, now, clock):
            seen["reread"].append((transport, number))
            return facts, HEAD, [], support.context()

        def role_write(transport, item_, kind, req, login):
            seen["role_write"].append((transport, item_, kind, login))
            return {"state": "applied", "key": "IC_x"}
        with unittest.mock.patch.object(reread, "item", item), \
                unittest.mock.patch.object(effects, "role_write", role_write):
            code, printed, ended, calls = self.go(job=None, a_job=a_job)
        self.assertEqual((code, ended["outcome"]), (0, None), printed)
        self.assertEqual(seen["reread"], [("the read transport", 42)])
        self.assertEqual([wanted for _, wanted in calls["minted"]][1], {"pull_requests": "write"})
        (transport, item_, kind, login), = seen["role_write"]
        self.assertIsInstance(transport, effects.Allowed)
        self.assertEqual((item_, kind, login), (dict(support.ITEM), "comment", "combsmith-sf-pr-review[bot]"))
        # Held: the allowlist refuses a write on another item.
        with self.assertRaises(github.Unanswered):
            transport.send(github.request("POST", "/repos/%s/issues/43/comments" % HOME, body={"body": "x"}))

    def test_the_last_step_leaves_the_outcome(self):
        kept = {"schema": "outcome/1", "run": RUN, "release": RELEASE, "outcome": "item", "reason": "uncovered"}
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "applied"))
            pathlib.Path(d, "applied", "outcome.json").write_text(json.dumps(kept))
            # A Run that did not succeed concludes so, by its code, once its outcome is written.
            self.assertEqual(ran(outcome.step, [NAME, "applied", "o1"], {"RELEASE": RELEASE}, d), (1, "uncovered\n"))
            self.assertEqual(json.loads(pathlib.Path(d, "o1", "outcome.json").read_text()), kept)
            os.mkdir(os.path.join(d, "fine"))
            pathlib.Path(d, "fine", "outcome.json").write_text(json.dumps(dict(kept, outcome=None, reason=None)))
            self.assertEqual(ran(outcome.step, [NAME, "fine", "o0"], {"RELEASE": RELEASE}, d), (0, "outcome none\n"))
            for folder, release in (("nothing", RELEASE), ("applied", "factory/v0.3.2")):
                out = "o-%s-%s" % (folder, release[-1])
                self.assertEqual(ran(outcome.step, [NAME, folder, out], {"RELEASE": release}, d), (1, "apply_failed\n"))
                said = json.loads(pathlib.Path(d, out, "outcome.json").read_text())
                self.assertEqual((said["run"], said["outcome"], said["reason"]), (RUN, "environment", "apply_failed"))
            self.assertEqual(ran(outcome.step, ["not a name", "applied", "o3"], {"RELEASE": RELEASE}, d),
                             (1, "run_unreadable\n"))


class Approve(unittest.TestCase):
    def test_the_approver_holds_to_its_item(self):
        seen = []

        reread_through = []

        def a_job(record, run_, read_, port, config, now):
            seen.append((record, run_, port, config))
            read_()
            return approve_step.approve._records(run_, config["release"], "applied", "PRR_x", None)

        def item(transport, *a):
            reread_through.append(transport)
            return None
        with tempfile.TemporaryDirectory() as d, \
                unittest.mock.patch.object(passes, "find", lambda transport, *a: (seen.append(transport), RECORD)[1]), \
                unittest.mock.patch.object(approve_step.approve, "job", a_job), \
                unittest.mock.patch.object(reread, "item", item):
            code, printed = ran(approve_step.step, [NAME, ITEM, PASS, "approved"],
                                {"RELEASE": RELEASE, approve_step.TOKEN: "t", "GITHUB_RUN_ID": "9"}, d,
                                lambda: 0, lambda token: ("live", token))
            self.assertEqual(code, 0, printed)
            done = json.loads(pathlib.Path(d, "approved", "applied.json").read_text())
        found, (record, run_, port, config) = seen
        self.assertIsInstance(found, effects.Approving)
        # The item is read again through the approver's token held to its item, too.
        self.assertEqual([type(t) for t in reread_through], [effects.Approving])
        self.assertEqual((record, run_, config["approver"], config["github_run"]), (RECORD, RUN, "donpetry-bot", "9"))
        self.assertEqual(done["effects"][0]["state"], "applied")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ran(approve_step.step, [NAME, ITEM, PASS, "o"], {}, d), (1, "release_unreadable\n"))
        # A record that cannot be read, or a Decision not the run-name's: nothing asked, and the step fails by its code.
        elsewhere = copy.deepcopy(RECORD)
        for e in elsewhere["pull_requests"]:
            if e["run"] == RUN:
                e["decision"]["item"]["number"] = 43

        def unread(*a):
            raise github.Unanswered("no answer")
        for found, want in ((unread, "record_unreadable"), (lambda *a: elsewhere, "not_the_decision"),
                            (lambda *a: dict(RECORD, release="factory/v0.3.2"), "release_differs")):
            asked = []
            with tempfile.TemporaryDirectory() as d, \
                    unittest.mock.patch.object(passes, "find", found), \
                    unittest.mock.patch.object(approve_step.approve, "job", lambda *a: asked.append(a)):
                code, printed = ran(approve_step.step, [NAME, ITEM, PASS, "o"],
                                    {"RELEASE": RELEASE, approve_step.TOKEN: "t"}, d, lambda: 0, lambda token: "live")
                ended = json.loads(pathlib.Path(d, "o", "outcome.json").read_text())
            self.assertEqual((code, printed, ended["reason"], asked), (1, want + "\n", want, []), want)


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
        # The Pause is read again, on the org and the item's repo, and a Pause or one unreadable is the context's.
        asked = []

        def runs(transport, repo, branch, workflows, dispatcher, **k):
            asked.append(workflows)
            return copy.deepcopy(listed)
        for paused, want in (({"org": "true", "repos": {HOME: None}}, True), ({"org": None, "repos": {HOME: "true"}}, True),
                             ({"org": None, "repos": {HOME: "maybe"}}, None)):
            with unittest.mock.patch.object(reread.records, "runs", runs), \
                    unittest.mock.patch.object(reread.facts_, "snapshot", lambda *a, **k: (facts, "t", HEAD)), \
                    unittest.mock.patch.object(reread.pause_, "read", lambda transport, org, repos: (
                        asked.append((org, list(repos))), paused)[1]):
                self.assertIs(reread.item("t", config, 42, support.NOW, lambda: support.NOW)[3]["paused"], want, paused)
        self.assertEqual(asked[:2], [["run.yml", "approve.yml"], ("combsmith", [HOME])])


if __name__ == "__main__":
    unittest.main()
