"""One command: everything the required check will run. `make verify`.

`make fast` runs the same checks and every test but the seeded simulation. `make checks` runs the checks alone, half a
minute, and is what a session's hooks run after an edit and before a stop (`tools/hooks/after_edit.py`,
`tools/hooks/before_stop.py`), and what the desk owes with the mutants of the files a change touches; the tests are CI's.

CI runs `make verify` in legs, each told CHECKS_SHARD and CHECKS_SHARDS by its matrix: each leg runs every check and its
share of the tests, so that across the legs every test runs once and no leg nears the step's limit. Neither set: every
test, as at a desk.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
import unittest

from tools import (check_apps, check_authority, check_context, check_decisions, check_examples, check_lifecycle,
                   check_purity, check_release, check_repo, check_rulesets, check_trials, check_workflows, check_writes)

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
    ("writes", check_writes.run),
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


def _tests(tests) -> list:
    return [test for item in tests for test in _tests(item)] if isinstance(tests, unittest.TestSuite) else [tests]


def suite(fast: bool, share: tuple = None) -> unittest.TestSuite:
    """Every test module under tests/, at any depth; when fast, all but those in SLOW. Given `share`, (a leg, the count
    of legs), the tests of the whole one by one, each `count`-th from the leg's place, so that the legs hold each once."""
    whole = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    if share is not None:
        index, count = share
        return unittest.TestSuite(_tests(whole)[index::count])
    if not fast:
        return whole
    slow = {"tests." + name for name in SLOW}
    return unittest.TestSuite(item for item in whole if not _modules(item) & slow)


def leg(environ) -> tuple:
    """(this leg, the count of legs) from CHECKS_SHARD and CHECKS_SHARDS, which CI's matrix sets, counted from 0; None
    when neither is set. Raises ValueError for one without the other, a value that is not a whole number, or a leg
    outside the count, which could leave tests in no leg."""
    index, count = environ.get("CHECKS_SHARD"), environ.get("CHECKS_SHARDS")
    if index is None and count is None:
        return None
    if not all(isinstance(said, str) and re.fullmatch(r"[0-9]+", said) for said in (index, count)):
        raise ValueError("CHECKS_SHARD is %r and CHECKS_SHARDS is %r; set both, to whole numbers, or neither"
                         % (index, count))
    if not 0 <= int(index) < int(count):
        raise ValueError("CHECKS_SHARD is %s and CHECKS_SHARDS is %s; the leg is counted from 0, below the count"
                         % (index, count))
    return int(index), int(count)


def notes() -> list:
    """What `verify` says of the records before the tests: what they were compared with, and how many Boundary rows
    name no mutant yet (issue 590)."""
    return ["%-22s %s" % ("decision base", check_decisions.described()),
            "%-22s %s" % ("boundary mutants", check_decisions.unnamed())]


def main(argv: list, environ=None) -> int:
    try:
        share = None if "--checks" in argv or "--fast" in argv else leg(environ or {})
    except ValueError as err:
        print(err)
        return 1
    checks_failed = failed(CHECKS)
    if "--checks" in argv:
        return 1 if checks_failed else 0
    for line in notes():
        print(line)
    unverified(check_trials.unverified())
    if share is not None:
        print("%-22s leg %d of %d counted from 0" % ("tests", share[0], share[1]))
    result = unittest.TextTestRunner(verbosity=1).run(suite("--fast" in argv, share))
    return 1 if checks_failed or not result.wasSuccessful() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ))
