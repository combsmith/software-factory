"""The release workflow's step (#197's rulings 4′, 4″ and 5′): the commit's facts read by `adapters/candidate.py`, the
tags written by `adapters/tags.py`, the Deployment by `adapters/deployments.py`, and `release.move step`, which sends
a plan's writes and reads each back. No test writes to GitHub: every answer is a replay, in the shapes GitHub's REST
reference gives, since no release step has run yet; the first cut's fixture is a later pull request's."""
from __future__ import annotations

import base64
import contextlib
import copy
import hashlib
import io
import json
import pathlib
import unittest
import zipfile

from adapters import candidate, deployments, github, tags
from harness import eval as eval_gate
from release import cut, move

REPO = "combsmith/software-factory"
A, B, D = ("a" * 40, "b" * 40, "d" * 40)
NEXT, VERSION = "factory/v0-next", "factory/v0.3.0"
REFS = {"factory/v0.1.0": A, "factory/v0.2.0": B, NEXT: B}
STORE = "https://productionresultssa7.blob.core.windows.net/actions-results/0a1b/eval-report.zip?sig=redacted"
SET = {"schema": "eval-set/1", "role": "pr-review", "intent": "review-change", "count": 1,
       "cases": [{"id": "synthetic-early-return", "sha256": "a" * 64}]}
SET_BYTES = (json.dumps(SET, indent=2) + "\n").encode()
EVAL_RUN = 4242
MAIN = "e" * 40     # main's head, read by its ref
ROOT = pathlib.Path(__file__).resolve().parent.parent


def ex(method, path, status, body, sent=None, headers=None, via="rest"):
    return {"request": {"via": via, "call": "%s %s" % (method, path), "headers": {}, "body": sent},
            "response": {"status": status, "headers": headers or {}, "body": body}}


def refs_read(refs, status=200):
    body = [{"ref": "refs/tags/" + name, "object": {"sha": sha, "type": "commit"}} for name, sha in sorted(refs.items())]
    return ex("GET", tags.path(REPO), status, body)


def report(commit=D, release=VERSION, verdict="pass", **change):
    document = {"schema": "eval-report/1", "release": release, "commit": commit, "role": SET["role"],
                "intent": SET["intent"], "set": {"count": SET["count"], "sha256": hashlib.sha256(SET_BYTES).hexdigest()},
                "cases": [dict(SET["cases"][0], verdict=verdict, reasons=[])], "passed": 1 if verdict == "pass" else 0,
                "split_ok": True}
    document.update(change)
    return document


def zipped(document) -> bytes:
    held = io.BytesIO()
    with zipfile.ZipFile(held, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(candidate.MEMBER, document if isinstance(document, str) else json.dumps(document))
    return held.getvalue()


def main_ref(sha=MAIN, **change):
    return ex("GET", "/repos/%s/git/ref/heads/main" % REPO, 200,
              dict({"ref": "refs/heads/main", "object": {"sha": sha, "type": "commit"}}, **change))


def compared(commit=D, status="ahead", base=None):
    """main's head read by its ref, then the commit compared with it."""
    return [main_ref(), ex("GET", "/repos/%s/compare/%s...%s?per_page=1" % (REPO, commit, MAIN), 200,
                           {"status": status, "merge_base_commit": {"sha": commit if base is None else base}})]


SUITE = 5150      # the check suite the verify check run is of


def verify_runs(commit=D, conclusion="success", app=candidate.ACTIONS_APP, more=()):
    runs = [{"name": "verify", "head_sha": commit, "status": "completed", "conclusion": conclusion, "app": {"id": app},
             "check_suite": {"id": SUITE}, "id": 77, "details_url": "https://github.com/%s/actions/runs/901/job/77" % REPO}]
    runs += list(more)
    return ex("GET", "/repos/%s/commits/%s/check-runs?check_name=verify&filter=latest&per_page=100" % (REPO, commit),
              200, {"total_count": len(runs), "check_runs": runs})


def verify_suite(commit=D, path=candidate.VERIFY_WORKFLOW, runs=None, total=None, status=200, suite=SUITE):
    """The verify check run's suite's workflow runs, read by the suite's id, as the actions runs list gives them."""
    runs = [{"id": 901, "path": path, "head_sha": commit, "check_suite_id": suite}] if runs is None else runs
    return ex("GET", "/repos/%s/actions/runs?check_suite_id=%d&per_page=100" % (REPO, suite), status,
              {"total_count": len(runs) if total is None else total, "workflow_runs": runs})


def manifest(commit=D, data=SET_BYTES, status=200):
    return ex("GET", "/repos/%s/contents/%s?ref=%s" % (REPO, candidate.SET, commit), status,
              {"type": "file", "path": candidate.SET, "encoding": "base64", "size": len(data),
               "content": base64.b64encode(data).decode()})


def run_of(commit=D, **change):
    return dict({"id": EVAL_RUN, "run_number": 7, "head_sha": commit, "conclusion": "success",
                 "event": "workflow_dispatch", "path": ".github/workflows/eval.yml"}, **change)


def eval_runs(commit=D, runs=None, total=None):
    runs = [run_of(commit)] if runs is None else runs
    return ex("GET", "/repos/%s/actions/workflows/eval.yml/runs?head_sha=%s&event=workflow_dispatch&status=success"
                     "&per_page=100" % (REPO, commit), 200,
              {"total_count": len(runs) if total is None else total, "workflow_runs": runs})


def report_download(document, ident=9, run=EVAL_RUN):
    data = zipped(document)
    return [ex("GET", "/repos/%s/actions/runs/%d/artifacts?name=eval-report&per_page=100" % (REPO, run), 200,
               {"total_count": 1, "artifacts": [{"id": ident, "name": "eval-report", "expired": False,
                                                 "size_in_bytes": len(data),
                                                 "digest": "sha256:" + hashlib.sha256(data).hexdigest()}]}),
            ex("GET", "/repos/%s/actions/artifacts/%d/zip" % (REPO, ident), 302, None, headers={"location": STORE}),
            ex("GET", STORE, 200, data.decode("utf-8", errors="surrogateescape"), via="storage")]


def gate_reads(commit=D, document=None):
    return [manifest(commit), eval_runs(commit)] + report_download(report(commit) if document is None else document)


def facts_reads(commit=D, document=None):
    return compared(commit) + [verify_runs(commit), verify_suite(commit)] + gate_reads(commit, document)


class Candidate(unittest.TestCase):
    def test_the_facts_of_a_commit_on_main_verified_and_judged(self):
        facts = candidate.facts(github.Replay(facts_reads()), REPO, D, VERSION)
        self.assertEqual(facts, {"commit": D, "on_main": True, "verified": True, "gate": "pass", "release": VERSION})
        self.assertTrue(candidate.on_main(github.Replay(compared(status="identical")), REPO, D))
        missing = [main_ref(), dict(compared()[1], response={"status": 404, "headers": {}, "body": {"message": "x"}})]
        for odd in (compared(status="diverged"), compared(status="behind"), compared(base=A), missing,
                    [dict(compared()[0], response=dict(compared()[0]["response"], body={"status": "ahead"}))],
                    # Each with the comparison it would lead to, so the ref's own reading is what refuses it.
                    [main_ref(ref="refs/tags/main"), compared()[1]],
                    [main_ref(object={"sha": MAIN, "type": "tag"}), compared()[1]],
                    [main_ref(object="bad")],
                    [main_ref(sha="main"), ex("GET", "/repos/%s/compare/%s...main?per_page=1" % (REPO, D), 200,
                                              {"status": "ahead", "merge_base_commit": {"sha": D}})],
                    [main_ref(), dict(compared()[1], response=dict(compared()[1]["response"],
                                                                     body={"status": "ahead", "merge_base_commit": "x"}))]):
            with self.subTest(reads=odd):
                self.assertFalse(candidate.on_main(github.Replay(odd), REPO, D))
        self.assertFalse(candidate.on_main(github.Replay([]), REPO, D))

    def test_verify_counts_only_as_github_actions_one_success_on_the_commit(self):
        for odd in (verify_runs(conclusion="failure"), verify_runs(app=99), verify_runs(commit=D, more=[
                        {"name": "verify", "head_sha": D, "status": "completed", "conclusion": "success",
                         "app": {"id": 99}}]),
                    ex("GET", "/repos/%s/commits/%s/check-runs?check_name=verify&filter=latest&per_page=100" % (REPO, D),
                       200, {"total_count": 2, "check_runs": []}),
                    ex("GET", "/repos/%s/commits/%s/check-runs?check_name=verify&filter=latest&per_page=100" % (REPO, D),
                       200, {"total_count": 0, "check_runs": []}),
                    verify_runs(more=[{"name": "verify-extra", "head_sha": D, "status": "completed",
                                       "conclusion": "success", "app": {"id": candidate.ACTIONS_APP}}]),
                    dict(verify_runs(), response=dict(verify_runs()["response"],
                                                      body=dict(verify_runs()["response"]["body"], total_count=2)))):
            with self.subTest(runs=odd["response"]["body"]):
                # The suite's run is answered as verify.yml's, so only the check run itself can make it fail.
                self.assertFalse(candidate.verified(github.Replay([odd, verify_suite()]), REPO, D))
        self.assertFalse(candidate.verified(github.Replay([]), REPO, D))
        self.assertTrue(candidate.verified(github.Replay([verify_runs(), verify_suite()]), REPO, D))
        for change in ({"head_sha": A}, {"status": "in_progress"}, {"app": "x"}):
            with self.subTest(change=change):
                answered = verify_runs()
                answered["response"]["body"]["check_runs"][0].update(change)
                self.assertFalse(candidate.verified(github.Replay([answered, verify_suite()]), REPO, D))

    def test_verify_counts_only_from_verify_yml_as_the_kernels_lens_reads_it(self):  # decision 0080
        # The check, its App and its workflow file are the Kernel's verify Lens's, read from config/defaults.json.
        lenses = json.loads((ROOT / "config" / "defaults.json").read_text())["required_lenses"]["deterministic"]
        lens = next(lens for lens in lenses if lens["lens"] == "verify")
        self.assertEqual((candidate.VERIFY, candidate.ACTIONS_APP, candidate.VERIFY_WORKFLOW),
                         (lens["check"], lens["app_id"], lens["workflow"]))
        # A check of that name and App that another workflow's job reported, or whose run cannot be read, is no verify.
        two = [{"id": 901, "path": candidate.VERIFY_WORKFLOW, "head_sha": D, "check_suite_id": SUITE},
               {"id": 902, "path": candidate.VERIFY_WORKFLOW, "head_sha": D, "check_suite_id": SUITE}]
        for suite in (verify_suite(path=".github/workflows/other.yml"), verify_suite(commit=A), verify_suite(runs=[]),
                      verify_suite(runs=two), verify_suite(total=2), verify_suite(status=500), verify_suite(runs=["x"]),
                      verify_suite(runs=[{"id": 901, "path": candidate.VERIFY_WORKFLOW, "head_sha": D,
                                          "check_suite_id": SUITE + 1}])):
            with self.subTest(suite=suite["response"]["body"]):
                self.assertFalse(candidate.verified(github.Replay([verify_runs(), suite]), REPO, D))
        # A check a job created under verify's name, in verify.yml's suite, has details that are not its own job's (P-35,
        # decision 0104): nor is one of another run or another check.
        for change in ({"details_url": "https://github.com/%s/runs/77" % REPO}, {"details_url": None}, {"id": 78},
                       {"details_url": "https://github.com/%s/actions/runs/902/job/77" % REPO}):
            with self.subTest(change=change):
                answered = verify_runs()
                answered["response"]["body"]["check_runs"][0].update(change)
                self.assertFalse(candidate.verified(github.Replay([answered, verify_suite()]), REPO, D))
        # A suite id that is no positive integer is none, though a suite of that number would answer as verify's.
        for change, suite in (({"check_suite": None}, []), ({"check_suite": {"id": True}}, [verify_suite(suite=1)]),
                              ({"check_suite": {"id": 0}}, [verify_suite(suite=0)])):
            with self.subTest(change=change):
                answered = verify_runs()
                answered["response"]["body"]["check_runs"][0].update(change)
                self.assertFalse(candidate.verified(github.Replay([answered] + suite), REPO, D))
        # A suite that is not answered is no verify, and is not an error.
        self.assertFalse(candidate.verified(github.Replay([verify_runs()]), REPO, D))
        # An answer that is no 200 is none, whatever its body holds.
        failed = verify_runs()
        failed["response"]["status"] = 500
        self.assertFalse(candidate.verified(github.Replay([failed, verify_suite()]), REPO, D))
        unmerged = compared()
        unmerged[1] = dict(unmerged[1], response=dict(unmerged[1]["response"], status=500))
        self.assertFalse(candidate.on_main(github.Replay(unmerged), REPO, D))

    def test_the_sets_manifest_is_read_only_as_the_file_it_names(self):  # Muse's read of #354
        for change in ({"type": "symlink"}, {"path": "evals/other.json"}, {"encoding": "utf-8"}, {"size": "x"},
                       {"size": candidate.SET_MOST + 1}, {"size": len(SET_BYTES) + 1}):
            with self.subTest(change=change):
                answered = manifest()
                answered["response"]["body"].update(change)
                self.assertEqual(candidate.gate(github.Replay([answered]), REPO, D, VERSION), "eval_set_unreadable")
        failed = manifest(status=500)
        self.assertEqual(candidate.gate(github.Replay([failed]), REPO, D, VERSION), "eval_set_unreadable")
        # A manifest past its bound, though whole and readable, is not read: GitHub inlines no more.
        big = manifest(data=SET_BYTES + b" " * candidate.SET_MOST)
        self.assertEqual(candidate.gate(github.Replay([big] + gate_reads()[1:]), REPO, D, VERSION),
                         "eval_set_unreadable")

    def test_the_eval_gate_is_closed_by_anything_not_read_whole_or_not_passed(self):
        # Ruling 4″: anything but the eval job's own `pass`, for this commit and this Release, keeps the gate closed,
        # and cut.plan reads every such word as eval_gate_closed.
        self.assertEqual(candidate.gate(github.Replay(gate_reads()), REPO, D, VERSION), "pass")
        empty = json.dumps(dict(SET, count=0, cases=[])).encode()
        broken = (
            ([manifest(status=404)], "eval_set_unreadable"),
            ([manifest(data=b"{")], "eval_set_unreadable"),
            ([dict(manifest(), response=dict(manifest()["response"], body=dict(manifest()["response"]["body"],
                                                                              size=len(SET_BYTES) + 1)))],
             "eval_set_unreadable"),
            ([manifest(data=empty)] + [eval_runs()] + report_download(report()), "another_set"),
            ([manifest(), eval_runs(runs=[])], "eval_not_run"),
            ([manifest(), eval_runs(runs=[run_of(head_sha=A)])], "eval_not_run"),
            ([manifest(), eval_runs(runs=[run_of(path=".github/workflows/other.yml")])], "eval_not_run"),
            ([manifest(), eval_runs(total=2)], "eval_not_run"),
            ([manifest(), eval_runs(runs=[run_of(conclusion="failure")])], "eval_not_run"),
            ([manifest(), eval_runs(runs=[run_of(event="push")])], "eval_not_run"),
            # A dispatch whose id is no GitHub id is none, though a run of that number would answer with a report.
            ([manifest(), eval_runs(runs=[run_of(id=0)])] + report_download(report(), run=0), "eval_not_run"),
            ([manifest(), eval_runs(runs=[run_of(id=True)])] + report_download(report(), run=1), "eval_not_run"),
            ([manifest(data=b"[" * 60000)], "eval_set_unreadable"),
            (gate_reads(document="[" * 60000), "report_unreadable"),
            (gate_reads(document=report(release="factory/v0.2.9")), "another_release"),
            (gate_reads(document=report(commit=A)), "another_commit"),
            (gate_reads(document=report(verdict="fail")), "case_failed"),
            # A set short of a kind closes the gate by the report's one word, which says neither count; and so does a
            # report that cannot say, and a run the job failed for it, whatever its report (decision 0109).
            (gate_reads(document=report(split_ok=False)), "eval_split_short"),
            (gate_reads(document=report(split_ok=None)), "eval_split_short"),
            (gate_reads(document={k: v for k, v in report().items() if k != "split_ok"}), "report_unreadable"),
            (gate_reads(document="not json"), "report_unreadable"),
            ([manifest(), eval_runs()], "report_unreadable"),
        )
        for reads, code in broken:
            with self.subTest(code=code):
                said = candidate.gate(github.Replay(reads), REPO, D, VERSION)
                self.assertEqual(said, code)
                self.assertEqual(cut.plan({"command": "cut", "channel": NEXT, "version": VERSION, "commit": D}, REFS,
                                          {"commit": D, "on_main": True, "verified": True, "gate": said,
                                           "release": VERSION}, frozenset({NEXT})), ([], cut.EVAL_GATE_CLOSED))
        # Of two dispatches on the commit, the later is read.
        later = [manifest(), eval_runs(runs=[run_of(id=1, run_number=3), run_of(run_number=9)])] + report_download(report())
        self.assertEqual(candidate.gate(github.Replay(later), REPO, D, VERSION), "pass")
        # A commit or a repo that is not one asks nothing, and closes the gate.
        for commit, repo in (("main", REPO), (D.upper(), REPO), (D, "combsmith/.."), (None, REPO)):
            with self.subTest(commit=commit, repo=repo):
                facts = candidate.facts(github.Replay([]), repo, commit, VERSION)
                self.assertEqual((facts["on_main"], facts["verified"], facts["gate"]), (False, False, "report_unreadable"))


class Writes(unittest.TestCase):
    def test_a_release_is_created_and_a_channel_created_once_then_moved_with_force(self):
        made = {"ref": "refs/tags/" + VERSION, "object": {"sha": D, "type": "commit"}}
        self.assertTrue(tags.write(github.Replay([ex("POST", "/repos/%s/git/refs" % REPO, 201, made,
                                                     sent={"ref": "refs/tags/" + VERSION, "sha": D})]),
                                   REPO, ("create", VERSION, D), REFS))
        moved = {"ref": "refs/tags/" + NEXT, "object": {"sha": D, "type": "commit"}}
        self.assertTrue(tags.write(github.Replay([ex("PATCH", "/repos/%s/git/refs/tags/%s" % (REPO, NEXT), 200, moved,
                                                     sent={"sha": D, "force": True})]),
                                   REPO, ("move", NEXT, D), REFS))
        self.assertTrue(tags.write(github.Replay([ex("POST", "/repos/%s/git/refs" % REPO, 201, moved,
                                                     sent={"ref": "refs/tags/" + NEXT, "sha": D})]),
                                   REPO, ("move", NEXT, D), {}))
        # Nothing is sent for a Release that exists, a Release moved, a Channel created as a Release, or a name of
        # neither; and an answer not of the ref and commit asked is no write.
        for planned, refs in ((("create", "factory/v0.1.0", D), REFS), (("move", "factory/v0.1.0", D), REFS),
                              (("move", "factory/v0-stable", D), REFS), (("move", "factory/v0-stable", D), {}),
                              (("create", NEXT, D), {}), (("create", "factory/x", D), {}), (("delete", NEXT, D), REFS),
                              (("move", NEXT, "main"), REFS), (("move", NEXT), REFS), (("move", NEXT, D), None)):
            with self.subTest(planned=planned):
                asked = []

                class Anything:
                    def send(self, req):
                        asked.append(req)
                        return {"status": 201, "headers": {}, "body": {"ref": "refs/tags/" + str(planned[1]),
                                                                       "object": {"sha": D}}}
                self.assertFalse(tags.write(Anything(), REPO, planned, refs))
                self.assertEqual(asked, [])
        for status, body in ((422, {"message": "Reference already exists"}), (201, dict(made, ref="refs/tags/x")),
                             (201, {"ref": "refs/tags/" + VERSION, "object": {"sha": A}})):
            with self.subTest(status=status, body=body):
                self.assertFalse(tags.write(github.Replay([ex("POST", "/repos/%s/git/refs" % REPO, status, body,
                                                              sent={"ref": "refs/tags/" + VERSION, "sha": D})]),
                                            REPO, ("create", VERSION, D), REFS))
        # A repo that could name another path is never asked, whatever GitHub would answer.
        for repo in ("combsmith/..", "combsmith/.", "combsmith", None):
            with self.subTest(repo=repo):
                asked = []

                class Answers:
                    def send(self, req):
                        asked.append(req)
                        return {"status": 201, "headers": {}, "body": {"ref": "refs/tags/" + VERSION, "object": {"sha": D}}}
                self.assertFalse(tags.write(Answers(), repo, ("create", VERSION, D), REFS))
                self.assertEqual(asked, [])

    def test_a_deployment_of_next_is_recorded_with_its_status(self):
        sent = {"ref": D, "task": "deploy", "auto_merge": False, "required_contexts": [], "environment": "factory-next",
                "description": VERSION, "transient_environment": False, "production_environment": False}
        made = ex("POST", "/repos/%s/deployments" % REPO, 201, {"id": 77, "sha": D, "environment": "factory-next"},
                  sent=sent)
        status = ex("POST", "/repos/%s/deployments/77/statuses" % REPO, 201, {"state": "success"},
                    sent={"state": "success", "environment": "factory-next"})
        self.assertEqual(deployments.record(github.Replay([made, status]), REPO, D, VERSION), 77)
        for answers in ([dict(made, response=dict(made["response"], status=202))], [made],
                        [dict(made, response=dict(made["response"], status=202)), status],
                        [dict(made, response=dict(made["response"], body={"id": 77, "sha": A,
                                                                           "environment": "factory-next"})), status],
                        [made, dict(status, response=dict(status["response"], body={"state": "failure"}))],
                        [dict(made, response=dict(made["response"], body={"id": 77, "sha": D, "environment": "other"})),
                         status],
                        [dict(made, response=dict(made["response"], body={"id": 0, "sha": D,
                                                                           "environment": "factory-next"})),
                         dict(status, request=dict(status["request"],
                                                   call="POST /repos/%s/deployments/0/statuses" % REPO))],
                        [dict(made, response=dict(made["response"], body={"id": True, "sha": D,
                                                                           "environment": "factory-next"})),
                         dict(status, request=dict(status["request"],
                                                   call="POST /repos/%s/deployments/1/statuses" % REPO))],
                        [made, dict(status, response=dict(status["response"], status=200))]):
            with self.subTest(answers=len(answers)):
                self.assertIsNone(deployments.record(github.Replay(answers), REPO, D, VERSION))


def cut_reads(document=None, version=VERSION):
    """Every exchange of a cut of version at D, from the first read of the tags to the Deployment."""
    after_create = dict(REFS, **{version: D})
    after_move = dict(after_create, **{NEXT: D})
    return ([refs_read(REFS)] + facts_reads(D, document if document is not None else report(release=version))
            + [ex("POST", "/repos/%s/git/refs" % REPO, 201, {"ref": "refs/tags/" + version, "object": {"sha": D}},
                  sent={"ref": "refs/tags/" + version, "sha": D}), refs_read(after_create), refs_read(after_create),
               ex("PATCH", "/repos/%s/git/refs/tags/%s" % (REPO, NEXT), 200,
                  {"ref": "refs/tags/" + NEXT, "object": {"sha": D}}, sent={"sha": D, "force": True}),
               refs_read(after_move),
               ex("POST", "/repos/%s/deployments" % REPO, 201, {"id": 77, "sha": D, "environment": "factory-next"},
                  sent={"ref": D, "task": "deploy", "auto_merge": False, "required_contexts": [],
                        "environment": "factory-next", "description": version, "transient_environment": False,
                        "production_environment": False}),
               ex("POST", "/repos/%s/deployments/77/statuses" % REPO, 201, {"state": "success"},
                  sent={"state": "success", "environment": "factory-next"})])


class Failing:
    def send(self, req):
        raise RecursionError("what GitHub answered")


class Step(unittest.TestCase):
    def run_step(self, environ, answers):
        replay, tokens = github.Replay(answers), []
        self.asked = []
        asked = self.asked

        class Kept:
            _left = property(lambda _: replay._left)

            def send(self, req):
                asked.append("%s %s" % (req["method"], req["path"]))
                return replay.send(req)

        def connect(token):
            tokens.append(token)
            return Kept()
        done, code = move.run(environ, connect)
        return done, code, tokens, replay

    def test_a_cut_creates_the_release_moves_next_reads_each_back_and_records_the_deployment(self):
        env = {"RELEASE_COMMAND": "cut", "RELEASE_VERSION": VERSION, "RELEASE_CUT_COMMIT": D, "RELEASE_TOKEN": "the token"}
        done, code, tokens, replay = self.run_step(env, cut_reads())
        self.assertEqual((done, code, tokens), ({"writes": [["create", VERSION, D], ["move", NEXT, D]],
                                                 "deployments": [77]}, None, ["the token"]))
        self.assertEqual(replay._left, [])

    def test_a_cut_asked_with_no_version_is_of_the_next_patch(self):
        # The schedule's cut names no version: it is the next patch of next's major, judged by the gate as that one.
        env = {"RELEASE_COMMAND": "cut", "RELEASE_VERSION": "", "RELEASE_CUT_COMMIT": D, "RELEASE_TOKEN": "t"}
        done, code, _, replay = self.run_step(env, cut_reads(version="factory/v0.2.1"))
        self.assertEqual((done["writes"], code, replay._left),
                         ([["create", "factory/v0.2.1", D], ["move", NEXT, D]], None, []))

    def test_a_closed_gate_writes_nothing(self):
        env = {"RELEASE_COMMAND": "cut", "RELEASE_VERSION": VERSION, "RELEASE_CUT_COMMIT": D, "RELEASE_TOKEN": "t"}
        reads = [refs_read(REFS)] + facts_reads(D, report(verdict="fail"))
        done, code, _, replay = self.run_step(env, reads)
        self.assertEqual((done, code, replay._left), ({"writes": [], "deployments": []}, cut.EVAL_GATE_CLOSED, []))

    def test_a_write_not_read_back_stops_the_step_there(self):
        env = {"RELEASE_COMMAND": "cut", "RELEASE_VERSION": VERSION, "RELEASE_CUT_COMMIT": D, "RELEASE_TOKEN": "t"}
        answers = cut_reads()
        unchanged = answers.index(refs_read(dict(REFS, **{VERSION: D})))
        answers[unchanged] = refs_read(REFS)
        done, code, _, _ = self.run_step(env, answers[:unchanged + 1] + [refs_read(REFS)])
        self.assertEqual((done, code), ({"writes": [], "deployments": [], "sent": ["create", VERSION, D]},
                                        "not_read_back"))
        # A read that had not caught up is read once more, and the step goes on.
        caught = answers[:unchanged + 1] + cut_reads()[unchanged:]
        done, code, _, _ = self.run_step(env, caught)
        self.assertEqual((done["writes"], code), ([["create", VERSION, D], ["move", NEXT, D]], None))
        # A Release read back on a commit another Release also names is not read back as the one planned.
        twice = cut_reads()[:unchanged] + [refs_read(dict(REFS, **{VERSION: D, "factory/v0.3.1": D}))] * 2
        done, code, _, _ = self.run_step(env, twice)
        self.assertEqual(code, "not_read_back")
        refused = copy.deepcopy(cut_reads())
        refused[refused.index(refs_read(dict(REFS, **{VERSION: D}))) - 1]["response"]["status"] = 422
        done, code, _, _ = self.run_step(env, refused[:len(facts_reads()) + 2])
        self.assertEqual((done, code), ({"writes": [], "deployments": []}, "write_unanswered"))
        undeployed = cut_reads()[:-1]
        undeployed[-1] = dict(undeployed[-1], response=dict(undeployed[-1]["response"], status=500))
        done, code, _, _ = self.run_step(env, undeployed)
        self.assertEqual((done["writes"], code), ([["create", VERSION, D], ["move", NEXT, D]], "deployment_unrecorded"))

    def test_next_moved_since_the_plan_stops_the_step_before_it_moves(self):  # decision 0080
        # Just before next is moved its tag is read again: moved since the plan by a step beside it or a person, the
        # step stops, channel_moved, and moves nothing; the Release a cut created stays, read back.
        env = {"RELEASE_COMMAND": "cut", "RELEASE_VERSION": VERSION, "RELEASE_CUT_COMMIT": D, "RELEASE_TOKEN": "t"}
        answers = cut_reads()
        recheck = answers.index(refs_read(dict(REFS, **{VERSION: D}))) + 1
        moved = answers[:recheck] + [refs_read(dict(REFS, **{VERSION: D, NEXT: A}))]
        done, code, _, replay = self.run_step(env, moved)
        self.assertEqual((done, code, replay._left), ({"writes": [["create", VERSION, D]], "deployments": []},
                                                      "channel_moved", []))
        # Moved before the created Release was read back: the read-back and the read before the move both show it,
        # and next is held to where the plan read it, not to the read-back (the Claude review of #379).
        early = dict(REFS, **{VERSION: D, NEXT: A})
        done, code, _, _ = self.run_step(env, answers[:recheck - 1] + [refs_read(early), refs_read(early)])
        self.assertEqual((done["writes"], code), ([["create", VERSION, D]], "channel_moved"))
        unread = answers[:recheck] + [refs_read(REFS, status=500)]
        self.assertEqual(self.run_step(env, unread)[1], "refs_unreadable")
        rollback = {"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": "t", "RELEASE_TO": "factory/v0.1.0"}
        done, code, _, _ = self.run_step(rollback, [refs_read(REFS), refs_read(dict(REFS, **{NEXT: D}))])
        self.assertEqual((done["writes"], code), ([], "channel_moved"))

    def test_a_channel_not_on_its_commit_after_the_move_is_not_read_back(self):  # Muse's read of #354
        # The PATCH answered, yet next still names the commit it was on: the Release moved to is read on its own tag,
        # but the Channel is not on it, so the move is not read back.
        env = {"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": "t", "RELEASE_TO": "factory/v0.1.0"}
        answers = [refs_read(REFS), refs_read(REFS),
                   ex("PATCH", "/repos/%s/git/refs/tags/%s" % (REPO, NEXT), 200,
                      {"ref": "refs/tags/" + NEXT, "object": {"sha": A}}, sent={"sha": A, "force": True}),
                   refs_read(REFS), refs_read(REFS)]
        done, code, _, _ = self.run_step(env, answers)
        self.assertEqual((done["writes"], done.get("sent"), code), ([], ["move", NEXT, A], "not_read_back"))

    def test_the_step_runs_with_no_argument_as_the_workflow_calls_it(self):  # Muse's read of #358
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = move.main([], environ={"RELEASE_COMMAND": "cut", "RELEASE_VERSION": VERSION,
                                          "RELEASE_CUT_COMMIT": D, "RELEASE_TOKEN": "the token"},
                             connect=lambda token: github.Replay(cut_reads()))
        self.assertEqual((code, json.loads(out.getvalue())),
                         (0, {"writes": [["create", VERSION, D], ["move", NEXT, D]], "deployments": [77]}))
        # Any other argument is no step.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(move.main(["move"], environ={}), 2)
        self.assertIn("usage", err.getvalue())

    def test_a_rollback_reads_no_fact_and_moves_next_back(self):
        env = {"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": "t", "RELEASE_TO": "factory/v0.1.0"}
        back = dict(REFS, **{NEXT: A})
        answers = [refs_read(REFS), refs_read(REFS),
                   ex("PATCH", "/repos/%s/git/refs/tags/%s" % (REPO, NEXT), 200,
                      {"ref": "refs/tags/" + NEXT, "object": {"sha": A}}, sent={"sha": A, "force": True}),
                   refs_read(back),
                   ex("POST", "/repos/%s/deployments" % REPO, 201, {"id": 78, "sha": A, "environment": "factory-next"},
                      sent={"ref": A, "task": "deploy", "auto_merge": False, "required_contexts": [],
                            "environment": "factory-next", "description": "factory/v0.1.0",
                            "transient_environment": False, "production_environment": False}),
                   ex("POST", "/repos/%s/deployments/78/statuses" % REPO, 201, {"state": "success"},
                      sent={"state": "success", "environment": "factory-next"})]
        done, code, _, replay = self.run_step(env, answers)
        self.assertEqual((done, code, replay._left), ({"writes": [["move", NEXT, A]], "deployments": [78]}, None, []))
        self.assertEqual(len(self.asked), len(answers), "a rollback asks nothing of the commit it moves to")

    def test_a_move_forward_reads_the_facts_of_the_release_it_moves_to(self):
        # Forward to an existing Release, through the gate judged for that Release at its commit (ruling 9′'s step 5).
        env = {"RELEASE_COMMAND": "move", "RELEASE_TO": "factory/v0.2.0", "RELEASE_TOKEN": "t"}
        refs = dict(REFS, **{NEXT: A})
        forward = dict(refs, **{NEXT: B})
        answers = ([refs_read(refs)] + facts_reads(B, report(commit=B, release="factory/v0.2.0"))
                   + [refs_read(refs), ex("PATCH", "/repos/%s/git/refs/tags/%s" % (REPO, NEXT), 200,
                         {"ref": "refs/tags/" + NEXT, "object": {"sha": B}}, sent={"sha": B, "force": True}),
                      refs_read(forward),
                      ex("POST", "/repos/%s/deployments" % REPO, 201, {"id": 79, "sha": B, "environment": "factory-next"},
                         sent={"ref": B, "task": "deploy", "auto_merge": False, "required_contexts": [],
                               "environment": "factory-next", "description": "factory/v0.2.0",
                               "transient_environment": False, "production_environment": False}),
                      ex("POST", "/repos/%s/deployments/79/statuses" % REPO, 201, {"state": "success"},
                         sent={"state": "success", "environment": "factory-next"})])
        done, code, _, replay = self.run_step(env, answers)
        self.assertEqual((done, code, replay._left), ({"writes": [["move", NEXT, B]], "deployments": [79]}, None, []))
        # The gate judged for another Release than the one moved to keeps it shut.
        shut = [refs_read(refs)] + facts_reads(B, report(commit=B, release=VERSION))
        done, code, _, _ = self.run_step(env, shut)
        self.assertEqual((done["writes"], code), ([], cut.EVAL_GATE_CLOSED))

    def test_a_step_that_cannot_be_read_asks_nothing(self):
        for env, code in (({"RELEASE_COMMAND": "delete", "RELEASE_TOKEN": "t"}, cut.STEP_UNREADABLE),
                          ({"RELEASE_COMMAND": "rollback"}, "token_unreadable"),
                          ({"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": ""}, "token_unreadable")):
            with self.subTest(env=env):
                done, said, tokens, _ = self.run_step(env, [])
                self.assertEqual((said, tokens), (code, []))
        done, said, _, _ = self.run_step({"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": "t"},
                                         [refs_read(REFS, status=500)])
        self.assertEqual(said, "refs_unreadable")
        # A token the transport refuses asks nothing.
        refused = move.run({"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": "bad token"},
                           lambda token: github.Live(token))
        self.assertEqual(refused, ({"writes": [], "deployments": []}, "token_unreadable"))
        # The ring file and the home come from the Release's own data; with neither, nothing is asked.
        self.assertEqual(move.run({"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": "t"}, None, rings={}),
                         ({"writes": [], "deployments": []}, cut.STEP_UNREADABLE))
        self.assertEqual(move.run({"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": "t"}, None, controller={}),
                         ({"writes": [], "deployments": []}, cut.STEP_UNREADABLE))
        # A home that is no object names neither the repo nor the branch: the step stops there, for every command, and
        # reads no default for either (Argon's read of #354).
        for bad in ("combsmith/software-factory", ["combsmith/software-factory"], 1, True, {"repo": 1, "branch": "main"},
                    {"branch": "main"}, {"repo": REPO, "branch": 1}, {"repo": REPO, "branch": ""}, {"repo": REPO}):
            for command in ("cut", "move", "rollback"):
                with self.subTest(home=bad, command=command):
                    env = {"RELEASE_COMMAND": command, "RELEASE_TOKEN": "t", "RELEASE_CUT_COMMIT": D,
                           "RELEASE_TO": VERSION}
                    self.assertEqual(move.run(env, None, controller={"home": bad}),
                                     ({"writes": [], "deployments": []}, cut.STEP_UNREADABLE))

    def test_the_step_prints_codes_alone_and_exits_by_them(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = move.main(["step"], environ={"RELEASE_COMMAND": "cut", "RELEASE_VERSION": VERSION,
                                                "RELEASE_CUT_COMMIT": D, "RELEASE_TOKEN": "the token"},
                             connect=lambda token: github.Replay(cut_reads()))
        self.assertEqual((code, json.loads(out.getvalue())),
                         (0, {"writes": [["create", VERSION, D], ["move", NEXT, D]], "deployments": [77]}))
        self.assertNotIn("the token", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = move.main(["step"], environ={"RELEASE_COMMAND": "rollback"}, connect=lambda token: None)
        self.assertEqual((code, json.loads(out.getvalue())["refused"]), (1, "token_unreadable"))
        # Whatever else stops the step prints one code and no traceback; a ring file that cannot be read moves nothing.
        out = io.StringIO()

        def broken(token):
            raise RecursionError("what GitHub answered")
        with contextlib.redirect_stdout(out):
            code = move.main(["step"], environ={"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": "t"},
                             connect=lambda token: Failing())
        self.assertEqual((code, json.loads(out.getvalue())), (1, {"writes": [], "deployments": [],
                                                                  "refused": "step_failed"}))
        self.assertNotIn("what GitHub answered", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = move.main(["step"], rings=pathlib.Path("/nonexistent/rings.json"),
                             environ={"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": "t"}, connect=broken)
        self.assertEqual((code, json.loads(out.getvalue())["refused"]), (1, cut.STEP_UNREADABLE))


if __name__ == "__main__":
    unittest.main()
