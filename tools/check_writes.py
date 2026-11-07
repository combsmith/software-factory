"""Only the write steps reach a GitHub write (issue 587). Read from the code's syntax, never by importing it.

A write is a request built by `adapters/github.py`'s `request` whose method is POST, PUT, PATCH or DELETE, but for a
GraphQL query, which GitHub reads by POST, and for minting or revoking an installation token, which is a credential:
CREDENTIALS. A writer is an adapter function that holds a write. A function reaches one when it calls it or names it,
names a module constant that names it, or names a class one of whose methods, its bases' among them, reaches it,
through any number of calls, modules and re-exports. Outside `adapters/` and the tests, only the callers in CALLERS
reach a writer, each exactly the writers it lists: a new caller, or a caller reaching a new writer, fails until
CALLERS names it in the same change, and a listing no longer true fails too. What the syntax cannot read is a problem,
never a pass: a method or a query that is not a literal, a name a module does not define, a module that reaches a write
handed on as a value, a request built by hand, or an adapter loaded by name.
"""
from __future__ import annotations

import ast
import pathlib
import re

from tools import walk

ROOT = pathlib.Path(__file__).resolve().parent.parent
GITHUB = "adapters.github"
SENDS = ("request", "download", "tarball")      # adapters/github.py's: a request, and the two that are GETs
VERBS = frozenset({"PO" "ST", "PU" "T", "PAT" "CH", "DEL" "ETE"})     # spelt apart, so this file holds no verb itself
CREDENTIALS = (re.compile(r"/app/installations/%d/access_tokens"), re.compile(r"/installation/token"))     # %d: a hole for text
# could hold another path (the Claude review)
# The callers outside adapters/ that may reach a write, each with the writers it reaches, by module and function. A
# change here is a change to who writes to GitHub, and is the Maintainer's (decision NNNN).
CALLERS = {
    "harness/apply_step.py": {"adapters.effects:_review", "adapters.effects:_check", "adapters.effects:_comment"},
    "harness/approve.py": {"adapters.effects:approve"},
    "harness/approve_step.py": {"adapters.effects:approve"},
    "harness/queue.py": {"adapters.queue:enqueue", "adapters.queue:dequeue", "adapters.queue:resolve"},
    "harness/queue_step.py": {"adapters.queue:enqueue", "adapters.queue:dequeue", "adapters.queue:resolve"},
    "release/move.py": {"adapters.tags:write", "adapters.deployments:record"},
}
# The transport's own: each checks again a request `request` built, whatever its method, and builds none of its own.
TRANSPORT = {(GITHUB, "Live.send"), (GITHUB, "Replay.send")}
# Python outside adapters/ that may hold a write verb as a string: each reads a command to classify it, and sends none.
VERB_HOLDERS = ("tools/hooks/identity.py", "tools/hooks/protected.py")
# Python that loads a module by a name it is given: tools/mutants.py loads a test under tests/, and checks it is one.
NAME_LOADERS = ("tools/mutants.py",)
# Python outside tests/ that imports a test: tools/make_corpus.py records the Kernel's decisions from tests/test_decide.py.
TEST_IMPORTERS = ("tools/make_corpus.py",)
# What a request is, by its keys: edited after `request` built it, it is sent as edited.
FIELDS = ("method", "path", "body")
# A module's names as a value: what is read from them cannot be.
NAMESPACES = ("__dict__", "__getattribute__", "__getattr__")
# The modules by which code loads a module by its name.
LOADER_MODULES = ("importlib", "builtins")
# What opens a scope of its own inside a function.
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.ClassDef)
# The calls on a request that only read it.
READS = ("get", "copy", "items", "keys", "values")
# The calls that fill a container in place.
FILLS = ("append", "extend", "insert", "update", "setdefault", "add")


def _name(rel: str) -> str:
    parts = rel[:-len(".py")].split("/")
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _text(node):
    """The text a str literal, a `%` format's left side or a `+` of literals holds, or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return _text(node.left)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _text(node.left), _text(node.right)
        return left + right if left is not None and right is not None else None
    return None


class Module:
    """A module as its syntax gives it: what its names are bound to, and its units of code, each walked once."""

    def __init__(self, rel: str, tree: ast.Module, known: set):
        self.rel, self.name, self.tree = rel, _name(rel), tree
        package = self.name if rel.endswith("__init__.py") else self.name.rpartition(".")[0]
        self.bindings, self.texts, self.functions, self.classes, self.values, self.stored = {}, {}, {}, {}, {}, set()
        self.conflicts, self.formatted = set(), set()       # names bound two ways; texts made by a `%` format
        self.nodes = list(ast.walk(tree))
        for node in self.nodes:     # an import anywhere, for one made inside a function binds as well
            bound = []
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    bound.append((local, ("module", alias.name if alias.asname else local)))
            elif isinstance(node, ast.ImportFrom):
                base = package.split(".")[:len(package.split(".")) - node.level + 1] if node.level else []
                source = ".".join(base + ([node.module] if node.module else [])) if node.level else node.module
                for alias in node.names:
                    whole = "%s.%s" % (source, alias.name)
                    bound.append((alias.asname or alias.name, ("module", whole) if whole in known else ("attr", source, alias.name)))
            for local, target in bound:
                if self.bindings.get(local, target) != target:
                    self.conflicts.add(local)
                self.bindings[local] = target
        inside = {id(n) for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                  for n in ast.walk(node)}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[node.name] = node
            elif isinstance(node, ast.ClassDef):
                self.classes[node.name] = node
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.functions["%s.%s" % (node.name, item.name)] = item
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):    # each assignment of one constant, all read as the one
                        self.values.setdefault(target.id, []).append(node.value)
                        if any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod) for n in ast.walk(node.value)):
                            self.formatted.add(target.id)
        # A text constant is one every assignment of which is that same text, and that nothing else at the top level
        # rebinds, under an if or by an augmented assignment: one assigned anything else is no constant.
        rebound = [n.id for n in self.nodes if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
                   and id(n) not in inside]
        for name, values in self.values.items():
            texts = {_text(v) for v in values}
            if len(texts) == 1 and None not in texts and rebound.count(name) == len(values):
                self.texts[name] = texts.pop()
        # Every name the module's own top level stores, in an if, a try or a loop too: a value, whatever it holds.
        self.stored = {n.id for n in self.nodes if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
                       and id(n) not in inside}
        self.units = {qual: list(ast.walk(fn)) for qual, fn in self.functions.items()}
        for name, node in self.classes.items():     # a class's bases and its own assignments, its methods aside
            methods = {id(n) for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                       for n in ast.walk(item)}
            self.units[name] = [n for n in ast.walk(node) if id(n) not in methods]
        for name, values in self.values.items():
            self.units.setdefault(name, [n for value in values for n in ast.walk(value)])
        for node in tree.body:      # a constant or a class filled at the top level, after it is made, holds what fills it
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for name in _filled_names(node) & (set(self.values) | set(self.classes)):
                self.units[name] = self.units[name] + list(ast.walk(node))
        held = {id(n) for nodes in self.units.values() for n in nodes} | inside
        self.units["<module>"] = [n for n in self.nodes if id(n) not in held]
        # A name both defined here and imported, or defined twice: which one a function means cannot be told by the syntax.
        self.conflicts |= set(self.bindings) & (set(self.functions) | set(self.classes) | set(self.values))
        defined = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        self.conflicts |= {name for name in defined if defined.count(name) > 1 or name in self.values}


def _filled_names(node) -> set:
    """The names `node` fills in place: `N[k] = v`, `N.a = v`, or `N.append(v)` and its kind."""
    out = set()
    for n in ast.walk(node):
        target = n.value if isinstance(n, (ast.Subscript, ast.Attribute)) and isinstance(n.ctx, ast.Store) else \
            n.func.value if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in FILLS else None
        while isinstance(target, (ast.Subscript, ast.Attribute)):     # TABLE['a']['b'] = w fills TABLE
            target = target.value
        if isinstance(target, ast.Name):
            out.add(target.id)
    return out


def _lookup(mods: dict, module: str, name: str, seen: frozenset = frozenset()):
    """What `name` is in `module`: ("def"|"class"|"value", module, name), ("module", name), ("unknown", module, name),
    or None for what this check does not read: a module outside the repo, or a name its top level stores some other way."""
    other = mods.get(module)
    if other is None:
        return None
    if (module, name) in seen:      # a re-export that comes back to itself
        return ("unknown", module, name)
    seen = seen | {(module, name)}
    if name in other.conflicts:
        return ("conflict", module, name)
    if name in other.functions:
        return ("def", module, name)
    if name in other.classes:
        return ("class", module, name)
    if name in other.values:
        return ("value", module, name)
    if name in other.bindings:
        return _bound(mods, other.bindings[name], seen)
    if "%s.%s" % (module, name) in mods:
        return ("module", "%s.%s" % (module, name))
    if name in NAMESPACES:
        return ("module", module)
    if name.startswith("__") and name.endswith("__"):
        return None
    if name in other.stored:    # stored some other way, by an if, a tuple or a loop: whatever the top level reaches
        return ("value", module, "<module>")
    return ("unknown", module, name)


def _bound(mods: dict, bound: tuple, seen: frozenset = frozenset()):
    if bound[0] == "module":
        return ("module", bound[1]) if bound[1] in mods else None
    return _lookup(mods, bound[1], bound[2], seen)


def _resolve(mods: dict, mod: Module, node, cls: str = None):
    """What a Name or a dotted Attribute is in the repo's code, as `_lookup` gives it, or None."""
    if isinstance(node, ast.Name):
        if node.id in mod.conflicts:
            return ("conflict", mod.name, node.id)
        if node.id in mod.functions or node.id in mod.classes or node.id in mod.values:
            return _lookup(mods, mod.name, node.id)
        if node.id in mod.bindings:
            return _bound(mods, mod.bindings[node.id])
        return ("value", mod.name, "<module>") if node.id in mod.stored else None
    if isinstance(node, ast.Attribute):
        own = isinstance(node.value, ast.Name) and node.value.id in ("self", "cls") or isinstance(node.value, ast.Call) \
            and isinstance(node.value.func, ast.Name) and node.value.func.id == "super"
        if own and cls:
            above = isinstance(node.value, ast.Call)        # super(): the bases' method, never the class's own
            found = [m for m in _methods(mods, mod.name, cls, set()) if m[1].rpartition(".")[2] == node.attr
                     and not (above and m[1].startswith(cls + "."))]
            return ("def",) + found[0] if found else None
        base = _resolve(mods, mod, node.value, cls)
        if base and base[0] == "module":
            return _lookup(mods, base[1], node.attr)
        if base and base[0] == "class":
            qual = "%s.%s" % (base[2], node.attr)
            return ("def", base[1], qual) if qual in mods[base[1]].functions else None
    return None


def _scope(fn) -> set:
    """The names a function binds in its own scope: its parameters and what it assigns, but not a nested function's,
    a lambda's or a comprehension's, nor a name it declares global."""
    nested = {id(n) for child in ast.walk(fn) if child is not fn and isinstance(child, SCOPES) for n in ast.walk(child)}
    own = [n for n in ast.walk(fn) if id(n) not in nested]
    names = {n.id for n in own if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    names |= {a.arg for a in ast.walk(fn.args) if isinstance(a, ast.arg)}
    names |= {n.name for n in ast.walk(fn) if n is not fn and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and id(n) not in nested}
    return names - {g for n in own if isinstance(n, (ast.Global, ast.Nonlocal)) for g in n.names}


def _methods(mods: dict, module: str, cls: str, seen: set) -> list:
    """Each method of a class and of its bases, as far as the repo's code holds them."""
    if (module, cls) in seen or module not in mods or cls not in mods[module].classes:
        return []
    seen.add((module, cls))
    out = [(module, cls)] + [(module, f) for f in mods[module].functions if f.startswith(cls + ".")]
    for base in mods[module].classes[cls].bases:
        got = _resolve(mods, mods[module], base)
        if got and got[0] == "class":
            out += _methods(mods, got[1], got[2], seen)
    return out


class Reading:
    """The repo's code read once: what each unit reaches by one step, its requests, and what cannot be read."""

    def __init__(self, mods: dict):
        self.mods, self.graph, self.problems, self.handed = mods, {}, [], []
        for mod in mods.values():
            for qual, nodes in mod.units.items():
                self.graph[(mod.name, qual)] = self._edges(mod, qual, nodes)

    def _edges(self, mod: Module, qual: str, nodes: list) -> list:
        cls = qual.split(".")[0] if "." in qual and qual.split(".")[0] in mod.classes else None
        inner = {id(n.value) for n in nodes if isinstance(n, ast.Attribute)}
        # A function's own names, its parameters and what it assigns, shadow the module's; what it assigns them is read.
        local = set() if qual not in mod.functions else _scope(mod.functions[qual]) - {"self", "cls"}     # read as the class
        out = []
        for node in nodes:
            if not isinstance(node, (ast.Name, ast.Attribute)) or not isinstance(node.ctx, ast.Load) or id(node) in inner:
                continue
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name) and root.id in local:
                continue
            got, part = None, node
            while got is None and isinstance(part, (ast.Name, ast.Attribute)):
                got = _resolve(self.mods, mod, part, cls)
                part = part.value if isinstance(part, ast.Attribute) else None
            if got is None:
                continue
            if got[0] == "def":
                out.append((got[1], got[2]))
            elif got[0] == "class":
                out += _methods(self.mods, got[1], got[2], set())
            elif got[0] == "value":
                out.append((got[1], got[2]))
            elif got[0] == "module":
                self.handed.append((mod, node.lineno, got[1]))
            elif got[0] == "conflict":
                self.problems.append("%s:%d names %s, which the module binds more than one way, so what it reaches cannot "
                                     "be read; give each its own name" % (mod.rel, node.lineno, got[2]))
            else:
                self.problems.append("%s:%d names %s, which %s does not define, so what it reaches cannot be read"
                                     % (mod.rel, node.lineno, got[2], got[1]))
        if qual == "<module>":
            self.problems += ["%s:%d imports * from %s, so what it reaches cannot be read; name what it imports"
                              % (mod.rel, n.lineno, n.module) for n in mod.nodes if isinstance(n, ast.ImportFrom)
                              and any(a.name == "*" for a in n.names) and _bound(self.mods, ("module", n.module or ""))]
        return out

    def sends(self, mod: Module, nodes: list) -> list:
        """(call, which) for each call in `nodes` of a function of adapters/github.py's that sends; and each place one is
        named but not called, as (node, None)."""
        called = {id(n.func) for n in nodes if isinstance(n, ast.Call)}
        out = []
        for node in nodes:
            if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
                got = _resolve(self.mods, mod, node)
                if got and got[0] == "def" and got[1] == GITHUB and got[2] in SENDS:
                    call = next((n for n in nodes if isinstance(n, ast.Call) and n.func is node), None)
                    out.append((call, got[2]) if id(node) in called else (node, None))
        return out


def _argument(call: ast.Call, at: int, name: str):
    return call.args[at] if len(call.args) > at else next((k.value for k in call.keywords if k.arg == name), None)


def _query(mods: dict, mod: Module, node, nodes: list):
    """The text of a GraphQL query, a literal or a module's text constant, or a sentence saying why it cannot be read."""
    if _text(node) is not None:
        formatted = any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod) for n in ast.walk(node))
        return _filled(_text(node), formatted)
    root = node
    while isinstance(root, ast.Attribute):
        root = root.value
    if isinstance(root, ast.Name) and any(isinstance(n, ast.Name) and n.id == root.id and isinstance(n.ctx, ast.Store)
                                          or isinstance(n, ast.arg) and n.arg == root.id for n in nodes):
        return "its GraphQL query is a name the function itself sets"
    got = _resolve(mods, mod, node) if isinstance(node, (ast.Name, ast.Attribute)) else None
    if got and got[0] == "value" and got[2] in mods[got[1]].texts:
        return _filled(mods[got[1]].texts[got[2]], got[2] in mods[got[1]].formatted)
    return "its GraphQL query is not a text constant"


def _filled(text: str, formatted: bool) -> str:
    """A query made by a `%` format is read only where each of its holes takes a number, which holds no operation."""
    return "its GraphQL query is formatted with text" if formatted and re.search(r"%(?![d%])", text) else text


def _kind(mods: dict, mod: Module, call: ast.Call, which: str, nodes: list):
    """"read", "credential", "write", or a sentence saying what the syntax cannot tell."""
    if which != "request":
        return "read"
    method, path = _argument(call, 0, "method"), _argument(call, 1, "path")
    if not (isinstance(method, ast.Constant) and isinstance(method.value, str)):
        return "its method is not a literal"
    if method.value == "GET":
        return "read"
    if method.value not in VERBS:
        return "its method %r is no verb this check knows" % method.value
    if method.value == "PO" "ST" and isinstance(path, ast.Constant) and path.value == "/graphql":
        body = _argument(call, 3, "body")
        if not isinstance(body, ast.Dict) or not all(isinstance(k, ast.Constant) for k in body.keys):
            return "its GraphQL body is not a literal dict"
        found = [v for k, v in zip(body.keys, body.values) if isinstance(k, ast.Constant) and k.value == "query"]
        if len(found) != 1:
            return "its GraphQL body has no one query"
        text = _query(mods, mod, found[0], nodes)
        if text.startswith("its GraphQL query"):
            return text
        if re.search(r"\bmutation\b", text):    # anywhere: a document may hold a query, then a mutation
            return "write"
        return "read" if re.match(r"\s*(query\b|\{)", text) else "its GraphQL document is neither a query nor a mutation"
    if _text(path) is not None and any(c.fullmatch(_text(path)) for c in CREDENTIALS):
        return "credential"
    return "write"


def _by_hand(mod: Module) -> list:
    """A request built as a dict with a method, not by `request`: what it sends cannot be read."""
    out = []
    for node in mod.nodes:
        if isinstance(node, ast.Dict) and any(isinstance(k, ast.Constant) and k.value == "method" for k in node.keys) \
                or isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict" \
                and any(k.arg == "method" for k in node.keywords):
            out.append("%s:%d builds a request with a method by hand, so what it sends cannot be read; build it with "
                       "adapters/github.py's request" % (mod.rel, node.lineno))
    return out


def _edited(mod: Module) -> list:
    """A request's method, path or body set after `request` built it, which is sent as set: what it sends cannot be read."""
    out = []
    for node in mod.nodes:
        key = node.slice if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store) else None
        if isinstance(key, ast.Constant) and key.value in FIELDS \
                or isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "update" \
                and any(k.arg in FIELDS for k in node.keywords):
            out.append("%s:%d sets a request's method, path or body after it is built, so what it sends cannot be read; build it with "
                       "adapters/github.py's request" % (mod.rel, node.lineno))
    return out


def _changed(mod: Module, nodes: list, call: ast.Call) -> list:
    """Where a request `request` built, bound to a name, is changed after: by a key set, or a call on it but a read."""
    names = {t.id for n in nodes if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is call
             for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
    grown = True
    while grown:        # alias = req: the alias is the request too
        more = {t.id for n in nodes if isinstance(n, (ast.Assign, ast.AnnAssign)) and isinstance(n.value, ast.Name)
                and n.value.id in names for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
        grown, names = not more <= names, names | more
    out = []
    for n in nodes:
        base = n.value if isinstance(n, ast.Subscript) and isinstance(n.ctx, (ast.Store, ast.Del)) else \
            n.func.value if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr not in READS else None
        if isinstance(base, ast.Name) and base.id in names:
            out.append("%s:%d changes a request after it is built, so what it sends cannot be read; build it whole with "
                       "adapters/github.py's request" % (mod.rel, n.lineno))
    return out


def _registry(mod: Module) -> list:
    """In adapters/, a function that fills a constant of its module: what a caller reads from it cannot be read."""
    out = []
    for qual, fn in mod.functions.items():
        for name in sorted(_filled_names(fn) & (set(mod.values) | set(mod.classes))):
            out.append("%s:%d fills %s from a function, so what a caller reads from it cannot be read; fill it at the "
                       "top level" % (mod.rel, fn.lineno, name))
    return out


def _tests(mod: Module) -> list:
    """An import of a test from outside tests/: the check does not read tests/, so what it reaches cannot be told."""
    return ["%s:%d imports %s, a test, which the check does not read" % (mod.rel, n.lineno, name)
            for n in mod.nodes for name in ([a.name for a in n.names] if isinstance(n, ast.Import) else
                                             [n.module or ""] if isinstance(n, ast.ImportFrom) and not n.level else [])
            if name == "tests" or name.startswith("tests.")]


def _loaded(mod: Module) -> list:
    """Each line that imports importlib or builtins, or names __import__: a module loaded by its name is one the syntax
    cannot follow."""
    return sorted({n.lineno for n in mod.nodes if isinstance(n, ast.Import) and any(a.name.split(".")[0] in LOADER_MODULES for a in n.names)
                   or isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] in LOADER_MODULES
                   or isinstance(n, ast.Name) and n.id == "__import__"})


def _verbs(mod: Module) -> list:
    """The lines of `mod` that hold a write verb as a whole string, its docstrings aside."""
    docs = {id(n.body[0].value) for n in mod.nodes
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return sorted({n.lineno for n in mod.nodes if isinstance(n, ast.Constant) and n.value in VERBS and id(n) not in docs})


def reaching(graph: dict, writers: set) -> dict:
    """{unit: the writers it reaches, through any number of steps}, read back from each writer."""
    back = {}
    for here, theres in graph.items():
        for there in theres:
            back.setdefault(there, set()).add(here)
    out = {}
    for writer in writers:
        seen, todo = {writer}, [writer]
        while todo:
            here = todo.pop()
            out.setdefault(here, set()).add(writer)
            for caller in back.get(here, ()):
                if caller not in seen:
                    seen.add(caller)
                    todo.append(caller)
    return out


def _adapter(mod: Module) -> bool:
    return mod.name == "adapters" or mod.name.startswith("adapters.")


def run(root: pathlib.Path = ROOT) -> list:
    problems, mods = [], {}
    sources = [p.relative_to(root).as_posix() for p in walk.files(root) if p.suffix == ".py"]
    sources = [rel for rel in sources if not rel.startswith("tests/")]
    known = {_name(rel) for rel in sources}
    for rel in sources:
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"), rel)
        except (SyntaxError, ValueError, UnicodeDecodeError) as err:
            problems.append("%s cannot be read as Python (%s), so what it writes cannot be told" % (rel, err))
            continue
        mods[_name(rel)] = Module(rel, tree, known)
    reading = Reading(mods)
    problems += reading.problems
    writers = set()
    for mod in mods.values():
        if mod.name != GITHUB:
            problems += _by_hand(mod) + _edited(mod)
        if _adapter(mod):
            problems += _registry(mod)
        if mod.rel not in TEST_IMPORTERS:
            problems += _tests(mod)
        if mod.rel not in NAME_LOADERS:
            problems += ["%s:%d loads a module by its name, or may, so what it reaches cannot be read; import it" % (mod.rel, line)
                         for line in _loaded(mod)]
        for qual, nodes in mod.units.items():
            for call, which in ([] if (mod.name, qual) in TRANSPORT else reading.sends(mod, nodes)):
                if which is None:
                    if mod.name != GITHUB:
                        problems.append("%s:%d names adapters/github.py's request without calling it, so what it "
                                        "sends cannot be read" % (mod.rel, call.lineno))
                    continue
                kind = _kind(mods, mod, call, which, nodes)
                if mod.name != GITHUB:
                    problems += _changed(mod, nodes, call)
                if kind == "write" and _adapter(mod):
                    writers.add((mod.name, qual))
                elif kind == "write" or (kind not in ("read", "credential") and not _adapter(mod)):
                    problems.append("%s:%d sends a request that is not a read outside adapters/; a write to GitHub is an "
                                    "adapter's, which a caller in tools/check_writes.py's CALLERS reaches" % (mod.rel, call.lineno))
                elif kind not in ("read", "credential"):
                    problems.append("%s:%d sends a request whose kind cannot be read: %s; write it as a literal" %
                                    (mod.rel, call.lineno, kind))
        if not _adapter(mod) and mod.rel not in VERB_HOLDERS and mod.rel != "tools/check_writes.py":
            problems += ["%s:%d holds a write verb; a write to GitHub is an adapter's, and Python that only reads "
                         "a command's verb is named in tools/check_writes.py's VERB_HOLDERS" % (mod.rel, line)
                         for line in _verbs(mod)]
    reach = reaching(reading.graph, writers)
    writing = {name for (name, _), found in reach.items() if found}
    for mod, line, module in reading.handed:
        if mod.name != GITHUB and (module in writing or module == "adapters" or module.startswith("adapters.")):
            problems.append("%s:%d uses the module %s as a value, so what it reaches cannot be read; name what it calls"
                            % (mod.rel, line, module))
    for node_mod in sorted(mods.values(), key=lambda m: m.rel):
        if _adapter(node_mod):
            continue
        found = {"%s:%s" % w for qual in node_mod.units for w in reach.get((node_mod.name, qual), ())}
        listed = CALLERS.get(node_mod.rel)
        if found and listed is None:
            problems.append("%s reaches a GitHub write, %s, and is not in tools/check_writes.py's CALLERS; a new writer "
                            "is the Maintainer's to allow, in the change that adds it" % (node_mod.rel, ", ".join(sorted(found))))
        elif listed is not None and found != listed:
            problems.append("%s reaches %s, and CALLERS lists %s; name what it reaches, in the change that changes it" %
                            (node_mod.rel, ", ".join(sorted(found)) or "no write", ", ".join(sorted(listed))))
    problems += ["CALLERS names %s, which is not here; take it off" % rel for rel in sorted(CALLERS) if _name(rel) not in mods]
    return problems
