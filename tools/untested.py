"""A changed line of Python that no test notices: the advisory check of issue 589.

"A changed line of Python that no test notices fails verify, unless the change says it keeps behaviour" (issue 589). The
`untested` job runs this from a checkout of the base, never the head, as `commits` runs the base's tool: a change cannot
set the rules it is read by (decision 0023). It fetches the head, exports it, and reads each hunk of
`git diff -U0 <merge base> <head>` in a `*.py` outside LEFT_OUT, but those of DATA in tools/mutants.py. A hunk whose
module reads the same to Python with the hunk reverted, its docstrings and its annotations aside, changes nothing and
is never run.

Every other hunk is reverted, alone, and the head's tests run on that edit through tools/mutants.py's own `attempt`,
which confirms a kill by two runs of the one test that failed (the Factory Builder's ruling 1 of 2026-11-07: revert
first, on every hunk). An edit that does not parse is UNPARSABLE, one whose module will not import is UNIMPORTABLE,
and one killed only by an exception in CRASH is CRASHED: none is a kill. Each falls back to the revert of its file's
every hunk together, and then, for a hunk of more than LARGE added lines alone, to at most MOST mutants of those lines;
a hunk no edit of which runs is UNCHECKED, and says why. The tests run first are those that import the changed module,
or a module that imports it; for a hunk in tools/, the classes that reach it (ruling 2), never a module whole.

A survivor, or a hunk UNCHECKED, is covered by a trailer of the head commit, `Behaviour-preserving: <path>:<start>-<end>`
in the head's lines, holding each line the hunk added, or for a hunk that only removes, the line after. A trailer that
names no changed line, or a path the change does not touch, or that cannot be read, is a problem of its own.

For its first month it is advisory (ruling 2): it reads a pull request and no merge group, it says what it found in the
job's log and summary and as a warning on each survivor's lines, and it exits 0 whatever it finds, or fails to find. Its
last line, `untested/1` and its counts, is what the weekly list in issue 589 is made from. Run with
`python3 -m tools.untested`, given BASE_SHA, HEAD_SHA and EVENT.
"""
from __future__ import annotations

import ast
import concurrent.futures
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

from tools import mutants, walk
from tools.verify import SLOW

ROOT = pathlib.Path(__file__).resolve().parent.parent
SECONDS = 120          # for each git command
BUDGET = 20 * 60       # seconds from the start before no new run of the tests begins; one begun runs to its end
IMPORT_SECONDS = 60    # for the import of an edited module
LARGE = 40             # the lines a hunk adds, above which an edit of it that cannot run falls back to mutants of them
MOST = 6               # mutants of one hunk's added lines, at most, spread among them
# The exceptions that say an edit broke the code's shape, not its behaviour: a test that raises one of them has noticed
# that a name is gone, not that a rule is. AttributeError is not one, since tests assert on attributes.
CRASH = ("SyntaxError", "IndentationError", "ImportError", "ModuleNotFoundError", "NameError")
# Where a changed line is not read: the tests themselves (the issue's own rule), and the trees that hold no Python.
LEFT_OUT = ("tests/", "trials/", "examples/", "schemas/")
# The lists in tools/mutants.py that are its data, the mutants themselves; the runner below them is read.
DATA = ("tools/mutants.py", ("ISSUE", "MUTANTS"))
TRAILER = "Behaviour-preserving"
# A path this prints: a path a pull request named, so held to plain characters before it reaches a log or a summary.
SAFE = re.compile(r"^[\w./-]+\.py$")
SPAN = re.compile(r"^([\w./-]+\.py):([1-9][0-9]*)-([1-9][0-9]*)$")
HUNK = re.compile(r"^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@")
# The kind of the failure unittest prints under its rule: an assertion that failed, or an exception the test raised.
KIND = re.compile(r"^={70}\n(FAIL|ERROR): ", re.M)
# The outcomes of an edit that no test was shown to notice, and that do not finish its hunk.
UNRUN = ("UNPARSABLE", "UNIMPORTABLE", "CRASHED")
NAME = "untested: %s:%d-%d%s"
SUMMARY = "untested/1"


class OverBudget(Exception):
    """The budget ran out before this run of the tests began."""


class Unimportable(Exception):
    """The edited module will not import."""


def git(root: pathlib.Path, *args: str) -> str:
    """What git prints for `args` in `root`; raises ValueError where it fails or takes too long."""
    try:
        done = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=SECONDS)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise ValueError("git %s could not run: %s" % (args[0], err)) from None
    if done.returncode:
        raise ValueError("git %s failed: %s" % (args[0], done.stderr.strip()[:200]))
    return done.stdout


def export(root: pathlib.Path, head: str, to: pathlib.Path) -> None:
    """Write the tree of `head` to `to`, a directory that exists, as git archive gives it, with no .git."""
    try:
        archive = subprocess.Popen(["git", "archive", "--format=tar", head], cwd=str(root), stdout=subprocess.PIPE)
        untar = subprocess.run(["tar", "-x", "-C", str(to)], stdin=archive.stdout, capture_output=True, timeout=SECONDS)
        archive.stdout.close()
        status = archive.wait(timeout=SECONDS)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise ValueError("the head could not be exported: %s" % err) from None
    if status or untar.returncode:
        raise ValueError("the head could not be exported: git archive %s, tar %s" % (status, untar.returncode))


def module_of(rel: str) -> str:
    """The dotted name `rel`, a path under the tree, is imported by."""
    name = rel[:-3].replace("/", ".")
    return name[:-len(".__init__")] if name.endswith(".__init__") else name


def hunks(diff: str, rel: str) -> list:
    """Each hunk of `diff`, `git diff -U0` of the one file `rel`, as a dict: its path, the start and count of its lines
    on each side, the base's first, and whether it only removes."""
    found = []
    for line in diff.splitlines():
        head = HUNK.match(line)
        if head:
            old, old_n, new, new_n = (int(head.group(i)) if head.group(i) is not None else 1 for i in range(1, 5))
            found.append({"path": rel, "old": old, "old_n": old_n, "new": new, "new_n": new_n, "removes": new_n == 0})
    return found


def revert(head_lines: list, base_lines: list, hunk: dict) -> list:
    """The head's lines with `hunk` put back as the base had it. A hunk that adds no line stands after its line."""
    old = base_lines[hunk["old"] - 1:hunk["old"] - 1 + hunk["old_n"]] if hunk["old_n"] else []
    at = hunk["new"] - 1 if hunk["new_n"] else hunk["new"]
    return head_lines[:at] + old + head_lines[at + hunk["new_n"]:]


def shape(text: str) -> str:
    """What Python sees of `text`: its tree, without docstrings, and without annotations where the module puts off
    their evaluation, as every module here does. Raises SyntaxError where it does not parse."""
    tree = ast.parse(text)
    later = any(isinstance(node, ast.ImportFrom) and node.module == "__future__"
                and any(alias.name == "annotations" for alias in node.names) for node in tree.body)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
        if later and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.returns = None
        if later and isinstance(node, ast.arg):
            node.annotation = None
        if later and isinstance(node, ast.AnnAssign):
            node.annotation = ast.Constant(value=None)
    return ast.dump(tree)


def data_lines(text: str) -> set:
    """The lines of tools/mutants.py's `text` that are its data: each line of an entry of a list or a tuple within an
    assignment to a name DATA names, where the entry is a literal, as `_literal` reads one, and each blank or comment
    line of the assignment; but no line on which any other part of it starts or ends, so that code there, a
    comprehension's clause or a condition, beside an entry or not, is never data."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    lines, found, code = text.splitlines(), set(), set()
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in DATA[1]
                                                     for target in node.targets)):
            continue
        found.update(at for at in range(node.lineno, node.end_lineno + 1)
                     if not lines[at - 1].strip() or lines[at - 1].strip().startswith("#"))
        todo = [node.value]
        while todo:
            inner = todo.pop()
            if hasattr(inner, "lineno"):
                code.update((inner.lineno, inner.end_lineno))
            for child in ast.iter_child_nodes(inner):
                if isinstance(inner, (ast.List, ast.Tuple)) and child in inner.elts and _literal(child):
                    found.update(range(child.lineno, child.end_lineno + 1))
                else:
                    todo.append(child)
    return found - code


def _literal(node) -> bool:
    """Whether `node` is made of constants, names, attributes and items alone, in tuples, lists, sums, products, and
    calls of such a name or attribute given no keyword, each maybe unpacked: a mutant's entry, as its helpers build one,
    and nothing that decides."""
    if isinstance(node, (ast.Constant, ast.Name)):
        return True
    if isinstance(node, (ast.Attribute, ast.Starred)):
        return _literal(node.value)
    if isinstance(node, ast.Subscript):
        return _literal(node.value) and _literal(node.slice)
    if isinstance(node, (ast.Tuple, ast.List)):
        return all(_literal(item) for item in node.elts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mult)):
        return _literal(node.left) and _literal(node.right)
    if isinstance(node, ast.Call):
        return _literal(node.func) and not node.keywords and all(_literal(arg) for arg in node.args)
    return False


def is_data(hunk: dict, head_lines: set, base_lines: set) -> bool:
    """Whether every line `hunk` adds is data at the head, and every line it removes was data at the base."""
    new = set(range(hunk["new"], hunk["new"] + hunk["new_n"]))
    old = set(range(hunk["old"], hunk["old"] + hunk["old_n"]))
    return bool(new | old) and new <= head_lines and old <= base_lines


def imports(tree: ast.AST, own: str) -> dict:
    """{the name or dotted chain it binds: the module it names} of each import in `tree`, a module whose dotted name is
    `own`. A name brought from a module may be a module itself, so both are given."""
    bound = {}
    package = own.rsplit(".", 1)[0] if "." in own else ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".") if package else []
                parts = parts[:len(parts) - node.level + 1] if node.level > 1 else parts
                base = ".".join(parts + ([node.module] if node.module else []))
            for alias in node.names:
                bound[alias.asname or alias.name] = base + "." + alias.name
                bound.setdefault("from " + base, base)
    return bound


def reached(root: pathlib.Path, rel: str) -> set:
    """The dotted names of `rel`'s module and of every module outside tests/ that imports it, at any remove."""
    importers = {}
    for path in walk.files(root):
        name = path.relative_to(root).as_posix()
        if path.suffix != ".py" or name.startswith(LEFT_OUT):
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, ValueError, OSError):
            continue
        for named in imports(tree, module_of(name)).values():
            for prefix in _prefixes(named):
                importers.setdefault(prefix, set()).add(module_of(name))
    found, todo = set(), [module_of(rel)]
    while todo:
        name = todo.pop()
        if name not in found:
            found.add(name)
            todo.extend(importers.get(name, ()))
    return found


def _prefixes(dotted: str) -> list:
    parts = dotted.split(".")
    return [".".join(parts[:end]) for end in range(len(parts), 0, -1)]


def _chain(node) -> str:
    """The dotted text of a name or an attribute of one, as `tools.untested.main`; "" for anything else."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return ".".join([node.id] + parts[::-1]) if isinstance(node, ast.Name) else ""


def _reaches(node: ast.AST, names: set, modules: set) -> bool:
    """Whether `node` uses a name in `names`, a dotted chain into `modules`, or a string naming one of `modules`."""
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and inner.id in names:
            return True
        chain = _chain(inner) if isinstance(inner, ast.Attribute) else ""
        if chain and any(chain == m or chain.startswith(m + ".") for m in modules):
            return True
        if isinstance(inner, ast.Constant) and isinstance(inner.value, str) and inner.value in modules:
            return True
        if isinstance(inner, (ast.Import, ast.ImportFrom)) and any(
                any(p in modules for p in _prefixes(m)) for m in imports(inner, "").values()):
            return True
    return False


def first_tests(root: pathlib.Path, rel: str) -> tuple:
    """The tests to run first on an edit of `rel`: each test module that imports its module or one that imports it, or,
    for a file in tools/ or a module holding a class WHOLE_TOO_LONG names, each class of it that reaches one, and each
    method of such a class that does. The slow modules are left to the whole suite, as a mutant leaves them."""
    modules = reached(root, rel)
    chosen = []
    for path in walk.files(root, "tests"):
        name = path.relative_to(root).as_posix()
        if not (path.name.startswith("test") and path.suffix == ".py"):
            continue
        dotted = module_of(name)
        if dotted.rsplit(".", 1)[-1] in SLOW:
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, ValueError, OSError):
            continue
        names = {bound for bound, named in imports(tree, dotted).items()
                 if not bound.startswith("from ") and any(p in modules for p in _prefixes(named))}
        if not names and not _reaches(tree, set(), modules):
            continue
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        slow = {dotted + "." + node.name for node in classes} & set(mutants.WHOLE_TOO_LONG)
        if not rel.startswith("tools/") and not slow:
            chosen.append(dotted)
            continue
        # A helper at the top that reaches the module carries it to whatever calls the helper.
        helpers = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                   and not _is_case(node) and _reaches(node, names, modules)}
        grown = True
        while grown:
            more = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                    and not _is_case(node) and node.name not in helpers and _reaches(node, names | helpers, modules)}
            grown, helpers = bool(more), helpers | more
        for node in classes:
            if not _is_case(node) or not _reaches(node, names | helpers, modules):
                continue
            whole = dotted + "." + node.name
            if whole not in slow:
                chosen.append(whole)
                continue
            chosen.extend(whole + "." + method.name for method in node.body
                          if isinstance(method, ast.FunctionDef) and method.name.startswith("test")
                          and _reaches(method, names | helpers, modules))
    return tuple(chosen)


def _is_case(node) -> bool:
    """Whether `node` is a class with a test method: a TestCase, as far as its text says."""
    return isinstance(node, ast.ClassDef) and any(isinstance(item, ast.FunctionDef) and item.name.startswith("test")
                                                  for item in node.body)


def crashed(output: str) -> str:
    """The exception in CRASH the one failure in `output` is, where it is an ERROR of one; else ""."""
    kind = KIND.search(output)
    if kind is None or kind.group(1) != "ERROR":
        return ""
    said = mutants.failures([output])
    error = said[0].split(": ", 1)[1] if said and ": " in said[0] else ""
    name = error.split(":", 1)[0].strip().rsplit(".", 1)[-1]
    return name if name in CRASH else ""


def bounded(deadline: float):
    """A run of the tests as tools/mutants.py's `suite` makes it, which begins no run of the suite past `deadline`, a
    time.monotonic(), but the run of one test alone that confirms a kill; and no run of any kind lasts past one
    TIMEOUT after it, each cut to what is left, so that the job ends inside its step's limit with its counts written."""
    end = deadline + mutants.TIMEOUT

    def left(limit: float) -> float:
        rest = end - time.monotonic()
        if rest <= 0:
            raise OverBudget()
        return min(limit, rest)

    def run(cwd: pathlib.Path, timeout: float = mutants.TIMEOUT, first: tuple = (), only=None) -> tuple:
        def one(args: list) -> tuple:
            if time.monotonic() > deadline:
                raise OverBudget()
            return mutants._unittest(cwd, left(timeout), args)
        if only:
            return mutants._unittest(cwd, left(timeout), ["-q", "-f", *((only,) if isinstance(only, str) else only)])
        if first:
            status, output = one(["-q", "-f", *first])
            if status != 0:
                return status, output
        status, output = 0, ""
        for part in mutants.whole_suite(cwd):
            status, output = one(["-q", "-f", *part])
            if status != 0:
                break
        return status, output
    return run


def importable(work: pathlib.Path, module: str) -> bool:
    """Whether `module` imports in `work`, in a Python of its own that writes no bytecode and reads no file where it
    stands but `work`."""
    try:
        done = subprocess.run([sys.executable, "-I", "-B", "-c",
                               "import importlib, sys; sys.path.insert(0, sys.argv[1]); importlib.import_module(sys.argv[2])",
                               str(work), module], cwd=str(work), capture_output=True, timeout=IMPORT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def edit(name: str, rel: str, head_text: str, new_text: str, tests: tuple, root: pathlib.Path, run, trees,
         guard_import: bool, deadline: float = float("inf")) -> tuple:
    """(outcome, why) of one edit of `rel`, `head_text` made `new_text`, through tools/mutants.py's `attempt`."""
    try:
        ast.parse(new_text, rel)
    except (SyntaxError, ValueError) as err:
        return "UNPARSABLE", "the edit does not parse: %s" % type(err).__name__
    seen, checked = [], []

    def recording(work: pathlib.Path, **given) -> tuple:
        if guard_import and not checked:
            if time.monotonic() > deadline:     # an import that hangs takes IMPORT_SECONDS: none begins past the budget
                raise OverBudget()
            checked.append(True)
            if not importable(work, module_of(rel)):
                raise Unimportable()
        said = run(work, **given)
        seen.append((given, said))
        return said
    mutant = (name, rel, head_text, new_text, tests) if tests else (name, rel, head_text, new_text)
    try:
        outcome, why = mutants.attempt(mutant, root, recording, trees)
    except OverBudget:
        return "UNCHECKED", "over budget"
    except Unimportable:
        return "UNIMPORTABLE", "the edited module does not import"
    except Exception as err:    # a failed copy, read or run; never a kill
        return "ERROR", "the run failed with %s" % type(err).__name__
    if outcome == "killed":
        again = [said for given, said in seen if given.get("only") and said[0] == 1]
        crash = crashed(again[-1][1]) if again else ""
        if crash:
            return "CRASHED", "the one test that noticed it raised %s" % crash
    # A test module that no longer imports is an edit that took a name away, which the mutant run calls an ERROR.
    if outcome == "ERROR" and seen and mutants.UNIMPORTABLE in seen[-1][1][1]:
        return "CRASHED", "a test module would not import"
    return outcome, why


def candidates(text: str, hunk: dict) -> list:
    """Mutants of the lines `hunk` adds to `text`, the head's, each the whole text with one line changed: a condition
    negated, a comparison off by one, a statement dropped, a constant changed. A line that is only a string, a call
    that prints or logs, or a raise, is not mutated: its mutants are the commonest equivalent ones; nor is one Python
    would read as the head, as an annotation never evaluated. At most MOST, spread among the lines."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines, head = text.splitlines(keepends=True), shape(text)
    first, last = hunk["new"], hunk["new"] + hunk["new_n"] - 1
    starts = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt) and first <= node.lineno <= last:
            starts.setdefault(node.lineno, node)
    found = []
    for at in sorted(starts):
        node, line = starts[at], lines[at - 1]
        if _quiet(node):
            continue
        made = _mutated(node, line)
        if made is not None and made != line:
            changed = lines[:at - 1] + [made] + lines[at:]
            try:
                same = shape("".join(changed)) == head
            except (SyntaxError, ValueError):
                continue
            if not same:    # a mutant Python reads as the head, of an annotation never evaluated, is no edit
                found.append((at, changed))
    if len(found) > MOST:
        found = [found[round(i * (len(found) - 1) / (MOST - 1))] for i in range(MOST)]
    return [(at, "".join(changed)) for at, changed in found]


def _quiet(node) -> bool:
    """Whether a mutant of the statement `node` would most often be an equivalent one."""
    if isinstance(node, (ast.Raise, ast.Pass, ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
        return True
    if isinstance(node, ast.Expr):
        value = node.value
        if isinstance(value, ast.Constant):
            return True
        called = _chain(value.func) if isinstance(value, ast.Call) else ""
        return bool(called) and (called == "print" or "log" in called.lower() or "warn" in called.lower())
    return False


COMPARE = re.compile(r" (<=|>=|<|>) ")
SWAP = {"<": "<=", "<=": "<", ">": ">=", ">=": ">"}


def _mutated(node, line: str):
    """One mutant of `line`, where the statement `node` starts, or None where none of the four fits."""
    one_line = getattr(node, "end_lineno", None) == node.lineno
    test = getattr(node, "test", None)
    if isinstance(node, (ast.If, ast.While)) and test is not None and test.lineno == test.end_lineno == node.lineno:
        raw = line.encode()     # the offsets are of UTF-8 bytes
        return (raw[:test.col_offset] + b"not (" + raw[test.col_offset:test.end_col_offset] + b")"
                + raw[test.end_col_offset:]).decode()
    compare = COMPARE.search(line)
    if compare and any(isinstance(inner, ast.Compare) for inner in ast.walk(node)):
        return line[:compare.start()] + " %s " % SWAP[compare.group(1)] + line[compare.end():]
    for inner in ast.walk(node):
        if isinstance(inner, ast.Constant) and inner.lineno == node.lineno and inner.end_lineno == node.lineno:
            if isinstance(inner.value, bool) or (isinstance(inner.value, int) and not isinstance(inner.value, bool)):
                raw = line.encode()
                now = raw[inner.col_offset:inner.end_col_offset].decode()
                new = str(not inner.value) if isinstance(inner.value, bool) else str(inner.value + 1)
                if now == repr(inner.value):
                    return (raw[:inner.col_offset].decode() + new + raw[inner.end_col_offset:].decode())
    if one_line and isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Expr, ast.Return, ast.Assert,
                                      ast.Delete, ast.Continue, ast.Break)):
        return line[:len(line) - len(line.lstrip())] + "pass\n"
    return None


def trailers(root: pathlib.Path, head: str) -> list:
    """Each `Behaviour-preserving` trailer of the commit `head`, as git's own parser reads the message's last block."""
    said = git(root, "log", "-1", "--format=%(trailers:key=" + TRAILER + ",valueonly,unfold)", head)
    return [line.strip() for line in said.splitlines() if line.strip()]


def changed_lines(hunk: dict) -> set:
    """The head's lines `hunk` adds; for a hunk that only removes, the line after where it removed."""
    return set(range(hunk["new"], hunk["new"] + hunk["new_n"])) if hunk["new_n"] else {hunk["new"] + 1}


def read_trailers(said: list, every: list) -> tuple:
    """([(path, start, end)] of the trailers in `said` that can stand, [what is wrong with each that cannot]), against
    `every` hunk of the change."""
    spans, problems = [], []
    paths = {hunk["path"] for hunk in every}
    for value in said:
        found = SPAN.match(value)
        if found is None or int(found.group(2)) > int(found.group(3)):
            problems.append("a %s trailer is not <path>:<start>-<end>, its lines the head's" % TRAILER)
            continue
        path, start, end = found.group(1), int(found.group(2)), int(found.group(3))
        if path not in paths:
            problems.append("the %s trailer %s names a file this change leaves as it was" % (TRAILER, value))
            continue
        touched = set().union(*(changed_lines(hunk) for hunk in every if hunk["path"] == path))
        if not touched & set(range(start, end + 1)):
            problems.append("the %s trailer %s names lines no hunk changed" % (TRAILER, value))
            continue
        spans.append((path, start, end))
    return spans, problems


def covered(hunk: dict, spans: list) -> bool:
    """Whether one of `spans` holds every line `hunk` changed."""
    lines = changed_lines(hunk)
    return any(path == hunk["path"] and start <= min(lines) and max(lines) <= end for path, start, end in spans)


def check(root: pathlib.Path, base: str, head: str, deadline: float, run=None, workers: int = None) -> dict:
    """What the change from the merge base of `base` and `head` to `head` holds that no test notices, read in `root`, a
    clone that holds both: {"hunks": each hunk, with its outcome, "problems": the trailers' problems, "counts": ...}."""
    run = run or bounded(deadline)
    workers = workers or min(os.cpu_count() or 1, mutants.WORKERS)
    since = git(root, "merge-base", base, head).strip()
    every, read, skipped = [], [], {"unsafe_path": 0, "deleted": 0, "same": 0, "data": 0, "unparsed_head": 0}
    with tempfile.TemporaryDirectory() as made:
        tree = pathlib.Path(made) / "head"
        tree.mkdir()
        export(root, head, tree)
        texts = {}
        for rel in git(root, "diff", "--name-only", "-z", "--no-renames", since, head, "--", "*.py").split("\0"):
            if not rel or rel.startswith(LEFT_OUT):
                continue
            if not SAFE.match(rel):
                skipped["unsafe_path"] += 1
                continue
            target = tree / rel
            if not target.is_file():
                skipped["deleted"] += 1
                continue
            head_text = target.read_text()
            try:
                base_text = git(root, "show", "%s:%s" % (since, rel))
            except ValueError:
                base_text = ""     # a file the change adds
            diff = git(root, "diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames", since, head, "--", rel)
            data = (data_lines(head_text), data_lines(base_text)) if rel == DATA[0] else (set(), set())
            texts[rel] = (head_text, base_text)
            try:
                head_shape = shape(head_text)
            except (SyntaxError, ValueError):
                head_shape = None
            for hunk in hunks(diff, rel):
                read.append(hunk)
                if is_data(hunk, *data):
                    skipped["data"] += 1
                    continue
                hunk["text"] = "".join(revert(head_text.splitlines(keepends=True), base_text.splitlines(keepends=True), hunk))
                if head_shape is None:
                    skipped["unparsed_head"] += 1
                    hunk.update(outcome="UNCHECKED", why="the head's file does not parse")
                    every.append(hunk)
                    continue
                try:
                    if shape(hunk["text"]) == head_shape:
                        skipped["same"] += 1
                        continue
                except (SyntaxError, ValueError):
                    pass
                every.append(hunk)
        tests = {rel: first_tests(tree, rel) for rel in texts}
        guard = {rel: time.monotonic() <= deadline and importable(tree, module_of(rel)) for rel in texts}
        trees = mutants.Trees(tree, made)

        def run_edit(item: tuple) -> tuple:
            name, rel, new_text = item
            return edit(name, rel, texts[rel][0], new_text, tests[rel], tree, run, trees, guard[rel], deadline)

        def many(items: list) -> list:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                return list(pool.map(run_edit, items))
        # Smallest file first, so that what the budget leaves unread is the fewest hunks.
        todo = sorted((hunk for hunk in every if "outcome" not in hunk), key=lambda h: (len(texts[h["path"]][0]), h["path"], h["new"]))
        for hunk, (outcome, why) in zip(todo, many([(NAME % (h["path"], h["new"], h["new"] + max(h["new_n"], 1) - 1, ""),
                                                      h["path"], h["text"]) for h in todo])):
            hunk.update(outcome=outcome, why=why, by="revert")
        # The first fallback: every hunk of the file reverted together, once for each file, which mends a hunk that
        # defines what its neighbour uses.
        whole = sorted({h["path"] for h in todo if h["outcome"] in UNRUN and texts[h["path"]][1] != h["text"]})
        files = dict(zip(whole, many([(NAME % (rel, 1, 1, " (its file)"), rel, texts[rel][1]) for rel in whole])))
        for hunk in todo:
            if hunk["outcome"] in UNRUN and hunk["path"] in files:
                hunk.setdefault("tried", []).append("file")
            if hunk["outcome"] in UNRUN and files.get(hunk["path"], ("UNPARSABLE",))[0] not in UNRUN:
                hunk.update(outcome=files[hunk["path"]][0], why=files[hunk["path"]][1], by="file")
        # The second: mutants of the lines a large hunk adds. Then whatever no edit ran is UNCHECKED, and says why.
        large = [h for h in todo if h["outcome"] in UNRUN and h["new_n"] > LARGE]
        made_of = [(h, at, text) for h in large for at, text in candidates(texts[h["path"]][0], h)]
        results = many([(NAME % (h["path"], at, at, " (a mutant)"), h["path"], text) for h, at, text in made_of])
        for hunk in large:
            said = [r for (h, _, _), r in zip(made_of, results) if h is hunk]
            ran = [outcome for outcome, _ in said if outcome in ("killed", "SURVIVED", "FLAKY")]
            outcome = "SURVIVED" if "SURVIVED" in ran else "FLAKY" if "FLAKY" in ran else "killed" if ran else hunk["outcome"]
            hunk.setdefault("tried", []).append("mutants")
            hunk.update(by="mutants", mutants=len(said), outcome=outcome,
                        why="%d of %d mutants of its added lines ran" % (len(ran), len(said)) if ran else hunk["why"])
            if not ran and said and all(said_one == ("UNCHECKED", "over budget") for said_one in said):
                hunk.update(outcome="UNCHECKED", why="over budget")
        for hunk in todo:
            if hunk["outcome"] in UNRUN:
                hunk.update(outcome="UNCHECKED", why="%s: %s" % (hunk["outcome"], hunk["why"]))
    # A trailer is held to every hunk of the change, those never run among them, so that one on a docstring is no problem.
    spans, problems = read_trailers(trailers(root, head), read)
    for hunk in every:
        hunk["covered"] = hunk["outcome"] in ("SURVIVED", "UNCHECKED") and covered(hunk, spans)
        hunk.pop("text", None)
    return {"hunks": every, "problems": problems, "skipped": skipped, "trailers": len(spans) + len(problems)}


def counts(found: dict, seconds: float) -> dict:
    """The numbers the weekly list in issue 589 is made from."""
    every = found["hunks"]
    by = lambda outcome: [h for h in every if h["outcome"] == outcome]
    # A kill of the file's revert may be a neighbour's: it is never counted as the hunk's own.
    return {"hunks": len(every), "killed": len([h for h in by("killed") if h.get("by") != "file"]),
            "killed_by_file": len([h for h in by("killed") if h.get("by") == "file"]), "survived": len(by("SURVIVED")),
            "survived_removing": len([h for h in by("SURVIVED") if h["removes"]]),
            "unchecked": len(by("UNCHECKED")), "over_budget": len([h for h in by("UNCHECKED") if h["why"] == "over budget"]),
            "flaky": len(by("FLAKY")), "error": len(by("ERROR")),
            # Each fallback tried, whatever edit gave the outcome: the month counts how often they run.
            "fallback_file": len([h for h in every if "file" in h.get("tried", ())]),
            "fallback_mutants": len([h for h in every if "mutants" in h.get("tried", ())]),
            "covered": len([h for h in every if h["covered"]]), "trailers": found["trailers"],
            "trailer_problems": len(found["problems"]), "seconds": round(seconds), **found["skipped"]}


def _flat(text: str) -> str:
    """`text` on one line, so that nothing of it can stand at the start of a line of the log."""
    return " ".join(str(text).split())


def report(found: dict, seconds: float) -> tuple:
    """(the lines for the job's log, the job's summary in Markdown)."""
    log, rows = [], []
    for hunk in found["hunks"]:
        span = "%s:%d-%d" % (hunk["path"], hunk["new"], hunk["new"] + max(hunk["new_n"], 1) - 1)
        notes = [note for note, on in (("by its file's revert", hunk.get("by") == "file"),
                                       ("by mutants of its lines", hunk.get("by") == "mutants"),
                                       ("only removes", hunk["removes"]), ("covered by its trailer", hunk["covered"])) if on]
        log.append("%-10s %s%s%s" % (hunk["outcome"], span, " (%s)" % _flat(hunk["why"]) if hunk["why"] else "",
                                       "; " + ", ".join(notes) if notes else ""))
        if hunk["outcome"] != "killed" or hunk.get("by") == "file":
            rows.append("| %s | `%s` | %s |" % (hunk["outcome"], span, ", ".join(notes)))
        if hunk["outcome"] == "SURVIVED" and not hunk["covered"]:
            first = hunk["new"] if hunk["new_n"] else hunk["new"] + 1
            log.append("::warning file=%s,line=%d,endLine=%d::no test notices this hunk reverted; if it keeps behaviour, "
                       "say so in the head commit: %s: %s" % (hunk["path"], first, first + max(hunk["new_n"], 1) - 1,
                                                               TRAILER, span if hunk["new_n"] else "%s:%d-%d" % (hunk["path"], first, first)))
    log += ["PROBLEM    %s" % _flat(problem) for problem in found["problems"]]
    total = counts(found, seconds)
    log.append("%s %s" % (SUMMARY, json.dumps(total, sort_keys=True)))
    summary = ["## untested (advisory)", "",
               "%(hunks)d hunks read: %(killed)d noticed by a test, %(killed_by_file)d only with their file's every hunk, "
               "%(survived)d survived, %(unchecked)d unchecked, "
               "%(flaky)d flaky, %(error)d in error, in %(seconds)d s." % total, ""]
    if rows:
        summary += ["| Outcome | Lines | Notes |", "|---|---|---|"] + rows + [""]
    summary += ["- %s" % _flat(problem) for problem in found["problems"]]
    return log, "\n".join(summary) + "\n"


def main(environ=os.environ, root: pathlib.Path = ROOT) -> int:
    started = time.monotonic()
    event, base, head = (environ.get(name) for name in ("EVENT", "BASE_SHA", "HEAD_SHA"))
    if event != "pull_request":
        print("untested is advisory in its first month and reads a pull request alone; on %s it does not run"
              % _flat(event or "no event"))
        return 0
    # The head's tests run under this process: they are given no file the runner reads back.
    summary_path = environ.get("GITHUB_STEP_SUMMARY")
    for name in ("GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_PATH", "GITHUB_STATE"):
        os.environ.pop(name, None)
    try:
        if not base or not head:
            raise ValueError("BASE_SHA and HEAD_SHA must be set from the event")
        git(root, "fetch", "--no-tags", "origin", head)
        found = check(root, base, head, started + BUDGET)
    except Exception as err:    # advisory: whatever fails is said, and the job stays green
        print("untested could not run: %s: %s" % (type(err).__name__, _flat(err)[:300]))
        print("%s %s" % (SUMMARY, json.dumps({"error": type(err).__name__}, sort_keys=True)))
        return 0
    log, summary = report(found, time.monotonic() - started)
    for line in log:
        print(line)
    if summary_path:
        try:
            with open(summary_path, "a") as out:
                out.write(summary)
        except OSError:
            print("the job's summary could not be written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
