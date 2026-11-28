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
        key = (str(root.resolve()), tuple((str(path), hashlib.sha256(path.read_bytes()).hexdigest())
                                          for path in _mutant_files(root)))
        if key not in _READ:
            _READ[key] = [(name, (rel, tests)) for name, rel, tests in read_mutants(root)]
    except Exception as err:    # noqa: BLE001 -- whatever stops it being read, the mutants are unreadable
        why = "%s: %s" % (type(err).__name__, err) if isinstance(err, ValueError) else type(err).__name__
        raise Unreadable("tools/mutants.py cannot be read (%s)" % why)
    read = _READ[key]
    if len({name for name, _ in read}) != len(read):
        raise Unreadable("two mutants in tools/mutants.py share a description, so a row cannot name one of them")
    return dict(read)


_READ = {}

# The mutants are read from the text of their files through ast, never imported: a file of tools/mutants_of/ that a push
# changes could end this process at import (issue 1377). The reader takes a file only in a narrow grammar in which no
# value, once bound, can change, and works out each value as Python would, or leaves it UNKNOWN where Python reads it
# from outside the text, a path or a file. It refuses with ValueError whatever else it meets, so it never reads a list
# other than the one Python would build. `tools/mutants.py`'s `areas(ROOT)`, which imports the files of mutants, is read
# only as PINNED writes it.
STDLIB = frozenset(("concurrent.futures", "contextlib", "importlib", "json", "os", "pathlib", "re", "signal", "subprocess",
                    "sys", "tempfile", "unittest"))
BUILTINS = frozenset(("dict", "iter", "len", "range", "tuple"))
EXCEPTIONS = frozenset(("Exception", "RuntimeError", "ValueError"))
# Of any value a file of mutants can reach, these methods and attributes change nothing: a str's, a dict's, a path's, a
# pattern's or re's. A str's `replace` is worked out at the top alone, on a str: a path's renames a file.
METHODS = frozenset(("endswith", "find", "fullmatch", "get", "isdigit", "items", "keys", "lower", "match", "read_text",
                     "resolve", "rfind", "search", "startswith", "strip", "sub", "values"))
ATTRIBUTES = frozenset(("name", "parent", "parents", "stem", "suffix"))
MODULE_CALLS = frozenset((("pathlib", "Path"), ("re", "compile"), ("re", "sub")))
MODULES = frozenset({name.split(".")[0] for name in STDLIB} | {"tools.walk"})
TYPES = frozenset(("bool", "dict", "float", "int", "list", "str", "tuple"))      # an annotation may name one
MODULE_VALUES = frozenset((("contextlib", "contextmanager"), ("importlib", "import_module"), ("re", "M")))
EXPRESSIONS = (ast.Constant, ast.Name, ast.Load, ast.Store, ast.Tuple, ast.List, ast.Dict, ast.Starred, ast.BinOp,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.UnaryOp, ast.USub, ast.Not,
               ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
               ast.IfExp, ast.Attribute, ast.Subscript, ast.Slice, ast.ListComp, ast.DictComp, ast.GeneratorExp,
               ast.comprehension, ast.Call, ast.keyword)
BUDGET = {"calls": 20000, "rounds": 200000, "length": 1000000, "width": 1000, "depth": 100}
PINNED = {
    "ROOT": 'ROOT = pathlib.Path(__file__).resolve().parent.parent',
    "AREA_NAME": 'AREA_NAME = re.compile(r"[a-z_][a-z0-9_]*")',
    "area_names": 'def area_names(root: pathlib.Path) -> list:\n    """The name of each file of mutants in `root`\'s '
                  'tools/mutants_of/: its Python files but __init__.py and common.py,\n    directly in it, as the walk '
                  'gives them."""\n    folder = root / "tools" / "mutants_of"\n    return [path.stem for path in '
                  'walk.files(root, "tools/mutants_of")\n            if path.parent == folder and path.suffix == ".py" '
                  'and path.stem not in ("__init__", "common")]',
    "areas": 'def areas(root: pathlib.Path, load=importlib.import_module) -> tuple:\n    """Each file of mutants in '
             '`root`, loaded by `load` in the order of the names. Each name is a module name, by\n    AREA_NAME, before '
             'it is loaded: nothing but a file of tools/mutants_of/ is imported."""\n    return tuple(load('
             '"tools.mutants_of." + name) for name in area_names(root) if AREA_NAME.fullmatch(name))',
    "main": 'if __name__ == "__main__":\n    sys.exit(front(os.environ, sys.argv[1:]))',
}
AREA = re.compile(r"[a-z_][a-z0-9_]*")       # the module names tools/mutants.py loads from tools/mutants_of/
FORMAT = re.compile(r"%(?:\([^)]*\))?[#0 +-]*(\*|\d+)?(?:\.(\*|\d+))?")


class _Opaque:
    """A value the reader does not work out: a module of STDLIB, ROOT, AREA_NAME or what Python reads from outside."""

    def __init__(self, what: str):
        self.what = what

    def __repr__(self):
        return self.what


UNKNOWN = _Opaque("UNKNOWN")


class _Module(dict):
    """The names a file of mutants binds, which `module.name` reads."""


class _Function:
    """A function defined at the top of a file of mutants, run by the reader when it is called, if `_safe` passes it."""

    def __init__(self, node, source: str, file: "_File", defaults: list):
        self.node, self.source, self.file, self.defaults = node, source, file, defaults


class _File:
    """One file of mutants as it is read: its text, the names its top binds, and its defs bound once there."""

    def __init__(self, read: "_Read", rel: str):
        self.read, self.rel, self.bound, self.future, self.safe = read, rel, _Module(), False, set()
        data = (read.root / rel).read_bytes()
        self.text = data.decode("utf-8")
        self.tree = ast.parse(data, filename=rel)
        top = [_targets(node) for node in self.tree.body]
        self.names = {name for names in top for name in names}
        self.defs = {node.name: node for node in self.tree.body if isinstance(node, ast.FunctionDef)
                     and sum(node.name in names for names in top) == 1}


class _Read:
    """One reading of a tree's mutants: its root, the modules read so far, and what is left of the budget."""

    def __init__(self, root: pathlib.Path):
        self.root, self.done, self.calls, self.rounds, self.depth = root, {}, 0, 0, 0

    def loaded(self, name: str) -> _Module:
        """tools.mutants_of's module `name`, or the package for "", read once, its package first, as Python imports."""
        folder = self.root / "tools" / "mutants_of"
        if name and "" not in self.done:
            self.loaded("")
        if name not in self.done:
            if name and ((folder / name).is_dir() or not (folder / "__init__.py").is_file()):
                raise ValueError("tools.mutants_of.%s is not the file the reader reads" % name)
            self.done[name] = None
            self.done[name] = _top(self, "tools/mutants_of/%s.py" % (name or "__init__"))
        if self.done[name] is None:
            raise ValueError("tools.mutants_of.%s imports itself" % name)
        return self.done[name]


def _targets(node) -> set:
    """Each name a statement at the top of a file binds."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {(alias.asname or alias.name).split(".")[0] for alias in node.names}
    return {one.id for one in ast.walk(node) if isinstance(one, ast.Name) and isinstance(one.ctx, ast.Store)}


def _mutant_files(root: pathlib.Path) -> list:
    """tools/mutants.py, then tools/mutants_of/__init__.py and common.py, then each file of mutants there in the order
    of its name, as tools/mutants.py finds them: a Python file directly in the folder, by a module name."""
    folder = root / "tools" / "mutants_of"
    areas = [path for path in walk.files(root, "tools/mutants_of") if path.parent == folder and path.suffix == ".py"
             and path.stem not in ("__init__", "common") and AREA.fullmatch(path.stem)]
    return [root / "tools" / "mutants.py"] + [folder / one for one in ("__init__.py", "common.py")
                                              if (folder / one).is_file()] + areas


def read_mutants(root: pathlib.Path) -> list:
    """(description, file, tests) of each mutant of tools/mutants.py's MUTANTS in `root`, read as Python builds it: its
    own, and those of each file of tools/mutants_of/ that its `areas(ROOT)` loads. Raises ValueError for a file or a
    mutant it cannot read so."""
    listed = _top(_Read(root), "tools/mutants.py").get("MUTANTS", UNKNOWN)
    if type(listed) is not list:
        raise ValueError("MUTANTS is not a list read as text")
    return [_parts(mutant) for mutant in listed]


def _parts(mutant) -> tuple:
    """(description, file, tests) of one mutant: its first, its second and its last part, of five."""
    if type(mutant) is not tuple or len(mutant) != 5:
        raise ValueError("a mutant is not a tuple of five parts")
    name, rel, tests = mutant[0], mutant[1], mutant[4]
    if not (type(name) is str and type(rel) is str and type(tests) is tuple and all(type(t) is str for t in tests)):
        raise ValueError("a mutant's description, file or tests is not read as text")
    return name, rel, tests


def _top(read: _Read, rel: str) -> _Module:
    """The names the file `rel` binds at its top, each to what the reader works out of it."""
    file = _File(read, rel)
    frame = _Frame(file)
    for node in file.tree.body:
        if _docstring(node):
            continue
        pinned = rel == "tools/mutants.py" and (isinstance(node, ast.If) or getattr(node, "name", "") in PINNED
                                                or isinstance(node, ast.Assign)
                                                and [getattr(t, "id", "") for t in node.targets] in (["ROOT"], ["AREA_NAME"]))
        source = ast.get_source_segment(file.text, node) if pinned else None
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _imported(node, file)
        elif isinstance(node, ast.FunctionDef) and not node.decorator_list:
            file.bound[node.name] = _Function(node, source, file, _signature(node, frame))
        elif isinstance(node, ast.ClassDef):
            _classed(node, frame)
        elif isinstance(node, ast.Assign) and rel == "tools/mutants.py" and source in (PINNED["ROOT"], PINNED["AREA_NAME"]):
            file.bound[node.targets[0].id] = _Opaque(node.targets[0].id)
        elif isinstance(node, ast.Assign):
            value = frame.value(node.value)
            for target in node.targets:
                _bind(target, value, file.bound)
        elif not (isinstance(node, ast.If) and rel == "tools/mutants.py" and source == PINNED["main"]):
            raise ValueError("%s line %d is not read" % (rel, node.lineno))
    return file.bound


def _docstring(node) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _imported(node, file: _File) -> None:
    """Bind what an import binds: a module of STDLIB, or a name of tools/mutants_of/common.py, or common itself; in
    tools/mutants.py also tools.walk and tools.verify's SLOW. Any other import is refused."""
    names = [(alias.name, alias.asname) for alias in node.names]
    if isinstance(node, ast.Import):
        for name, asname in names:
            if name not in STDLIB or asname:
                raise ValueError("%s imports %s" % (file.rel, name))
            file.bound[name.split(".")[0]] = _Opaque(name.split(".")[0])
        return
    module, runner = node.module, file.rel == "tools/mutants.py"
    if node.level or any(name == "*" for name, _ in names):
        raise ValueError("%s imports from %s" % (file.rel, module))
    if module == "__future__" and names == [("annotations", None)]:
        file.future = True
    elif module == "tools.mutants_of.common" and file.rel != "tools/mutants_of/common.py":
        common = file.read.loaded("common")
        for name, asname in names:
            if name not in common:
                raise ValueError("%s imports %s, which common.py does not bind" % (file.rel, name))
            file.bound[asname or name] = common[name]
    elif module == "tools.mutants_of" and names == [("common", None)]:
        file.bound["common"] = file.read.loaded("common")
    elif runner and (module, names) in (("tools", [("walk", None)]), ("tools.verify", [("SLOW", None)])):
        file.bound[names[0][0]] = _Opaque(module + "." + names[0][0])
    else:
        raise ValueError("%s imports from %s" % (file.rel, module))


def _signature(node, frame: "_Frame") -> list:
    """The defaults of a def, worked out as Python does when it runs the def, and its annotations checked alike."""
    args = node.args
    notes = [] if frame.file.future else [one.annotation for one in getattr(args, "posonlyargs", []) + args.args
                                          + args.kwonlyargs + [args.vararg, args.kwarg] if one and one.annotation]
    for one in notes + ([node.returns] if node.returns and not frame.file.future else []):
        frame.inert(one)
    return [frame.inert(one) for one in args.defaults + [d for d in args.kw_defaults if d is not None]]


def _classed(node, frame: "_Frame") -> None:
    """A class of the runner: bases of EXCEPTIONS, a body of defs alone, whose one decorator is contextlib's."""
    if node.decorator_list or node.keywords or not all(isinstance(b, ast.Name) and b.id in EXCEPTIONS
                                                       and b.id not in frame.file.bound for b in node.bases):
        raise ValueError("%s line %d: a class is not read" % (frame.file.rel, node.lineno))
    for one in node.body:
        if _docstring(one):
            continue
        if not isinstance(one, ast.FunctionDef) or any(repr(frame.inert(d)) != "contextlib.contextmanager"
                                                      or not isinstance(frame.inert(d), _Opaque) for d in one.decorator_list):
            raise ValueError("%s line %d: a class is not read" % (frame.file.rel, one.lineno))
        _signature(one, frame)
    frame.file.bound[node.name] = UNKNOWN


def _bind(target, value, bound: dict) -> None:
    """Bind a name, or a tuple of names, as an assignment does."""
    if isinstance(target, ast.Name):
        bound[target.id] = value
    elif isinstance(target, (ast.Tuple, ast.List)) and all(isinstance(one, ast.Name) for one in target.elts):
        if _plain(value) and len(list(value)) != len(target.elts):
            raise ValueError("an assignment unpacks the wrong number of values")
        parts = list(value) if isinstance(value, (tuple, list)) else [UNKNOWN] * len(target.elts)
        for one, part in zip(target.elts, parts):
            bound[one.id] = part
    else:
        raise ValueError("an assignment binds what is not a name")


def _plain(value) -> bool:
    """Whether `value` is worked out whole: no _Opaque, module or function at any depth."""
    if value is None or type(value) in (bool, int, float, complex, str, bytes, range, slice, type(...)):
        return True
    if type(value) in (tuple, list, type({}.keys()), type({}.values())):
        return all(_plain(one) for one in value)
    if type(value) in (dict, type({}.items())):
        return all(_plain(one) for one in (value.items() if type(value) is dict else value))
    return False


def _sized(value):
    if isinstance(value, (str, bytes, tuple, list)) and len(value) > BUDGET["length"]:
        raise ValueError("a value is longer than the reader builds")
    return value


class _Frame:
    """Where an expression is worked out: a file's top, or a function's call, whose `local` names `names` holds."""

    def __init__(self, file: _File, local: dict = None, names: frozenset = frozenset(), top: bool = True):
        self.file, self.local, self.names, self.top = file, local, names, top

    def name(self, name: str):
        if self.local is not None and name in self.names:
            if name not in self.local:
                raise ValueError("%s is read before it is bound" % name)
            return self.local[name]
        if name.startswith("__") and name != "__file__":
            raise ValueError("%s is not read" % name)
        if name in self.file.bound:
            return self.file.bound[name]
        if name in BUILTINS or name == "__file__":
            return _Opaque("builtins." + name)
        raise ValueError("%s: %s is not bound" % (self.file.rel, name))

    def inert(self, node):
        """A default, an annotation or a decorator: names, attributes, constants and tuples of them, which call nothing."""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Tuple):
            return tuple(self.inert(one) for one in node.elts)
        if isinstance(node, ast.Name):
            local = node.id not in self.file.bound and node.id in TYPES
            return _Opaque("builtins." + node.id) if local else self.name(node.id)
        if isinstance(node, ast.Attribute) and not node.attr.startswith("_"):
            held = self.inert(node.value)
            if isinstance(held, _Module) and node.attr in held:
                return held[node.attr]
            if isinstance(held, _Opaque) and (held.what, node.attr) in MODULE_VALUES:
                return _Opaque(held.what + "." + node.attr)
        raise ValueError("%s: a default, an annotation or a decorator calls or builds a value" % self.file.rel)

    def test(self, node):
        """Whether a test is true; None where it is not worked out, which at the top of a file is refused."""
        value = self.value(node)
        if _plain(value):
            return bool(value)
        if self.top:
            raise ValueError("%s: a test at the top is not worked out" % self.file.rel)
        return None

    def value(self, node):
        """What `node` evaluates to, as Python would; UNKNOWN where Python reads it from outside the text."""
        kind = type(node)
        if kind is ast.Constant:
            return node.value
        if kind is ast.Name:
            return self.name(node.id)
        if kind in (ast.Tuple, ast.List):
            out = []
            for one in node.elts:
                out += self.spread(one.value) if isinstance(one, ast.Starred) else [self.value(one)]
            return _sized(tuple(out) if kind is ast.Tuple else out)
        if kind is ast.Dict and None not in node.keys:
            keys = [self.value(one) for one in node.keys]
            values = [self.value(one) for one in node.values]
            return _real(lambda: dict(zip(keys, values))) if _plain(keys) else UNKNOWN
        if kind is ast.BinOp:
            return _operation(node.op, self.value(node.left), self.value(node.right))
        if kind is ast.UnaryOp and type(node.op) in (ast.USub, ast.Not):
            inner = self.value(node.operand)
            return UNKNOWN if not _plain(inner) else _real(lambda: -inner if type(node.op) is ast.USub else not inner)
        if kind is ast.Compare:
            return self.compared(node)
        if kind is ast.IfExp:
            test = self.test(node.test)
            return UNKNOWN if test is None else self.value(node.body if test else node.orelse)
        if kind is ast.Attribute:
            return self.attribute(self.value(node.value), node.attr)
        if kind is ast.Subscript:
            held, at = self.value(node.value), self.index(node.slice)
            return _real(lambda: held[at]) if _plain(held) and _plain(at) else UNKNOWN
        if kind is ast.ListComp:
            rounds = self.rounds(node)
            return UNKNOWN if rounds is None else _sized([inner.value(node.elt) for inner in rounds])
        if kind is ast.DictComp:
            rounds = self.rounds(node)
            if rounds is None:
                return UNKNOWN
            pairs = [(inner.value(node.key), inner.value(node.value)) for inner in rounds]
            return _real(lambda: dict(pairs)) if _plain([key for key, _ in pairs]) else UNKNOWN
        if kind is ast.Call:
            return self.called(node)
        raise ValueError("%s line %d: a %s is not read" % (self.file.rel, node.lineno, kind.__name__))

    def generated(self, node):
        """The items of a generator that is read once, whole, where it is made: given to tuple(), or looped over."""
        rounds = self.rounds(node)
        return UNKNOWN if rounds is None else _sized([inner.value(node.elt) for inner in rounds])

    def spread(self, node) -> list:
        """The parts `*node` gives a list or a tuple: those of a value worked out, or as many UNKNOWN as each return of
        the function it calls gives, when it returns a tuple of one fixed length."""
        value = self.value(node)
        if isinstance(value, (tuple, list)) or _plain(value):
            return _real(lambda: list(value))
        called = self.value(node.func) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) else None
        returns = [one.value for one in ast.walk(called.node) if isinstance(one, ast.Return)] \
            if isinstance(called, _Function) else []
        widths = {len(one.elts) for one in returns if isinstance(one, ast.Tuple)
                  and not any(isinstance(part, ast.Starred) for part in one.elts)}
        if not returns or len(widths) != 1 or not all(isinstance(one, ast.Tuple) for one in returns):
            raise ValueError("%s: a starred part is not worked out" % self.file.rel)
        return [UNKNOWN] * widths.pop()

    def compared(self, node):
        left = self.value(node.left)
        for op, right in zip(node.ops, node.comparators):
            right = self.value(right)
            if not (_plain(left) and _plain(right)):
                return UNKNOWN
            if not _real(lambda: COMPARE[type(op)](left, right)):
                return False
            left = right
        return True

    def attribute(self, held, attr: str):
        if attr.startswith("_"):
            raise ValueError("%s: .%s is not read" % (self.file.rel, attr))
        if isinstance(held, _Module) and attr in held:
            return held[attr]
        if attr in ATTRIBUTES:
            return _real(lambda: getattr(held, attr)) if _plain(held) else UNKNOWN
        if isinstance(held, _Opaque) and (held.what, attr) in MODULE_VALUES:
            return _Opaque(held.what + "." + attr)
        raise ValueError("%s: .%s is not read" % (self.file.rel, attr))

    def index(self, node):
        if isinstance(node, ast.Slice):
            parts = [None if one is None else self.value(one) for one in (node.lower, node.upper, node.step)]
            return slice(*parts) if _plain(parts) else UNKNOWN
        return self.value(node)

    def rounds(self, node):
        """A frame for each round of a comprehension's loops that its conditions keep; None where its loops or its
        conditions are not worked out, which at the top of a file is refused."""
        rounds = [self]
        for loop in node.generators:
            after = []
            for inner in rounds:
                over = inner.generated(loop.iter) if isinstance(loop.iter, ast.GeneratorExp) else inner.value(loop.iter)
                if not (type(over) in (tuple, list) or _plain(over)) or loop.is_async:
                    if self.top:
                        raise ValueError("%s: a loop at the top is not worked out" % self.file.rel)
                    return None
                for item in _real(lambda: list(over)):
                    self.file.read.rounds += 1
                    if self.file.read.rounds > BUDGET["rounds"]:
                        raise ValueError("the mutants take more rounds than the reader runs")
                    local = dict(inner.local or {})
                    _bind(loop.target, item, local)
                    one = _Frame(self.file, local, inner.names | set(local), self.top)
                    kept = [one.test(test) for test in loop.ifs]
                    if None in kept:
                        return None
                    if all(kept):
                        after.append(one)
            rounds = after
        return rounds

    def called(self, node):
        func = node.func
        if any(isinstance(one, ast.Starred) for one in node.args) or \
                any(k.arg is not None for k in node.keywords) or node.keywords and getattr(func, "id", "") != "dict":
            raise ValueError("%s line %d: a call is not read" % (self.file.rel, node.lineno))
        if isinstance(func, ast.Attribute):
            return self.method(node, self.value(func.value), func.attr)
        if not isinstance(func, ast.Name):
            raise ValueError("%s line %d: a call is not read" % (self.file.rel, node.lineno))
        called = self.name(func.id)
        if isinstance(called, _Opaque) and called.what == "builtins.tuple" and len(node.args) == 1 \
                and isinstance(node.args[0], ast.GeneratorExp):
            made = self.generated(node.args[0])
            return made if made is UNKNOWN else tuple(made)
        args = [self.value(one) for one in node.args] + [self.value(k.value) for k in node.keywords]
        if isinstance(called, _Opaque) and called.what in ("builtins." + name for name in BUILTINS):
            if not _plain(args) or called.what == "builtins.iter":
                return UNKNOWN      # an iterator changes as it is read: what reads it is not worked out
            if called.what == "builtins.dict" and len(node.args) <= 1:
                return _merged(args[:len(node.args)], args[len(node.args):])
            if called.what != "builtins.dict" and not node.keywords:
                return _sized(_real(lambda: {"len": len, "range": range, "tuple": tuple}[called.what[9:]](*args)))
        if isinstance(called, _Function) and _pinned(called, "areas") and self.file.rel == "tools/mutants.py" \
                and self.top and len(args) == 1 and args[0] is self.file.bound.get("ROOT"):
            return _areas(self.file, called)
        if isinstance(called, _Function) and not node.keywords:
            return _ran(called, args)
        raise ValueError("%s line %d: %s is called" % (self.file.rel, node.lineno, func.id))

    def method(self, node, held, attr: str):
        args = [self.value(one) for one in node.args]
        if isinstance(held, _Opaque) and (held.what, attr) in MODULE_CALLS:
            return UNKNOWN
        if attr == "replace" and self.top and type(held) is str and len(args) in (2, 3) \
                and type(args[0]) is type(args[1]) is str and all(type(one) is int for one in args[2:]):
            if len(held) + (held.count(args[0]) + 1) * len(args[1]) > BUDGET["length"]:
                raise ValueError("a value is longer than the reader builds")
            return held.replace(*args)
        if attr not in METHODS or isinstance(held, (_Module, _Function)) or isinstance(held, _Opaque) and held.what in MODULES:
            raise ValueError("%s line %d: .%s is called" % (self.file.rel, node.lineno, attr))
        if not (_plain(held) and _plain(args)):
            return UNKNOWN
        return _sized(_real(lambda: getattr(held, attr)(*args)))


COMPARE = {ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b, ast.Lt: lambda a, b: a < b,
           ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
           ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b, ast.Is: lambda a, b: a is b,
           ast.IsNot: lambda a, b: a is not b}


def _merged(given: list, spread: list) -> dict:
    """`dict(given, **one, **two)` as Python builds it: a spread key that is not a str, or that two spreads give, raises."""
    out = _real(lambda: dict(*given))
    seen = set()
    for one in spread:
        if type(one) is not dict or not all(type(key) is str and key not in seen for key in one):
            raise ValueError("dict() is given what Python refuses")
        seen |= set(one)
        out.update(one)
    return out


def _real(work):
    """What Python gives for an operation on values worked out whole; whatever it raises, it is refused."""
    try:
        return work()
    except Exception as err:    # noqa: BLE001 -- where Python would raise, the file cannot be read
        raise ValueError("an operation raises %s" % type(err).__name__)


def _operation(op, left, right):
    """`left op right`, as Python works it out, within the reader's budget; UNKNOWN for a value not worked out. Two
    tuples or two lists are joined whatever they hold, which the join does not read."""
    if type(op) is ast.Add and type(left) is type(right) and type(left) in (tuple, list):
        if len(left) + len(right) > BUDGET["length"]:
            raise ValueError("a value is longer than the reader builds")
        return left + right
    if not (_plain(left) and _plain(right)):
        return UNKNOWN
    if type(op) is ast.Mod and isinstance(left, str):
        for width in FORMAT.finditer(left):
            if "*" in width.group(0) or any(part and int(part) > BUDGET["width"] for part in width.groups()):
                raise ValueError("a format is wider than the reader builds")
    if type(op) is ast.Pow and not (type(left) is type(right) is int and 0 <= right <= 64 and abs(left) < 2 ** 64):
        raise ValueError("a power is larger than the reader works out")
    if type(op) is ast.Mult:
        sizes = [len(one) for one in (left, right) if isinstance(one, (str, bytes, tuple, list))]
        counts = [one for one in (left, right) if type(one) is int]
        if sizes and counts and sizes[0] * max(counts[0], 0) > BUDGET["length"] or \
                len(counts) == 2 and counts[0].bit_length() + counts[1].bit_length() > 4096:
            raise ValueError("a product is larger than the reader works out")
    if type(op) is ast.Add and isinstance(left, (str, bytes, tuple, list)) and isinstance(right, (str, bytes, tuple, list)):
        if len(left) + len(right) > BUDGET["length"]:
            raise ValueError("a value is longer than the reader builds")
    return _sized(_real(lambda: OPERATIONS[type(op)](left, right)))


OPERATIONS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
              ast.Div: lambda a, b: a / b, ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
              ast.Pow: lambda a, b: a ** b}


def _pinned(function: _Function, name: str) -> bool:
    return function.node.name == name and function.source == PINNED[name]


def _areas(file: _File, areas: _Function) -> tuple:
    """What `areas(ROOT)` loads, as PINNED writes it: the files of mutants, in the order of their names."""
    bound = file.bound
    if not (isinstance(bound.get("area_names"), _Function) and _pinned(bound["area_names"], "area_names")
            and isinstance(bound.get("AREA_NAME"), _Opaque) and bound["AREA_NAME"].what == "AREA_NAME"
            and isinstance(bound.get("walk"), _Opaque) and bound["walk"].what == "tools.walk"
            and len(areas.defaults) == 1 and isinstance(areas.defaults[0], _Opaque)
            and areas.defaults[0].what == "importlib.import_module"):
        raise ValueError("areas(ROOT) is not read as PINNED writes it")
    return tuple(file.read.loaded(path.stem) for path in _mutant_files(file.read.root)[1:]
                 if path.stem not in ("__init__", "common"))


def _safe(node, file: _File) -> None:
    """Refuse a function the reader may not run: one whose body could change a value or reach outside on any path, or
    whose arguments are not positional alone. Each function it calls by name is checked alike."""
    if id(node) in file.safe:
        return
    file.safe.add(id(node))
    args = node.args
    if node.decorator_list or args.vararg or args.kwarg or args.kwonlyargs or args.defaults \
            or getattr(args, "posonlyargs", []):
        raise ValueError("%s: %s takes what the reader does not give" % (file.rel, node.name))
    local = {one.arg for one in args.args} | {one.id for one in ast.walk(node) if isinstance(one, ast.Name)
                                               and isinstance(one.ctx, ast.Store)}
    for one in ast.walk(node):
        if isinstance(one, ast.stmt) and one is not node and not (
                _docstring(one) or isinstance(one, ast.If) or isinstance(one, ast.Return) and one.value is not None
                or isinstance(one, ast.Assign) and all(isinstance(t, ast.Name) or isinstance(t, ast.Tuple) and all(
                    isinstance(e, ast.Name) for e in t.elts) for t in one.targets)):
            raise ValueError("%s line %d: %s is not run by the reader" % (file.rel, one.lineno, node.name))
    calls = {id(one.func) for one in ast.walk(node) if isinstance(one, ast.Call)}
    tupled = {id(one.args[0]) for one in ast.walk(node) if isinstance(one, ast.Call)
              and getattr(one.func, "id", "") == "tuple" and len(one.args) == 1} | \
        {id(one.iter) for one in ast.walk(node) if isinstance(one, ast.comprehension)}
    for one in ast.walk(node):
        if isinstance(one, (ast.stmt, ast.arguments, ast.arg)):
            continue
        bad = not isinstance(one, EXPRESSIONS) \
            or isinstance(one, ast.Name) and one.id.startswith("__") \
            or isinstance(one, (ast.Attribute, ast.Subscript)) and not isinstance(one.ctx, ast.Load) \
            or isinstance(one, ast.Attribute) and not (one.attr in ATTRIBUTES or one.attr in METHODS and id(one) in calls) \
            or isinstance(one, ast.GeneratorExp) and id(one) not in tupled \
            or isinstance(one, ast.Dict) and None in one.keys \
            or isinstance(one, ast.comprehension) and one.is_async \
            or isinstance(one, ast.Call) and _unsafe_call(one, local, file)
        if bad:
            raise ValueError("%s line %d: %s is not run by the reader" % (file.rel, getattr(one, "lineno", node.lineno),
                                                                          node.name))


def _unsafe_call(node, local: set, file: _File) -> bool:
    """Whether a call in a function may reach what the reader does not run: anything but a method of METHODS, a name
    of BUILTINS the file leaves unbound, or a def bound once at the top of the file, itself checked."""
    if any(isinstance(one, ast.Starred) for one in node.args) or node.keywords:
        return True
    if isinstance(node.func, ast.Attribute):
        return False
    name = getattr(node.func, "id", None)
    if name is None or name in local:
        return True
    if name in BUILTINS:
        return name in file.names
    if name not in file.defs:
        return True
    _safe(file.defs[name], file)
    return False


def _ran(function: _Function, args: list):
    """What a function returns, run by the reader: UNKNOWN from the first test it does not work out."""
    read, node = function.file.read, function.node
    _safe(node, function.file)
    if len(args) != len(node.args.args):
        raise ValueError("%s is called with %d arguments" % (node.name, len(args)))
    read.calls += 1
    if read.calls > BUDGET["calls"] or read.depth >= BUDGET["depth"]:
        raise ValueError("the mutants take more calls than the reader runs")
    names = frozenset(one.id for one in ast.walk(node) if isinstance(one, ast.Name) and isinstance(one.ctx, ast.Store))
    frame = _Frame(function.file, {one.arg: value for one, value in zip(node.args.args, args)},
                   names | {one.arg for one in node.args.args}, top=False)
    read.depth += 1
    try:
        out = _steps(node.body[1:] if node.body and _docstring(node.body[0]) else node.body, frame)
    finally:
        read.depth -= 1
    return None if out is _ON else out


_ON = _Opaque("ON")      # what a run of statements gives when none of them returns


def _steps(body: list, frame: _Frame):
    """Run a function's statements: what one returns, else _ON; UNKNOWN from a test not worked out."""
    for node in body:
        if isinstance(node, ast.Return):
            return frame.value(node.value)
        if isinstance(node, ast.Assign):
            value = frame.value(node.value)
            for target in node.targets:
                _bind(target, value, frame.local)
            continue
        test = frame.test(node.test)
        if test is None:
            return UNKNOWN
        out = _steps(node.body if test else node.orelse, frame)
        if out is not _ON:
            return out
    return _ON


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
