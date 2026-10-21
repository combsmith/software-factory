"""The Apps' permissions: each serves a need, as the table of needs maps it, and the reader writes nothing.

A need is a code. `effect:` is an Effect a Result requests and `apply` makes; `write:` is a write
the Controller makes that is not an Effect; `read:` is something read. The table in
`config/apps.json` maps each need to one GitHub permission and level, or says what it waits on.
No App holds `workflows` or `security_events` (NEVER).
A write permission serves a read of the same permission too, since GitHub's write includes read.

The data is held to what GitHub granted (decision 0035). Trial P-39's fixtures record each App's
registration, the org's installations as GitHub listed them, and the repos each installation
reaches. Each fixture's verdict is `pass`, each read was answered 200, and each list was read
whole: one page, each item once, as many as it counts. For each App, its registration and its
installation are of its `app_id` and its name, with exactly the permissions and levels here and no
events; the installation is on `selected` repos; and it reaches exactly `installed_on`. Anything short of that is a fail, and no key is stored. Each App's
key is kept in the environment of the one job that holds it (design §4.9): the Controller's in the
poller's, the reader's in `run`'s, and each Role's in `apply`'s. A job that names an environment
reads every secret in it, so no other job's environment may hold a key, and `run`, which reads
untrusted text, never holds one that writes. The secret is named for the App.
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
# Permissions no Factory App holds, at any level. Without `workflows` GitHub refuses an App's push under
# .github/workflows/, so a Role cannot change what a required Lens runs; with `security_events` an App could upload to
# code scanning under CodeQL's tool and category, and might stand for CodeQL's verdict (design, trial P-36).
NEVER = ("workflows", "security_events")
REPO = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9._-]*$")
# What trial P-39 recorded: in trials/P-39.json or a fixture of it, as P-39.grants.json and P-39.reach.json. Each read
# is found by its call: the org's installations, an App's registration, and the repos an installation reaches.
TRIAL = "P-39"
INSTALLATIONS = "GET /orgs/combsmith/installations"
REGISTRATION = "GET /apps/"
REACH = "GET /installation/repositories"
# A read that lists: the field its list is in, and the field each item of it is known by.
LISTS = {"installations": ("installations", "app_id"), "reach": ("repositories", "full_name")}
# The job that holds each App's key (design §4.9), and the environment each job names (decision 0035). Every App not
# named here is a Role's, whose key `apply` holds; so several Roles' keys share apply's environment, and nothing else.
HOLDER = {"controller": "poller", READER: "run"}
ROLE_HOLDER = "apply"
ENVIRONMENT = {"poller": "factory-poller", "apply": "factory-apply", "run": "factory-run"}


def _kind(call) -> str:
    """Which of P-39's reads a call is: installations, registration or reach; or "" for none of them."""
    if not isinstance(call, str):
        return ""
    if call == INSTALLATIONS:
        return "installations"
    if call.startswith(REGISTRATION):
        return "registration"
    if call == REACH or call.startswith(REACH + "?"):
        return "reach"
    return ""


def _short(kind: str, body: dict, headers) -> str:
    """Why a read that lists cannot be held to the data, or "" if it was read whole: one page, each item once."""
    field, key = LISTS[kind]
    listed = body.get(field)
    if not isinstance(listed, list):
        return "holds no list of %s" % field
    if isinstance(headers, dict) and any(str(name).lower() == "link" for name in headers):
        return "has a link header, so it is one page of more"
    keys = [item.get(key) if isinstance(item, dict) else None for item in listed]
    twice = sorted({str(k) for k in keys if keys.count(k) > 1})
    if twice:
        return "lists %s%s more than once" % ("App " if kind == "installations" else "", ", ".join(twice))
    if body.get("total_count") != len(set(map(str, keys))):
        return "lists %d of the %s it counts" % (len(listed), body.get("total_count"))
    return ""


def _reads(root: pathlib.Path) -> tuple:
    """({kind: [(fixture, who asked, body)]} for each read P-39 recorded, [problems with the fixtures])."""
    reads, problems = {"installations": [], "registration": [], "reach": []}, []
    paths = sorted((root / "trials").glob(TRIAL + ".json")) + sorted((root / "trials").glob(TRIAL + ".*.json"))
    for path in paths:
        rel = "trials/" + path.name
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as err:
            problems.append("%s cannot be read, so no App can be held to it: %s" % (rel, err))
            continue
        data = data if isinstance(data, dict) else {}
        if data.get("verdict") != "pass":
            problems.append("%s: its verdict is %s; P-39 passes only if each of its fixtures does, and no App's key is "
                            "stored until then, so correct the registration and run %s again"
                            % (rel, data.get("verdict"), TRIAL))
        exchanges = data.get("exchanges")
        for exchange in exchanges if isinstance(exchanges, list) else []:
            request = exchange.get("request") if isinstance(exchange, dict) else None
            kind = _kind(request.get("call")) if isinstance(request, dict) else ""
            if not kind:
                continue
            response = exchange.get("response") if isinstance(exchange.get("response"), dict) else {}
            body = response.get("body")
            if response.get("status") != 200 or not isinstance(body, dict):
                problems.append("%s: its read %s was answered %s, not 200, so it holds nothing GitHub granted; run %s "
                                "again" % (rel, request.get("call"), response.get("status"), TRIAL))
                continue
            short = _short(kind, body, response.get("headers")) if kind in LISTS else ""
            if short:
                problems.append("%s: its read %s %s; a list not read whole cannot be held to the data, so run %s "
                                "again" % (rel, request.get("call"), short, TRIAL))
                continue
            asker = request.get("as") if isinstance(request.get("as"), dict) else {}
            reads[kind].append((rel, asker.get("name"), body))
    if not reads["installations"]:
        problems.append("no fixture of trial %s in trials/ records %s, so no App's permissions can be held to what "
                        "GitHub granted; run %s and add its fixture" % (TRIAL, INSTALLATIONS, TRIAL))
    return reads, problems


def _levels(permissions) -> dict:
    return dict(permissions) if isinstance(permissions, dict) else {}


def _differ(app: str, want: dict, have: dict, seen: str) -> list:
    """Each permission whose level in the data differs from GitHub's, as `seen` says where."""
    return ["%s: %s is %s in the data and %s %s; they must agree exactly, so correct the registration and run %s again"
            % (app, name, want.get(name) or "absent", have.get(name) or "absent", seen, TRIAL)
            for name in sorted(set(want) | set(have)) if want.get(name) != have.get(name)]


def _granted(app: str, entry: dict, reads: dict) -> list:
    """Each way what GitHub registered, installed and reached for the App differs from the data."""
    app_id, name = entry.get("app_id"), entry.get("name")
    if type(app_id) is not int:
        return ["%s: has no app_id that is a whole number; give GitHub's id for the App" % app]
    permissions = entry.get("permissions") if isinstance(entry.get("permissions"), dict) else {}
    want = {need: (grant.get("level") if isinstance(grant, dict) else None) for need, grant in permissions.items()}
    problems = []
    for fixture, _, body in reads["installations"]:
        listed = body.get("installations") if isinstance(body.get("installations"), list) else []
        installation = next((i for i in listed if isinstance(i, dict) and i.get("app_id") == app_id), None)
        if installation is None:
            problems.append("%s: %s records no installation of App %d; install it, or correct app_id"
                            % (app, fixture, app_id))
            continue
        if installation.get("app_slug") != name:
            problems.append("%s: App %d is installed as %s in %s, and the data names it %s; correct app_id or the name"
                            % (app, app_id, installation.get("app_slug"), fixture, name))
        problems += _differ(app, want, _levels(installation.get("permissions")), "as GitHub granted it in " + fixture)
        if installation.get("events") != []:
            problems.append("%s: its installation in %s receives the events %s; the data asks for none, so take "
                            "them out of the registration" % (app, fixture, installation.get("events")))
        if installation.get("repository_selection") != "selected":
            problems.append("%s: its installation in %s has the selection %s; install it on selected repos only"
                            % (app, fixture, installation.get("repository_selection")))
    registered = [(fixture, body) for fixture, _, body in reads["registration"] if body.get("slug") == name]
    if not registered:
        problems.append("%s: no fixture of trial %s records %s%s, so the App's registration is unread; run %s again"
                        % (app, TRIAL, REGISTRATION, name, TRIAL))
    for fixture, body in registered:
        if body.get("id") != app_id:
            problems.append("%s: %s is registered as App %s in %s, and the data says %d; correct app_id"
                            % (app, name, body.get("id"), fixture, app_id))
        problems += _differ(app, want, _levels(body.get("permissions")), "as the App is registered in " + fixture)
        if body.get("events") != []:
            problems.append("%s: the App is registered in %s for the events %s; the data asks for none, so take "
                            "them out of the registration" % (app, fixture, body.get("events")))
    reached = [(fixture, body) for fixture, asker, body in reads["reach"] if asker == name]
    if not reached:
        problems.append("%s: no fixture of trial %s records %s read as %s, so which repos it reaches is unread; run "
                        "%s again" % (app, TRIAL, REACH, name, TRIAL))
    installed_on = entry.get("installed_on") if isinstance(entry.get("installed_on"), list) else []
    for fixture, body in reached:
        listed = body.get("repositories") if isinstance(body.get("repositories"), list) else []
        repos = sorted(str(r.get("full_name")) for r in listed if isinstance(r, dict))
        if body.get("repository_selection") != "selected":
            problems.append("%s: its installation reaches repos by the selection %s in %s; install it on selected "
                            "repos only" % (app, body.get("repository_selection"), fixture))
        if repos != sorted(str(r) for r in installed_on):
            problems.append("%s: its installation reaches %s in %s, and installed_on names %s; they must agree "
                            "exactly" % (app, ", ".join(repos) or "no repo", fixture,
                                         ", ".join(sorted(str(r) for r in installed_on)) or "none"))
    return problems


def _secret(app: str) -> str:
    """The name of the secret that holds the App's key: CONTROLLER_APP_KEY for controller."""
    return re.sub(r"[^A-Z0-9]", "_", app.upper()) + "_APP_KEY"


def _keys(apps: dict) -> list:
    """Each App whose key is not kept in the environment of the job that holds it, or not under its own name."""
    problems = []
    for app, entry in sorted(apps.items()):
        key = entry.get("key") if isinstance(entry, dict) else None
        environment = key.get("environment") if isinstance(key, dict) else None
        if not isinstance(environment, str) or not environment:
            problems.append("%s: names no environment its key is kept in; give it a key of environment and secret"
                            % app)
            continue
        job = HOLDER.get(app, ROLE_HOLDER)
        if environment != ENVIRONMENT[job]:
            problems.append("%s: its key is kept in %s, and the %s job holds it; a job reads every secret in the "
                            "environment it names, so keep it in %s" % (app, environment, job, ENVIRONMENT[job]))
        if key.get("secret") != _secret(app):
            problems.append("%s: its key is kept as %s; name it %s, for the App"
                            % (app, key.get("secret"), _secret(app)))
    return problems


def fields(schema: dict) -> set:
    """What a read of facts/1 may name: each of its fields, and each property of one of its definitions as
    definition.property, such as actor.can_write, which every actor the facts carry holds (decision 0046)."""
    named = set(schema["properties"])
    for name, definition in schema.get("$defs", {}).items():
        for prop in definition.get("properties", {}) if isinstance(definition, dict) else {}:
            named.add("%s.%s" % (name, prop))
    return named


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
            problems.append("%s reads a field facts/1 does not have; name a field in schemas/facts.schema.json, or a "
                            "property of one of its definitions as definition.property" % code)
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
        facts = fields(json.loads((root / "schemas" / "facts.schema.json").read_text()))
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
            if name in NEVER:
                problems.append("%s: holds %s; no Factory App may, at any level: take it out" % (app, name))
            problems += _grant(app, name, grant, needs)
            for need in grant.get("needs", []) if isinstance(grant, dict) else []:
                if isinstance(need, str) and need.startswith(WRITES):
                    holders.setdefault(need, set()).add(app)
    for need, held in sorted(holders.items()):
        if len(held) > 1:
            problems.append("%s is held by %s; a write need belongs to one App" % (need, " and ".join(sorted(held))))
    reads, unread = _reads(root)
    problems += unread
    for app, entry in sorted(apps.items()):
        problems += _granted(app, entry if isinstance(entry, dict) else {}, reads)
    return problems + _keys(apps)
