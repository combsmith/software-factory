"""The advisory check of issue 589: a changed line of Python that no test notices (tools/untested.py)."""
from __future__ import annotations

import contextlib
import io
import os
import pathlib
import re
import subprocess
import tempfile
import time
import unittest

from tools import untested

WORKFLOWS = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows"
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t@example.invalid", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
CALC = '''from __future__ import annotations


def bigger(a: int, b: int) -> int:
    """The bigger of the two."""
    if a > b:
        return a
    return b


def doubled(x):
    return x * 2
'''
CALC_TEST = '''import unittest

from pkg import calc


class Calc(unittest.TestCase):
    def test_the_bigger_is_given(self):
        self.assertEqual(calc.bigger(3, 2), 3)
        self.assertEqual(calc.bigger(2, 3), 3)
'''


def tree(at: pathlib.Path, files: dict) -> None:
    for rel, text in files.items():
        path = at / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if text is None:
            path.unlink()
        else:
            path.write_text(text)


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(root), env=ENV, capture_output=True, text=True, check=True).stdout


def change(base: dict, head: dict, message: str = "the change") -> tuple:
    """(a repo, its base commit, its head commit): `base`'s files, then `head`'s written over them, None deleting one."""
    made = tempfile.TemporaryDirectory()
    root = pathlib.Path(made.name)
    git(root, "init", "-q", "-b", "main")
    tree(root, dict({"pkg/__init__.py": "", "tests/__init__.py": ""}, **base))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    first = git(root, "rev-parse", "HEAD").strip()
    tree(root, head)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return made, root, first, git(root, "rev-parse", "HEAD").strip()


def checked(base: dict, head: dict, message: str = "the change", seconds: float = 600) -> dict:
    made, root, first, last = change(base, head, message)
    with made:
        return untested.check(root, first, last, time.monotonic() + seconds, workers=2)


def outcomes(found: dict) -> list:
    return [(h["path"], h["new"], h["outcome"], h.get("by")) for h in found["hunks"]]


class Reverts(unittest.TestCase):
    def test_a_revert_no_test_notices_survives_and_one_a_test_notices_is_killed(self):
        base = {"pkg/calc.py": CALC.replace("if a > b:", "if a < b:"), "tests/test_calc.py": CALC_TEST}
        found = checked(base, {"pkg/calc.py": CALC.replace("-> int:", "-> float:").replace("x * 2", "x * 3")})
        self.assertEqual(outcomes(found), [("pkg/calc.py", 6, "killed", "revert"), ("pkg/calc.py", 12, "SURVIVED", "revert")])
        self.assertEqual(found["skipped"]["same"], 1)      # the annotation

    def test_a_hunk_that_changes_nothing_python_sees_is_never_run(self):
        same = untested.shape(CALC)
        for text in (CALC.replace("The bigger of the two.", "Which is bigger."), CALC.replace("-> int:", "-> float:"),
                     CALC.replace("(a: int, b: int)", "(a: str, b)"), CALC.replace("    return b\n", "    return b  # b\n")):
            self.assertEqual(untested.shape(text), same, text)
        self.assertNotEqual(untested.shape(CALC.replace("x * 2", "x * 3")), same)
        self.assertNotEqual(untested.shape(CALC.replace('"""The bigger of the two."""', "pass")), same)
        eager = CALC.replace("from __future__ import annotations\n", "")
        self.assertNotEqual(untested.shape(eager.replace("-> int:", "-> float:")), untested.shape(eager))

    def test_an_edit_a_crash_alone_notices_falls_back_to_its_files_revert(self):
        base = {"pkg/calc.py": CALC.replace("    if a > b:\n        return a\n    return b\n", "    return a\n"),
                "tests/test_calc.py": CALC_TEST}
        head = {"pkg/calc.py": CALC.replace("    if a > b:\n        return a\n    return b\n", "    return pick(a, b)\n")
                + "\n\ndef pick(a, b):\n    return a if a > b else b\n"}
        found = checked(base, head)
        self.assertEqual(outcomes(found), [("pkg/calc.py", 6, "killed", "revert"), ("pkg/calc.py", 11, "killed", "file")])
        self.assertEqual(untested.crashed(CRASHED), "NameError")
        self.assertEqual(untested.crashed(CRASHED.replace("ERROR:", "FAIL:")), "")
        self.assertEqual(untested.crashed(CRASHED.replace("NameError", "AttributeError")), "")

    def test_a_small_hunk_no_edit_of_which_runs_is_unchecked_and_a_large_one_gets_mutants(self):
        test = "import unittest\n\nfrom pkg.%s import f\n\n\nclass T(unittest.TestCase):\n    def test_f(self):\n" \
               "        self.assertEqual(f(1), 1)\n"
        large = "def f(x):\n    if x > 0:\n        return x\n    return 0\n" + "".join("\n\ndef g%d(y):\n    return y + %d\n" % (n, n)
                                                                              for n in range(10))
        found = checked({}, {"pkg/small.py": "def f(x):\n    return x\n", "tests/test_small.py": test % "small",
                             "pkg/large.py": large, "tests/test_large.py": test % "large"})
        by_path = {h["path"]: h for h in found["hunks"]}
        self.assertEqual((by_path["pkg/small.py"]["outcome"], by_path["pkg/small.py"]["why"].split(":")[0]),
                         ("UNCHECKED", "CRASHED"))
        self.assertEqual((by_path["pkg/large.py"]["by"], by_path["pkg/large.py"]["mutants"]), ("mutants", untested.MOST))
        self.assertEqual(by_path["pkg/large.py"]["outcome"], "SURVIVED")

    def test_a_mutant_is_made_of_an_added_line_and_never_of_a_quiet_one(self):
        text = ("def f(x, log):\n    if x > 1:\n        x = x + 2\n    print(x)\n    log.info(x)\n    'said'\n"
                "    raise ValueError('no')\n    return x <= 3\n")
        made = dict(untested.candidates(text, {"new": 1, "new_n": 8}))
        self.assertEqual(sorted(made), [2, 3, 8])
        self.assertIn("    if not (x > 1):\n", made[2])
        self.assertIn("        x = x + 3\n", made[3])
        self.assertIn("    return x < 3\n", made[8])
        self.assertIn("    pass\n", dict(untested.candidates("def f(x):\n    g(x)\n", {"new": 2, "new_n": 1}))[2])
        many = "def f(x):\n" + "".join("    x = x + %d\n" % n for n in range(20))
        self.assertEqual(len(untested.candidates(many, {"new": 2, "new_n": 20})), untested.MOST)

    def test_a_path_a_pull_request_names_is_read_only_in_plain_characters(self):
        found = checked({}, {"pkg/odd name.py": "x = 1\n", "pkg/plain.py": "x = 1\n"})
        self.assertEqual(found["skipped"]["unsafe_path"], 1)
        self.assertEqual([h["path"] for h in found["hunks"]], ["pkg/plain.py"])

    def test_no_run_of_the_tests_begins_past_the_budget(self):
        base = {"pkg/calc.py": CALC, "tests/test_calc.py": CALC_TEST}
        found = checked(base, {"pkg/calc.py": CALC.replace("x * 2", "x * 3")}, seconds=-1)
        self.assertEqual([(h["outcome"], h["why"]) for h in found["hunks"]], [("UNCHECKED", "over budget")])

    def test_the_lists_of_mutants_are_data_and_the_runner_below_them_is_read(self):
        text = "ISSUE = [\n    1,\n]\nMUTANTS = [\n    2,\n    3,\n]\n\n\ndef run():\n    return 4\n"
        spans = untested.data_lines(text)
        self.assertEqual(spans, [(1, 3), (4, 7)])
        self.assertTrue(untested.is_data({"new": 5, "new_n": 2}, spans))
        self.assertTrue(untested.is_data({"new": 6, "new_n": 0}, spans))
        self.assertFalse(untested.is_data({"new": 11, "new_n": 1}, spans))
        self.assertFalse(untested.is_data({"new": 7, "new_n": 3}, spans))


CRASHED = ("=" * 70 + "\nERROR: test_x (tests.test_calc.Calc)\n" + "-" * 70 + "\nTraceback (most recent call last):\n"
           "  File \"x.py\", line 1, in test_x\nNameError: name 'pick' is not defined\n\n" + "-" * 70 +
           "\nRan 1 test in 0.001s\n\nFAILED (errors=1)\n")


class Trailers(unittest.TestCase):
    HUNKS = [{"path": "pkg/a.py", "new": 10, "new_n": 3, "removes": False},
             {"path": "pkg/a.py", "new": 20, "new_n": 0, "removes": True}]

    def test_a_trailer_covers_a_hunk_only_when_it_holds_every_line_the_hunk_changed(self):
        spans, problems = untested.read_trailers(["pkg/a.py:10-12", "pkg/a.py:21-21"], self.HUNKS)
        self.assertEqual(problems, [])
        self.assertTrue(untested.covered(self.HUNKS[0], spans))
        self.assertTrue(untested.covered(self.HUNKS[1], spans))
        narrow, _ = untested.read_trailers(["pkg/a.py:10-11"], self.HUNKS)
        self.assertFalse(untested.covered(self.HUNKS[0], narrow))
        late, _ = untested.read_trailers(["pkg/a.py:11-12"], self.HUNKS)
        self.assertFalse(untested.covered(self.HUNKS[0], late))

    def test_a_trailer_that_names_no_changed_line_or_cannot_be_read_is_a_problem(self):
        for value, said in (("pkg/a.py:13-19", "names lines no hunk changed"), ("pkg/b.py:1-2", "leaves as it was"),
                            ("pkg/a.py:12-10", "is not <path>"), ("pkg/a.py 10-12", "is not <path>"),
                            ("::warning::pkg/a.py:10-12", "is not <path>")):
            spans, problems = untested.read_trailers([value], self.HUNKS)
            self.assertEqual(spans, [], value)
            self.assertEqual(len(problems), 1, value)
            self.assertIn(said, problems[0], value)
        self.assertNotIn("::", untested.read_trailers(["::warning::x"], self.HUNKS)[1][0])

    def test_the_head_commits_trailer_covers_its_survivor(self):
        base = {"pkg/calc.py": CALC, "tests/test_calc.py": CALC_TEST}
        message = "Faster doubling\n\nIt keeps behaviour.\n\nBehaviour-preserving: pkg/calc.py:12-12\nCo-Authored-By: x <x@x>\n"
        found = checked(base, {"pkg/calc.py": CALC.replace("x * 2", "x + x")}, message)
        self.assertEqual([(h["outcome"], h["covered"]) for h in found["hunks"]], [("SURVIVED", True)])
        self.assertEqual(found["problems"], [])


class FirstTests(unittest.TestCase):
    def setUp(self):
        made = tempfile.TemporaryDirectory()
        self.addCleanup(made.cleanup)
        self.root = pathlib.Path(made.name)
        tree(self.root, {
            "tools/__init__.py": "", "tools/check_x.py": "def run():\n    return []\n",
            "tools/uses_x.py": "from tools import check_x\n", "kernel/__init__.py": "", "kernel/rule.py": "A = 1\n",
            "kernel/decide.py": "from kernel import rule\n",
            "tests/__init__.py": "",
            "tests/test_tools.py": "import unittest\nfrom tools import check_x, uses_x\n\n\ndef ran():\n    return check_x.run()\n\n\n"
                                   "class Workflows(unittest.TestCase):\n    def test_a(self):\n        ran()\n"
                                   "    def test_b(self):\n        pass\n\n\nclass Other(unittest.TestCase):\n"
                                   "    def test_c(self):\n        uses_x\n\n\nclass Apart(unittest.TestCase):\n"
                                   "    def test_d(self):\n        pass\n",
            "tests/test_decide.py": "import unittest\nfrom kernel import decide\n",
            "tests/test_other.py": "import unittest\nfrom tools import check_x\n\n\nclass Reads(unittest.TestCase):\n"
                                   "    def test_e(self):\n        check_x.run()\n\n\nclass Not(unittest.TestCase):\n"
                                   "    def test_f(self):\n        pass\n",
            "tests/test_simulator.py": "import unittest\nfrom kernel import rule\n"})

    def test_a_hunk_in_tools_names_the_classes_that_reach_it_and_a_slow_class_its_methods(self):
        self.assertEqual(untested.first_tests(self.root, "tools/check_x.py"),
                         ("tests.test_other.Reads", "tests.test_tools.Workflows.test_a", "tests.test_tools.Other"))

    def test_a_hunk_elsewhere_names_each_module_that_reaches_it_but_the_slow_ones(self):
        self.assertEqual(untested.first_tests(self.root, "kernel/rule.py"), ("tests.test_decide",))


class Job(unittest.TestCase):
    def test_on_a_merge_group_it_does_not_run_and_it_is_green_whatever_fails(self):
        for environ, said in (({"EVENT": "merge_group", "BASE_SHA": "a", "HEAD_SHA": "b"}, "does not run"),
                              ({"EVENT": "pull_request"}, "could not run")):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(untested.main(environ), 0)
            self.assertIn(said, out.getvalue())

    def test_a_survivor_is_warned_of_on_its_lines_and_told_its_trailer(self):
        found = {"hunks": [{"path": "pkg/a.py", "new": 4, "new_n": 2, "removes": False, "outcome": "SURVIVED", "why": "",
                            "by": "revert", "covered": False},
                           {"path": "pkg/a.py", "new": 9, "new_n": 1, "removes": False, "outcome": "killed", "why": "",
                            "by": "revert", "covered": False}],
                 "problems": [], "skipped": {}, "trailers": 0}
        log, summary = untested.report(found, 3)
        self.assertIn("::warning file=pkg/a.py,line=4,endLine=5::", "\n".join(log))
        self.assertIn("Behaviour-preserving: pkg/a.py:4-5", "\n".join(log))
        self.assertTrue(log[-1].startswith("untested/1 {"))
        self.assertIn('"survived": 1', log[-1])
        self.assertIn("| SURVIVED | `pkg/a.py:4-5` |", summary)
        self.assertNotIn("9-9", summary)

    def test_the_job_runs_the_bases_tool_on_both_events_and_no_job_needs_it(self):
        text = (WORKFLOWS / "untested.yml").read_text()
        self.assertIn("      - run: python3 -m tools.untested\n", text)
        self.assertIn("          ref: ${{ github.event.pull_request.base.sha || github.event.merge_group.base_sha }}\n", text)
        self.assertNotIn("needs", re.sub(r"(?m)^#.*\n", "", text))
        self.assertNotIn("untested", (WORKFLOWS / "verify.yml").read_text())


if __name__ == "__main__":
    unittest.main()
