"""Only the write steps reach a GitHub write (issue 587). Read from the code's syntax, never by importing it.

A write is a request through `adapters/github.py` whose method is POST, PUT, PATCH or DELETE, but for a GraphQL query,
which GitHub reads by POST, and for minting or revoking an installation token, which is a credential: CREDENTIALS. A
writer is an adapter function that holds a write, and a function reaches one when it calls it, names it as a value, or
names a class one of whose methods reaches it, across modules. Outside `adapters/` and the tests, only the callers in
CALLERS reach a writer, and each reaches exactly the writers it lists: a new caller, or a caller reaching a new writer,
fails until CALLERS names it in the same change, and a listing no longer true fails too. What the syntax cannot read,
a method or a query that is not a literal, or an adapter module handed on as a value, is a problem, never a pass.
"""
from __future__ import annotations

import ast
import pathlib
import re

from tools import walk

ROOT = pathlib.Path(__file__).resolve().parent.parent
GITHUB = "adapters.github"
VERBS = frozenset({"PO" "ST", "PU" "T", "PAT" "CH", "DEL" "ETE"})     # spelt apart, so this file holds no verb itself
CREDENTIALS = (re.compile(r"/app/installations/%[sd]/access_tokens"), re.compile(r"/installation/token"))
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
    def __init__(self, rel: str, tree: ast.Module, known: set):
        self.rel, self.name, self.tree = rel, _name(rel), tree
        package = self.name if rel.endswith("__init__.py") else self.name.rpartition(".")[0]
        self.bindings, self.texts, self.functions, self.classes = {}, {}, {}, set()
        for node in ast.walk(tree):     # an import anywhere, for one made inside a function binds as well
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    self.bindings[local] = ("module", alias.name if alias.asname else local)
            elif isinstance(node, ast.ImportFrom):
                base = package.split(".")[:len(package.split(".")) - node.level + 1] if node.level else []
                source = ".".join(base + ([node.module] if node.module else [])) if node.level else node.module
                for alias in node.names:
                    whole = "%s.%s" % (source, alias.name)
                    self.bindings[alias.asname or alias.name] = ("module", whole) if whole in known else \
                        ("attr", source, alias.name)
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                    and _text(node.value) is not None:
                self.texts[node.targets[0].id] = _text(node.value)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[node.name] = node
            if isinstance(node, ast.ClassDef):
                self.classes.add(node.name)
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.functions["%s.%s" % (node.name, item.name)] = item

    def module(self, local: str):
        bound = self.bindings.get(local)
        return bound[1] if bound and bound[0] == "module" else None

    def units(self):
        """(name, nodes) for each function and method, a def or lambda inside one as its own, and `<module>` for the rest."""
        inside = set()
        for qual, fn in self.functions.items():
            nodes = list(ast.walk(fn))
            inside |= {id(n) for n in nodes}
            yield qual, nodes
        yield "<module>", [n for n in ast.walk(self.tree) if id(n) not in inside]


def _requests(mod: Module, nodes: list) -> list:
    """Each call in `nodes` of adapters/github.py's `request`, `download` or `tarball`: (call, what it is called)."""
    out = []
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        f, called = node.func, None
        if isinstance(f, ast.Name):
            bound = mod.bindings.get(f.id)
            if mod.name == GITHUB and f.id in ("request", "download", "tarball"):
                called = f.id
            elif bound and bound[0] == "attr" and bound[1] == GITHUB and bound[2] in ("request", "download", "tarball"):
                called = bound[2]
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and mod.module(f.value.id) == GITHUB \
                and f.attr in ("request", "download", "tarball"):
            called = f.attr
        if called:
            out.append((node, called))
    return out


def _argument(call: ast.Call, at: int, name: str):
    return call.args[at] if len(call.args) > at else next((k.value for k in call.keywords if k.arg == name), None)


def _query(mods: dict, mod: Module, node):
    """The text of a GraphQL query: a literal, or a module's own or another module's text constant; None if neither."""
    if _text(node) is not None:
        return _text(node)
    if isinstance(node, ast.Name):
        bound = mod.bindings.get(node.id)
        if node.id in mod.texts:
            return mod.texts[node.id]
        if bound and bound[0] == "attr" and bound[1] in mods:
            return mods[bound[1]].texts.get(bound[2])
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and mod.module(node.value.id) in mods:
        return mods[mod.module(node.value.id)].texts.get(node.attr)
    return None


def _kind(mods: dict, mod: Module, call: ast.Call, called: str):
    """"read", "credential", "write", or a sentence saying what the syntax cannot tell."""
    if called != "request":
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
        found = [v for k, v in zip(body.keys, body.values) if isinstance(k, ast.Constant) and k.value == "query"] \
            if isinstance(body, ast.Dict) else []
        text = _query(mods, mod, found[0]) if len(found) == 1 else None
        if text is None:
            return "its GraphQL query is not a text constant"
        word = re.match(r"\s*(\w+|\{)", text)
        word = word.group(1) if word else ""
        return "write" if word == "mutation" else "read" if word in ("query", "{") else \
            "its GraphQL operation %r is neither a query nor a mutation" % word
    if _text(path) is not None and any(c.fullmatch(_text(path)) for c in CREDENTIALS):
        return "credential"
    return "write"


def _edges(mods: dict, mod: Module) -> dict:
    """{function: [(module, function)]}: what each unit calls, or names as a value; a class named, each of its methods."""
    out = {}
    for qual, nodes in mod.units():
        cls, seen = qual.split(".")[0] if "." in qual else None, []
        for node in nodes:
            if not isinstance(node, (ast.Name, ast.Attribute)) or not isinstance(node.ctx, ast.Load):
                continue
            target = None
            if isinstance(node, ast.Name):
                bound = mod.bindings.get(node.id)
                if node.id in mod.functions or node.id in mod.classes:
                    target = (mod.name, node.id)
                elif bound and bound[0] == "attr" and bound[1] in mods:
                    target = (bound[1], bound[2])
            elif isinstance(node.value, ast.Name):
                if node.value.id == "self" and cls:
                    target = (mod.name, "%s.%s" % (cls, node.attr))
                elif mod.module(node.value.id) in mods:
                    target = (mod.module(node.value.id), node.attr)
            if target is None or target[0] not in mods:
                continue
            other = mods[target[0]]
            if target[1] in other.classes:
                seen += [(target[0], f) for f in other.functions if f.startswith(target[1] + ".")]
            elif target[1] in other.functions:
                seen.append(target)
        out[(mod.name, qual)] = seen
    return out


def _handed_on(mod: Module) -> list:
    """Where `mod` uses an adapter module as a value, not by a name of it: what it reaches then cannot be read."""
    out, read = [], set()
    for node in ast.walk(mod.tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            read.add(id(node.value))
    for node in ast.walk(mod.tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and id(node) not in read \
                and (mod.module(node.id) or "").startswith("adapters"):
            out.append("%s:%d uses the module %s as a value, so what it reaches cannot be read; name what it calls"
                       % (mod.rel, node.lineno, mod.module(node.id)))
    for node in ast.walk(mod.tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names) \
                and (node.module or "").startswith("adapters"):
            out.append("%s:%d imports * from %s, so what it reaches cannot be read; name what it calls"
                       % (mod.rel, node.lineno, node.module))
    return out


def _verbs(mod: Module) -> list:
    """The lines of `mod` that hold a write verb as a whole string, its docstrings aside."""
    docs = {id(n.body[0].value) for n in ast.walk(mod.tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return sorted({n.lineno for n in ast.walk(mod.tree) if isinstance(n, ast.Constant) and n.value in VERBS
                   and id(n) not in docs})


def reached(mods: dict, graph: dict, writers: set, start: tuple) -> set:
    """The writers `start` reaches, through any number of calls."""
    seen, todo, out = {start}, [start], set()
    while todo:
        here = todo.pop()
        if here in writers:
            out.add(here)
        for there in graph.get(here, []):
            if there not in seen:
                seen.add(there)
                todo.append(there)
    return out


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
    graph, writers = {}, set()
    for mod in mods.values():
        graph.update(_edges(mods, mod))
        adapter = mod.name.startswith("adapters.") or mod.name == "adapters"
        for qual, nodes in mod.units():
            for call, called in ([] if (mod.name, qual) in TRANSPORT else _requests(mod, nodes)):
                kind = _kind(mods, mod, call, called)
                if kind == "write" and adapter:
                    writers.add((mod.name, qual))
                elif kind == "write" or (kind not in ("read", "credential") and not adapter):
                    problems.append("%s:%d sends a request that is not a read outside adapters/; a write to GitHub is an "
                                    "adapter's, which a caller in tools/check_writes.py's CALLERS reaches" % (mod.rel, call.lineno))
                elif kind not in ("read", "credential"):
                    problems.append("%s:%d sends a request whose kind cannot be read: %s; write it as a literal" %
                                    (mod.rel, call.lineno, kind))
        if not adapter:
            problems += _handed_on(mod)
            if mod.rel not in VERB_HOLDERS and mod.rel != "tools/check_writes.py":
                problems += ["%s:%d holds a write verb; a write to GitHub is an adapter's, and Python that only reads "
                             "a command's verb is named in tools/check_writes.py's VERB_HOLDERS" % (mod.rel, line)
                             for line in _verbs(mod)]
    for mod in sorted(mods.values(), key=lambda m: m.rel):
        if mod.name.startswith("adapters.") or mod.name == "adapters":
            continue
        reach = set()
        for qual, _ in mod.units():
            reach |= reached(mods, graph, writers, (mod.name, qual))
        found = {"%s:%s" % w for w in reach}
        listed = CALLERS.get(mod.rel)
        if found and listed is None:
            problems.append("%s reaches a GitHub write, %s, and is not in tools/check_writes.py's CALLERS; a new writer "
                            "is the Maintainer's to allow, in the change that adds it" % (mod.rel, ", ".join(sorted(found))))
        elif listed is not None and found != listed:
            problems.append("%s reaches %s, and CALLERS lists %s; name what it reaches, in the change that changes it" %
                            (mod.rel, ", ".join(sorted(found)) or "no write", ", ".join(sorted(listed))))
    problems += ["CALLERS names %s, which is not here; take it off" % rel for rel in sorted(CALLERS) if _name(rel) not in mods]
    return problems
