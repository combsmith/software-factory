"""Whether a job of a workflow takes its settings only from files on the base's protected list (issue 1177; the Factory
Builder's ruling 2a of 2026-11-27 on record 0239).

Record 0239's first row refuses `push_commits` where a job that holds a secret takes its configuration from a file a
Factory patch may change. A file on the base's list is not one: a Role's push that touches it is refused, and the list
is read again at each push (decision 0188). So such a job passes this clause where every file it takes its settings
from is on that list. This guard holds that clause alone, and fails closed: what it does not read as the table below
says is refused, never passed.

- `refusal(path, text, listed)`: None where every job of the workflow at `path`, of text `text`, takes its settings
  only from files `listed` holds, or the one reason, a code, why not:
  - `UNREADABLE`: a path, a text or a list of no exact kind; a control character but the line feed, a tab among them,
    or what YAML may read as a line's end, a carriage return, U+0085, U+2028 or U+2029, or the byte order mark,
    anywhere; a line outside the narrow form (an anchor, an alias, a tag, a block scalar, a flow form, a quote left
    open, a key of another spelling, a key or a job given twice, a dash alone, or a line of no key, wherever it
    stands); a key the table does not name, at the top, in a job or in a step; a job that calls another workflow or
    runs in a container; a step that runs a command (`run:`) or uses an action, at its pin, that `ACTIONS` does not
    name; an input of an action its row does not name; an `env:` name outside `ENV`.
  - `UNLISTED`: a file the job takes its settings from, its own workflow among them, that the list holds neither word
    for word nor under a directory it names.

Every route that points SonarCloud's scan at another settings file is refused: the scan's `args` and `projectBaseDir`
are inputs its row does not name, and `SONAR_SCANNER_OPTS`, `SONAR_SCANNER_JSON_PARAMS` and `SONARQUBE_SCANNER_PARAMS`
are names outside `ENV`. With neither, the scan action at its pin runs the scanner with `-Dsonar.projectBaseDir=.`,
which reads `sonar-project.properties` where the checkout put the repo. The checkout's `path` and `ref` are refused
too, so the file is the commit the run is for, and the scanner's other variables, `SONARCLOUD_URL`, `SONAR_HOST_URL` and
`SONAR_ROOT_CERT` among them, are names outside `ENV`.

Its stated limits:
- Every job read is taken to hold a secret: which jobs do is the rest of record 0239's first row, which waits on
  `adapters/settings.py`. So a job with no secret beside one that has is refused with it. It costs a grant, never
  passes one.
- What an action reads at its pin is read from its source by a person when its row is written: the rows hold the pins
  `.github/workflows/sonarcloud.yml` holds, which decision 0225's row was written from. A new pin is refused until a
  row names it.
- What a listed file says is a person's: a `sonar-project.properties` that names modules points the scanner at files
  of their folders, and this reads no file's text.
- The events and the runner are not read: a runner is taken to be GitHub's own, which keeps nothing of an earlier job
  and sets no variable of its own.
- That `listed` is the base's list, never the head's, is the caller's: `adapters/rules.py` reads it at the base commit.

The caller gives all three arguments; this reads nothing itself.
"""
from __future__ import annotations

UNREADABLE = "settings_unreadable"   # a workflow, or a part of one, this does not read as its table says
UNLISTED = "settings_unlisted"       # a file a job takes its settings from that the base's list does not hold

FOLDER = ".github/workflows/"
KEY = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
# What no value read here begins with: an anchor, an alias, a tag, a block scalar, a flow form, a directive or a
# reserved mark. A flow form is read only as `{}`, the empty mapping `permissions` is often given.
MARKS = "&*!|>{}[]%@`"
# What YAML may read as a line's end, or as nothing, where this reads none: a carriage return, the next line, the line
# and paragraph separators and the byte order mark. Every other character below the space, the DEL and the C1 controls
# are refused with them, a tab among them.
BREAKS = "\r\x85\u2028\u2029\ufeff"
SPACE = " "
DEL = "\x7f"
C1_LAST = "\x9f"
# Keys whose values say nothing of the files a job reads: their values are not read, so may be of any form.
TOP = ("name", "run-name", "on", "permissions", "concurrency")
JOB = ("name", "runs-on", "timeout-minutes", "permissions", "if", "needs", "concurrency", "environment",
       "continue-on-error")
STEP = ("name", "id", "if", "continue-on-error", "timeout-minutes")
# The names an `env:` may give: the scan's token, and the job's own. Any other may point a tool at another file.
ENV = ("SONAR_TOKEN", "GITHUB_TOKEN")
# Each action a job may use, at its pin: the inputs it may be given, and the files of the repo it takes settings from.
ACTIONS = (
    ("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", ("fetch-depth", "persist-credentials"), ()),
    ("actions/setup-java@de7274f081f381c8f8158605e0321c36c376e2e6", ("distribution", "java-version"), ()),
    ("SonarSource/sonarqube-scan-action@d209202bc7d53ff1cc128f7f907dac145c9d6ae9", (), ("sonar-project.properties",)),
)


def _lstrip(said: str) -> str:
    """`said` with the spaces before it taken off."""
    return said[::-1].rstrip(" ")[::-1]


def _value(said: str):
    """The value after a key's colon, its comment taken off and its quotes, or None where it is in no form read here."""
    if said and not said.startswith(" "):
        return None
    plain = _lstrip(said.split(" #")[0].rstrip(" "))
    if plain == "{}":
        return plain
    first = plain[:1]
    if first in ("'", '"'):
        inner = plain[1:-1]
        return inner if len(plain) > 1 and plain[-1:] == first and first not in inner else None
    return None if first and first in MARKS else plain


def _lines(text: str):
    """Each line that is no comment as `(column, item, key, value)`: where its key starts, the column of its list item's
    dash or None, its key, None for an item that is a value alone, and its value; or None where a line is outside the
    narrow form."""
    if any(c < SPACE and c != "\n" or DEL <= c <= C1_LAST or c in BREAKS for c in text):
        return None
    out = []
    for raw in text.split("\n"):
        body = _lstrip(raw)
        if not body or body.startswith("#"):
            continue
        item = None
        if body.startswith("- "):
            item = len(raw) - len(body)
            body = _lstrip(body[1:])
        key, colon, rest = body.partition(":")
        if item is not None and not colon:     # a list item that is a value alone, as `- main`
            key, rest = None, " " + body
        value = _value(rest) if colon or key is None else None
        if key is not None and (not key or any(c not in KEY for c in key)) or value is None:
            return None
        out.append((len(raw) - len(body), item, key, value))
    return out


def _node(key, value, at) -> dict:
    return {"key": key, "value": value, "kids": [], "at": at}


def _tree(lines: list):
    """The lines as a tree of nodes, each a key, its value and its kids, a list item's key None; or None where a node's
    kids stand at more than one column, or a node that has a value has kids too."""
    root = _node(None, "", None)
    stack = [root]
    for column, item, key, value in lines:
        alone = key is None
        for node in (_node(None, value if alone else "", item), _node(key, value, None if alone else column)):
            if node["at"] is None:
                continue
            while stack[-1]["at"] is not None and stack[-1]["at"] >= node["at"]:
                stack.pop()
            kids = stack[-1]["kids"]
            if stack[-1]["value"] or kids and kids[0]["at"] != node["at"]:
                return None
            kids.append(node)
            stack.append(node)
    return root


def _keys(node: dict, allowed: tuple):
    """`{key: node}` of a mapping's kids, or None where one is a list item, given twice or not among `allowed`."""
    out = {}
    for kid in node["kids"]:
        if kid["key"] is None or kid["key"] in out or kid["key"] not in allowed:
            return None
        out[kid["key"]] = kid
    return out


def _flat(node: dict, allowed: tuple) -> bool:
    """Whether `node` is a mapping of `allowed` keys alone, each a value with no kids."""
    return not node["value"] and _keys(node, allowed) is not None and not any(kid["kids"] for kid in node["kids"])


def _env(node) -> bool:
    """Whether an `env:` is a mapping of names `ENV` holds, or absent."""
    return node is None or _flat(node, ENV)


def _job(node: dict):
    """The files of the repo a job takes its settings from, or None where it is not read as the table says."""
    keys = _keys(node, JOB + ("env", "steps"))
    steps = keys.get("steps") if keys else None
    if steps is None or steps["value"] or not _env(keys.get("env")):
        return None
    files = []
    for step in steps["kids"]:
        held = _keys(step, STEP + ("uses", "with", "env"))
        uses = held.get("uses") if held else None
        rows = [(inputs, read) for name, inputs, read in ACTIONS if uses and not uses["kids"] and uses["value"] == name]
        given = held.get("with") if rows else None
        if not rows or not _env(held.get("env")) or given is not None and not _flat(given, rows[0][0]):
            return None
        files += rows[0][1]
    return files


def _listed(name: str, listed: list) -> bool:
    return name in listed or any(entry.endswith("/") and name.startswith(entry) for entry in listed)


def refusal(path, text, listed):
    """None where every job of the workflow at `path`, of `text`, takes its settings only from files on `listed`, the
    base's protected list, or the one reason why not."""
    if type(path) is not str or not path.startswith(FOLDER) or type(text) is not str or type(listed) is not list \
            or not all(type(entry) is str for entry in listed):
        return UNREADABLE
    lines = _lines(text)
    root = _tree(lines) if lines is not None else None
    top = _keys(root, TOP + ("env", "jobs")) if root is not None else None
    jobs = top.get("jobs") if top else None
    names = [job["key"] for job in jobs["kids"]] if jobs else []
    if jobs is None or jobs["value"] or not names or len(dict.fromkeys(names)) != len(names) \
            or not _env(top.get("env")):
        return UNREADABLE
    files = [path]
    for job in jobs["kids"]:
        found = _job(job) if job["key"] is not None and not job["value"] else None
        if found is None:
            return UNREADABLE
        files += found
    return None if all(_listed(name, listed) for name in files) else UNLISTED
