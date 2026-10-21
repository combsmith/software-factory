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
# A fixture of the canary reads the org's repos alone, and is answered with them alone (decision 0035, issue 226): a
# REST read names a repo of the org, the org, an App or an installation in its path; a query's root fields are
# repository, organization and rateLimit, each owner a literal or a declared variable; a command-line read names no
# other owner's repo; an answer names a repo by nameWithOwner, full_name, a name beside its owner's login, or a URL or
# resource path under these keys; and an App's read names, and is answered with, only repos its installation reaches.
REST_READ = re.compile(r"^[A-Z]+ /(?:repos/([^/?\s]+)/([^/?\s]+)|orgs/([^/?\s]+)(?:[/?]|$)|app/|apps/|installation/)")
ANY_REPO = re.compile(r"\brepos/([^/?\s]+)/([^/?\s]+)")
# A command-line read names a repo by --repo, -R or GH_REPO, with or without a space, an equals sign, quotes or the
# site's address; by `gh repo <verb> owner/name`; or by a path or an address in its words.
CLI_REPO = re.compile(r"(?:--repo|-R|GH_REPO)[ =]?[\"']?(?:https://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)"
                      r"|\bgh repo \w+ ([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")
GH_API = re.compile(r"\bgh api (?:-X \w+ )?([^\s'\"]+)")
ROOT_FIELD = re.compile(r"^(?:\w+\s*:\s*)?(\w+)\s*(?:\(([^)]*)\))?$")
ARGUMENT = re.compile(r"\b(owner|name|login)\s*:\s*(?:\"([^\"]*)\"|\$(\w+))")
# A repo's address, wherever a string holds one: the site, its API, or a git remote, with or without .git.
URL_REPO = re.compile(r"(?:https?://(?:www\.|api\.)?github\.com/(?:repos/)?|git(?:@|://)github\.com[:/])"
                      r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?=$|[/?#\s\"'])")
# A repo's address counts under these keys, which GitHub fills with a repo's own; a log or a comment may quote any.
URL_KEYS = {"url", "html_url", "repository_url", "clone_url", "ssh_url", "git_url", "svn_url", "mirror_url"}
# A resource path names a repo under these keys alone: elsewhere a string that starts with a slash is a path of its own.
PATH_KEYS = {"resourcePath"}
PATH_REPO = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:[/?#].*)?$")
# The first segment of a URL that is not an owner: GitHub's own paths for Apps, users, orgs and the rest.
NOT_AN_OWNER = {"apps", "app", "orgs", "organizations", "users", "user", "installation", "installations", "search",
                "repositories", "repos", "login", "settings", "marketplace", "sponsors", "notifications", "gists",
                "codes_of_conduct", "licenses", "emojis", "rate_limit", "meta", "events", "feeds"}
TRIAL = re.compile(r"^P-[1-9][0-9]*$")
CODE = re.compile(r"^[a-z_]+$")
# What a rule no trial can ask says, before its reason (issue 190).
ASSUMED = "assumed, no trial can ask it: "
# Where section 6's trials are, one row each: a trial a rule names must be one of them.
DESIGN = "docs/architecture/software-factory-design.md"
WORD = re.compile(r"[A-Za-z]{2,}")
SECOND = re.compile(r"[.!?]\s+\S")       # a sentence that ends before the reason does
ROW = re.compile(r"^\| (P-[1-9][0-9]*) \|", re.M)
FENCED = re.compile(r"^```.*?^```", re.M | re.S)
MARK = re.compile(r"^\s*# GitHub: (\S+)\s*$", re.M)

# A key that names a credential, however it is spelt: compared after strip(), lower() and - to _.
KEY_PARTS = ("token", "secret", "password", "credential", "jit_config", "otp", "cookie", "authorization",
             "api_key", "apikey", "private_key", "privatekey", "passphrase",
             "authentication", "passwd", "passcode", "bearer", "access_key", "accesskey", "encryption_key", "signing_key",
             "master_key", "auth_key", "authkey", "pwd", "encryptionkey", "signingkey", "masterkey")
KEY_WHOLE = {"auth", "jwt"}
KEY_HARMLESS = {"token_type", "input_tokens", "output_tokens", "total_tokens", "cache_creation_input_tokens",
                "cache_read_input_tokens",
                # The vendor's CLI counts tokens in camelCase under modelUsage, and in nested fields under usage
                # (issue 178); compared after lower(), so inputTokens is input_tokens here.
                "inputtokens", "outputtokens", "cachereadinputtokens", "cachecreationinputtokens", "maxoutputtokens",
                "thinkingtokens", "thinking_tokens", "ephemeral_1h_input_tokens", "ephemeral_5m_input_tokens",
                "output_tokens_details"}
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


# How a place is named when its key is shaped like a credential: by this, never by the key.
KEY_SHAPED = "<a key shaped like a credential>"
# What a repr writes for a character it does not print: each is read as a separator when a message is hidden.
ESCAPED = re.compile(r"\\(?:x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|[ntrfvab0])")
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\xa0]")


def hidden(text: str) -> str:
    """`text` with each word shaped like a credential replaced by KEY_SHAPED, and hidden whole when a shape spans
    words: a message never carries one. An escaped character, as a repr writes a newline, a vertical tab or a
    non-breaking space, is read as a separator."""
    plain = ESCAPED.sub(" ", text)
    text = re.sub(r"\S+", lambda m: KEY_SHAPED if shaped(ESCAPED.sub(" ", m.group())) else m.group(), text)
    return text if not shaped(plain) else "a message that holds something shaped like a credential, hidden whole"


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
    """Whether `text` holds something shaped like a credential, plainly or in base64. A control character is read as a
    separator, so a shape split by one is still seen."""
    text = CONTROL.sub(" ", text)
    if SHAPES.search(text) or REGISTRATION.match(text.strip()):    # the whole string, a newline after it or not
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
            shown = KEY_SHAPED if shaped(key) else key     # a place is never named by a credential
            here = "%s.%s" % (where, shown) if where else shown
            if refused_key(key):
                out.append((here, "is a field for a credential; leave it out, and list where in removed"))
            elif shaped(key):
                out.append((here, "is a key shaped like a credential; leave it out, and list where in removed"))
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


def _roots(query: str):
    """([(root field, its arguments)] of the one operation in `query`, what is wrong or None). A string is read whole,
    an escaped quote inside it included, a block string to its closing three quotes, and a comment to the end of its
    line; a fragment on another type is skipped, since its fields hang off a root field of the operation; a fragment
    on Query, or a second operation, is refused."""
    depth, found, text, quoted, escaped, skipping, operations, at = 0, [], "", False, False, False, 0, 0
    while at < len(query):
        ch = query[at]
        at += 1
        if quoted == "block":
            if query.startswith('""', at) and ch == '"':
                quoted, at = False, at + 2
            text += ch
            continue
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
            text += ch
            continue
        if ch == '"':
            if query.startswith('""', at):
                quoted, at = "block", at + 2
            else:
                quoted = True
            text += ch
            continue
        if ch == "#":
            # A comment runs to the end of its line, and holds no field and no brace that counts.
            end = query.find("\n", at)
            at = len(query) if end < 0 else end
            continue
        if ch == "{":
            if depth == 0:
                opening = text.strip()
                skipping = opening.startswith("fragment ")
                if skipping and re.search(r"\bon\s+Query\b", opening):
                    return [], "holds a fragment on Query, whose fields are root fields; write them in the operation"
                if not skipping:
                    operations += 1
                text = ""
            elif depth == 1 and not skipping:
                found.append(text.strip())
                text = ""
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth <= 1:
                text = ""
        elif depth == 0 or (depth == 1 and not skipping):
            text += ch
    if operations != 1 or depth != 0:
        return [], "holds %d operations, or a brace left open; a read is one operation" % operations
    out = []
    for item in found:
        field = ROOT_FIELD.match(item.strip())
        if not field:
            return [], "has a root field that cannot be read: %r" % item[:60]
        out.append((field.group(1), field.group(2) or ""))
    return out, None


def _bound(args: str, key: str, variables: dict):
    """The one value of `key` among `args`, a literal or a declared variable's; None if not exactly one."""
    found = [m for m in ARGUMENT.finditer(args) if m.group(1) == key]
    if len(found) != 1:
        return None
    literal, var = found[0].group(2), found[0].group(3)
    return literal if literal is not None else variables.get(var)


def _asked(request: dict) -> tuple:
    """({owners}, {repos}, [what is wrong]) a request names, by its query's root fields, its REST path or its
    command line."""
    owners, repos, wrong = set(), set(), []
    via, call = request.get("via"), request.get("call")
    if via == "graphql":
        body = request.get("body") if isinstance(request.get("body"), dict) else {}
        query = body.get("query")
        variables = body.get("variables") if isinstance(body.get("variables"), dict) else {}
        if not isinstance(query, str) or not query.lstrip().startswith(("query", "{")):
            return owners, repos, ["is not a query; a read is one query, not a mutation or a subscription"]
        roots, problem = _roots(query)
        if problem:
            return owners, repos, [problem]
        for field, args in roots:
            if field == "repository":
                owner, name = _bound(args, "owner", variables), _bound(args, "name", variables)
                if not (isinstance(owner, str) and isinstance(name, str)):
                    wrong.append("has a repository call whose owner or name cannot be read: %s" % args[:60])
                    continue
                owners.add(owner)
                repos.add(owner + "/" + name)
            elif field == "organization":
                login = _bound(args, "login", variables)
                if not isinstance(login, str):
                    wrong.append("has an organization call whose login cannot be read: %s" % args[:60])
                    continue
                owners.add(login)
            elif field != "rateLimit":
                wrong.append("has a root field the check does not read: %s" % field)
        if not owners and not wrong:
            wrong.append("is a query that names no repo and no org")
    elif via == "rest":
        found = REST_READ.match(call) if isinstance(call, str) else None
        if not found:
            wrong.append("names no repo of the org, nor the org, an App or an installation, in its path; a read of a "
                         "fixture of the canary is of one of those")
        elif CLIMBS.search(call.split(" ", 1)[1].split("?", 1)[0]):
            wrong.append("climbs out of its repo with a .. segment; write the path it reads")
        else:
            for owner, name in ANY_REPO.findall(call):
                owners.add(owner)
                repos.add(owner + "/" + name)
            if found.group(3):
                owners.add(found.group(3))
    elif via in ("cli", "git") and isinstance(call, str):
        for m in CLI_REPO.finditer(call):
            owner, name = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            owners.add(owner)
            repos.add(owner + "/" + name)
        for owner, name in ANY_REPO.findall(call) + URL_REPO.findall(call):
            owners.add(owner)
            repos.add(owner + "/" + name)
        for path in GH_API.findall(call):
            # gh api takes an API path: the same rule as a REST read, or graphql, whose query the fixture would carry.
            if path != "graphql" and not REST_READ.match("GET /" + path.lstrip("/")):
                wrong.append("asks gh api for %s, which names no repo of the org, nor the org, an App or an installation"
                             % path[:60])
    return owners, repos, wrong


def _named(value, under=None):
    """Each repo an answer names: nameWithOwner, full_name, a name beside its owner's login (which an App, under the
    key app or with a slug, has as well and is not one), a repo's address under a key that carries one (a log or a
    comment may quote any address, which names no repo the read was of), or a resource path under a key that carries
    one."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("nameWithOwner", "full_name") and isinstance(item, str):
                yield item
            elif key in URL_KEYS and isinstance(item, str):
                for owner, name in URL_REPO.findall(item):
                    if owner not in NOT_AN_OWNER:
                        yield owner + "/" + name
            elif key in PATH_KEYS and isinstance(item, str):
                found = PATH_REPO.match(item)
                if found and found.group(1) not in NOT_AN_OWNER:
                    yield found.group(1) + "/" + found.group(2)
            yield from _named(item, key)
        owner = value.get("owner")
        if isinstance(value.get("name"), str) and isinstance(owner, dict) and isinstance(owner.get("login"), str) \
                and under != "app" and "slug" not in value:
            yield owner["login"] + "/" + value["name"]
    elif isinstance(value, list):
        for item in value:
            yield from _named(item, under)


def _installed(root: pathlib.Path):
    """{App name: the repos its installation reaches}, from config/apps.json; None when it cannot be read."""
    try:
        apps = _load(root / "config" / "apps.json")["apps"]
        return {app["name"]: set(app["installed_on"]) for app in apps.values()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def _repos(data: dict, installed) -> list:
    """(path, what is wrong) for each read of a fixture of the canary that names another owner's repo, is answered with
    one, or, made by an App, names or is answered with a repo its installation does not reach; and for a command-line
    read that is not the Maintainer's own. An App the data does not know reaches the canary alone; a data file that
    cannot be read is one problem, and every App is then held to the canary."""
    out, canary = [], "%s/%s" % (ORG, CANARY)
    if installed is None:
        out.append(("config/apps.json", "cannot be read, so every App's reach is the canary alone"))
        installed = {}
    for i, exchange in enumerate(data.get("exchanges") or []):
        request = exchange.get("request") if isinstance(exchange, dict) else None
        if not isinstance(request, dict):
            continue
        where = "exchanges[%d].request" % i
        owners, repos, wrong = _asked(request)
        out += [(where + ".call", what) for what in wrong]
        for owner in sorted(owners - {ORG}):
            out.append((where + ".call", "names the owner %s; a read of a fixture of the canary names the org alone" % owner))
        response = exchange.get("response") if isinstance(exchange.get("response"), dict) else {}
        answered = set(_named(response.get("body")))
        for repo in sorted(r for r in answered if not r.startswith(ORG + "/")):
            out.append(("exchanges[%d].response.body" % i, "names the repo %s; an answer names the org's repos alone" % repo))
        asker = request.get("as") if isinstance(request.get("as"), dict) else {}
        if request.get("via") == "cli" and asker.get("kind") != "person":
            out.append((where + ".as", "is %s; a command-line read is the Maintainer's own, a person's" % asker.get("kind")))
        if asker.get("kind") == "app":
            name = str(asker.get("name", "")).split(",")[0].replace("[bot]", "")
            reach = installed.get(name, {canary})
            if request.get("via") == "graphql" and ORG in owners and not repos:
                out.append((where + ".call", "asks of the org by an App, whose installation reaches repos alone"))
            for repo in sorted(repos - reach):
                out.append((where + ".call", "asks of %s, which the App's installation does not reach" % repo))
            for repo in sorted(answered - reach):
                out.append(("exchanges[%d].response.body" % i, "names %s, which the App's installation does not reach" % repo))
    return out


def fixture_problems(data: dict, root: pathlib.Path = ROOT) -> list:
    """Every problem with one fixture beyond its schema, as the check finds them: who asked, the repos it reads and is
    answered with, credentials and headers. A counter-example under examples/invalid is held to this."""
    out = ["%s %s" % (where, what) for where, what in _askers(data)]
    if not out and data.get("repo") == "%s/%s" % (ORG, CANARY):
        out += ["%s %s" % (where, what) for where, what in _repos(data, _installed(root))]
    return out + ["%s %s" % (where, what) for where, what in _credentials(data, "") + _headers(data)]


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
                    shown = KEY_SHAPED if shaped(name) else name     # a place is never named by a credential
                    out.append(("exchanges[%d].%s.headers.%s" % (i, side, shown),
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
            if not isinstance(found, (tuple, list)) or not all(isinstance(r, tuple) and len(r) == 5 for r in found):
                raise ValueError("RULES must be a tuple of (code, rule, trials, fixture, note)")
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
            problems.append("%s cannot be read: %s" % (rel, hidden(str(err))))
            continue
        wrong = ["%s: %s" % (rel, hidden(err)) for err in validate(data, schema)]
        if not wrong and data["trial"] != name.group(1):
            wrong.append("%s: records trial %s; a fixture is named for its trial" % (rel, data["trial"]))
        if not wrong:
            wrong += ["%s: %s" % (rel, problem) for problem in fixture_problems(data, root)]
        else:
            wrong += ["%s: %s %s" % (rel, where, what) for where, what in _credentials(data, "") + _headers(data)]
        problems += wrong
        if not wrong:
            valid[rel] = data
    return valid


def _examples(root: pathlib.Path) -> list:
    """The examples of a fixture, counter-examples too, hold no credential and no header a fixture may not keep; a
    valid example is held to every rule a fixture is."""
    problems = []
    for path in walk.files(root, "examples"):
        if not (path.name.startswith("trial") and path.suffix == ".json"):
            continue
        rel = path.relative_to(root).as_posix()
        try:
            data = _load(path)
        except (OSError, ValueError):
            continue        # check_examples reports it
        if "invalid" in path.relative_to(root).parts:
            problems += ["%s: %s %s" % (rel, where, what) for where, what in _credentials(data, "") + _headers(data)]
        else:
            problems += ["%s: %s" % (rel, problem) for problem in fixture_problems(data, root)]
    return problems


def section_6(root: pathlib.Path) -> set:
    """The trials section 6 of the design has a row for, outside any fenced block, or None when the design cannot be
    read. A row anywhere else in the design is no trial."""
    try:
        text = (root / DESIGN).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    start = text.find("\n## 6. ")
    end = text.find("\n## ", start + 1) if start >= 0 else -1
    section = text[start:end if end >= 0 else len(text)] if start >= 0 else ""
    return set(ROW.findall(FENCED.sub("", section)))


def _grounding(root: pathlib.Path, valid: dict, problems: list) -> None:
    try:
        listed = rules(root)
    except ValueError as err:
        problems.append("sim/grounding.py: %s" % err)
        return
    rows = section_6(root)
    if rows is None:
        problems.append("%s cannot be read, so no trial a rule names can be found in section 6" % DESIGN)
    seen = set()
    for code, rule, trials, fixture, note in listed:
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
        for trial in trials if rows is not None else ():
            if trial not in rows:
                problems.append("sim/grounding.py: %s: %s has no row in section 6; add the trial there first"
                                % (code, trial))
        # A rule no trial asks names the trial that will, or says in one sentence why none can (issue 190); a rule a
        # trial asks, or a fixture grounds, says nothing more.
        if not trials and fixture is None:
            if not (isinstance(note, str) and note.startswith(ASSUMED) and WORD.search(note[len(ASSUMED):])
                    and not SECOND.search(note[len(ASSUMED):])):
                problems.append("sim/grounding.py: %s: no trial asks this; name the trial of section 6 that will, "
                                "or say in one sentence why none can, '%s...'" % (code, ASSUMED))
        elif note is not None:
            problems.append("sim/grounding.py: %s: a trial asks this, or a fixture grounds it, so it says nothing of "
                            "why none can" % code)
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
    return ["%s: %s (%s)" % (code, rule, "asked by %s, no fixture yet" % ", ".join(trials)
                             if isinstance(trials, tuple) and trials
                             else note if isinstance(note, str) else "no trial asks it")
            for code, rule, trials, fixture, note in listed if fixture is None]


def main(root: pathlib.Path = ROOT) -> int:
    problems = run(root)
    for problem in problems:
        print(problem)
    print("trials: %s" % ("ok" if not problems else "%d problems" % len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
