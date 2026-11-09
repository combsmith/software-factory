"""The advisory check of issue 589: a changed line of Python that no test notices (tools/untested.py)."""
from __future__ import annotations

import contextlib
import io
import os
import pathlib
import re
import subprocess
import tempfile
import unittest
from unittest import mock

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


def checked(base: dict, head: dict, message: str = "the change", deadline: float = float("inf")) -> dict:
    """`untested.check` of the change, its deadline never reached unless one is given: no test here reads the clock."""
    made, root, first, last = change(base, head, message)
    with made:
        return untested.check(root, first, last, deadline, workers=2)


def outcomes(found: dict) -> list:
    return [(h["path"], h["new"], h["outcome"], h.get("by")) for h in found["hunks"]]


class Reverts(unittest.TestCase):
    def test_a_revert_no_test_notices_survives_and_one_a_test_notices_is_killed(self):
        for ending in ("\n", "\r\n"):    # a file's line endings, kept as they are
            calc = CALC.replace("\n", ending)
            base = {"pkg/calc.py": calc.replace("if a > b:", "if a < b:"), "tests/test_calc.py": CALC_TEST}
            found = checked(base, {"pkg/calc.py": calc.replace("-> int:", "-> float:").replace("x * 2", "x * 3")})
            self.assertEqual(outcomes(found), [("pkg/calc.py", 6, "killed", "revert"),
                                               ("pkg/calc.py", 12, "SURVIVED", "revert")], repr(ending))
            self.assertEqual(found["skipped"]["same"], 1)      # the annotation

    def test_the_change_is_read_from_the_merge_base_and_not_from_main_as_it_moved_on(self):
        # Muse's read of #634: main changed pkg/calc.py after the branch left it. Read from main as it is, the change
        # would hold main's own hunk, put back; read from the merge base, it holds the branch's alone.
        made, root, first, main = change({"pkg/calc.py": CALC, "tests/test_calc.py": CALC_TEST},
                                         {"pkg/calc.py": CALC.replace("if a > b:", "if b < a:")}, "main moves on")
        with made:
            git(root, "checkout", "-q", "-b", "branch", first)
            tree(root, {"pkg/calc.py": CALC.replace("x * 2", "x * 3")})
            git(root, "commit", "-q", "-am", "the branch")
            found = untested.check(root, main, git(root, "rev-parse", "HEAD").strip(), float("inf"), workers=2)
            self.assertEqual(outcomes(found), [("pkg/calc.py", 12, "SURVIVED", "revert")])

    def test_a_line_is_what_git_numbers_one_and_not_each_break_python_splits_on(self):
        label = 'LABEL = "a b\x0cc"\n\n\ndef f():\n    return %d\n'
        test = "import unittest\n\nfrom pkg import label\n\n\nclass L(unittest.TestCase):\n    def test_f(self):\n" \
               "        self.assertEqual(label.f(), 2)\n"
        found = checked({"pkg/label.py": label % 1, "tests/test_label.py": test}, {"pkg/label.py": label % 2})
        self.assertEqual((outcomes(found), found["skipped"]["same"]), ([("pkg/label.py", 5, "killed", "revert")], 0))
        made = dict(untested.candidates(label % 2, {"new": 5, "new_n": 1}))
        self.assertEqual(made[5].split("\n")[4], "    return 3")
        self.assertEqual(untested.data_lines('MUTANTS = [\n    "a b",\n\n    2,\n]\n'), {2, 3, 4})

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
        said = untested.counts(found, 0)
        self.assertEqual((said["killed"], said["killed_by_file"]), (1, 1))
        self.assertEqual(untested.crashed(CRASHED), "NameError")
        self.assertEqual(untested.crashed(CRASHED.replace("ERROR:", "FAIL:")), "")
        self.assertEqual(untested.crashed(CRASHED.replace("NameError", "AttributeError")), "")
        long = CRASHED.replace("tests.test_calc.Calc", "tests.test_calc." + "Calc" * 60)     # past the width of a log's line
        self.assertEqual(untested.crashed(long), "NameError")

    def test_a_small_hunk_no_edit_of_which_runs_is_unchecked_and_a_large_one_gets_mutants(self):
        test = "import unittest\n\nfrom pkg.%s import f\n\n\nclass T(unittest.TestCase):\n    def test_f(self):\n" \
               "        self.assertEqual(f(1), 1)\n"
        large = "def f(x):\n    if x > 0:\n        return x\n    return 0\n" + "".join("\n\ndef g%d(y):\n    return y + %d\n" % (n, n)
                                                                              for n in range(10))
        found = checked({}, {"pkg/small.py": "def f(x):\n    return x\n", "tests/test_small.py": test % "small",
                             "pkg/large.py": large, "tests/test_large.py": test % "large"})
        by_path = {h["path"]: h for h in found["hunks"]}
        self.assertEqual(sorted(by_path), ["pkg/large.py", "pkg/small.py"])      # never tests/
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
        # The comparison's own operator, not one a string holds before it (Muse's read of #634).
        quoted = dict(untested.candidates("def g(x):\n    return 'a < b' + str(x < 3)\n", {"new": 2, "new_n": 1}))
        self.assertIn("    return 'a < b' + str(x <= 3)\n", quoted[2])
        # A comparison it cannot swap is passed over, and one on another line of the statement is never read here.
        passed = dict(untested.candidates("def g(x, y):\n    return x == 1 or y < 2\n", {"new": 2, "new_n": 1}))
        self.assertIn("    return x == 1 or y <= 2\n", passed[2])
        spread = dict(untested.candidates("def h(y):\n    return g(1,\n             y < 2)\n", {"new": 2, "new_n": 2}))
        self.assertIn("    return g(2,\n", spread[2])
        for now, then in (("x > 3", "x >= 3"), ("x >= 3", "x > 3")):
            swapped = dict(untested.candidates("def g(x):\n    return %s\n" % now, {"new": 2, "new_n": 1}))
            self.assertIn("    return %s\n" % then, swapped[2], now)
        self.assertIn("    pass\n", dict(untested.candidates("def f(x):\n    g(x)\n", {"new": 2, "new_n": 1}))[2])
        annotated = "from __future__ import annotations\n\n\ndef f(x: Literal[0]) -> int:\n    return x + 1\n"
        self.assertEqual(sorted(dict(untested.candidates(annotated, {"new": 4, "new_n": 2}))), [5])
        many = "def f(x):\n" + "".join("    x = x + %d\n" % n for n in range(20))
        self.assertEqual(len(untested.candidates(many, {"new": 2, "new_n": 20})), untested.MOST)

    def test_a_hunk_that_only_removes_is_put_back_where_it_was(self):
        self.assertEqual(untested.revert(["a\n", "c\n"], ["a\n", "b\n", "c\n"], {"old": 2, "old_n": 1, "new": 1, "new_n": 0}),
                         ["a\n", "b\n", "c\n"])
        base = {"pkg/calc.py": CALC.replace('two."""\n', 'two."""\n    noted = 1\n').replace("(x):\n", "(x):\n    x = x + 1\n"),
                "tests/test_calc.py": CALC_TEST + "        self.assertEqual(calc.doubled(2), 4)\n"}
        found = checked(base, {"pkg/calc.py": CALC})
        self.assertEqual([(h["new"], h["removes"], h["outcome"], h["by"]) for h in found["hunks"]],
                         [(5, True, "SURVIVED", "revert"), (11, True, "killed", "revert")])
        log = "\n".join(untested.report(found, 1)[0])
        self.assertIn("::warning file=pkg/calc.py,line=6,endLine=6::", log)
        self.assertIn("Behaviour-preserving: pkg/calc.py:6-6", log)
        self.assertEqual(untested.counts(found, 1)["survived_removing"], 1)

    def test_an_edit_that_does_not_parse_or_import_is_never_a_kill(self):
        listed = "def f():\n    return (1,\n            0,\n            2)\n"
        test = "import unittest\n\nfrom pkg import a\n\n\nclass A(unittest.TestCase):\n    def test_f(self):\n" \
               "        self.assertEqual(list(a.f()), [1, 0, 2])\n"
        found = checked({"pkg/a.py": "import json_not_here\n\n\n" + listed, "tests/test_a.py": test},
                        {"pkg/a.py": "\n\n" + listed.replace("(1,", "[1,").replace("2)", "2]")})
        self.assertEqual([(h["new"], h["outcome"], h["why"].split(":")[0]) for h in found["hunks"]],
                         [(0, "UNCHECKED", "UNIMPORTABLE"), (4, "UNCHECKED", "UNPARSABLE"), (6, "UNCHECKED", "UNPARSABLE")])
        said = untested.counts(found, 0)
        self.assertEqual((said["fallback_file"], said["fallback_mutants"]), (3, 0))     # tried, and no edit of it ran

    def test_a_hunk_of_more_than_forty_added_lines_alone_falls_back_to_mutants(self):
        made = lambda n: "def f(x):\n    return x\n" + "".join("y%d = %d\n" % (k, k) for k in range(n - 2))
        test = "import unittest\n\nfrom pkg import f40, f41\n\n\nclass T(unittest.TestCase):\n    def test_f(self):\n" \
               "        f40.f(1), f41.f(1)\n"

        heads = {"f40.py": made(40), "f41.py": made(41)}

        def run(work, first=(), only=None, **given):
            texts = {name: (work / "pkg" / name).read_text() for name in heads}
            if any(not text.strip() for text in texts.values()):
                return 1, CRASHED
            if self.mode == "spent" and not only:      # as bounded() runs it, a kill's confirmation is never cut
                raise untested.OverBudget()
            if self.mode == "mixed" and texts != heads:     # a mutant: the dropped statement hangs, the rest are noticed
                return (None, "") if "    pass\n" in texts["f41.py"] else (1, NOTICED)
            if self.mode == "partial" and texts != heads:   # a mutant: the first is noticed, the budget leaves the rest
                if "    pass\n" in texts["f41.py"]:
                    return 1, NOTICED
                if not only:
                    raise untested.OverBudget()
            return 0, "OK\n"
        for mode, f41 in (("survive", ("SURVIVED", "mutants")), ("spent", ("UNCHECKED", "mutants")),
                          ("mixed", ("ERROR", "mutants")), ("partial", ("UNCHECKED", "mutants"))):
            self.mode = mode
            made_at, root, first, last = change({}, {"pkg/f40.py": made(40), "pkg/f41.py": made(41), "tests/test_f.py": test})
            with made_at:
                found = untested.check(root, first, last, float("inf"), run=run, workers=1)
            by_path = {h["path"]: h for h in found["hunks"]}
            self.assertEqual((by_path["pkg/f40.py"]["outcome"], by_path["pkg/f40.py"].get("by")), ("UNCHECKED", "revert"))
            self.assertEqual((by_path["pkg/f41.py"]["outcome"], by_path["pkg/f41.py"]["by"]), f41)
            if mode in ("spent", "partial"):
                self.assertEqual(by_path["pkg/f41.py"]["why"], "over budget")
                self.assertEqual(untested.counts(found, 0)["over_budget"], 1)

    def test_no_run_lasts_past_one_timeout_after_the_budget(self):
        seen = []
        with mock.patch.object(untested.time, "monotonic", return_value=1000.0), \
                mock.patch.object(untested.mutants, "_unittest", lambda cwd, timeout, args: seen.append(timeout) or (0, "")):
            late = untested.bounded(900.0)      # past the budget, within one TIMEOUT of it
            self.assertEqual(late(pathlib.Path("."), only="tests.test_x"), (0, ""))
            self.assertEqual(seen, [900.0 + untested.mutants.TIMEOUT - 1000.0])
            with self.assertRaises(untested.OverBudget):
                late(pathlib.Path("."), first=("tests.test_x",))
            self.assertEqual(len(seen), 1)      # the named tests did not begin
            with self.assertRaises(untested.OverBudget):
                untested.bounded(1000.0 - untested.mutants.TIMEOUT)(pathlib.Path("."), only="tests.test_x")
            untested.bounded(2000.0)(pathlib.Path("."), only="tests.test_x")
        self.assertEqual(seen[-1], untested.mutants.TIMEOUT)

    def test_no_import_of_an_edit_is_probed_past_the_budget(self):
        made = tempfile.TemporaryDirectory()
        self.addCleanup(made.cleanup)
        root = pathlib.Path(made.name) / "head"
        tree(root, {"pkg/__init__.py": "", "pkg/a.py": "A = 1\n"})
        probed = []

        def run(work, **given):
            raise AssertionError("no run of the tests past the budget")
        with mock.patch.object(untested, "importable", lambda work, module: probed.append(module) or True):
            said = untested.edit("an edit", "pkg/a.py", "A = 1\n", "A = 2\n", (), root, run,
                                 untested.mutants.Trees(root, made.name), True, float("-inf"))
        self.assertEqual((said, probed), (("UNCHECKED", "over budget"), []))

    def test_the_suite_is_not_read_past_the_budget(self):
        read = []
        with mock.patch.object(untested.time, "monotonic", side_effect=[998.0, 998.0, 1000.0]), \
                mock.patch.object(untested.mutants, "_unittest", lambda cwd, timeout, args: (0, "")), \
                mock.patch.object(untested.mutants, "whole_suite", lambda cwd: read.append(cwd) or []):
            with self.assertRaises(untested.OverBudget):
                untested.bounded(999.0)(pathlib.Path("."), first=("tests.test_x",))
        self.assertEqual(read, [])

    def test_a_path_a_pull_request_names_is_read_only_in_plain_characters(self):
        found = checked({}, {"pkg/odd name.py": "x = 1\n", "pkg/plain.py": "x = 1\n"})
        self.assertEqual(found["skipped"]["unsafe_path"], 1)
        self.assertEqual([h["path"] for h in found["hunks"]], ["pkg/plain.py"])

    def test_no_run_of_the_tests_begins_past_the_budget(self):
        base = {"pkg/calc.py": CALC, "tests/test_calc.py": CALC_TEST}
        probed = []
        with mock.patch.object(untested, "importable", lambda work, module: probed.append(module) or True):
            found = checked(base, {"pkg/calc.py": CALC.replace("x * 2", "x * 3")}, deadline=float("-inf"))
        self.assertEqual([(h["outcome"], h["why"]) for h in found["hunks"]], [("UNCHECKED", "over budget")])
        self.assertEqual(probed, [])        # no import is probed past the budget, the head's or an edit's

    def test_the_lists_of_mutants_are_data_and_the_runner_below_them_is_read(self):
        text = ("def run():\n    return 4\n\n\nISSUE = [\n    1,\n]\nMUTANTS = [\n    2,\n    # a note\n"
                "    3 if os.environ else 2,\n] + [m for m in (\n    (4, run(5)),\n) if m]\n\n\ndef main():\n"
                "    return run()\n")
        data = untested.data_lines(text)
        self.assertEqual(data, {6, 9, 10, 13})
        self.assertEqual(untested.data_lines("MUTANTS = [m for m in (1, 2) if True]\n"), set())
        self.assertEqual(untested.data_lines("MUTANTS = [\n    (1, 2),\n    (3, 4)] + [\n    (5, 6)]\n"), {2})
        self.assertTrue(untested.is_data({"new": 9, "new_n": 2, "old": 9, "old_n": 1}, data, data))
        self.assertTrue(untested.is_data({"new": 12, "new_n": 0, "old": 13, "old_n": 1}, data, data))
        for hunk in ({"new": 11, "new_n": 1, "old": 11, "old_n": 1}, {"new": 12, "new_n": 1, "old": 12, "old_n": 1},
                     {"new": 14, "new_n": 1, "old": 14, "old_n": 1}, {"new": 18, "new_n": 1, "old": 18, "old_n": 1},
                     {"new": 2, "new_n": 1, "old": 2, "old_n": 1}, {"new": 9, "new_n": 1, "old": 11, "old_n": 1}):
            self.assertFalse(untested.is_data(hunk, data, data), hunk)

    def test_a_call_in_the_mutant_lists_is_data_only_of_the_modules_own_helpers(self):
        # Muse's read of #634: a call of a builtin or of another module's function may read the world, so the entry
        # that holds it decides, and its hunk is run. A helper the module defines, and a text's replace, are data.
        text = ("MUTANTS = [\n    ('a', helper('x')),\n    ('b', os.getenv('X', 'old')),\n    ('c', abs(-1)),\n"
                "    ('d', open('x').read()),\n    ('e', __import__('os').getenv('X')),\n"
                "    ('f', TEXT.replace('a', 'b')),\n    ('g', helper(x=1)),\n    ('h', ROOT.replace('x')),\n"
                "    ('i', os.environ['X']),\n    ('j', sys.platform),\n    ('k', OLD[sys.platform]),\n"
                "    ('l', helper('x').replace('x', 'y')),\n    ('m', 'a b'.replace('a', 'c')),\n]\n")
        head = ("import os\nimport sys\nimport pathlib\nTEXT = 'a'\nROOT = pathlib.Path('.')\n\n\n"
                "def helper(text: str) -> str:\n    return text\n\n\n")
        # A text's replace is data, but ROOT's, a path's, renames a file; what is read of os or sys reads the runner.
        self.assertEqual(untested.data_lines(head + text), {13, 18, 24, 25})
        # Another module's replace renames a file, as does a path's; a name bound twice may be anything, as here, where
        # the list is read while helper is still os.getenv; a helper defined after the list is no helper of it.
        self.assertEqual(untested.data_lines("import os\nMUTANTS = [\n    ('a', os.replace('x', 'y')),\n"
                                             "    ('b', open('x').read().replace('a', 'b')),\n]\n"), set())
        shadowed = ("from os import getenv as helper\nMUTANTS = [\n    ('a', helper('X')),\n]\n\n\n"
                    "def helper(x):\n    return x\n")
        self.assertEqual(untested.data_lines(shadowed), set())
        later = "MUTANTS = [\n    ('a', later('X')),\n]\n\n\ndef later(x):\n    return x\n"
        self.assertEqual(untested.data_lines(later), set())
        # A, B = x, y binds each name to its own value, as tools/mutants.py binds the issue Kernel's path and tests.
        paired = "PY, TESTS = 'kernel/issue.py', ('t',)\nMUTANTS = [\n    ('a', PY.replace('k', 'K'), TESTS),\n]\n"
        self.assertEqual(untested.data_lines(paired), {3})
        # Muse's and the Claude review's further cases. A walrus, a global in a helper, a method that fills a list, and
        # globals() or eval may each change a name past what its assignment says; a helper's __globals__ is the whole
        # module; a decorator may make a helper anything; and only a helper that says it gives a text gives one.
        for case in ("import os\nTEXT = 'a'\nA = (TEXT := os.environ['X'])\nMUTANTS = [\n    ('a', TEXT),\n]\n",
                     "import os\nVAL = [1]\nVAL.append(os.environ['X'])\nMUTANTS = [\n    ('a', VAL),\n]\n",
                     "import os\nTEXT = 'a'\nglobals()['TEXT'] = os.environ['X']\nMUTANTS = [\n    ('a', TEXT),\n]\n",
                     "TEXT = 'a'\nMUTANTS = [\n    (eval('1'), TEXT),\n]\n",
                     "import os\nTEXT = 'a'\nMUTANTS = [\n    (TEXT := os.environ['X'], TEXT),\n]\n",
                     "import os\nTEXT = 'a'\n\n\ndef helper():\n    global TEXT\n    TEXT = os.environ['X']\n"
                     "    return 1\n\n\nMUTANTS = [\n    ('b', TEXT),\n]\n",
                     "import os\nVAL = [1]\n\n\ndef helper(x):\n    VAL.append(x)\n    return x\n\n\n"
                     "MUTANTS = [\n    ('b', VAL),\n]\n",
                     "import os\n\n\ndef helper(x):\n    return x\n\n\nMUTANTS = [\n"
                     "    ('a', helper.__globals__['os'].environ['X']),\n]\n",
                     "import os\n\n\n@lambda f: os.getenv\ndef helper(x):\n    return x\n\n\nMUTANTS = [\n"
                     "    ('a', helper('X')),\n]\n",
                     "import pathlib\nROOT = pathlib.Path('.')\n\n\ndef helper():\n    return ROOT\n\n\nMUTANTS = [\n"
                     "    ('a', helper().replace('x')),\n]\n",
                     "import os\nMUTANTS = [\n    ('a', os.environ['X'].replace('a', 'b').replace('c', 'd')),\n]\n",
                     "import os\n\n\ndef helper(x):\n    return x\n\n\nglobals()['helper'] = os.getenv\nMUTANTS = [\n"
                     "    ('a', helper('X')),\n]\n",
                     "import os\nVAL = [1]\n\n\ndef helper(x):\n    VAL[0] = os.environ['X']\n    return x\n\n\n"
                     "MUTANTS = [\n    ('b', VAL),\n]\n",
                     "def open(x) -> str:\n    return x\n\n\ndel open\nMUTANTS = [\n    ('a', open('README.md')),\n]\n",
                     "import os\n\n\ndef helper(x):\n    VAL.append(os.environ['X'])\n    return x\n\n\nVAL = [1]\n"
                     "MUTANTS = [\n    ('b', VAL),\n]\n",
                     "import os\nEMPTY = ()\nA, B = *EMPTY, *(os.getcwd(), os.getcwd())\nMUTANTS = [\n    ('a', A),\n]\n",
                     "TEXT = 'a'\nMUTANTS = [\n    ('a', TEXT.format(1)),\n]\n"):
            self.assertEqual(untested.data_lines(case), set(), case)
        # A helper's own name, an annotated text, and a method on a text are no change to what a name is.
        kept = ("TEXT: str = 'a'\nPAIR = ('a', 'b')\n\n\ndef helper(text: str, PAIR=()) -> str:\n    text.upper()\n"
                "    PAIR.index('a')\n    return text\n\n\nMUTANTS = [\n    ('a', TEXT.replace('a', 'b')),\n"
                "    ('b', helper('x').replace('x', 'y')),\n    ('c', PAIR),\n]\n")
        self.assertEqual(untested.data_lines(kept), {12, 13, 14})
        later = ("def helper(x: str) -> str:\n    return LATER.replace('a', x)\n\n\nLATER = 'a'\nMUTANTS = [\n"
                 "    ('a', LATER.replace('a', 'b')),\n]\n")
        self.assertEqual(untested.data_lines(later), {7})
        # An import behind an if, a try or a with binds its name as one at the top does; a star import binds names no
        # one can read, so a name nothing bound is code; and so is a name bound to what code gave, or by an unpacking.
        for fenced in ("if True:\n    import os\n", "try:\n    import os\nexcept ImportError:\n    os = None\n",
                       "with x:\n    import os.path\n", "import os.path\n", "from os import *\n",
                       "import os\nENV = os.environ\n", "import os\nA, B = os.environ['X'].split()\n",
                       "import pathlib\nENV = 'a'\nfor ENV in [pathlib.Path('.')]:\n    pass\n",
                       "class ENV:\n    pass\n", "os = 'a'\nif True:\n    import os\n", "os = 'a'\nimport os.path\n",
                       "ENV = 'a'\nENV, B = os.environ['X'].split()\n"):
            for read in ("os.environ['X']", "environ['X']", "ENV['X']", "A", "ENV.replace('x')"):
                text = fenced + "MUTANTS = [\n    ('a', %s),\n]\n" % read
                self.assertEqual(untested.data_lines(text), set(), text)


CRASHED = ("=" * 70 + "\nERROR: test_x (tests.test_calc.Calc)\n" + "-" * 70 + "\nTraceback (most recent call last):\n"
           "  File \"x.py\", line 1, in test_x\nNameError: name 'pick' is not defined\n\n" + "-" * 70 +
           "\nRan 1 test in 0.001s\n\nFAILED (errors=1)\n")
NOTICED = CRASHED.replace("ERROR:", "FAIL:").replace("NameError: name 'pick' is not defined", "AssertionError: 1 != 2") \
    .replace("errors=1", "failures=1")


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

    def test_a_trailers_span_is_never_read_line_by_line(self):
        def short(*args):
            made = range(*args)     # this module's own, which the patch leaves as it is
            if len(made) > 10 ** 6:
                raise AssertionError("a range of %d lines" % len(made))
            return made
        far = 10 ** 12
        with mock.patch.object(untested, "range", short, create=True):
            said = [untested.read_trailers([value], self.HUNKS) for value in ("pkg/a.py:12-%d" % far, "pkg/a.py:22-%d" % far)]
        self.assertEqual(said[0], ([("pkg/a.py", 12, far)], []))
        self.assertEqual(said[1][0], [])
        self.assertIn("names lines no hunk changed", said[1][1][0])

    def test_the_head_commits_trailer_covers_its_survivor(self):
        base = {"pkg/calc.py": CALC, "tests/test_calc.py": CALC_TEST}
        message = "Faster doubling\n\nIt keeps behaviour.\n\nBehaviour-preserving: pkg/calc.py:12-12\nCo-Authored-By: x <x@x>\n"
        found = checked(base, {"pkg/calc.py": CALC.replace("x * 2", "x + x")}, message)
        self.assertEqual([(h["outcome"], h["covered"]) for h in found["hunks"]], [("SURVIVED", True)])
        self.assertEqual(found["problems"], [])
        reworded = checked(base, {"pkg/calc.py": CALC.replace("The bigger", "Which is bigger")},
                           "Reworded\n\nBehaviour-preserving: pkg/calc.py:5-5\n")
        self.assertEqual((reworded["hunks"], reworded["problems"]), ([], []))

    def test_a_trailer_is_read_from_the_head_commit_alone(self):
        # Muse's read of #634: lines move each fix round, so a trailer an earlier commit of the change wrote names lines
        # that may no longer be the ones it meant, and is never read.
        made, root, first, earlier = change({"pkg/calc.py": CALC}, {"pkg/calc.py": CALC.replace("x * 2", "x + x")},
                                            "Faster\n\nBehaviour-preserving: pkg/calc.py:12-12\n")
        with made:
            self.assertEqual(untested.trailers(root, earlier), ["pkg/calc.py:12-12"])
            tree(root, {"pkg/notes.py": "A = 1\n"})
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "A fix round\n\nIt says nothing of the lines.\n")
            self.assertEqual(untested.trailers(root, git(root, "rev-parse", "HEAD").strip()), [])
            self.assertEqual(untested.trailers(root, earlier), ["pkg/calc.py:12-12"])     # the commit asked, not HEAD


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
            with mock.patch.dict(os.environ), contextlib.redirect_stdout(out):
                self.assertEqual(untested.main(environ), 0)
            self.assertIn(said, out.getvalue())

    def test_the_heads_tests_are_given_no_file_the_runner_reads_back(self):
        given = {name: "/nowhere/" + name for name in ("GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_PATH",
                                                       "GITHUB_STATE")}
        seen = {}

        def check(*args, **kwargs):
            seen.update(os.environ)
            return {"hunks": [], "problems": [], "skipped": {}, "trailers": 0}
        with mock.patch.dict(os.environ, given), mock.patch.object(untested, "check", check), \
                mock.patch.object(untested, "git", lambda *args: ""), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(untested.main(dict(given, EVENT="pull_request", BASE_SHA="a", HEAD_SHA="b")), 0)
        self.assertTrue(seen)
        self.assertEqual(set(given) & set(seen), set())

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
