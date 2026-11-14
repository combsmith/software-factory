"""The steps a Run's jobs run (issue 196, PR 2b-1): the reader's step that reads what the Task is built from, `run`'s
form that takes its folder, `verify`, `apply`'s step and the outcome it always leaves, the approving act's step, and the
Controller's token minted from its key in the effects step. Each step is driven with its ports stood in for, as the
workflow will call it; nothing here reaches the network, and each test reads and writes in a scratch folder alone."""
from __future__ import annotations

import base64
import contextlib
import copy
import datetime
import hashlib
import io
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
import unittest.mock

from adapters import effects, github, identity, passes, records
from controller import writes as writes_
from harness import apply_step, approve_step, outcome, read, reread, run, shared, steps, verify
from tests import support
from tests import test_approve as ta
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
    """The step's exit and what it printed, its Release the one its environment names as `RELEASE`."""
    printed = io.StringIO()
    environ = given[1] if len(given) > 1 and isinstance(given[1], dict) else {}
    with contextlib.redirect_stdout(printed), support.releasing(environ):
        code = steps.run(step, *given)
    return code, printed.getvalue()


ISSUE_TEXT = {"id": "issue:7", "by": {"kind": "human", "name": "don-petry", "can_write": True}, "body": "What it asks."}
LENS = {"kind": "lens", "name": "pr-review", "can_write": False}

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


class ReleaseName(unittest.TestCase):
    """The Release a step runs as, read from its own checkout's tags (the ruling on issue 196's Release name)."""

    def repo(self, d, *tags):
        env = dict(steps.GIT_ENV, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@t", HOME=d)
        for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "x"]) + tuple(["tag", t] for t in tags):
            subprocess.run(["git"] + args, cwd=d, env=env, check=True, capture_output=True)

    def test_the_release_is_its_one_tag(self):
        for tags, want in ((("factory/v0.3.1",), "factory/v0.3.1"),
                           (("factory/v0.3.1", "factory/v0-next"), "factory/v0.3.1"),
                           (("factory/v0.3.1", "a-tag", "v0.3.1"), "factory/v0.3.1")):
            with tempfile.TemporaryDirectory() as d:
                self.repo(d, *tags)
                self.assertEqual(steps.release(d), want, tags)
                self.assertRegex(steps.commit(d), r"^[0-9a-f]{40}$")
        # None, the Channel's alone, or a name a Release's tag is not, is no Release; two refuse rather than pick.
        for tags, want in (((), "release_untagged"), (("factory/v0-next",), "release_untagged"),
                           (("factory/v0.3.01", "factory/v1.2"), "release_untagged"),
                           (("factory/v0.3.1", "factory/v0.3.2"), "release_twice")):
            with tempfile.TemporaryDirectory() as d:
                self.repo(d, *tags)
                with self.assertRaisesRegex(steps.Stop, "^%s$" % want, msg=tags):
                    steps.release(d)
        with tempfile.TemporaryDirectory() as d:
            for read in (steps.release, steps.commit):
                with self.assertRaisesRegex(steps.Stop, "^release_unreadable$"):
                    read(d)     # no repository at all
        # It asks git for the tags on HEAD, in an environment of its own.
        seen = []

        def run(args, **kw):
            seen.append((args, kw["env"]))
            return subprocess.CompletedProcess(args, 0, "factory/v1.0.0\n", "")
        self.assertEqual(steps.release("/x", run), "factory/v1.0.0")
        for said in ("not a sha\n", "abc\n", ""):
            with self.assertRaisesRegex(steps.Stop, "^release_unreadable$", msg=said):
                steps.commit("/x", lambda args, **kw: subprocess.CompletedProcess(args, 0, said, ""))
        self.assertEqual(seen, [(["git", "tag", "--points-at", "HEAD"], steps.GIT_ENV)])

    def test_the_first_job_hands_on_the_commit_it_checked_out(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "github_output")
            with unittest.mock.patch.object(steps, "commit", lambda: "a" * 40):
                self.assertEqual(steps.handed_on({"GITHUB_OUTPUT": out}), "commit " + "a" * 40)
            self.assertEqual(pathlib.Path(out).read_text(), "commit=%s\n" % ("a" * 40))

    def test_a_step_with_no_release_reads_no_key(self):
        # apply and the act refuse before a key or a token is read, so no credential is held under no Release.
        _, printed, _, calls = Apply().go({"RELEASE": "factory/v0-next"})
        self.assertEqual((printed, calls["minted"]), ("release_untagged\n", []))
        used = []
        with tempfile.TemporaryDirectory() as d:
            code, printed = ran(approve_step.step, [NAME, ITEM, PASS, "o"], {approve_step.TOKEN: "t"}, d,
                                lambda: 0, lambda token: used.append(token))
        self.assertEqual((code, printed, used), (1, "release_untagged\n", []))


class WorkflowForm(unittest.TestCase):
    def test_each_step_takes_the_runs_inputs_from_its_environment_and_its_folders_by_name(self):
        # A workflow's run: line is `python3 -m <module>` alone, so a step with no argument reads the Run's three inputs
        # from its environment, and its folders by their fixed names.
        env = {"NAME": NAME, "ITEM": ITEM, "PASS": PASS}
        self.assertEqual(steps.given([], env, steps.INPUTS, ("task",)), [NAME, ITEM, PASS, "task"])
        self.assertEqual(steps.given(["a", "b"], env, steps.INPUTS, ("task",)), ["a", "b"])
        self.assertEqual(steps.given([], {}, ("NAME",), ("applied", "outcome")), [None, "applied", "outcome"])
        seen = []
        for module, folders in ((read, ["task"]), (verify, ["result", "verdict"]), (apply_step, ["result", "applied"]),
                                (outcome, ["applied", "outcome", "reader-outcome"]), (approve_step, ["applied"])):
            with tempfile.TemporaryDirectory() as d:
                with unittest.mock.patch.object(steps, "given", lambda a, e, i, f: seen.append((module, list(f))) or
                                                (_ for _ in ()).throw(steps.Stop("seen"))):
                    ran(module.step, [], env, d)
        self.assertEqual(seen, [(m, f) for m, f in ((read, ["task"]), (verify, ["result", "verdict"]),
                                                    (apply_step, ["result", "applied"]),
                                                    (outcome, ["applied", "outcome", "reader-outcome"]),
                                                    (approve_step, ["applied"]))])

    def test_run_hands_on_the_digest_alone_as_its_steps_output(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "github_output")
            with unittest.mock.patch.object(run, "job", lambda paths, env, config: "sha256:" + "a" * 64), \
                    unittest.mock.patch.object(run, "from_folder", lambda folder, result: [folder, result]), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run.main([], {"GITHUB_OUTPUT": out}), 0)
            self.assertEqual(pathlib.Path(out).read_text(), "digest=sha256:%s\n" % ("a" * 64))



def recorded_spy(module, calls: list):
    """`module.applied.recorded`, patched to keep what each caller asks it, the Lenses' names and the authority table
    among it, and to answer as it does (issue 338)."""
    real = module.applied.recorded

    def spy(transport, repo, runs, numbers, lenses, authority):
        calls.append({"repo": repo, "numbers": list(numbers), "lenses": set(lenses), "authority": authority})
        return real(transport, repo, runs, numbers, lenses, authority)
    return unittest.mock.patch.object(module.applied, "recorded", spy)


AUTHORITY = json.loads((ROOT / "config" / "authority.json").read_text())


README_BLOB = hashlib.sha1(b"blob 9\0# a repo\n").hexdigest()   # the git blob of the one file support.tarball holds


class Reader(unittest.TestCase):
    """The reader's step, its ports stood in for: what it reads, what it holds them to, and its token."""

    def go(self, record=RECORD, head=HEAD, first=HEAD, change=DIFF, revoked=True, argv=None, environ=None, complete=True,
           refs=TAGS, commit=CHECKED_OUT, tarred=None, tree=None, raising=None, threads=(), said=None):
        """`commit` is what `steps.commit()` gives, or a function that stands in for it; `tarred` what the head's
        tarball read gives for a commit, or raises; `tree` what the read of the commit's tree gives, or raises: by default
        the tree of the one file `support.tarball` holds. `raising`, where given, is `(module, name, error)`: that read
        raises `error` in place of its stand-in."""
        calls = {"minted": [], "revoked": 0, "tags": [], "tarballs": [], "trees": []}

        def fetched(transport, repo, sha):
            calls["tarballs"].append((transport, repo, sha))
            return support.tarball(sha) if tarred is None else tarred(sha)

        def tree_read(transport, repo, sha):
            calls["trees"].append((transport, repo, sha))
            return {"files": {"README.md": (README_BLOB, 9)}, "links": set()} if tree is None else tree(sha)

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
        facts = support.facts(item=dict(support.ITEM, number=42), content_id=CONTENT, threads=list(threads))
        pulled = {"head": {"sha": first}, "number": 42}
        listed = {"runs": [], "unidentified": [], "complete": complete, "reads": [], "github_ids": {}}
        calls["recorded"], calls["listed"], calls["asked"], calls["opener"] = [], [], [], []
        calls["opened"], calls["opened_role"] = [], []
        made = {"named": {26: [("r_01JA7Q", 36)]}, "unreadable": set(), "whole": True}

        def snapshot(*a, **k):
            calls["recorded"].append(k["recorded"])
            calls["opener"].append(k.get("opener", "not told"))
            calls["opened"].append(k["opened"] is made)
            return facts, "title", head

        def read_issues(transport, pull_read, who, opener, opened):
            calls["issues"] = (pull_read is pulled, opener, opened is made)
            return [ISSUE_TEXT]

        def read_findings(transport, pull_read, who, lens, asked):
            calls.setdefault("findings", []).append((transport, pull_read is pulled, lens, list(asked)))
            return [{"id": "thread:%s" % ident, "by": dict(LENS), "body": "What it said on %s." % ident}
                    for ident in asked] if said is None else said

        def read_opened(transport, repo, runs, role):
            calls["opened_role"].append(role)
            return made
        with tempfile.TemporaryDirectory() as d, \
                unittest.mock.patch.object(identity, "from_key", from_key), \
                unittest.mock.patch.object(passes, "find", lambda *a: copy.deepcopy(record)), \
                unittest.mock.patch.object(read.steps, "commit", commit if callable(commit) else lambda: commit), \
                unittest.mock.patch.object(read.tags, "read", tags_read), \
                unittest.mock.patch.object(read.records, "runs",
                                           lambda *a, **k: calls["listed"].append((a[3], k)) or copy.deepcopy(listed)), \
                recorded_spy(read, calls["asked"]), \
                unittest.mock.patch.object(read.facts_, "snapshot", snapshot), \
                unittest.mock.patch.object(read.facts_, "opener_of", lambda *told: (12, "Bot")), \
                unittest.mock.patch.object(read.applied, "opened", read_opened), \
                unittest.mock.patch.object(read.facts_, "opener_role", lambda kernel: "dev-lead"), \
                unittest.mock.patch.object(read.pull, "read", lambda *a: pulled), \
                unittest.mock.patch.object(read.pull, "base", lambda *a: {"head": "b" * 40}), \
                unittest.mock.patch.object(read.pull, "change", lambda *a: change), \
                unittest.mock.patch.object(read.texts, "issues", read_issues), \
                unittest.mock.patch.object(read.texts, "findings", read_findings), \
                unittest.mock.patch.object(read.head_, "fetch", fetched), \
                unittest.mock.patch.object(read.head_, "tree", tree_read), \
                contextlib.ExitStack() as more:
            if raising is not None:
                module, name, error = raising

                def raised(*a, **k):
                    raise error
                more.enter_context(unittest.mock.patch.object(module, name, raised))
            code, printed = ran(read.step, argv or [NAME, ITEM, PASS, "task"],
                                environ if environ is not None else {read.KEY: "the key"}, d)
            folder = pathlib.Path(d, "task")
            files = sorted(p.name for p in folder.iterdir()) if folder.is_dir() else None
            kept = {n: (folder / n).read_bytes() for n in files or () if n != "head"}
            calls["head"] = sorted(p.name for p in (folder / "head").iterdir()) if (folder / "head").is_dir() else None
        return code, printed, files, kept, calls

    def test_the_reader_writes_the_tasks_inputs(self):
        code, printed, files, kept, calls = self.go()
        self.assertEqual((code, files), (0, sorted(read.FILES + ("head",))), printed)
        # The head's tarball is read of the home repo, at the head the diff was read at, with the reader's token, and
        # unpacked into `head/` (decision 0138); and the commit's tree, which the head is held to, the same way (decision 0142).
        self.assertEqual((calls["tarballs"], calls["head"]), ([("the reader's transport", HOME, HEAD)], ["README.md"]))
        self.assertEqual(calls["trees"], [("the reader's transport", HOME, HEAD)])
        self.assertEqual(kept["diff"], DIFF)
        self.assertEqual(kept["run"].decode().strip(), RUN)
        self.assertEqual(json.loads(kept["record.json"]), RECORD)
        self.assertEqual((json.loads(kept["texts.json"]), json.loads(kept["findings.json"])), ([ISSUE_TEXT], []))
        # The issues the change serves are read of the pull request read, by what the snapshot was told of its opener.
        self.assertEqual(calls["issues"], (True, (12, "Bot"), True))
        self.assertEqual(json.loads(kept["role.json"])["name"], "pr-review")
        # The threads are held to what the item's Lenses recorded, read from the run records (issue 338).
        self.assertEqual(calls["recorded"], [({}, True, [])])
        # What the opening Runs recorded is read for the configured Role and handed to the snapshot (issue 342).
        self.assertEqual((calls["opened"], calls["opened_role"]), ([True], ["dev-lead"]))
        # Of the run list of both Role workflows, the model Lenses' Runs on this item, held to the authority table.
        # No job is asked: this read hands the Kernel no run record, so when a Run began is nothing to it, and jobs
        # that could not be read would refuse a Task for nothing (decision 0199).
        self.assertEqual(calls["listed"], [(["run.yml", "approve.yml"], {})])
        self.assertEqual(calls["asked"], [{"repo": HOME, "numbers": [42], "lenses": {"pr-review"}, "authority": AUTHORITY}])
        # A list read short holds them to nothing recorded, not whole: the Task is refused rather than built on it.
        self.assertEqual(self.go(complete=False)[4]["recorded"], [({}, False, [])])
        # Minted once, for the home repo, with reads alone, and revoked once.
        (app, repo, wanted, key), = calls["minted"]
        self.assertEqual((app, repo, key, calls["revoked"]), ("combsmith-sf-reader", HOME, "the key", 1))
        self.assertEqual(set(wanted.values()), {"read"})
        # The pull request is read with the App that opens pull requests, as the pass reads it (issue 295).
        self.assertEqual(calls["opener"], [(12, "Bot")])
        # What `run` takes from the folder is what the reader wrote.
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "task"))
            for name, data in kept.items():
                pathlib.Path(d, "task", name).write_bytes(data)
            self.assertEqual(run.from_folder("task", "result", d)[:2], [os.path.join("task", "record.json"), RUN])
            pathlib.Path(d, "task", "run").write_text("../../x\n")
            with self.assertRaises(run.task.Refused):
                run.from_folder("task", "result", d)

    def test_the_reader_hands_a_review_its_lenss_open_findings_and_what_it_said(self):  # issue 856
        # A review rules on a Finding only if it is shown it. The reader lists each open thread of the Run's own Lens
        # that gates, `apply.shown` of the facts, as a Finding of the Task, and reads what the Lens said on it, by the
        # thread's id, as the text `finding:` and the Finding's id, before the issue's.
        fid = lambda key: read.apply.finding_id("pr-review", {"type": "thread", "key": key})
        threads = [support.thread("PRRT_kw7"), support.thread("PRRT_kw9", kind="human", name="don-petry"),
                   support.thread("PRRT_kw8", category="security"), support.thread("PRRT_kw14", severity="blocking")]
        code, printed, files, kept, calls = self.go(threads=threads)
        self.assertEqual(code, 0, printed)
        self.assertEqual(calls["findings"], [("the reader's transport", True, "pr-review", ["PRRT_kw7", "PRRT_kw14"])])
        self.assertEqual(json.loads(kept["findings.json"]), [fid("PRRT_kw7"), fid("PRRT_kw14")])
        self.assertEqual(json.loads(kept["texts.json"]), [
            {"id": "finding:" + fid("PRRT_kw7"), "by": LENS, "body": "What it said on PRRT_kw7."},
            {"id": "finding:" + fid("PRRT_kw14"), "by": LENS, "body": "What it said on PRRT_kw14."}, ISSUE_TEXT])
        # With none to show, nothing is asked of the texts port for it.
        self.assertNotIn("findings", self.go(threads=threads[1:3])[4])
        # What the Lens said that cannot be read, an edited comment's among them, builds no Task: the step stops by
        # its code, the token revoked, and so it does where the port answers other than one text for each thread.
        for raising, said in (((read.texts, "findings", read.Unanswered("a thread's first comment was edited")), None),
                              (None, []), (None, [{"id": "thread:PRRT_kw7", "by": LENS, "body": "x"}] * 3)):
            code, printed, files, kept, calls = self.go(threads=threads, raising=raising, said=said)
            self.assertEqual((code, files, calls["revoked"]), (1, [], 1), printed)
            self.assertIn("finding_texts_unreadable", printed)

    def test_a_head_that_cannot_be_read_or_unpacked_whole_builds_no_task(self):
        # Decision 0138: the review reads the head, so a head the reader cannot read, or an archive it will not write,
        # stops the step by its one code, and the token is revoked all the same.
        def refused(sha):
            raise read.head_.Refused("the tarball was not answered")
        for name, tarred in (("not answered", refused), ("another commit's", lambda sha: support.tarball("e" * 40)),
                             ("a device", lambda sha: support.tarball(sha, [("dev", b"3", b"")]))):
            with self.subTest(name=name):
                code, printed, files, _, calls = self.go(tarred=tarred)
                self.assertEqual((code, printed, calls["revoked"]), (1, "head_unreadable\n", 1))
                # Nothing is left that a run could take for a Task: no file, and no part of the head (Astra's read).
                self.assertEqual(files, [], name)
        partial = lambda sha: support.tarball(sha, [("README.md", b"0", b"# a\n"), ("dev", b"3", b"")])
        code, printed, files, _, _ = self.go(tarred=partial)
        self.assertEqual((code, printed, files), (1, "head_unreadable\n", []))
        # Issue 543: a tree that cannot be read, or a head that is not its commit's tree, a file the archive left out or
        # one it holds otherwise than committed, is refused the same way, and leaves nothing either.
        def unread(sha):
            raise read.head_.Refused("the commit's tree was not answered whole")
        for name, tree in (("no tree", unread),
                           ("a file left out", lambda sha: {"files": {"README.md": (README_BLOB, 9), "kept.md": (README_BLOB, 9)},
                                                            "links": set()}),
                           ("a file otherwise", lambda sha: {"files": {"README.md": ("e" * 40, 9)}, "links": set()})):
            with self.subTest(name=name):
                code, printed, files, _, calls = self.go(tree=tree)
                self.assertEqual((code, printed, files, calls["revoked"]), (1, "head_unreadable\n", [], 1))

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
        # A token GitHub did not revoke is the step's one code: no outcome is left to say the Run was superseded
        # (Muse's read of #340).
        code, printed, files, _, _ = self.go(refs=moved, revoked=False)
        self.assertEqual((code, printed, files), (1, "token_not_revoked\n", []))
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
            # The workflow's form: the run job's `reader-outcome` artifact, downloaded to the folder of its name.
            os.rename(os.path.join(d, "task"), os.path.join(d, "reader-outcome"))
            self.assertEqual(ran(outcome.step, [], dict(env, NAME=NAME), d), (1, "release_moved\n"))
            self.assertEqual(json.loads(pathlib.Path(d, "outcome", "outcome.json").read_bytes()),
                             json.loads(kept["outcome.json"]))
            os.rename(os.path.join(d, "reader-outcome"), os.path.join(d, "task"))
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
                       {"commit": None}, {"commit": "HEAD"}, {"commit": CHECKED_OUT.upper()}):
            with self.subTest(change=change):
                code, printed, files, _, calls = self.go(**change)
                self.assertEqual((code, printed, files, calls["revoked"]), (1, "release_unresolved\n", [], 1))
        # The commit is the job's own, `steps.commit()`, read before any key: a checkout it cannot read mints nothing.
        def unreadable():
            raise steps.Stop("release_unreadable")
        code, printed, files, _, calls = self.go(commit=unreadable)
        self.assertEqual((code, printed, calls["minted"]), (1, "release_unreadable\n", []))

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
        # An approving run-name finds its act, and the reader builds no Task on it: the approval is the approving act's.
        out = tc.passed(tc.reads(pulls=[tc.pr(1), tc.pr(42)], runs=[tc.run(number=42)]))
        approving, = [d for d in out["dispatch"] if " issue-approval " in d["name"]]
        code, printed, files, _, calls = self.go(record=out["record"],
                                                 argv=[approving["name"], ITEM, out["record"]["pass"], "task"])
        self.assertEqual((code, printed, files, calls["revoked"]), (1, "not_the_decision\n", [], 1))
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
        # A read GitHub did not answer stops the step by a code that names the read, never by what GitHub said, so a Run
        # that stops says which read it was (pull request 688, the dry run); one that moved is told apart; the token is
        # revoked anyway.
        def part():
            err = github.Unanswered("what GitHub said")
            err.part = "timeline"
            return err
        no = lambda: github.Unanswered("what GitHub said")
        for (module, name, error), want in (((read.tags, "read", no), "release_refs_unreadable"),
                                            ((passes, "find", no), "pass_record_unreadable"),
                                            ((read.records, "runs", no), "run_records_unreadable"),
                                            ((read.applied, "recorded", no), "lens_records_unreadable"),
                                            ((read.applied, "opened", no), "opened_records_unreadable"),
                                            ((read.facts_, "snapshot", no), "snapshot_unreadable"),
                                            ((read.facts_, "snapshot", part), "snapshot_timeline_unreadable"),
                                            ((read.facts_, "snapshot", lambda: read.facts_.Moved("moved")), "pull_moved"),
                                            ((read.pull, "read", no), "pull_unreadable"),
                                            ((read.pull, "change", no), "change_unreadable"),
                                            ((read.texts, "issues", no), "issue_texts_unreadable"),
                                            # A read no stage names, should one be added, still stops by a code.
                                            ((read.facts_, "accounts_of", no), "facts_unreadable"),
                                            # A fault of a read's own code is told its stage (decision 0187), and the
                                            # reader still fails on it as it did, by no read's code.
                                            ((read.facts_, "snapshot", lambda: TypeError("x")), "step_failed"),
                                            ((read.records, "runs", lambda: KeyError("x")), "step_failed")):
            code, printed, files, _, calls = self.go(raising=(module, name, error()))
            self.assertEqual((code, printed, files, calls["revoked"]), (1, want + "\n", [], 1), want)


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
            ok = {"RUN_DIGEST": digest, "RELEASE": result["release"]}
            self.assertEqual(ran(verify.step, ["result", "verdict"], ok, d)[0], 0)
            # A commit no Release tag names is refused first; a Result of another Release than the job's, refused.
            self.assertEqual(ran(verify.step, ["result", "v4"], {"RUN_DIGEST": digest}, d), (1, "release_untagged\n"))
            self.assertEqual(ran(verify.step, ["result", "v5"], dict(ok, RELEASE="factory/v9.9.9"), d),
                             (1, "release_differs\n"))
            said = json.loads(pathlib.Path(d, "verdict", "verdict.json").read_text())
            self.assertEqual((said["checks"], said["digest"], said["run"]), ("not_run", digest, result["run"]))
            for environ, want in (({"RUN_DIGEST": "sha256:" + "0" * 64}, "result_not_the_runs"),
                                  ({}, "digest_unreadable"), ({"RUN_DIGEST": "abc"}, "digest_unreadable")):
                environ = dict(environ, RELEASE=result["release"])
                self.assertEqual(ran(verify.step, ["result", "v2"], environ, d), (1, want + "\n"), environ)
            pathlib.Path(d, "result", "result.json").write_bytes(b"{}")
            self.assertEqual(ran(verify.step, ["result", "v3"], {"RUN_DIGEST": "sha256:" + hashlib.sha256(b"{}").hexdigest(),
                                                                 "RELEASE": result["release"]}, d), (1, "result_unreadable\n"))


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

        def recorded(admit, result, read_, write, mint, role, config, now, held=None):
            calls["job"].append((admit, result, config))
            if a_job:
                return a_job(admit, result, read_, write, mint, role, config, now, held)
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

    def test_apply_says_whether_the_engine_step_started(self):  # issue 757
        # The run job hands on its Engine step's outcome. GitHub skips that step once a step before it failed, as the
        # CLI's install did in the outage: then the Run spent no model, and its outcome says `engine_started` false.
        # The run job hands on its Engine step's outcome, and `apply` is given every job's results and outputs.
        live = (ROOT / ".github" / "workflows" / "run-jobs.yml").read_text()
        for line in ("      engine: ${{ steps.engine.outcome }}\n", "      - name: Run the Engine\n        id: engine\n",
                     "      NEEDS: ${{ toJSON(needs) }}\n"):
            self.assertEqual(live.count(line), 1, line)

        def needs(run_result, engine, verify="skipped"):
            run = {"result": run_result, "outputs": {} if engine is None else {"engine": engine}}
            return json.dumps({"run": run, "verify": {"result": verify, "outputs": {}}})
        for engine, run_result, started in (("skipped", "failure", False), ("failure", "failure", True),
                                            ("cancelled", "cancelled", True), ("success", "failure", True)):
            code, _, ended, calls = self.go({"NEEDS": needs(run_result, engine)})
            self.assertEqual((code, ended["outcome"], ended["reason"], ended.get("engine_started"), calls["minted"]),
                             (0, "environment", "run_failed", started, []), engine)
        # A Run whose run job succeeded reached the Engine, whatever ends it after.
        code, _, ended, _ = self.go({"NEEDS": needs("success", "success", verify="failure")})
        self.assertEqual((ended["reason"], ended.get("engine_started")), ("verify_failed", True))
        code, printed, ended, _ = self.go({"NEEDS": needs("success", "success", verify="success")})
        self.assertEqual((code, ended["outcome"], ended.get("engine_started")), (0, None, True), printed)
        # What does not say the Engine step was skipped, or ran, says nothing: the field is left out, and the Run is read
        # as one that may have reached the model.
        for engine in (None, "", "neutral", 0, True, ["skipped"]):
            code, _, ended, _ = self.go({"NEEDS": needs("failure", engine)})
            self.assertEqual((ended["reason"], "engine_started" in ended), ("run_failed", False), engine)
        odd = json.dumps({"run": {"result": "failure", "outputs": "skipped"}, "verify": {"result": "skipped"}})
        for said in (odd, json.dumps({"run": {"result": "failure"}, "verify": {"result": "skipped"}}), "not json", None):
            code, _, ended, _ = self.go({"NEEDS": said})
            self.assertNotIn("engine_started", ended, said)

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
        # The reviewers a Finding may be adopted from are the ones the configuration names advisory (decision 0145).
        self.assertEqual(config["advisory"], json.loads((ROOT / "config" / "harness.json").read_text())["advisory"])
        self.assertTrue(config["advisory"])
        # The Task's diff is built again cut at the Kernel's own bound, as the read step's Task was (issue 327).
        defaults = json.loads((ROOT / "config" / "defaults.json").read_text())
        self.assertEqual(config["max_diff_characters"], defaults["limits"]["max_diff_characters"])
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
        staged = github.Unanswered("no answer")
        staged.stage, staged.part = "snapshot", "timeline"
        for raised, want in ((reread.facts_.Moved("moved"), ("superseded", "head_moved")),
                             (github.Unanswered("no answer"), ("environment", "facts_unreadable")),
                             # Named by the read again's stage and the snapshot's part (pull request 688, the dry run).
                             (staged, ("environment", "snapshot_timeline_unreadable"))):
            def reading(*a, raised=raised):
                raise raised
            with unittest.mock.patch.object(reread, "item", reading):
                code, _, ended, _ = self.go(a_job=lambda admit, result, read_, *a: read_())
            self.assertEqual((ended["outcome"], ended["reason"]), want, raised)
        # A fault of the read's own code is told its stage (decision 0187), and apply still fails on it as it did: by
        # no read's code, and with no outcome of its own.
        def faulty(*a):
            with shared.staged("context"):
                raise TypeError("an answer no adapter expected")
        with unittest.mock.patch.object(reread, "item", faulty):
            code, printed, ended, _ = self.go(a_job=lambda admit, result, read_, *a: read_())
        self.assertEqual((code, printed, ended), (1, "step_failed\n", None))
        # Apply asks the read again for no part of the Pause: it reads its Pause in the context, in its own order, as
        # it did (decision 0192).
        asked_for = []

        def plain(*a, **k):
            asked_for.append(k)
            raise reread.facts_.Moved("moved")
        with unittest.mock.patch.object(reread, "item", plain):
            self.go(a_job=lambda admit, result, read_, *a: read_())
        self.assertEqual(asked_for, [{}])
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
        self.assertEqual(self.go({"RELEASE": "v1"})[:3], (1, "release_untagged\n", None))
        # No Decision for this Run: superseded, and the job is never asked.
        code, _, ended, calls = self.go(record=None)
        self.assertEqual((ended["outcome"], ended["reason"], calls["job"], calls["revoked"]),
                         ("superseded", "no_decision", [], 1))

    def test_apply_holds_a_push_to_the_list_at_the_base_its_pull_request_was_read_at(self):  # issue 139
        # The step gives apply its hold: the base commit from a read of the pull request at the head its facts were read
        # at, and the list read through the read token at that commit, never one the head names.
        asked = []

        def read_pull(transport, repo, number):
            asked.append(("read", transport, repo, number))
            return {"head": {"sha": HEAD}, "base": {"sha": "b" * 40}}

        def holding(effects, base, transport, repo, fetch=None):
            asked.append(("held", effects, base, transport, repo))
            return "item", "push_protected"

        def a_job(admit, result, read_, write, mint, role, config, now, held):
            read_()
            return apply_step._ended(admit["run"], admit["release"], held({"push_commits": ["e9"]}))
        with unittest.mock.patch.object(apply_step.pull, "read", read_pull), \
                unittest.mock.patch.object(apply_step.bundle, "held", holding), \
                unittest.mock.patch.object(reread, "item", lambda *a, **k: ("facts", HEAD, [], {})):
            code, _, ended, _ = self.go(a_job=a_job)
        self.assertEqual((code, ended["outcome"], ended["reason"]), (0, "item", "push_protected"))
        self.assertEqual(asked, [("read", "the read transport", HOME, 42),
                                 ("held", {"push_commits": ["e9"]}, "b" * 40, "the read transport", HOME)])
        # A pull request that moved from the head its facts were read at is a change under the Run.
        with unittest.mock.patch.object(apply_step.pull, "read", read_pull):
            with self.assertRaises(reread.facts_.Moved):
                apply_step.base_at("t", HOME, 42, "c" * 40)

    def test_apply_reads_the_diff_again_at_the_head_its_facts_were_read_at(self):  # issue 567
        asked = []
        first = {"head": {"sha": HEAD}}

        def read_pull(transport, repo, number):
            asked.append(("read", transport, repo, number))
            return first

        def change(transport, pull_, base_head):
            asked.append(("change", transport, pull_, base_head))
            return b"the diff"
        with unittest.mock.patch.object(apply_step.pull, "read", read_pull), \
                unittest.mock.patch.object(apply_step.pull, "base", lambda t, p: {"head": "b" * 40}), \
                unittest.mock.patch.object(apply_step.pull, "change", change):
            self.assertEqual(apply_step.change_at("t", HOME, 42, HEAD), b"the diff")
            self.assertEqual(asked, [("read", "t", HOME, 42), ("change", "t", first, "b" * 40)])
            # A pull request whose head is not the facts' has moved under the Run: its diff is not read.
            del asked[:]
            with self.assertRaises(apply_step.Moved):
                apply_step.change_at("t", HOME, 42, "c" * 40)
            self.assertEqual(asked, [("read", "t", HOME, 42)])

    def test_apply_writes_through_its_roles_allowlist_on_the_item_read_again(self):
        # The job's callbacks, as `apply` calls them: the item read again through the read token; a write token minted
        # from the key with what the Effects need; and each write held to the Role's allowlist on the admitted item.
        seen = {"reread": [], "role_write": []}
        # The facts of the content admitted, so the diff is read again of it.
        facts = dict(support.facts(), threads=[support.thread("T1")], content_id=CONTENT)

        def a_job(admit, result, read_, write, mint, role, config, now, held):
            read_()[4]()
            transport, revoke = mint({"pull_requests": "write"})
            write(transport, "comment", {"on": "item"})
            revoke()
            return apply_step._ended(admit["run"], admit["release"], (None, None))

        def item(transport, config, number, now, clock):
            seen["reread"].append((transport, number))
            return facts, HEAD, [], support.context()

        def change_at(transport, repo, number, head):
            seen["change"].append((transport, repo, number, head))
            return b"the diff"
        seen["change"] = []

        def role_write(transport, item_, kind, req, login):
            seen["role_write"].append((transport, item_, kind, login))
            return {"state": "applied", "key": "IC_x"}
        with unittest.mock.patch.object(reread, "item", item), \
                unittest.mock.patch.object(apply_step, "change_at", change_at), \
                unittest.mock.patch.object(effects, "role_write", role_write):
            code, printed, ended, calls = self.go(job=None, a_job=a_job)
        self.assertEqual((code, ended["outcome"]), (0, None), printed)
        self.assertEqual(seen["reread"], [("the read transport", 42)])
        # The diff is read again through the read token, at the head the facts were read at (issue 567).
        self.assertEqual(seen["change"], [("the read transport", HOME, 42, HEAD)])
        self.assertEqual([wanted for _, wanted in calls["minted"]][1], {"pull_requests": "write"})
        (transport, item_, kind, login), = seen["role_write"]
        self.assertIsInstance(transport, effects.Allowed)
        self.assertEqual((item_, kind, login), (dict(support.ITEM), "comment", "combsmith-sf-pr-review[bot]"))
        # Held: the allowlist refuses a write on another item.
        with self.assertRaises(github.Unanswered):
            transport.send(github.request("POST", "/repos/%s/issues/43/comments" % HOME, body={"body": "x"}))
        # The diff is read when `apply` asks for it, and not before: the item read again reads none.
        del seen["change"][:]
        with unittest.mock.patch.object(reread, "item", item), \
                unittest.mock.patch.object(apply_step, "change_at", change_at), \
                unittest.mock.patch.object(effects, "role_write", role_write):
            def reads_only(admit, result, read_, *a):
                read_()
                return apply_step._ended(admit["run"], admit["release"], (None, None))
            self.go(job=None, a_job=reads_only)
        self.assertEqual(seen["change"], [])

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

        reread_through, asked_for = [], []

        def a_job(record, run_, read_, port, config, now):
            seen.append((record, run_, port, config))
            read_()
            return approve_step.approve._records(run_, config["release"], "applied", "PRR_x", None)

        def item(transport, *a, **k):
            reread_through.append(transport)
            asked_for.append(k)
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
        # And asked for the Pause by name, so a Pause the port could not read says which read it was (decision 0192).
        self.assertEqual(asked_for, [{"name_pause": True}])
        self.assertEqual((record, run_, config["approver"], config["github_run"]), (RECORD, RUN, "donpetry-bot", "9"))
        self.assertEqual(done["effects"][0]["state"], "applied")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ran(approve_step.step, [NAME, ITEM, PASS, "o"], {}, d), (1, "release_untagged\n"))
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

    def test_an_approving_run_finds_its_act_by_its_run_name_and_approves(self):  # pull request 688, the fourth dry run
        # The pass names the approving Run by its Intent, `issue-approval`, and records its act by the Kernel's action,
        # `issue_approval`. The step finds the one by the other, in a record that holds an admission too, and the job,
        # run whole on it, sends the approval of the head read again and nothing else.
        out = tc.passed(tc.reads(pulls=[tc.pr(1), tc.pr(42)], runs=[tc.run(number=42)]))
        record, (reviewing, approving) = out["record"], out["dispatch"]
        named = records.named(approving["name"])
        self.assertEqual((named["intent"], named["item"], named["role"]), ("issue-approval", ta.ITEM, "pr-review"))
        entry, = [e for e in record["pull_requests"] if e["run"] == approving["run"]]
        self.assertEqual((entry["decision"]["outcome"], entry["decision"]["action"]), ("act", "issue_approval"))
        now = datetime.datetime.strptime(record["now"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc).timestamp()

        def go(name, item=ITEM, found=record, context=record["context"], raised=None):
            sent = ta.GitHub()

            def read_again(*a, **k):
                if raised is not None:
                    raise raised
                return (copy.deepcopy(entry["facts"]), ta.HEAD, copy.deepcopy(record["runs"]), copy.deepcopy(context))
            with tempfile.TemporaryDirectory() as d, \
                    unittest.mock.patch.object(passes, "find", lambda *a: copy.deepcopy(found)), \
                    unittest.mock.patch.object(reread, "item", read_again):
                code, printed = ran(approve_step.step, [name, item, record["pass"], "approved"],
                                    {"RELEASE": RELEASE, approve_step.TOKEN: "t", "GITHUB_RUN_ID": "9"}, d,
                                    lambda: now, lambda token: sent)
                ended = json.loads(pathlib.Path(d, "approved", "outcome.json").read_text())
                done = json.loads(pathlib.Path(d, "approved", "applied.json").read_text())
            return code, printed, ended["outcome"], done["effects"][0]["state"], sent.writes()
        approval = ("POST", ta.PULL + "/reviews", {"commit_id": ta.HEAD, "event": "APPROVE"})
        self.assertEqual(go(approving["name"]), (0, "approval applied\n", None, "applied", [approval]))
        # A run-name that is not the act's own, part by part, finds no Decision, and nothing is written: the Run id of
        # the record's admission, another content, another Role than the owner, another item, and another Intent.
        mine = approving["name"]
        for name, item in ((mine.replace(approving["run"], reviewing["run"]), ITEM),
                           (mine.replace("sha256:aaaa", "sha256:bbbb"), ITEM),
                           (mine.replace(" pr-review ", " security-review "), ITEM),
                           (mine.replace("#42 ", "#1 "), "%s#1" % HOME),
                           (mine.replace(" issue-approval ", " review-change "), ITEM)):
            self.assertNotEqual(name, mine)
            self.assertEqual(go(name, item), (1, "not_the_decision\n", "superseded", "refused", []), name)
        # An act that names no content is no run-name's: the record is read, and nothing is written.
        bare = copy.deepcopy(record)
        for e in bare["pull_requests"]:
            if e["run"] == approving["run"]:
                del e["decision"]["content_id"]
        self.assertEqual(shared.errors(bare, "pass"), [])
        self.assertEqual(go(mine, found=bare), (1, "not_the_decision\n", "superseded", "refused", []))
        # A Pause the approver's token may not read is handed back unread by the Pause's port, never raised; the step
        # ends by the Pause's own code, and nothing is written (pull request 688, the fifth dry run).
        class Refusing:
            def send(self, req):
                return {"status": 403, "body": {}, "headers": {}}
        unread, _ = reread.pass_.human_pause(reread.pause_.read(Refusing(), HOME.split("/")[0], [HOME]), [HOME])
        self.assertIsNone(unread)
        self.assertEqual(go(mine, context=dict(record["context"], paused=unread)),
                         (1, "pause_unreadable\n", "environment", "refused", []))
        # Asked by name, the read again raises that Pause as a read of its own stage, its part the port's, and the step
        # ends by the code of both: which read GitHub refused, and nothing GitHub said (decision 0192, after the
        # seventh dry run stopped at the code above).
        from controller import configuration
        with unittest.mock.patch.object(reread.records, "runs", lambda *a, **k: copy.deepcopy(tc.listed([]))), \
                unittest.mock.patch.object(reread.facts_, "snapshot", lambda *a, **k: (entry["facts"], "t", ta.HEAD)), \
                self.assertRaises(github.Unanswered) as named:
            reread.item(Refusing(), configuration.load(ROOT, RELEASE, "pr-review"), 42, record["now"],
                        lambda: record["now"], name_pause=True)
        self.assertEqual((named.exception.stage, named.exception.part), ("pause", "org_refused"))
        self.assertEqual(go(mine, raised=named.exception),
                         (1, "pause_org_refused_unreadable\n", "environment", "refused", []))


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
        # The pr-review App, expanded on 2026-10-27, is granted every read apply makes again, each at read (decision 0054).
        apps = json.loads((ROOT / "config" / "apps.json").read_text())
        self.assertEqual(set(identity.granted(apps["apps"]["pr-review"], apps["needs"], apply_step.apply.READS,
                                              "read").values()), {"read"})


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
        # The status's checks: write, the tracking issue's issues: write and the Pause's variables read, each granted
        # the App on 2026-10-27.
        self.assertEqual(asked, [("combsmith-sf-controller", HOME, {"actions_variables": "read", "checks": "write",
                                                                    "issues": "write"}, "k")])
        # A need that still waits on its grant is not minted for, and the rest are.
        asked.clear()
        with unittest.mock.patch.object(effects, "CONTROLLER_NEEDS", effects.CONTROLLER_NEEDS + ("effect:dequeue_merge",)), \
                unittest.mock.patch.object(identity, "from_key",
                                           lambda app, repo, wanted, key, now, connect: asked.append(wanted) or
                                           ("t", lambda: True)):
            effects.controller_token({"CONTROLLER_APP_KEY": "k"}, config, 0)
        self.assertEqual(asked, [{"actions_variables": "read", "checks": "write", "issues": "write"}])
        # The workflow's form, with no argument: the pass's own folder, `pass/`, and written.json into it.
        out = tc.passed(tc.reads(pulls=[]))
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "pass"))
            pathlib.Path(d, "pass", "pass.json").write_text(json.dumps(out["record"]))
            pathlib.Path(d, "pass", "writes.json").write_text(json.dumps(writes_.plan(out)))
            # With the Controller's account set the tracking issue is the Controller's to write, so it is told what that
            # write came to: this is the step's form, not that write.
            with contextlib.redirect_stdout(io.StringIO()), \
                    unittest.mock.patch.object(effects, "tracking", lambda *a, **k: ("applied", None, None)):
                self.assertEqual(effects.main([], {}, d), 0)
            self.assertTrue(pathlib.Path(d, "pass", "written.json").is_file())
        # The step fails when GitHub did not revoke the token, and only then.
        out = tc.passed(tc.reads(pulls=[]))
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "pass.json").write_text(json.dumps(out["record"]))
            pathlib.Path(d, "writes.json").write_text(json.dumps(writes_.plan(out)))

            class Quiet:
                def send(self, req):
                    return {"status": 404, "headers": {}, "body": None}
            for revoked, code in ((True, 0), (False, 1)):
                with contextlib.redirect_stdout(io.StringIO()), \
                        unittest.mock.patch.object(effects, "tracking", lambda *a, **k: ("applied", None, None)):
                    self.assertEqual(effects.main(["pass.json", "writes.json", "."], {}, d,
                                                  mint=lambda e, c: (Quiet(), lambda: revoked)), code, revoked)


class Reread(unittest.TestCase):
    def test_the_item_is_read_again(self):
        listed = tc.listed([tc.run(status="in_progress")])
        facts = support.facts()
        whole = []

        def snapshot(transport, repo, number, identities, who, runs_whole, clock, with_head=False, opener=None, *,
                     recorded, opened):
            whole.append((runs_whole, recorded))
            return facts, "t", HEAD
        from controller import configuration
        config = configuration.load(ROOT, RELEASE, "pr-review")
        for short in (dict(listed, complete=False), {"runs": "x"}):
            with unittest.mock.patch.object(reread.records, "runs", lambda *a, **k: copy.deepcopy(short)), \
                    unittest.mock.patch.object(reread.facts_, "snapshot", snapshot), \
                    unittest.mock.patch.object(reread.pause_, "read", lambda *a: {"org": None, "repos": {HOME: None}}):
                if short.get("runs") == "x":
                    with self.assertRaises(github.Unanswered) as raised:
                        reread.item("t", config, 42, support.NOW, lambda: support.NOW)
                    self.assertEqual(getattr(raised.exception, "stage", None), "run_records")
                else:
                    self.assertIsNone(reread.item("t", config, 42, support.NOW, lambda: support.NOW)[3]["active_runs"])
        # Each read GitHub did not answer is named by its stage, and a snapshot's part is kept (pull request 688).
        def no(*a, **k):
            err = github.Unanswered("what GitHub said")
            if a and a[0] == "part":
                err.part = "timeline"
            raise err
        fine = {"runs": lambda *a, **k: copy.deepcopy(listed), "snapshot": lambda *a, **k: (facts, "t", HEAD),
                "pause": lambda *a: {"org": None, "repos": {HOME: None}}}
        for target, name, standin, want in ((reread.records, "runs", no, ("run_records", None)),
                                            (reread.applied, "recorded", no, ("lens_records", None)),
                                            (reread.applied, "opened", no, ("opened_records", None)),
                                            (reread.facts_, "snapshot", lambda *a, **k: no("part"), ("snapshot", "timeline")),
                                            (reread.pause_, "read", no, ("pause", None))):
            with unittest.mock.patch.object(reread.records, "runs", fine["runs"]), \
                    unittest.mock.patch.object(reread.facts_, "snapshot", fine["snapshot"]), \
                    unittest.mock.patch.object(reread.pause_, "read", fine["pause"]), \
                    unittest.mock.patch.object(target, name, standin), self.assertRaises(github.Unanswered) as raised:
                reread.item("t", config, 42, support.NOW, lambda: support.NOW)
            self.assertEqual((getattr(raised.exception, "stage", None), getattr(raised.exception, "part", None)), want)
        # A fault of the read's own code is told its stage too, and so is the context's building, which reads nothing:
        # the approving act records every fault of the read again, and one left unnamed no log can find (decision 0187).
        def odd(*a, **k):
            raise TypeError("an answer no adapter expected")
        for target, name, want in ((reread.records, "runs", "run_records"), (reread.applied, "recorded", "lens_records"),
                                   (reread.applied, "opened", "opened_records"), (reread.facts_, "snapshot", "snapshot"),
                                   (reread.pause_, "read", "pause"), (reread.reads_, "configured", "context"),
                                   (reread.pass_, "context_of", "context")):
            with unittest.mock.patch.object(reread.records, "runs", fine["runs"]), \
                    unittest.mock.patch.object(reread.facts_, "snapshot", fine["snapshot"]), \
                    unittest.mock.patch.object(reread.pause_, "read", fine["pause"]), \
                    unittest.mock.patch.object(target, name, odd), self.assertRaises(TypeError) as raised:
                reread.item("t", config, 42, support.NOW, lambda: support.NOW)
            self.assertEqual(getattr(raised.exception, "stage", None), want, name)
        # A list read short holds the threads to nothing recorded, and they are not whole (issue 338).
        self.assertEqual(whole, [(False, ({}, False, [])), (False, ({}, False, []))])
        asked_ = []
        with unittest.mock.patch.object(reread.records, "runs", lambda *a, **k: copy.deepcopy(listed)), \
                recorded_spy(reread, asked_), \
                unittest.mock.patch.object(reread.facts_, "snapshot", lambda *a, **k: (facts, "t", HEAD)), \
                unittest.mock.patch.object(reread.pause_, "read",
                                           lambda transport, org, repos: {"org": None, "repos": {HOME: None}}):
            got = reread.item("t", config, 42, support.NOW, lambda: support.NOW)
        self.assertEqual(got[:3], (facts, HEAD, listed["runs"]))
        # What the item's model Lenses recorded is read from that list, held to the authority table (issue 338).
        self.assertEqual(asked_, [{"repo": HOME, "numbers": [42], "lenses": {"pr-review"}, "authority": AUTHORITY}])
        self.assertEqual((got[3]["paused"], got[3]["active_runs"], got[3]["passes_since"]), (False, 1, None))
        # What the opening Runs recorded is read for the configured Role and handed to the snapshot (issue 342).
        made, seen, given = {"named": {26: [("r_01JA7Q", 36)]}, "unreadable": set(), "whole": True}, [], []
        with unittest.mock.patch.object(reread.records, "runs", lambda *a, **k: copy.deepcopy(listed)), \
                unittest.mock.patch.object(reread.facts_, "snapshot",
                                           lambda *a, **k: given.append(k["opened"]) or (facts, "t", HEAD)), \
                unittest.mock.patch.object(reread.applied, "opened",
                                           lambda transport, repo, runs, role: seen.append(role) or made), \
                unittest.mock.patch.object(reread.facts_, "opener_role", lambda kernel: "dev-lead"), \
                unittest.mock.patch.object(reread.pause_, "read",
                                           lambda transport, org, repos: {"org": None, "repos": {HOME: None}}):
            reread.item("t", config, 42, support.NOW, lambda: support.NOW)
        self.assertEqual((seen, len(given)), (["dev-lead"], 1))
        self.assertIs(given[0], made)
        # The pull request is read with the App that opens pull requests, as the pass reads it (issue 295).
        told = []
        with unittest.mock.patch.object(reread.records, "runs", lambda *a, **k: copy.deepcopy(listed)), \
                unittest.mock.patch.object(reread.facts_, "snapshot",
                                           lambda *a, **k: told.append(k.get("opener", "not told")) or (facts, "t", HEAD)), \
                unittest.mock.patch.object(reread.facts_, "opener_of", lambda *a: (12, "Bot")), \
                unittest.mock.patch.object(reread.pause_, "read",
                                           lambda transport, org, repos: {"org": None, "repos": {HOME: None}}):
            reread.item("t", config, 42, support.NOW, lambda: support.NOW)
        self.assertEqual(told, [(12, "Bot")])
        # The Pause is read again, on the org and the item's repo, and a Pause or one unreadable is the context's.
        asked = []

        def runs(transport, repo, branch, workflows, dispatcher, **k):
            asked.append(workflows)
            began.append(k)
            return copy.deepcopy(listed)
        began = []
        for paused, want in (({"org": "true", "repos": {HOME: None}}, True), ({"org": None, "repos": {HOME: "true"}}, True),
                             ({"org": None, "repos": {HOME: "maybe"}}, None)):
            with unittest.mock.patch.object(reread.records, "runs", runs), \
                    unittest.mock.patch.object(reread.facts_, "snapshot", lambda *a, **k: (facts, "t", HEAD)), \
                    unittest.mock.patch.object(reread.pause_, "read", lambda transport, org, repos: (
                        asked.append((org, list(repos))), paused)[1]):
                self.assertIs(reread.item("t", config, 42, support.NOW, lambda: support.NOW)[3]["paused"], want, paused)
        self.assertEqual(asked[:2], [["run.yml", "approve.yml"], ("combsmith", [HOME])])
        # The read asks the records port when this item's Runs began, with nothing kept, and no other item's, so
        # that the act decides on its item's records as the pass does (decision 0199).
        self.assertEqual(began[0], {"began": {}, "on": {"repo": HOME, "type": "pull_request", "number": 42}})
        # Asked for the Pause by name, a Pause the port could not read is raised as a read of the `pause` stage, its
        # part the port's for the first scope unreadable, the org's before the repo's (decision 0192). Not asked, as
        # apply reads it, the same Pause is the context's and nothing is raised.
        entry = {"name": reread.pause_.NAME, "value": "false"}
        clear, unset = (200, {"total_count": 1, "variables": [entry]}), (200, {"total_count": 0, "variables": []})

        class Answering:
            def __init__(self, org, repo):
                self.org, self.repo = org, repo

            def send(self, req):
                status, body = self.org if "/organization-variables" in req["path"] else self.repo
                return {"status": status, "headers": {}, "body": body}
        patched = lambda runs=listed: (
            unittest.mock.patch.object(reread.records, "runs", lambda *a, **k: copy.deepcopy(runs)),
            unittest.mock.patch.object(reread.facts_, "snapshot", lambda *a, **k: (facts, "t", HEAD)))
        for org, repo, want in (((403, {}), (200, entry), "org_refused"), ((404, {}), (200, entry), "org_refused"),
                                (unset, (200, entry), "org_unnamed"), ((500, {}), (200, entry), "org"),
                                (clear, (403, {}), "repo_refused"), (clear, (500, {}), "repo"),
                                ((403, {}), (403, {}), "org_refused"), (unset, (500, {}), "org_unnamed"),
                                ((500, {}), (403, {}), "org")):
            a, b = patched()
            with a, b, self.assertRaises(github.Unanswered) as raised:
                reread.item(Answering(org, repo), config, 42, support.NOW, lambda: support.NOW, name_pause=True)
            self.assertEqual((raised.exception.stage, raised.exception.part), ("pause", want), (org, repo))
            a, b = patched()
            with a, b:
                self.assertIsNone(reread.item(Answering(org, repo), config, 42, support.NOW, lambda: support.NOW)[3]["paused"])
        # A scope that pauses is a Pause whatever else could not be read, and a value that is no Pause is one the port
        # read: neither is raised, and each is the context's as before. A Pause read clear raises nothing.
        for org, repo, want in (((403, {}), (200, dict(entry, value="true")), True),
                                ((200, {"total_count": 1, "variables": [dict(entry, value="true")]}), (403, {}), True),
                                (clear, (200, dict(entry, value="maybe")), None), (clear, (200, entry), False),
                                (clear, (404, {}), False)):
            a, b = patched()
            with a, b:
                got = reread.item(Answering(org, repo), config, 42, support.NOW, lambda: support.NOW, name_pause=True)
            self.assertIs(got[3]["paused"], want, (org, repo))
        # Run records that cannot be read are named first, as they are read first.
        a, b = patched({"runs": "x"})
        with a, b, self.assertRaises(github.Unanswered) as raised:
            reread.item(Answering((403, {}), (403, {})), config, 42, support.NOW, lambda: support.NOW, name_pause=True)
        self.assertEqual((raised.exception.stage, getattr(raised.exception, "part", None)), ("run_records", None))


if __name__ == "__main__":
    unittest.main()
