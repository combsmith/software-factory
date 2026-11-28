"""One command: everything the required check will run. `make verify`.

`make fast` runs the same checks and every test but the seeded simulation. `make checks` runs the checks alone, half a
minute, and is what a session's hooks run after an edit and before a stop (`tools/hooks/after_edit.py`,
`tools/hooks/before_stop.py`), and what the desk owes with the mutants of the files a change touches; the tests are CI's.
After the checks it prints one note that fails nothing, `tools/desk.py`'s size (`desk_note`), at a desk alone.
`make tests` runs the tests alone, and prints first what verify says of the records and of the fake GitHub.

CI runs `make checks` in a step of its own, then `make tests` in another, in legs, each told CHECKS_SHARD and
CHECKS_SHARDS by its matrix, so that across the legs every test runs once and no leg nears the step's limit. A failed
check ends the job before any test runs. Neither set: every test, as at a desk.

The Makefile runs this file in Python's isolated mode, without site, so the repo's top is put on the path here, after
the standard library: a file at the top named as one of its modules is never imported in its place. `make verify` runs
the checks here and the tests in a process of their own (`tested`), and no test module is imported in this one, so a
test module that ends its process at import ends only the tests' process, and the checks' verdict is still the answer
(issue 1050).
"""
from __future__ import annotations

import ast
import importlib
import importlib.machinery
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))      # after the standard library: a file at the top never stands in for one of its modules

# Each check, by its name, its module of tools/ and its function. Each runs in a process of its own (`answers`), and
# this one imports none of them: a check whose code ends its process, or forges its answer, can blind only itself
# (issue 1377).
CHECKS = [
    ("schemas and examples", "check_examples", "run"),
    ("lifecycle", "check_lifecycle", "run"),
    ("authority", "check_authority", "run"),
    ("apps", "check_apps", "run"),
    ("rulesets", "check_rulesets", "run"),
    ("kernel purity", "check_purity", "run"),
    ("guards purity", "check_purity", "guards"),
    ("trials", "check_trials", "run"),
    ("release", "check_release", "run"),
    ("repo", "check_repo", "run"),
    ("workflows", "check_workflows", "run"),
    ("writes", "check_writes", "run"),
    ("context", "check_context", "run"),
    ("decision records", "check_decisions", "run"),
    ("gate sets", "check_gate_sets", "run"),
]
# What imports a module by a name worked out as it runs: a check that holds one is never read as closed.
DYNAMIC = frozenset(("__import__", "import_module", "importlib", "imp", "pkgutil", "runpy", "zipimport"))
# What runs text as code: called by its own name, or imported under another, it is never read as closed.
RUNS_TEXT = frozenset(("exec", "eval", "compile"))
# Where a check's process finds the standard library, ahead of the tree it appends: a module found here is never a
# file of the tree, whatever file of that name the tree holds (Claude's security read).
STANDARD = [os.path.dirname(os.__file__), os.path.join(os.path.dirname(os.__file__), "lib-dynload")]
DRAIN_SECONDS = 5       # for a stopped check's pipes to close, which a process it started may hold open
EARLY = 2               # what `failed` says when a check that runs no Role code failed: nothing else was started
CHECK_SECONDS = 180     # for every check of a phase to answer, within the step's four minutes
# How a check's process gives its answer: its last line of output, this, then {"check": its name, "problems": [...]}.
ANSWER = "verify: the check answers "
# The test modules `make fast` leaves out, each of which runs the seeded simulation. `make verify` runs them all.
SLOW = ("test_simulator", "test_issue_simulator", "test_reasons")


def check(entry: tuple):
    """The function an entry of CHECKS names, imported: in the check's own process, or in a test."""
    _, module, function = entry
    return getattr(importlib.import_module("tools." + module), function)


def answered(name: str) -> int:
    """Run the check `name` in this process, and print its answer as the last line: `verify --check NAME`."""
    entry = next(e for e in CHECKS if e[0] == name)
    problems = check(entry)()
    sys.stdout.flush()      # a line the check left open is closed first, so the answer stands on a line of its own
    print("\n" + ANSWER + json.dumps({"check": name, "problems": problems}), flush=True)
    return 0


def answers(checks: list) -> dict:
    """{name: (exit, output, errors)} of each check, run together, each in a process of its own, isolated as this one
    is and told nothing but its name. Its bytecode is written to and read from a folder outside the tree, never a
    __pycache__ a push could hold, and one that has not answered by CHECK_SECONDS is stopped."""
    cache = tempfile.mkdtemp(prefix="verify-bytecode-")
    if pathlib.Path(cache).resolve() == ROOT or ROOT in pathlib.Path(cache).resolve().parents:   # TMPDIR in the tree
        shutil.rmtree(cache, ignore_errors=True)
        return {name: (None, "", "its bytecode folder would be %s, inside the tree" % cache) for name, _, _ in checks}
    started = {}
    try:
        for name, _, _ in checks:
            started[name] = subprocess.Popen([sys.executable, "-I", "-S", "-X", "pycache_prefix=" + cache,
                                              str(ROOT / "tools" / "verify.py"), "--check", name],
                                             cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE)
        out, until = {}, time.monotonic() + CHECK_SECONDS
        for name, process in started.items():
            try:
                said, errors = process.communicate(timeout=max(1.0, until - time.monotonic()))
                code = process.returncode
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    said, errors = process.communicate(timeout=DRAIN_SECONDS)
                except subprocess.TimeoutExpired:
                    said, errors = b"", b""
                code, errors = "on a timeout", errors + b"\nit gave no answer within %d seconds" % CHECK_SECONDS
            out[name] = (code, said.decode("utf-8", "replace"), errors.decode("utf-8", "replace"))
        return out
    finally:
        for process in started.values():
            if process.returncode is None:      # one started before another could not be: never left running
                process.kill()
        shutil.rmtree(cache, ignore_errors=True)


def phase_one(checks: list, root: pathlib.Path = ROOT) -> list:
    """The entries of `checks` that run no Role code: each whose whole import closure, read through ast and never run,
    is on the protected list of config/hooks.json. They answer, and pass, before any other check starts (issue 1377).
    The list decides, not a check's name: a check whose closure leaves it, or cannot be read, runs later. Raises
    ValueError when the list cannot be read, since then no check can be told to run no Role code."""
    held = _held(root)
    return [entry for entry in checks if _leaves("tools." + entry[1], held, root) is None]


def unclosed(checks: list, root: pathlib.Path = ROOT) -> list:
    """Why a protected check could run a file a push can change: for each entry of `checks` whose own file is on the
    protected list, the file of tools/ its import closure reaches that is not, or the import of tools/ it cannot
    follow. Verify fails on any before the first phase starts, so a protected check never moves to the later phase in
    silence (issue 1377). Raises ValueError when the list cannot be read."""
    held, why = _held(root), []
    for _, module, _ in checks:
        files = _found("tools." + module, root)
        leaves = _leaves("tools." + module, held, root, "tools/") if len(files) == 2 and held(files[-1]) else None
        if leaves and leaves not in why:
            why.append(leaves)
    return why


def _held(root: pathlib.Path):
    """Whether a path of the repo is on the protected list of config/hooks.json, as a function of the path. Raises
    ValueError when the list cannot be read."""
    from tools.hooks import protected      # protected itself; it imports none of the checks
    try:
        listed = protected.entries(protected.load(root / "config" / "hooks.json")["protected"])
    except Exception as err:       # noqa: BLE001 -- a list that cannot be read fails, never sorts every check later
        raise ValueError("the protected list of config/hooks.json cannot be read (%s)" % type(err).__name__)
    return lambda rel: any(whole.match(rel.casefold()) for _, _, _, whole in listed)


def _leaves(start: str, held, root: pathlib.Path, within: str = ""):
    """None when every file of the repo that importing the module `start` runs, at any depth, is held; else why not,
    naming the file. Given `within`, only the files under it are followed, and an import of any other is not read. An
    import made by a name worked out as it runs, relative to its package, or of `*`, cannot be followed: it leaves."""
    found = _found(start, root)
    if len(found) != start.count(".") + 1:
        return "%s cannot be found" % start
    seen, todo = set(), [(rel, "") for rel in found]
    while todo:
        rel, by = todo.pop()
        if rel in seen or not rel.startswith(within):
            continue
        seen.add(rel)
        if not held(rel):
            return "%s imports %s, which is not on the protected list" % (by, rel) if by else \
                "%s is not on the protected list" % rel
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError, SyntaxError):
            return "%s cannot be read" % rel
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.level or "*" in [a.name for a in node.names]) \
                    or isinstance(node, ast.Attribute) and node.attr in DYNAMIC \
                    or isinstance(node, ast.Name) and (node.id in DYNAMIC or node.id in RUNS_TEXT):
                return "%s imports by a name worked out as it runs, relative to its package or of *, or runs text " \
                       "as code, so its imports cannot be followed" % rel
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module] + [node.module + "." + a.name for a in node.names] if isinstance(node, ast.ImportFrom) \
                else []
            for name in names:
                parts = name.split(".")
                if any(part in DYNAMIC for part in parts) or parts[0] == "builtins" and parts[-1] in RUNS_TEXT:
                    return "%s imports %s, so its imports cannot be followed" % (rel, name)
                if not _standard(parts[0]):
                    todo += [(found, rel) for found in _found(name, root)]
    return None


def _found(name: str, root: pathlib.Path) -> list:
    """The files of the repo that importing `name` runs, each package's `__init__.py` before what it holds. A package
    comes before a module of its name, as Python finds them: a file beside it, which is never imported, is not one."""
    parts, files = name.split("."), []
    for at in range(1, len(parts) + 1):
        base = root.joinpath(*parts[:at])
        found = base / "__init__.py" if (base / "__init__.py").is_file() else base.with_suffix(".py")
        files += [found.relative_to(root).as_posix()] if found.is_file() else []
    return files


def _standard(name: str) -> bool:
    """Whether a check's process finds the top-level module `name` in the standard library, ahead of the tree."""
    return name in sys.builtin_module_names or importlib.machinery.PathFinder.find_spec(name, STANDARD) is not None


def problems_of(name: str, answer) -> list:
    """The problems a check's process answered: those its last line gives, when it ended 0 and that line is its answer
    to this check, a list of sentences. Anything else, no answer among it, is its problem."""
    if answer is None:
        return ["the check gave no answer"]
    code, said, errors = answer
    lines = said.splitlines()
    last = lines[-1] if lines else ""
    try:
        given = json.loads(last[len(ANSWER):]) if last.startswith(ANSWER) else None
    except (ValueError, RecursionError):
        given = None
    whole = isinstance(given, dict) and set(given) == {"check", "problems"} and given["check"] == name \
        and isinstance(given["problems"], list) and all(isinstance(p, str) for p in given["problems"])
    if code != 0 or not whole:
        tail = [line for line in (lines + errors.splitlines()) if line.strip()][-5:]
        return ["the check's process ended %s without its answer" % code] + tail
    return given["problems"]


def failed(checks: list, ran=answers, first=phase_one) -> int:
    """Run each check, print what it found, and say whether any found a problem: 0 if none did, else 1, or EARLY if
    one that runs no Role code did, which run first, or none of them can be told. A check that gives no answer has
    found one. After EARLY nothing that runs Role code has started, and `main` starts nothing more."""
    early = led(checks, ran, first)
    if early is None:
        print("%-22s %s" % ("role code", "not run, since a check that runs none failed"))
        return EARLY
    return 1 if told([entry for entry in checks if entry not in early], ran) else 0


def led(checks: list, ran=answers, first=phase_one):
    """Run the entries of `checks` that run no Role code, alone, and print what each found: those entries if all
    passed, else None. That none of them can be told, or that none runs no Role code, fails too; and before any runs,
    that a protected check's import closure over tools/ leaves the protected list (`unclosed`), its first answer."""
    try:
        leaving = unclosed(checks)
    except ValueError as err:
        leaving = [str(err)]
    print("%-22s %s" % ("closure", "FAILED" if leaving else "ok"), flush=True)
    for why in leaving:
        print("    " + why)
    if leaving:
        return None
    try:
        early = first(checks)
    except ValueError as err:
        print("%-22s %s\n    %s" % ("phases", "FAILED", err))
        return None
    if not early:
        print("%-22s %s\n    %s" % ("phases", "FAILED", "no check runs first: none has its whole import closure on "
                                                         "the protected list"))
        return None
    return None if told(early, ran) else early


def told(checks: list, ran=answers) -> bool:
    """Run `checks` at once, print what each found, and say whether any found a problem."""
    said, any_failed = ran(checks) if checks else {}, False
    for name, _, _ in checks:
        problems = problems_of(name, said.get(name))
        print("%-22s %s" % (name, "ok" if not problems else "FAILED"), flush=True)
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
    from tools import check_decisions       # the tests' process alone imports a check here
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
    if argv[:1] == ["--check"] and len(argv) == 2:      # one check's own process, which `answers` starts
        return answered(argv[1])
    try:
        share = None if {"--checks", "--checks-first", "--fast"} & set(argv) else leg(environ or {})
    except ValueError as err:
        print(err)
        return 1
    if "--tests" in argv:       # `make tests`, or the tests' process that `tested` starts: it runs no check
        for line in notes():
            print(line)
        from tools import check_trials
        unverified(check_trials.unverified())
        if share is not None:
            print("%-22s leg %d of %d counted from 0" % ("tests", share[0], share[1]))
        result = unittest.TextTestRunner(verbosity=1).run(suite("--fast" in argv, share))
        return 0 if result.wasSuccessful() else 1
    if "--checks-first" in argv:    # CI's step before `make checks`: the checks that run no Role code, alone
        return 1 if led(CHECKS, answers, phase_one) is None else 0
    checks_failed = failed(CHECKS, answers, phase_one)
    if checks_failed == EARLY:      # nothing that runs Role code starts: no other check, no note, no test
        return 1
    if "--checks" in argv:
        answer = 1 if checks_failed else 0      # the checks' answer, told before the note runs
        if any(name in (environ or {}) for name in ("CHECKS_SHARD", "CHECKS_SHARDS", "CI")):
            return answer       # CI: the note's code, which a push can change, is never imported there
        try:
            print("%-22s %s" % ("diff size", desk_note()), flush=True)
        except BaseException:       # NOSONAR: a closed pipe too; the note never decides make checks' answer
            quiet(sys.stdout)
        return answer
    sys.stdout.flush()      # what the checks printed goes out before what the tests' process prints
    tests = tested("--fast" in argv, share)
    print("%-22s %s" % ("tests", "their process ended %d" % tests))
    return 1 if checks_failed or tests != 0 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ))
