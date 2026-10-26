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


def ex(method, path, status, body, sent=None, headers=None, via="rest"):
    return {"request": {"via": via, "call": "%s %s" % (method, path), "headers": {}, "body": sent},
            "response": {"status": status, "headers": headers or {}, "body": body}}


def refs_read(refs, status=200):
    body = [{"ref": "refs/tags/" + name, "object": {"sha": sha, "type": "commit"}} for name, sha in sorted(refs.items())]
    return ex("GET", tags.path(REPO), status, body)


def report(commit=D, release=VERSION, verdict="pass", **change):
    document = {"schema": "eval-report/1", "release": release, "commit": commit, "role": SET["role"],
                "intent": SET["intent"], "set": {"count": SET["count"], "sha256": hashlib.sha256(SET_BYTES).hexdigest()},
                "cases": [dict(SET["cases"][0], verdict=verdict, reasons=[])], "passed": 1 if verdict == "pass" else 0}
    document.update(change)
    return document


def zipped(document) -> bytes:
    held = io.BytesIO()
    with zipfile.ZipFile(held, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(candidate.MEMBER, document if isinstance(document, str) else json.dumps(document))
    return held.getvalue()


def compared(commit=D, status="ahead"):
    return ex("GET", "/repos/%s/compare/%s...main" % (REPO, commit), 200,
              {"status": status, "merge_base_commit": {"sha": commit}})


def verify_runs(commit=D, conclusion="success", app=candidate.ACTIONS_APP, more=()):
    runs = [{"name": "verify", "head_sha": commit, "status": "completed", "conclusion": conclusion, "app": {"id": app}}]
    runs += list(more)
    return ex("GET", "/repos/%s/commits/%s/check-runs?check_name=verify&filter=latest&per_page=100" % (REPO, commit),
              200, {"total_count": len(runs), "check_runs": runs})


def manifest(commit=D, data=SET_BYTES, status=200):
    return ex("GET", "/repos/%s/contents/%s?ref=%s" % (REPO, candidate.SET, commit), status,
              {"type": "file", "path": candidate.SET, "encoding": "base64", "size": len(data),
               "content": base64.b64encode(data).decode()})


def eval_runs(commit=D, runs=None):
    runs = [{"id": EVAL_RUN, "run_number": 7, "head_sha": commit, "conclusion": "success",
             "path": ".github/workflows/eval.yml"}] if runs is None else runs
    return ex("GET", "/repos/%s/actions/workflows/eval.yml/runs?head_sha=%s&event=workflow_dispatch&status=success"
                     "&per_page=100" % (REPO, commit), 200, {"total_count": len(runs), "workflow_runs": runs})


def report_download(document, ident=9):
    data = zipped(document)
    return [ex("GET", "/repos/%s/actions/runs/%d/artifacts?name=eval-report&per_page=100" % (REPO, EVAL_RUN), 200,
               {"total_count": 1, "artifacts": [{"id": ident, "name": "eval-report", "expired": False,
                                                 "size_in_bytes": len(data),
                                                 "digest": "sha256:" + hashlib.sha256(data).hexdigest()}]}),
            ex("GET", "/repos/%s/actions/artifacts/%d/zip" % (REPO, ident), 302, None, headers={"location": STORE}),
            ex("GET", STORE, 200, data.decode("utf-8", errors="surrogateescape"), via="storage")]


def gate_reads(commit=D, document=None):
    return [manifest(commit), eval_runs(commit)] + report_download(report(commit) if document is None else document)


def facts_reads(commit=D, document=None):
    return [compared(commit), verify_runs(commit)] + gate_reads(commit, document)


class Candidate(unittest.TestCase):
    def test_the_facts_of_a_commit_on_main_verified_and_judged(self):
        facts = candidate.facts(github.Replay(facts_reads()), REPO, D, VERSION)
        self.assertEqual(facts, {"commit": D, "on_main": True, "verified": True, "gate": "pass", "release": VERSION})
        self.assertTrue(candidate.on_main(github.Replay([compared(status="identical")]), REPO, D))
        for odd in (compared(status="diverged"), compared(status="behind"),
                    ex("GET", "/repos/%s/compare/%s...main" % (REPO, D), 200, {"status": "ahead",
                                                                               "merge_base_commit": {"sha": A}}),
                    ex("GET", "/repos/%s/compare/%s...main" % (REPO, D), 404, {"message": "Not Found"})):
            with self.subTest(compare=odd["response"]):
                self.assertFalse(candidate.on_main(github.Replay([odd]), REPO, D))
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
                self.assertFalse(candidate.verified(github.Replay([odd]), REPO, D))
        self.assertFalse(candidate.verified(github.Replay([]), REPO, D))
        self.assertTrue(candidate.verified(github.Replay([verify_runs()]), REPO, D))

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
            ([manifest(), eval_runs(runs=[{"id": EVAL_RUN, "run_number": 7, "head_sha": A, "conclusion": "success",
                                            "path": ".github/workflows/eval.yml"}])], "eval_not_run"),
            ([manifest(), eval_runs(runs=[{"id": EVAL_RUN, "run_number": 7, "head_sha": D, "conclusion": "success",
                                            "path": ".github/workflows/other.yml"}])], "eval_not_run"),
            (gate_reads(document=report(release="factory/v0.2.9")), "another_release"),
            (gate_reads(document=report(commit=A)), "another_commit"),
            (gate_reads(document=report(verdict="fail")), "case_failed"),
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
        self.assertFalse(tags.write(github.Replay([]), "combsmith/..", ("create", VERSION, D), REFS))

    def test_a_deployment_of_next_is_recorded_with_its_status(self):
        sent = {"ref": D, "task": "deploy", "auto_merge": False, "required_contexts": [], "environment": "factory-next",
                "description": VERSION, "transient_environment": False, "production_environment": False}
        made = ex("POST", "/repos/%s/deployments" % REPO, 201, {"id": 77, "sha": D, "environment": "factory-next"},
                  sent=sent)
        status = ex("POST", "/repos/%s/deployments/77/statuses" % REPO, 201, {"state": "success"},
                    sent={"state": "success", "environment": "factory-next"})
        self.assertEqual(deployments.record(github.Replay([made, status]), REPO, D, VERSION), 77)
        for answers in ([dict(made, response=dict(made["response"], status=202))], [made],
                        [dict(made, response=dict(made["response"], body={"id": 77, "sha": A,
                                                                           "environment": "factory-next"})), status],
                        [made, dict(status, response=dict(status["response"], body={"state": "failure"}))]):
            with self.subTest(answers=len(answers)):
                self.assertIsNone(deployments.record(github.Replay(answers), REPO, D, VERSION))


def cut_reads(document=None):
    """Every exchange of a cut of VERSION at D, from the first read of the tags to the Deployment."""
    after_create = dict(REFS, **{VERSION: D})
    after_move = dict(after_create, **{NEXT: D})
    return ([refs_read(REFS)] + facts_reads(D, document)
            + [ex("POST", "/repos/%s/git/refs" % REPO, 201, {"ref": "refs/tags/" + VERSION, "object": {"sha": D}},
                  sent={"ref": "refs/tags/" + VERSION, "sha": D}), refs_read(after_create),
               ex("PATCH", "/repos/%s/git/refs/tags/%s" % (REPO, NEXT), 200,
                  {"ref": "refs/tags/" + NEXT, "object": {"sha": D}}, sent={"sha": D, "force": True}),
               refs_read(after_move),
               ex("POST", "/repos/%s/deployments" % REPO, 201, {"id": 77, "sha": D, "environment": "factory-next"},
                  sent={"ref": D, "task": "deploy", "auto_merge": False, "required_contexts": [],
                        "environment": "factory-next", "description": VERSION, "transient_environment": False,
                        "production_environment": False}),
               ex("POST", "/repos/%s/deployments/77/statuses" % REPO, 201, {"state": "success"},
                  sent={"state": "success", "environment": "factory-next"})])


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
        env = {"RELEASE_COMMAND": "cut", "RELEASE_VERSION": VERSION, "RELEASE_COMMIT": D, "RELEASE_TOKEN": "the token"}
        done, code, tokens, replay = self.run_step(env, cut_reads())
        self.assertEqual((done, code, tokens), ({"writes": [["create", VERSION, D], ["move", NEXT, D]],
                                                 "deployments": [77]}, None, ["the token"]))
        self.assertEqual(replay._left, [])

    def test_a_closed_gate_writes_nothing(self):
        env = {"RELEASE_COMMAND": "cut", "RELEASE_VERSION": VERSION, "RELEASE_COMMIT": D, "RELEASE_TOKEN": "t"}
        reads = [refs_read(REFS)] + facts_reads(D, report(verdict="fail"))
        done, code, _, replay = self.run_step(env, reads)
        self.assertEqual((done, code, replay._left), ({"writes": [], "deployments": []}, cut.EVAL_GATE_CLOSED, []))

    def test_a_write_not_read_back_stops_the_step_there(self):
        env = {"RELEASE_COMMAND": "cut", "RELEASE_VERSION": VERSION, "RELEASE_COMMIT": D, "RELEASE_TOKEN": "t"}
        answers = cut_reads()
        unchanged = answers.index(refs_read(dict(REFS, **{VERSION: D})))
        answers[unchanged] = refs_read(REFS)
        done, code, _, _ = self.run_step(env, answers[:unchanged + 1])
        self.assertEqual((done, code), ({"writes": [], "deployments": []}, "not_read_back"))
        refused = copy.deepcopy(cut_reads())
        refused[refused.index(refs_read(dict(REFS, **{VERSION: D}))) - 1]["response"]["status"] = 422
        done, code, _, _ = self.run_step(env, refused[:len(facts_reads()) + 2])
        self.assertEqual((done, code), ({"writes": [], "deployments": []}, "write_unanswered"))
        undeployed = cut_reads()[:-1]
        undeployed[-1] = dict(undeployed[-1], response=dict(undeployed[-1]["response"], status=500))
        done, code, _, _ = self.run_step(env, undeployed)
        self.assertEqual((done["writes"], code), ([["create", VERSION, D], ["move", NEXT, D]], "deployment_unrecorded"))

    def test_a_rollback_reads_no_fact_and_moves_next_back(self):
        env = {"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": "t", "RELEASE_TO": "factory/v0.1.0"}
        back = dict(REFS, **{NEXT: A})
        answers = [refs_read(REFS),
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
        # The ring file and the home come from the Release's own data; with neither, nothing is asked.
        self.assertEqual(move.run({"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": "t"}, None, rings={}),
                         ({"writes": [], "deployments": []}, cut.STEP_UNREADABLE))
        self.assertEqual(move.run({"RELEASE_COMMAND": "rollback", "RELEASE_TOKEN": "t"}, None, controller={}),
                         ({"writes": [], "deployments": []}, cut.STEP_UNREADABLE))

    def test_the_step_prints_codes_alone_and_exits_by_them(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = move.main(["step"], environ={"RELEASE_COMMAND": "cut", "RELEASE_VERSION": VERSION,
                                                "RELEASE_COMMIT": D, "RELEASE_TOKEN": "the token"},
                             connect=lambda token: github.Replay(cut_reads()))
        self.assertEqual((code, json.loads(out.getvalue())),
                         (0, {"writes": [["create", VERSION, D], ["move", NEXT, D]], "deployments": [77]}))
        self.assertNotIn("the token", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = move.main(["step"], environ={"RELEASE_COMMAND": "rollback"}, connect=lambda token: None)
        self.assertEqual((code, json.loads(out.getvalue())["refused"]), (1, "token_unreadable"))


if __name__ == "__main__":
    unittest.main()
