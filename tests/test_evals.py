"""The review Intent's held-out eval set: what this repo holds of it, and how a Result is scored against a case.

The cases live in the private home and never here (design §3.13); a synthetic case, made in the test, stands in."""
from __future__ import annotations

import copy
import io
import json
import pathlib
import re
import unittest
from unittest import mock

from tests.support import pending
from tools import check_examples, eval_result, walk
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SET = ROOT / "evals" / "pr-review" / "cases.json"
# The eval job's workflow as issue 309's ruling 10 shapes it, for the check to hold: the live file lands with its `run`
# step's Task (the ruling's PR 2), and until then this text is the shape.
EVAL_WORKFLOW = """name: factory
on:
  workflow_dispatch:
    inputs:
      release:
        required: true
        type: string
permissions: {}
jobs:
  eval:
    runs-on: ubuntu-24.04
    timeout-minutes: 120
    permissions:
      contents: read
    environment: factory-eval
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - run: python3 -m harness.eval.plan
        env:
          RELEASE: ${{ inputs.release }}
      - run: python3 -m harness.eval.fetch
        env:
          HELDOUT_TOKEN: ${{ secrets.HELDOUT_TOKEN }}
          HELDOUT_OWNER: ${{ secrets.HELDOUT_OWNER }}
          HELDOUT_REPO: ${{ secrets.HELDOUT_REPO }}
      - run: python3 -m harness.eval.run
        env:
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: eval-report
          path: eval-report.json
          if-no-files-found: error
          retention-days: 90
      - run: python3 -m harness.eval.judge
"""


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
        # One Finding must be the expected one in every respect: two that are each right in part are no match, and the
        # nearest of them says what it missed.
        split = copy.deepcopy(result)
        split["findings"][0]["severity"] = "minor"
        split["findings"].append(dict(result["findings"][0], ref="n3", category="architecture"))
        self.assertEqual(eval_result.score(case, split)["reasons"], ["severity_differs"])
        split["findings"][0]["location"] = {"path": "kernel/gate.py"}
        self.assertEqual(eval_result.score(case, split)["reasons"], ["category_differs"])
        # Lines are read whole: an end with no start, or before its start, is nowhere in a Result, and unreadable in
        # a case; a Result's location given without lines is the whole file.
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
        # A criterion the Role's rubric does not have, or a Role with no rubric here, is nobody's to pass.
        for over in ({"expected": dict(case["expected"], criterion="PR-9")}, {"role": "qa-lead"}):
            unknown = dict(copy.deepcopy(case), **over)
            self.assertEqual(eval_result.score(unknown, result)["reasons"], ["criterion_unknown"], over)

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
        with mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(eval_result.main([str(case), str(result)], base=ROOT / "examples"), 0)


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
            "a second job": (EVAL_WORKFLOW + "  other:\n    runs-on: ubuntu-24.04\n    timeout-minutes: 5\n"
                                             "    environment: factory-poller\n    steps:\n      - run: make verify\n",
                             "it holds the job eval and no other"),
        }
        for why, (text, words) in broken.items():
            self.assertTrue(caught(check_workflows.eval_problems(text), words), why)
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

    @pending
    def test_the_review_intents_eval_set_has_its_cases(self):
        # Decision 0010: an Intent family is cut over only after its eval set exists. The cases are written in the
        # private home by a session opened there, and this manifest then carries their hashes (issue 183).
        manifest = json.loads(SET.read_text())
        self.assertGreaterEqual(manifest["count"], 20)

    @pending
    def test_a_fresh_agent_given_the_repo_adds_a_rule_and_passes_the_check(self):
        # Decision 0013 and docs/context-engineering.md: the context's test (issue 8, decision 0042). The runs are made at
        # the Maintainer's terminal by tools/context_eval.sh and recorded in evals/context/task.json; this holds the record:
        # one task sentence that names a rule and its reason code, the sha256 of the held-out answer, and the newest three
        # runs on it all passed. Until the runs are recorded the task is null, and this fails.
        known = eval_result.schemas()
        record = load("evals/context/task.json")
        self.assertEqual(validate(record, known["context-eval"], schemas=known), [])
        self.assertIsInstance(record["task"], str)
        self.assertEqual(len(re.findall(r"`[a-z_]+`", record["task"])), 1, "the sentence names one reason code")
        self.assertIsInstance(record["held_out_sha256"], str)
        runs = record["runs"]
        self.assertGreaterEqual(len(runs), 3)
        newest = sorted(runs, key=lambda r: r["ran_at"])[-3:]
        self.assertTrue(all(r["passed"] for r in newest), [r["verdicts"] for r in newest])
        code = re.search(r"`([a-z_]+)`", record["task"]).group(1)
        script = (ROOT / "tools" / "context_eval.sh").read_text()
        pin, cap = re.search(r"^PIN=(\S+)$", script, re.M).group(1), int(re.search(r"^CAP=(\d+)$", script, re.M).group(1))
        for r in newest:
            self.assertEqual(r["passed"], r["verdicts"] == {"held_out_test": "pass", "verify": "pass", "mutant": "killed"})
            self.assertEqual((r["cli_version"], r["cap_turns"]), (pin, cap))
            self.assertEqual(r["added"]["reason"], code)
            self.assertIsNotNone(r["added"]["test"])
            self.assertIsNotNone(r["added"]["mutant"])
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
        two = dict(copy.deepcopy(one), id="poc-two")
        self.cases = {c["id"]: (json.dumps(c, indent=2) + "\n").encode() for c in (one, two)}
        self.set(self.cases)
        self.env = {"RELEASE": "factory/v0.1.0", "GITHUB_SHA": "a" * 40, "RUNNER_TEMP": str(self.temp),
                    "HELDOUT_OWNER": "o", "HELDOUT_REPO": "home"}

    def tearDown(self):
        self.dir.cleanup()

    def set(self, cases: dict) -> None:
        import hashlib
        manifest = {"schema": "eval-set/1", "role": "pr-review", "intent": "review-change", "count": len(cases),
                    "cases": [{"id": i, "sha256": hashlib.sha256(d).hexdigest()} for i, d in cases.items()]}
        (self.root / "evals" / "pr-review").mkdir(parents=True, exist_ok=True)
        (self.root / "evals" / "pr-review" / "cases.json").write_text(json.dumps(manifest, indent=2) + "\n")

    def step(self, step, *given, env=None):
        from harness import eval as job
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
        # Ruling 8: the set this repo holds today has no case; the run says so and makes nothing, not even the scratch.
        from harness import eval as job
        self.assertEqual(self.step_root(job.plan), "eval_set_empty")
        self.assertEqual(list(self.temp.iterdir()), [])
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

    def step_root(self, step):
        from harness import eval as job
        try:
            return step(dict(self.env), ROOT, self.work)
        except job.Stop as stop:
            return stop.code

    def test_each_case_is_fetched_into_the_scratch_and_scored_and_only_the_report_reaches_the_workspace(self):
        from harness import eval as job
        result = load("examples/result.json")
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
        self.assertEqual(self.step(job.judge), "passed 2 of 2 cases")

    def test_a_case_not_read_whole_or_failed_fails_the_run_with_its_report_uploaded(self):
        from harness import eval as job
        result = load("examples/result.json")
        wrong = copy.deepcopy(result)
        wrong["findings"] = []
        self.step(job.plan)
        first = next(iter(self.cases))
        self.assertEqual(self.step(job.fetch, self.home(dict(self.cases, **{first: b"changed"}))), "fetched 1 of 2 cases")
        self.assertEqual(json.loads((self.temp / "heldout" / "fetched.json").read_text()), {first: "hash_differs", "poc-two": None})
        self.assertFalse((self.temp / "heldout" / "cases" / ("%s.json" % first)).exists())
        self.step(job.score, lambda case: wrong)
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual([(c["verdict"], c["reasons"]) for c in written["cases"]],
                         [("unreadable", ["hash_differs"]), ("fail", ["finding_not_raised"])])
        self.assertEqual(self.step(job.judge), "case_failed")
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
                 "poc-six": (json.dumps(dict(stray, id="poc-six", role="devops-lead")) + "\n").encode()}
        self.set(cases)
        self.step(job.plan)
        self.step(job.fetch, self.home(cases))
        self.step(job.score, lambda case: self.fail("no case of this set is reviewed"))
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual([c["reasons"] for c in written["cases"]],
                         [["not_this_set"], ["schema"], ["not_this_set"], ["not_this_set"], ["not_this_set"]])

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
                          found, {i: ("pass", []) for i in self.cases})
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
                                "case_failed"),
                               (changed(cases=[first, dict(good["cases"][1], reasons=["schema"])]), "case_failed"),
                               (changed(cases=[first, dict(good["cases"][1], verdict="fail")]), "case_failed"),
                               (changed(cases=[first, dict(good["cases"][1], verdict="unreadable")]), "case_failed"),
                               (changed(role="devops-lead"), "another_set"),
                               (changed(passed="2"), "report_unreadable"),
                               (changed(passed=1), "count_differs")):
            self.assertEqual(job.verdict(document, found, digest, "a" * 40, "factory/v0.1.0"), code, code)
        empty = dict(found, count=0, cases=[])
        self.assertEqual(job.verdict(changed(set={"count": 0, "sha256": digest}, cases=[], passed=0), empty, digest,
                                     "a" * 40, "factory/v0.1.0"), "eval_set_empty")

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

    def test_a_step_says_counts_and_codes_and_never_what_it_raised(self):
        # Whatever a step raised is never printed: its message could quote a case or name the home.
        from harness import eval as job

        def leaks(env, root, work):
            raise ValueError("the case's diff: --- a/kernel/x.py")
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out, mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(job.main(leaks), 1)
            self.assertEqual(job.main(lambda env, root, work: (_ for _ in ()).throw(job.Stop("eval_set_empty"))), 1)
            self.assertEqual(job.main(lambda env, root, work: "planned 2 cases"), 0)
        self.assertEqual((out.getvalue(), err.getvalue()), ("eval_step_failed\neval_set_empty\nplanned 2 cases\n", ""))


if __name__ == "__main__":
    unittest.main()
