"""Whether a reviewing Result reports on every criterion of its rubric that applies (design §3.14, I-37, decision 0029).

`covered` is pure, and `apply` asks it before any Effect; the Kernel reads only the run record it leaves.
"""
from __future__ import annotations

import copy
import json
import unittest

from kernel import terms as t
from kernel.coverage import covered
from tests.support import ROOT, changed

RUBRIC = json.loads((ROOT / "config" / "rubric-pr-review.json").read_text())
# A change to one Kernel module: PR-1 and PR-2 apply to every change, PR-3 to a Python file, PR-4 to the Kernel. PR-5,
# for the documents, does not apply.
KERNEL = [changed("kernel/derive.py")]
APPLYING = ["PR-1", "PR-2", "PR-3", "PR-4"]
# The severity a Finding that cites each criterion has: the rubric's (section 3.14).
SEVERITY = {c["id"]: c["severity_if_violated"] for c in RUBRIC["criteria"]}


def entry(criterion: str, verdict: str = "met", reason=None) -> dict:
    """What a Result says of one criterion."""
    return {"criterion": criterion, "verdict": verdict, "reason": reason}


def every(*over) -> list:
    """An entry `met` for each criterion that applies to KERNEL, but those `over` gives, in their place."""
    given = {e["criterion"]: e for e in over}
    return [given.get(c, entry(c)) for c in APPLYING] + [e for c, e in given.items() if c not in APPLYING]


def finding(criterion, severity=None) -> dict:
    """A Finding of the Result, citing `criterion`, or none, at `severity`, or else the one the rubric gives it."""
    return {"criterion": criterion, "severity": severity or SEVERITY.get(criterion, "minor")}


def rubric_with(criterion: str, **over) -> dict:
    """The rubric, with `over` in place of fields of `criterion`, and a field given as None taken out."""
    out = copy.deepcopy(RUBRIC)
    for c in out["criteria"]:
        if c["id"] == criterion:
            c.update(over)
            for name in [name for name, value in over.items() if value is None]:
                del c[name]
    return out


class Coverage(unittest.TestCase):
    def test_a_criterion_that_applies_must_be_covered(self):  # I-37
        self.assertEqual(covered(RUBRIC, every(), [], KERNEL), ("covered", []))
        # Each criterion that applies, left out, given twice, or given a verdict that is not one, is uncovered.
        for c in APPLYING:
            left = [e for e in every() if e["criterion"] != c]
            self.assertEqual(covered(RUBRIC, left, [], KERNEL), ("uncovered", [c]), c)
            self.assertEqual(covered(RUBRIC, every() + [entry(c)], [], KERNEL), ("uncovered", [c]), c)
            for verdict in ("passed", None, "MET"):
                self.assertEqual(covered(RUBRIC, every(entry(c, verdict)), [], KERNEL), ("uncovered", [c]),
                                 (c, verdict))
        self.assertEqual(covered(RUBRIC, [], [], KERNEL), ("uncovered", APPLYING))
        # An entry for a criterion that does not apply is passed over, whatever it says, and so is its absence.
        for extra in ([], [entry("PR-5")], [entry("PR-5", "nonsense"), entry("PR-5")]):
            self.assertEqual(covered(RUBRIC, every() + extra, [], KERNEL), ("covered", []), extra)
        # An entry for a criterion the rubric does not have is uncovered: by its id, or `unreadable` when it is none.
        self.assertEqual(covered(RUBRIC, every(entry("PR-9")), [], KERNEL), ("uncovered", ["PR-9"]))
        for said in ("pr-9", "PR-", "a sentence", None, 7, "-1", "PR-prose from outside", "PR-9x", "PR9"):
            self.assertEqual(covered(RUBRIC, every() + [entry(said)], [], KERNEL), ("uncovered", ["unreadable"]), said)
        # Each is named once, however often it is given.
        self.assertEqual(covered(RUBRIC, every() + [entry("PR-9"), entry("PR-9")], [], KERNEL), ("uncovered", ["PR-9"]))
        self.assertEqual(covered(RUBRIC, every() + [entry(None), entry(7), "x"], [], KERNEL),
                         ("uncovered", ["unreadable"]))
        self.assertEqual(covered(RUBRIC, every() + [entry("PR-9"), entry("PR-8")], [], KERNEL),
                         ("uncovered", ["PR-9", "PR-8"]))
        self.assertEqual(covered(RUBRIC, every() + ["PR-1"], [], KERNEL), ("uncovered", ["unreadable"]))
        # Coverage or Findings that are no list report on nothing.
        for said, found in ((None, []), ({"PR-1": "met"}, []), (every(), None)):
            self.assertEqual(covered(RUBRIC, said, found, KERNEL), ("uncovered", APPLYING), (said, found))
        # A criterion applies by its own patterns: `**` as a whole name stands for any run of names, none included.
        for path, applying in (("docs/notes.md", ["PR-1", "PR-2", "PR-5"]), ("AGENTS.md", ["PR-1", "PR-2", "PR-5"]),
                               ("sim/AGENTS.md", ["PR-1", "PR-2", "PR-5"]), ("setup.py", ["PR-1", "PR-2", "PR-3"]),
                               ("tools/hooks/protected.py", ["PR-1", "PR-2", "PR-3"]),
                               ("kernel/a/b.txt", ["PR-1", "PR-2", "PR-4"]), ("docsx/a.md", ["PR-1", "PR-2"]),
                               ("Kernel/Derive.PY", APPLYING)):
            self.assertEqual(covered(RUBRIC, [], [], [changed(path)]), ("uncovered", applying), path)
        # One whose `applies_when` cannot be read applies: read as applying to nothing, it could be left out.
        for when in ({"paths": ["../kernel/**"]}, {"paths": []}, {"paths": "kernel/**"}, {}, None, "kernel/**",
                     {"paths": [""]}, {"paths": [None]}):
            rubric = copy.deepcopy(RUBRIC)
            rubric["criteria"][3]["applies_when"] = when
            self.assertEqual(covered(rubric, [], [], [changed("docs/notes.md")]),
                             ("uncovered", ["PR-1", "PR-2", "PR-4", "PR-5"]), when)

    def test_a_renamed_files_old_path_makes_a_criterion_apply(self):  # I-37
        # A file moved off the Kernel changes the Kernel: the path it had before is read as one the change touches.
        moved = [changed("docs/notes.md", "kernel/derive.py")]
        self.assertEqual(covered(RUBRIC, [entry("PR-1"), entry("PR-2"), entry("PR-5")], [], moved),
                         ("uncovered", ["PR-3", "PR-4"]))
        self.assertEqual(covered(RUBRIC, every(entry("PR-5")), [], moved), ("covered", []))
        # The other side: with no previous path, neither applies.
        self.assertEqual(covered(RUBRIC, [entry("PR-1"), entry("PR-2"), entry("PR-5")], [], [changed("docs/notes.md")]),
                         ("covered", []))

    def test_not_applicable_needs_a_reason_code(self):  # I-37
        for c in APPLYING:
            self.assertEqual(covered(RUBRIC, every(entry(c, "not_applicable", "no_linked_issue")), [], KERNEL),
                             ("covered", []), c)
            for reason in (None, "", "No linked issue.", "no linked issue", "no-linked-issue", "NO_ISSUE", 1, ["a"]):
                self.assertEqual(covered(RUBRIC, every(entry(c, "not_applicable", reason)), [], KERNEL),
                                 ("uncovered", [c]), (c, reason))

    def test_a_finding_verdict_needs_a_finding_that_cites_it(self):  # I-37
        for c in APPLYING:
            said = every(entry(c, "finding"))
            self.assertEqual(covered(RUBRIC, said, [finding(c)], KERNEL), ("covered", []), c)
            # With no Finding that cites it, or only one that cites another criterion or none, it is uncovered.
            for found in ([], [finding("PR-5")], [finding(None)], [finding("PR-9")], ["%s" % c]):
                self.assertEqual(covered(RUBRIC, said, found, KERNEL), ("uncovered", [c]), (c, found))
            # A Finding that cites a criterion said to be `met`, or not to apply, contradicts it.
            for verdict, reason in (("met", None), ("not_applicable", "no_linked_issue")):
                self.assertEqual(covered(RUBRIC, every(entry(c, verdict, reason)), [finding(c)], KERNEL),
                                 ("uncovered", [c]), (c, verdict))
        # A Finding off the rubric, or citing a criterion that does not apply, contradicts nothing.
        self.assertEqual(covered(RUBRIC, every(), [finding(None), finding("PR-5")], KERNEL), ("covered", []))

    def test_a_finding_that_cites_a_criterion_has_the_rubrics_severity(self):  # section 3.14, issue 373
        # A model that grades a cited Finding below the rubric would post it as an annotation, off the gate; one that
        # grades it above has still not taken the rubric's. Either leaves the criterion uncovered, and so does no
        # severity at all, whether the criterion applies or not.
        for c in SEVERITY:
            said = every(entry(c, "finding")) if c in APPLYING else every()
            self.assertEqual(covered(RUBRIC, said, [finding(c)], KERNEL), ("covered", []), c)
            for other in [s for s in t.SEVERITIES if s != SEVERITY[c]] + ["Major", "", None, 2]:
                given = dict(finding(c), severity=other)
                self.assertEqual(covered(RUBRIC, said, [given], KERNEL), ("uncovered", [c]), (c, other))
            self.assertEqual(covered(RUBRIC, said, [{"criterion": c}], KERNEL), ("uncovered", [c]), c)
            # Named once, however many Findings cite it.
            twice = [finding(c, "info"), finding(c, "info"), finding(c)]
            self.assertEqual(covered(RUBRIC, said, twice, KERNEL), ("uncovered", [c]), c)
        # Beside the rest of what is uncovered.
        self.assertEqual(covered(RUBRIC, every(entry("PR-2", "finding"), entry("PR-9")), [finding("PR-2", "info")],
                                 KERNEL), ("uncovered", ["PR-2", "PR-9"]))
        # The other side: a Finding off the rubric has the severity the model gives it.
        for severity in t.SEVERITIES:
            self.assertEqual(covered(RUBRIC, every(), [finding(None, severity)], KERNEL), ("covered", []), severity)

    def test_an_unreadable_rubric_is_unreadable_never_covered(self):  # I-13
        # The Factory's fault, never the item's: whatever the Result says, nothing is read as covered.
        # Each criterion with an id at fault gives a severity, so that its id alone is what cannot be read.
        major = {"severity_if_violated": "major"}
        broken = [None, [], {}, {"criteria": []}, {"criteria": "PR-1"}, {"criteria": [None]},
                  {"criteria": [dict(major, statement="no id")]}, {"criteria": [dict(major, id="pr-1")]},
                  {"criteria": [dict(major, id=1)]}, {"criteria": [dict(major, id="PR-1"), dict(major, id="PR-1")]},
                  {"criteria": [dict(major, id="-1")]}, {"criteria": [dict(major, id="PR-x")]},
                  # A criterion with no severity that a Finding citing it could be given.
                  {"criteria": [{"id": "PR-1"}]}, {"criteria": [{"id": "PR-1", "severity_if_violated": "Major"}]},
                  {"criteria": [{"id": "PR-1", "severity_if_violated": None}]},
                  rubric_with("PR-2", severity_if_violated=None), rubric_with("PR-5", severity_if_violated="high")]
        for rubric in broken:
            for said in (every(), []):
                self.assertEqual(covered(rubric, said, [], KERNEL), ("unreadable", []), (rubric, len(said)))
        # So are paths that cannot be read whole, or were not read in full, which the caller gives as None.
        for paths in ([changed("../kernel/x.py")], [changed("kernel//x.py")], [changed("docs/a.md", "")],
                      [changed("docs/a.md", "../kernel/x.py")], [changed("docs/a.md"), changed("kernel/../x.py")],
                      None, "kernel/derive.py", [None], [{"path": "kernel/derive.py"}], [changed(None)]):
            self.assertEqual(covered(RUBRIC, every(), [], paths), ("unreadable", []), paths)
        # The other side: a rubric of one criterion that applies to everything, and no paths at all, are read.
        one = {"criteria": [{"id": "X-1", "severity_if_violated": "info"}]}
        self.assertEqual(covered(one, [entry("X-1")], [], []), ("covered", []))
        self.assertEqual(covered(one, [], [], []), ("uncovered", ["X-1"]))
        two = {"criteria": [dict(major, id="PR-1"), dict(major, id="PR-2")]}
        self.assertEqual(covered(two, [entry("PR-1"), entry("PR-2")], [], []), ("covered", []))
        self.assertEqual(covered(rubric_with("PR-3", applies_when=None), [], [], [changed("docs/a.md")]),
                         ("uncovered", ["PR-1", "PR-2", "PR-3", "PR-5"]))


if __name__ == "__main__":
    unittest.main()
