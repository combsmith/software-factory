"""One command: everything the required check will run. `make verify`.

`make fast` runs the same checks and every test but the seeded simulation, which is most of the
time `make verify` takes. A session runs it after each edit (`tools/hooks/after_edit.py`).
"""
from __future__ import annotations

import pathlib
import sys
import unittest

from tools import (check_apps, check_authority, check_context, check_decisions, check_examples, check_lifecycle,
                   check_purity, check_release, check_repo, check_rulesets, check_trials, check_workflows)

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECKS = [
    ("schemas and examples", check_examples.run),
    ("lifecycle", check_lifecycle.run),
    ("authority", check_authority.run),
    ("apps", check_apps.run),
    ("rulesets", check_rulesets.run),
    ("kernel purity", check_purity.run),
    ("trials", check_trials.run),
    ("release", check_release.run),
    ("repo", check_repo.run),
    ("workflows", check_workflows.run),
    ("context", check_context.run),
    ("decision records", check_decisions.run),
]
# The test modules `make fast` leaves out. `make verify` runs them all.
SLOW = ("test_simulator", "test_issue_simulator")


def failed(checks: list) -> bool:
    """Run each check, print what it found, and say whether any found a problem."""
    any_failed = False
    for name, check in checks:
        problems = check()
        print("%-22s %s" % (name, "ok" if not problems else "FAILED"))
        for p in problems:
            print("    " + p)
        any_failed = any_failed or bool(problems)
    return any_failed


def unverified(rules: list) -> None:
    """Print each rule of the fake GitHub that no trial has grounded. It fails nothing (design, section 4.5)."""
    print("%-22s %d unverified" % ("fake GitHub", len(rules)))
    for rule in rules:
        print("    unverified: " + rule)


def _modules(tests) -> set:
    found = set()
    for item in tests:
        found |= _modules(item) if isinstance(item, unittest.TestSuite) else {type(item).__module__}
    return found


def suite(fast: bool) -> unittest.TestSuite:
    """Every test module under tests/, at any depth; when fast, all but those in SLOW."""
    whole = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    if not fast:
        return whole
    slow = {"tests." + name for name in SLOW}
    return unittest.TestSuite(item for item in whole if not _modules(item) & slow)


def main(argv: list) -> int:
    checks_failed = failed(CHECKS)
    print("%-22s %s" % ("decision base", check_decisions.described()))
    unverified(check_trials.unverified())
    result = unittest.TextTestRunner(verbosity=1).run(suite("--fast" in argv))
    return 1 if checks_failed or not result.wasSuccessful() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
