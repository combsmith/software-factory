"""The review Intent's held-out eval set: what this repo holds of it, and how a Result is scored against a case.

The cases live in the private home and never here (design §3.13); a synthetic case, made in the test, stands in."""
from __future__ import annotations

import copy
import io
import json
import pathlib
import re
import shutil
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

    def test_a_case_whose_expected_finding_is_off_its_rubric_scores_nothing(self):  # issue 421
        # A Result whose Finding cites a criterion at another severity or category than the rubric's is refused (decisions
        # 0088 and 0095), so a case that expects one would reward a Result `apply` refuses: what is measured would not be
        # what runs. Such a case is no answer, whatever the Result says, and it is read as a code alone.
        case, result = load("examples/eval-case.json"), load("examples/result.json")
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
        install = EVAL_WORKFLOW[EVAL_WORKFLOW.index("      - env:\n          CLI_VERSION"):
                                EVAL_WORKFLOW.index("      - run: python3 -m harness.eval.run\n")]
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
            # The CLI's install, between the fetch and the model's step, at the Engine's pin by its checksum, word for
            # word as the Run's jobs install it (issue 309, amendment 1).
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
        # (decision 0099).
        manifest = json.loads(SET.read_text())
        self.assertGreaterEqual(manifest["count"], 40)

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
        # These sets stand in with two cases of one kind: the test of the split sets its own least.
        from harness import eval as job
        least = mock.patch.object(job, "KIND_LEAST", 0)
        least.start()
        self.addCleanup(least.stop)

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

    def test_a_set_short_of_a_kind_fails_the_run_and_closes_the_gate_saying_no_count(self):  # issue 365
        # Decision 0099: the set must hold KIND_LEAST of each kind, read from the cases fetched, where they are. A set short
        # of a kind fails `judge` by a code alone, and its report, uploaded all the same, says one word of the set, which
        # `verdict`, the Release's gate too, refuses. Neither says how many of a kind.
        from harness import eval as job
        self.assertEqual(job.KIND_LEAST, 0, "as these fixtures set it")
        result = load("examples/result.json")
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
                shutil.rmtree(str(self.temp / "heldout"), ignore_errors=True)
                self.set(cases)
                self.step(job.plan)
                self.step(job.fetch, self.home(cases))
                self.assertIs(job.split_ok(found(), self.temp / "heldout"), held)
        # Short of a kind: the run says so by a code alone, and neither the log nor the report holds a count of a kind.
        with mock.patch.object(job, "KIND_LEAST", 1):
            shutil.rmtree(str(self.temp / "heldout"), ignore_errors=True)
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
            self.assertEqual(sorted(written), ["cases", "commit", "intent", "passed", "release", "role", "schema", "set",
                                               "split_ok"], "no count of a kind, nor any field of one")
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
        result = load("examples/result.json")
        wrong = copy.deepcopy(result)
        wrong["findings"] = []
        self.step(job.plan)
        first = next(iter(self.cases))
        self.assertEqual(self.step(job.fetch, self.home(dict(self.cases, **{first: b"changed"}))), "fetched 1 of 2 cases")
        self.assertEqual(json.loads((self.temp / "heldout" / "fetched.json").read_text()), {first: "hash_differs", "poc-two": None})
        self.assertFalse((self.temp / "heldout" / "cases" / ("%s.json" % first)).exists())
        # The scorer says why the case failed, finding_not_raised; the report says only that it did, case_failed: what
        # the scorer said would tell what the case expected, and the report is public (decision 0078). Nor does a step
        # print it: the run step says counts, and judge one code.
        self.assertEqual(eval_result.score(load("examples/eval-case.json"), wrong)["reasons"][0], "finding_not_raised")
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(job.main(lambda env, root, work: job.score(dict(self.env), self.root, self.work,
                                                                        lambda case: wrong)), 0)
            self.assertEqual(job.main(lambda env, root, work: job.judge(dict(self.env), self.root, self.work)), 1)
        self.assertEqual(out.getvalue(), "scored 2 of 2 cases, 0 passed\ncase_failed\n")
        written = (self.work / job.REPORT).read_text()
        self.assertEqual([(c["verdict"], c["reasons"]) for c in json.loads(written)["cases"]],
                         [("unreadable", ["hash_differs"]), ("fail", ["case_failed"])])
        for code in ("finding_not_raised", "coverage_disagrees", "finding_raised_wrongly", "criterion_not_met",
                     "category_differs", "severity_differs", "location_differs", "answer_disagrees_with_verdict"):
            self.assertNotIn(code, written + out.getvalue(), code)
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

    def test_a_case_off_its_rubric_is_unreadable_by_its_code_and_asks_nothing(self):  # issue 421
        # Where the cases are, at run time: a case whose expected Finding is not as its criterion gives it asks nothing of
        # the model, and the run fails by a code alone, naming neither the severity nor the category. Its owner mends it
        # in the home; nothing here holds what it expected.
        from harness import eval as job
        first = next(iter(self.cases))
        off = json.loads(self.cases[first])
        off["expected"]["finding"]["category"] = "delivery"
        cases = dict(self.cases, **{first: (json.dumps(off, indent=2) + "\n").encode()})
        self.set(cases)
        self.step(job.plan)
        self.step(job.fetch, self.home(cases))
        asked = []
        self.step(job.score, lambda case: asked.append(case["id"]) or load("examples/result.json"))
        self.assertEqual(asked, ["poc-two"], "the case off its rubric is never given to the review")
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual(validate(written, load("schemas/eval-report.schema.json"), schemas=eval_result.schemas()), [])
        self.assertEqual([(c["id"], c["verdict"], c["reasons"]) for c in written["cases"]],
                         [(first, "unreadable", ["answer_off_rubric"]), ("poc-two", "pass", [])])
        self.assertNotIn("delivery", (self.work / job.REPORT).read_text())
        self.assertEqual(self.step(job.judge), "case_failed")

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
                          found, {i: ("pass", []) for i in self.cases}, True)
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
        # but for its Run id, and the CLI is called as a live Run calls it, the Task as data, with no tool.
        from harness import engine, task
        from harness.eval import run as step
        case, live = self.reviewed()
        cli = live.CLI(said=live.answer(live.judged(findings=[], effects={})))
        env = dict(live.JOB, HELDOUT_TOKEN="a-stand-in-held-out-token", HELDOUT_OWNER="o")
        with mock.patch.object(step, "run_id", lambda: live.RUN):
            result = step.reviewer(env, "factory/v0.1.0", 0, cli, live.Clock(0.0, 1.0, 2.0))(case)
        self.assertEqual((result["status"], result["run"]), ("completed", live.RUN))
        asked, = cli.asked()
        given = json.loads(asked["args"][2].split(engine.TASK, 1)[1])
        config = dict(live.config(), release="factory/v0.1.0")
        config["harness"] = live.HARNESS
        manifest = load("roles/pr-review.json")
        self.assertEqual(given, task.build(live.record(), live.RUN, live.facts(), [], manifest, [], config, live.DIFF))
        self.assertTrue(engine.no_tool(asked["args"]))
        # The model's credential reaches the CLI, and nothing of the home: not its token, nor where it is.
        self.assertEqual(asked["env"]["CLAUDE_CODE_OAUTH_TOKEN"], live.TOKEN)
        self.assertFalse([k for k in asked["env"] if k.startswith("HELDOUT")])
        self.assertNotIn("a-stand-in-held-out-token", json.dumps(cli.calls))

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
                step.reviewer(live.JOB, "factory/v0.1.0", 0, cli, live.Clock(0.0))(bad)
            self.assertEqual((stopped.exception.code, cli.asked()), ("not_this_set", []))
        # Less time left than a case's tier allows: the step starts no case, and the case is unanswered.
        cli = live.CLI()
        late = live.HARNESS["limits"]["standard"]["seconds"]
        review = step.reviewer(live.JOB, "factory/v0.1.0", 0, cli, live.Clock(step.BUDGET - late + 1))
        with self.assertRaises(job.Stop) as stopped:
            review(case)
        self.assertEqual((stopped.exception.code, cli.asked()), ("unanswered", []))
        # Less time left than the tier allows and the Engine's two reads of the CLI's version: not started either.
        cli = live.CLI()
        review = step.reviewer(live.JOB, "factory/v0.1.0", 0, cli, live.Clock(step.BUDGET - late - step.VERSION_READS + 1))
        with self.assertRaises(job.Stop) as stopped:
            review(case)
        self.assertEqual((stopped.exception.code, cli.asked()), ("unanswered", []))
        # With just that time left, it is asked.
        cli = live.CLI(said=live.answer(live.judged(findings=[], effects={})))
        with mock.patch.object(step, "run_id", lambda: live.RUN):
            step.reviewer(live.JOB, "factory/v0.1.0", 0, cli,
                          live.Clock(step.BUDGET - late - step.VERSION_READS, 1.0, 2.0))(case)
        self.assertEqual(len(cli.asked()), 1)
        # The limit is the case's own tier's, read from the configuration, never a constant.
        from harness import run as running
        longer = running.configuration()
        longer["harness"]["limits"]["standard"]["seconds"] = late * 2
        cli = live.CLI()
        with mock.patch.object(step.live, "configuration", lambda: longer):
            review = step.reviewer(live.JOB, "factory/v0.1.0", 0, cli, live.Clock(step.BUDGET - late - step.VERSION_READS))
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
            step.reviewer(live.JOB, "factory/v0.1.0", 0, cli, live.Clock(0.0))(dict(case, diff="\ud800"))
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
        self.assertEqual(self.step(judge), "case_failed")
        # The step itself, as the workflow runs it: the checkout's Role and configuration, each case Stopped here
        # because the example's facts do not name its diff, and the report written.
        (self.work / job.REPORT).unlink()
        self.assertEqual(self.step(step.step), "scored 2 of 2 cases, 0 passed")
        written = json.loads((self.work / job.REPORT).read_text())
        self.assertEqual({tuple(c["reasons"]) for c in written["cases"]}, {("not_this_set",)})

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
