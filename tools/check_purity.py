"""The Kernel does no I/O and keeps nothing between calls. Asserted from its syntax tree, not from trust.

It is strict by allowing little: a Kernel module holds a docstring, imports, constants and
functions, and nothing else. That is narrower than Python, on purpose. It assigns no attribute, so
no module changes another's names. The brakes and the gate, each a protected path alone, import
only what CONFINED allows, and no module binds a name either of them owns but as its own. It calls
no function it is given but the parameters CALLABLE_PARAMETERS names, and on a value only the built-in
types' methods BUILTIN_METHODS names, so that no function handed in can read the world for it. It calls a module only
at a function the module defines or imports, raises nothing and names no special name, and where Python would
import another module than the one it reads, it refuses that (issue 593).
"""
from __future__ import annotations

import ast
import pathlib

from tools import walk

ROOT = pathlib.Path(__file__).resolve().parent.parent
# `typing` is not among them: it reaches `sys` and an `eval` of its own, and the Kernel needs none of it (issue 588).
ALLOWED_IMPORTS = {"__future__", "kernel"}
FORBIDDEN_NAMES = {"open", "print", "input", "exec", "eval", "__import__", "compile", "globals", "locals", "vars",
                   "getattr", "setattr", "delattr", "__builtins__", "breakpoint", "callable", "iter"}
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
    line, and `__future__`, the module `from __future__ import` names, is the one allowed."""
    if isinstance(node, (ast.Constant, ast.alias)):
        return []
    words = []
    for field, value in ast.iter_fields(node):
        for part in value if isinstance(value, list) else [value]:
            if isinstance(part, ast.alias):
                part = part.name + "." + (part.asname or "")
            if isinstance(part, str) and not (field == "module" and part == "__future__"):
                words += part.split(".")
    return [w for w in words if len(w) > 4 and w.startswith("__") and w.endswith("__")]


def _constant(node) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Tuple):
        return all(_constant(e) for e in node.elts)
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in CONSTANT_CALLS


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


def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    files = [p for p in walk.files(root, "kernel") if p.suffix == ".py"]
    if not files:
        return ["there is no kernel/ to check"]
    trees = {}
    for path in files:
        name = path.relative_to(root / "kernel").as_posix()
        try:
            trees[name] = ast.parse(path.read_text(errors="replace"), str(path))
        except (SyntaxError, ValueError) as err:
            problems.append("%s cannot be read as Python: %s" % (name, err))
    owned = {name: _defined(name, tree) for name, tree in trees.items() if name in CONFINED}
    takers = _takers(trees)
    tops = {name: _names(name, tree, trees) for name, tree in trees.items()}
    problems += _packages(trees, tops)
    for name, tree in trees.items():
        problems += _confined(name, tree, owned)
        problems += _calls(name, tree, trees, takers, tops)
        calendar, wrong = _calendar(name, tree)
        problems += wrong
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
                if not all(_constant(d) for d in defaults):
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
            elif not _constant(value):
                problems.append("%s:%d holds a value that can change; State is never stored" % (name, node.lineno))
    return problems
