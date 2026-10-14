"""The fixtures of the platform trials, and the fake GitHub's grounding in them (design, sections 4.5 and 6).

A fixture in `trials/` is what one trial sent to GitHub in the canary repo and what came back,
with every credential removed. It validates against `schemas/trial.schema.json`, and nothing else
is kept there. A credential is refused here and not by the schema, which cannot express it.

Each rule the fake GitHub applies is listed in `sim/grounding.py` and marked where `sim/world.py`
applies it. A fixture named there must exist and be valid. A rule with no fixture is unverified,
and `verify` prints it.

Nothing in this repo reads the canary at run time: a fixture arrives by pull request. So no code
and no workflow names the canary.
"""
from __future__ import annotations

import ast
import pathlib
import re

from tools.check_examples import _load
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP = {".git", "__pycache__", "corpus"}
# Named in data and in documents. Code or a workflow that names it could read it.
CANARY = "software-factory-" + "canary"
FIXTURE = re.compile(r"^(P-[1-9][0-9]*)(\.[a-z0-9-]+)?\.json$")
TRIAL = re.compile(r"^P-[1-9][0-9]*$")
CODE = re.compile(r"^[a-z_]+$")
MARK = re.compile(r"^\s*# GitHub: (\S+)\s*$", re.M)
# A field that holds a credential, however it is spelt. Leave the field out, and list where in `removed`.
FIELDS = {"authorization", "proxy-authorization", "cookie", "set-cookie", "token", "access_token", "refresh_token",
          "id_token", "password", "secret", "client_secret", "private_key", "api_key", "x-api-key"}
# The start of a credential, at any length: a token GitHub issues, a bearer header, a signed JWT, a key.
SHAPES = re.compile(r"\bgh[opsur]_|\bgithub_pat_|\b[Bb]earer\s+\S|\beyJ[A-Za-z0-9_-]{8,}\.|-----BEGIN [A-Z ]*PRIVATE KEY")


def _credentials(value, where: str) -> list:
    """(path, what is wrong) for each credential's field and each credential-shaped string in `value`."""
    out = []
    if isinstance(value, dict):
        for key, item in value.items():
            here = "%s.%s" % (where, key) if where else key
            if key.lower() in FIELDS:
                out.append((here, "is a field for a credential; leave it out, and list where in removed"))
            out += _credentials(item, here)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            out += _credentials(item, "%s[%d]" % (where, i))
    elif isinstance(value, str) and SHAPES.search(value):
        out.append((where or "$", "holds something shaped like a credential"))
    return out


def rules(root: pathlib.Path = ROOT) -> list:
    """The rules in `sim/grounding.py`, read as a literal; a ValueError says why they cannot be."""
    path = root / "sim" / "grounding.py"
    try:
        tree = ast.parse(path.read_text(), str(path))
    except (OSError, SyntaxError) as err:
        raise ValueError("cannot be read: %s" % err)
    for node in tree.body:
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == ["RULES"]:
            try:
                found = ast.literal_eval(node.value)
            except ValueError:
                raise ValueError("RULES must be a literal, so that a check can read it")
            if not isinstance(found, (tuple, list)) or not all(isinstance(r, tuple) and len(r) == 4 for r in found):
                raise ValueError("RULES must be a tuple of (code, rule, trial, fixture)")
            return list(found)
    raise ValueError("holds no RULES")


def _fixtures(root: pathlib.Path, schema: dict, problems: list) -> dict:
    """{path: the fixture} for each valid fixture in trials/; each problem found is recorded."""
    folder, valid = root / "trials", {}
    for path in sorted(folder.iterdir()) if folder.is_dir() else []:
        rel, name = "trials/%s" % path.name, FIXTURE.match(path.name)
        if path.name == "AGENTS.md":
            continue
        if not path.is_file() or not name:
            problems.append("%s: trials/ holds fixtures only, named <trial>.json or <trial>.<what>.json" % rel)
            continue
        try:
            data = _load(path)
        except (OSError, ValueError) as err:
            problems.append("%s cannot be read: %s" % (rel, err))
            continue
        wrong = ["%s: %s" % (rel, err) for err in validate(data, schema)]
        if not wrong and data["trial"] != name.group(1):
            wrong.append("%s: records trial %s; a fixture is named for its trial" % (rel, data["trial"]))
        wrong += ["%s: %s %s" % (rel, where, what) for where, what in _credentials(data, "")]
        problems += wrong
        if not wrong:
            valid[rel] = data
    return valid


def _grounding(root: pathlib.Path, valid: dict, problems: list) -> None:
    try:
        listed = rules(root)
    except ValueError as err:
        problems.append("sim/grounding.py: %s" % err)
        return
    seen = set()
    for code, rule, trial, fixture in listed:
        if not isinstance(code, str) or not CODE.match(code):
            problems.append("sim/grounding.py: %r is not a code" % (code,))
            continue
        if code in seen:
            problems.append("sim/grounding.py: %s is listed twice" % code)
        seen.add(code)
        if not isinstance(rule, str) or not rule:
            problems.append("sim/grounding.py: %s states no rule" % code)
        if trial is not None and not (isinstance(trial, str) and TRIAL.match(trial)):
            problems.append("sim/grounding.py: %s names %r, which is not a trial of section 6" % (code, trial))
        if fixture is None:
            continue
        if not isinstance(fixture, str) or not fixture.startswith("trials/"):
            problems.append("sim/grounding.py: %s: %s is not a fixture in trials/" % (code, fixture))
        elif not (root / fixture).is_file():
            problems.append("sim/grounding.py: %s: %s does not exist" % (code, fixture))
        elif fixture not in valid:
            problems.append("sim/grounding.py: %s: %s is not a valid fixture" % (code, fixture))
        elif valid[fixture]["trial"] != trial:
            problems.append("sim/grounding.py: %s: %s records %s, and %s asks this"
                            % (code, fixture, valid[fixture]["trial"], trial))
    world = root / "sim" / "world.py"
    marked = set(MARK.findall(world.read_text())) if world.exists() else set()
    for code in sorted(marked - seen):
        problems.append("sim/world.py applies %s, which sim/grounding.py does not list" % code)
    for code in sorted(seen - marked):
        problems.append("%s is listed in sim/grounding.py and applied nowhere in sim/world.py; mark it "
                        "'# GitHub: %s' where it is applied, or take it out" % (code, code))


def _code(root: pathlib.Path) -> list:
    """Each file of code or workflow that names the canary, and so could read it at run time."""
    found = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if SKIP & set(rel.parts) or not path.is_file():
            continue
        workflow = rel.parts[0] == ".github" and path.suffix in (".yml", ".yaml")
        if (path.suffix == ".py" or workflow) and CANARY in path.read_text(errors="replace"):
            found.append("%s: names the canary repo; nothing here reads it, and a fixture arrives by pull request"
                         % rel)
    return found


def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    try:
        schema = _load(root / "schemas" / "trial.schema.json")
    except (OSError, ValueError) as err:
        return ["schemas/trial.schema.json cannot be read: %s" % err]
    valid = _fixtures(root, schema, problems)
    example = root / "examples" / "trial.json"
    if example.exists():
        try:
            data = _load(example)
        except ValueError:
            data = None     # check_examples reports it
        problems += ["examples/trial.json: %s %s" % (where, what) for where, what in _credentials(data, "")]
    _grounding(root, valid, problems)
    return problems + _code(root)


def unverified(root: pathlib.Path = ROOT) -> list:
    """Each rule of the fake GitHub that no fixture grounds, as a line `verify` prints."""
    try:
        listed = rules(root)
    except ValueError:
        return []           # run() reports it
    return ["%s: %s (%s)" % (code, rule, trial or "no trial asks it")
            for code, rule, trial, fixture in listed if fixture is None]
