"""The fixtures of the platform trials, and the fake GitHub's grounding in them (design, sections 4.5 and 6).

A fixture in `trials/` is what one trial sent to GitHub in the canary repo, or of the org itself for a
trial about the org and its Apps (decision 0035), and what came back, with every credential removed.
`repo` is the org exactly when every call is of the org or its Apps. It validates against
`schemas/trial.schema.json`, and nothing else is kept there. A credential is refused here and not by
the schema, which cannot express it: `tools/redact_trial.py` applies the same rules to a raw capture
before anyone reads it.

Each rule the fake GitHub applies is listed in `sim/grounding.py` and marked where a world under
`sim/` applies it. A fixture named there must exist and be valid. A rule with no fixture is unverified,
and `verify` prints it.

Nothing in this repo reads the canary at run time: a fixture arrives by pull request. So nothing
names the canary but a document, a fixture and the fixture's schema, and the declaration of where
the Apps are installed (`config/apps.json`, its schema and its counter-examples), which is data the
Maintainer registers from and which nothing runs.

`python3 -m tools.check_trials` runs this check alone, before a fixture is added to git.
"""
from __future__ import annotations

import ast
import base64
import json
import pathlib
import re
import sys

from tools import walk
from tools.check_examples import _load
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Named in data and in documents. Anything else that names it could read it.
CANARY = "software-factory-" + "canary"
# A trial about the org and its Apps records the org as its repo, and only such a trial: one whose every call is a
# REST call of an App, of the org, or of an installation, with no segment that climbs out of it (decision 0035).
ORG = "combsmith"
ORG_CALL = re.compile(r"^[A-Z]+ /(apps/|orgs/%s/|installation/)" % ORG)
CLIMBS = re.compile(r"(^|/)\.{1,2}(/|$)|%2e", re.I)
FIXTURE = re.compile(r"^(P-[1-9][0-9]*)(\.[a-z0-9-]+)?\.json$")
TRIAL = re.compile(r"^P-[1-9][0-9]*$")
CODE = re.compile(r"^[a-z_]+$")
MARK = re.compile(r"^\s*# GitHub: (\S+)\s*$", re.M)

# A key that names a credential, however it is spelt: compared after strip(), lower() and - to _.
KEY_PARTS = ("token", "secret", "password", "credential", "jit_config", "otp", "cookie", "authorization")
KEY_WHOLE = {"auth", "jwt"}
KEY_HARMLESS = {"token_type", "input_tokens", "output_tokens", "total_tokens", "cache_creation_input_tokens",
                "cache_read_input_tokens"}
# The headers a fixture may keep, compared in lower case. Any other is left out: allow what is named.
HEADERS = {"accept", "cache-control", "content-length", "content-type", "date", "etag", "last-modified", "link",
           "location", "retry-after", "server", "user-agent", "vary", "x-accepted-github-permissions",
           "x-accepted-oauth-scopes", "x-github-api-version", "x-github-media-type", "x-github-request-id",
           "x-oauth-scopes", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
           "x-ratelimit-resource", "x-ratelimit-used"}
# What a credential looks like inside any string, at any length and in any case.
SHAPES = re.compile("|".join((
    r"gh[opsur]_[a-z0-9]",                          # a token GitHub issues, wherever it starts
    r"github_pat_", r"ghsat[0-9a-z]", r"sk-ant-",
    r"\b(token|basic|bearer)\s+\S{8,}", r"\bbearer\s+\S",
    r"eyJ[a-z0-9_-]*\.",                            # a signed token
    r"//[^/\s:@]+:[^/\s@]+@",                       # a user and password in a URL
    r"[?&](sig|token|access_token|x-amz-signature|x-amz-credential)=",
    r"\b(set-cookie|cookie|authorization|proxy-authorization)\s*:",
    r"(token|auth[a-z]*|bearer|secret|password)\W{0,3}[0-9a-f]{40}",
    r"encoded_jit_config", r"-----BEGIN [a-z ]*PRIVATE KEY",
    r"\bMII[a-z0-9+/]{20,}", r"b3BlbnNzaC1rZXktdjE",  # the body of a private key
)), re.I)
# A runner's registration token: the whole string, 29 of base32's capitals and digits.
REGISTRATION = re.compile(r"^[A-Z2-7]{29}$")
ENCODED = re.compile(r"[A-Za-z0-9+/_-]{20,}={0,2}")


def refused_key(key: str) -> bool:
    name = key.strip().lower().replace("-", "_")
    return name not in KEY_HARMLESS and (name in KEY_WHOLE or any(part in name for part in KEY_PARTS))


def _decoded(text: str) -> list:
    """Each run of base64 in `text` that decodes to text, however little of it prints."""
    out = []
    for run in ENCODED.findall(text):
        padded = run + "=" * (-len(run) % 4)
        for decode in (base64.b64decode, base64.urlsafe_b64decode):
            try:
                plain = decode(padded.encode()).decode("utf-8")
            except ValueError:     # not base64, or not text
                continue
            out.append(plain)
            break
    return out


def shaped(text: str, depth: int = 0) -> bool:
    """Whether `text` holds something shaped like a credential, plainly or in base64."""
    if SHAPES.search(text) or REGISTRATION.match(text):
        return True
    if depth:
        return False
    for plain in _decoded(text):
        try:
            if _credentials(json.loads(plain), ""):
                return True
        except ValueError:
            pass
        if shaped(plain, depth + 1):
            return True
    return False


def _credentials(value, where: str) -> list:
    """(path, what is wrong) for each credential's field and each credential-shaped string in `value`."""
    out = []
    if isinstance(value, dict):
        for key, item in value.items():
            here = "%s.%s" % (where, key) if where else key
            if refused_key(key):
                out.append((here, "is a field for a credential; leave it out, and list where in removed"))
            out += _credentials(item, here)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            out += _credentials(item, "%s[%d]" % (where, i))
    elif isinstance(value, str) and shaped(value):
        out.append((where or "$", "holds something shaped like a credential"))
    return out


def _askers(data) -> list:
    """(path, what is wrong) for who asked, and of what, beyond what the schema can say (decisions 0033, 0035).

    A trial of a vendor's CLI ran in no repo: `repo` is null exactly when every request is made as
    `subscription`. A trial about the org and its Apps records the org: `repo` is `combsmith` exactly
    when every call is of an App, the org or an installation. And an asker is named in words, never by
    an address, which could tie the fixture to an account at a vendor.
    """
    out = []
    exchanges = data.get("exchanges") if isinstance(data, dict) else None
    exchanges = exchanges if isinstance(exchanges, list) else []
    kinds = []
    for i, exchange in enumerate(exchanges):
        request = exchange.get("request") if isinstance(exchange, dict) else None
        asker = request.get("as") if isinstance(request, dict) else None
        asker = asker if isinstance(asker, dict) else {}
        kinds.append(asker.get("kind"))
        if "@" in str(asker.get("name", "")):
            out.append(("exchanges[%d].request.as.name" % i, "looks like an address; name the account in words, "
                        "never by its address"))
    if isinstance(data, dict) and "repo" in data:
        if data["repo"] is None:
            for i, kind in enumerate(kinds):
                if kind != "subscription":
                    out.append(("exchanges[%d].request.as.kind" % i, "is %s, and repo is null; only a trial of a "
                                "vendor's CLI, every request of it made as subscription, records no repo" % kind))
        else:
            for i, kind in enumerate(kinds):
                if kind == "subscription":
                    out.append(("exchanges[%d].request.as.kind" % i, "is subscription, and repo is %s; a trial of a "
                                "vendor's CLI ran in no repo, so its repo is null" % data["repo"]))
            out += _org(data["repo"], exchanges)
    return out


def _of_org(request) -> bool:
    """Whether a request is a REST call of an App, of the org or of an installation, whose path climbs nowhere."""
    request = request if isinstance(request, dict) else {}
    call = request.get("call")
    if request.get("via") != "rest" or not isinstance(call, str) or not ORG_CALL.match(call):
        return False
    path = call.split(" ", 1)[1].split("?", 1)[0]
    return not CLIMBS.search(path)


def _org(repo, exchanges: list) -> list:
    """(path, what is wrong) when `repo` is the org and a call is not of the org or its Apps, or the other way round."""
    requests = [exchange.get("request") if isinstance(exchange, dict) else None for exchange in exchanges]
    calls = [_of_org(request) for request in requests]
    if repo == ORG:
        return [("exchanges[%d].request.call" % i, "is not a REST call of the org or its Apps, and repo is %s; only a "
                 "trial whose every call is a REST call of an App, the org or an installation, with no segment that "
                 "climbs out of it, records the org" % ORG)
                for i, of_org in enumerate(calls) if not of_org]
    if calls and all(calls):
        return [("repo", "is %s, and every call is of the org or its Apps; such a trial records the org, %s"
                 % (repo, ORG))]
    return []


def _headers(data) -> list:
    """(path, what is wrong) for each header of an exchange that a fixture may not keep."""
    out = []
    exchanges = data.get("exchanges") if isinstance(data, dict) else None
    for i, exchange in enumerate(exchanges if isinstance(exchanges, list) else []):
        for side in ("request", "response"):
            part = exchange.get(side) if isinstance(exchange, dict) else None
            headers = part.get("headers") if isinstance(part, dict) else None
            for name in headers if isinstance(headers, dict) else []:
                if name.strip().lower() not in HEADERS:
                    out.append(("exchanges[%d].%s.headers.%s" % (i, side, name),
                                "is not a header a fixture may keep; leave it out, or add it to HEADERS in "
                                "tools/check_trials.py if it can never carry a credential"))
    return out


WORLDS = ("world.py", "issues.py")


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
                raise ValueError("RULES must be a tuple of (code, rule, trials, fixture)")
            return list(found)
    raise ValueError("holds no RULES")


def _fixtures(root: pathlib.Path, schema: dict, problems: list) -> dict:
    """{path: the fixture} for each valid fixture in trials/; each problem found is recorded."""
    folder, valid = root / "trials", {}
    for path in sorted(folder.iterdir()) if folder.is_dir() else []:
        rel, name = "trials/%s" % path.name, FIXTURE.match(path.name)
        if path.name == "AGENTS.md":
            if shaped(path.read_text(errors="replace")):
                problems.append("%s: holds something shaped like a credential" % rel)
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
        if not wrong:
            wrong += ["%s: %s %s" % (rel, where, what) for where, what in _askers(data)]
        wrong += ["%s: %s %s" % (rel, where, what) for where, what in _credentials(data, "") + _headers(data)]
        problems += wrong
        if not wrong:
            valid[rel] = data
    return valid


def _examples(root: pathlib.Path) -> list:
    """The examples of a fixture, counter-examples too, hold no credential either; an example names its askers as a
    fixture must."""
    problems = []
    for path in walk.files(root, "examples"):
        if not (path.name.startswith("trial") and path.suffix == ".json"):
            continue
        rel = path.relative_to(root).as_posix()
        try:
            data = _load(path)
        except (OSError, ValueError):
            continue        # check_examples reports it
        found = _credentials(data, "") + _headers(data)
        if "invalid" not in path.relative_to(root).parts:
            found += _askers(data)
        problems += ["%s: %s %s" % (rel, where, what) for where, what in found]
    return problems


def _grounding(root: pathlib.Path, valid: dict, problems: list) -> None:
    try:
        listed = rules(root)
    except ValueError as err:
        problems.append("sim/grounding.py: %s" % err)
        return
    seen = set()
    for code, rule, trials, fixture in listed:
        if not isinstance(code, str) or not CODE.match(code):
            problems.append("sim/grounding.py: %r is not a code" % (code,))
            continue
        if code in seen:
            problems.append("sim/grounding.py: %s is listed twice" % code)
        seen.add(code)
        if not isinstance(rule, str) or not rule:
            problems.append("sim/grounding.py: %s states no rule" % code)
        if not isinstance(trials, tuple) or not all(isinstance(t, str) and TRIAL.match(t) for t in trials):
            problems.append("sim/grounding.py: %s: %r is not a tuple of trials of section 6" % (code, trials))
            continue
        if fixture is None:
            continue
        # One fixture grounds a rule, or a tuple of them when more than one trial's fixture shows it holds.
        fixtures = fixture if isinstance(fixture, tuple) else (fixture,)
        if not fixtures:
            problems.append("sim/grounding.py: %s: an empty tuple grounds nothing; write None" % code)
        for fixture in fixtures:
            if not isinstance(fixture, str) or not fixture.startswith("trials/"):
                problems.append("sim/grounding.py: %s: %s is not a fixture in trials/" % (code, fixture))
            elif not (root / fixture).is_file():
                problems.append("sim/grounding.py: %s: %s does not exist" % (code, fixture))
            elif fixture not in valid:
                problems.append("sim/grounding.py: %s: %s is not a valid fixture" % (code, fixture))
            elif not trials:
                problems.append("sim/grounding.py: %s: no trial asks this; add one to section 6 first" % code)
            elif valid[fixture]["trial"] not in trials:
                problems.append("sim/grounding.py: %s: %s records %s, and %s asks this"
                                % (code, fixture, valid[fixture]["trial"], " or ".join(trials)))
    # Each world marks the rules it applies: the pull request's in world.py, the issue's in issues.py. Only these two
    # are read, so a mark in any other file counts for nothing.
    marked = set()
    for world in (root / "sim" / name for name in WORLDS):
        applied = set(MARK.findall(world.read_text())) if world.is_file() else set()
        for code in sorted(applied - seen):
            problems.append("sim/%s applies %s, which sim/grounding.py does not list" % (world.name, code))
        marked |= applied
    for code in sorted(seen - marked):
        problems.append("%s is listed in sim/grounding.py and applied nowhere under sim/; mark it "
                        "'# GitHub: %s' where it is applied, or take it out" % (code, code))


def _canary(root: pathlib.Path) -> list:
    """Each file but a document, a fixture, the fixture's schema or the Apps' installation data that names
    the canary, and so could read it. `tools/walk.py` decides which files are this repo's."""
    found = []
    for path in walk.files(root):
        rel = path.relative_to(root)
        exempt = rel.parts[0] in ("docs", "trials") or path.suffix == ".md" or \
            rel.as_posix() in ("schemas/trial.schema.json", "config/apps.json", "schemas/apps.schema.json") or \
            (rel.parts[0] == "examples" and path.name.startswith(("trial", "apps.")))
        if exempt:
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue        # not text
        if CANARY in text:
            found.append("%s: names the canary repo; nothing here reads it, and a fixture arrives by pull request"
                         % rel.as_posix())
    return found


def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    try:
        schema = _load(root / "schemas" / "trial.schema.json")
    except (OSError, ValueError) as err:
        return ["schemas/trial.schema.json cannot be read: %s" % err]
    valid = _fixtures(root, schema, problems)
    problems += _examples(root)
    _grounding(root, valid, problems)
    return problems + _canary(root)


def unverified(root: pathlib.Path = ROOT) -> list:
    """Each rule of the fake GitHub that no fixture grounds, as a line `verify` prints."""
    try:
        listed = rules(root)
    except ValueError:
        return []           # run() reports it
    return ["%s: %s (%s)" % (code, rule, ", ".join(trials) if isinstance(trials, tuple) and trials
                             else "no trial asks it")
            for code, rule, trials, fixture in listed if fixture is None]


def main(root: pathlib.Path = ROOT) -> int:
    problems = run(root)
    for problem in problems:
        print(problem)
    print("trials: %s" % ("ok" if not problems else "%d problems" % len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
