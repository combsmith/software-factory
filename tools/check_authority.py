"""Mechanical checks on who decides what: who owns each category of Finding, and that nothing speaks for a Lens."""
from __future__ import annotations

import ast
import json
import re
import pathlib

from kernel import terms
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
# A Role's name, as role/1 spells one (schemas/role.schema.json).
ROLE_NAME = re.compile(r"[a-z][a-z-]*[a-z]")
MODEL_JUDGED = {"functional", "security", "architecture", "delivery", "reliability",
                "requirements", "uncategorised"}
# What opens a pull request for the Factory, read from the code's syntax (issue 808): an adapter that sends a write to a
# repo's pulls, which only an opening does; a step of the Harness that tools/check_writes.py's CALLERS lists as reaching
# it; and, in that step's module, a call of harness/apply.py's `opened`, which records the Run that opened the pull
# request (decision 0097). The writer of "Acceptance: a pull request the Factory opens is bound to its issue by the Run
# that opened it" (issue 342) is what makes all three true.
OPENS = re.compile(r"/repos/%s/pulls")


def _folded(name: str) -> str:
    """A name as a reader that ignores case and the space around it would read it."""
    return name.strip().casefold()


def manifests(root: pathlib.Path = ROOT) -> dict:
    """Each Role manifest in `roles/`, by its file's name; one that cannot be read is None, and `team` says so."""
    out = {}
    for p in sorted((root / "roles").glob("*.json")):
        try:
            out[p.name[: -len(".json")]] = json.loads(p.read_text())
        except (OSError, ValueError):
            out[p.name[: -len(".json")]] = None
    return out


def _parsed(path: pathlib.Path):
    """A Python file's syntax, or None where it cannot be read."""
    try:
        return ast.parse(path.read_text(encoding="utf-8"), str(path))
    except (OSError, SyntaxError, ValueError, UnicodeDecodeError):
        return None


def _functions(tree):
    """Each top-level function of a module, and each method of a top-level class, by the name tools/check_writes.py
    gives a writer: `name`, or `Class.name`."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name, node
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield "%s.%s" % (node.name, item.name), item


def openers(root: pathlib.Path = None) -> set:
    """The adapter functions that open a pull request, as `adapters.module:function`: each builds a request whose method
    is a write, one of tools/check_writes.py's VERBS, and whose path is written as text, a repo's pulls and nothing
    after it. A method or a path that is not text is no opening: what is not read is not counted as the writer."""
    from tools.check_writes import VERBS
    found = set()
    for path in sorted(((ROOT if root is None else root) / "adapters").glob("*.py")):
        tree = _parsed(path)
        for name, fn in _functions(tree) if tree is not None else ():
            for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call) and len(n.args) >= 2):
                called = call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", None)
                verb, where = call.args[0], call.args[1]
                where = where.left if isinstance(where, ast.BinOp) and isinstance(where.op, ast.Mod) else where
                if (called == "request" and isinstance(verb, ast.Constant) and verb.value in VERBS
                        and isinstance(where, ast.Constant) and isinstance(where.value, str) and OPENS.fullmatch(where.value)):
                    found.add("adapters.%s:%s" % (path.stem, name))
    return found


def records_the_opening(tree, rel: str) -> bool:
    """Whether a module calls harness/apply.py's `opened`: by that name imported from harness.apply, as an attribute of
    harness.apply however it is imported, or, in harness/apply.py, by its own name."""
    names, modules = {"opened"} if rel == "harness/apply.py" else set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "harness.apply":
            names |= {a.asname or a.name for a in node.names if a.name == "opened"}
        elif isinstance(node, ast.ImportFrom) and node.module == "harness":
            modules |= {a.asname or a.name for a in node.names if a.name == "apply"}
        elif isinstance(node, ast.Import):
            modules |= {a.asname for a in node.names if a.name == "harness.apply" and a.asname}
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        f = call.func
        if isinstance(f, ast.Name) and f.id in names:
            return True
        if isinstance(f, ast.Attribute) and f.attr == "opened" and (
                isinstance(f.value, ast.Name) and f.value.id in modules
                or isinstance(f.value, ast.Attribute) and f.value.attr == "apply"
                and isinstance(f.value.value, ast.Name) and f.value.value.id == "harness"):
            return True
    return False


def opening_problems(config: dict, root: pathlib.Path = None, callers: dict = None) -> list:
    """A configuration that names a Role for `open-pull-request` while `open_pull_request` has no writer, with the first
    part of the writer missing (OPENS): the gap a pull request's author's closing link leaves must not outlive the
    first Role named to open pull requests (issue 808, restating issue 295's limit). None named, as in slice 1, passes."""
    issues = config.get("issues") if isinstance(config, dict) else None
    intents = issues.get("intents") if isinstance(issues, dict) else None
    if not isinstance(intents, dict) or intents.get("open-pull-request") is None:
        return []
    from tools.check_writes import CALLERS
    root, callers = ROOT if root is None else root, CALLERS if callers is None else callers
    said = "the configuration names a Role to open pull requests, and "
    found = openers(root)
    if not found:
        return [said + "no adapter sends a write to a repo's pulls; name none until open_pull_request has its writer (issue 342)"]
    reaching = sorted(rel for rel, writers in callers.items() if rel.startswith("harness/") and set(writers) & found)
    if not reaching:
        return [said + "no step of the Harness reaches %s as tools/check_writes.py's CALLERS lists; name none until one "
                "does (issue 342)" % ", ".join(sorted(found))]
    if not any(records_the_opening(tree, rel) for rel in reaching for tree in [_parsed(root / rel)] if tree is not None):
        return [said + "%s, which reach the opening, never call harness/apply.py's opened to record the Run that opened "
                "it; name none until one does (issue 342)" % ", ".join(reaching)]
    return []


def _read(path: pathlib.Path):
    """A JSON file, or None where it cannot be read."""
    try:
        return json.loads(path.read_text()) if path.is_file() else None
    except (OSError, ValueError):
        return None


def team(roles: dict, authority: dict, apps: dict, live, root: pathlib.Path = ROOT) -> list:
    """Section 5.4's checks over every Role manifest (issue 194's ruling 8, decision 0059): each category one owner, the
    one the authority table names, whose `owns` is exactly what it names; each permitted Effect within the ceiling of
    the Role's own App, which no other Role shares (L-44); every Intent of class `gate` naming an eval set of its own
    Role and Intent; a shadow's Intents writing nothing and spending from `shadow`; each manifest named as its file and
    held to `role/1`."""
    problems = []
    cats = authority["categories"]
    # The Controller's App, the reader's and the release App are no Role's, and a Role writes through none of them.
    no_role = {entry.get("name") for key, entry in apps["apps"].items() if key in ("controller", "reader", "release")}
    unread = sorted(stem for stem, m in roles.items() if not isinstance(m, dict))
    for stem in unread:
        problems.append("roles/%s.json cannot be read as a manifest" % stem)
    # A manifest is held to role/1 before anything is read from it: one of another shape is a problem, never a
    # traceback, and nothing else is read from it (issue 330).
    # role/1 and the one schema it refers to, and no other, so a fault elsewhere is not this check's (CodeRabbit's read).
    schemas = {name: json.loads((ROOT / "schemas" / ("%s.schema.json" % name)).read_text()) for name in ("role", "effect")}
    shaped = {}
    for stem, m in sorted(roles.items()):
        if not isinstance(m, dict):
            continue
        wrong = validate(m, schemas["role"], schemas=schemas)
        if wrong:
            problems.append("roles/%s.json does not hold to role/1: %s" % (stem, wrong[0]))
        else:
            shaped[stem] = m
    roles = shaped
    # The authority table names a person and nobody by these words: no Role is either.
    for stem, m in sorted(roles.items()):
        if m["name"] in ("human", "none"):
            problems.append("roles/%s.json names a Role %r, which the authority table reads as no Role" % (stem, m["name"]))
    for stem, m in sorted(roles.items()):
        name = m.get("name")
        if name != stem:
            problems.append("roles/%s.json names the Role %r; a manifest is named as its file" % (stem, name))
        if live.get("roles/%s.json" % stem) != "role":
            problems.append("roles/%s.json is held to no schema; add it to LIVE in tools/check_examples.py" % stem)
        owns = set(m.get("owns", ()))
        named = {c for c, entry in cats.items() if entry.get("owner") == name}
        # A Role the table names an owner is an owner, owning exactly what the table names (Argon's read).
        if named and m.get("kind") != "owner":
            problems.append("%s is named the owner of %s by the authority table, and is no owner" % (name, sorted(named)))
        if (m.get("kind") == "owner" or named) and owns != named:
            problems.append("%s owns %s, and the authority table names it the owner of %s; they must agree"
                            % (name, sorted(owns), sorted(named)))
        if m.get("kind") != "owner" and owns:
            problems.append("%s owns %s, and only an owner owns a category" % (name, sorted(owns)))
        intents = m.get("intents", [])
        if m.get("kind") == "shadow":
            for i in intents:
                if i.get("permitted_effects") or i.get("budget_class") != "shadow":
                    problems.append("%s is a shadow, and its Intent %s writes or spends from %s; a shadow writes "
                                    "nothing and spends from shadow" % (name, i.get("name"), i.get("budget_class")))
        # An Intent that writes spends from gate, so it is held to an eval set before it can write.
        for i in intents:
            if i.get("permitted_effects") and i.get("budget_class") != "gate":
                problems.append("%s's Intent %s writes and spends from %s; an Intent that writes spends from gate"
                                % (name, i.get("name"), i.get("budget_class")))
        if m.get("app") in no_role:
            problems.append("%s names %s, which is no Role's App" % (name, m["app"]))
        effects = sorted({e for i in intents for e in i.get("permitted_effects", ())})
        app = next((entry for entry in apps["apps"].values() if entry.get("name") == m.get("app")), None)
        if (effects or "app" in m) and app is None:
            problems.append("%s permits %s and names no App of config/apps.json to write them through"
                            % (name, effects))
        for effect in effects if app is not None else ():
            need = "effect:" + effect
            grant = apps["needs"].get(need, {})
            grants = app.get("permissions") if isinstance(app.get("permissions"), dict) else {}
            held = grants.get(grant.get("permission"), {}) if "permission" in grant else {}
            levels = ("read", "write")
            if (need not in held.get("needs", ()) or held.get("level") not in levels
                    or levels.index(held["level"]) < levels.index(grant.get("level", "write"))):
                problems.append("%s permits %s, beyond the ceiling of its App %s; grant it, or permit it no more"
                                % (name, effect, m.get("app")))
        for i in intents:
            if i.get("budget_class") != "gate":
                continue
            found = _read(root / (i.get("evals", "") + "/cases.json"))
            if not isinstance(found, dict) or (found.get("role"), found.get("intent")) != (name, i.get("name")):
                problems.append("%s's Intent %s spends from gate and names no eval set of its own at %s"
                                % (name, i.get("name"), i.get("evals")))
    # One owner a category: a Role the table names as owner has a manifest that owns it, and no two own one.
    owners = {}
    for m in roles.values():
        for c in m.get("owns", ()):
            owners.setdefault(c, []).append(m.get("name"))
    for c, names in sorted(owners.items()):
        if len(names) > 1:
            problems.append("%s is owned by %s; a category has one owner" % (c, sorted(names)))
    for c, entry in sorted(cats.items()):
        owner = entry.get("owner")
        if owner not in ("none", "human") and owner not in {m.get("name") for m in roles.values()}:
            problems.append("%s's owner %s has no manifest in roles/" % (c, owner))
    # Each Role writes through its own App, and no two share one (L-44).
    used = {}
    for m in roles.values():
        if m.get("app"):
            used.setdefault(m["app"], []).append(m.get("name"))
    for app, names in sorted(used.items()):
        if len(names) > 1:
            problems.append("%s write through one App, %s; each Role has its own" % (sorted(names), app))
    return problems


def run(authority: dict = None, config: dict = None, facts: dict = None, result: dict = None, role: dict = None,
        case: dict = None, roles: dict = None, apps: dict = None) -> list:
    a = json.loads((ROOT / "config" / "authority.json").read_text()) if authority is None else authority
    c = json.loads((ROOT / "config" / "defaults.json").read_text()) if config is None else config
    problems = []
    # The configuration names the author Role the authority table names, or none while that Role has no manifest: a fix
    # Run dispatched to a Role with none fails at its read, on every pass, until the Run ceiling holds it (issue 675).
    if c["author_role"] is not None and a["author_role"] != c["author_role"]:
        problems.append("the author Role differs between the authority table and the configuration")
    # Each a Role's own name, as role/1 spells one, so it names no file outside roles/ (Muse); the owner always, the
    # author or none.
    for field in ("author_role", "owner_role"):
        name = c[field]
        if name is None and field == "author_role":
            continue
        if not (isinstance(name, str) and ROLE_NAME.fullmatch(name)):
            problems.append("the configuration's %s is %r, which is no Role's name" % (field, name))
        elif not (ROOT / "roles" / ("%s.json" % name)).is_file():
            problems.append("the configuration's %s is %r, and roles/ holds no %s.json%s"
                            % (field, name, name, "; name none until it does" if field == "author_role" else ""))
    problems += opening_problems(c)
    if a["max_rounds"] != c["limits"]["max_rounds"]:
        problems.append("max_rounds differs between the authority table and the configuration")
    # A Lens or a check named twice, deterministic or model, could pin two Apps or be read as the other, and which one
    # judges would be unclear. Names are compared folded, as a reader of names may fold them.
    lenses = c["required_lenses"]
    names = [lens["lens"] for lens in lenses["deterministic"]] + list(lenses["model"])
    checks = [lens["check"] for lens in lenses["deterministic"]]
    for what, listed in (("Lens", names), ("check", checks)):
        seen = set()
        for name in listed:
            if _folded(name) in seen:
                problems.append("the %s %r is named twice in required_lenses; name each once" % (what, name))
            seen.add(_folded(name))
    # The Controller posts the status on the item as a check run. Under a required Lens's name, or the name of its
    # check, it would speak for that Lens.
    if _folded(c["status_on_item"]) in {_folded(name) for name in names + checks}:
        problems.append("the status on the item is named %r, a required Lens's or its check's; give it a name no Lens "
                        "or check has" % c["status_on_item"])
    cats = a["categories"]
    finding = json.loads((ROOT / "schemas" / "finding.schema.json").read_text())
    known = set(finding["properties"]["category"]["enum"])
    for name in sorted(known - set(cats)):
        problems.append("a Finding may carry the category %s, and nobody owns it" % name)
    for name in sorted(set(cats) - known):
        problems.append("%s has an owner, and no Finding can carry it" % name)
    # A thread in the facts carries its Finding's category, in the same terms, or null where a Lens writes it as prose.
    # The Kernel reads a required Lens's thread only in those terms, and its severity only in the Finding's.
    f = json.loads((ROOT / "schemas" / "facts.schema.json").read_text()) if facts is None else facts
    fields = f.get("properties", {}).get("threads", {}).get("items", {}).get("properties", {})
    if not isinstance(fields.get("category"), dict) or not isinstance(fields["category"].get("enum"), list):
        problems.append("a thread in the facts carries no category")
        on_threads = set()
    else:
        on_threads = set(fields["category"]["enum"]) - {None}
    for name in sorted(on_threads - known):
        problems.append("a thread may carry the category %s, and no Finding can" % name)
    for name in sorted(known - on_threads):
        problems.append("a Finding may carry the category %s, and no thread can" % name)
    # A Role raises a Finding in its Result, in the same terms as the Finding record apply writes from it.
    r = json.loads((ROOT / "schemas" / "result.schema.json").read_text()) if result is None else result
    raised = r.get("$defs", {}).get("raised", {}).get("properties", {})
    for field, held in (("category", known), ("severity", set(finding["properties"]["severity"]["enum"]))):
        if not isinstance(raised.get(field), dict) or not isinstance(raised[field].get("enum"), list):
            problems.append("a raised Finding in a Result carries no %s" % field)
            continue
        for name in sorted(set(raised[field]["enum"]) - held):
            problems.append("a raised Finding may carry the %s %s, and no Finding record can" % (field, name))
        for name in sorted(held - set(raised[field]["enum"])):
            problems.append("a Finding record may carry the %s %s, and no raised Finding can" % (field, name))
    # A Role manifest names what it owns, shadows and raises in the Finding's categories, and no others.
    m = json.loads((ROOT / "schemas" / "role.schema.json").read_text()) if role is None else role
    named = {"owns": m.get("properties", {}).get("owns"), "shadows": m.get("properties", {}).get("shadows"),
             "raises": m.get("properties", {}).get("lens", {}).get("properties", {}).get("raises")}
    for field, held in sorted(named.items()):
        listed = held.get("items", {}).get("enum") if isinstance(held, dict) else None
        if not isinstance(listed, list):
            problems.append("a Role manifest's %s names no category" % field)
            continue
        for name in sorted(set(listed) - known):
            problems.append("a Role manifest may %s the category %s, and no Finding can carry it" % (field.rstrip("s"), name))
        for name in sorted(known - set(listed)):
            problems.append("a Finding may carry the category %s, and no Role manifest can %s it" % (name, field.rstrip("s")))
    # A held-out case expects a Finding in the Finding's own categories and severities, and no others.
    e = json.loads((ROOT / "schemas" / "eval-case.schema.json").read_text()) if case is None else case
    answer = e.get("properties", {}).get("expected", {}).get("properties", {}).get("finding", {}).get("properties", {})
    expected_in = (("category", known), ("severity", set(finding["properties"]["severity"]["enum"])))
    for field, held in expected_in:
        listed = answer.get(field, {}).get("enum") if isinstance(answer.get(field), dict) else None
        if not isinstance(listed, list):
            problems.append("a held-out case's expected Finding carries no %s" % field)
            continue
        for name in sorted(set(listed) - held):
            problems.append("a held-out case may expect the %s %s, and no Finding can carry it" % (field, name))
        for name in sorted(held - set(listed)):
            problems.append("a Finding may carry the %s %s, and no held-out case can expect it" % (field, name))
    if set(terms.CATEGORIES) != known:
        problems.append("the Kernel reads the categories %s, and a Finding carries %s"
                        % (sorted(terms.CATEGORIES), sorted(known)))
    if set(terms.SEVERITIES) != set(finding["properties"]["severity"]["enum"]):
        problems.append("the Kernel reads the severities %s, and a Finding carries %s"
                        % (sorted(terms.SEVERITIES), sorted(finding["properties"]["severity"]["enum"])))
    for name in sorted(MODEL_JUDGED - set(cats)):
        problems.append("category has no owner: %s" % name)
    for name, c in sorted(cats.items()):
        owner = c["owner"]
        if name in MODEL_JUDGED and owner in ("none", "human"):
            problems.append("%s is judged by a model and needs a Role as owner" % name)
        if owner == a["author_role"]:
            problems.append("%s: the author Role may not own a category" % name)
        if c.get("shadow") == owner:
            problems.append("%s: a Role cannot shadow itself" % name)
        if c.get("shadow") == a["author_role"]:
            problems.append("%s: the author Role may not shadow a category" % name)
    weak = set(cats.get("security", {}).get("may_accept", [])) & {"declined", "deferred"}
    if weak:
        problems.append("a security Finding may never be accepted as: %s" % sorted(weak))
    from tools.check_examples import LIVE
    problems += team(manifests() if roles is None else roles, a,
                     json.loads((ROOT / "config" / "apps.json").read_text()) if apps is None else apps, LIVE)
    return problems
