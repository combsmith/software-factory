"""The Kernel does no I/O and keeps nothing between calls. Asserted from its syntax tree, not from trust.

It is strict by allowing little: a Kernel module holds a docstring, imports, constants and
functions, and nothing else. That is narrower than Python, on purpose. It assigns no attribute, so
no module changes another's names. The brakes and the gate, each a protected path alone, import
only what CONFINED allows, and no module binds a name either of them owns but as its own. It calls
no function it is given but the parameters CALLABLE_PARAMETERS names, and on a value only the built-in
types' methods BUILTIN_METHODS names, so that no function handed in can read the world for it. It calls a module only
at a function the module defines or imports, raises nothing and names no special name, and where Python would
import another module than the one it reads, it refuses that (issue 593). It writes no function into text, by `str`,
an f-string or `%`, which would give its address in memory (issue 1137). That mark assumes good faith, as decision
0215's limit row says: a function reached through another name, a container or a parameter is for review.
"""
from __future__ import annotations

import ast
import pathlib
import re

from tools import walk

ROOT = pathlib.Path(__file__).resolve().parent.parent
# `typing` is not among them: it reaches `sys` and an `eval` of its own, and the Kernel needs none of it (issue 588).
ALLOWED_IMPORTS = {"__future__", "kernel"}
FORBIDDEN_NAMES = {"open", "print", "input", "exec", "eval", "__import__", "compile", "globals", "locals", "vars",
                   "getattr", "setattr", "delattr", "__builtins__", "breakpoint", "callable", "iter",
                   # site's builtins, each of which reads a file, starts the help system or ends the process as a value
                   # it is handed, `str(license)` among them (issue 909).
                   "license", "copyright", "credits", "help", "exit", "quit"}
# The statements that call a method of a value they are handed: `__enter__` and `__exit__`, `__await__`, the iterator
# `yield from` drives, and `assert`, which raises (issue 909). A `for` over a value is not among them: what the Kernel
# loops over is a fact, a list or a dictionary, and so is what it hands `next()` or `len()`: the line is drawn at the
# statements, which a fact never needs.
HANDLING = {ast.With: "enters what it is handed", ast.AsyncWith: "enters what it is handed",
            ast.Await: "awaits what it is handed", ast.YieldFrom: "drives what it is handed",
            ast.Assert: "raises", ast.AsyncFor: "drives what it is handed"}
# What a module may hold at its top level: a value that cannot change after import.
CONSTANT_CALLS = {"frozenset"}
# The calendar, which nobody chooses, and so the only numbers but 0 and 1 the Kernel may write: each a constant of
# kernel/terms.py, under this name, with exactly this value. Any other number is a limit, and a limit is data.
CALENDAR = {"SECONDS_PER_MINUTE": 60, "MINUTES_PER_HOUR": 60, "HOURS_PER_DAY": 24, "DAYS_PER_YEAR": 365,
            "LEAP_YEARS": (4, 100, 400), "FEBRUARY": 2,
            "DAYS_BEFORE_MONTH": (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)}
# The modules protected alone (config/hooks.json), and the Kernel modules each may import: the gate none, the brakes
# the codes alone. What they decide cannot then be changed from a module that is not protected.
CONFINED = {"gate.py": frozenset(), "brakes.py": frozenset({"kernel.terms"})}
# The parameters a Kernel function may call: Admission's maker of a Decision, `decide.py`'s `_decision`. Only a function
# at a module's top takes one, it is only ever called, and what fills one is a function of the Kernel's or the caller's
# own parameter of that name, so nothing handed in is called through it. Any other value a function is given, or
# binds, it never calls: the Kernel is given values, not ways to get them.
CALLABLE_PARAMETERS = frozenset({"_decision"})
# The modules a rule above names by its file. A package held as the Kernel is names no module of its own so, or a rule
# written for the Kernel's module would be read of it: the calendar's numbers allowed in a `terms.py` that is not the
# Kernel's.
KEYED = frozenset(CONFINED) | {"terms.py"}
# The methods the Kernel calls on a value, each a built-in type's, by its exact name: a method of another name is the
# value's own, which may do anything. A name is added here only as the Kernel needs it.
BUILTIN_METHODS = frozenset({"append", "casefold", "count", "endswith", "find", "fromkeys", "get", "items", "join",
                             "partition", "pop", "rstrip", "split", "startswith", "update", "values"})
# The builtins the Kernel may call, each by its exact name: those it calls on main, and map and filter, whose first
# argument is held as `key=` is. Any other, such as `__build_class__`, may call what it is handed or reach past the
# Kernel. A name is added here only as the Kernel needs it.
BUILTIN_CALLS = frozenset({"abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "frozenset", "int",
                           "isinstance", "len", "list", "map", "max", "min", "next", "range", "set", "sorted", "str",
                           "sum", "tuple", "type", "zip"})
# The builtins that call what they are handed as their first argument. Any call calls what it is handed as `key=`, and
# nothing is spread into a builtin that calls what it is handed, so that what it is handed is read. `iter` given a
# sentinel calls its first argument too, and is forbidden with `callable`.
CALLING_BUILTINS = frozenset({"map", "filter"})
KEYED_BUILTINS = frozenset({"map", "filter", "sorted", "max", "min"})
# The builtins never handed to be called: each calls what it is then given, `type` given three as a class's bases, so
# `map(map, [f], [xs])` would call f unread (issue 593).
UNHANDED_BUILTINS = frozenset({"map", "filter", "type"})
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _special(node) -> list:
    """The special names, written `__x__`, that a node holds: any name in it, but a constant's value. Through one a
    module's names are rewritten, as by `__dict__`, or a name is handed back that no module binds, as by a module's
    `__getattr__`; the Kernel names none (issue 593). An import's names are read with it, so that a problem has its
    line, and `__future__`, the module an absolute `from __future__ import` names, is the one allowed: a relative one
    names a module of the Kernel's (issue 600)."""
    if isinstance(node, (ast.Constant, ast.alias)):
        return []
    words = []
    for field, value in ast.iter_fields(node):
        for part in value if isinstance(value, list) else [value]:
            if isinstance(part, ast.alias):
                part = part.name + "." + (part.asname or "")
            if isinstance(part, str) and not (field == "module" and part == "__future__" and not node.level):
                words += part.split(".")
    return [w for w in words if len(w) > 4 and w.startswith("__") and w.endswith("__")]


def _assigned(node) -> list:
    """The names an assignment at a module's top binds, each element of a tuple or list it unpacks into among them."""
    targets = list(getattr(node, "targets", [getattr(node, "target", None)]))
    names = []
    while targets:
        target = targets.pop(0)
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            targets += target.elts
    return names


def _shaped(target, value) -> bool:
    """Whether an assignment at a module's top binds names alone, and unpacks into a tuple or list of them only a tuple
    written out with as many elements, each of its own shape: so that no starred name keeps a list, and no name is a
    set's element in an order the hash seed picks. A list written out is a value that can change, refused before."""
    if isinstance(target, ast.Name):
        return True
    return (isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, ast.Tuple)
            and len(target.elts) == len(value.elts) and all(_shaped(t, v) for t, v in zip(target.elts, value.elts)))


def _top_names(tree) -> set:
    """The names a module binds at its top: a function's, an assignment's, an import's."""
    return {word for node in tree.body for word in _bound(node) + _assigned(node)
            + ([alias.asname or alias.name.split(".")[0] for alias in node.names]
               if isinstance(node, (ast.Import, ast.ImportFrom)) else [])}


def _answered(name: str, node, word: str, read: set, bound: dict, hidden=lambda parts: False) -> bool:
    """Whether `from <module> import word` in the file `name` is answered by what is read here: `word` is a module of
    the package read, or a name its module's file binds at its top (issue 909). A relative import is read from the
    file's own folder; one that climbs past the package is another rule's. Neither the module nor `word` may be a
    folder that is `hidden`, there with its `__init__.py` unread: Python imports that folder before a file of its
    name, or a name its module binds by importing it."""
    folder = name.split("/")[:-1]
    if node.level:
        if node.level - 1 > len(folder):
            return True
        parts = folder[:len(folder) - (node.level - 1)] + (node.module.split(".") if node.module else [])
    else:
        parts = node.module.split(".")[1:]
    module = ["/".join(parts + ["__init__.py"]).lstrip("/"), "/".join(parts) + ".py"]
    inner = "/".join(parts + [word])
    if word != "*" and (hidden(parts) or hidden(parts + [word])):
        return False
    return (word == "*" or inner + ".py" in read or inner + "/__init__.py" in read
            or any(word in bound.get(m, ()) for m in module))


def _constant(node, held: frozenset = frozenset()) -> bool:
    """Whether `node` is a value that cannot change after import: a constant, a tuple of them, or a call of
    CONSTANT_CALLS whose arguments call nothing but another such call and name nothing but `held`, the names bound at
    the module's top (less, for a default inside a function, those the function may bind; `_scopes`), and attributes
    of them: so that no list a generator yields, and no local value, is kept in it (issue 909). Each node is read
    once."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Tuple):
        return all(_constant(e, held) for e in node.elts)
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in CONSTANT_CALLS
            and not any(k.arg is None for k in node.keywords)
            and all(_inert(argument, held) for argument in node.args + [k.value for k in node.keywords]))


def _scopes(tree, held: frozenset) -> dict:
    """The names a default may name, by the id of each function or lambda: `held` for one at the module's top, whose
    defaults the module's top evaluates; for one inside another, `held` less every name bound anywhere in the statement
    at the top that holds it, as its defaults are evaluated where such a name may be a local (issue 909)."""
    scopes = {}
    for top in tree.body:
        inner = frozenset(word for node in ast.walk(top) for word in _bound(node) + (
            [alias.asname or alias.name.split(".")[0] for alias in node.names]
            if isinstance(node, (ast.Import, ast.ImportFrom)) else []))
        for node in ast.walk(top):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                scopes[id(node)] = held if node is top else held - inner
    return scopes


def _inert(node, held: frozenset) -> bool:
    """Whether `node`, in a constant's argument, evaluates to a value that cannot change: it calls nothing but a
    constant's own call, binds nothing, iterates nothing, an unpacking of either kind among it, formats nothing into
    text, which could write a set's order there, and names only `held`, read once each."""
    if isinstance(node, ast.Call):
        return _constant(node, held)
    if isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.DictComp, ast.NamedExpr, ast.Yield,
                         ast.YieldFrom, ast.Starred, ast.JoinedStr)):
        return False
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) or isinstance(node, ast.Dict) and None in node.keys:
        return False
    if isinstance(node, ast.Name):
        return node.id in held
    return all(_inert(child, held) for child in ast.iter_child_nodes(node)
               if not isinstance(child, ast.expr_context))


def _pinned(name: str, node) -> bool:
    """Whether `node` is the one form a calendar unit is written in: at the top of terms.py, alone, at its value."""
    if not (name == "terms.py" and isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name) and node.targets[0].id in CALENDAR):
        return False
    try:
        value = ast.literal_eval(node.value)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False
    return repr(value) == repr(CALENDAR[node.targets[0].id])


def _calendar(name: str, tree) -> tuple:
    """(the numbers in `tree` that are the calendar's, as ids of their nodes; the problems with how it is written).

    Each unit is assigned once, in its pinned form. Any other assignment to its name, a second one to 0, 1 or True
    among them, or to an attribute of that name anywhere in the Kernel, is a problem: it would change the unit.
    """
    out, problems, seen = set(), [], set()
    pinned = {id(node) for node in tree.body if _pinned(name, node)}
    for node in ast.walk(tree):
        if id(node) in pinned and node.targets[0].id not in seen:
            seen.add(node.targets[0].id)
            out |= {id(n) for n in ast.walk(node.value)}
            continue
        targets = node.targets if isinstance(node, ast.Assign) else \
            [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr, ast.For)) else []
        for target in targets:
            for part in ast.walk(target):
                unit = part.id if isinstance(part, ast.Name) else part.attr if isinstance(part, ast.Attribute) else None
                if unit in CALENDAR and isinstance(part.ctx, ast.Store):
                    problems.append("%s:%d assigns %s, a unit of the calendar: it is written once, in terms.py, as "
                                    "tools/check_purity.py pins it" % (name, node.lineno, unit))
    return out, problems


def _kernel_imports(node) -> list:
    """The Kernel modules an import names, as `kernel.<module>`; a relative import is named as written."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names if alias.name.split(".")[0] == "kernel"]
    if node.level:
        return ["." * node.level + (node.module or "")]
    if node.module == "kernel":
        return ["kernel." + alias.name for alias in node.names]
    return [node.module] if (node.module or "").split(".")[0] == "kernel" else []


def _defined(name: str, tree) -> set:
    """The names a confined module owns: its own name, and the functions and constants it defines at its top level."""
    out = {name[:-len(".py")]}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out.add(node.name)
        for target in node.targets if isinstance(node, ast.Assign) else \
                [node.target] if isinstance(node, ast.AnnAssign) else []:
            out |= {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}
    return out


def _bindings(tree) -> list:
    """(line, name, (import, alias) or None) for every name a module binds, at any depth: a definition, a parameter, an
    assignment or any other target, a name an exception or a pattern is caught as, and an import."""
    out = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append((line, node.name, None))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            given = node.args
            out += [(line, arg.arg, None) for arg in given.posonlyargs + given.args + given.kwonlyargs +
                    [a for a in (given.vararg, given.kwarg) if a is not None]]
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            out.append((line, node.id, None))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            out += [(line, alias.asname or alias.name.split(".")[0], (node, alias)) for alias in node.names]
        elif isinstance(node, ast.ExceptHandler) or type(node).__name__.startswith("Match"):
            out += [(line, getattr(node, field), None) for field in ("name", "rest")
                    if isinstance(getattr(node, field, None), str)]
    return out


def _brought(imported: tuple, word: str, owner: str) -> bool:
    """Whether an import binds `word` to the owner's own: `from kernel.gate import gates`, `from kernel import gate`,
    or `import kernel.gate as gate`. Any other binding of that name stands in for it."""
    node, alias = imported
    stem = owner[:-len(".py")]
    if isinstance(node, ast.Import):
        return alias.name == "kernel." + stem and alias.asname == stem == word
    if node.level:
        return False
    if node.module == "kernel":
        return alias.name == stem == word and alias.asname in (None, stem)
    return node.module == "kernel." + stem and alias.asname is None and alias.name == word


def _confined(name: str, tree, owned: dict) -> list:
    """What a module does that could change the brakes or the gate from outside them: in either of them, an import of
    the Kernel beyond what CONFINED allows; in any module, a binding of a name either owns, but its own definitions in
    the module that owns it, and an import of the owner's own from another."""
    problems = []
    if name in CONFINED:
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for mod in _kernel_imports(node):
                    if mod not in CONFINED[name]:
                        problems.append("%s:%d imports %s; %s imports %s of the Kernel" % (
                            name, node.lineno, mod, name, " and ".join(sorted(CONFINED[name])) or "nothing"))
    for line, word, imported in _bindings(tree):
        for owner, names in sorted(owned.items()):
            if word not in names:
                continue
            if (owner == name and imported is None) or (owner != name and imported and _brought(imported, word, owner)):
                continue
            problems.append("%s:%d binds %s, which %s owns; use that one, so that what %s decides is changed only "
                            "there" % (name, line, word, owner, owner))
    return problems


def _own(fn) -> list:
    """The nodes of a function's body that are its own: none inside a function it defines, but that function's node
    and what Python reads of it where it is defined, its decorators, defaults and annotations."""
    out, todo = [], list(fn.body) if isinstance(fn.body, list) else [fn.body]
    while todo:
        node = todo.pop()
        out.append(node)
        if not isinstance(node, FUNCTIONS):
            todo.extend(ast.iter_child_nodes(node))
        else:
            todo.extend(getattr(node, "decorator_list", []) + [node.args] + ([node.returns] if getattr(node, "returns", None) else []))
    return out


def _file(dotted: str, trees: dict):
    """The file under kernel/ that a dotted name of the Kernel's is, as `run` names it: a module, or a package's
    __init__.py; None for a name that is neither."""
    parts = dotted.split(".")[1:]
    for key in (("/".join(parts) + ".py") if parts else None, "/".join(parts + ["__init__.py"])):
        if key in trees:
            return key
    return None


def _imported(name: str, node, alias, trees: dict) -> tuple:
    """(the file, and the function's name or None for the module itself) that an import of the Kernel binds, read as
    Python reads it from the module `name`, relative or not; (None, None) for any other import, and a None file for a
    name of the Kernel's that is no file."""
    if isinstance(node, ast.Import):
        return (_file(alias.name, trees), None) if alias.name.split(".")[0] == "kernel" else (None, None)
    if node.level:
        package = ["kernel"] + name.split("/")[:-1]
        package = package[:len(package) - node.level + 1] if node.level <= len(package) else []
        dotted = ".".join(package + ([node.module] if node.module else []))
    else:
        dotted = node.module or ""
    if dotted.split(".")[0] != "kernel":
        return None, None
    module = _file(dotted + "." + alias.name, trees)
    return (module, None) if module else (_file(dotted, trees), alias.name)


def _names(name: str, scope, trees: dict) -> dict:
    """What a module, or a function, binds each of its own names to: ("parameter", None); ("function", None) for a
    function it defines, or a lambda it assigns to the name, and no other binding; ("import", what `_imported` reads);
    or ("value", None) for anything else, and for a name bound more than one of these ways."""
    kinds = {}

    def bind(word, kind):
        kinds[word] = kind if kinds.get(word, kind) == kind else ("value", None)
    if isinstance(scope, ast.Module):
        own = list(scope.body)
        own += [n for top in scope.body if not isinstance(top, FUNCTIONS) for n in ast.walk(top)]
        # What Python reads of a function where it is defined binds in the module: a walrus in a default, say.
        own += [n for top in scope.body if isinstance(top, FUNCTIONS)
                for part in top.decorator_list + [top.args] + ([top.returns] if top.returns else []) for n in ast.walk(part)]
    else:
        given = scope.args
        for arg in given.posonlyargs + given.args + given.kwonlyargs + [a for a in (given.vararg, given.kwarg) if a]:
            bind(arg.arg, ("parameter", None))
        own = _own(scope)
    lambdas = set()
    for node in own:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Lambda):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) == 1 and isinstance(targets[0], ast.Name):
                lambdas.add(id(targets[0]))
                bind(targets[0].id, ("function", None))
    for node in own:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bind(node.name, ("function", None) if not isinstance(node, ast.ClassDef) else ("value", None))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)) and id(node) not in lambdas:
            bind(node.id, ("value", None))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bind(alias.asname or alias.name.split(".")[0], ("import", _imported(name, node, alias, trees)))
        elif isinstance(node, ast.ExceptHandler) or type(node).__name__.startswith("Match"):
            for field in ("name", "rest"):
                if isinstance(getattr(node, field, None), str):
                    bind(getattr(node, field), ("value", None))
    return kinds


def _takers(trees: dict) -> dict:
    """{(module key, function): (its positional parameters, the parameters it takes by keyword)} for each function at
    a module's top that takes a parameter CALLABLE_PARAMETERS names. A positional-only one is not taken by keyword."""
    out = {}
    for name, tree in trees.items():
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                given = node.args
                positional = [a.arg for a in given.posonlyargs + given.args]
                keyword = [a.arg for a in given.args + given.kwonlyargs]
                if CALLABLE_PARAMETERS & set(positional + keyword):
                    out[(name, node.name)] = (positional, keyword)
    return out


def _calls(name: str, tree, trees: dict, takers: dict, tops: dict) -> list:
    """What a module calls that it was handed, or binds, or that is a value's own method; and each place a parameter
    CALLABLE_PARAMETERS names is taken, named or filled other than as that constant's comment says. `tops` is what
    each module binds at its top, as `_names` reads it, so that a name one module imports from another is followed."""
    problems, callees, bases, top = [], set(), set(), tops[name]

    def resolve(word, chain):
        """(kind, detail, whether a function binds it) for a name as `chain`, innermost first, reads it."""
        for _, kinds in chain:
            if word in kinds:
                return kinds[word] + (True,)
        return top.get(word, ("builtin", None)) + (False,)

    def module_file(node, chain):
        """The file of the Kernel's module an expression names, by a name or as a module's attribute, followed through
        each module that imports it, or None."""
        outer = module_file(node.value, chain) if isinstance(node, ast.Attribute) else None
        if isinstance(node, ast.Name):
            kind, detail, _ = resolve(node.id, chain)
        elif outer:
            kind, detail = tops.get(outer, {}).get(node.attr, (None, None))
        else:
            return None
        seen = set()
        while kind == "import" and detail[0] is not None and detail not in seen:
            if detail[1] is None:
                return detail[0]
            seen.add(detail)
            kind, detail = tops.get(detail[0], {}).get(detail[1], (None, None))
        return None

    def module(node, chain) -> bool:
        """Whether an expression names a module of the Kernel's."""
        return module_file(node, chain) is not None

    def origin(target):
        """The function a (file, name) is, followed through each module that imports it under that name; None where
        it is no function at a Kernel module's top."""
        seen = set()
        while target not in seen:
            seen.add(target)
            kind, detail = tops.get(target[0], {}).get(target[1], (None, None))
            if kind == "function":
                return target
            if kind != "import" or not (detail[0] and detail[1]):
                return None
            target = detail
        return None

    def kernel_function(node, chain):
        """The (file, function) a name or a module's attribute is, at a module's top in the Kernel, or None."""
        if isinstance(node, ast.Name):
            kind, detail, local = resolve(node.id, chain)
            if kind == "function" and not local:
                return name, node.id
            if kind == "import" and detail[0] and detail[1]:
                return origin(detail)
        if isinstance(node, ast.Attribute) and module(node.value, chain):
            return origin((module_file(node.value, chain), node.attr))
        return None

    def handed(node, chain) -> bool:
        """Whether what an expression gives to be called is not what the Kernel may call: a lambda, a function it
        defines or imports, a builtin, or a method BUILTIN_METHODS names."""
        if isinstance(node, ast.Lambda):
            return False
        if isinstance(node, ast.Name):
            kind = resolve(node.id, chain)[0]
            if kind == "import":
                return kernel_function(node, chain) is None
            return kind in ("parameter", "value") or (kind == "builtin" and (node.id not in BUILTIN_CALLS or
                                                                            node.id in UNHANDED_BUILTINS))
        if isinstance(node, ast.Attribute):
            if module(node.value, chain):
                return kernel_function(node, chain) is None
            return node.attr not in BUILTIN_METHODS
        return True

    def call(node, chain):
        line, f = node.lineno, node.func
        callees.add(id(f))
        if isinstance(f, ast.Name):
            kind = resolve(f.id, chain)[0]
            if kind == "parameter" and f.id not in CALLABLE_PARAMETERS:
                problems.append("%s:%d calls %s, which it is given; the Kernel is given values, not ways to get them, "
                                "and calls no parameter but %s" % (name, line, f.id, ", ".join(sorted(CALLABLE_PARAMETERS))))
            elif kind == "value":
                problems.append("%s:%d calls %s, a value it binds; the Kernel calls only the functions it defines or "
                                "imports, and the builtins" % (name, line, f.id))
            elif kind == "import" and kernel_function(f, chain) is None and not module(f, chain):
                problems.append("%s:%d calls %s, which it imports but is no function of the Kernel's that can be read"
                                % (name, line, f.id))
            elif kind == "builtin" and f.id not in BUILTIN_CALLS:
                problems.append("%s:%d calls %s, a builtin BUILTIN_CALLS does not name; a builtin may call what it is "
                                "handed or reach past the Kernel" % (name, line, f.id))
            elif kind == "builtin" and f.id == "type" and not (len(node.args) == 1 and not node.keywords and
                                                                not isinstance(node.args[0], ast.Starred)):
                problems.append("%s:%d calls type with other than one argument written out, which makes a class and "
                                "calls what it is given as a base; the Kernel asks type of one value only" % (name, line))
        elif isinstance(f, ast.Attribute):
            if module(f.value, chain) and kernel_function(f, chain) is None:
                problems.append("%s:%d calls %s, which is no function of that module's; a module of the Kernel's is "
                                "called into only at a function it defines or imports" % (name, line, ast.unparse(f)))
            elif not module(f.value, chain) and f.attr not in BUILTIN_METHODS:
                problems.append("%s:%d calls the method %s, which is not a built-in type's that BUILTIN_METHODS names; "
                                "a value's own method may do anything" % (name, line, f.attr))
        else:
            problems.append("%s:%d calls what an expression gives; the Kernel calls a function by its name"
                            % (name, line))
        builtin = isinstance(f, ast.Name) and resolve(f.id, chain)[0] == "builtin"
        if builtin and f.id in KEYED_BUILTINS and (any(isinstance(a, ast.Starred) for a in node.args) or
                                                   any(kw.arg is None for kw in node.keywords)):
            problems.append("%s:%d spreads its arguments into %s, which calls what it is handed; what it is handed is "
                            "written out, so that it is read" % (name, line, f.id))
        given = [kw.value for kw in node.keywords if kw.arg == "key"]
        if builtin and f.id in CALLING_BUILTINS and node.args:
            given.append(node.args[0])
        for value in given:
            if handed(value, chain):
                problems.append("%s:%d hands %s to be called, which may be a value it was given or binds; what the "
                                "Kernel hands to be called is a function it defines or imports, a lambda or a method "
                                "BUILTIN_METHODS names" % (name, line, ast.unparse(value)))
        target = kernel_function(f, chain)
        if target in takers:
            positional, keyword = takers[target]
            for word in sorted(CALLABLE_PARAMETERS & set(positional + keyword)):
                said = [kw.value for kw in node.keywords if kw.arg == word] if word in keyword else []
                place = positional.index(word) if word in positional else None
                spread = any(isinstance(a, ast.Starred) for a in node.args[:(place or 0) + 1]) or \
                    any(kw.arg is None for kw in node.keywords)
                value = said[0] if said else node.args[place] if place is not None and place < len(node.args) and \
                    not spread else None
                if value is None:
                    problems.append("%s:%d calls %s, which takes %s, and how it is filled cannot be read; it is given "
                                    "by its name or its place" % (name, line, target[1], word))
                    continue
                own = isinstance(value, ast.Name) and value.id == word and resolve(word, chain)[0] == "parameter"
                if not own and kernel_function(value, chain) is None:
                    problems.append("%s:%d gives %s as %s, which is not a function of the Kernel's; what fills %s is "
                                    "a function the Kernel defines or imports, or the caller's own %s"
                                    % (name, line, ast.unparse(value), word, word, word))

    def visit(node, chain):
        if isinstance(node, FUNCTIONS):
            given = node.args
            taken = CALLABLE_PARAMETERS & {a.arg for a in given.posonlyargs + given.args + given.kwonlyargs +
                                           [a for a in (given.vararg, given.kwarg) if a]}
            spread = CALLABLE_PARAMETERS & {a.arg for a in (given.vararg, given.kwarg) if a}
            if spread:
                problems.append("%s:%d takes %s as a spread of arguments; it is taken by its name or its place, so "
                                "that what fills it is read" % (name, node.lineno, ", ".join(sorted(spread))))
            if taken and (chain or isinstance(node, ast.Lambda)):
                problems.append("%s:%d takes %s in a function inside another or a lambda; only a function at a "
                                "module's top takes it, so that what fills it is read" % (name, node.lineno,
                                                                                        ", ".join(sorted(taken))))
            for decorator in getattr(node, "decorator_list", []):
                problems.append("%s:%d decorates a function, which calls the decorator with it; the Kernel calls a "
                                "function by its name" % (name, decorator.lineno))
            inner = [(node, _names(name, node, trees))] + chain
            # A function's decorators, defaults and annotations are read where it is defined, its body inside it.
            for part in getattr(node, "decorator_list", []) + [given] + ([node.returns] if getattr(node, "returns", None) else []):
                visit(part, chain)
            for part in node.body if isinstance(node.body, list) else [node.body]:
                visit(part, inner)
            return
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "kernel" and not alias.asname:
                    problems.append("%s:%d imports %s without naming it; the Kernel imports a module of its own as "
                                    "`from kernel import x` or `import kernel.x as x`" % (name, node.lineno, alias.name))
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            problems.append("%s:%d imports * from %s, which hides what it binds; the Kernel names each name it imports"
                            % (name, node.lineno, node.module or "." * node.level))
        if isinstance(node, ast.Call):
            call(node, chain)
        # A function written into text is its address in memory, which another process gives otherwise (issue 1137).
        shown = []
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str":
            shown = node.args + [k.value for k in node.keywords]
        elif isinstance(node, ast.FormattedValue):
            shown = [node.value]
        elif isinstance(node, (ast.BinOp, ast.AugAssign)) and isinstance(node.op, ast.Mod):
            right = node.right if isinstance(node, ast.BinOp) else node.value
            shown = [right] + (right.elts if isinstance(right, ast.Tuple) else right.values if isinstance(right, ast.Dict)
                               else [])
        # What an expression picks is written as itself: either branch of `a if c else b`, each of `a or b` (Astra, Kimi).
        for value in shown:
            shown += [value.body, value.orelse] if isinstance(value, ast.IfExp) else \
                value.values if isinstance(value, ast.BoolOp) else []
        if any(isinstance(value, ast.Lambda) or kernel_function(value, chain) is not None
               or (isinstance(value, ast.Name) and resolve(value.id, chain)[0] == "function") for value in shown):
            problems.append("%s:%d writes a function into text, which is its address in memory, and so another "
                            "process's replay reads other text; the Kernel writes no function into text"
                            % (name, node.lineno))
        if isinstance(node, ast.Attribute):
            bases.add(id(node.value))
        if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load) and id(node) not in bases \
                and module(node, chain):
            problems.append("%s:%d names the module %s but to read a name of it; a module of the Kernel's is not a "
                            "value, so that what a call of it reaches is read" % (name, node.lineno, ast.unparse(node)))
        if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load) and id(node) not in callees:
            target = kernel_function(node, chain)
            if target in takers:
                problems.append("%s:%d names %s without calling it; a function that takes %s is only called, so "
                                "that what fills it is read" % (name, node.lineno, target[1], ", ".join(
                                    sorted(CALLABLE_PARAMETERS & set(takers[target][0] + takers[target][1])))))
        for child in ast.iter_child_nodes(node):
            visit(child, chain)
    visit(tree, [])
    return problems


def _packages(trees: dict, tops: dict) -> list:
    """Where the check would read another module than Python imports: a module beside a package of its name, which
    Python passes over for the package, and a name a package binds that also names a module in it, which Python's `from`
    import takes as the package's binding. A package that binds the name to that very module is read alike."""
    problems = []
    for key in sorted(trees):
        if not key.endswith("__init__.py"):
            continue
        folder = key[:-len("__init__.py")]
        if folder and folder.rstrip("/") + ".py" in trees:
            problems.append("%s and %s are both kernel.%s; Python imports the package, so one of them is not what the "
                            "check reads" % (folder.rstrip("/") + ".py", key, folder.rstrip("/").replace("/", ".")))
        for word, kind in sorted(tops[key].items()):
            module = _file(".".join(["kernel"] + folder.split("/")[:-1] + [word]), trees)
            if module and kind != ("import", (module, None)):
                problems.append("%s binds %s, which also names the module %s; Python's `from` import takes the "
                                "binding, so the module is not what the check reads" % (key, word, module))
    return problems


# A source encoding declaration, as PEP 263 writes it, which Python reads on either of a file's first two lines.
CODING = re.compile(rb"^[ \t\f]*#.*?coding[:=][ \t]*([-\w.]+)")
UTF8 = ("utf-8", "utf8")
BOM = b"\xef\xbb\xbf"


def _source(path: pathlib.Path) -> str:
    """The text of a Kernel file, as Python and every reader of the text read it alike: UTF-8, strictly, and declared so
    or not at all. A file declaring another encoding would run code its text does not show, so it is refused, as are
    bytes that are not UTF-8 (issue 992). Read after a byte order mark, as Python reads it, each of the first two lines
    is held to that whatever the first holds, and only the names utf-8 and utf8 are UTF-8's: stricter than Python, which
    reads the second only after a comment or a blank line and knows other names, so that it can refuse, never miss.
    Raises ValueError for either."""
    data = path.read_bytes()
    head = data[len(BOM):] if data.startswith(BOM) else data
    for line in head.splitlines()[:2]:
        declared = CODING.match(line)
        name = declared.group(1).decode("ascii", "replace") if declared else None
        if name is not None and name.lower().replace("_", "-") not in UTF8:
            raise ValueError("it declares the encoding %s, and Python would run what its text does not show" % name)
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("its bytes are not UTF-8") from None


def _swapped(dotted: str, package: str) -> str:
    """A module's name with the Kernel's and `package`'s changed over at its head, or as it was: the rules below then
    read the package's imports of itself as they read the Kernel's of itself, and its imports of the Kernel as of any
    package that is not its own."""
    names = dotted.split(".")
    other = {"kernel": package, package: "kernel"}.get(names[0])
    return dotted if other is None else ".".join([other] + names[1:])


def _said(problem: str, package: str) -> str:
    """A problem the Kernel's rules found in `package`, which they read under the Kernel's name. The sentence is the
    rule's own and is left as it is. Only the module an import names was changed over, so the note says that of those
    alone: a file's name, an alias and a local are as the file has them."""
    return ("%s [a rule of the Kernel's, read of %s/: where it names a module an import names, `kernel` is `%s` in "
            "the file and `%s` is `kernel`; a file's name and every other name are as written]"
            % (problem, package, package, package))


def _modules(tree, trees: dict, package: str) -> tuple:
    """`(names, imports, twice)`: the names a file binds to modules of `package`; the imports that bind them, each by
    its id: `import package.x as name`, and `from package[.y] import name` where that names a file or a folder of the
    package's; and (line, name) for each of those that binds a name another binds to another module. A name is read
    file-wide, not by scope."""
    found, imports, twice = {}, set(), []
    for node in ast.walk(tree):
        own = []
        if isinstance(node, ast.Import):       # the package itself is no module of it: `import kernel as k` binds none
            own = [alias for alias in node.names if alias.asname and alias.name.split(".")[0] == package
                   and "." in alias.name]
        elif isinstance(node, ast.ImportFrom) and not node.level and (node.module or "").split(".")[0] == package:
            folder = "/".join(node.module.split(".")[1:] + [""]).lstrip("/")
            own = [alias for alias in node.names
                   if folder + alias.name + ".py" in trees or folder + alias.name + "/__init__.py" in trees]
        for alias in own:
            dotted = alias.name if isinstance(node, ast.Import) else node.module + "." + alias.name
            if found.setdefault(alias.asname or alias.name, dotted) != dotted:
                twice.append((node.lineno, alias.asname or alias.name))
            imports.add(id(alias))
    return set(found), imports, twice


def _bound(node) -> list:
    """The names a node binds, other than by an import: a parameter, a name assigned or looped over, a function's or a
    class's own, and what an `except` names."""
    if isinstance(node, ast.arg):
        return [node.arg]
    if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
        return [node.id]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.ExceptHandler) and node.name:
        return [node.name]
    return []


def _alone(root: pathlib.Path, read: set, trees: dict, package: str) -> list:
    """What is asked of the Kernel and of a package held as it is, under its own name, `guards/`, beyond the rules
    below (issues 838 and 851). The first and the last are asked of both; the two between of `guards/` alone, since
    the Kernel imports itself by its own rules, and its own modules and `_decision` are what those rules are about.
    For the Kernel the last narrows what it may write: a module's name is read off only where `import kernel.x as name`
    or `from kernel[.y] import name` binds it, so one imported relatively, or re-exported by another module, is a value
    here, and nothing is read off it; and a built-in type's method is read only to be called, never handed as a key.

    - It is the package Python imports, and what Python imports of it is what is read here: each folder of it has an
      `__init__.py`; it holds the source this check reads and an `AGENTS.md` alone, so no compiled module stands in a
      source's place and no file Python could run goes unread; and it holds no link. A committed `__pycache__/` is not
      this check's: tools/walk.py passes over it, and tools/check_repo.py refuses it (`_unloadable`).
    - It imports itself alone, by its name, and never the Kernel, which is not protected whole: so what it decides is
      changed nowhere but in it. A relative import is refused: the package is then imported in one way, and
      `from .. import x`, of which the Kernel's rules say nothing, reaches nothing above it.
    - No rule written for a module of the Kernel's by that module's name is read of one of its own, and it takes no
      parameter the Kernel may call: it calls nothing it is given.
    - It reads nothing of a value but by a built-in type's method that it calls: a generator's frame, and through it
      every builtin and every module's names, is one attribute away from any function. A name of one of its own
      modules is read off, and so that name is bound by its import alone: no parameter, local or other import takes it,
      and no two imports bind it to two modules.
    - A limit: a module's name is resolved file-wide, not by scope, so a name a guard imports in one function and reads
      in another, where Python reads it as a builtin, passes. No builtin's plain attribute reaches a frame, globals or
      builtins, for the Kernel and the guards alike.
    - A limit: a folder that holds a `.git` is another working tree, left out as tools/walk.py leaves it out. What the
      package imports of it is refused, as every import no file read here answers to is (issue 909); what only code
      outside the package imports of it is not this check's. Git commits no `.git`, so only a desk's tree can hold one.
    """
    problems, guest = [], package != "kernel"
    if (root / package).is_symlink():
        problems.append("%s is a link; what Python imports as %s is then kept somewhere else, which nothing protects"
                        % (package, package))
    held = [path.relative_to(root / package).as_posix() for path in walk.files(root, package)]
    for name in held:
        if name not in read and name.split("/")[-1] != "AGENTS.md":
            problems.append("%s/%s is neither Python's source nor an AGENTS.md; %s/ holds nothing else, so that nothing "
                            "compiled is imported in a source's place" % (package, name, package))
    for link in walk.links(root):
        if package in [parent.relative_to(root).as_posix() for parent in link.parents if root in parent.parents]:
            problems.append("%s is a link; Python imports through it, and what it points at is not read here"
                            % link.relative_to(root).as_posix())
    folders = {"/".join(name.split("/")[:n]) for name in held for n in range(name.count("/") + 1)}
    for folder in sorted(folders):
        if "/".join(filter(None, [folder, "__init__.py"])) not in held:
            problems.append("%s has no __init__.py; Python may then import another %s, which this does not read"
                            % ("/".join([package, folder]), package))
    for name, tree in trees.items():
        if guest and name in KEYED:
            problems.append("%s/%s bears the name of a module the Kernel's rules are written for, and they would be "
                            "read of it; name it otherwise" % (package, name))
        called = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
        modules, imports, twice = _modules(tree, trees, package)
        for line, word in twice:
            problems.append("%s:%d binds %s, which another import binds to another module of %s/; a module's name is "
                            "bound by one import alone, so that what is read off it is that module's"
                            % (name, line, word, package))
        for node in ast.walk(tree):
            taken = _bound(node)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                taken = [alias.asname or alias.name.split(".")[0] for alias in node.names if id(alias) not in imports]
            for word in taken:
                if word in modules:
                    problems.append("%s:%d binds %s, which names a module of %s/; a module's name is bound by its "
                                    "import alone, so that what is read off it is the module's"
                                    % (name, getattr(node, "lineno", 0), word, package))
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                own = isinstance(node.value, ast.Name) and node.value.id in modules
                if not own and not (id(node) in called and node.attr in BUILTIN_METHODS):
                    problems.append("%s:%d reads %s off a value; %s/ reads a name of a module of its own, calls a "
                                    "built-in type's method, and reads nothing else of a value"
                                    % (name, node.lineno, node.attr, package))
            elif type(node).__name__ == "Match":
                problems.append("%s:%d matches a value against patterns, which can read its attributes; %s/ reads "
                                "nothing of a value but by a built-in type's method" % (name, node.lineno, package))
            if not guest:
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "kernel":
                        problems.append("%s:%d imports %s; %s/ imports itself alone" % (name, node.lineno, alias.name, package))
                    alias.name = _swapped(alias.name, package)
            elif isinstance(node, ast.ImportFrom) and node.level:
                problems.append("%s:%d imports %s; %s/ imports itself alone, by its name"
                                % (name, node.lineno, "." * node.level + (node.module or ""), package))
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] == "kernel":
                    problems.append("%s:%d imports %s; %s/ imports itself alone" % (name, node.lineno, node.module, package))
                node.module = _swapped(node.module, package)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                given = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                given += [a for a in (node.args.vararg, node.args.kwarg) if a]
                for word in sorted(CALLABLE_PARAMETERS & {a.arg for a in given}):
                    problems.append("%s:%d takes %s, which the Kernel alone may call; %s/ makes no Decision and calls "
                                    "no function it is given" % (name, node.lineno, word, package))
    return problems


def guards(root: pathlib.Path = ROOT) -> list:
    """`guards/`, held as the Kernel is: what a Role's push may land is decided by functions that read nothing."""
    return run(root, "guards")


def run(root: pathlib.Path = ROOT, package: str = "kernel") -> list:
    unread, problems = [], []
    files = [p for p in walk.files(root, package) if p.suffix == ".py"]
    if not files:
        return ["there is no %s/ to check" % package]
    trees = {}
    for path in files:
        name = path.relative_to(root / package).as_posix()
        try:
            trees[name] = ast.parse(_source(path), str(path))
        except (SyntaxError, ValueError) as err:
            unread.append("%s cannot be read as Python: %s" % (name, err))
    read = {path.relative_to(root / package).as_posix() for path in files}
    own = _alone(root, read, trees, package)
    owned = {name: _defined(name, tree) for name, tree in trees.items() if name in CONFINED}
    takers = _takers(trees)
    tops = {name: _names(name, tree, trees) for name, tree in trees.items()}
    problems += _packages(trees, tops)
    bound = {name: _top_names(tree) for name, tree in trees.items()}

    def hidden(parts: list) -> bool:
        """A folder of the package that is there, its `__init__.py` not read: another working tree, which the walk
        leaves out, or a folder Python imports as a namespace (issue 909)."""
        return (root / package).joinpath(*parts).is_dir() and "/".join(parts + ["__init__.py"]) not in read

    for name, tree in trees.items():
        problems += _confined(name, tree, owned)
        problems += _calls(name, tree, trees, takers, tops)
        calendar, wrong = _calendar(name, tree)
        problems += wrong
        held = frozenset(bound[name])
        scopes = _scopes(tree, held)
        for node in ast.walk(tree):
            line = getattr(node, "lineno", 0)
            mods = []
            if isinstance(node, ast.Import):
                mods = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                mods = [node.module or ""]
            for mod in mods:
                if mod.split(".")[0] not in ALLOWED_IMPORTS:
                    problems.append("%s:%d imports %s" % (name, line, mod))
                inner = "/".join(mod.split(".")[1:])
                if mod.split(".")[0] == "kernel" and inner and hidden(inner.split("/")):
                    problems.append("%s:%d imports %s, a folder here that is not read, which Python imports before a "
                                    "file of its name" % (name, line, mod))
                elif mod.split(".")[0] == "kernel" and inner and inner + ".py" not in read and inner + "/__init__.py" not in read:
                    problems.append("%s:%d imports %s, which no file read here is: Python would import what this does "
                                    "not read" % (name, line, mod))
            # The guards refuse every relative import by their own rule, whatever it names.
            if isinstance(node, ast.ImportFrom) and ((node.level and package == "kernel")
                                                     or (not node.level and (node.module or "").split(".")[0] == "kernel")):
                for alias in node.names:
                    if not _answered(name, node, alias.name, read, bound, hidden):
                        problems.append("%s:%d imports %s from %s, which no file read here is and its module binds no "
                                        "such name" % (name, line, alias.name, "." * node.level + (node.module or "")))
            if package == "kernel" and isinstance(node, ast.ImportFrom) and node.level > name.count("/") + 1:
                problems.append("%s:%d imports %s, from above kernel/, which no rule here reads"
                                % (name, line, "." * node.level + (node.module or "")))
            for word in _bound(node) + ([alias.asname or alias.name.split(".")[0] for alias in node.names]
                                         if isinstance(node, (ast.Import, ast.ImportFrom)) else []):
                if word in CONSTANT_CALLS:
                    problems.append("%s:%d binds %s, the builtin a constant is made by; a module's top would then keep "
                                    "what that name returns" % (name, line, word))
            if isinstance(node, ast.comprehension) and node.is_async:
                problems.append("%s:%d drives what it is handed, which calls a method of a value; the Kernel calls none"
                                % (name, getattr(node.iter, "lineno", line)))
            for kind, does in HANDLING.items():
                if isinstance(node, kind):
                    problems.append("%s:%d %s, which calls a method of a value; the Kernel calls none"
                                    % (name, line, does))
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
                problems.append("%s:%d uses %s" % (name, line, node.id))
            if (isinstance(node, ast.Constant) and type(node.value) in (int, float) and node.value not in (0, 1)
                    and id(node) not in calendar):
                problems.append("%s:%d writes the number %s; a limit is data, read from the configuration"
                                % (name, line, node.value))
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                problems.append("%s:%d keeps state between calls" % (name, line))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                defaults = node.args.defaults + [d for d in node.args.kw_defaults if d is not None]
                if not all(_constant(d, scopes[id(node)]) for d in defaults):
                    problems.append("%s:%d has a default that can change, which is state kept between calls"
                                    % (name, line))
            if isinstance(node, ast.ClassDef):
                problems.append("%s:%d defines a class; the Kernel is functions and constants" % (name, line))
            if isinstance(node, ast.Raise):
                problems.append("%s:%d raises, which calls what it raises if that is a class; the Kernel raises "
                                "nothing, and what it cannot read is a deferral or a Hold" % (name, line))
            for word in _special(node):
                problems.append("%s:%d names %s, a special name, through which a module's names can be changed or a "
                                "value's workings reached; the Kernel names none" % (name, line, word))
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
                problems.append("%s:%d assigns an attribute, %s; the Kernel changes no module's names and no object "
                                "it did not make" % (name, line, node.attr))
        # State is derived at every call and never stored: a module holds constants only.
        for i, node in enumerate(tree.body):
            docstring = i == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            if docstring or isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)):
                continue
            value = getattr(node, "value", None) if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
            if isinstance(node, ast.AsyncFunctionDef):
                problems.append("%s:%d defines an async function; the Kernel waits on nothing" % (name, node.lineno))
            elif value is None:
                problems.append("%s:%d runs when the module is imported; a module holds constants and functions"
                                % (name, node.lineno))
            elif not _constant(value, held):
                problems.append("%s:%d holds a value that can change; State is never stored" % (name, node.lineno))
            elif not all(_shaped(target, value) for target in (node.targets if isinstance(node, ast.Assign) else [node.target])):
                problems.append("%s:%d assigns other than to names, or unpacks other than a tuple of its own shape, which "
                                "can keep a list a starred name unpacks into, or a set's order; "
                                "State is never stored" % (name, node.lineno))
    return unread + own + ([_said(problem, package) for problem in problems] if package != "kernel" else problems)
