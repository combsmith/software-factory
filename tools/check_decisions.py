"""A decision record states what is decided now; to change one, add a record that replaces it.

Each record in `docs/decisions/` that the base holds is compared with this working tree, all of it
but two parts. Its Status may change once, in the change that replaces it, and only to "replaced
by" and the path, in backticks, of the record that replaces it: a record new in that change, whose
own Status says it replaces this one. After that the Status is fixed too. Its Boundaries may gain
rows, and a row's Check cell may change, since a row is added when the check for it is written and
that changes nothing decided; no row is taken away and no Boundary cell is changed. Everything
else, the title, the Decision and the Why among it, stays line for line as it was. A new record is
always allowed, but one whose Status says it replaces records replaces each of them, as above. In
every record a title comes first, then one `Status:` line; there is no HTML comment, which hides
text from a reader; and nothing in `docs/decisions/` is a link.

The base is the merge base of HEAD and refs/remotes/origin/main, named in full, read as the Stop
hook reads it (`tools/hooks/rules_changed.py`): git's replacement refs, grafts and commit graph off.
CI checks out the whole history for it. With a `.git` here, a directory or a worktree's file, and no
base to read, a shallow clone, no origin, no git, the check fails: it never passes what it could not
compare. With no `.git` at all the tree is an export, which has no history, and the comparison is
skipped; `verify` says so. In GitHub Actions a missing `.git` fails, so CI cannot skip it.
"""
from __future__ import annotations

import ast
import hashlib
import os
import pathlib
import re
import shutil
import subprocess

from tools import walk
from tools.check_context import LINK, PENDING, TOKEN, WAITING, _cells, _is_pending, _rows, _sections

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "refs/remotes/origin/main"
NO_GRAFTS = "/dev/null/grafts"      # a path that cannot exist: below a file, not a directory
SECONDS = 30                        # for each git command
FOLDER = "docs/decisions"
PATH = r"`(%s/([0-9]{4,})-[^`/\s]+\.md)`" % FOLDER
# How decision 0012 says it was replaced, from the start of its Status: the path, then a comma, a stop or the end.
REPLACED = re.compile(r"^Status: replaced by %s(?=[,.]|$)" % PATH)
# How decision 0015 says what it replaces: one record, or a list of them, straight after its own Status.
REPLACES = re.compile(r"^Status: accepted\. Replaces (`[^`]+`(?:(?:, and |, | and )`[^`]+`)*)(?=[,.]|$)")
# Words that claim a replacement. Past the one declaration a Status makes, none of them, and no record's path, stands.
CLAIM = re.compile(r"replace|supersede", re.I)
# A record's number, at least four digits, compared as a number: one of five digits comes after 9999 (decision 1121).
NUMBER = re.compile(r"^([0-9]{4,})-")
BOUNDARIES = "## Boundaries"
# A mutant a row names, by its description in tools/mutants.py (issue 590).
MUTANT = re.compile(r'mutant: "([^"\n]+)"')


class Unreadable(Exception):
    """The base could not be read, so nothing could be compared."""


def _git(root: pathlib.Path, *args: str) -> str:
    exe = shutil.which("git")
    if exe is None:
        raise Unreadable("git is not on PATH")
    # Only this tree's .git is read: no GIT_DIR or the like from whatever runs this. Replacement refs,
    # grafts and the commit graph are off, since any of them could make the base read as the change.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_GRAFT_FILE"] = NO_GRAFTS
    try:
        done = subprocess.run([exe, "--no-replace-objects", "-c", "core.commitGraph=false", *args], cwd=str(root),
                              env=env, capture_output=True, timeout=SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        raise Unreadable("git %s did not finish" % args[0])
    if done.returncode != 0:
        raise Unreadable("git %s failed" % args[0])
    return done.stdout.decode("utf-8", "replace")


def base(root: pathlib.Path = ROOT):
    """The commit the records are compared with; None in an export, which has no `.git`. Raises Unreadable."""
    if not os.path.lexists(str(root / ".git")):
        if os.environ.get("GITHUB_ACTIONS"):
            raise Unreadable("there is no .git, and in GitHub Actions the checkout always writes one")
        return None
    if _git(root, "rev-parse", "--is-shallow-repository").strip() != "false":
        raise Unreadable("this clone is shallow")
    _git(root, "rev-parse", "--verify", "--quiet", BASE + "^{commit}")
    return _git(root, "merge-base", "HEAD", BASE).strip()


def described(root: pathlib.Path = ROOT) -> str:
    """What the records were compared with, for `verify` to print."""
    try:
        at = base(root)
    except Unreadable as err:
        return "unreadable (%s)" % err
    if at is None:
        return "skipped: no .git here, so this is an export with no history to compare with"
    return "compared with %s, the merge base with origin/main" % at[:12]


def _recorded(root: pathlib.Path, at: str) -> dict:
    """{path: text} of each record the base holds."""
    names = _git(root, "ls-tree", "-z", "--name-only", at, "--", FOLDER + "/").split("\0")
    return {name: _git(root, "cat-file", "blob", "%s:%s" % (at, name))
            for name in names if name.endswith(".md") and name.count("/") == FOLDER.count("/") + 1}


def _words(lines: list) -> str:
    return " ".join(" ".join(lines).split())


def parse(text: str):
    """(status, rest, rows) of a record, or a sentence saying why it cannot be read as one.

    `status` is the Status paragraph, its words joined by single spaces. `rows` is the Boundary
    cells, all but the Check, of each row of the first table under Boundaries. `rest` is every other
    line, as it stands but for space at its end, with the blank lines at the end of the file left out.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    if "<!--" in text:
        return "it holds an HTML comment, which hides text from a reader"
    if not lines or not lines[0].startswith("# "):
        return "it must open with its title, on a line that opens '# '"
    starts = [i for i, line in enumerate(lines) if line.startswith("Status:")]
    first = next((i for i in range(1, len(lines)) if lines[i]), None)
    if len(starts) != 1 or starts[0] != first:
        return "it must have one line that opens 'Status:', the first after the title"
    end = next((i for i in range(first, len(lines)) if not lines[i]), len(lines))
    heads = [i for i, line in enumerate(lines) if line == BOUNDARIES]
    if len(heads) != 1 or heads[0] < end:
        return "it must have one line '%s', after its Status" % BOUNDARIES
    region = lines[heads[0]:]
    body = _body(region)
    rows = [tuple(" ".join(cell.split()) for cell in _cells(region[i])[:-1]) for i in body]
    rest = lines[:first] + lines[end:heads[0]] + [line for i, line in enumerate(region) if i not in body]
    while rest and not rest[-1]:
        rest.pop()
    return _words(lines[first:end]), rest, rows


def _body(region: list) -> range:
    """The rows of the first table in `region`, below its header and the line under it."""
    # A table may be indented, as Markdown and `check_context` read one (issue 590).
    top = next((i for i, line in enumerate(region) if line.lstrip().startswith("|")), len(region))
    bottom = next((i for i in range(top, len(region)) if not region[i].lstrip().startswith("|")), len(region))
    return range(top + 2, bottom)


def boundaries(text: str) -> list:
    """(Boundary cells, Check cell) of each row of the first table under Boundaries, as `check_context` reads the table,
    outside any fence and however it is indented; [] for a record `parse` cannot read (issue 590)."""
    if isinstance(parse(text), str):
        return []
    rows = _rows(dict(_sections(text, "## ")).get("Boundaries", ""))
    return [(tuple(" ".join(cell.split()) for cell in row[:-1]), " ".join(row[-1].split()) if row else "") for row in rows]


def _names(cell: str) -> list:
    """Every name a cell gives, as `check_context` reads them: in backticks, or as a link's target."""
    return TOKEN.findall(cell) + [m for m in LINK.findall(cell) if "://" not in m and not m.startswith("mailto:")]


def _tokens(cell: str) -> set:
    return set(_names(cell))


def _named_tests(cell: str) -> list:
    """(path, name) of each test a cell names as path::name, its path as the repo holds it, under `tests/`."""
    out = []
    for name in _names(cell):
        path, _, test = name.partition("::")
        path = _path(re.sub(r":\d+$", "", path))
        if test and path.split("/")[0] == "tests":
            out.append((path, test))
    return out


def _tests(cell: str) -> list:
    """(module, name) of each test a cell names as path::name."""
    return [(path[:-len(".py")].replace("/", "."), name) for path, name in _named_tests(cell)]


def _exempt(cell: str, root: pathlib.Path) -> bool:
    """Whether a row has no test that can kill a mutant yet: it waits on a planned part, or says it is not held yet,
    and every test it names is marked @pending (issue 590)."""
    return bool(WAITING.search(cell) or PENDING in cell) and \
        all(_is_pending("%s::%s" % (path, name), root, root) for path, name in _named_tests(cell))


def _is_tests(token: str) -> bool:
    return _path(token.partition("::")[0]).split("/")[0] == "tests"


def _same_check(old: str, new: str) -> bool:
    """Whether a row's Check is the one it was: the same names, but that a test file the old one named bare may now be
    named as a test of that file; the same mutants; and the same wait or the same word that it is not held yet, so a
    rule that stops waiting is a changed row (issue 590)."""
    was = _tokens(old)
    now = {t.partition("::")[0] if "::" in t and t.partition("::")[0] in was and _is_tests(t) else t for t in _tokens(new)}
    return (now == was and MUTANT.findall(old) == MUTANT.findall(new)
            and WAITING.findall(old) == WAITING.findall(new) and (PENDING in old) == (PENDING in new))


def _changed(old: list, new: list) -> list:
    """(number, row) of each row of `new` that is new or whose Check changed, against `old`, in order (issue 590)."""
    left, out = list(old), []
    for at, row in enumerate(new, 1):
        if row in left:
            left.remove(row)
            continue
        same = next((o for o in left if o[0] == row[0] and _same_check(o[1], row[1])), None)
        if same is not None:
            left.remove(same)
        else:
            out.append((at, row))
    return out


def _mutants(root: pathlib.Path) -> dict:
    """{description: (file, the tests that kill it)} of every mutant `tools/mutants.py` runs in `root`, read once for
    each root and each text of its files. Two that share a description name no one mutant. Raises Unreadable."""
    try:
        files = _mutant_files(root)
        key = (str(root.resolve()), tuple((str(path), hashlib.sha256(path.read_bytes()).hexdigest()) for path in files))
    except OSError as err:
        raise Unreadable("tools/mutants.py cannot be read (%s)" % type(err).__name__)
    if key not in _READ:
        try:
            read = [(name, (rel, tests)) for name, rel, tests in read_mutants(root)]
        except Exception as err:    # noqa: BLE001 -- whatever stops it being read, the mutants are unreadable
            raise Unreadable("tools/mutants.py cannot be read (%s)" % type(err).__name__)
        if len({name for name, _ in read}) != len(read):
            raise Unreadable("two mutants in tools/mutants.py share a description, so a row cannot name one of them")
        _READ[key] = dict(read)
    return _READ[key]


_READ = {}

# The mutants are read from the text of their files through ast, never imported: a file of tools/mutants_of/ that a push
# changes could end this process at import (issue 1377). What the reader does not work out, a call or a name it was not
# given, is UNKNOWN; a starred part it cannot work out is SPREAD. A mutant whose description, file or tests is either
# cannot be read.
UNKNOWN = type("Unknown", (), {"__repr__": lambda self: "UNKNOWN"})()
SPREAD = type("Spread", (), {"__repr__": lambda self: "SPREAD"})()
AREA = re.compile(r"[a-z_][a-z0-9_]*")       # the module names tools/mutants.py loads from tools/mutants_of/


class _Module(dict):
    """The names a file of mutants binds, which `module.name` reads."""


class _Function:
    """A function of a file of mutants that the reader runs itself: positional parameters alone, and a body of
    assignments to names, `if` statements and returns that call a name, `.items()` or `.get()` alone. Of those calls
    it works out only another such function, `tuple`, `dict` and the two methods of a dict; any other is UNKNOWN."""

    def __init__(self, node, bound: dict):
        self.node, self.bound = node, bound

    @staticmethod
    def readable(node) -> bool:
        args = node.args
        if node.decorator_list or args.vararg or args.kwarg or args.kwonlyargs or args.defaults \
                or getattr(args, "posonlyargs", []):
            return False
        body = node.body[1:] if node.body and _docstring(node.body[0]) else node.body
        return all(_statement(one) for one in body)


def _docstring(node) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _statement(node) -> bool:
    """Whether a function's statement is one the reader runs: see _Function."""
    if isinstance(node, ast.If):
        return all(_statement(one) for one in node.body + node.orelse) and _pure(node.test)
    if isinstance(node, ast.Assign):
        return all(isinstance(target, ast.Name) for target in node.targets) and _pure(node.value)
    return isinstance(node, ast.Return) and node.value is not None and _pure(node.value)


def _pure(node) -> bool:
    """Whether an expression calls nothing but a name (a function the reader runs, `tuple` or `dict`), or `.items()`
    and `.get()`, which change nothing."""
    return all(isinstance(one.func, ast.Name) or (isinstance(one.func, ast.Attribute) and one.func.attr in ("items", "get"))
               for one in ast.walk(node) if isinstance(one, ast.Call)) \
        and not any(isinstance(one, (ast.Lambda, ast.NamedExpr)) for one in ast.walk(node))


def _mutant_files(root: pathlib.Path) -> list:
    """tools/mutants.py, then tools/mutants_of/common.py, then each file of mutants there in the order of its name, as
    tools/mutants.py finds them: a Python file directly in the folder, by a module name, but __init__ and common."""
    folder = root / "tools" / "mutants_of"
    areas = [path for path in walk.files(root, "tools/mutants_of") if path.parent == folder and path.suffix == ".py"
             and path.stem not in ("__init__", "common") and AREA.fullmatch(path.stem)]
    common = [folder / "common.py"] if (folder / "common.py").is_file() else []
    return [root / "tools" / "mutants.py"] + common + areas


def read_mutants(root: pathlib.Path) -> list:
    """(description, file, tests) of each mutant of tools/mutants.py's MUTANTS in `root`, read as that file builds it:
    its own, and those of each file of tools/mutants_of/, which its `areas(ROOT)` loads. Raises ValueError for a
    mutant it cannot read."""
    files = _mutant_files(root)
    folder = root / "tools" / "mutants_of"
    common = _module(folder / "common.py", {}, None) if folder / "common.py" in files else {}
    areas = tuple(_module(path, common, None) for path in files[1:] if path.stem != "common")
    listed = _module(files[0], common, areas).get("MUTANTS", UNKNOWN)
    if not isinstance(listed, list):
        raise ValueError("MUTANTS is not a list read as text")
    return [_parts(mutant) for mutant in listed]


def _parts(mutant) -> tuple:
    """(description, file, tests) of one mutant: its first, its second and its last part, of five."""
    if not isinstance(mutant, tuple) or len(mutant) < 3 or SPREAD in (mutant[0], mutant[1], mutant[-1]):
        raise ValueError("a mutant is not a tuple read as text")
    if SPREAD not in mutant and len(mutant) != 5:
        raise ValueError("a mutant has not five parts")
    name, rel, tests = mutant[0], mutant[1], mutant[-1]
    if not (isinstance(name, str) and isinstance(rel, str) and isinstance(tests, tuple)
            and all(isinstance(test, str) for test in tests)):
        raise ValueError("a mutant's description, file or tests is not read as text")
    return name, rel, tests


def _module(path: pathlib.Path, common: dict, areas) -> dict:
    """The names a file of mutants binds at its top, each to what the reader works out of it, else UNKNOWN. `areas` is
    what `areas(ROOT)` loads when the file is tools/mutants.py, and None in any other. A name any
    other statement binds, and a list or dict that a call or any other statement names, is UNKNOWN after it."""
    bound = _Module()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "tools.mutants_of.common":
            for alias in node.names:
                bound[alias.asname or alias.name] = common.get(alias.name, UNKNOWN)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "tools.mutants_of":
            for alias in node.names:
                bound[alias.asname or alias.name] = _Module(common) if alias.name == "common" else UNKNOWN
        elif isinstance(node, ast.FunctionDef) and _Function.readable(node):
            bound[node.name] = _Function(node, bound)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            value = _value(node.value, bound, areas)
            _touched(node.value, bound)
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                _bind(target, value, bound)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # A def runs its decorators and its defaults, never its body.
            for one in node.decorator_list + node.args.defaults + [d for d in node.args.kw_defaults if d is not None]:
                _touched(one, bound, every=True)
            bound[node.name] = UNKNOWN
        else:
            _touched(node, bound, every=True)
    return bound


def _bind(target, value, bound: dict) -> None:
    if isinstance(target, ast.Name):
        bound[target.id] = value
    elif isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (tuple, list)) and SPREAD not in value \
            and len(value) == len(target.elts) and not any(isinstance(t, ast.Starred) for t in target.elts):
        for one, part in zip(target.elts, value):
            _bind(one, part, bound)
    else:
        for name in _stored(target):
            bound[name] = UNKNOWN


def _stored(node) -> set:
    """Every name a statement or a target binds, by any means at any depth, and each it declares global."""
    out = set()
    for one in ast.walk(node):
        if isinstance(one, ast.Name) and not isinstance(one.ctx, ast.Load):
            out.add(one.id)
        elif isinstance(one, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(one.name)
        elif isinstance(one, (ast.Import, ast.ImportFrom)):
            out |= {(alias.asname or alias.name).split(".")[0] for alias in one.names}
        elif isinstance(one, (ast.Global, ast.Nonlocal)):
            out |= set(one.names)
    return out


def _touched(node, bound: dict, every: bool = False) -> None:
    """Make UNKNOWN what `node` could change: when `every`, each name it binds and each list or dict it names; else each
    list or dict named inside a call."""
    names = _stored(node) if every else set()
    calls = [n for n in ast.walk(node) if isinstance(n, ast.Call) and not _harmless(n, bound)]
    for one in [node] if every else calls:
        names |= {n.id for n in ast.walk(one) if isinstance(n, ast.Name) and isinstance(bound.get(n.id), (list, dict))}
    for name in names:
        bound[name] = UNKNOWN


def _harmless(call, bound: dict) -> bool:
    """Whether a call changes nothing it is given: `tuple`, `dict`, `.items()`, `.get()` or a function the reader runs."""
    func = call.func
    if isinstance(func, ast.Name):
        return isinstance(bound.get(func.id), _Function) or (func.id in ("tuple", "dict") and func.id not in bound)
    return isinstance(func, ast.Attribute) and func.attr in ("items", "get")


def _value(node, bound: dict, areas: tuple, scope: dict = None):
    """What `node` evaluates to, where the reader works it out from text alone; UNKNOWN otherwise."""
    scope = bound if scope is None else scope
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return scope.get(node.id, UNKNOWN)
    if isinstance(node, (ast.Tuple, ast.List)):
        out = []
        for one in node.elts:
            inner = _value(one.value if isinstance(one, ast.Starred) else one, bound, areas, scope)
            if not isinstance(one, ast.Starred):
                out.append(inner)
            else:
                out += list(inner) if isinstance(inner, (tuple, list)) else [SPREAD]
        return tuple(out) if isinstance(node, ast.Tuple) else out
    if isinstance(node, ast.Dict) and None not in node.keys:
        keys = [_value(one, bound, areas, scope) for one in node.keys]
        return dict(zip(keys, [_value(one, bound, areas, scope) for one in node.values])) if _plain(keys) else UNKNOWN
    if isinstance(node, ast.BinOp):
        return _operation(node, bound, areas, scope)
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        return _compared(node, bound, areas, scope)
    if isinstance(node, ast.Attribute):
        held = _value(node.value, bound, areas, scope)
        return held.get(node.attr, UNKNOWN) if isinstance(held, _Module) else UNKNOWN
    if isinstance(node, ast.Subscript):
        held, at = _value(node.value, bound, areas, scope), _index(node.slice, bound, areas, scope)
        if type(held) is dict and _plain(_value(node.slice, bound, areas, scope)):
            return held.get(_value(node.slice, bound, areas, scope), UNKNOWN)
        if isinstance(held, (str, tuple)) and at is not UNKNOWN and _plain(held):
            try:
                return held[at]
            except (IndexError, TypeError):
                return UNKNOWN
        return UNKNOWN
    if isinstance(node, (ast.ListComp, ast.GeneratorExp)):
        made = _comprehension(node, bound, areas, scope)
        return made if made is UNKNOWN or isinstance(node, ast.ListComp) else tuple(made)
    if isinstance(node, ast.Call):
        return _called(node, bound, areas, scope)
    if isinstance(node, ast.IfExp):
        test = _truth(_value(node.test, bound, areas, scope))
        return UNKNOWN if test is None else _value(node.body if test else node.orelse, bound, areas, scope)
    if isinstance(node, ast.DictComp):
        made = _comprehension(ast.ListComp(elt=ast.Tuple(elts=[node.key, node.value], ctx=ast.Load()),
                                           generators=node.generators), bound, areas, scope)
        return dict(made) if made is not UNKNOWN and _plain([key for key, _ in made]) else UNKNOWN
    return UNKNOWN


def _called(node, bound: dict, areas: tuple, scope: dict, depth: int = 0):
    """A call the reader works out: a function it runs, `dict(d, **e)`, `.items()` or `.get(key[, default])`."""
    func = node.func
    args = [_value(one, bound, areas, scope) for one in node.args]
    if isinstance(func, ast.Attribute) and not node.keywords and func.attr in ("items", "get"):
        held = _value(func.value, bound, areas, scope)
        if type(held) is not dict:
            return UNKNOWN
        if func.attr == "items" and not args:
            return list(held.items())
        if func.attr == "get" and len(args) in (1, 2) and _plain(args[0]):
            return held.get(args[0], args[1] if len(args) == 2 else None)
        return UNKNOWN
    if not isinstance(func, ast.Name) or node.keywords and func.id != "dict":
        return UNKNOWN
    if func.id == "areas" and "areas" in scope and areas is not None and len(args) == 1:
        return areas        # tools/mutants.py's own areas(ROOT): the files of tools/mutants_of/, read alike
    if func.id == "tuple" and "tuple" not in scope and len(args) == 1:
        made = args[0]
        return tuple(made) if isinstance(made, (tuple, list, dict)) and _plain(list(made)) else UNKNOWN
    if func.id == "dict" and "dict" not in scope and len(args) <= 1:
        out = {}
        for one in args + [_value(k.value, bound, areas, scope) for k in node.keywords if k.arg is None]:
            if type(one) is not dict:
                return UNKNOWN
            out.update(one)
        return out if all(k.arg is None for k in node.keywords) else UNKNOWN
    called = scope.get(func.id)
    if isinstance(called, _Function) and not node.keywords and len(args) == len(called.node.args.args):
        if len(_CALLS) > 50:
            return UNKNOWN
        _CALLS.append(func.id)
        try:
            return _ran(called, dict(called.bound, **{a.arg: v for a, v in zip(called.node.args.args, args)}), areas)
        finally:
            _CALLS.pop()
    return UNKNOWN


_CALLS = []     # the functions being run, so that one calling itself ends


def _ran(function: _Function, local: dict, areas: tuple):
    """What a function the reader runs returns: UNKNOWN where a test it meets is not worked out."""
    body = function.node.body
    for node in body[1:] if body and _docstring(body[0]) else body:
        out = _step(node, local, function.bound, areas)
        if out is not _ON:
            return out
    return UNKNOWN


_ON = object()      # a statement that returned nothing: run the next one


def _step(node, local: dict, bound: dict, areas: tuple):
    if isinstance(node, ast.Return):
        return _value(node.value, bound, areas, local)
    if isinstance(node, ast.Assign):
        value = _value(node.value, bound, areas, local)
        for target in node.targets:
            local[target.id] = value
        return _ON
    test = _truth(_value(node.test, bound, areas, local))
    if test is None:
        return UNKNOWN
    for one in node.body if test else node.orelse:
        out = _step(one, local, bound, areas)
        if out is not _ON:
            return out
    return _ON


def _compared(node, bound: dict, areas: tuple, scope: dict):
    """`a == b`, `a != b`, `a in b` or `a not in b` of values worked out whole; UNKNOWN otherwise."""
    left, right = _value(node.left, bound, areas, scope), _value(node.comparators[0], bound, areas, scope)
    if not (_plain(left) and _plain(right)):
        return UNKNOWN
    op = type(node.ops[0])
    if op in (ast.In, ast.NotIn) and not isinstance(right, (str, tuple, list, dict)):
        return UNKNOWN
    answers = {ast.Eq: lambda: left == right, ast.NotEq: lambda: left != right,
               ast.In: lambda: left in right, ast.NotIn: lambda: left not in right}
    return answers[op]() if op in answers else UNKNOWN


def _operation(node, bound: dict, areas: tuple, scope: dict):
    """`a + b` of two strings, tuples or lists, or `text % values`, worked out; UNKNOWN otherwise."""
    left, right = _value(node.left, bound, areas, scope), _value(node.right, bound, areas, scope)
    if isinstance(node.op, ast.Add) and type(left) is type(right) and isinstance(left, (str, tuple, list)):
        return left + right
    if isinstance(node.op, ast.Mod) and isinstance(left, str) and _plain(right):
        try:
            return left % right
        except (TypeError, ValueError, KeyError):
            return UNKNOWN
    return UNKNOWN


def _truth(value):
    """Whether a value worked out whole is true, as `if` reads it; None for one that is not worked out."""
    return bool(value) if _plain(value) else None


def _plain(value) -> bool:
    """Whether `value` is worked out whole: no UNKNOWN or SPREAD at any depth."""
    if value is UNKNOWN or value is SPREAD:
        return False
    if isinstance(value, dict):
        return not isinstance(value, _Module) and _plain(list(value)) and _plain(list(value.values()))
    return all(_plain(one) for one in value) if isinstance(value, (tuple, list)) else True


def _index(node, bound: dict, areas: tuple, scope: dict):
    if isinstance(node, ast.Slice):
        parts = [None if one is None else _index(one, bound, areas, scope) for one in (node.lower, node.upper, node.step)]
        return slice(*parts) if UNKNOWN not in parts else UNKNOWN
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _index(node.operand, bound, areas, scope)
        return -inner if inner is not UNKNOWN else UNKNOWN
    at = _value(node, bound, areas, scope)
    return at if isinstance(at, int) and not isinstance(at, bool) else UNKNOWN


def _comprehension(node, bound: dict, areas: tuple, scope: dict):
    """The list a comprehension builds, each of its loops over what the reader works out, with no condition."""
    rounds = [dict(scope)]
    for loop in node.generators:
        if loop.is_async:
            return UNKNOWN
        after = []
        for inner in rounds:
            over = _value(loop.iter, bound, areas, inner)
            if type(over) is dict:
                over = list(over)
            if not isinstance(over, (tuple, list)) or SPREAD in over:
                return UNKNOWN
            for item in over:
                one = dict(inner)
                _bind(loop.target, item, one)
                kept = [_truth(_value(test, bound, areas, one)) for test in loop.ifs]
                if None in kept:
                    return UNKNOWN
                if all(kept):
                    after.append(one)
        rounds = after
    return [_value(node.elt, bound, areas, inner) for inner in rounds]


def _is_test(killer: str, module: str, name: str) -> bool:
    """Whether a mutant's killer is the test `name` of `module`: a test of one class, by its module, its class and its
    own name, which the row gives as `Class.name`, or as `name` alone. A module or a class is not a test, whatever it
    is called (issue 590)."""
    parts = killer.split(".")
    if not killer.startswith(module + ".") or len(parts) != module.count(".") + 3:
        return False
    return ".".join(parts[-2:]) == name if "." in name else parts[-1] == name


def _path(name: str) -> str:
    """A path as the repo holds it, so that `./tests/x.py` and `tools/../tests/x.py` are `tests/x.py`. One that climbs
    out of the repo keeps its `..`, and so names nothing here."""
    parts = []
    for part in name.split("/"):
        if part in ("", "."):
            continue
        if part == ".." and parts and parts[-1] != "..":
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def _named_mutant(rel: str, at: int, row: tuple, root: pathlib.Path, mutants: dict) -> list:
    """Why the row at boundary `at` does not name the mutant its test kills, or [] (issue 590)."""
    where, cell = "%s, boundary %d" % (rel, at), row[1]
    if _exempt(cell, root):
        return []
    named = MUTANT.findall(cell)
    if not named:
        return ['%s: a new or changed row names no mutant; name one as mutant: "<its description in tools/mutants.py>"'
                % where]
    tests = _tests(cell)
    if not tests:
        return ["%s: names no test for its mutant to be killed by; name it as path::name" % where]
    names = {_path(t.partition("::")[0]) for t in _tokens(" ".join(row[0]) + " " + cell)}
    problems = []
    for name in named:
        if name not in mutants:
            problems.append('%s: names mutant "%s", which tools/mutants.py does not hold' % (where, name))
            continue
        changed, killers = mutants[name]
        changed = _path(changed)
        if changed.split("/")[0] == "tests" or changed not in names:
            problems.append('%s: mutant "%s" changes %s, which this row does not name' % (where, name, changed))
        # The mutant is run against the tests it lists alone (tools/mutants.py), so each is one this row names.
        if not killers or not all(any(_is_test(k, module, test) for module, test in tests) for k in killers):
            problems.append('%s: mutant "%s" lists a test this row does not name, or none' % (where, name))
    return problems


def unnamed(root: pathlib.Path = ROOT) -> str:
    """How many Boundary rows name no mutant, of how many that could, for `verify` to print (issue 590)."""
    rows = [cell for path in sorted((root / FOLDER).glob("*.md"))
            for _, cell in boundaries(path.read_text(encoding="utf-8", errors="replace")) if not _exempt(cell, root)]
    return "%d of %d boundary rows name no mutant" % (sum(1 for c in rows if not MUTANT.search(c)), len(rows))


def held_by_rows(root: pathlib.Path = ROOT) -> set:
    """The description of each mutant a Boundary row names, which `tools/mutants.py` runs against its own tests alone."""
    return {name for path in sorted((root / FOLDER).glob("*.md"))
            for _, cell in boundaries(path.read_text(encoding="utf-8", errors="replace")) for name in MUTANT.findall(cell)}


def _declared(pattern, status: str):
    """`pattern` matched at the start of `status`, or None when it is not, or when what follows it claims more."""
    found = pattern.match(status)
    rest = status[found.end():] if found else ""
    if found is None or CLAIM.search(rest) or FOLDER + "/" in rest:
        return None
    return found


def _status(rel: str, old: str, new: str, before: dict, root: pathlib.Path) -> str:
    """Why the Status at `rel` may not change from `old` to `new`, or "" when it may."""
    if new == old:
        return ""
    if REPLACED.match(old):
        return "its Status named the record that replaces it, and is fixed from then on"
    named = _declared(REPLACED, new)
    if named is None:
        return ("its Status changes only to say what replaces it: 'Status: replaced by' and the path in backticks, "
                "as decision 0012's does, and nothing more of replacing or of another record")
    path, number = named.group(1), named.group(2)
    own = NUMBER.match(rel.rsplit("/", 1)[-1])
    if path in before:
        return "it names %s, which is not new in this change; the record that replaces it is" % path
    target = root / path
    if target.is_symlink() or not target.is_file():
        return "it names %s, which does not exist" % path
    if own is None or int(number) <= int(own.group(1)):
        return "it names %s, which is not a later record" % path
    said = parse(target.read_text(encoding="utf-8", errors="replace"))
    if rel not in (_replaces(said[0]) if isinstance(said, tuple) else []):
        return "%s's Status does not say it replaces this one: 'Status: accepted. Replaces' and its path" % path
    return ""


def _replaces(status: str) -> list:
    """The paths a Status names, in decision 0015's words, as the records it replaces."""
    listed = _declared(REPLACES, status)
    return re.findall(r"`([^`]+)`", listed.group(1)) if listed else []


def _replacing(rel: str, status: str, before: dict, current: dict) -> list:
    """Why the new record at `rel` does not replace what its Status says it does: each record it names is in the
    base, earlier, and in this change has its Status set to 'replaced by' this one."""
    if not CLAIM.search(status):
        return []
    names = _replaces(status)
    if not names:
        return ["its Status says what it replaces only as 'Status: accepted. Replaces' and each path in backticks, "
                "and nothing more of replacing or of another record"]
    own, why = NUMBER.match(rel.rsplit("/", 1)[-1]), []
    for name in names:
        number = NUMBER.match(name.rsplit("/", 1)[-1]) if re.fullmatch(PATH, "`%s`" % name) else None
        now = current.get(name)
        said = _declared(REPLACED, now[0]) if isinstance(now, tuple) else None
        if name not in before or number is None or now is None:
            why.append("it replaces %s, which is not a record main holds" % name)
        elif own is None or int(number.group(1)) >= int(own.group(1)):
            why.append("it replaces %s, which is not an earlier record" % name)
        elif said is None or said.group(1) != rel:
            why.append("it replaces %s, whose Status does not say 'replaced by' and this record's path" % name)
    return why


def _boundaries(old: list, new: list) -> str:
    """Why the Boundaries rows may not change from `old` to `new`, or "" when they may."""
    left = list(new)
    for row in old:
        if row not in left:
            return ("the row '%s' is gone or its Boundary changed; a row is only added, or its Check changed"
                    % " | ".join(row))
        left.remove(row)
    return ""


def _linked(root: pathlib.Path) -> list:
    folder = root / FOLDER
    if folder.is_symlink():
        return ["%s: is a link; the records are files here, which this check reads" % FOLDER]
    entries = sorted(folder.iterdir()) if folder.is_dir() else []
    return ["%s: is a link; a record is a file, which this check reads where it stands" % p.relative_to(root).as_posix()
            for p in entries if p.is_symlink()]


def _mutants_named(root: pathlib.Path, before: dict, texts: dict) -> list:
    """Why each Boundary row new in this change, or whose Check changed, or that names a mutant, does not name the
    mutant its test kills. Rows main holds that name none are left as they are (issue 590)."""
    problems, mutants = [], None
    for rel, text in sorted(texts.items()):
        rows = boundaries(text)
        fresh = dict(_changed(boundaries(before[rel]), rows) if rel in before else enumerate(rows, 1))
        for at, row in enumerate(rows, 1):
            if at not in fresh and not MUTANT.search(row[1]):
                continue
            if mutants is None and not _exempt(row[1], root):
                try:
                    mutants = _mutants(root)
                except Unreadable as err:
                    return problems + ["%s, boundary %d: %s, so no mutant it names can be read" % (rel, at, err)]
            problems += _named_mutant(rel, at, row, root, mutants or {})
    return problems


def run(root: pathlib.Path = ROOT) -> list:
    problems = _linked(root)
    folder = root / FOLDER
    current, texts = {}, {}
    for path in sorted(folder.glob("*.md")) if folder.is_dir() and not folder.is_symlink() else []:
        rel = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.is_file():
            continue
        try:
            texts[rel] = path.read_text(encoding="utf-8")
            current[rel] = parse(texts[rel])
        except UnicodeDecodeError:
            current[rel] = "it is not UTF-8"
        if isinstance(current[rel], str):
            problems.append("%s: %s" % (rel, current[rel]))
    try:
        at = base(root)
        before = _recorded(root, at) if at else {}
    except Unreadable as err:
        return problems + ["the decision records cannot be compared with the merge base of HEAD and %s (%s); fetch "
                           "main's whole history (git fetch --unshallow origin, or git fetch origin main) and run "
                           "again" % (BASE, err)]
    for rel, new in sorted(current.items()):
        if at and rel not in before and isinstance(new, tuple):     # with no base, nothing is known to be new
            problems += ["%s: %s" % (rel, why) for why in _replacing(rel, new[0], before, current)]
    if at:
        problems += _mutants_named(root, before, texts)
    for rel, text in sorted(before.items()):
        old, new = parse(text), current.get(rel)
        if new is None:
            problems.append("%s: is gone; a record is never removed or renamed, so restore it, and add a record "
                            "that replaces it" % rel)
            continue
        if isinstance(new, str):
            continue        # said above
        if isinstance(old, str):
            problems.append("%s: the base's copy cannot be read as a record (%s), so it cannot be compared" % (rel, old))
            continue
        why = [w for w in (_status(rel, old[0], new[0], before, root),
                           "its title, Decision or Why changed" if old[1] != new[1] else "",
                           _boundaries(old[2], new[2])) if w]
        if why:
            problems.append("%s: %s; a record is never edited, only replaced: restore it, add a record that replaces "
                            "it, and set this one's Status to 'replaced by' and that record's path" % (rel, "; ".join(why)))
    return problems
