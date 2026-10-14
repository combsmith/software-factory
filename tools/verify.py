"""One command: everything the required check will run. `make verify`.

`make fast` runs the same checks and every test but the seeded simulation, which is most of the
time `make verify` takes. A session runs it after each edit (`tools/hooks/after_edit.py`).
"""
from __future__ import annotations

import pathlib
import sys
import unittest

from tools import (check_apps, check_authority, check_context, check_examples, check_lifecycle, check_purity,
                   check_repo, check_trials, check_workflows)

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECKS = [
    ("schemas and examples", check_examples.run),
    ("lifecycle", check_lifecycle.run),
    ("authority", check_authority.run),
    ("apps", check_apps.run),
    ("kernel purity", check_purity.run),
    ("trials", check_trials.run),
    ("repo", check_repo.run),
    ("workflows", check_workflows.run),
    ("context", check_context.run),
]
# The test modules `make fast` leaves out. `make verify` runs them all.
SLOW = ("test_simulator",)


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


def modules(fast: bool) -> list:
    """The test modules to run: every one, or, when fast, every one but the slow."""
    found = sorted(p.stem for p in (ROOT / "tests").glob("test_*.py"))
    return [m for m in found if not (fast and m in SLOW)]


def main(argv: list) -> int:
    fast = "--fast" in argv
    checks_failed = failed(CHECKS)
    unverified(check_trials.unverified())
    names = ["tests." + m for m in modules(fast)]
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 1 if checks_failed or not result.wasSuccessful() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
