"""The Apps' permissions: each serves a need, as the table of needs maps it, and the reader writes nothing.

A need is a code. `effect:` is an Effect a Result requests and `apply` makes; `write:` is a write
the Controller makes that is not an Effect; `read:` is something read. The table in
`config/apps.json` maps each need to one GitHub permission and level, or says what it waits on.
A write permission serves a read of the same permission too, since GitHub's write includes read.
"""
from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
READER = "reader"
PREFIX = "combsmith-sf-"
WRITES = ("effect:", "write:")
FACT = "read:facts."
REPO = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9._-]*$")


def _table(needs: dict, facts: set) -> list:
    problems = []
    for code, entry in sorted(needs.items()):
        entry = entry if isinstance(entry, dict) else {}
        mapped = "permission" in entry or "level" in entry
        if mapped and "waits_on" in entry:
            problems.append("%s both maps to a permission and waits; keep one" % code)
        elif not mapped and "waits_on" not in entry:
            problems.append("%s maps to no permission and waits on nothing; map it or say what it waits on" % code)
        elif mapped and not ("permission" in entry and "level" in entry):
            problems.append("%s maps to a permission with no level, or a level with no permission; give both" % code)
        if code.startswith(FACT) and code[len(FACT):] not in facts:
            problems.append("%s reads a field facts/1 does not have; name a field in schemas/facts.schema.json"
                            % code)
    return problems


def _grant(app: str, name: str, grant, needs: dict) -> list:
    problems = []
    grant = grant if isinstance(grant, dict) else {}
    level, served = grant.get("level"), grant.get("needs")
    served = [n for n in served if isinstance(n, str)] if isinstance(served, list) else []
    writes = [n for n in served if n.startswith(WRITES)]
    if not served:
        problems.append("%s: %s names no Effect, write or read that needs it; state the need or remove the "
                        "permission" % (app, name))
    if level not in ("read", "write"):
        problems.append("%s: %s has the level %r; GitHub's levels are read and write" % (app, name, level))
    if app == READER:
        if level == "write":
            problems.append("reader: %s is write; the reader App writes nothing, so make it read" % name)
        for need in writes:
            problems.append("reader: %s serves %s; the reader App writes nothing, so move the need to the App of "
                            "the Role that makes it" % (name, need))
    elif level == "write" and served and not writes:
        problems.append("%s: %s is write and only a read needs it; make it read" % (app, name))
    for need in served:
        entry = needs.get(need)
        if not isinstance(entry, dict):
            problems.append("%s: %s serves %s, which is not in the table of needs; add it there first"
                            % (app, name, need))
        elif "waits_on" in entry:
            problems.append("%s: %s serves %s, which waits on %s; take the need out until it is settled"
                            % (app, name, need, entry["waits_on"]))
        elif entry.get("permission") != name:
            problems.append("%s: %s serves %s, which the table maps to %s; move the need there"
                            % (app, name, need, entry.get("permission")))
        elif entry.get("level") == "write" and level != "write":
            problems.append("%s: %s is %s and serves %s, which the table maps to %s write; make it write or move "
                            "the need" % (app, name, level, need, name))
    return problems


def run(root: pathlib.Path = ROOT) -> list:
    try:
        table = json.loads((root / "config" / "apps.json").read_text())
    except (OSError, ValueError) as err:
        return ["config/apps.json cannot be read: %s" % err]
    apps = table.get("apps") if isinstance(table, dict) else None
    if not isinstance(apps, dict) or not apps:
        return ["config/apps.json names no Apps; give each App its permissions under apps"]
    try:
        facts = set(json.loads((root / "schemas" / "facts.schema.json").read_text())["properties"])
    except (OSError, ValueError, KeyError) as err:
        return ["schemas/facts.schema.json cannot be read, so no read of a fact can be checked: %s" % err]
    needs = table.get("needs")
    if not isinstance(needs, dict):
        return ["config/apps.json has no table of needs; map each need under needs"]
    problems = _table(needs, facts)
    holders = {}
    for app, entry in sorted(apps.items()):
        entry = entry if isinstance(entry, dict) else {}
        if entry.get("name") != PREFIX + app:
            problems.append("%s: the App is named %s; name it %s%s" % (app, entry.get("name"), PREFIX, app))
        repos = entry.get("installed_on") if isinstance(entry.get("installed_on"), list) else []
        if not repos or not all(isinstance(r, str) and REPO.match(r) for r in repos):
            problems.append("%s: installed_on is not a list of named repos; until a Consumer repo is served "
                            "(slice 3), install each App on named repos only, never the whole org" % app)
        for repo in sorted({r for r in repos if repos.count(r) > 1}, key=str):
            problems.append("%s: %s is named twice in installed_on; name each repo once" % (app, repo))
        permissions = entry.get("permissions")
        if not isinstance(permissions, dict):
            problems.append("%s: no permissions can be read; give the App an object of permissions" % app)
            continue
        for name, grant in sorted(permissions.items()):
            problems += _grant(app, name, grant, needs)
            for need in grant.get("needs", []) if isinstance(grant, dict) else []:
                if isinstance(need, str) and need.startswith(WRITES):
                    holders.setdefault(need, set()).add(app)
    for need, held in sorted(holders.items()):
        if len(held) > 1:
            problems.append("%s is held by %s; a write need belongs to one App" % (need, " and ".join(sorted(held))))
    return problems
