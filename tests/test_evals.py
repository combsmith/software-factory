"""The review Intent's held-out eval set: what this repo holds of it, and how a Result is scored against a case.

The cases live in the private home and never here (design §3.13); a synthetic case, made in the test, stands in."""
from __future__ import annotations

import copy
import io
import json
import pathlib
import unittest
from unittest import mock

from tests.support import pending
from tools import check_examples, eval_result, walk
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SET = ROOT / "evals" / "pr-review" / "cases.json"


def load(rel: str):
    return json.loads((ROOT / rel).read_text())


class Scoring(unittest.TestCase):
    def test_a_result_that_raises_the_expected_finding_passes_and_one_that_does_not_fails(self):
        case, result = load("examples/eval-case.json"), load("examples/result.json")
        self.assertEqual(eval_result.score(case, result), {"case": case["id"], "verdict": "pass", "reasons": []})
        # A Result that raised nothing, one that raised it against another criterion, in another category, at another
        # severity, in another file, or that covered the criterion as met: each is a fail that says why.
        wrong = copy.deepcopy(result)
        wrong["findings"] = []
        wrong["coverage"][2]["verdict"] = "met"
        self.assertEqual(eval_result.score(case, wrong)["reasons"], ["finding_not_raised", "coverage_disagrees"])
        for field, value, reason in (("category", "architecture", "category_differs"), ("severity", "minor", "severity_differs"),
                                     ("location", {"path": "kernel/gate.py"}, "location_differs"),
                                     ("location", {"path": "kernel/decide.py", "start_line": 1, "end_line": 85}, "location_differs")):
            wrong = copy.deepcopy(result)
            wrong["findings"][0][field] = value
            self.assertEqual(eval_result.score(case, wrong), {"case": case["id"], "verdict": "fail", "reasons": [reason]}, reason)
        # A location given without lines is the whole file; one with lines must overlap the expected ones.
        whole = copy.deepcopy(result)
        whole["findings"][0]["location"] = {"path": "kernel/decide.py"}
        self.assertEqual(eval_result.score(case, whole)["verdict"], "pass")
        edge = copy.deepcopy(result)
        edge["findings"][0]["location"] = {"path": "kernel/decide.py", "start_line": 94, "end_line": 120}
        self.assertEqual(eval_result.score(case, edge)["verdict"], "pass")
        # A Result that did not complete is no review, whatever it raised.
        unfinished = copy.deepcopy(result)
        unfinished["status"], unfinished["reason"] = "incomplete", "turns_exhausted"
        self.assertEqual(eval_result.score(case, unfinished)["reasons"], ["result_not_completed"])

    def test_a_right_change_is_scored_by_its_coverage(self):
        case, result = load("examples/eval-case.met.json"), load("examples/result.json")
        self.assertEqual(eval_result.score(case, result)["verdict"], "pass")
        # The other side: a Finding raised against a criterion the change met, or the criterion left uncovered.
        wrong = copy.deepcopy(result)
        wrong["findings"][0]["criterion"] = "PR-1"
        wrong["coverage"][0]["verdict"] = "finding"
        self.assertEqual(eval_result.score(case, wrong)["reasons"], ["finding_raised_wrongly", "criterion_not_met"])
        wrong = copy.deepcopy(result)
        del wrong["coverage"][0]
        self.assertEqual(eval_result.score(case, wrong)["reasons"], ["criterion_not_met"])

    def test_a_case_or_a_result_that_cannot_be_read_scores_nothing(self):
        case, result = load("examples/eval-case.json"), load("examples/result.json")
        for broken in ({}, dict(case, expected=None), dict(case, diff=None), "a case", None):
            self.assertEqual(eval_result.score(broken, result)["verdict"], "unreadable", broken)
        for broken in ({}, dict(result, status="done"), dict(result, findings=[{"ref": "n1"}])):
            self.assertEqual(eval_result.score(case, broken)["verdict"], "unreadable", broken)
        # An answer that disagrees with its verdict: a Finding expected and none given, or one given where met.
        disagrees = copy.deepcopy(case)
        disagrees["expected"]["finding"] = None
        self.assertEqual(eval_result.score(disagrees, result)["reasons"], ["answer_disagrees_with_verdict"])
        met = load("examples/eval-case.met.json")
        met["expected"]["finding"] = case["expected"]["finding"]
        self.assertEqual(eval_result.score(met, result)["reasons"], ["answer_disagrees_with_verdict"])

    def test_the_front_door_scores_two_files_and_says_so_in_its_exit(self):
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            self.assertEqual(eval_result.main([str(ROOT / "examples" / "eval-case.json"), str(ROOT / "examples" / "result.json")]), 0)
        self.assertEqual(json.loads(out.getvalue())["verdict"], "pass")
        with mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(eval_result.main([str(ROOT / "examples" / "eval-case.met.json"),
                                               str(ROOT / "examples" / "result.failed.json")]), 1)
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(eval_result.main([str(ROOT / "examples" / "eval-case.json"), str(ROOT / "nothing.json")]), 2)
            self.assertEqual(eval_result.main([str(ROOT / "examples" / "eval-case.json")]), 2)


class TheSet(unittest.TestCase):
    def test_the_manifest_counts_its_cases_and_holds_no_case(self):
        # Only each case's id and hash are here: the count is the list's length, and no file under evals/ is a case.
        known = eval_result.schemas()
        manifest = json.loads(SET.read_text())
        self.assertEqual(validate(manifest, known["eval-set"], schemas=known), [])
        self.assertEqual((manifest["role"], manifest["intent"]), ("pr-review", "review-change"))
        self.assertEqual(manifest["count"], len(manifest["cases"]))
        self.assertEqual(len({c["id"] for c in manifest["cases"]}), len(manifest["cases"]))
        for path in walk.files(ROOT, "evals"):
            if path.suffix != ".json":
                continue
            text = path.read_text()
            self.assertNotIn('"diff"', text, path)
            self.assertNotIn("eval-case/1", text, path)
            self.assertEqual(validate(json.loads(text), known["eval-set"], schemas=known), [], path)
        self.assertIn("evals/pr-review/cases.json", check_examples.LIVE)
        # The example manifest is held the same way: a count that disagrees with the list is caught.
        example = load("examples/eval-set.json")
        self.assertEqual(example["count"], len(example["cases"]))

    @pending
    def test_the_review_intents_eval_set_has_its_cases(self):
        # Decision 0010: an Intent family is cut over only after its eval set exists. The cases are written in the
        # private home by a session opened there, and this manifest then carries their hashes (issue 183).
        manifest = json.loads(SET.read_text())
        self.assertGreaterEqual(manifest["count"], 20)

    @pending
    def test_a_fresh_agent_given_the_repo_adds_a_rule_and_passes_the_check(self):
        # Decision 0013 and docs/context-engineering.md: the context's test, which issue 8 runs once evals/ exists.
        self.fail("not run yet")


if __name__ == "__main__":
    unittest.main()
