"""The Apps' permissions: each is needed by something, a write by a write, and the reader writes nothing.

Each need is a code. `effect:` is an Effect a Result requests and `apply` makes; `write:` is a write
the Controller makes that is not an Effect; `read:` is something read. Its schema names the codes.
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
READER = "reader"
WRITES = ("effect:", "write:")


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
    problems = []
    for app, entry in sorted(apps.items()):
        permissions = entry.get("permissions") if isinstance(entry, dict) else None
        if not isinstance(permissions, dict):
            problems.append("%s: no permissions can be read; give the App an object of permissions" % app)
            continue
        for name, grant in sorted(permissions.items()):
            grant = grant if isinstance(grant, dict) else {}
            level, needs = grant.get("level"), grant.get("needs")
            needs = [n for n in needs if isinstance(n, str)] if isinstance(needs, list) else []
            writes = [n for n in needs if n.startswith(WRITES)]
            if not needs:
                problems.append("%s: %s names no Effect, write or read that needs it; state the need or remove "
                                "the permission" % (app, name))
            if level not in ("read", "write"):
                problems.append("%s: %s has the level %r; GitHub's levels are read and write" % (app, name, level))
            if app == READER:
                if level == "write":
                    problems.append("reader: %s is write; the reader App writes nothing, so make it read" % name)
                for need in writes:
                    problems.append("reader: %s serves %s; the reader App writes nothing, so move the need to "
                                    "the App of the Role that makes it" % (name, need))
            elif level == "write" and needs and not writes:
                problems.append("%s: %s is write and only a read needs it; make it read" % (app, name))
            elif level == "read":
                for need in writes:
                    problems.append("%s: %s is read and serves %s, which needs write; make it write or move the "
                                    "need" % (app, name, need))
            for need in needs:
                if need.startswith("read:facts.") and need[len("read:facts."):] not in facts:
                    problems.append("%s: %s reads %s, which is not a field of facts/1; name a field in "
                                    "schemas/facts.schema.json" % (app, name, need[len("read:"):]))
    return problems
