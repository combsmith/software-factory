"""The review Intent's held-out eval set: what this repo holds of it, and how a Result is scored against a case.

The cases live in the private home and never here (design §3.13); a synthetic case, made in the test, stands in."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import pathlib
import re
import shutil
import subprocess
import unittest
from unittest import mock

from tests.support import pending
from tools import check_examples, eval_result, walk
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SET = ROOT / "evals" / "pr-review" / "cases.json"
# The eval job's workflow, the live file, as issue 309's ruling 10 and its first amendment shape it: the planted faults
# below are made from it.
EVAL_WORKFLOW = (ROOT / ".github" / "workflows" / "eval.yml").read_text()
FETCH_STEP = EVAL_WORKFLOW[EVAL_WORKFLOW.index("      - run: python3 -m harness.eval.fetch\n"):
                          EVAL_WORKFLOW.index("      - run: python3 -m harness.eval.run\n")]


def load(rel: str):
    return json.loads((ROOT / rel).read_text())


def example_result() -> dict:
    """The public example Result, posting none of its Findings: the example cases' diff holds no line of the test file
    one is on, and the scorer refuses a Result that posts a Finding off every hunk, as `apply` does (issue 574), which
    would hide what a test scores it for. A test of that rule posts its Findings itself."""
    return dict(load("examples/result.json"), effects={})


class Heads:
    """A transport standing in for the anonymous one `fetch` reads each case's head with: each commit's tarball as
    codeload serves one (P-60), or, for a commit in `refused`, a 404. What it was asked is kept by path."""

    def __init__(self, refused=()):
        self.refused, self.asked = set(refused), []

    def send(self, req: dict) -> dict:
        from adapters import github
        from tests import support
        self.asked.append((req["path"], req.get("follow"), req.get("bound")))
        sha = github.TARBALL.fullmatch(req["path"]).group(3)
        if sha in self.refused:
            return {"status": 404, "headers": {}, "body": "404: Not Found"}
        return {"status": 200, "headers": {}, "body": support.tarball(sha).decode("utf-8", errors="surrogateescape")}


def github_tarred() -> int:
    from adapters import github
    return github.TARRED


def reviewed(env, release, began, call=None, clock=None, heads=None):
    """`harness/eval/run.reviewer`, given a directory of heads, `heads`, a new one unless it is given, whose `<id>`
    stands for the head `fetch` unpacked for each case it is asked (decision 0138, issue 623)."""
    import tempfile
    from harness.eval import run as step
    from tests import test_harness as live
    heads = pathlib.Path(tempfile.mkdtemp()) / "heads" if heads is None else heads
    review = step.reviewer(env, release, began, call, clock if clock is not None else live.Clock(), heads)

    def asking(case):
        if isinstance(case, dict) and isinstance(case.get("id"), str):
            (heads / case["id"]).mkdir(parents=True, exist_ok=True)
        return review(case)
    asking.seen = review.seen
    return asking


class Scoring(unittest.TestCase):
    def test_a_result_that_raises_the_expected_finding_passes_and_one_that_does_not_fails(self):
        case, result = load("examples/eval-case.json"), example_result()
        self.assertEqual(eval_result.score(case, result), {"case": case["id"], "verdict": "pass", "reasons": []})
        # A Result that raised nothing, one that raised it against another criterion, in another category, at another
        # severity, in another file, or that covered the criterion as met: each is a fail that says why.
        wrong = copy.deepcopy(result)
        wrong["findings"] = []
        wrong["coverage"][2]["verdict"] = "met"
        self.assertEqual(eval_result.score(case, wrong)["reasons"], ["finding_not_raised", "coverage_disagrees"])
        for field, value, reason in (("category", "architecture", "category_differs"), ("severity", "minor", "severity_differs"),
                                     ("location", {"path": "kernel/gate.py"}, "location_differs"),
                                     ("location", {"path": "kernel/gate.py", "start_line": 86, "end_line": 94}, "location_differs"),
                                     ("location", {"path": "kernel/decide.py", "start_line": 1, "end_line": 85}, "location_differs")):
            wrong = copy.deepcopy(result)
            wrong["findings"][0][field] = value
            # A gating Finding put elsewhere is counted as one away from the place (issue 610).
            self.assertEqual(eval_result.score(case, wrong), dict({"case": case["id"], "verdict": "fail", "reasons": [reason]},
                                                                  **({"surplus_gating": 1} if field == "location" else {})), reason)
        # A Finding's lines must overlap the expected ones, and span no more than fifteen lines beyond them; one given
        # without lines could be at any place, and is at none (decision 0143). The expected place is 86 to 94, nine lines.
        self.assertEqual(eval_result.SPAN_BEYOND, 15)
        for lines, verdict in (({"start_line": 94, "end_line": 117}, "pass"), ({"start_line": 94, "end_line": 118}, "fail"),
                               ({"start_line": 63, "end_line": 86}, "pass"), ({"start_line": 62, "end_line": 86}, "fail"),
                               ({"start_line": 70, "end_line": 85}, "fail"),
                               ({"start_line": 94}, "pass"), ({}, "fail")):
            edge = copy.deepcopy(result)
            edge["findings"][0]["location"] = dict(lines, path="kernel/decide.py")
            scored = eval_result.score(case, edge)
            self.assertEqual((scored["verdict"], scored["reasons"]), (verdict, [] if verdict == "pass" else ["location_differs"]), lines)
        # A case's place given without lines is the whole file: any Finding there with lines is at it, however wide.
        anywhere = copy.deepcopy(case)
        anywhere["expected"]["finding"]["location"] = {"path": "kernel/decide.py"}
        wide = copy.deepcopy(result)
        wide["findings"][0]["location"] = {"path": "kernel/decide.py", "start_line": 1, "end_line": 900}
        self.assertEqual(eval_result.score(anywhere, wide)["verdict"], "pass")
        wide["findings"][0]["location"] = {"path": "kernel/decide.py"}
        self.assertEqual(eval_result.score(anywhere, wide)["reasons"], ["location_differs"])
        # One Finding must be the expected one in every respect: two that are each right in part are no match, the
        # nearest of them says what it missed, and two at the place are one too many (issue 610).
        split = copy.deepcopy(result)
        split["findings"][0]["severity"] = "minor"
        split["findings"].append(dict(result["findings"][0], ref="n3", category="architecture"))
        self.assertEqual(eval_result.score(case, split)["reasons"], ["severity_differs", "surplus_at_place"])
        split["findings"][0]["location"] = {"path": "kernel/gate.py"}
        self.assertEqual(eval_result.score(case, split)["reasons"], ["category_differs"])
        # Lines are read whole: an end with no start, or before its start, is nowhere in a Result, and unreadable in
        # a case.
        for lines in ({"path": "kernel/decide.py", "end_line": 94}, {"path": "kernel/decide.py", "start_line": 94, "end_line": 86}):
            nowhere = copy.deepcopy(result)
            nowhere["findings"][0]["location"] = lines
            self.assertEqual(eval_result.score(case, nowhere)["reasons"], ["location_differs"], lines)
            unreadable = copy.deepcopy(case)
            unreadable["expected"]["finding"]["location"] = lines
            self.assertEqual(eval_result.score(unreadable, result), {"case": case["id"], "verdict": "unreadable",
                                                                     "reasons": ["location_unreadable"]}, lines)
        # A Result that did not complete is no review, whatever it raised.
        unfinished = copy.deepcopy(result)
        unfinished["status"], unfinished["reason"] = "incomplete", "change_not_reviewed_whole"
        self.assertEqual(eval_result.score(case, unfinished)["reasons"], ["result_not_completed"])

    def test_a_finding_no_finding_cited_says_where_it_went(self):
        # Run 41315433150 read 19 cases as `finding_not_raised`, and could not tell a miss from a Finding raised and not
        # cited. Each of these fails the case alike: only what it says has changed.
        case, right = load("examples/eval-case.json"), example_result()
        self.assertEqual(eval_result.score(case, right)["verdict"], "pass")
        at = right["findings"][0]
        place = at["location"]

        def said(*findings):
            made = [dict(at, **f) for f in findings]
            result = dict(right, findings=[{k: v for k, v in f.items() if k != "location" or v is not None} for f in made])
            scored = eval_result.score(case, result)
            self.assertEqual(scored["verdict"], "fail", findings)
            return [r for r in scored["reasons"] if r != "coverage_disagrees"]
        self.assertEqual(said(dict(criterion=None)), ["finding_uncited"])
        self.assertEqual(said(dict(criterion="PR-1")), ["finding_cites_another"])
        self.assertEqual(said(dict(criterion=None), dict(criterion="PR-1")),
                         ["finding_uncited", "finding_cites_another", "surplus_at_place"])
        # What it has otherwise, of the nearest: the place is its being there.
        self.assertEqual(said(dict(criterion=None, severity="minor")), ["finding_uncited", "severity_differs"])
        self.assertEqual(said(dict(criterion=None, category="security")), ["finding_uncited", "category_differs"])
        self.assertEqual(said(dict(criterion=None, severity="minor"), dict(criterion=None)), ["finding_uncited", "surplus_at_place"])
        self.assertEqual(said(dict(criterion="PR-1", severity="minor")), ["finding_cites_another", "severity_differs"])
        # In the file, on other lines, or with no lines or too many, which is no place (decision 0143); in another
        # file, or none, is not raised.
        away = dict(place, start_line=place["end_line"] + 1, end_line=place["end_line"] + 5)
        self.assertEqual(said(dict(criterion=None, location=away)), ["finding_elsewhere"])
        self.assertEqual(said(dict(criterion=None, location={"path": place["path"]})), ["finding_elsewhere"])
        key = case["expected"]["finding"]["location"]
        wide = dict(key, end_line=key["end_line"] + eval_result.SPAN_BEYOND)
        self.assertEqual(said(dict(criterion=None, location=wide)), ["finding_uncited"])
        self.assertEqual(said(dict(criterion=None, location=dict(wide, end_line=wide["end_line"] + 1))), ["finding_elsewhere"])
        self.assertEqual(said(dict(criterion=None, location={"path": "kernel/gate.py"})), ["finding_not_raised"])
        self.assertEqual(said(), ["finding_not_raised"])
        # A Finding of no location, which result/1 allows, is nowhere; so is one whose lines cannot be read, in the file or not.
        self.assertEqual(said(dict(criterion=None, location=None)), ["finding_not_raised"])
        self.assertEqual(said(dict(location=None)), ["location_differs"])
        for lines in (dict(end_line=2), dict(start_line=9, end_line=2)):
            self.assertEqual(said(dict(criterion=None, location=dict(path=place["path"], **lines))), ["finding_not_raised"])
        # Beside the Finding that cites it, one that holds nothing elsewhere is nothing: the pass rule has not moved. One
        # at the place too is one too many (issue 610).
        extra = dict(at, ref="n9", criterion=None, severity="minor", location=away)
        self.assertEqual(eval_result.score(case, dict(right, findings=[at, extra]))["verdict"], "pass")
        extra["location"] = place
        self.assertEqual(eval_result.score(case, dict(right, findings=[at, extra]))["reasons"], ["surplus_at_place"])

    def test_a_finding_at_any_place_the_case_gives_is_at_the_place(self):  # decision 0143
        # A fault that spans several changed lines is rightly placed on any of them: a case may name up to three such
        # places beside its `location`, in `also_at`, each on lines a hunk of its own diff holds on the head's side. One
        # fault, several places: what else a Finding must be is unchanged.
        case, result = load("examples/eval-case.also-at.json"), example_result()
        first, other = case["expected"]["finding"]["location"], case["expected"]["finding"]["also_at"][0]
        self.assertNotEqual(eval_result._lines(first), eval_result._lines(other))

        def placed(location, **given):
            made = copy.deepcopy(result)
            made["findings"][0].update(dict(given, location=location))
            return made
        # At its `location`, a pass as before; at an alternate place alone, a pass the report can count.
        self.assertEqual(eval_result.score(case, placed(first)), {"case": case["id"], "verdict": "pass", "reasons": []})
        self.assertEqual(eval_result.score(case, placed(other)),
                         {"case": case["id"], "verdict": "pass", "reasons": [], "at_alternate": True})
        # One that overlaps the `location` too is at it.
        self.assertNotIn("at_alternate", eval_result.score(case, placed(dict(other, end_line=other["end_line"] + 40))))
        for location in ({"path": "kernel/gate.py"}, {"path": first["path"]}, dict(first, start_line=89, end_line=94)):
            self.assertEqual(eval_result.score(case, placed(location))["reasons"], ["location_differs"], location)
        self.assertEqual(eval_result.score(case, placed(other, severity="minor"))["reasons"], ["severity_differs"])
        self.assertEqual(eval_result.score(case, placed(other, category="architecture"))["reasons"], ["category_differs"])
        # One fault at two of its places is put twice: a right Finding at the `location` beside one at an alternate place
        # fails, as one at the `location` that is not the expected Finding, or cites no criterion, does; a fail is never
        # marked (issue 610).
        both = placed(other)
        both["findings"].append(dict(both["findings"][0], ref="n9", location=first))
        self.assertEqual(eval_result.score(case, both), {"case": case["id"], "verdict": "fail", "reasons": ["surplus_at_place"]})
        both["findings"][-1]["severity"] = "minor"
        self.assertEqual(eval_result.score(case, both), {"case": case["id"], "verdict": "fail", "reasons": ["surplus_at_place"]})
        both["findings"][-1].update(severity=both["findings"][0]["severity"], criterion=None)
        self.assertEqual(eval_result.score(case, both), {"case": case["id"], "verdict": "fail", "reasons": ["surplus_at_place"]})
        self.assertNotIn("at_alternate", eval_result.score(case, placed(other, criterion=None)))
        # A clean case's pass is never marked: its Result's major Finding, which would hold it (decision 0144), at minor.
        clean = copy.deepcopy(result)
        clean["findings"][0]["severity"] = "minor"
        self.assertEqual(eval_result.score(load("examples/eval-case.met.json"), clean)["verdict"], "pass")
        self.assertNotIn("at_alternate", eval_result.score(load("examples/eval-case.met.json"), clean))
        # Absent, the Finding has its one place, as before.
        alone = copy.deepcopy(case)
        del alone["expected"]["finding"]["also_at"]
        self.assertEqual(eval_result.score(alone, placed(first))["verdict"], "pass")
        self.assertEqual(eval_result.score(alone, placed(other))["reasons"], ["location_differs"])
        # Where it went, when nothing cited the criterion: at any place given, or in a file of one of them but
        # elsewhere, or in none of them; each in a file of its own, the diff changing each.
        apart = copy.deepcopy(case)
        # The example's hunk claims more lines than it holds, so a file after it would be read inside it: its own
        # hunk is given its true counts here.
        apart["diff"] = (case["diff"].replace("@@ -86,9 +86,9 @@", "@@ -86,4 +86,4 @@")
                         + "--- a/kernel/gate.py\n+++ b/kernel/gate.py\n@@ -10,2 +10,3 @@\n a\n+b\n c\n"
                         + "--- a/kernel/state.py\n+++ b/kernel/state.py\n@@ -5,1 +5,2 @@\n x\n+y\n")
        self.assertEqual(eval_result._hunks(apart["diff"]),
                         {"kernel/decide.py": [{86, 87, 88, 89}], "kernel/gate.py": [{10, 11, 12}], "kernel/state.py": [{5, 6}]})
        apart["expected"]["finding"]["also_at"] = [{"path": "kernel/gate.py", "start_line": 10, "end_line": 12}]

        def went(location):
            scored = eval_result.score(apart, placed(location, criterion=None))
            return [r for r in scored["reasons"] if r != "coverage_disagrees"]
        self.assertEqual(went({"path": "kernel/gate.py", "start_line": 11, "end_line": 11}), ["finding_uncited"])
        self.assertEqual(went(first), ["finding_uncited"])
        self.assertEqual(went({"path": "kernel/gate.py", "start_line": 40, "end_line": 41}), ["finding_elsewhere"])
        self.assertEqual(went({"path": first["path"], "start_line": 200, "end_line": 201}), ["finding_elsewhere"])
        self.assertEqual(went({"path": "kernel/gate.py", "start_line": 12, "end_line": 2}), ["finding_not_raised"])
        self.assertEqual(went({"path": "kernel/state.py", "start_line": 11, "end_line": 11}), ["finding_not_raised"])
        # An alternate place holds a Finding to its span as `location` does: three lines and fifteen more, or none.
        self.assertEqual(eval_result.score(apart, placed({"path": "kernel/gate.py", "start_line": 10, "end_line": 27}))["at_alternate"], True)
        self.assertEqual(eval_result.score(apart, placed({"path": "kernel/gate.py", "start_line": 10, "end_line": 28}))["reasons"],
                         ["location_differs"])
        self.assertEqual(went({"path": "kernel/gate.py", "start_line": 10, "end_line": 27}), ["finding_uncited"])
        self.assertEqual(went({"path": "kernel/gate.py", "start_line": 10, "end_line": 28}), ["finding_elsewhere"])
        self.assertEqual(went({"path": "kernel/gate.py"}), ["finding_elsewhere"])
        # Every entry is read, not the first alone (Muse's read of #561): a later one is a place as the first is.
        apart["expected"]["finding"]["also_at"].append({"path": "kernel/state.py", "start_line": 5, "end_line": 6})
        later = {"path": "kernel/state.py", "start_line": 6, "end_line": 6}
        self.assertEqual(eval_result.score(apart, placed(later))["verdict"], "pass")
        self.assertEqual(went(later), ["finding_uncited"])
        self.assertEqual(went({"path": "kernel/state.py", "start_line": 11, "end_line": 11}), ["finding_elsewhere"])

        def unreadable(places, diff=None):
            made = copy.deepcopy(apart)
            made["expected"]["finding"]["also_at"] = places
            made["diff"] = made["diff"] if diff is None else diff
            return eval_result.score(made, placed(first))
        gone = {"case": case["id"], "verdict": "unreadable", "reasons": ["location_unreadable"]}
        # Every place a case gives must be readable, whichever it is.
        for lines in ({"start_line": 12, "end_line": 10}, {"start_line": 6, "end_line": 5}):
            for at in (0, 1):
                places = [{"path": "kernel/gate.py", "start_line": 10, "end_line": 12}, {"path": "kernel/state.py", "start_line": 5}]
                places[at] = dict(places[at], **lines)
                self.assertEqual(unreadable(places), gone, places)
        # And each inside a hunk of the case's own diff, on the head's side, in its own file: not on a line the head's
        # side does not hold, not across the gap between two hunks, not in a file the diff does not change, and not in
        # a file's hunks once its header names another prefix, whichever entry it is.
        inside = {"path": "kernel/gate.py", "start_line": 10, "end_line": 12}
        self.assertEqual(unreadable([inside, {"path": "kernel/state.py", "start_line": 5, "end_line": 6}])["verdict"], "pass")
        for outside in ({"path": "kernel/gate.py", "start_line": 13}, {"path": "kernel/gate.py", "start_line": 9, "end_line": 10},
                        {"path": "kernel/gate.py", "start_line": 12, "end_line": 13}, {"path": "kernel/state.py", "start_line": 7},
                        {"path": "kernel/other.py", "start_line": 5}, {"path": first["path"], "start_line": 90},
                        {"path": "kernel/gate.py", "start_line": 10, "end_line": 1000000000}):
            for places in ([outside], [inside, outside], [inside, inside, outside]):
                self.assertEqual(unreadable(places), gone, places)
        two = apart["diff"] + "--- a/kernel/far.py\n+++ b/kernel/far.py\n@@ -1,1 +1,1 @@\n a\n@@ -9,1 +9,1 @@\n z\n"
        self.assertEqual(unreadable([{"path": "kernel/far.py", "start_line": 9}], two)["verdict"], "pass")
        self.assertEqual(unreadable([{"path": "kernel/far.py", "start_line": 1, "end_line": 9}], two), gone)
        # Inside one hunk, not two that meet (Muse's read of #561): lines 10 to 13 are held, but by no one hunk.
        near = apart["diff"] + "--- a/kernel/near.py\n+++ b/kernel/near.py\n@@ -10,2 +10,2 @@\n a\n b\n@@ -12,2 +12,2 @@\n c\n d\n"
        self.assertEqual(unreadable([{"path": "kernel/near.py", "start_line": 12, "end_line": 13}], near)["verdict"], "pass")
        self.assertEqual(unreadable([{"path": "kernel/near.py", "start_line": 10, "end_line": 13}], near), gone)
        # A line is one the Task numbered: a row outside every hunk that reads as numbered is none (Muse's read of #561).
        stray = apart["diff"].replace(" c\n--- a/kernel/state.py", " c\n999| stray\n--- a/kernel/state.py")
        self.assertNotEqual(stray, apart["diff"])
        self.assertEqual(unreadable([{"path": "kernel/gate.py", "start_line": 999}], stray), gone)
        # A header git quotes, as it does a path of other than plain characters, is none either: the key never loosens.
        for header in ("+++ kernel/gate.py", "+++ c/kernel/gate.py", '+++ "b/kernel/gate.py"'):
            self.assertEqual(unreadable([inside], apart["diff"].replace("+++ b/kernel/gate.py", header)), gone, header)
        # A removed line is no line of the head's side: the base's line 10 of a hunk that only removes is not held.
        removed = apart["diff"] + "--- a/kernel/cut.py\n+++ b/kernel/cut.py\n@@ -10,1 +9,0 @@\n-gone\n"
        self.assertEqual(unreadable([{"path": "kernel/cut.py", "start_line": 9}], removed), gone)
        # The schema holds a case to it: `also_at`, where given, names one to three places, each with its path and lines.
        self.assertEqual(validate(case, eval_result.schemas()["eval-case"], schemas=eval_result.schemas()), [])
        three = [other, other, other]
        self.assertEqual(validate(dict(case, expected=dict(case["expected"], finding=dict(case["expected"]["finding"], also_at=three))),
                                  eval_result.schemas()["eval-case"], schemas=eval_result.schemas()), [])
        for places in ([], three + [other], [{"start_line": 86}], [{"path": first["path"]}], [{"path": first["path"], "end_line": 86}],
                       [dict(other, at="x")], other):
            bad = copy.deepcopy(case)
            bad["expected"]["finding"]["also_at"] = places
            self.assertNotEqual(validate(bad, eval_result.schemas()["eval-case"], schemas=eval_result.schemas()), [], places)
    def test_a_right_change_is_scored_by_its_coverage(self):
        case, result = load("examples/eval-case.met.json"), example_result()
        # The example's major Finding would hold a pull request, which a clean case fails (decision 0144): at minor, it
        # holds none.
        result["findings"][0]["severity"] = "minor"
        self.assertEqual(eval_result.score(case, result)["verdict"], "pass")
        # The other side: a Finding raised against a criterion the change met, or the criterion left uncovered.
        wrong = copy.deepcopy(result)
        wrong["findings"][0]["criterion"] = "PR-1"
        wrong["coverage"][0]["verdict"] = "finding"
        self.assertEqual(eval_result.score(case, wrong)["reasons"], ["finding_raised_wrongly", "criterion_not_met"])
        wrong = copy.deepcopy(result)
        del wrong["coverage"][0]
        self.assertEqual(eval_result.score(case, wrong)["reasons"], ["criterion_not_met"])

    def test_a_gating_finding_fails_a_clean_case(self):  # decision 0144
        # A clean case holds no fault a gate should stop. A Finding that would hold its pull request, blocking or major or
        # a security Finding at any severity, as `kernel/gate.py` reads a required Lens's, fails the case whatever
        # criterion it cites or none, and even with the case's own criterion covered as met.
        from kernel import gate, terms
        case, result = load("examples/eval-case.met.json"), example_result()
        self.assertEqual(result["findings"][0]["severity"], "major")
        self.assertNotEqual(result["findings"][0]["criterion"], case["expected"]["criterion"])
        self.assertEqual([c["verdict"] for c in result["coverage"] if c["criterion"] == case["expected"]["criterion"]], ["met"])
        self.assertEqual(eval_result.score(case, result), {"case": case["id"], "verdict": "fail", "reasons": ["finding_raised_wrongly"]})
        # Every severity of every category, cited to another criterion or to none: it fails where the gate would hold it,
        # and only there.
        for severity in terms.SEVERITIES:
            for category in terms.CATEGORIES:
                for criterion in ("PR-3", None):
                    raised = copy.deepcopy(result)
                    raised["findings"][0].update(severity=severity, category=category, criterion=criterion)
                    holds = severity in gate.GATING_SEVERITIES or category == gate.SECURITY
                    self.assertEqual(eval_result.score(case, raised)["reasons"], ["finding_raised_wrongly"] if holds else [],
                                     (severity, category, criterion))
        # Any one such Finding among others that would not fails it; the code is given once.
        among = copy.deepcopy(result)
        among["findings"][0]["severity"] = "minor"
        among["findings"].append(dict(among["findings"][1], ref="n9", category="security", severity="info"))
        self.assertEqual(eval_result.score(case, among)["reasons"], ["finding_raised_wrongly"])
        cites = copy.deepcopy(result)
        cites["findings"][0]["criterion"] = case["expected"]["criterion"]
        self.assertEqual(eval_result.score(case, cites)["reasons"], ["finding_raised_wrongly"])
        # A Finding the case's own criterion cites still fails it at a severity that holds nothing, as before.
        cites["findings"][0]["severity"] = "info"
        self.assertEqual(eval_result.score(case, cites)["reasons"], ["finding_raised_wrongly"])
        # The other side: a case that expects a Finding is scored as before, a Finding elsewhere that would hold it no fault.
        found = load("examples/eval-case.json")
        extra = copy.deepcopy(example_result())
        extra["findings"].append(dict(extra["findings"][1], ref="n9", category="security", severity="blocking"))
        self.assertEqual(eval_result.score(found, extra)["verdict"], "pass")

    def test_a_case_whose_expected_finding_is_off_its_rubric_scores_nothing(self):  # issue 421
        # A Result whose Finding cites a criterion at another severity or category than the rubric's is refused (decisions
        # 0088 and 0095), so a case that expects one would reward a Result `apply` refuses: what is measured would not be
        # what runs. Such a case is no answer, whatever the Result says, and it is read as a code alone.
        case, result = load("examples/eval-case.json"), example_result()
        self.assertEqual(eval_result.score(case, result)["verdict"], "pass")
        self.assertFalse(eval_result.off_rubric(case))
        for change in ({"category": "delivery"}, {"severity": "minor"}, {"category": "security", "severity": "blocking"}):
            off = copy.deepcopy(case)
            off["expected"]["finding"].update(change)
            self.assertTrue(eval_result.off_rubric(off), change)
            # A Result that gives what the case expects is still no pass, and the answer is said in no word of the code.
            said = copy.deepcopy(result)
            said["findings"][0].update(change)
            self.assertEqual(eval_result.score(off, said),
                             {"case": case["id"], "verdict": "unreadable", "reasons": ["answer_off_rubric"]}, change)
        # Each criterion's own severity and category are what is held, not the first's.
        rubric = load("config/rubric-pr-review.json")
        for criterion in rubric["criteria"]:
            on = copy.deepcopy(case)
            on["expected"]["criterion"] = criterion["id"]
            on["expected"]["finding"].update(category=criterion["category"], severity=criterion["severity_if_violated"])
            self.assertFalse(eval_result.off_rubric(on), criterion["id"])
        # The other side: a case of a criterion met expects no Finding, and one whose rubric lacks the criterion, or
        # whose Role has none, is the scorer's `criterion_unknown`, as before.
        met = load("examples/eval-case.met.json")
        self.assertIsNone(met["expected"]["finding"])
        self.assertFalse(eval_result.off_rubric(met))
        unknown = copy.deepcopy(case)
        unknown["expected"]["criterion"] = "PR-99"
        self.assertFalse(eval_result.off_rubric(unknown))
        self.assertEqual(eval_result.score(unknown, result)["reasons"], ["criterion_unknown"])
        nobody = dict(copy.deepcopy(case), role="no-such-role")
        self.assertFalse(eval_result.off_rubric(nobody))
        # A rubric read, but whose criterion gives no severity or category, holds no case to it: the case is off it, and
        # is never asked of the model. One that cannot be read at all is the scorer's, as above.
        import tempfile
        with tempfile.TemporaryDirectory() as made:
            place = pathlib.Path(made)
            (place / "config").mkdir()
            given = place / "config" / "rubric-pr-review.json"
            for field in ("category", "severity_if_violated"):
                broken = copy.deepcopy(rubric)
                del broken["criteria"][-1][field]
                given.write_text(json.dumps(broken))
                self.assertTrue(eval_result.off_rubric(case, place), field)
            given.write_text(json.dumps(dict(rubric, criteria=[None])))
            self.assertTrue(eval_result.off_rubric(case, place))
            # Nor is the case on a rubric coverage refuses wholesale, though the criterion it cites reads as it expects
            # (Muse's read of #421): another criterion's severity or category out of the Factory's, or one given twice.
            cited = next(c for c in rubric["criteria"] if c["id"] == case["expected"]["criterion"])
            other = next(c for c in rubric["criteria"] if c["id"] != cited["id"])
            for at_fault in ([dict(other, severity_if_violated="high"), cited], [dict(other, category=None), cited],
                             [cited, dict(cited)]):
                given.write_text(json.dumps(dict(rubric, criteria=at_fault)))
                self.assertTrue(eval_result.off_rubric(case, place), at_fault)
            given.write_text(json.dumps(dict(rubric, criteria=[other, cited])))
            self.assertFalse(eval_result.off_rubric(case, place))
            given.write_text("not json")
            self.assertFalse(eval_result.off_rubric(case, place))
        # The cases the repo gives as examples are on it.
        for path in sorted((ROOT / "examples").glob("eval-case*.json")):
            self.assertFalse(eval_result.off_rubric(json.loads(path.read_text())), path.name)

    def test_a_case_or_a_result_that_cannot_be_read_scores_nothing(self):
        case, result = load("examples/eval-case.json"), example_result()
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
        # A criterion the Role's rubric does not have, or a Role with no rubric here, is nobody's to pass.
        for over in ({"expected": dict(case["expected"], criterion="PR-9")}, {"role": "qa-lead"}):
            unknown = dict(copy.deepcopy(case), **over)
            self.assertEqual(eval_result.score(unknown, result)["reasons"], ["criterion_unknown"], over)

    def test_a_result_that_hedges_at_the_place_or_gates_elsewhere_fails_its_case(self):  # issue 610
        # The scorer takes the nearest of the Findings that cite a case's criterion, so extra Findings would cost nothing:
        # on a case that expects a Finding, one is put at the place, whatever it cites, and one gating Finding away from
        # every place is allowed, for a real fault the case's authors could have missed.
        from kernel import gate, terms
        case, result = load("examples/eval-case.json"), example_result()
        right = result["findings"][0]
        place, far = right["location"], {"path": "kernel/gate.py", "start_line": 10, "end_line": 12}
        self.assertEqual(eval_result.score(case, result), {"case": case["id"], "verdict": "pass", "reasons": []})

        def scored(*more, first=None):
            made = [dict(right, **(first or {}))] + [dict(right, ref="n%d" % (5 + n), **f) for n, f in enumerate(more)]
            return eval_result.score(case, dict(result, findings=[{k: v for k, v in f.items() if k != "location" or v is not None}
                                                                  for f in made]))
        failed = {"case": case["id"], "verdict": "fail", "reasons": ["surplus_at_place"]}
        # Two at the place fail, whatever the second cites, its category or severity, the right one among them.
        for given in ({}, {"criterion": None}, {"criterion": "PR-1"}, {"category": "security"}, {"severity": "info"},
                      {"location": dict(place, start_line=place["end_line"])}):
            self.assertEqual(scored(given), failed, given)
        self.assertEqual(scored({}, {})["reasons"], ["surplus_at_place"])
        # One at the place and one gating Finding elsewhere pass, counted; two gating Findings elsewhere fail, counted.
        self.assertEqual(scored({"location": far}), {"case": case["id"], "verdict": "pass", "reasons": [], "surplus_gating": 1})
        self.assertEqual(scored({"location": far}, {"location": dict(far, path="kernel/state.py"), "criterion": None}),
                         {"case": case["id"], "verdict": "fail", "reasons": ["surplus_gating_elsewhere"], "surplus_gating": 2})
        # Both bounds are told, the place's first.
        self.assertEqual(scored({}, {"location": far}, {"location": far})["reasons"], ["surplus_at_place", "surplus_gating_elsewhere"])
        self.assertEqual(scored(*[{"location": far}] * 3),
                         {"case": case["id"], "verdict": "fail", "reasons": ["surplus_gating_elsewhere"], "surplus_gating": 3})
        # What gates elsewhere is what would hold a pull request, as on a clean case (decision 0144): blocking or major,
        # or security at any severity. Any other Finding elsewhere is nothing, however many.
        for severity in terms.SEVERITIES:
            for category in terms.CATEGORIES:
                holds = severity in gate.GATING_SEVERITIES or category == gate.SECURITY
                two = scored(*[{"location": far, "severity": severity, "category": category, "criterion": c} for c in ("PR-1", None)])
                self.assertEqual((two["reasons"], two.get("surplus_gating")),
                                 (["surplus_gating_elsewhere"], 2) if holds else ([], None), (severity, category))
        self.assertEqual(scored(*[{"location": far, "severity": "minor"}] * 4), {"case": case["id"], "verdict": "pass", "reasons": []})
        # A Finding with no lines, or none at all, is at no place (decision 0143), so it is away from every place.
        self.assertEqual(scored({"location": {"path": place["path"]}}, {"location": None})["reasons"], ["surplus_gating_elsewhere"])
        # A miss is told as before, beside them, and the expected Finding put elsewhere is one of them.
        self.assertEqual(scored({"location": far}, first={"location": far}),
                         {"case": case["id"], "verdict": "fail", "reasons": ["location_differs", "surplus_gating_elsewhere"],
                          "surplus_gating": 2})
        # Each place of `also_at` is the place: one fault put at two of its places is put twice.
        also = load("examples/eval-case.also-at.json")
        first, other = also["expected"]["finding"]["location"], also["expected"]["finding"]["also_at"][0]
        twice = dict(result, findings=[dict(right, location=first), dict(right, ref="n9", criterion=None, location=other)])
        self.assertEqual(eval_result.score(also, twice), {"case": also["id"], "verdict": "fail", "reasons": ["surplus_at_place"]})
        # Nor is a Finding at an alternate place away from the place: the right one there and one gating elsewhere pass.
        alternate = dict(result, findings=[dict(right, location=other), dict(right, ref="n9", location=far)])
        self.assertEqual(eval_result.score(also, alternate),
                         {"case": also["id"], "verdict": "pass", "reasons": [], "at_alternate": True, "surplus_gating": 1})
        # A clean case is unchanged: any gating Finding already fails it, and none is counted.
        met = load("examples/eval-case.met.json")
        clean = dict(result, findings=[dict(right, severity=s, location=far, ref="n%d" % n) for n, s in enumerate(("major", "blocking"))])
        self.assertEqual(eval_result.score(met, clean), {"case": met["id"], "verdict": "fail", "reasons": ["finding_raised_wrongly"]})
        clean["findings"] = [dict(f, severity="minor", location=place) for f in clean["findings"]]
        self.assertEqual(eval_result.score(met, clean), {"case": met["id"], "verdict": "pass", "reasons": []})
        # A case that cannot be read counts nothing.
        unknown = dict(case, expected=dict(case["expected"], criterion="PR-99"))
        two = dict(result, findings=[right, dict(right, ref="n9", location=far), dict(right, ref="n10", location=far)])
        self.assertEqual(eval_result.score(unknown, two), {"case": case["id"], "verdict": "unreadable", "reasons": ["criterion_unknown"]})

    def test_a_posted_finding_off_every_hunk_fails_the_case_as_apply_refuses_the_result(self):  # issue 574
        # `apply` refuses a Result whole when a Finding it posts is not all on one hunk of its file at the head (decision
        # 0146), so the scorer fails the case by that code alone, as a live Run would meet it, by `apply`'s own readers.
        from harness import apply, task
        case = load("examples/eval-case.json")
        shown = {"texts": [{"id": "diff:x", "body": task.numbered(case["diff"])}]}

        def posting(*places, annotate=None):
            result = example_result()
            for finding, place in zip(result["findings"], places):
                finding["location"] = place
            result["effects"] = {"submit_review": [{"id": "e1", "comments": [{"finding": "n1", "body": "x"}], "body": None}]}
            if annotate:
                result["effects"]["create_check_run"] = [{"id": "e2", "annotations": [{"finding": "n2", "body": "x"}]}]
            return result
        decide = {"path": "kernel/decide.py", "start_line": 88, "end_line": 94}
        on = posting(decide)
        self.assertEqual(eval_result.score(case, on), {"case": case["id"], "verdict": "pass", "reasons": []})
        # The hunk's first and last lines are on it; a line before or past it, or a file the diff does not hold, is not.
        for place, off in ((dict(decide, start_line=86), False), (dict(decide, end_line=95), True),
                           (dict(decide, start_line=85), True), (dict(decide, path="kernel/derive.py"), True)):
            result = posting(place)
            self.assertEqual(eval_result.score(case, result)["reasons"] == ["finding_not_in_hunk"], off, place)
            self.assertEqual(apply.off_hunks(shown, result) is not None, off, place)
        # An annotation is held as a review's comment is, and the case fails by it alone, the right Finding beside it.
        noted = posting(decide, {"path": "tests/test_decide.py", "start_line": 410, "end_line": 410}, annotate=True)
        self.assertEqual(eval_result.score(case, noted), {"case": case["id"], "verdict": "fail", "reasons": ["finding_not_in_hunk"]})
        self.assertEqual(eval_result.score(load("examples/eval-case.met.json"), noted)["reasons"], ["finding_not_in_hunk"])
        # A review's comment is held beside an annotation that is on the hunk, as the annotation is beside a comment.
        swapped = copy.deepcopy(noted)
        swapped["effects"]["submit_review"][0]["comments"][0]["finding"] = "n2"
        swapped["effects"]["create_check_run"][0]["annotations"][0]["finding"] = "n1"
        self.assertEqual(eval_result.score(case, swapped)["reasons"], ["finding_not_in_hunk"])
        self.assertEqual(eval_result.score(load("examples/eval-case.met.json"), swapped)["reasons"], ["finding_not_in_hunk"])
        # A fault of the case is told first, as before: it is the case owner's, never the reviewer's.
        for over, code in (({"criterion": "PR-99"}, "criterion_unknown"), ({"finding": None}, "answer_disagrees_with_verdict"),
                           ({"finding": dict(case["expected"]["finding"], severity="minor")}, "answer_off_rubric"),
                           ({"finding": dict(case["expected"]["finding"], also_at=[{"path": "kernel/decide.py",
                                                                                    "start_line": 1, "end_line": 1}])},
                            "location_unreadable")):
            broken = dict(case, expected=dict(case["expected"], **over))
            self.assertEqual(eval_result.score(broken, noted)["reasons"], [code], code)
        # A Result that did not complete is told as that, as `apply` refuses it first.
        unfinished = dict(noted, status="incomplete", reason="change_not_reviewed_whole")
        self.assertEqual(eval_result.score(case, unfinished)["reasons"][0], "result_not_completed")
        self.assertNotIn("finding_not_in_hunk", eval_result.score(case, unfinished)["reasons"])
        # A Finding the Result does not post is scored as before, and so is a posted one with no lines, which `apply`
        # refuses by another code.
        unposted = dict(posting(dict(decide, path="kernel/derive.py")), effects={})
        self.assertEqual(eval_result.score(case, unposted)["reasons"], ["location_differs"])
        whole = posting({"path": "kernel/decide.py"})
        self.assertEqual(eval_result.score(case, whole)["reasons"], ["location_differs"])

    def test_the_front_door_scores_two_files_and_says_so_in_its_exit(self):
        import tempfile
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d, mock.patch("sys.stdout", out):
            given = pathlib.Path(d).resolve()
            (given / "case.json").write_text(json.dumps(load("examples/eval-case.json")))
            (given / "result.json").write_text(json.dumps(example_result()))
            self.assertEqual(eval_result.main([str(given / "case.json"), str(given / "result.json")], base=given), 0)
        self.assertEqual(json.loads(out.getvalue())["verdict"], "pass")
        with mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(eval_result.main([str(ROOT / "examples" / "eval-case.met.json"),
                                               str(ROOT / "examples" / "result.failed.json")]), 1)
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(eval_result.main([str(ROOT / "examples" / "eval-case.json"), str(ROOT / "nothing.json")]), 2)
            self.assertEqual(eval_result.main([str(ROOT / "examples" / "eval-case.json")]), 2)
        # The scorer reads only under the directory it runs in: a path that points elsewhere, however written, is
        # refused before it is opened, and the refusal names no path.
        case, result = ROOT / "examples" / "eval-case.json", ROOT / "examples" / "result.json"
        said = io.StringIO()
        with mock.patch("sys.stderr", said):
            for outside in ([str(case), str(ROOT.parent / "elsewhere.json")],
                            [str(ROOT / "examples" / ".." / ".." / "elsewhere.json"), str(result)],
                            [str(case), str(result)]):
                base = ROOT if outside[0] != str(case) or "elsewhere" in outside[1] else ROOT / "examples" / "invalid"
                self.assertEqual(eval_result.main(outside, base=base), 2, outside)
        self.assertNotIn("elsewhere", said.getvalue())
        self.assertIn("file_outside", said.getvalue())
        # A path inside it is read: the example Result posts a Finding off the example case's hunks, so it fails.
        with mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(eval_result.main([str(case), str(result)], base=ROOT / "examples"), 1)


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
            kind = check_examples.LIVE[path.relative_to(ROOT).as_posix()]
            self.assertEqual(validate(json.loads(text), known[kind], schemas=known), [], path)
        self.assertIn("evals/pr-review/cases.json", check_examples.LIVE)
        # The example manifest is held the same way: a count that disagrees with the list is caught.
        example = load("examples/eval-set.json")
        self.assertEqual(example["count"], len(example["cases"]))

    def test_a_case_dropped_under_evals_in_any_file_is_caught(self):
        # The front door: a JSON file not in LIVE, and a case's content in a file of any name, a diff among it.
        from tests.test_tools import clone, caught
        problems = check_examples.run(clone({"evals/qa-lead/cases.json": '{"schema": "eval-set/1"}'}))
        self.assertTrue(caught(problems, "evals/qa-lead/cases.json is validated against no schema"))
        case = (ROOT / "examples" / "eval-case.json").read_text()
        for name, text in (("evals/pr-review/notes.txt", "--- a/kernel/x.py\n+++ b/kernel/x.py\n@@ -1 +1 @@\n"),
                           ("evals/pr-review/README.md", "A case:\n```json\n" + case + "\n```\n"),
                           ("evals/pr-review/leaked.yaml", 'schema: eval-case/1\n')):
            problems = check_examples.run(clone({name: text}))
            self.assertTrue(caught(problems, "%s holds what looks like a held-out case" % name), name)
        # Nothing else lives under evals/: a note, however harmless, is refused, and a manifest in LIVE and the
        # directory's rules are all that pass.
        problems = check_examples.run(clone({"evals/pr-review/NOTE.md": "The hashes are the home's.\n"}))
        self.assertTrue(caught(problems, "evals/pr-review/NOTE.md is neither a manifest in LIVE nor the directory's rules"))
        self.assertEqual(check_examples.run(), [])

    def test_a_cases_categories_are_the_findings(self):
        from tests.test_tools import caught
        from tools import check_authority
        case = load("schemas/eval-case.schema.json")
        answer = case["properties"]["expected"]["properties"]["finding"]["properties"]
        answer["category"]["enum"].append("cosmetic")
        answer["severity"]["enum"].remove("info")
        problems = check_authority.run(case=case)
        self.assertTrue(caught(problems, "a held-out case may expect the category cosmetic, and no Finding can carry it"))
        self.assertTrue(caught(problems, "a Finding may carry the severity info, and no held-out case can expect it"))
        del answer["category"]
        self.assertTrue(caught(check_authority.run(case=case), "a held-out case's expected Finding carries no category"))

    def test_the_eval_jobs_name_is_reserved(self):
        from tests.test_tools import clone, caught, GOOD
        from tools import check_workflows
        taken = GOOD.replace("  checks:\n", "  eval:\n", 1)
        problems = check_workflows.run(clone({".github/workflows/other.yml": taken}))
        self.assertTrue(caught(problems, ".github/workflows/other.yml: the job eval is reserved for eval.yml"))
        # GitHub names a check run by the job's name where it has one: a job of another id named eval is reserved too.
        by_name = GOOD.replace("  checks:\n", "  other:\n    name: eval\n", 1)
        problems = check_workflows.run(clone({".github/workflows/other.yml": by_name}))
        self.assertTrue(caught(problems, ".github/workflows/other.yml: the job eval is reserved for eval.yml"))
        problems = check_workflows.run(clone({".github/workflows/eval.yml": GOOD}))
        self.assertTrue(caught(problems, ".github/workflows/eval.yml: holds the job eval and no other"))

    def test_the_eval_workflow_names_each_credential_in_one_step_alone(self):
        # Issue 309, ruling 10: dispatched alone with the Release it judges; one job on factory-eval, granted
        # contents: read; its steps in order; the Maintainer's token for the held-out home named by
        # fetch alone and the model's credential by run alone, so no step holds both; the upload takes the report alone.
        from tests.test_tools import clone, caught, GOOD
        from tools import check_workflows
        self.assertEqual(check_workflows.eval_problems(EVAL_WORKFLOW), [])
        # eval.yml runs main's own file on a dispatch, as the eval job judges main's commit: it is spared the shim rule,
        # since eval_problems holds every line of it, and keeps every other rule.
        self.assertEqual([r for r in check_workflows.lint(EVAL_WORKFLOW) if r[0] not in check_workflows.SHAPED["eval.yml"]], [])
        token = "          HELDOUT_TOKEN: ${{ secrets.HELDOUT_TOKEN }}\n"
        install = EVAL_WORKFLOW[EVAL_WORKFLOW.index("      - env:\n          CLI_VERSION"):
                                EVAL_WORKFLOW.index("      - run: python3 -m harness.eval.fetch\n")]
        model = "          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}\n"
        broken = {
            "the token beside the model": (EVAL_WORKFLOW.replace(token, token + model), "its fetch step is given under env"),
            "the model beside the token": (EVAL_WORKFLOW.replace(model, model + token), "its run step is given under env"),
            "the token handed to the plan": (EVAL_WORKFLOW.replace("          RELEASE: ${{ inputs.release }}\n",
                                                                   "          RELEASE: ${{ inputs.release }}\n" + token),
                                             "its plan step is given under env"),
            "the token given to the upload": (EVAL_WORKFLOW.replace("          retention-days: 90\n",
                                                                    "          retention-days: 90\n          token: ${{ secrets.HELDOUT_TOKEN }}\n"),
                                              "its upload step is given under with"),
            "the token under another name": (EVAL_WORKFLOW.replace("${{ secrets.HELDOUT_TOKEN }}", "${{ secrets.HELDOUT_PAT }}"),
                                             "its fetch step is given under env"),
            "a token minted beside it": (EVAL_WORKFLOW.replace("      - run: python3 -m harness.eval.fetch\n",
                                                               "      - uses: actions/create-github-app-token@64ab729a6294000f5aa4a4bc0b73d1f32bc45510 # v3.3.0\n"
                                                               "      - run: python3 -m harness.eval.fetch\n"), "in that order"),
            "the token on the job": (EVAL_WORKFLOW.replace("    environment: factory-eval\n",
                                                           "    environment: factory-eval\n    env:\n" + token[4:]),
                                     "its job has exactly"),
            "a shorter timeout": (EVAL_WORKFLOW.replace("timeout-minutes: 120", "timeout-minutes: 20"),
                                  "with a timeout of 120 minutes"),
            "another runner": (EVAL_WORKFLOW.replace("runs-on: ubuntu-24.04", "runs-on: ubuntu-24.04-big"),
                               "its job runs on ubuntu-24.04"),
            "another environment": (EVAL_WORKFLOW.replace("environment: factory-eval", "environment: factory-run"),
                                    "runs on the environment factory-eval"),
            "a write": (EVAL_WORKFLOW.replace("      contents: read\n", "      contents: read\n      actions: read\n"),
                        "granted contents: read and nothing else"),
            "a pull request": (EVAL_WORKFLOW.replace("on:\n", "on:\n  pull_request:\n  merge_group:\n"),
                               "runs on workflow_dispatch alone"),
            "a schedule": (EVAL_WORKFLOW.replace("on:\n", "on:\n  schedule:\n    - cron: '17 3 * * *'\n"),
                           "runs on workflow_dispatch alone"),
            "no release": (EVAL_WORKFLOW.replace("      release:\n", "      version:\n"), "one input, release"),
            "a release left optional": (EVAL_WORKFLOW.replace("required: true", "required: false"), "one input, release"),
            "the fetch first": (EVAL_WORKFLOW.replace("      - run: python3 -m harness.eval.plan\n        env:\n"
                                                      "          RELEASE: ${{ inputs.release }}\n", "", 1)
                                .replace("      - run: python3 -m harness.eval.run\n",
                                         "      - run: python3 -m harness.eval.plan\n        env:\n"
                                         "          RELEASE: ${{ inputs.release }}\n"
                                         "      - run: python3 -m harness.eval.run\n", 1), "in that order"),
            "no judge": (EVAL_WORKFLOW.replace("      - run: python3 -m harness.eval.judge\n", ""), "in that order"),
            "a step of its own": (EVAL_WORKFLOW.replace("      - run: python3 -m harness.eval.judge\n",
                                                        "      - run: python3 -m harness.eval.judge\n"
                                                        "      - run: make verify\n"), "in that order"),
            "a step skipped": (EVAL_WORKFLOW.replace("      - run: python3 -m harness.eval.judge\n",
                                                     "      - run: python3 -m harness.eval.judge\n        if: false\n"),
                               "its judge step has a key it may not"),
            "an id on fetch": (EVAL_WORKFLOW.replace("      - run: python3 -m harness.eval.fetch\n",
                                                     "      - run: python3 -m harness.eval.fetch\n        id: home\n"),
                               "its fetch step has a key it may not"),
            "the whole workspace uploaded": (EVAL_WORKFLOW.replace("path: eval-report.json", "path: ."),
                                             "its upload step is given under with"),
            "a credential left on disk": (EVAL_WORKFLOW.replace("persist-credentials: false", "persist-credentials: true"),
                                          "its checkout step is given under with"),
            "an upload of another commit": (EVAL_WORKFLOW.replace("upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9",
                                                                  "upload-artifact@" + "0" * 40), "in that order"),
            "an upload of its own": (EVAL_WORKFLOW.replace("uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
                                                           " # v7.0.2", "run: python3 -m harness.eval.upload"), "in that order"),
            "the home as a variable": (EVAL_WORKFLOW.replace("${{ secrets.HELDOUT_OWNER }}", "${{ vars.HELDOUT_OWNER }}"),
                                       "its fetch step is given under env"),
            "a credential for every step": (EVAL_WORKFLOW.replace("permissions: {}\n", "permissions: {}\nenv:\n"
                                                                  "  KEY: ${{ secrets.HELDOUT_TOKEN }}\n"),
                                            "nothing else above its job"),
            "a default for every step": (EVAL_WORKFLOW.replace("permissions: {}\n", "permissions: {}\ndefaults:\n  run:\n"
                                                               "    working-directory: x\n"), "nothing else above its job"),
            "another name": (EVAL_WORKFLOW.replace("name: factory\n", "name: eval\n"), "nothing else above its job"),
            "a grant above the job": (EVAL_WORKFLOW.replace("permissions: {}\n", "permissions:\n  contents: read\n"),
                                      "nothing else above its job"),
            "an empty env on the judge": (EVAL_WORKFLOW + "        env:\n", "its judge step has a env: it is not given"),
            # The CLI's install, before the fetch, at the Engine's pin by its checksum, word for
            # word as the Run's jobs install it (issue 309, amendment 1).
            # Bubblewrap is in the block, and the block comes before the fetch: it runs as root, before the cases are here.
            "no bubblewrap": (EVAL_WORKFLOW.replace("          sudo apt-get install -y --no-install-recommends bubblewrap\n", ""),
                              "its steps are"),
            "the install after the fetch": (EVAL_WORKFLOW.replace(FETCH_STEP, "").replace(
                "      - env:\n          CLI_VERSION", FETCH_STEP + "      - env:\n          CLI_VERSION"), "its steps are"),
            "the CLI at another version": (EVAL_WORKFLOW.replace('CLI_VERSION: "2.1.306"', 'CLI_VERSION: "2.1.305"'),
                                           "its install step is given under env"),
            "the CLI by another checksum": (EVAL_WORKFLOW.replace('CLI_CHECKSUM: "520bc6', 'CLI_CHECKSUM: "000000'),
                                            "its install step is given under env"),
            "the model's credential at the install": (EVAL_WORKFLOW.replace('          CLI_VERSION: "2.1.306"\n',
                                                                            '          CLI_VERSION: "2.1.306"\n' + model),
                                                      "its install step is given under env"),
            "the CLI's install a module of its own": (EVAL_WORKFLOW.replace(
                install[install.index("        run: |"):], "        run: python3 -m harness.eval.install\n"), "in that order"),
            "the CLI unchecked": (EVAL_WORKFLOW.replace('          echo "${CLI_CHECKSUM}  /tmp/claude" | sha256sum -c\n', ""),
                                  "in that order"),
            "the CLI's block folded": (EVAL_WORKFLOW.replace("        run: |\n          url=", "        run: >\n          url="),
                                       "in that order"),
            "the CLI after the model": (EVAL_WORKFLOW.replace(install, "").replace(
                "      - uses: actions/upload-artifact", install + "      - uses: actions/upload-artifact"), "in that order"),
            "the CLI from another path": (EVAL_WORKFLOW.replace("CLAUDE_CLI: /usr/local/bin/claude", "CLAUDE_CLI: /tmp/claude"),
                                          "its run step is given under env"),
            "a second job": (EVAL_WORKFLOW + "  other:\n    runs-on: ubuntu-24.04\n    timeout-minutes: 5\n"
                                             "    environment: factory-poller\n    steps:\n      - run: make verify\n",
                             "it holds the job eval and no other"),
        }
        for why, (text, words) in broken.items():
            self.assertNotEqual(text, EVAL_WORKFLOW, why)
            self.assertTrue(caught(check_workflows.eval_problems(text), words), why)
        # The install is the one the Run's jobs hold word for word, and a pin with no checksum holds no install at all.
        self.assertIn("\n".join("          " + line for line in check_workflows.CLI_INSTALL_RUN),
                      check_workflows.RUN_JOBS_FILE)
        unpinned = clone({"config/harness.json": json.dumps(dict(load("config/harness.json"), engine=dict(
            load("config/harness.json")["engine"], version="9.9.9")))})
        self.assertTrue(caught(check_workflows.eval_problems(EVAL_WORKFLOW, unpinned), "pins no CLI whose checksum"))
        # Run whole: the shape is held in eval.yml, and no other workflow names its environment, the home or its steps.
        problems = check_workflows.run(clone({".github/workflows/eval.yml": EVAL_WORKFLOW}))
        self.assertEqual(problems, [])
        for line in ("          HELDOUT_OWNER: ${{ secrets.HELDOUT_OWNER }}\n", "          X: ${{ secrets.heldout_app_key }}\n"):
            other = GOOD.replace("      - run: make verify\n", "      - run: make verify\n        env:\n" + line, 1)
            problems = check_workflows.run(clone({".github/workflows/eval.yml": EVAL_WORKFLOW,
                                                  ".github/workflows/other.yml": other}))
            self.assertTrue(caught(problems, "other.yml: line"), (line, problems))
        self.assertTrue(check_workflows.EVAL_ONLY.search("    environment: Factory-Eval"))
        # The model's credential, an organisation secret any branch could read, is named by the model's steps alone.
        other = GOOD.replace("      - run: make verify\n", "      - run: make verify\n        env:\n"
                             "          T: ${{ secrets.claude_code_oauth_token }}\n", 1)
        problems = check_workflows.run(clone({".github/workflows/eval.yml": EVAL_WORKFLOW,
                                              ".github/workflows/other.yml": other}))
        self.assertTrue(caught(problems, "names the model's credential, which only"), problems)
        problems = check_workflows.run(clone({".github/workflows/eval.yml": EVAL_WORKFLOW.replace(
            "      - run: python3 -m harness.eval.fetch\n", "      - run: python3 -m harness.eval.fetch\n        id: x\n")}))
        self.assertTrue(caught(problems, "eval.yml: its fetch step"), problems)
        # The Maintainer's token, in another workflow under its one name, in any case, is the eval job's alone.
        other = GOOD.replace("      - run: make verify\n", "      - run: make verify\n        env:\n"
                             "          T: ${{ secrets.Heldout_Token }}\n", 1)
        problems = check_workflows.run(clone({".github/workflows/eval.yml": EVAL_WORKFLOW,
                                              ".github/workflows/other.yml": other}))
        self.assertTrue(caught(problems, "other.yml: line"), problems)

    def test_the_review_intents_eval_set_has_its_cases(self):
        # Decision 0010: an Intent family is cut over only after its eval set exists. The cases are written in the
        # private home by a session opened there, and this manifest then carries their hashes (issue 183). Twenty cases
        # with a Finding and as many of a change that was right: forty at least. The manifest keeps no count of a kind,
        # since a session here cannot read a case to hold it true; the eval job holds the split where the cases are
        # (decision 0120).
        manifest = json.loads(SET.read_text())
        self.assertGreaterEqual(manifest["count"], 40)

    @pending
    def test_a_fresh_agent_given_the_repo_adds_a_rule_and_passes_the_check(self):
        # Decision 0013 and docs/context-engineering.md: the context's test (issue 8, decision 0129). The runs are made at
        # the Maintainer's terminal by tools/context_eval.sh and recorded in evals/context/task.json; this holds the record:
        # the sha256 of the task sentence and of the held-out answer, never the sentence, so the rule is named nowhere
        # here (the Maintainer's choice), and the newest three runs on that sentence all passed, each adding a test, a
        # mutant and the sentence's reason code. Until the runs are recorded the hashes are null, and this fails.
        known = eval_result.schemas()
        record = load("evals/context/task.json")
        self.assertEqual(validate(record, known["context-eval"], schemas=known), [])
        self.assertIsInstance(record["task_sha256"], str)
        self.assertIsInstance(record["held_out_sha256"], str)
        runs = record["runs"]
        self.assertGreaterEqual(len(runs), 3)
        newest = sorted(runs, key=lambda r: r["ran_at"])[-3:]
        self.assertTrue(all(r["passed"] for r in newest), [r["verdicts"] for r in newest])
        script = (ROOT / "tools" / "context_eval.sh").read_text()
        pin, cap = re.search(r"^PIN=(\S+)$", script, re.M).group(1), int(re.search(r"^CAP=(\d+)$", script, re.M).group(1))
        for r in newest:
            # A run passes on its three verdicts and having looked nowhere outside its export (issue 511).
            self.assertEqual(r["passed"], r["verdicts"] == {"held_out_test": "pass", "verify": "pass", "mutant": "killed"}
                             and r["outside_reads"] == 0 and r["unread_commands"] == 0)
            self.assertEqual((r["cli_version"], r["cap_turns"]), (pin, cap))
            self.assertEqual(r["task_sha256"], record["task_sha256"], "a run on another sentence")
            self.assertEqual(r["added"], {"test": True, "mutant": True, "reason": True})
            # The agent changed the Kernel, tests and the mutants' list alone, and dropped nothing from the list.
            for change in r["changed"]:
                self.assertTrue(change["path"].startswith(("kernel/", "tests/")) or change["path"] == "tools/mutants.py", change)
                if change["path"] == "tools/mutants.py":
                    self.assertEqual(change["removed"], 0)
            self.assertEqual(r["restored"], [])


class EvalJob(unittest.TestCase):
    """The eval job's steps (issue 309), run against a stand-in home and a stand-in reviewer: a synthetic case, made
    from examples/, stands in for the home's; nothing of the home is in this repo."""

    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.dir.name)
        self.root, self.work, self.temp = base / "root", base / "work", base / "temp"
        for place in (self.root, self.work, self.temp):
            place.mkdir()
        one = load("examples/eval-case.json")
        # A case's facts name the content its diff is, as the set's must.
        one["facts"]["content_id"] = "sha256:" + hashlib.sha256(one["diff"].encode()).hexdigest()
        two = dict(copy.deepcopy(one), id="poc-two")
        self.cases = {c["id"]: (json.dumps(c, indent=2) + "\n").encode() for c in (one, two)}
        self.set(self.cases)
        self.env = {"RELEASE": "factory/v0.1.0", "GITHUB_SHA": "a" * 40, "RUNNER_TEMP": str(self.temp),
                    "HELDOUT_OWNER": "o", "HELDOUT_REPO": "home"}
        # These sets stand in with two cases of one kind: the test of the split sets its own least.
        from harness import eval as job
        blocking_least = mock.patch.object(job, "BLOCKING_LEAST", 0)
        blocking_least.start()
        self.addCleanup(blocking_least.stop)
        least = mock.patch.object(job, "KIND_LEAST", 0)
        least.start()
        self.addCleanup(least.stop)

    def tearDown(self):
        self.dir.cleanup()

    def clean(self) -> None:
        """A run's scratch and its heads, apart from it (issue 623), removed for the next run."""
        for folder in ("heldout", "heads"):
            shutil.rmtree(str(self.temp / folder), ignore_errors=True)

    def set(self, cases: dict) -> None:
        import hashlib
        manifest = {"schema": "eval-set/1", "role": "pr-review", "intent": "review-change", "count": len(cases),
                    "cases": [{"id": i, "sha256": hashlib.sha256(d).hexdigest()} for i, d in cases.items()]}
        (self.root / "evals" / "pr-review").mkdir(parents=True, exist_ok=True)
        (self.root / "evals" / "pr-review" / "cases.json").write_text(json.dumps(manifest, indent=2) + "\n")

    def step(self, step, *given, env=None):
        from harness import eval as job
        if getattr(step, "__module__", None) == job.__name__ and getattr(step, "__name__", None) == "fetch" \
                and len(given) == 1:
            given += (Heads(),)     # each case's head, read as codeload would answer it (decision 0138)
        try:
            return step(dict(self.env, **(env or {})), self.root, self.work, *given)
        except job.Stop as stop:
            return stop.code

    def home(self, cases: dict):
        from adapters import github
        from tests.test_adapters import home_file
        return github.Replay([home_file(i, d) for i, d in cases.items()])

    def test_a_set_of_no_case_ends_the_run_before_anything_is_read(self):
        import os
        # Ruling 8: a set of no case ends the run, which says so and makes nothing, not even the scratch.
        from harness import eval as job
        self.set({})
        self.assertEqual(self.step(job.plan), "eval_set_empty")
        self.assertEqual(list(self.temp.iterdir()), [])
        self.set(self.cases)
        for env, code in (({"RELEASE": "v0.1.0"}, "release_unreadable"), ({"RELEASE": None}, "release_unreadable"),
                          ({"GITHUB_SHA": "a" * 39}, "commit_unreadable"),
                          # A relative path is refused, even one to a directory that could be the scratch.
                          ({"RUNNER_TEMP": os.path.relpath(str(self.temp))}, "scratch_unreadable"),
                          ({"RUNNER_TEMP": str(self.work)}, "scratch_in_workspace"),
                          ({"RUNNER_TEMP": str(self.work / "deeper")}, "scratch_in_workspace")):
            self.assertEqual(self.step(job.plan, env=env), code, env)
        # And a workspace that is the scratch, or inside it.
        for work in (self.temp / "heldout", self.temp / "heldout" / "sub"):
            self.assertEqual(self.step_at(job.plan, work), "scratch_in_workspace", work)
        # A manifest that is no eval-set/1, or miscounts its cases, or names one id twice, is no set.
        manifest = json.loads((self.root / "evals" / "pr-review" / "cases.json").read_text())
        for broken in ({"schema": "eval-set/1", "count": 3}, dict(manifest, count=3),
                       dict(manifest, cases=[manifest["cases"][0], dict(manifest["cases"][0], sha256="0" * 64)])):
            (self.root / "evals" / "pr-review" / "cases.json").write_text(json.dumps(broken))
            self.assertEqual(self.step(job.plan), "eval_set_unreadable", broken)
        self.assertEqual(list(self.temp.iterdir()), [])

    def step_at(self, step, work):
        from harness import eval as job
        try:
            return step(dict(self.env), self.root, work)
        except job.Stop as stop:
            return stop.code

    def test_each_case_is_fetched_into_the_scratch_and_scored_and_only_the_report_reaches_the_workspace(self):
        from harness import eval as job
        result = example_result()
        self.assertEqual(self.step(job.plan), "planned 2 cases")
        self.assertEqual(self.step(job.fetch, self.home(self.cases)), "fetched 2 of 2 cases")
        kept = self.temp / "heldout" / "cases"
        self.assertEqual(sorted(p.name for p in kept.iterdir()), sorted("%s.json" % i for i in self.cases))
        self.assertEqual({p.stat().st_mode & 0o777 for p in kept.iterdir()}, {0o600})
        asked = []
        self.assertEqual(self.step(job.score, lambda case: asked.append(case["id"]) or result),
                         "scored 2 of 2 cases, 2 passed")
        self.assertEqual(asked, list(self.cases))
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), [job.REPORT])
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual(validate(written, load("schemas/eval-report.schema.json"), schemas=eval_result.schemas()), [])
        self.assertEqual((written["passed"], written["commit"], written["release"]), (2, "a" * 40, "factory/v0.1.0"))
        self.assertNotIn("diff", (self.work / job.REPORT).read_text())
        self.assertEqual(self.step(job.judge), "2 of 2 passed; no code")

    def test_a_pass_at_an_alternate_place_alone_is_marked_in_the_report_and_counted(self):  # decision 0143
        # How much of a score `also_at` gave can be counted from the report, by a mark that says no place.
        from harness import eval as job
        one = json.loads(next(iter(self.cases.values())))
        two = dict(copy.deepcopy(one), id="poc-alternate")
        two["expected"]["finding"].update(location={"path": "kernel/decide.py", "start_line": 87, "end_line": 88},
                                          also_at=[{"path": "kernel/decide.py", "start_line": 86}])
        # A case that names an alternate place but is passed at its `location` is not marked.
        one["expected"]["finding"]["also_at"] = [{"path": "kernel/decide.py", "start_line": 88}]
        cases = {c["id"]: (json.dumps(c, indent=2) + "\n").encode() for c in (one, two)}
        self.set(cases)
        self.step(job.plan)
        self.step(job.fetch, self.home(cases))
        result = example_result()
        result["findings"][0]["location"] = {"path": "kernel/decide.py", "start_line": 86, "end_line": 86}
        self.assertEqual(self.step(job.score, lambda case: result), "scored 2 of 2 cases, 2 passed")
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual(validate(written, load("schemas/eval-report.schema.json"), schemas=eval_result.schemas()), [])
        self.assertEqual({c["id"]: c.get("at_alternate") for c in written["cases"]}, {one["id"]: None, two["id"]: True})
        self.assertEqual(self.step(job.judge), "2 of 2 passed, 1 at an alternate place; no code")
        # Only a pass is marked: the job writes no mark on any other, and the gate refuses a report that holds one.
        found, digest = job.manifest(self.root)
        kept = {"release": "factory/v0.1.0", "commit": "a" * 40, "set": {"count": 2, "sha256": digest}}
        assessed = {one["id"]: ("pass", []), two["id"]: ("fail", ["location_differs"])}
        unmarked = job.report(kept, found, assessed, True, {"finding": True, "met": True}, True, None, {one["id"], two["id"]})
        self.assertEqual([c.get("at_alternate") for c in unmarked["cases"]], [True, None])
        marked = copy.deepcopy(unmarked)
        marked["cases"][1]["at_alternate"] = True
        self.assertEqual(job.verdict(marked, found, digest, "a" * 40, "factory/v0.1.0"), "count_differs")
        self.assertIn(", 1 at an alternate place;", job.tally(marked))
        self.assertEqual(job.verdict(unmarked, found, digest, "a" * 40, "factory/v0.1.0"), "pass")
        for mark in (False, 1):
            self.assertNotEqual(validate(dict(unmarked, cases=[dict(unmarked["cases"][0], at_alternate=mark), unmarked["cases"][1]]),
                                         load("schemas/eval-report.schema.json"), schemas=eval_result.schemas()), [], mark)

    def test_the_report_counts_each_cases_gating_findings_away_from_the_place(self):  # issue 610
        # How many gating Findings a review put away from every place can be counted from the report, case by case, by a
        # count that says no place; a case with none, or none read, carries none.
        from harness import eval as job
        one = json.loads(next(iter(self.cases.values())))
        two = dict(copy.deepcopy(one), id="poc-surplus")
        cases = {c["id"]: (json.dumps(c, indent=2) + "\n").encode() for c in (one, two)}
        plan, fetch = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch"))
        self.set(cases)
        self.step(plan)
        self.step(fetch, self.home(cases))
        result = example_result()
        far = dict(result["findings"][0], location={"path": "kernel/gate.py", "start_line": 10, "end_line": 12})
        given = {one["id"]: dict(result, findings=result["findings"] + [dict(far, ref="n7")]),
                 two["id"]: dict(result, findings=result["findings"] + [dict(far, ref="n8"), dict(far, ref="n9")])}
        self.assertEqual(self.step(job.score, lambda case: given[case["id"]]), "scored 2 of 2 cases, 1 passed")
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual(validate(written, load("schemas/eval-report.schema.json"), schemas=eval_result.schemas()), [])
        # One away is allowed and still counted, on a pass; two fail, counted; the run's line sums them.
        self.assertEqual({c["id"]: (c["reasons"], c.get("surplus_gating")) for c in written["cases"]},
                         {one["id"]: ([], 1), two["id"]: (["surplus_gating_elsewhere"], 2)})
        self.assertEqual(job.tally(written), "1 of 2 passed, 3 gating away from the place; surplus_gating_elsewhere 1")
        given[one["id"]] = result
        self.step(job.score, lambda case: given[case["id"]])
        self.assertEqual([c.get("surplus_gating") for c in json.loads((self.work / job.REPORT).read_text())["cases"]], [None, 2])
        # The report writes what the scorer counted, on any verdict, and no count of none.
        found, digest = job.manifest(self.root)
        kept = {"release": "factory/v0.1.0", "commit": "a" * 40, "set": {"count": 2, "sha256": digest}}
        assessed = {one["id"]: ("pass", []), two["id"]: ("unreadable", ["schema"])}
        counted = job.report(kept, found, assessed, True, None, True, None, None, {one["id"]: 1, two["id"]: 0})
        self.assertEqual([c.get("surplus_gating") for c in counted["cases"]], [1, None])
        self.assertEqual(validate(counted, load("schemas/eval-report.schema.json"), schemas=eval_result.schemas()), [])
        self.assertEqual(validate(dict(counted, cases=[dict(counted["cases"][0], surplus_gating=0)] + counted["cases"][1:]),
                                  load("schemas/eval-report.schema.json"), schemas=eval_result.schemas()) == [], False)

    def test_a_set_short_of_a_kind_fails_the_run_and_closes_the_gate_saying_no_count(self):  # issue 365
        # Decision 0120: the set must hold KIND_LEAST of each kind, read from the cases fetched, where they are. A set short
        # of a kind fails `judge` by a code alone, and its report, uploaded all the same, says one word of the set, which
        # `verdict`, the Release's gate too, refuses. Neither says how many of a kind.
        from harness import eval as job
        self.assertEqual(job.KIND_LEAST, 0, "as these fixtures set it")
        result = example_result()
        one = json.loads(next(iter(self.cases.values())))
        right = dict(copy.deepcopy(one), id="poc-right",
                     expected={"verdict": "met", "criterion": one["expected"]["criterion"], "finding": None})
        known = eval_result.schemas()
        self.assertEqual(validate(right, known["eval-case"], schemas=known), [])
        mixed = {one["id"]: self.cases[one["id"]], "poc-right": (json.dumps(right, indent=2) + "\n").encode()}
        found = lambda: json.loads((self.root / "evals" / "pr-review" / "cases.json").read_text())
        right_only = {"poc-right": mixed["poc-right"]}
        for least, cases, held in ((1, mixed, True), (2, mixed, False), (1, self.cases, False), (1, right_only, False),
                                   (0, self.cases, True)):
            with self.subTest(least=least, cases=sorted(cases)), mock.patch.object(job, "KIND_LEAST", least):
                self.clean()
                self.set(cases)
                self.step(job.plan)
                self.step(job.fetch, self.home(cases))
                self.assertIs(job.split_ok(found(), self.temp / "heldout"), held)
        # Short of a kind: the run says so by a code alone, and neither the log nor the report holds a count of a kind.
        with mock.patch.object(job, "KIND_LEAST", 1):
            self.clean()
            self.set(self.cases)
            self.step(job.plan)
            self.step(job.fetch, self.home(self.cases))
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(job.main(lambda env, root, work: job.score(dict(self.env), self.root, self.work,
                                                                            lambda case: result)), 0)
                self.assertEqual(job.main(lambda env, root, work: job.judge(dict(self.env), self.root, self.work)), 1)
            self.assertEqual(out.getvalue(), "scored 2 of 2 cases, 2 passed\neval_split_short\n")
            written = json.loads((self.work / job.REPORT).read_text())
            self.assertIs(written["split_ok"], False)
            self.assertEqual(sorted(written), ["blocking_pass", "cases", "commit", "intent", "kinds_pass", "passed", "release", "role",
                                               "schema", "set", "split_ok"], "no count of a kind, nor any field of one")
            self.assertEqual(sorted(written["cases"][0]), ["id", "reasons", "sha256", "verdict"])
            self.assertEqual(self.step(job.judge), "eval_split_short")
        # The answer of a case that is read as no kind, or not read at all, says nothing: its run fails by that case.
        first = next(iter(self.cases))
        for odd in ({"expected": {"verdict": "maybe"}}, {"expected": {"verdict": ["met"]}}, {"expected": None}, []):
            (self.temp / "heldout" / "cases" / ("%s.json" % first)).write_text(json.dumps(odd))
            self.assertIsNone(job.split_ok(found(), self.temp / "heldout"), odd)
        (self.temp / "heldout" / "cases" / ("%s.json" % first)).unlink()
        self.assertIsNone(job.split_ok(found(), self.temp / "heldout"))
        # The set's least is issue 183's, twenty of each.
        least_is = (ROOT / "harness" / "eval" / "__init__.py").read_text()
        self.assertEqual(len(re.findall(r"^KIND_LEAST = 20$", least_is, re.M)), 1)

    def test_a_case_not_read_whole_or_failed_fails_the_run_with_its_report_uploaded(self):
        from harness import eval as job
        result = example_result()
        wrong = copy.deepcopy(result)
        wrong["findings"] = []
        self.step(job.plan)
        first = next(iter(self.cases))
        self.assertEqual(self.step(job.fetch, self.home(dict(self.cases, **{first: b"changed"}))), "fetched 1 of 2 cases")
        self.assertEqual(json.loads((self.temp / "heldout" / "fetched.json").read_text()), {first: "hash_differs", "poc-two": None})
        self.assertFalse((self.temp / "heldout" / "cases" / ("%s.json" % first)).exists())
        # The report and the judge's log say what the scorer said, as codes: a run cannot be read without them, and a
        # case's kind is not worth hiding (decision 0109, on the ruling that closed "Evals: the public report's per-case
        # verdicts can publish each case's kind"). A run under the bar says `case_failed`, and this one's `hash_differs` is `run_fault`.
        self.assertEqual(eval_result.score(load("examples/eval-case.json"), wrong)["reasons"][0], "finding_not_raised")
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(job.main(lambda env, root, work: job.score(dict(self.env), self.root, self.work,
                                                                        lambda case: wrong)), 0)
            self.assertEqual(job.main(lambda env, root, work: job.judge(dict(self.env), self.root, self.work)), 1)
        self.assertEqual(out.getvalue(), "scored 2 of 2 cases, 0 passed\n0 of 2 passed; finding_not_raised 1, hash_differs 1\n"
                                         "run_fault\n")
        written = (self.work / job.REPORT).read_text()
        self.assertEqual([(c["verdict"], c["reasons"]) for c in json.loads(written)["cases"]],
                         [("unreadable", ["hash_differs"]), ("fail", ["finding_not_raised"])])
        # Whatever else wrote the report, no word reaches the log: a reason outside the enum is `report_unreadable`, alone.
        said = json.loads(written)
        said["cases"][1]["reasons"] = ["the model wrote this"]
        (self.work / job.REPORT).write_text(json.dumps(said))
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(job.main(lambda env, root, work: job.judge(dict(self.env), self.root, self.work)), 1)
        self.assertEqual(out.getvalue(), "report_unreadable\n")
        (self.work / job.REPORT).write_text(written)
        self.assertEqual(self.step(job.judge), "run_fault")
        # A set changed since the plan is no set of this run, and a report that is not there passes nothing.
        (self.work / job.REPORT).unlink()
        self.assertEqual(self.step(job.judge), "report_unreadable")
        self.set({first: self.cases[first]})
        self.assertEqual(self.step(job.judge), "eval_set_changed")

    def test_a_case_the_home_does_not_answer_is_unanswered_and_the_rest_are_fetched(self):
        # Each case is written as it is read, one held at a time; one whose read fails however it fails is unanswered,
        # and says nothing of why.
        from harness import eval as job
        first = next(iter(self.cases))
        home = self.home({"poc-two": self.cases["poc-two"]})

        class Failing:
            def send(self, req):
                if first in req["path"]:
                    raise RuntimeError("the home is o/home")
                return home.send(req)
        self.step(job.plan)
        self.assertEqual(self.step(job.fetch, Failing()), "fetched 1 of 2 cases")
        self.assertEqual(json.loads((self.temp / "heldout" / "fetched.json").read_text()), {first: "unanswered", "poc-two": None})

    def test_a_case_that_is_no_case_of_this_set_is_unreadable(self):
        from harness import eval as job
        other = dict(json.loads(next(iter(self.cases.values()))), intent="fix-findings")
        stray = dict(json.loads(next(iter(self.cases.values()))), id="poc-three")
        bare = {"id": "poc-five", "role": "pr-review", "intent": "review-change"}
        cases = {next(iter(self.cases)): (json.dumps(other) + "\n").encode(), "poc-two": b"not json",
                 "poc-three": (json.dumps(dict(stray, id="poc-four")) + "\n").encode(),
                 "poc-five": (json.dumps(bare) + "\n").encode(),
                 "poc-six": (json.dumps(dict(stray, id="poc-six", role="devops-lead")) + "\n").encode(),
                 # JSON that is no object is one of the set's no more than text is: none of them ends the step.
                 "poc-seven": b"3", "poc-eight": b'"facts"', "poc-nine": b"null", "poc-ten": b"true", "poc-eleven": b"[]",
                 # Nested past what the parser reads, whatever Python's limit: it costs that case, not the report of all.
                 "poc-deep": b"[" * 100000 + b"]" * 100000}
        self.set(cases)
        self.step(job.plan)
        self.step(job.fetch, self.home(cases))
        self.step(job.score, lambda case: self.fail("no case of this set is reviewed"))
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual([c["reasons"] for c in written["cases"]],
                         [["not_this_set"], ["schema"], ["not_this_set"], ["not_this_set"], ["not_this_set"]] + [["not_this_set"]] * 5 + [["schema"]])
        self.assertIsNone(job.split_ok({"cases": [{"id": "poc-deep"}]}, self.temp / "heldout"), "a case not read says nothing")

    def test_a_case_off_its_rubric_is_unreadable_by_its_code_and_asks_nothing(self):  # issue 421
        # Where the cases are, at run time: a case whose expected Finding is not as its criterion gives it asks nothing of
        # the model, and counts as not passing by a code alone, naming neither the severity nor the category. Its owner
        # mends it in the home; nothing here holds what it expected.
        from harness import eval as job
        first = next(iter(self.cases))
        off = json.loads(self.cases[first])
        off["expected"]["finding"]["category"] = "delivery"
        cases = dict(self.cases, **{first: (json.dumps(off, indent=2) + "\n").encode()})
        self.set(cases)
        self.step(job.plan)
        self.step(job.fetch, self.home(cases))
        asked = []
        self.step(job.score, lambda case: asked.append(case["id"]) or example_result())
        self.assertEqual(asked, ["poc-two"], "the case off its rubric is never given to the review")
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual(validate(written, load("schemas/eval-report.schema.json"), schemas=eval_result.schemas()), [])
        self.assertEqual([(c["id"], c["verdict"], c["reasons"]) for c in written["cases"]],
                         [(first, "unreadable", ["answer_off_rubric"]), ("poc-two", "pass", [])])
        self.assertNotIn("delivery", (self.work / job.REPORT).read_text())
        # The bar weighs it as one case not passed: 1 of 2 that expect a Finding clears it.
        self.assertEqual(self.step(job.judge), "1 of 2 passed; answer_off_rubric 1")

    def test_the_fetch_step_takes_its_token_from_its_environment_alone(self):
        from harness import eval as job
        import importlib
        step = importlib.import_module("harness.eval.fetch")     # the module, not the function it calls
        for token in ("", None, "two words"):
            with self.assertRaises(job.Stop) as stopped:
                step.transport({"HELDOUT_TOKEN": token})
            self.assertEqual(stopped.exception.code, "token_unreadable")
        # The token reads, and never writes: a request that is not a bare GET is refused before it is sent.
        from adapters import github
        sent = []

        class Stand:
            def send(self, req):
                sent.append(req["method"])
                return {"status": 200, "headers": {}, "body": {}}
        read = step.ReadOnly(Stand())
        self.assertEqual(read.send(github.request("GET", "/repos/o/home/contents/pr-review/c.json"))["status"], 200)
        for req in (github.request("PUT", "/repos/o/home/contents/x", body={"content": ""}),
                    github.request("DELETE", "/repos/o/home/contents/x"), dict(github.request("GET", "/x"), body={}), None):
            with self.assertRaises(github.Unanswered):
                read.send(req)
        self.assertEqual(sent, ["GET"])
        self.assertIsInstance(step.transport({"HELDOUT_TOKEN": "t0ken"}), step.ReadOnly)

    def test_the_gate_passes_only_this_sets_report_on_this_commit_for_this_release(self):
        from harness import eval as job
        found, digest = job.manifest(self.root)
        good = job.report({"release": "factory/v0.1.0", "commit": "a" * 40, "set": {"count": 2, "sha256": digest}},
                          found, {i: ("pass", []) for i in self.cases}, True, {"finding": True, "met": True}, True)
        self.assertEqual(job.verdict(good, found, digest, "a" * 40, "factory/v0.1.0"), "pass")

        def changed(**change):
            return dict(copy.deepcopy(good), **change)
        first = good["cases"][0]
        for document, code in ((changed(schema="eval-report/2"), "report_unreadable"),
                               (changed(commit="b" * 40), "another_commit"),
                               (changed(release="factory/v0.1.1"), "another_release"),
                               (changed(set={"count": 2, "sha256": "0" * 64}), "another_set"),
                               (changed(intent="fix-findings"), "another_set"),
                               (changed(cases=good["cases"][:1]), "cases_differ"),
                               (changed(cases=[first, dict(first, verdict="fail")]), "cases_differ"),
                               (changed(cases=[first, dict(good["cases"][1], sha256="0" * 64)]), "cases_differ"),
                               (changed(cases=[first, dict(good["cases"][1], verdict="fail", reasons=["schema"])]),
                                "run_fault"),
                               (changed(cases=[first, dict(good["cases"][1], reasons=["schema"])]), "run_fault"),
                               (changed(cases=[first, dict(good["cases"][1], reasons=["finding_uncited"])]), "count_differs"),
                               # A case not passed with its code is the job's, and counts against its kind's bar.
                               (changed(cases=[first, dict(good["cases"][1], verdict="fail", reasons=["finding_uncited"])], passed=1,
                                        kinds_pass={"finding": False, "met": True}), "case_failed"),
                               (changed(cases=[first, dict(good["cases"][1], verdict="unreadable", reasons=["not_this_set"])], passed=1,
                                        kinds_pass={"finding": False, "met": True}), "case_failed"),
                               # What the job never writes is no report of the job's: a case not passed with no code.
                               (changed(cases=[first, dict(good["cases"][1], verdict="fail")], passed=1), "count_differs"),
                               (changed(cases=[first, dict(good["cases"][1], verdict="unreadable")], passed=1), "count_differs"),
                               (changed(role="devops-lead"), "another_set"),
                               (changed(passed="2"), "report_unreadable"),
                               (changed(passed=1), "count_differs")):
            self.assertEqual(job.verdict(document, found, digest, "a" * 40, "factory/v0.1.0"), code, code)
        empty = dict(found, count=0, cases=[])
        self.assertEqual(job.verdict(changed(set={"count": 0, "sha256": digest}, cases=[], passed=0), empty, digest,
                                     "a" * 40, "factory/v0.1.0"), "eval_set_empty")

    def test_the_gate_holds_each_kinds_bar_and_a_fault_still_closes_it(self):  # decisions 0120 and 0150
        from harness import eval as job
        found_of = lambda count: {"role": "pr-review", "intent": "review-change", "count": count,
                                  "cases": [{"id": "c-%d" % i, "sha256": "%064x" % i} for i in range(count)]}

        def read(count, passed, kinds=None, others=(("fail", ["criterion_not_met"]),), blocking=True, held=True):
            """The verdict on a report of `count` cases, the first `passed` passed and the rest as `others` says in turn."""
            found = found_of(count)
            assessed = {c["id"]: ("pass", []) if i < passed else others[i % len(others)] for i, c in enumerate(found["cases"])}
            told = {"finding": True, "met": True} if kinds is None else kinds
            document = job.report({"release": "factory/v0.1.0", "commit": "a" * 40, "set": {"count": count, "sha256": "0" * 64}},
                                  found, assessed, held, told, blocking)
            return job.verdict(document, found, "0" * 64, "a" * 40, "factory/v0.1.0")
        # The set's share is no bar of its own: each kind clearing its bar, a set clears at the lowest of them, 30%, and
        # just under it no report of the job's could say each kind cleared, whatever the size.
        for count, least in ((10, 3), (20, 6), (40, 12), (42, 13), (39, 12), (1, 1)):
            self.assertEqual(read(count, least), "pass", (count, least))
            self.assertEqual(read(count, least - 1), "case_failed", (count, least))
        self.assertEqual(read(42, 42), "pass")
        self.assertEqual(read(40, 35), "pass", "under 0120's 90% of the set, which no longer holds")
        # Where the split held, each kind holds KIND_LEAST cases, so the fewest passes the two words allow are 90% of
        # those clean ones and 30% of the rest: a report claiming both with fewer is not passed, as 12 of 40 is not.
        with mock.patch.object(job, "KIND_LEAST", 20):
            for count, least in ((40, 24), (50, 27), (41, 25)):
                self.assertEqual(read(count, least), "pass", (count, least))
                self.assertEqual(read(count, least - 1), "case_failed", (count, least))
            self.assertEqual(read(40, 12, blocking=False), "case_failed", "the report the security pass made")
            self.assertEqual(job.least_passed(40, 20), 24)
            # A report whose split did not hold is held to the lowest bar of the whole set, and is short all the same.
            self.assertEqual(read(40, 12, held=False), "eval_split_short")
            self.assertEqual(read(40, 11, held=False), "case_failed")
        # The fewest follow the bars, wherever they are set, and a set too small for the split has no least.
        with mock.patch.object(job, "BAR_OF_A_KIND", {"met": (1, 2), "finding": (4, 5)}):
            self.assertEqual(job.least_passed(40, 10), 23, "the rest of the set in the clean kind, whose bar asks fewer")
        self.assertEqual(job.least_passed(30, 20), 9)
        # A word for each kind closes it by itself, every case passed; a report that can't say is short.
        self.assertEqual(read(10, 10, {"finding": False, "met": True}), "case_failed")
        self.assertEqual(read(10, 10, {"finding": True, "met": False}), "case_failed")
        # A case that expects a blocking Finding and did not pass closes nothing by itself, each kind cleared; a report
        # that can't say of them is short all the same.
        self.assertEqual(read(10, 9, blocking=False), "pass")
        self.assertEqual(read(10, 9, {"finding": False, "met": True}, blocking=False), "case_failed")
        self.assertEqual(read(10, 10, blocking=None), "eval_split_short")
        found = found_of(10)
        document = job.report({"release": "factory/v0.1.0", "commit": "a" * 40, "set": {"count": 10, "sha256": "0" * 64}},
                              found, {c["id"]: ("pass", []) for c in found["cases"]}, True, None, True)
        self.assertEqual(job.verdict(document, found, "0" * 64, "a" * 40, "factory/v0.1.0"), "eval_split_short")
        # A case's own fault counts as not passing, and the bar can hold it.
        own = {"not_this_set", "facts_not_current", "facts_read_short", "diff_unreadable", "diff_not_content", "pusher_unnamed",
               "diff_not_whole", "issue_not_whole", "issue_unreadable", "answer_off_rubric", "answer_disagrees_with_verdict",
               "location_unreadable", "criterion_unknown"}
        for code in own:
            self.assertEqual(read(10, 3, others=(("unreadable", [code]),)), "pass", code)
            self.assertEqual(read(10, 2, others=(("unreadable", [code]),)), "case_failed", code)
        # And so does the reviewer's own: a miss, and an answer the Harness could not read, which a CLI with no answer gives too.
        for code in ("finding_not_raised", "result_not_completed", "criterion_not_met") + eval_result.SURPLUS:
            self.assertEqual(read(10, 9, others=(("fail", [code]),)), "pass", code)
        # What stops the run reaching or trusting a case closes it, however many passed.
        for code in job.RUN_FAULTS:
            self.assertEqual(read(10, 9, others=(("unreadable", [code]),)), "run_fault", code)
        for code in job.ENGINE_FAULTS:
            self.assertEqual(read(10, 9, others=(("unreadable", [code]),)), "engine_fault", code)
        # No code is left out of telling the two apart: each of the report's is a Fault, the reviewer's or a case's own.
        scorer = set(eval_result.MISSES) | set(eval_result.WENT) | set(eval_result.SURPLUS) | {
            "result_not_completed", "coverage_disagrees", "finding_raised_wrongly", "criterion_not_met", "finding_not_in_hunk"}
        self.assertEqual(job.eval_result_codes(), scorer | own | set(job.RUN_FAULTS) | set(job.ENGINE_FAULTS))
        self.assertEqual(own & (set(job.RUN_FAULTS) | set(job.ENGINE_FAULTS)), set())

    def test_each_kind_is_held_to_its_own_bar_where_the_cases_are(self):  # decisions 0120 and 0150
        from harness import eval as job

        def told(finding_cases, finding_passed, met_cases, met_passed):
            place = self.temp / "bar"
            shutil.rmtree(str(place), ignore_errors=True)
            (place / "cases").mkdir(parents=True)
            found, assessed, made = {"cases": []}, {}, [("finding", finding_cases, finding_passed), ("met", met_cases, met_passed)]
            for kind, cases, passed in made:
                for i in range(cases):
                    name = "c-%s-%d" % (kind, i)
                    (place / "cases" / (name + ".json")).write_text(json.dumps({"expected": {"verdict": kind}}))
                    found["cases"].append({"id": name})
                    assessed[name] = ("pass", []) if i < passed else ("fail", ["criterion_not_met"])
            return job.kinds_pass(found, place, assessed)
        # Exactly 30% of the cases that expect a Finding clears, and exactly 90% of the clean ones; one case under does
        # not; each kind by itself.
        for cases in (10, 20, 40):
            finding, met = cases * 3 // 10, cases * 9 // 10
            self.assertEqual(told(cases, finding, cases, met), {"finding": True, "met": True}, cases)
            self.assertEqual(told(cases, finding - 1, cases, met), {"finding": False, "met": True}, cases)
            self.assertEqual(told(cases, finding, cases, met - 1), {"finding": True, "met": False}, cases)
        self.assertEqual(told(7, 3, 11, 10), {"finding": True, "met": True})
        self.assertEqual(told(7, 2, 11, 9), {"finding": False, "met": False})
        # Each kind's bar is its own: a share that clears one does not clear the other.
        self.assertEqual(told(10, 3, 10, 3), {"finding": True, "met": False})
        self.assertEqual(told(10, 9, 10, 9), {"finding": True, "met": True})
        # A kind with no case has nothing to fail here: `split_ok` is what closes on it.
        self.assertEqual(told(0, 0, 5, 5), {"finding": True, "met": True})
        self.assertEqual(told(43, 12, 5, 5)["finding"], False, "27.91% is under the bar, however near")
        self.assertEqual(told(43, 13, 5, 5)["finding"], True)
        self.assertEqual(told(5, 5, 43, 38)["met"], False, "88.37% is under the bar, however near")
        self.assertEqual(told(5, 5, 43, 39)["met"], True)
        # Nearer still, inside the hundredth under each bar.
        self.assertEqual(told(17, 5, 5, 5)["finding"], False, "29.41%")
        self.assertEqual(told(5, 5, 19, 17)["met"], False, "89.47%")
        # A verdict of pass with a code is not passed, and a case not read leaves nothing to say.
        place = self.temp / "bar"
        found = {"cases": [{"id": "c-finding-0"}]}
        self.assertEqual(job.kinds_pass(found, place, {"c-finding-0": ("pass", ["criterion_not_met"])})["finding"], False)
        self.assertIsNone(job.kinds_pass({"cases": [{"id": "c-none"}]}, place, {"c-none": ("pass", [])}))

    def _least_held(self, job):
        """The verdict and the word of a set of this fixture's cases, none of which expects a blocking Finding."""
        plan, fetch = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch"))
        self.clean()
        self.set(self.cases)
        self.step(plan)
        self.step(fetch, self.home(self.cases))
        said = lambda case, result: {"case": case["id"], "verdict": "pass", "reasons": []}
        with mock.patch.object(job, "BLOCKING_LEAST", 1), mock.patch.object(job.eval_result, "score", said):
            self.step(job.score, lambda case: example_result())
            return self.step(job.judge), json.loads((self.work / job.REPORT).read_text())["split_ok"]

    def test_a_missed_blocking_case_is_said_and_closes_nothing_by_itself(self):  # decisions 0120 and 0150
        from harness import eval as job
        plan, fetch = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch"))
        place = self.temp / "blocking"
        (place / "cases").mkdir(parents=True)
        made = {"c-blocking": {"verdict": "finding", "finding": {"severity": "blocking"}}, "c-blocking-2": {"verdict": "finding", "finding": {"severity": "blocking"}},
                "c-major": {"verdict": "finding", "finding": {"severity": "major"}}, "c-met": {"verdict": "met", "finding": None},
                "c-minor": {"verdict": "finding", "finding": {"severity": "minor"}},
                "c-states-less": {"verdict": "finding", "criterion": "PR-2", "finding": {"severity": "major"}},
                "c-met-on-pr-2": {"verdict": "met", "criterion": "PR-2", "finding": None}}
        for name, said in made.items():
            (place / "cases" / (name + ".json")).write_text(json.dumps({"expected": said}))
        found = {"role": "pr-review", "cases": [{"id": name} for name in made]}
        passed = {name: ("pass", []) for name in made}

        def told(**then):
            return job.blocking_pass(found, place, dict(passed, **then))
        miss = ("fail", ["finding_not_raised"])
        self.assertIs(told(), True)
        self.assertIs(told(**{"c-blocking": miss}), False)
        # Every one of them, in either place: one that passed covers no other's miss.
        self.assertIs(told(**{"c-blocking-2": miss}), False)
        # By what it states or what the rubric gives its criterion: one that states less, off its rubric and never asked,
        # does not leave the rule. A clean case on that criterion expects no Finding, so it is the bar's.
        self.assertIs(told(**{"c-states-less": ("unreadable", ["answer_off_rubric"])}), False)
        self.assertIs(told(**{"c-met-on-pr-2": ("fail", ["criterion_not_met"])}), True)
        self.assertIs(told(**{"c-blocking": ("unreadable", ["diff_not_whole"])}), False, "a case's own fault is not passed")
        self.assertIs(told(**{"c-blocking": ("pass", ["finding_not_raised"])}), False)
        # Any other severity, and a clean case, is the bar's to weigh.
        self.assertIs(told(**{"c-major": miss, "c-minor": miss, "c-met": ("fail", ["criterion_not_met"])}), True)
        # A set with none has nothing for the word to hold, and a set must hold one: it is short, by a code and no count.
        self.assertIs(job.blocking_pass({"cases": [{"id": "c-major"}]}, place, passed), True)
        with mock.patch.object(job, "BLOCKING_LEAST", 1):
            self.assertIs(job.split_ok(found, place), True)
            self.assertIs(job.split_ok({"role": "pr-review", "cases": [{"id": "c-major"}, {"id": "c-met"}]}, place), False)
            self.assertIs(job.split_ok({"role": "pr-review", "cases": [{"id": "c-states-less"}, {"id": "c-met"}]}, place), True, "by the rubric")
            self.assertIs(job.split_ok({"role": "pr-review", "cases": [{"id": "c-met-on-pr-2"}, {"id": "c-met"}]}, place), False, "a clean case is none")
        self.assertEqual(self._least_held(job), ("eval_split_short", False))
        # A case not read leaves nothing to say.
        self.assertIsNone(job.blocking_pass({"cases": [{"id": "c-none"}]}, place, {"c-none": ("pass", [])}))
        # Through the job: 23 of 24, each kind cleared, and the one miss is the blocking one. It is said, and the run passes.
        self.clean()
        expected = {"verdict": "finding", "criterion": "PR-2", "finding": {"category": "security", "severity": "blocking",
                    "location": {"path": "kernel/decide.py", "start_line": 86, "end_line": 94}}}
        base = json.loads(next(iter(self.cases.values())))
        cases = {"poc-b%d" % i: (json.dumps(dict(base, id="poc-b%d" % i, expected=expected if i == 0 else base["expected"])) + "\n").encode()
                 for i in range(24)}
        self.set(cases)
        self.step(plan)
        self.step(fetch, self.home(cases))
        said = lambda case, result: {"case": case["id"], "verdict": "fail" if case["id"] == "poc-b0" else "pass",
                                     "reasons": ["finding_not_raised"] if case["id"] == "poc-b0" else []}
        with mock.patch.object(job.eval_result, "score", said):
            self.step(job.score, lambda case: example_result())
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual((written["passed"], written["kinds_pass"]["finding"], written["blocking_pass"]), (23, True, False))
        # The line says so, as 23 of 24 would not.
        self.assertEqual(self.step(job.judge), "23 of 24 passed; finding_not_raised 1; a blocking case not passed")

    def test_the_job_writes_each_kinds_word_and_the_judge_holds_it(self):  # decisions 0120 and 0150
        # Plan, fetch, score and judge over a set of 4 cases that expect a Finding and 20 clean ones: each kind is held to
        # its own bar, 30% and 90%.
        from harness import eval as job
        plan, fetch = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch"))
        finding, met = json.loads(next(iter(self.cases.values()))), None
        for raw in self.cases.values():
            if json.loads(raw)["expected"]["verdict"] == "met":
                met = json.loads(raw)
        met = met or load("examples/eval-case.met.json")
        met["facts"] = dict(met["facts"], content_id="sha256:" + hashlib.sha256(met["diff"].encode()).hexdigest())

        def run(miss):
            self.clean()
            cases = {}
            for i in range(24):
                name = "poc-k%d" % i
                cases[name] = (json.dumps(dict(finding if i < 4 else met, id=name)) + "\n").encode()
            self.set(cases)
            self.step(plan)
            self.step(fetch, self.home(cases))
            said = lambda case, result: {"case": case["id"], "verdict": "fail" if case["id"] in miss else "pass",
                                         "reasons": ["finding_not_raised"] if case["id"] in miss else []}
            with mock.patch.object(job.eval_result, "score", said):
                self.step(job.score, lambda case: example_result())
            return json.loads((self.work / job.REPORT).read_text())
        # A kind under its bar: 1 of 4 that expect a Finding, and the job's own word closes the gate, 21 of 24 passed.
        written = run({"poc-k0", "poc-k1", "poc-k2"})
        self.assertEqual((written["passed"], written["kinds_pass"]), (21, {"finding": False, "met": True}))
        self.assertIs(written["blocking_pass"], True)
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(self.step(job.judge), "case_failed")
        self.assertEqual(out.getvalue(), "21 of 24 passed; finding_not_raised 3; finding under its bar\n")
        # And 17 of 20 clean ones.
        written = run({"poc-k4", "poc-k5", "poc-k6"})
        self.assertEqual((written["passed"], written["kinds_pass"]), (21, {"finding": True, "met": False}))
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(self.step(job.judge), "case_failed")
        self.assertEqual(out.getvalue(), "21 of 24 passed; finding_not_raised 3; met under its bar\n")
        # Each kind on or over its bar, 2 of 4 and 19 of 20: it opens, and the judge says what did not pass.
        written = run({"poc-k0", "poc-k1", "poc-k4"})
        self.assertEqual((written["passed"], written["kinds_pass"]), (21, {"finding": True, "met": True}))
        self.assertEqual(self.step(job.judge), "21 of 24 passed; finding_not_raised 3")

    def test_the_job_reads_and_writes_a_file_of_its_own_directory_alone(self):
        # Every file the job reads or writes is named by one part, a case's id or the step's own, and resolves inside
        # its directory: a name that climbs out, names a sub-path, or reaches out through a link is no file of the job's.
        import os
        from harness import eval as job
        (self.work / "out").mkdir()
        os.symlink(str(self.temp), str(self.work / "link.json"))
        self.assertEqual(job.within(self.work, "eval-report.json"), os.path.realpath(str(self.work / "eval-report.json")))
        for name in ("../eval-report.json", "out/eval-report.json", "link.json", ".hidden", "", None, "a.b.json", "Eval.json"):
            with self.assertRaises(job.Stop) as stopped:
                job.within(self.work, name)
            self.assertEqual(stopped.exception.code, "path_outside", name)

    def reviewed(self):
        """A held-out case of the review Intent, as #183 writes them: its facts name the content its diff is, so its
        Task is a live Run's Task of that content. Made from tests/test_harness.py's change; nothing of the home."""
        from tests import test_harness as live
        case = dict(load("examples/eval-case.json"), id="poc-reviewed", facts=live.facts(), diff=live.DIFF.decode())
        return case, live

    def test_the_facts_the_set_was_made_with_read_as_todays_once_filled(self):  # decision 0105
        # The guard. The set's facts are as facts/1 stood when it was made, d556992; this snapshot is the repo's own
        # example of that commit, holding nothing of the home. Filled by the job's table it must pass today's schema, so
        # that a field made required since fails here until it has a row, or the set is issued again.
        from harness import eval as job
        known = eval_result.schemas()
        then = json.loads((ROOT / "tests" / "facts_as_the_held_out_set_was_made.json").read_text())
        before = validate(then, known["facts"], schemas=known)
        self.assertTrue(before, "the snapshot is of the set's time: it does not pass today's schema unfilled")
        kept = copy.deepcopy(then)
        self.assertEqual(validate(job.current_facts(then), known["facts"], schemas=known), [])
        self.assertEqual(then, kept, "the fill changes a copy")
        # Each row is of a field the schema requires now, and the snapshot lacks: no row outlives its reason.
        facts = known["facts"]
        for field, _, why in job.FACTS_THE_SET_PREDATES:
            self.assertIn(field, facts["required"], field)
            self.assertNotIn(field, then, field)
            self.assertTrue(why, field)
        for field, _, why in job.THREAD_FIELDS_THE_SET_PREDATES:
            self.assertIn(field, facts["properties"]["threads"]["items"]["required"], field)
            self.assertTrue(then["threads"] and all(field not in t for t in then["threads"]), field)
            self.assertTrue(why, field)
        # Take a row away, and the guard says so: a field made required with no row fails here.
        for table in ("FACTS_THE_SET_PREDATES", "THREAD_FIELDS_THE_SET_PREDATES"):
            with mock.patch.object(job, table, getattr(job, table)[1:]):
                self.assertTrue(validate(job.current_facts(then), known["facts"], schemas=known), table)

    def test_a_case_the_set_predates_is_filled_where_it_is_read_and_the_live_path_is_not(self):  # decision 0105
        # Each default is what the field says of a pull request of which nothing is known: never reopened, no review past
        # retention, no ruling on a thread. A field a case gives is its own; the live path still refuses such facts.
        from harness import eval as job
        from harness import task as tasks
        from harness.eval import run as step
        then = json.loads((ROOT / "tests" / "facts_as_the_held_out_set_was_made.json").read_text())
        filled = job.current_facts(then)
        self.assertIsNone(filled["last_reopened_at"])
        self.assertEqual(filled["expired_reviews"], [])
        self.assertEqual({t["ruling"] for t in filled["threads"]}, {None})
        given = dict(then, last_reopened_at="2026-10-01T00:00:00Z", expired_reviews=["r_ABC123"],
                     threads=[dict(then["threads"][0], ruling="accepted")] + then["threads"][1:])
        kept = job.current_facts(given)
        self.assertEqual((kept["last_reopened_at"], kept["expired_reviews"], kept["threads"][0]["ruling"]),
                         ("2026-10-01T00:00:00Z", ["r_ABC123"], "accepted"))
        self.assertEqual(kept["threads"][1]["ruling"], None)
        # Two cases share no default: a list one is filled with is its own.
        job.current_facts(then)["expired_reviews"].append("r_ABC123")
        self.assertEqual(job.current_facts(then)["expired_reviews"], [])
        # What is no facts is left as it is, for the schema to refuse.
        for odd in (None, [], "facts", dict(then, threads="none"), dict(then, threads=None), dict(then, threads=[None])):
            self.assertEqual(job.current_facts(odd) if not isinstance(odd, dict) else job.current_facts(odd)["threads"],
                             odd if not isinstance(odd, dict) else odd["threads"], odd)
        # Nested past what can be copied, facts are handed back for the schema to refuse, and the report is still written.
        deep = dict(then, item=[])
        for _ in range(2000):
            deep["item"] = [deep["item"]]
        self.assertIs(job.current_facts(deep), deep)
        # Through the job as the workflow runs it: a case of the set's time reaches the review, filled, and is scored.
        case, live = self.reviewed()
        old = copy.deepcopy(case)
        for field in ("last_reopened_at", "expired_reviews"):
            del old["facts"][field]
        for thread in old["facts"]["threads"]:
            del thread["ruling"]
        old["facts"]["threads"] = old["facts"]["threads"] or [dict(then["threads"][0])]
        known = eval_result.schemas()
        self.assertTrue(validate(old, known["eval-case"], schemas=known), "as the set's cases read today")
        cases = {old["id"]: (json.dumps(old, indent=2) + "\n").encode()}
        self.set(cases)
        self.step(job.plan)
        self.step(job.fetch, self.home(cases))
        cli = live.CLI(said=live.answer(live.judged(findings=[], effects={})))
        kept_plan = json.loads((self.temp / "heldout" / "plan.json").read_text())
        (self.temp / "heldout" / "plan.json").write_text(json.dumps(dict(kept_plan, planned_at=1000)))
        self.assertEqual(self.step(step.step, cli, lambda: 1000.0, env=live.JOB), "scored 1 of 1 cases, 0 passed")
        self.assertEqual(len(cli.asked()), 1, "the case is asked of the model")
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertNotIn("facts_not_current", json.dumps(written))
        self.assertNotIn("not_this_set", json.dumps(written))
        # The live path does not fill: facts of that time are no facts/1 to it, as they should not be.
        with self.assertRaises(tasks.Refused):
            tasks.from_admission({"role": "pr-review", "intent": "review-change", "content_id": old["facts"]["content_id"]},
                                 old["facts"]["item"], live.RUN, old["facts"], [], load("roles/pr-review.json"), [],
                                 dict(live.config(), release="factory/v0.1.0"), old["diff"].encode())

    def test_the_manifest_holds_a_cases_raw_bytes_and_the_fill_never_touches_them(self):  # decision 0105
        # The id and hash are read of the bytes the home gives, at the fetch, before any fill. A case the fill would read
        # alike is still a changed case, and a filled case is never written back, so neither can pass for the other.
        from harness import eval as job
        plan, fetch = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch"))
        first = next(iter(self.cases))
        raw = json.loads(self.cases[first])
        del raw["facts"]["last_reopened_at"], raw["facts"]["expired_reviews"]
        bytes_of = (json.dumps(raw, indent=2) + "\n").encode()
        cases = {first: bytes_of}
        self.set(cases)
        self.step(plan)
        self.assertEqual(self.step(fetch, self.home(cases)), "fetched 1 of 1 cases")
        given = []
        self.step(job.score, lambda case: given.append(case) or example_result())
        self.assertEqual(len(given), 1, "the case is read as filled")
        self.assertIsNone(given[0]["facts"]["last_reopened_at"])
        # And the scorer reads the filled case too: raw, it would be refused by its schema, and every case would fail.
        self.assertEqual([(c["verdict"], c["reasons"]) for c in json.loads((self.work / job.REPORT).read_text())["cases"]],
                         [("pass", [])])
        # What the scratch holds is what the manifest hashed: the fill is of a copy in memory.
        kept = self.temp / "heldout" / "cases" / ("%s.json" % first)
        self.assertEqual(kept.read_bytes(), bytes_of)
        manifest = json.loads((self.root / "evals" / "pr-review" / "cases.json").read_text())
        self.assertEqual(hashlib.sha256(kept.read_bytes()).hexdigest(), manifest["cases"][0]["sha256"])
        # The same case with its fields already given is another file, whatever the fill would make of the first: the
        # fetch refuses it by its bytes, and it asks nothing.
        import shutil
        self.clean()
        (self.work / job.REPORT).unlink()
        self.step(plan)
        filled = dict(raw, facts=job.current_facts(raw["facts"]))
        self.assertEqual(self.step(fetch, self.home({first: (json.dumps(filled, indent=2) + "\n").encode()})),
                         "fetched 0 of 1 cases")
        self.step(job.score, lambda case: self.fail("a changed case asks nothing"))
        self.assertEqual([c["reasons"] for c in json.loads((self.work / job.REPORT).read_text())["cases"]],
                         [["hash_differs"]])

    def test_what_would_refuse_a_cases_task_says_so_by_a_code_of_its_own(self):  # decision 0105
        # Each is what `harness/task.py` would refuse, read first, so a set that fails says why by a code alone. Each asks
        # nothing of the model, and names nothing of the case.
        from harness import eval as job
        plan, fetch = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch"))
        first = next(iter(self.cases))
        base = json.loads(self.cases[first])
        self.assertIsNone(job.case_fault(base))

        def changed(**facts):
            return dict(copy.deepcopy(base), facts=dict(copy.deepcopy(base["facts"]), **facts))
        short = changed(complete=dict(base["facts"]["complete"], reviews=False))
        unnamed = changed(last_pusher=None)
        spaced = changed(last_pusher="Some Name")
        faults = (("facts_read_short", short), ("diff_unreadable", dict(base, diff="")),
                  ("diff_unreadable", dict(base, diff="\ud800")),
                  ("diff_not_content", dict(base, diff=base["diff"] + "x")),
                  ("diff_not_content", changed(content_id="sha256:" + "0" * 64)),
                  ("pusher_unnamed", unnamed), ("pusher_unnamed", spaced))
        for code, case in faults:
            self.assertEqual(job.case_fault(case), code, code)
        self.assertIsNone(job.case_fault(changed(last_pusher="coderabbitai[bot]")))
        # As task/1's own reader holds it: a login that ends in a new line is none.
        self.assertEqual(job.case_fault(changed(last_pusher="bob\n")), "pusher_unnamed")
        # Each read first: facts read short and an unnamed pusher, on a diff that is also not its content, say the first.
        self.assertEqual(job.case_fault(dict(short, diff=base["diff"] + "x")), "facts_read_short")
        self.assertEqual(job.case_fault(dict(unnamed, diff=base["diff"] + "x")), "diff_not_content")
        # In the job: nothing is asked, and each code stands beside its case, with no word of the case.
        cases = {"poc-%d" % at: (json.dumps(dict(case, id="poc-%d" % at), indent=2) + "\n").encode()
                 for at, (_, case) in enumerate(faults) if case["diff"] != "\ud800"}
        self.set(cases)
        self.step(plan)
        self.step(fetch, self.home(cases))
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(job.main(lambda env, root, work: job.score(dict(self.env), self.root, self.work,
                                                                        lambda case: self.fail("nothing is asked"))), 0)
        written = (self.work / job.REPORT).read_text()
        self.assertEqual([c["reasons"][0] for c in json.loads(written)["cases"]],
                         [code for code, case in faults if case["diff"] != "\ud800"])
        self.assertEqual(validate(json.loads(written), load("schemas/eval-report.schema.json"), schemas=eval_result.schemas()), [])
        self.assertNotIn("Some Name", written + out.getvalue())

    def test_a_diff_over_the_bound_says_so_and_asks_nothing(self):  # decision 0105
        # A Task whose diff is cut is never reviewed in part: without this it read as a case the reviewer failed.
        from harness.eval import run as step
        from harness import eval as job
        case, live = self.reviewed()
        cli = live.CLI()
        env = dict(live.JOB)
        small = dict(step.live.configuration(), max_diff_characters=1)
        with mock.patch.object(step.live, "configuration", lambda *a: small):
            with self.assertRaises(job.Stop) as stopped:
                reviewed(env, "factory/v0.1.0", 0, cli, live.Clock(0.0, 1.0, 2.0))(case)
        self.assertEqual((stopped.exception.code, cli.asked()), ("diff_not_whole", []))
        # And the code reaches the report, not `unanswered`, as the job writes it.
        first = next(iter(self.cases))
        plan, fetch = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch"))
        self.step(plan)
        self.step(fetch, self.home(self.cases))

        def over_the_bound(asked):
            raise job.Stop("diff_not_whole")
        self.step(job.score, over_the_bound)
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual({c["id"]: c["reasons"] for c in written["cases"]}[first], ["diff_not_whole"])

    def test_a_fault_of_the_engine_or_the_factory_is_not_the_reviewers(self):  # decision 0106
        # The first eval on a runner read 42 cases as failed in 8 s: the CLI never started, and each failed Result was
        # scored as the reviewer's. A reason that says the model gave no answer is the case's code, tells nothing of what
        # it expected, fails the run, and says so in a code of its own.
        from harness import engine
        from harness import eval as job
        plan, fetch, judge = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch", "judge"))
        first = next(iter(self.cases))
        usage = example_result()["usage"]
        for reason in job.ENGINE_FAULTS:
            with self.subTest(reason):
                self.clean()
                self.set(self.cases)
                self.step(plan)
                self.step(fetch, self.home(self.cases))
                task = {"run": "r_ABC123", "release": "factory/v0.1.0"}
                failed = engine.failed(task, reason, usage)
                good = example_result()
                self.step(job.score, lambda case: failed if case["id"] == first else good)
                written = json.loads((self.work / job.REPORT).read_text())
                self.assertEqual(validate(written, load("schemas/eval-report.schema.json"), schemas=eval_result.schemas()), [])
                self.assertEqual([(c["verdict"], c["reasons"]) for c in written["cases"]],
                                 [("unreadable", [reason]), ("pass", [])])
                with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                    self.assertEqual(self.step(judge), "engine_fault")
                self.assertEqual(out.getvalue(), "1 of 2 passed; %s 1\n" % reason, "it closes, the kind's bar cleared")
        # The reviewer's own failure stays as it was: a Result it gave that does not pass, and one that cannot be read.
        self.clean()
        self.step(plan)
        self.step(fetch, self.home(self.cases))
        wrong = dict(example_result(), findings=[])
        invalid = engine.failed({"run": "r_ABC123", "release": "factory/v0.1.0"}, "result_invalid", usage)
        self.step(job.score, lambda case: wrong if case["id"] == first else invalid)
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual([c["reasons"] for c in written["cases"]],
                         [["finding_not_raised"], ["result_not_completed", "finding_not_raised", "coverage_disagrees"]])
        self.assertEqual(self.step(judge), "case_failed")
        # A reason the model wrote is the reviewer's, whatever it says: a Result it refused, naming an Engine fault, is
        # no fault of the Engine's, or a case's text could choose the report's code.
        self.clean()
        self.step(plan)
        self.step(fetch, self.home(self.cases))
        said = dict(example_result(), status="refused", reason="engine_failed", findings=[])
        self.step(job.score, lambda case: said)
        report = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual([c["reasons"] for c in report["cases"]],
                         [["result_not_completed", "finding_not_raised"]] * 2)
        self.assertEqual(self.step(judge), "case_failed")
        # One Engine fault among failed cases says so: the run cannot say what the reviewer would have done.
        mixed = copy.deepcopy(written)
        mixed["cases"][1].update(verdict="unreadable", reasons=["engine_failed"])
        found, digest = job.manifest(self.root)
        self.assertEqual(job.verdict(mixed, found, digest, "a" * 40, "factory/v0.1.0"), "engine_fault")
        # A reason the model wrote is never one of these: `status` failed is the Harness's alone. And every reason the
        # Engine or the run can write is told: a new one is one or the other, by a decision.
        said = (ROOT / "harness" / "engine.py").read_text() + (ROOT / "harness" / "run.py").read_text()
        reasons = set(re.findall(r'failed\(task, "([a-z_]+)"', said)) | set(re.findall(r'reason = "([a-z_]+)"', said)) | \
            set(re.findall(r'fault = "([a-z_]+)"', said))
        self.assertGreater(len(reasons), 5)
        self.assertEqual(sorted(reasons - set(job.ENGINE_FAULTS) - {"result_invalid", "diff_not_whole"}), [])
        self.assertNotIn("result_invalid", job.ENGINE_FAULTS)

    def test_a_case_whose_facts_are_not_current_says_so_by_a_code_alone(self):  # decision 0105
        # A case whose facts fail the schema after the fill is told from one of another set, or none: a code of its own,
        # asking nothing of the model, with no field's name in the report or the log.
        from harness import eval as job
        first = next(iter(self.cases))
        short = json.loads(self.cases[first])
        del short["facts"]["mergeable"]
        odd = json.loads(self.cases["poc-two"])
        odd["facts"]["expired_reviews"] = "none"
        other = dict(json.loads(self.cases[first]), id="poc-other", intent="fix-findings")
        bare = {"id": "poc-bare", "role": "pr-review", "intent": "review-change"}
        cases = {first: (json.dumps(short) + "\n").encode(), "poc-two": (json.dumps(odd) + "\n").encode(),
                 "poc-other": (json.dumps(other) + "\n").encode(), "poc-bare": (json.dumps(bare) + "\n").encode()}
        self.set(cases)
        self.step(job.plan)
        self.step(job.fetch, self.home(cases))
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(job.main(lambda env, root, work: job.score(dict(self.env), self.root, self.work,
                                                                        lambda case: self.fail("nothing is asked"))), 0)
        written = (self.work / job.REPORT).read_text()
        self.assertEqual([c["reasons"] for c in json.loads(written)["cases"]],
                         [["facts_not_current"], ["facts_not_current"], ["not_this_set"], ["not_this_set"]])
        self.assertEqual(validate(json.loads(written), load("schemas/eval-report.schema.json"), schemas=eval_result.schemas()), [])
        for field in ("mergeable", "expired_reviews"):
            self.assertNotIn(field, written + out.getvalue(), field)
        self.assertEqual(self.step(job.judge), "case_failed")

    def test_a_case_is_reviewed_by_the_task_and_the_engine_a_live_run_is(self):  # issue 309, ruling 5
        # What is measured is what runs: the case's Task is the one a live Run admitted for the same content is given,
        # but for its Run id, and the CLI is called as a live Run calls it, the Task as data, with the read tools alone.
        from harness import engine, task
        from harness.eval import run as step
        case, live = self.reviewed()
        cli = live.CLI(said=live.answer(live.judged(findings=[], effects={})))
        env = dict(live.JOB, HELDOUT_TOKEN="a-stand-in-held-out-token", HELDOUT_OWNER="o")
        with mock.patch.object(step, "run_id", lambda: live.RUN):
            result = reviewed(env, "factory/v0.1.0", 0, cli, live.Clock(0.0, 1.0, 2.0))(case)
        self.assertEqual((result["status"], result["run"]), ("completed", live.RUN))
        asked, = cli.asked()
        given = json.loads(asked["args"][2].split(engine.TASK, 1)[1])
        config = dict(live.config(), release="factory/v0.1.0")
        config["harness"] = live.HARNESS
        manifest = load("roles/pr-review.json")
        self.assertEqual(given, task.build(live.record(), live.RUN, live.facts(), [], manifest, [], config, live.DIFF))
        # With the read tools alone, held to the case's head, the folder it starts in (decision 0138).
        self.assertTrue(engine.read_alone(asked["args"]))
        self.assertEqual(pathlib.Path(asked["head"]).parts[-2:], ("heads", case["id"]))
        # The model's credential reaches the CLI, and nothing of the home: not its token, nor where it is.
        self.assertEqual(asked["env"]["CLAUDE_CODE_OAUTH_TOKEN"], live.TOKEN)
        self.assertFalse([k for k in asked["env"] if k.startswith("HELDOUT")])
        self.assertNotIn("a-stand-in-held-out-token", json.dumps(cli.calls))

    def test_every_code_the_scorer_gives_is_one_the_report_may_carry(self):  # decision 0120
        # A code the enum lacks would make the whole report unreadable, and the run would say so and nothing else.
        from harness import eval as job
        source = (ROOT / "tools" / "eval_result.py").read_text()
        given = set(re.findall(r'"reasons": \["([a-z_]+)"\]|reasons\.append\("([a-z_]+)"\)', source))
        codes = {code for pair in given for code in pair if code} | set(eval_result.MISSES) | set(eval_result.WENT)
        self.assertGreater(len(codes), 10)
        self.assertEqual(codes - job.eval_result_codes() - {"file", "file_outside"}, set())
        self.assertNotIn("case_failed", job.eval_result_codes())

    def test_the_judges_line_counts_the_cases_passed_and_each_code(self):
        from harness import eval as job
        cases = [{"verdict": "pass", "reasons": []}, {"verdict": "fail", "reasons": ["criterion_not_met"]},
                 {"verdict": "fail", "reasons": ["criterion_not_met", "coverage_disagrees"]}]
        cleared = {"kinds_pass": {"finding": True, "met": True}, "blocking_pass": True}
        self.assertEqual(job.tally(dict(cleared, passed=1, cases=cases)), "1 of 3 passed; coverage_disagrees 1, criterion_not_met 2")
        self.assertEqual(job.tally(dict(cleared, passed=0, cases=[{"verdict": "fail", "reasons": []}])), "0 of 1 passed; no code")
        # Which of its words closed the gate, and a blocking case not passed, which does not by itself, as the share may not
        # say; a report that can't say names nothing.
        self.assertEqual(job.tally(dict(passed=1, cases=cases, kinds_pass={"finding": False, "met": False}, blocking_pass=False)),
                         "1 of 3 passed; coverage_disagrees 1, criterion_not_met 2; finding under its bar; met under its bar; "
                         "a blocking case not passed")
        self.assertEqual(job.tally(dict(passed=1, cases=cases, kinds_pass=None, blocking_pass=None)),
                         "1 of 3 passed; coverage_disagrees 1, criterion_not_met 2")

    def test_a_case_the_scorer_cannot_read_is_unreadable_in_the_report(self):
        # What the scorer calls unreadable is no failure of the reviewer's, and the report says so by the scorer's verdict.
        from harness import eval as job
        first, kept = next(iter(self.cases.items()))
        one = json.loads(kept)
        one["expected"] = dict(one["expected"], criterion="PR-99")
        cases = {first: (json.dumps(one) + "\n").encode()}
        self.set(cases)
        self.step(job.plan)
        self.step(job.fetch, self.home(cases))
        self.step(job.score, lambda case: example_result())
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual([(c["verdict"], c["reasons"]) for c in written["cases"]], [("unreadable", ["criterion_unknown"])])
        self.assertEqual(self.step(job.judge), "case_failed")

    def test_the_canary_installs_the_block_the_jobs_hold(self):  # decision 0106
        # Word for word what the eval job and the Run's jobs run, at the pin and by its checksum: a line taken from them
        # is taken from the check, which a copy in the canary's workflow would not notice.
        from harness.eval import canary
        from tools import check_workflows
        calls = []

        def run(args, env, check):
            calls.append((args, env, check))
            return mock.Mock(returncode=7)
        pin = load("config/harness.json")["engine"]["version"]
        self.assertEqual(canary.install({"PATH": "/bin"}, run), 7)
        (args, env, check), = calls
        self.assertEqual(args, ["bash", "-e", "-c", "\n".join(check_workflows.CLI_INSTALL_RUN)])
        self.assertIn("sudo apt-get update -q\nsudo apt-get install -y --no-install-recommends bubblewrap", args[3])
        self.assertEqual(env, {"PATH": "/bin", "CLI_VERSION": pin, "CLI_CHECKSUM": check_workflows.CLI_CHECKSUMS[pin]})
        self.assertFalse(check)

    def test_the_canary_is_red_unless_the_cli_answered(self):  # decision 0106
        from harness.eval import canary, run as step
        from tests import test_harness as live

        class Said(live.CLI):
            """The CLI, with the stderr `harness/run.cli_call` always captures."""

            def __call__(self, args, env, timeout, **given):
                done = super().__call__(args, env, timeout)
                # The credential is cut across by where the end of it begins: taken out after the cut, a piece would be left.
                last = "error: bubblewrap is required"
                done.stderr = "x" * canary.TAIL + live.TOKEN + "x" * (canary.TAIL - 9 - len(last)) + last
                return done

        def checked(cli, env=None):
            out = io.StringIO()
            with mock.patch.object(step, "run_id", lambda: live.RUN), mock.patch("sys.stdout", out):
                code = canary.review(dict(live.JOB) if env is None else env, cli, live.Clock(*[float(i) for i in range(9)]),
                                     Heads())
            return code, out.getvalue()
        # An answer the eval's path read and scored is green, on the repo's own case and by one call of the model.
        answered = Said(said=live.answer(live.judged(findings=[], effects={})))
        code, said = checked(answered)
        self.assertEqual((code, len(answered.asked())), (0, 1), said)
        self.assertIn("status completed", said)
        # A healthy CLI's stderr stays out of a public log: only a failing one's is any use.
        self.assertNotIn("bubblewrap is required", said)
        # A model that refused or gave up has answered: that is the eval's matter, and the Engine is sound.
        for status, reason in (("incomplete", "change_not_reviewed_whole"), ("refused", "task_not_a_review")):
            code, said = checked(Said(said=live.answer(live.judged(status=status, reason=reason, findings=[], effects={}))))
            self.assertEqual(code, 0, said)
            self.assertIn("status %s" % status, said)
        # A CLI that failed is red, and says the end of what it said, which names the cause, and no more of it.
        code, said = checked(Said(said="", returncode=1))
        self.assertEqual(code, 1)
        self.assertIn("error: bubblewrap is required", said)
        self.assertIn("engine_failed", said)
        self.assertNotIn("x" * canary.TAIL, said)
        self.assertNotIn(live.TOKEN[-9:], said)
        self.assertIn("***", said)
        # An answer the Harness cannot read, a CLI at another version and no credential are each red.
        for cli, env in ((Said(said="not a result"), None), (Said(versions=("9.9.9", "9.9.9")), None),
                         (Said(), {k: v for k, v in live.JOB.items() if k != "CLAUDE_CODE_OAUTH_TOKEN"})):
            code, said = checked(cli, env)
            self.assertEqual(code, 1, said)
        # What never reached the model is red whatever is said of it, and a case the review raised on is unanswered.
        with mock.patch.object(step, "reviewer", lambda *given: lambda case: (_ for _ in ()).throw(ValueError())):
            code, said = checked(Said())
        self.assertEqual(code, 1)
        self.assertIn("unanswered", said)

    def test_a_case_that_holds_its_issue_gives_it_to_the_task_as_a_live_run_is(self):  # decision 0110
        from harness import engine, eval as job, task
        from harness.eval import run as step
        case, live = self.reviewed()
        by = {"kind": "human", "name": "a-colleague", "can_write": False}
        held = dict(case, issue={"number": 12, "by": by, "body": "Return early when the list is empty."})
        self.assertEqual(validate(held, load("schemas/eval-case.schema.json"), schemas=eval_result.schemas()), [])
        cli = live.CLI(said=live.answer(live.judged(findings=[], effects={})))
        with mock.patch.object(step, "run_id", lambda: live.RUN):
            reviewed(dict(live.JOB), "factory/v0.1.0", 0, cli, live.Clock(0.0, 1.0, 2.0))(held)
        asked, = cli.asked()
        given = json.loads(asked["args"][2].split(engine.TASK, 1)[1])
        config = dict(live.config(), release="factory/v0.1.0")
        config["harness"] = live.HARNESS
        text = {"id": "issue:12", "by": by, "body": held["issue"]["body"]}
        self.assertEqual(given, task.build(live.record(), live.RUN, live.facts(), [text], load("roles/pr-review.json"), [], config, live.DIFF))
        # Its class is read from who wrote it, never from the case, and a case with none holds the diff alone.
        self.assertEqual([(t["id"], t["trust"], t["source"]) for t in given["texts"] if t["id"].startswith("issue:")],
                         [("issue:12", "outside", "a-colleague")])
        # Whoever opened it: anyone who can write can edit its body, so its opener's name is no label for what it says.
        config_of = dict(live.config(), release="factory/v0.1.0")
        mine = {"id": "issue:12", "by": live.MAINTAINER, "body": "x"}
        self.assertEqual(task.class_of(mine, config_of), "outside")
        self.assertEqual(task.class_of(dict(mine, id="thread:PRRT_kw1"), config_of), "maintainer")
        # An issue no Task can carry whole, and one whose writer no Task can name, say so by a code and ask nothing.
        too_long = dict(case, issue=dict(held["issue"], body="x" * (live.HARNESS["texts"]["characters"] + 1)))
        cli = live.CLI()
        with self.assertRaises(job.Stop) as stopped:
            reviewed(dict(live.JOB), "factory/v0.1.0", 0, cli, live.Clock(0.0))(too_long)
        self.assertEqual((stopped.exception.code, cli.asked()), ("issue_not_whole", []))
        spaced = dict(case, issue=dict(held["issue"], by=dict(by, name="a colleague")))
        self.assertEqual(job.case_fault(spaced), "issue_unreadable")
        self.assertIsNone(job.case_fault(held))

    def test_a_cli_with_no_answer_is_the_engines_and_closes_the_gate(self):  # decision 0121
        from harness import eval as job
        from harness.eval import run as step
        case, live = self.reviewed()
        for said in ("", "not json", json.dumps({"is_error": False})):
            with mock.patch.object(step, "run_id", lambda: live.RUN):
                result = reviewed(dict(live.JOB), "factory/v0.1.0", 0, live.CLI(said=said), live.Clock(0.0, 1.0, 2.0))(case)
            self.assertEqual((result["status"], result["reason"]), ("failed", "no_answer"), said)
            self.assertIn(result["reason"], job.ENGINE_FAULTS)
        # So through the job it is the case's code, and however many others passed the run is `engine_fault`.
        first = next(iter(self.cases))
        self.step(job.plan)
        self.step(job.fetch, self.home(self.cases))
        self.step(job.score, lambda c: result if c["id"] == first else example_result())
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual({c["id"]: c["reasons"] for c in written["cases"]}[first], ["no_answer"])
        self.assertEqual(self.step(job.judge), "engine_fault")

    def test_the_review_is_told_to_cite_and_what_met_means(self):  # decision 0110
        # Run 41329046436 read 10 cases as `finding_uncited`: the fault was found and no criterion cited. The rubric's ids
        # do not move, and the set's answers hold to them; a logic error plainly falls under PR-3, whose evidence is the
        # diff, as no Task holds test results.
        rubric = {c["id"]: c for c in load("config/rubric-pr-review.json")["criteria"]}
        self.assertEqual(sorted(rubric), ["PR-1", "PR-2", "PR-3", "PR-4", "PR-5"])
        self.assertEqual((rubric["PR-3"]["category"], rubric["PR-3"]["severity_if_violated"]), ("functional", "major"))
        self.assertIn("no logic error", rubric["PR-3"]["statement"])
        self.assertEqual(rubric["PR-3"]["evidence"], "The diff.")
        prompt = (ROOT / "roles" / "pr-review" / "prompt.md").read_text()
        self.assertIn("Cite the criterion whenever the problem falls under one", " ".join(prompt.split()))
        self.assertIn("which includes a change that gives it nothing to break", " ".join(prompt.split()))
        self.assertIn("only when what the criterion judges is not in the Task", " ".join(prompt.split()))
        # Citing the nearest must not move a security fault out of `security`, whose thread `apply` holds apart (decision 0095).
        self.assertIn("A security fault no `security` criterion reaches is cited to none, at category `security`", " ".join(prompt.split()))

    def test_the_review_reads_the_head_places_a_finding_where_a_fix_goes_and_cites_what_it_raises(self):  # 0138
        # The private replay's misses, as counts alone: the right problem placed in another changed file or a few lines
        # off, a Finding cited to no criterion while that criterion was met, and nothing raised with it met. The review
        # is told it reads the head (decision 0138), where a Finding sits, and that its Findings and coverage agree.
        prompt = " ".join((ROOT / "roles" / "pr-review" / "prompt.md").read_text().split())
        for said in ("which you may read with Read, Grep and Glob",
                     "A file left out is not reviewed, though the head holds it",
                     "Read them before you judge the change, not after.",
                     "Each tool call is one of the Task's turns",
                     "A fault that is a removed line sits on the numbered lines of its hunk nearest where it was",
                     "a fault its deletion brings sits on the changed lines of another file that it breaks",
                     "only when what the criterion judges is not in the Task or the head",
                     "the numbers the diff gives the lines where the problem is brought in",
                     "A Finding sits on the changed lines that bring the fault in, the lines a fix would change",
                     "A fault that spans files sits on the change that causes it",
                     "give none only when no criterion of the rubric reaches it, and only after checking each criterion",
                     "A Finding you raise cites the criterion it falls under, the nearest where more than one fits, and that criterion's coverage is `finding`, never `met`",
                     "A security fault that no `security` criterion reaches stays cited to none, at category `security`, "
                     "and counts against no criterion's coverage",
                     "Never `met` on the diff's face alone.",
                     "Each Finding's lines, from `start_line` to `end_line`, are all on one hunk of its file in the diff, "
                     "lines the diff numbers: a Finding on a line you read only in the head, or across two hunks, refuses "
                     "the whole Result, every other Finding with it."):
            self.assertIn(said, prompt)

    def test_a_finding_at_the_line_its_task_numbers_is_where_the_scorer_looks(self):  # decision 0137
        # Run 41718110053 read 7 cases as `location_differs` and 3 as `finding_elsewhere`: the model is now given each
        # head line's number, and a Finding placed by the number the public example's Task shows passes the scorer.
        from harness import engine
        from harness.eval import current_facts, run as step
        from tests import test_harness as live
        case = load("examples/eval-case.json")
        case["facts"] = current_facts(case["facts"])
        case["facts"]["content_id"] = "sha256:" + hashlib.sha256(case["diff"].encode("utf-8")).hexdigest()
        shown = []

        class Reading(live.CLI):
            """The CLI, answering at the line the Task numbers for the check the change moved below its use."""
            def __call__(self, args, env, timeout, **given):
                if args[1:] != ["--version"]:
                    diff = json.loads(args[2].split(engine.TASK, 1)[1])["texts"][0]["body"]
                    shown.extend(int(n) for n in re.findall(r"^(\d+)\|\+    if not items:$", diff, re.M))
                    at = {"path": "kernel/decide.py", "start_line": shown[-1], "end_line": shown[-1]}
                    self.said = live.answer(live.judged(effects={}, findings=[
                        {"ref": "n1", "location": at, "category": "functional", "severity": "major", "criterion": "PR-3"}],
                        coverage=[{"criterion": "PR-3", "verdict": "finding", "reason": None}]))
                return super().__call__(args, env, timeout)

        with mock.patch.object(step, "run_id", lambda: live.RUN):
            result = reviewed(live.JOB, "factory/v0.1.0", 0, Reading(), live.Clock(0.0, 1.0, 2.0))(case)
        # The hunk's header names line 86 first; the moved check is the head's second line, after `first = items[0]`.
        self.assertEqual(shown, [87])
        self.assertEqual(eval_result.score(case, result), {"case": case["id"], "verdict": "pass", "reasons": []})
        # The model is told what the numbers are.
        prompt = " ".join((ROOT / "roles" / "pr-review" / "prompt.md").read_text().split())
        self.assertIn("is led by its line number in the head's file and `|`", prompt)
        self.assertIn("A removed line has no number", prompt)
        self.assertIn("`start_line`, `end_line`, the numbers the diff gives the lines where the problem is", prompt)

    def test_a_case_that_names_other_content_or_comes_too_late_is_not_reviewed(self):  # issue 309, rulings 5 and 9
        from harness.eval import run as step
        from harness import eval as job
        case, live = self.reviewed()
        # A case whose facts do not name the content its diff is, or that is no pull request's, is no case of this
        # set: no Task, and nothing asked of the model.
        for bad in (dict(case, diff=case["diff"] + "+more\n"), dict(case, facts=dict(case["facts"], item={"x": 1})),
                    dict(case, facts=dict(case["facts"], content_id=None))):
            cli = live.CLI()
            with self.assertRaises(job.Stop) as stopped:
                reviewed(live.JOB, "factory/v0.1.0", 0, cli, live.Clock(0.0))(bad)
            self.assertEqual((stopped.exception.code, cli.asked()), ("not_this_set", []))
        # Less time left than a case's tier allows: the step starts no case, and the case is unanswered.
        cli = live.CLI()
        late = live.HARNESS["limits"]["standard"]["seconds"]
        review = reviewed(live.JOB, "factory/v0.1.0", 0, cli, live.Clock(step.BUDGET - late + 1))
        with self.assertRaises(job.Stop) as stopped:
            review(case)
        self.assertEqual((stopped.exception.code, cli.asked()), ("unanswered", []))
        # Less time left than the tier allows and the Engine's two reads of the CLI's version: not started either.
        cli = live.CLI()
        review = reviewed(live.JOB, "factory/v0.1.0", 0, cli, live.Clock(step.BUDGET - late - step.VERSION_READS + 1))
        with self.assertRaises(job.Stop) as stopped:
            review(case)
        self.assertEqual((stopped.exception.code, cli.asked()), ("unanswered", []))
        # With just that time left, it is asked.
        cli = live.CLI(said=live.answer(live.judged(findings=[], effects={})))
        with mock.patch.object(step, "run_id", lambda: live.RUN):
            reviewed(live.JOB, "factory/v0.1.0", 0, cli,
                          live.Clock(step.BUDGET - late - step.VERSION_READS, 1.0, 2.0))(case)
        self.assertEqual(len(cli.asked()), 1)
        # The limit is the case's own tier's, read from the configuration, never a constant.
        from harness import run as running
        longer = running.configuration()
        longer["harness"]["limits"]["standard"]["seconds"] = late * 2
        cli = live.CLI()
        with mock.patch.object(step.live, "configuration", lambda: longer):
            review = reviewed(live.JOB, "factory/v0.1.0", 0, cli, live.Clock(step.BUDGET - late - step.VERSION_READS))
        with self.assertRaises(job.Stop) as stopped:
            review(case)
        self.assertEqual((stopped.exception.code, cli.asked()), ("unanswered", []))
        # The job's time is held inside its timeout, which tools/check_workflows.py holds, counted from when the plan
        # was made, less ten minutes for the checkout before it and the upload and judge after the step.
        from tools import check_workflows
        self.assertEqual(step.BUDGET, (int(check_workflows.EVAL_RUNNER["timeout-minutes"]) - 10) * 60)
        # A diff that cannot be the bytes of any content, a lone surrogate, is no case of this set either.
        cli = live.CLI()
        with self.assertRaises(job.Stop) as stopped:
            reviewed(live.JOB, "factory/v0.1.0", 0, cli, live.Clock(0.0))(dict(case, diff="\ud800"))
        self.assertEqual((stopped.exception.code, cli.asked()), ("not_this_set", []))
        # Only the eval job builds a Task from an admission it holds itself; every other Task is a pass record's.
        callers = sorted(p.relative_to(ROOT).as_posix() for p in walk.files(ROOT) if p.suffix == ".py"
                         and not p.relative_to(ROOT).as_posix().startswith("tests/") and "from_admission(" in p.read_text())
        self.assertEqual(callers, ["harness/eval/run.py", "harness/task.py"])

    def test_the_run_step_writes_the_report_whatever_a_case_raised(self):  # issue 309, ruling 4
        # A case the review raises on is unanswered, one it cannot be asked of is unreadable by its code, and the
        # report of every case is written all the same, so that the upload finds it and judge fails the run.
        from harness import eval as job
        from harness.eval import run as step
        # A step module once imported takes its function's name in the package: each is read through its module too.
        plan, fetch, judge = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch", "judge"))
        self.assertEqual(self.step(plan), "planned 2 cases")
        self.assertEqual(self.step(fetch, self.home(self.cases)), "fetched 2 of 2 cases")
        said = {"poc-two": job.Stop("not_this_set")}

        def review(case):
            if case["id"] in said:
                raise said[case["id"]]
            raise RuntimeError("a fault that quotes %s" % case["diff"])
        self.assertEqual(self.step(job.score, review), "scored 2 of 2 cases, 0 passed")
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual([(c["verdict"], c["reasons"]) for c in written["cases"]],
                         [("unreadable", ["unanswered"]), ("unreadable", ["not_this_set"])])
        self.assertEqual(self.step(judge), "run_fault")
        # The step itself, as the workflow runs it: the checkout's Role and configuration, each case stopped before the
        # model because its facts do not name its diff, and the report written.
        (self.work / job.REPORT).unlink()
        for kept in (self.temp / "heldout" / "cases").iterdir():
            held = json.loads(kept.read_text())
            held["facts"]["content_id"] = "sha256:" + "0" * 64
            kept.write_text(json.dumps(held))
        self.assertEqual(self.step(step.step), "scored 2 of 2 cases, 0 passed")
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual({tuple(c["reasons"]) for c in written["cases"]}, {("diff_not_content",)})

    def test_an_unanswered_case_says_why_by_its_class_its_place_and_its_code(self):  # decision 0131
        # The first cut's eval closed on three cases unanswered, and nothing said why. A case that raised says its
        # exception's class and the last line of the repo's code it passed, never the message, which here quotes the
        # case; a step's code the report has no word for says that code; a read of the home that raised says the same.
        from harness import eval as job
        plan, fetch, judge = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch", "judge"))
        self.step(plan)
        self.step(fetch, self.home(self.cases))
        first, second = list(self.cases)
        raised = {first: ValueError("the case's diff: %s" % "--- a/kernel/x.py"), second: job.Stop("path_outside")}

        def review(case):
            raise raised[case["id"]]
        self.step(job.score, review)
        text = (self.work / job.REPORT).read_text()
        written = json.loads(text)
        self.assertEqual(validate(written, load("schemas/eval-report.schema.json"), schemas=eval_result.schemas()), [])
        one, two = sorted(written["cases"], key=lambda c: [first, second].index(c["id"]))
        self.assertEqual((one["reasons"], one["cause"]["exception"]), (["unanswered"], "ValueError"))
        self.assertRegex(one["cause"]["at"], r"^harness/eval/__init__\.py:[1-9][0-9]*$")
        self.assertEqual((two["reasons"], two["cause"]), (["unanswered"], {"stop": "path_outside"}))
        self.assertNotIn("kernel/x.py", text)
        self.assertEqual(self.step(judge), "run_fault")
        self.assertIn("at=%s exception=ValueError 1" % one["cause"]["at"], job.tally(written))
        self.assertIn("stop=path_outside 1", job.tally(written))
        # A case passed or failed by the reviewer, or stopped by a code of the report's own, has no cause.
        self.step(job.score, lambda case: (_ for _ in ()).throw(job.Stop("not_this_set")))
        self.assertEqual([c.get("cause") for c in json.loads((self.work / job.REPORT).read_text())["cases"]], [None, None])
        # An interrupt says its own; every case after it is unanswered, and has none.
        self.step(job.score, lambda case: (_ for _ in ()).throw(KeyboardInterrupt))
        first, after = json.loads((self.work / job.REPORT).read_text())["cases"]
        self.assertEqual((first["cause"]["exception"], after.get("cause")), ("KeyboardInterrupt", None))
        # The home's read that raised.
        from adapters import heldout
        self.clean()
        self.set(self.cases)
        self.step(plan)
        with mock.patch.object(heldout, "case", side_effect=OSError("the home's name")):
            self.step(fetch, self.home(self.cases))
        self.step(job.score, lambda case: example_result())
        text = (self.work / job.REPORT).read_text()
        self.assertEqual({(c["reasons"][0], c["cause"]["exception"]) for c in json.loads(text)["cases"]}, {("unanswered", "OSError")})
        self.assertNotIn("home's name", text)
        # The causes of the home's read that cannot be read are none: the report is written all the same.
        (self.temp / "heldout" / "fetch-causes.json").unlink()
        self.step(job.score, lambda case: example_result())
        self.assertEqual([c.get("cause") for c in json.loads((self.work / job.REPORT).read_text())["cases"]], [None, None])
        # A class, a code, an exit or a timeout not of its shape is left out, so the report holds to its schema.
        class timeout(Exception):
            pass
        self.step(fetch, self.home(self.cases))
        one_id, two_id = list(self.cases)
        held = {one_id: timeout(), two_id: job.Stop("A step's words")}
        self.step(job.score, lambda case: (_ for _ in ()).throw(held[case["id"]]))
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual(validate(written, load("schemas/eval-report.schema.json"), schemas=eval_result.schemas()), [])
        causes = {c["id"]: c.get("cause") for c in written["cases"]}
        self.assertEqual((set(causes[one_id]), causes[two_id]), ({"at"}, None))

        def asked():
            pass
        for seen, said in (({"exit": 300}, {}), ({"exit": True}, {}), ({"exit": -1}, {"exit": -1}),
                           ({"timed_out": "yes"}, {}), ({"raised": "socket.timeout"}, {}), ({"raised": "OSError"}, {"exception": "OSError"})):
            asked.seen = seen
            self.assertEqual(job.seen_of(asked), said, seen)

    def test_a_case_the_engine_stopped_says_what_the_cli_said_of_it(self):  # decision 0131
        # Through the step as the workflow runs it: a case whose CLI erred says its subtype and exit, one whose call timed
        # out says so, one that raised after the call says where and what the CLI had said, and nothing carries over to
        # the next case.
        from harness import engine
        from harness import eval as job
        from harness.eval import run as step
        plan, fetch = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch"))
        case, live = self.reviewed()
        cases = {i: (json.dumps(dict(case, id=i), indent=2) + "\n").encode() for i in ("poc-one", "poc-two")}

        def run(cli):
            self.clean()
            self.set(cases)
            with mock.patch.object(job, "now", lambda: 1000):
                self.step(plan)
            self.step(fetch, self.home(cases))
            self.step(step.step, cli, lambda: 1000.0, env=live.JOB)
            return json.loads((self.work / job.REPORT).read_text())["cases"]
        erred = run(live.CLI(said=live.answer(is_error=True, subtype="error_during_execution"), returncode=1))
        self.assertEqual([(c["reasons"], c["cause"]) for c in erred],
                         [(["engine_failed"], {"subtype": "error_during_execution", "exit": 1})] * 2)
        # A subtype the pin does not give is `other`, whatever its words, as is one in snake case.
        for words in ("An error, as the model put it", "the_expected_finding_is_in_kernel_decide"):
            worded = run(live.CLI(said=live.answer(is_error=True, subtype=words), returncode=1))
            self.assertEqual([c["cause"] for c in worded], [{"subtype": "other", "exit": 1}] * 2, words)
        # A case the tier's cost ceiling stopped says so by the CLI's own word (decision 0136).
        halted = run(live.CLI(said=live.answer(is_error=True, subtype="error_max_budget_usd"), returncode=1))
        self.assertEqual([(c["reasons"], c["cause"]) for c in halted],
                         [(["no_answer"], {"subtype": "error_max_budget_usd", "exit": 1})] * 2)
        # A call that could not be made says the class of what it raised.
        refused = run(live.CLI(raises=ValueError("embedded null byte")))
        self.assertEqual([(c["reasons"], c["cause"]) for c in refused], [(["engine_failed"], {"exception": "ValueError"})] * 2)
        late = run(live.CLI(raises=subprocess.TimeoutExpired(["claude"], 600)))
        self.assertEqual([(c["reasons"], c["cause"]) for c in late], [(["engine_timeout"], {"timed_out": True})] * 2)
        with mock.patch.object(engine, "validate", side_effect=TypeError("what the model wrote")):
            after = run(live.CLI(said=live.answer(live.judged(findings=[], effects={}))))
        self.assertEqual({(c["cause"]["exception"], c["cause"]["subtype"], c["cause"]["exit"]) for c in after},
                         {("TypeError", "success", 0)})
        self.assertTrue(all(c["cause"]["at"].startswith("harness/engine.py:") for c in after), after)
        # The second case's engine changed before its call: it says nothing of the first case's CLI.
        once = run(live.CLI(said=live.answer(is_error=True, subtype="error_during_execution"), returncode=1,
                            versions=(live.PIN, live.PIN, "9.9.9", "9.9.9")))
        self.assertEqual([(c["reasons"], c.get("cause")) for c in once],
                         [(["engine_failed"], {"subtype": "error_during_execution", "exit": 1}), (["engine_version"], None)])

    def test_an_interrupt_asks_nothing_more_and_the_report_is_written(self):  # issue 309, ruling 4
        # A cancel that lands during a case's call ends the asking: that case and every one after it are unanswered,
        # nothing more is asked of the model, and the report is written for the upload.
        from harness import eval as job
        plan, fetch = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch"))
        self.step(plan)
        self.step(fetch, self.home(self.cases))
        asked = []

        def review(case):
            asked.append(case["id"])
            raise KeyboardInterrupt
        try:
            said = self.step(job.score, review)
        except KeyboardInterrupt:       # an interrupt that escapes the step writes no report: a failure, not a stop
            said = "the interrupt escaped the step"
        self.assertEqual(said, "scored 2 of 2 cases, 0 passed")
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual((len(asked), [(c["verdict"], c["reasons"]) for c in written["cases"]]),
                         (1, [("unreadable", ["unanswered"])] * 2))

    def test_each_head_is_unpacked_apart_from_the_cases(self):  # issue 623
        # The CLI starts in a case's head. The set's cases, answers and all, are kept in the scratch: no head is in it,
        # nor holds it, and the two share no folder below the runner's own temporary directory, so the read tools'
        # confinement (decision 0138) is not the only thing between the model and the answers.
        import os
        from harness import eval as job
        from harness.eval import run as step
        case, live = self.reviewed()
        cases = {case["id"]: (json.dumps(case, indent=2) + "\n").encode()}
        plan, fetch = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch"))
        self.set(cases)
        self.step(plan)
        self.assertEqual(self.step(fetch, self.home(cases), Heads()), "fetched 1 of 1 cases")
        place = self.temp / "heldout"
        kept_plan = json.loads((place / "plan.json").read_text())
        (place / "plan.json").write_text(json.dumps(dict(kept_plan, planned_at=1000)))
        seen = {}

        class Looking(live.CLI):
            def __call__(self, args, env, timeout, **given):
                if args[1:] != ["--version"]:
                    seen["head"] = os.path.realpath(given["head"])
                    seen["beside"] = sorted(os.listdir(os.path.dirname(seen["head"])))
                return super().__call__(args, env, timeout, **given)
        cli = Looking(said=live.answer(live.judged(findings=[], effects={})))
        self.step(step.step, cli, lambda: 1000.0, env=live.JOB)
        scratch, temp = os.path.realpath(str(place)), os.path.realpath(str(self.temp))
        self.assertTrue(os.path.isdir(os.path.join(scratch, "cases")), "the cases are where the scratch keeps them")
        self.assertEqual(os.path.commonpath([seen["head"], scratch]), temp)
        self.assertEqual(seen["beside"], [case["id"]], "beside the head, nothing but the heads")
        # A heads folder that would be the scratch or the workspace, or inside either, or hold either, the root among
        # them, through a link, is refused.
        for target in (place / "linked", self.work / "linked", place, self.work, self.temp, pathlib.Path(os.sep)):
            self.clean()
            target.mkdir(parents=True, exist_ok=True)
            os.symlink(str(target), str(self.temp / "heads"))
            with self.assertRaises(job.Stop) as stopped:
                job.heads_place(self.env, self.work)
            self.assertEqual(stopped.exception.code, "scratch_in_workspace", target)
            os.unlink(str(self.temp / "heads"))
        self.assertEqual(job.heads_place(self.env, self.work), pathlib.Path(temp, "heads"))

    def test_each_cases_head_is_read_with_no_credential_and_one_not_read_closes_the_gate(self):  # decision 0138
        # The fetch reads each case's head, the commit its diff was taken at, as its tarball through a transport of its
        # own, never the home's, and unpacks it under heads/; the run step reads it as the case's folder and removes it
        # once the case is asked. A head that cannot be read whole is the case's `head_unreadable`, an Engine's or the
        # Factory's fault, never the reviewer's: the gate closes.
        from harness import eval as job
        from harness.eval import run as step
        case, live = self.reviewed()
        cases = {i: (json.dumps(dict(case, id=i, head=h), indent=2) + "\n").encode()
                 for i, h in (("poc-one", "1" * 40), ("poc-two", "2" * 40))}
        self.set(cases)
        self.step(job.plan)
        heads = Heads(refused={"2" * 40})
        self.assertEqual(self.step(job.fetch, self.home(cases), heads), "fetched 1 of 2 cases")
        repo = case["facts"]["item"]["repo"]
        self.assertEqual(heads.asked, [("/repos/%s/tarball/%s" % (repo, "1" * 40), True, github_tarred()),
                                       ("/repos/%s/tarball/%s" % (repo, "2" * 40), True, github_tarred())])
        place = self.temp / "heldout"
        self.assertEqual(json.loads((place / "fetched.json").read_text()), {"poc-one": None, "poc-two": "head_unreadable"})
        self.assertEqual(sorted(p.name for p in (self.temp / "heads").iterdir()), ["poc-one"])
        self.assertTrue((self.temp / "heads" / "poc-one" / "README.md").is_file())
        cli = live.CLI(said=live.answer(live.judged(findings=[], effects={})))
        kept_plan = json.loads((place / "plan.json").read_text())
        (place / "plan.json").write_text(json.dumps(dict(kept_plan, planned_at=1000)))
        self.step(step.step, cli, lambda: 1000.0, env=live.JOB)
        asked, = cli.asked()
        self.assertEqual(pathlib.Path(asked["head"]).parts[-2:], ("heads", "poc-one"))
        self.assertFalse((self.temp / "heads" / "poc-one").exists(), "removed once its case is asked")
        report = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual({c["id"]: c["reasons"] for c in report["cases"]}["poc-two"], ["head_unreadable"])
        self.assertIn("head_unreadable", job.ENGINE_FAULTS)
        self.assertEqual(self.step(job.judge.step if hasattr(job.judge, "step") else job.judge), "engine_fault")
        # The fetch step's own transport for the heads sends no token: the home's is never sent anywhere else.
        import importlib
        from adapters import github
        fetching = importlib.import_module("harness.eval.fetch")
        made = []
        with mock.patch.object(fetching, "fetch", lambda env, root, work, home, heads: made.append((home, heads)) or "x"):
            fetching.step({"HELDOUT_TOKEN": "a-stand-in-held-out-token"}, self.root, self.work)
        (home, anonymous), = made
        self.assertIsNone(anonymous._token)
        self.assertIsInstance(anonymous, github.Live)

    def test_the_step_gives_each_case_the_release_dispatched_and_a_fresh_run(self):  # issue 309, ruling 5
        # Through the step as the workflow runs it: each case's Task names the Release the dispatch named, which plan
        # kept, and a Run id of its own, in the form a pass mints one; the time is counted from the plan's.
        from harness import engine, task
        from harness import eval as job
        from harness.eval import run as step
        plan, fetch = (getattr(getattr(job, n), n, getattr(job, n)) for n in ("plan", "fetch"))
        case, live = self.reviewed()
        cases = {i: (json.dumps(dict(case, id=i), indent=2) + "\n").encode() for i in ("poc-one", "poc-two")}
        self.set(cases)
        with mock.patch.object(job, "now", lambda: 1000):
            self.assertEqual(self.step(plan), "planned 2 cases")
        self.assertEqual(json.loads((self.temp / "heldout" / "plan.json").read_text())["planned_at"], 1000)
        self.step(fetch, self.home(cases))
        cli = live.CLI(said=live.answer(live.judged(findings=[], effects={})))
        self.assertEqual(self.step(step.step, cli, lambda: 1000.0, env=live.JOB), "scored 2 of 2 cases, 0 passed")
        report = json.loads((self.work / job.REPORT).read_text())
        given = [json.loads(c["args"][2].split(engine.TASK, 1)[1]) for c in cli.asked()]
        self.assertEqual(len(given), 2, report)
        self.assertEqual([g["release"] for g in given], ["factory/v0.1.0"] * 2)
        runs = [g["run"] for g in given]
        self.assertTrue(all(live.run.RUN_ID.fullmatch(r) for r in runs) and len(set(runs)) == 2, runs)
        # A plan whose time cannot be read starts no case.
        kept = json.loads((self.temp / "heldout" / "plan.json").read_text())
        (self.temp / "heldout" / "plan.json").write_text(json.dumps(dict(kept, planned_at="soon")))
        self.assertEqual(self.step(step.step, live.CLI(), lambda: 1000.0), "scratch_unreadable")

    def test_a_step_says_counts_and_codes_and_never_what_it_raised(self):
        # Whatever a step raised is never printed: its message could quote a case or name the home.
        from harness import eval as job

        def leaks(env, root, work):
            raise ValueError("the case's diff: --- a/kernel/x.py")
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out, mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(job.main(leaks), 1)
            self.assertEqual(job.main(lambda env, root, work: (_ for _ in ()).throw(job.Stop("eval_set_empty"))), 1)
            self.assertEqual(job.main(lambda env, root, work: "planned 2 cases"), 0)
            # An interrupt too, a cancel landing as the CLI's call times out, whose default report would quote the call.
            def interrupted(env, root, work):
                try:
                    raise TimeoutError("the CLI was called with: --- a/kernel/x.py")
                except TimeoutError:
                    raise KeyboardInterrupt
            try:
                code = job.main(interrupted)
            except KeyboardInterrupt:   # one that escapes main is reported by Python, quoting what it was chained to
                code = "the interrupt escaped main"
            self.assertEqual(code, 1)
        self.assertEqual((out.getvalue(), err.getvalue()),
                         ("eval_step_failed\neval_set_empty\nplanned 2 cases\neval_step_failed\n", ""))


if __name__ == "__main__":
    unittest.main()
