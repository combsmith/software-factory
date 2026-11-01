"""The fixtures of the platform trials, and the fake GitHub's grounding in them (design, sections 4.5 and 6).

A fixture in `trials/` is what one trial sent to GitHub in the canary repo, or of the org itself for a
trial about the org and its Apps (decision 0035), and what came back, with every credential removed.
`repo` is the org exactly when every call is of the org or its Apps. It validates against
`schemas/trial.schema.json`, and nothing else is kept there. A credential is refused here and not by
the schema, which cannot express it: `tools/redact_trial.py` applies the same rules to a raw capture
before anyone reads it.

Each rule the fake GitHub applies is listed in `sim/grounding.py` and marked where a world under
`sim/` applies it. A trial a rule names has a row in section 6 of the design whose question asks it,
in the words the rule quotes (issue 265). A fixture named there must exist and be valid. A rule with
no fixture is unverified, and `verify` prints it.

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
ORG_CALL = re.compile(r"^[A-Z]+ /(apps/|orgs/%s/|installation/|users/%s-sf-[a-z-]+\[bot\]$)" % (ORG, ORG))
CLIMBS = re.compile(r"(^|/)\.{1,2}(/|$)|%2e", re.I)
FIXTURE = re.compile(r"^(P-[1-9][0-9]*)(\.[a-z0-9-]+)?\.json$")
# A fixture of the canary reads the org's repos alone, and is answered with them alone (decision 0035, issue 226): a
# REST read names a repo of the org, the org, an App or an installation in its path; a query's root fields are
# repository, organization and rateLimit, each owner a literal or a declared variable; a command-line read names no
# other owner's repo; an answer names a repo by nameWithOwner, full_name, a name beside its owner's login, or a URL or
# resource path under these keys; and an App's read names, and is answered with, only repos its installation reaches.
REST_READ = re.compile(r"^[A-Z]+ /(?:repos/([^/?\s]+)/([^/?\s]+)|orgs/([^/?\s]+)(?:[/?]|$)|app/|apps/|installation/)")
ANY_REPO = re.compile(r"\brepos/([^/?\s]+)/([^/?\s]+)")
# A star of a repo, by the account that asks, names that repo in its path (P-20).
STARRED = re.compile(r"^[A-Z]+ /user/starred/([^/?,\s]+)/([^/?,\s]+)(?:[?,\s]|$)")
# Decision 0035: a trial whose question is a read beyond the org's repos the App reaches is named here with what it may
# read beyond. A trial of forks reads the forks of the canary, which keep its name, and their owners; a trial of reach
# has its App read repos of the org its installation does not reach. Neither reads any other owner's repo.
TRIALS_OF_FORKS = {"P-27"}
TRIALS_OF_REACH = {"P-4"}
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
# A row's question is its second cell. A rule a row asks quotes the words of that question that ask it (issue 265): at
# least this many, so that a quote names a question and not a word every row has. The question is its cell alone: a
# cell whose close lacks its space does not run on into the next, nor past its line, and a pipe escaped is the cell's
# own (the second-family read of #357).
QUESTION = re.compile(r"^\| (P-[1-9][0-9]*) \| ((?:[^\\|\n]|\\[^\n])*?) \| ", re.M)
QUOTED_WORDS = 4
# A fenced block holds no row, nor does a block fenced with tildes or an HTML comment (the review of #265). They are
# read in one pass from the top, as a renderer reads them, so that a fence inside a comment, or a comment's close inside
# a block, ends nothing (the second-family read of #357). A fence is three marks or more, indented three spaces at
# most, and only a line of the same mark, at least as long, closes it.
HIDDEN = re.compile(r"(?:^ {0,3}(`{3,})[^\n]*\n.*?^ {0,3}\1`*[ \t]*$)|(?:^ {0,3}(~{3,})[^\n]*\n.*?^ {0,3}\2~*[ \t]*$)"
                    r"|(?:<!--.*?-->)", re.M | re.S)
# An opener with no close hides the rest, as a renderer reads it: no row after it is a trial.
OPENED = re.compile(r"(?:^ {0,3}(?:```|~~~))|(?:<!--)", re.M)
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
# age and if-none-match: the records port keeps a read's age, and may ask by its etag (decision 0036, ruling 4).
# x-oauth-scopes is not among them: it names what the token that asked may do, the Maintainer's admin scopes among
# them, which no rule needs and a public repo should not advertise (the orchestrator's ruling, 2026-10-28).
HEADERS = {"accept", "age", "cache-control", "content-length", "if-none-match", "content-type", "date", "etag", "last-modified", "link",
           "location", "retry-after", "server", "user-agent", "vary", "x-accepted-github-permissions",
           "x-accepted-oauth-scopes", "x-github-api-version", "x-github-media-type", "x-github-request-id",
           "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
           "x-ratelimit-resource", "x-ratelimit-used"}
# What a credential looks like inside any string, at any length and in any case.
SHAPES = re.compile("|".join((
    r"gh[opsur]_[a-z0-9]",                          # a token GitHub issues, wherever it starts
    # Any other prefix of that form, whatever issues it. Not after a letter, where right_now and height_px are ordinary
    # words, unless a long run follows, as after a percent escape's letter or a word run into it.
    r"(?<![a-z])gh[a-z]_[a-z0-9]", r"gh[a-z]_[a-z0-9]{20,}",
    r"github_pat_", r"ghsat[0-9a-z]", r"sk-ant-",
    r"\b(token|basic|bearer)\s+\S{8,}", r"\bbearer\s+\S",
    # A signed token, eyJ and on to a dot. A run that holds eyJ is read once, from its start: trying each eyJ in it
    # again to the run's end took time in the square of a run of them with no dot (issue 370).
    r"(?<![a-z0-9_-])(?=[a-z0-9_-]*?eyJ)[a-z0-9_-]*\.",
    r"//[^/\s:@]+:[^/\s@]+@",                       # a user and password in a URL
    r"[?&](sig|token|access_token|x-amz-signature|x-amz-credential)=",
    r"\b(set-cookie|cookie|authorization|proxy-authorization)\s*:",
    r"(token|bearer|secret|password)\W{0,3}[0-9a-f]{40}",
    # auth and any letters after it, then a hex secret. Only the first auth of a run of letters is tried, and is not
    # tried again, since a later one finds less; trying each took time in the square of the run (issue 370).
    r"(?<![a-z])(?=(?P<auth>[a-z]*?auth))(?P=auth)[a-z]*\W{0,3}[0-9a-f]{40}",
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
            # Read once: shaped reads what it decodes through this function, so a second reading doubled the work at each
            # level of base64 inside a key, and a capture of a few kilobytes held up the redactor for a minute.
            key_is_shaped = shaped(key)
            shown = KEY_SHAPED if key_is_shaped else key     # a place is never named by a credential
            here = "%s.%s" % (where, shown) if where else shown
            if refused_key(key):
                out.append((here, "is a field for a credential; leave it out, and list where in removed"))
            elif key_is_shaped:
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


# The writes a trial of the canary may record, each on one node by its input's one key: a pull request or a review
# thread. Its scope is the node's, so a fixture holds a write only on a node a read of the canary alone in it answered.
WRITES = {"enqueuePullRequest": "pullRequestId", "dequeuePullRequest": "id", "enablePullRequestAutoMerge": "pullRequestId",
          "convertPullRequestToDraft": "pullRequestId", "resolveReviewThread": "threadId"}
WRITE = re.compile(r"^\s*mutation\s*\(\s*\$id\s*:\s*ID!\s*\)\s*\{\s*(\w+)\s*\(\s*input\s*:\s*\{\s*(\w+)\s*:\s*\$id"
                   r"(\s*,\s*mergeMethod\s*:\s*[A-Z]+)?\s*\}\s*\)\s*\{")
# The canary's repository id, as its reads answer it (trials/P-49.json, trials/P-2.least.json). A node id GitHub issues
# today is a prefix and base64url of msgpack [0, the repository's id, ...]: a write is held to a node of the canary by it.
CANARY_ID = 1414593263


def node_repo(node: str):
    """The repository id a node id of GitHub's current form names, or None when it cannot be read as one."""
    prefix, _, encoded = node.partition("_") if isinstance(node, str) else ("", "", "")
    if not prefix.isalpha() or not encoded or not re.fullmatch(r"[A-Za-z0-9_-]+", encoded):
        return None
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, TypeError):
        return None
    if len(raw) < 3 or not 0x92 <= raw[0] <= 0x9f or raw[1] != 0:
        return None
    tag, rest = raw[2], raw[3:]
    if tag <= 0x7f:
        return tag
    width = {0xcc: 1, 0xcd: 2, 0xce: 4, 0xcf: 8}.get(tag)
    return int.from_bytes(rest[:width], "big") if width and len(rest) >= width else None


def written(request: dict):
    """(the write, the node id it writes) of a GraphQL mutation a fixture may record, or None: one root field among
    WRITES, its input's one key bound to the one variable `id`, a node id, and nothing after its selection."""
    body = request.get("body") if isinstance(request, dict) and isinstance(request.get("body"), dict) else {}
    query, variables = body.get("query"), body.get("variables")
    if request.get("via") != "graphql" or not isinstance(query, str) or '"' in query or "#" in query \
            or set(body) != {"query", "variables"} \
            or not isinstance(variables, dict) or set(variables) != {"id"} or not isinstance(variables["id"], str):
        return None
    found = WRITE.match(query)
    if not found or WRITES.get(found.group(1)) != found.group(2) \
            or (found.group(3) and found.group(1) != "enablePullRequestAutoMerge"):
        return None
    depth, at = 1, found.end()
    while at < len(query) and depth:
        depth += {"{": 1, "}": -1}.get(query[at], 0)
        at += 1
    return (found.group(1), variables["id"]) if depth == 0 and query[at:].strip() == "}" else None


# Anything but a brace between the word and its brace, a GraphQL comment among it, in one repeated class, so the match
# is linear in the text (Sonar's S8786).
MUTATION = re.compile(r"\bmutation\b[^{}]*\{")


def _sent_writes(value) -> list:
    """Each GraphQL write an exchange carries anywhere but as its own request, as a dict of `query` and `variables`
    (a script's record of what it sent), at any depth; and each other string that reads as a mutation, as None."""
    out = []
    if isinstance(value, dict):
        query = value.get("query")
        if isinstance(query, str) and MUTATION.search(query):
            out.append(value if set(value) <= {"query", "variables"} else None)
        out += [w for k, v in value.items() if k != "query" for w in _sent_writes(v)]
    elif isinstance(value, list):
        out += [w for v in value for w in _sent_writes(v)]
    elif isinstance(value, str) and MUTATION.search(value):
        out.append(None)
    return out


def _a_read(request: dict) -> bool:
    """Whether a request reads: a GraphQL query, or a REST GET. Only a read's answer ties a node to a repo."""
    if request.get("via") == "graphql":
        body = request.get("body") if isinstance(request.get("body"), dict) else {}
        return isinstance(body.get("query"), str) and body["query"].lstrip().startswith(("query", "{"))
    return request.get("via") == "rest" and isinstance(request.get("call"), str) and request["call"].startswith("GET ")


def _nodes(value) -> set:
    """Every node id an answer holds: a `node_id`, or an `id` that is a string, at any depth."""
    out = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("node_id", "id") and isinstance(item, str):
                out.add(item)
            out |= _nodes(item)
    elif isinstance(value, list):
        for item in value:
            out |= _nodes(item)
    return out


def _asked(request: dict) -> tuple:
    """({owners}, {repos}, [what is wrong]) a request names, by its query's root fields, its REST path or its
    command line."""
    owners, repos, wrong = set(), set(), []
    via, call = request.get("via"), request.get("call")
    if via == "graphql":
        body = request.get("body") if isinstance(request.get("body"), dict) else {}
        query = body.get("query")
        variables = body.get("variables") if isinstance(body.get("variables"), dict) else {}
        if written(request):
            return owners, repos, []      # held to the node a read of the org's repos answered (_repos)
        if not isinstance(query, str) or not query.lstrip().startswith(("query", "{")):
            return owners, repos, ["is not a query; a read is one query, and a write one of WRITES on one node by `id`"]
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
        starred = STARRED.match(call) if isinstance(call, str) else None
        if starred:
            owners.add(starred.group(1))
            repos.add(starred.group(1) + "/" + starred.group(2))
        if not found and not starred:
            wrong.append("names no repo of the org, nor the org, an App or an installation, in its path; a read of a "
                         "fixture of the canary is of one of those")
        elif CLIMBS.search(call.split(" ", 1)[1].split("?", 1)[0]):
            wrong.append("climbs out of its repo with a .. segment; write the path it reads")
        else:
            for owner, name in ANY_REPO.findall(call):
                owners.add(owner)
                repos.add(owner + "/" + name)
            if found and found.group(3):
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


def _orgs_named(request: dict) -> set:
    """The owners a request names at an org's level: an organization call of its query, or an /orgs/ path."""
    out, via, call = set(), request.get("via"), request.get("call")
    if via == "graphql":
        body = request.get("body") if isinstance(request.get("body"), dict) else {}
        variables = body.get("variables") if isinstance(body.get("variables"), dict) else {}
        query = body.get("query")
        roots, problem = _roots(query) if isinstance(query, str) else ([], None)
        for field, args in roots:
            login = _bound(args, "login", variables) if field == "organization" else None
            if isinstance(login, str):
                out.add(login)
    elif via == "rest" and isinstance(call, str):
        found = REST_READ.match(call)
        if found and found.group(3):
            out.add(found.group(3))
    return out


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
    trial = data.get("trial")
    fork = lambda repo: trial in TRIALS_OF_FORKS and repo.count("/") == 1 and repo.split("/")[1] == CANARY
    allowed = lambda repo: repo.startswith(ORG + "/") or fork(repo)
    # The nodes a read of the canary itself answered, naming no other repo, which alone a recorded write may name: a read
    # of another repo of the org ties its nodes to that repo.
    nodes = set()
    for exchange in data.get("exchanges") or []:
        request = exchange.get("request") if isinstance(exchange, dict) else None
        response = exchange.get("response") if isinstance(exchange, dict) and isinstance(exchange.get("response"), dict) else {}
        if isinstance(request, dict) and _a_read(request) and response.get("status") == 200:
            owners, repos, wrong = _asked(request)
            if not wrong and repos == {canary} and set(_named(response.get("body"))) <= {canary}:
                nodes |= _nodes(response.get("body"))
    for i, exchange in enumerate(data.get("exchanges") or []):
        request = exchange.get("request") if isinstance(exchange, dict) else None
        if not isinstance(request, dict):
            continue
        where = "exchanges[%d].request" % i
        write = written(request)
        if write and write[1] not in nodes:
            out.append((where + ".body", "writes %s on a node no read of the canary alone in this fixture answered"
                        % write[0]))
        elif write and node_repo(write[1]) != CANARY_ID:
            out.append((where + ".body", "writes %s on a node that is not the canary's by its id: %s"
                        % (write[0], node_repo(write[1]) or "an id that cannot be read")))
        # A write carried any other way, by a command line, a workflow, or inside an answer, is held as one sent: one of
        # WRITES, on a node of the canary a read here answered; a mutation in any other text is refused.
        response = exchange.get("response") if isinstance(exchange.get("response"), dict) else {}
        # A GraphQL request's own query and variables are its read or its write, held above; any other field of its body
        # is scanned as the rest of the exchange is.
        body = request.get("body") if isinstance(request.get("body"), dict) else {}
        own = request.get("via") == "graphql"
        carried = _sent_writes({k: v for k, v in request.items() if not (own and k == "body")}) \
            + _sent_writes({k: v for k, v in body.items() if k not in ("query", "variables")} if own else {}) \
            + _sent_writes(response)
        for sent in carried:
            held = written({"via": "graphql", "body": sent}) if sent is not None else None
            if held is None:
                out.append((where, "carries a GraphQL write that is not one of WRITES, sent as a request of its own"))
            elif held[1] not in nodes or node_repo(held[1]) != CANARY_ID:
                out.append((where, "carries a write of %s on a node no read of the canary alone answered" % held[0]))
        owners, repos, wrong = _asked(request)
        out += [(where + ".call", what) for what in wrong]
        forks_named = {r.split("/")[0] for r in repos if fork(r)} - _orgs_named(request)
        for owner in sorted(owners - {ORG} - forks_named):
            out.append((where + ".call", "names the owner %s; a read of a fixture of the canary names the org alone, or in a "
                        "trial of forks the owner of a fork of the canary" % owner))
        response = exchange.get("response") if isinstance(exchange.get("response"), dict) else {}
        answered = set(_named(response.get("body")))
        for repo in sorted(r for r in answered if not allowed(r)):
            out.append(("exchanges[%d].response.body" % i, "names the repo %s; an answer names the org's repos alone, or "
                        "in a trial of forks a fork of the canary" % repo))
        asker = request.get("as") if isinstance(request.get("as"), dict) else {}
        if request.get("via") == "cli" and asker.get("kind") != "person":
            out.append((where + ".as", "is %s; a command-line read is the Maintainer's own, a person's" % asker.get("kind")))
        if asker.get("kind") == "app":
            name = str(asker.get("name", "")).split(",")[0].replace("[bot]", "")
            # A trial of reach reads beyond the App's install by its question; the owner's check above still holds it to
            # the org's repos.
            reach = installed.get(name, {canary}) if trial not in TRIALS_OF_REACH else repos | answered
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
    out += ["%s %s" % (where, what) for where, what in _credentials(data, "") + _headers(data)]
    # A message names what the data holds, a repo or a kind among them, so none carries a credential (issue 247).
    return [hidden(message) for message in out]


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


def _literal(root: pathlib.Path, name: str):
    """The literal `sim/grounding.py` assigns to `name`; a ValueError says why it cannot be read."""
    path = root / "sim" / "grounding.py"
    try:
        tree = ast.parse(path.read_text(), str(path))
    except (OSError, SyntaxError) as err:
        raise ValueError("cannot be read: %s" % err)
    for node in tree.body:
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == [name]:
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                raise ValueError("%s must be a literal, so that a check can read it" % name)
    raise ValueError("holds no %s" % name)


def rules(root: pathlib.Path = ROOT) -> list:
    """The rules in `sim/grounding.py`, read as a literal; a ValueError says why they cannot be."""
    found = _literal(root, "RULES")
    if not isinstance(found, (tuple, list)) or not all(isinstance(r, tuple) and len(r) == 5 for r in found):
        raise ValueError("RULES must be a tuple of (code, rule, trials, fixture, note)")
    return list(found)


def asks(root: pathlib.Path = ROOT) -> dict:
    """What each trial a rule names asks of it, `{code: {trial: quote}}`, the words of the trial's question in section
    6 that ask it, read as a literal from `sim/grounding.py`; a ValueError says why they cannot be (issue 265)."""
    found = _literal(root, "ASKS")
    if not isinstance(found, dict) or not all(isinstance(v, dict) for v in found.values()):
        raise ValueError("ASKS must be a dict of {code: {trial: the words of its question that ask it}}")
    return found


# What each fixture was found to hold, by all that finding reads: its name, its text, the schema and the Apps' reach. It is
# most of a run, and a test that runs the check many times on copies of the tree changes one file in each (issue 438).
_FOUND = {}


def _apps_text(root: pathlib.Path):
    try:
        return (root / "config" / "apps.json").read_text()
    except (OSError, ValueError):       # `_installed` says so, for each fixture that reads it
        return None


def _fixtures(root: pathlib.Path, schema: dict, problems: list) -> dict:
    """{path: the fixture} for each valid fixture in trials/; each problem found is recorded."""
    folder, valid = root / "trials", {}
    told, apps = json.dumps(schema, sort_keys=True), _apps_text(root)
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
            key = (rel, path.read_text(), told, apps)
            data = _load(path) if key not in _FOUND else _FOUND[key][0]
        except (OSError, ValueError) as err:
            problems.append("%s cannot be read: %s" % (rel, hidden(str(err))))
            continue
        if key not in _FOUND:
            wrong = ["%s: %s" % (rel, hidden(err)) for err in validate(data, schema)]
            if not wrong and data["trial"] != name.group(1):
                wrong.append("%s: records trial %s; a fixture is named for its trial" % (rel, data["trial"]))
            if not wrong:
                wrong += ["%s: %s" % (rel, problem) for problem in fixture_problems(data, root)]
            else:
                wrong += ["%s: %s %s" % (rel, where, what) for where, what in _credentials(data, "") + _headers(data)]
            _FOUND[key] = (data, wrong)
        else:
            wrong = _FOUND[key][1]
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


def _section_6(root: pathlib.Path):
    """Section 6 of the design with its fenced blocks taken out, or None when the design cannot be read. A row
    anywhere else in the design, or in a fenced block, is no trial."""
    try:
        text = (root / DESIGN).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    start = text.find("\n## 6. ")
    end = text.find("\n## ", start + 1) if start >= 0 else -1
    section = text[start:end if end >= 0 else len(text)] if start >= 0 else ""
    section = HIDDEN.sub("", section)
    opened = OPENED.search(section)
    return section[:opened.start()] if opened else section


def section_6(root: pathlib.Path) -> set:
    """The trials section 6 of the design has a row for, or None when the design cannot be read."""
    section = _section_6(root)
    return None if section is None else set(ROW.findall(section))


def _quoted(quote: str, question: str) -> bool:
    """Whether `quote` is in `question` as whole words: it starts and ends where a word does."""
    return re.search(r"(?<![\w`'])%s(?![\w`])" % re.escape(quote), question) is not None


def questions(root: pathlib.Path) -> dict:
    """What each trial's row in section 6 asks, its second cell, or None when the design cannot be read."""
    section = _section_6(root)
    return None if section is None else dict(QUESTION.findall(section))


def _grounding(root: pathlib.Path, valid: dict, problems: list) -> None:
    try:
        listed = rules(root)
    except ValueError as err:
        problems.append("sim/grounding.py: %s" % err)
        return
    rows, asked = section_6(root), questions(root)
    if rows is None:
        problems.append("%s cannot be read, so no trial a rule names can be found in section 6" % DESIGN)
    else:
        # A trial has one row: a second could answer a quote the first no longer does (the security pass on #265).
        listed_rows = ROW.findall(_section_6(root))
        for trial in sorted({t for t in listed_rows if listed_rows.count(t) > 1}):
            problems.append("%s: section 6 has more than one row for %s; a trial has one" % (DESIGN, trial))
    try:
        quoted = asks(root)
    except ValueError as err:
        problems.append("sim/grounding.py: %s" % err)
        quoted = None
    named = {}
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
        named[code] = trials
        for trial in trials if rows is not None else ():
            if trial not in rows:
                problems.append("sim/grounding.py: %s: %s has no row in section 6; add the trial there first"
                                % (code, trial))
                continue
            # A trial a rule names asks it in its row: the rule quotes the words of the row's question that do, so a
            # row that never asked it, or stops asking it, refuses the rule (issue 265).
            quote = (quoted.get(code) or {}).get(trial) if quoted is not None else None
            if quoted is not None and asked is not None and not (
                    isinstance(quote, str) and len(WORD.findall(quote)) >= QUOTED_WORDS and _quoted(quote, asked.get(trial, ""))):
                problems.append("sim/grounding.py: %s: %s's row in section 6 does not ask it; quote in ASKS the words "
                                "of its question that do, at least %d, or name the trial whose row does"
                                % (code, trial, QUOTED_WORDS))
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
        for one in fixtures:
            if not isinstance(one, str) or not one.startswith("trials/"):
                problems.append("sim/grounding.py: %s: %s is not a fixture in trials/" % (code, one))
            elif not (root / one).is_file():
                problems.append("sim/grounding.py: %s: %s does not exist" % (code, one))
            elif one not in valid:
                problems.append("sim/grounding.py: %s: %s is not a valid fixture" % (code, one))
            elif not trials:
                problems.append("sim/grounding.py: %s: no trial asks this; add one to section 6 first" % code)
            elif valid[one]["trial"] not in trials:
                problems.append("sim/grounding.py: %s: %s records %s, and %s asks this"
                                % (code, one, valid[one]["trial"], " or ".join(trials)))
    # A quote is of a trial its rule names, and of no other.
    for code, by_trial in sorted((quoted or {}).items(), key=lambda kv: str(kv[0])):
        for trial in sorted(set(by_trial) - set(named.get(code) or ()), key=str):
            problems.append("sim/grounding.py: ASKS quotes %s for %s, which %s; take it out"
                            % (trial, code, "names no such trial" if code in named else "is no rule"))
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
