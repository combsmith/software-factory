"""One command: everything the required check will run. `make verify`.

`make fast` runs the same checks and every test but the seeded simulation. `make checks` runs the checks alone, half a
minute, and is what a session's hooks run after an edit and before a stop (`tools/hooks/after_edit.py`,
`tools/hooks/before_stop.py`), and what the desk owes with the mutants of the files a change touches; the tests are CI's.
After the checks it prints one note that fails nothing, `tools/desk.py`'s size (`desk_note`), which CI's legs never run.

CI runs `make verify` in legs, each told CHECKS_SHARD and CHECKS_SHARDS by its matrix: each leg runs every check and its
share of the tests, so that across the legs every test runs once and no leg nears the step's limit. Neither set: every
test, as at a desk.

The Makefile runs this file in Python's isolated mode, without site, so the repo's top is put on the path here, after
the standard library: a file at the top named as one of its modules is never imported in its place. The tests run in a
process of their own (`tested`), and no test module is imported in this one, so a test module that ends its process at
import ends only the tests' process, and the checks' verdict is still the answer (issue 1050).
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))      # after the standard library: a file at the top never stands in for one of its modules

from tools import (check_apps, check_authority, check_context, check_decisions, check_examples, check_gate_sets,
                   check_lifecycle,
                   check_purity, check_release, check_repo, check_rulesets, check_trials, check_workflows, check_writes)

CHECKS = [
    ("schemas and examples", check_examples.run),
    ("lifecycle", check_lifecycle.run),
    ("authority", check_authority.run),
    ("apps", check_apps.run),
    ("rulesets", check_rulesets.run),
    ("kernel purity", check_purity.run),
    ("guards purity", check_purity.guards),
    ("trials", check_trials.run),
    ("release", check_release.run),
    ("repo", check_repo.run),
    ("workflows", check_workflows.run),
    ("writes", check_writes.run),
    ("context", check_context.run),
    ("decision records", check_decisions.run),
    ("gate sets", check_gate_sets.run),
]
# The test modules `make fast` leaves out, each of which runs the seeded simulation. `make verify` runs them all.
SLOW = ("test_simulator", "test_issue_simulator", "test_reasons")


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


def desk_note() -> str:
    """`tools/desk.py`'s note on about the size the Factory will count the branch at, which `make checks` prints after
    the checks have answered (issue 1109). It is imported here alone, late, and whatever it raises, an exit among
    them, is the note's: it never changes what make checks answers. Each git it runs has a timeout."""
    try:
        from tools import desk      # late: a fault in it is the note's, never the checks'
        return desk.size()
    except BaseException as err:    # NOSONAR: an exit too; the note never decides make checks' answer
        return "no note: it raised %s" % type(err).__name__


def quiet(stream) -> None:
    """Once the note failed to write to `stream`, writes out what the checks left held in it; only where that fails too
    (a closed pipe) points the stream's file at the null device, so the flush at exit, which tries again what is still
    held, finds nothing closed and cannot change make checks' answer."""
    try:
        stream.flush()      # a failure that is no closed pipe, an encoding say, leaves the checks' output to go out
        return
    except BaseException:       # NOSONAR: a closed pipe; the note never decides make checks' answer
        pass
    try:
        fd = stream.fileno()
        null = os.open(os.devnull, os.O_WRONLY)
        if null != fd:      # the null device took the stream's own number, closed already: it is left as it is
            os.dup2(null, fd)
            os.close(null)
    except BaseException:       # NOSONAR: a stream with no file too; the note never decides make checks' answer
        pass


def tested(fast: bool, share: tuple = None) -> int:
    """The exit of the tests, run in a process of their own, isolated as this one is, told the leg this one read, or
    none: a test module that ends that process can end only the tests' verdict."""
    env = {k: v for k, v in os.environ.items() if k not in ("CHECKS_SHARD", "CHECKS_SHARDS")}
    if share is not None:
        env.update(CHECKS_SHARD=str(share[0]), CHECKS_SHARDS=str(share[1]))
    return subprocess.run([sys.executable, "-I", "-S", str(ROOT / "tools" / "verify.py"), "--tests"]
                          + (["--fast"] if fast else []), cwd=str(ROOT), env=env, check=False).returncode


def main(argv: list, environ=None) -> int:
    try:
        share = None if "--checks" in argv or "--fast" in argv else leg(environ or {})
    except ValueError as err:
        print(err)
        return 1
    if "--tests" in argv:       # the tests' own process, which `tested` starts: it runs no check
        result = unittest.TextTestRunner(verbosity=1).run(suite("--fast" in argv, share))
        return 0 if result.wasSuccessful() else 1
    checks_failed = failed(CHECKS)
    if "--checks" in argv:
        answer = 1 if checks_failed else 0      # the checks' answer, told before the note runs
        try:
            print("%-22s %s" % ("diff size", desk_note()), flush=True)
        except BaseException:       # NOSONAR: a closed pipe too; the note never decides make checks' answer
            quiet(sys.stdout)
        return answer
    for line in notes():
        print(line)
    unverified(check_trials.unverified())
    if share is not None:
        print("%-22s leg %d of %d counted from 0" % ("tests", share[0], share[1]))
    tests = tested("--fast" in argv, share)
    print("%-22s %s" % ("tests", "their process ended %d" % tests))
    return 1 if checks_failed or tests != 0 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ))
