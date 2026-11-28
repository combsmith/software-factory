"""Whether a job of a workflow takes its settings only from files on the base's protected list (issue 1177; the Factory
Builder's ruling 2a of 2026-11-27 on record 0239).

Record 0239's first row refuses `push_commits` where a job that holds a secret takes its configuration from a file a
Factory patch may change. A file on the base's list is not one: a Role's push that touches it is refused, and the list
is read again at each push (decision 0188). So such a job passes this clause where every file it takes its settings
from is on that list. This guard holds that clause alone, and fails closed: what it does not read as the table below
says is refused, never passed.

- `refusal(path, text, listed)`: None where every job of the workflow at `path`, of text `text`, takes its settings
  only from files `listed` holds, or the one reason, a code, why not:
  - `UNREADABLE`: a path, a text or a list of no exact kind, or a path of no file right in the folder; a control character but the line feed, a tab among them,
    or what YAML may read as a line's end, a carriage return, U+0085, U+2028 or U+2029, or the byte order mark,
    anywhere; a line outside the narrow form (an anchor, an alias, a tag, a block scalar but a key's `|` or `>`
    with a chomping mark or none, a flow form, a quote left open, a key of another spelling, a key or a job given twice, a dash alone, or a line of no key, wherever it
    stands); a key the table does not name, at the top, in a job or in a step; a job that calls another workflow or
    runs in a container; a step that runs a command (`run:`) beside `uses:`, `with:` or an `env:` name outside
    `ENV`; one that uses an action, at its pin, that `ACTIONS` does not name; an input of an action its row does not name, or one whose value holds an expression, `${{`, which may read
    a file; a job whose steps are no list of items, or none; an `env:` name outside `ENV`; a quoted `{}`; a double-quoted value that
    holds an escape.
  - `UNLISTED`: a file the job takes its settings from, its own workflow among them, that the list holds neither word
    for word nor under a directory it names.
  - `STARTED`: a step that runs a command, where a branch but the default may start the workflow. `refusal` is
    told no default branch, so every command is refused there.
- `refusal_at(files, listed, default)`: the same answer for every workflow a commit holds, `files` mapping each one's path to
  its text, but of the jobs that hold a secret alone: the first reason, the workflows in their paths' order, or None.
  A job holds a secret unless all of these are so (record 0239's first row): neither it nor its workflow outside its
  jobs names `secrets`, in any case, as a key or in a value, `secrets: inherit` and `${{ secrets.X }}` among them; it
  calls no other workflow; and its own `permissions:`, or its workflow's where it has none, let its token write
  nothing, `read-all`, `{}`, or each scope `read` or `none`. With neither, the repo's default permission for
  `GITHUB_TOKEN` applies, which `adapters/settings.py` will read: until it does, it is taken as write, so such a job
  holds a secret. A key with a capital, at the job or at the top, is taken to hold one too, as Actions may read a
  key in any case. A workflow's lines are still read whole in the narrow form, a job that holds no secret among them, so
  that what a job names is never hidden: lines this does not read are `UNREADABLE`, and so is no mapping of path to
  text. Its keys at the top and its `env:` are held to the table only where one of its jobs holds a secret.
  A command such a job runs passes only where its workflow is on the list, as every job's must be, and its `on:` names
  nothing but `workflow_dispatch`, `schedule`, and `push` with a list of `branches` that names `default` alone, word
  for word (the Solution Architect's ruling 1 of 2026-11-28): no branch but the default can then start it before a
  review. `on: workflow_dispatch` alone passes too. Any other event, its list form, a `push:` with no list or with
  more beside it, a `default` that is no text, and a push's filter where `default` holds a pattern's mark, refuse the
  command as `STARTED`. A command of no text, `{}` among it, is `UNREADABLE`.
  A workflow on the list that no branch but the default may start passes whole, its actions and `env:` unread (the
  record of pull request 1378's follow-up): a patch cannot change it, and a work branch cannot start it. So does one
  whose one trigger is `workflow_call`, where every job in the folder that names it, at least one, calls it by its
  path here from a workflow itself passed so, or at `home`'s Release or Channel tag, `factory/...`, word for word.
  Any other call that names it refuses it, and so does a chain of callers past `DEPTH` or one that comes back. In
  such a workflow, a job that holds a secret must call a workflow of this folder by its path, or `home`'s at such a
  tag, or run on a label `HOSTED` names; else it is `UNREADABLE`. The poller's shim, `SHIM`, passes whole on the list
  word for word but for its comments, its call held as such a job's is. Every job that holds a secret and runs steps
  runs on a label `HOSTED` names, wherever its workflow stands.

Every route that points SonarCloud's scan at another settings file is refused: the scan's `args` and `projectBaseDir`
are inputs its row does not name, and `SONAR_SCANNER_OPTS`, `SONAR_SCANNER_JSON_PARAMS` and `SONARQUBE_SCANNER_PARAMS`
are names outside `ENV`. With neither, the scan action at its pin runs the scanner with `-Dsonar.projectBaseDir=.`,
which reads `sonar-project.properties` where the checkout put the repo. The checkout's `path` and `ref` are refused
too, so the file is the commit the run is for, and the scanner's other variables, `SONARCLOUD_URL`, `SONAR_HOST_URL` and
`SONAR_ROOT_CERT` among them, are names outside `ENV`.

Its stated limits:
- `refusal` takes every job to hold a secret, so a job with no secret beside one that has is refused with it.
  `refusal_at` reads which jobs hold one, but takes the repo's default permission as write: it costs a push, never
  passes one.
- A command is read as text only: what it runs is the base's, from the default branch after a review, or from the
  ref a person dispatches. A command a person wrote that fetches a work branch, or checks one out, runs that
  branch's files beside its secret, from the schedule too: what a listed workflow says is a person's. A person or an App that may dispatch a workflow on a work branch runs that branch's files
  beside its secret; that is theirs, as the ruling says, never a Role's.
- A job that calls another workflow is read only in a workflow passed whole, or as the shim's. What a call at the
  home repo's tag runs is the Release's, so whoever may move a `factory/` tag changes it: the tag's protection is the
  boundary. A repo outside the folder that calls a workflow here, at any ref, runs it with its own secrets, never
  this repo's; for a Consumer that is a term of the grant. Callers are read in `files` alone: that the caller gives
  both the base's and the branch head's is the caller's.
- The Actions cache a job may write is not read: no action the table names restores one, and a command is given no
  cache's token by the table.
- What an action reads at its pin is read from its source by a person when its row is written: the rows hold the pins
  `.github/workflows/sonarcloud.yml` holds, which decision 0225's row was written from. A new pin is refused until a
  row names it.
- What a listed file says is a person's: a `sonar-project.properties` that names modules points the scanner at files
  of their folders, and this reads no file's text.
- A runner named by a label `HOSTED` holds is taken to be GitHub's own, on Linux, which keeps nothing of an earlier
  job, sets no variable of its own, and reads a file's name in its case: a self-hosted runner given such a label is
  the org's setting. A job that holds no secret may run anywhere, and a self-hosted runner it poisons is issue 1380's.
- That a listed file is a plain file, not a link to an unlisted one, is the caller's to read in the tree. A file
  `.gitattributes` may change how a listed file's bytes land, never what a person wrote in it.
- What an analyser reads as source to analyse is not settings, as decision 0239 says: a `tsconfig.json` among them.
- That `listed` is the base's list, never the head's, is the caller's: `adapters/rules.py` reads it at the base commit.

The caller gives every argument; this reads nothing itself.
"""
from __future__ import annotations

UNREADABLE = "settings_unreadable"   # a workflow, or a part of one, this does not read as its table says
UNLISTED = "settings_unlisted"       # a file a job takes its settings from that the base's list does not hold
STARTED = "settings_started"         # a command run beside a secret, in a workflow a branch but the default may start

FOLDER = ".github/workflows/"
KEY = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
# What no value read here begins with: an anchor, an alias, a tag, a block scalar, a flow form, a directive or a
# reserved mark. A flow form is read only as `{}`, the empty mapping `permissions` is often given.
MARKS = "&*!|>{}[]%@`"
# A block scalar, read only as a key's value: literal or folded, its chomping mark or none, no indentation mark.
BLOCKS = ("|", "|-", "|+", ">", ">-", ">+")
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
# What a `permissions:` may give a scope, or the whole token, that lets it write nothing. Anything else, a scope's
# `write` or `write-all` among it, or no `permissions:` at the job or its workflow, lets the token write.
QUIET = ("read", "none")
QUIET_ALL = ("read-all", "{}")
# The events a workflow beside whose secret a command runs may start on: a person's dispatch, the schedule, and a push
# to a list of branches that names the default branch alone. Every other, `pull_request`, `pull_request_target`,
# `workflow_run`, `workflow_call` and a push to every branch among them, refuses the command.
DISPATCH = "workflow_dispatch"
EVENTS = ("workflow_dispatch", "schedule")
# What a branch filter reads as a pattern: a default branch's name with one is never matched word for word.
PATTERN = "*?+[]!"
# A workflow a job calls: by its path in this folder, run at the caller's own commit, or in the home repo at a Release's
# tag, `factory/v1.2.3`, or a Channel's, `factory/v0-next` or `factory/v0-stable`, run as released (decision 1378's
# follow-up; the Solution Architect's rulings of 2026-11-28).
CALL = "workflow_call"
LOCAL = "./.github/workflows/"
TAG = "@factory/"
CHANNELS = ("next", "stable")
SEMVER = ("major", "minor", "patch")
DIGITS = "0123456789"
NAME = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-."
WORKFLOW_ENDS = (".yml", ".yaml")
# How many workflows deep a called one's callers are followed: a chain longer, or one that comes back to itself, refuses.
DEPTH = ("caller", "its caller", "the caller of that")
# The labels of GitHub's own Linux runners, the only ones a job that holds a secret may run on: any other, a
# self-hosted runner's among them, or an expression, is refused (the Solution Architect's ruling of 2026-11-28).
HOSTED = ("ubuntu-latest", "ubuntu-24.04", "ubuntu-22.04", "ubuntu-24.04-arm", "ubuntu-22.04-arm")
# The poller's shim, frozen, word for word but for its comments: it checks out nothing, calls the pass at the home
# repo's Channel, and reads nothing of what woke it, so a run a work branch ends gives that branch only the timing
# (the Solution Architect's option A of 2026-11-28). `tests/test_guards.py` pins it to `tools/check_workflows.py`'s.
SHIM = """name: sf-poller
on:
  schedule:
    - cron: "13 * * * *"
    - cron: "33 * * * *"
    - cron: "53 * * * *"
  workflow_dispatch:
  workflow_run:
    workflows:
      - factory
      - ci
    types:
      - completed
permissions: {}
jobs:
  pass:
    permissions:
      actions: write
      contents: read
    concurrency:
      group: sf-poller
      cancel-in-progress: false
    uses: combsmith/software-factory/.github/workflows/pass.yml@factory/v0-next
    secrets: inherit
"""
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
        whole = len(plain) > 1 and plain[-1:] == first and first not in inner
        # A quoted `{}` is the text, not the empty mapping: it is read nowhere, so never as quiet permissions.
        return inner if whole and not (first == '"' and "\\" in inner) and inner != "{}" else None
    return None if first and first in MARKS else plain


def _lines(text: str):
    """Each line that is no comment as `(column, item, key, value)`: where its key starts, the column of its list item's
    dash or None, its key, None for an item that is a value alone, and its value; or None where a line is outside the
    narrow form. A key's block scalar, `|` or `>` with a chomping mark or none, takes as its value every line after it
    that is blank or stands right of its key, comments among them, joined as written; a line left of its first that
    is not blank, which YAML reads as neither, is outside the form. The value is compared as written, never folded, so
    a block scalar is never read as a quiet `permissions:` or an event's name."""
    if any(c < SPACE and c != "\n" or DEL <= c <= C1_LAST or c in BREAKS for c in text):
        return None
    out = []
    left = text.split("\n")[::-1]
    while left:
        raw = left.pop()
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
        column = len(raw) - len(body)
        if colon and rest.startswith(" ") and _lstrip(rest).rstrip(" ") in BLOCKS:
            kept, first = [], None
            while left and (not left[-1].rstrip(" ") or len(left[-1]) - len(_lstrip(left[-1])) > column):
                line = left.pop()
                at = len(line) - len(_lstrip(line))
                first = first or line.rstrip(" ") and at
                if line.rstrip(" ") and at < first:
                    return None
                kept.append(line)
            value = "\n".join(kept)
        else:
            value = _value(rest) if colon or key is None else None
        if key is not None and (not key or any(c not in KEY for c in key)) or value is None:
            return None
        out.append((column, item, key, value))
    return out


def _node(key, value, at) -> dict:
    return {"key": key, "value": value, "kids": [], "at": at}


def _tree(lines: list):
    """The lines as a tree of nodes, each a key, its value and its kids, a list item's key None; or None where a node's
    kids stand at more than one column, a node that has a value has kids too, or a key is given twice beside itself."""
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
            if stack[-1]["value"] or kids and kids[0]["at"] != node["at"] \
                    or node["key"] is not None and any(kid["key"] == node["key"] for kid in kids):
                return None
            kids.append(node)
            stack.append(node)
    return root


def _keys(node: dict, allowed: tuple):
    """`{key: node}` of a mapping's kids, or None where one is a list item or not among `allowed`."""
    out = {}
    for kid in node["kids"]:
        if kid["key"] is None or kid["key"] not in allowed:
            return None
        out[kid["key"]] = kid
    return out


def _flat(node: dict, allowed: tuple) -> bool:
    """Whether `node` is a mapping of `allowed` keys alone, each a value with no kids."""
    return not node["value"] and _keys(node, allowed) is not None and not any(kid["kids"] for kid in node["kids"])


def _env(node) -> bool:
    """Whether an `env:` is a mapping of names `ENV` holds, or absent."""
    return node is None or _flat(node, ENV)


def _hosted(node: dict) -> bool:
    """Whether a job runs on one of GitHub's own Linux runners, its `runs-on:` one label `HOSTED` names."""
    runs = [kid for kid in node["kids"] if kid["key"] == "runs-on"]
    return bool(runs) and not runs[0]["kids"] and runs[0]["value"] in HOSTED


def _job(node: dict, started: bool):
    """The files of the repo a job takes its settings from, `STARTED` where a step runs a command and `started` says a
    branch but the default may start the workflow, or None where it is not read as the table says."""
    keys = _keys(node, JOB + ("env", "steps"))
    steps = keys.get("steps") if keys else None
    if steps is None or steps["value"] or not steps["kids"] or not _env(keys.get("env")) or not _hosted(node) \
            or any(kid["key"] is not None for kid in steps["kids"]):
        return None
    files = []
    for step in steps["kids"]:
        held = _keys(step, STEP + ("uses", "with", "env", "run"))
        run = held.get("run") if held else None
        if run is not None and run["value"] not in ("", "{}") and "uses" not in held and "with" not in held and _env(held.get("env")):
            if started:
                return STARTED
            continue
        uses = held.get("uses") if held and run is None else None
        rows = [(inputs, read) for name, inputs, read in ACTIONS if uses and not uses["kids"] and uses["value"] == name]
        given = held.get("with") if rows else None
        if not rows or not _env(held.get("env")) or given is not None and (
                not _flat(given, rows[0][0]) or any("${{" in kid["value"] for kid in given["kids"])):
            return None
        files += rows[0][1]
    return files


def _branches(node: dict, default: str) -> bool:
    """Whether a `push:` names a list of branches alone, and in it `default` alone, word for word, where `default` holds
    no mark a filter reads as a pattern."""
    named = node["kids"][0]["kids"] if [kid["key"] for kid in node["kids"]] == ["branches"] else []
    return bool(named) and not any(c in PATTERN for c in default) \
        and all(kid["key"] is None and not kid["kids"] and kid["value"] == default for kid in named)


def _started(root: dict, default) -> bool:
    """Whether a branch but `default`, the default branch, may start the workflow: true unless its `on:` names
    `workflow_dispatch` alone, or a mapping of `workflow_dispatch`, `schedule` and a `push:` that `_branches` holds."""
    on = [kid for kid in root["kids"] if kid["key"] == "on"]
    if type(default) is not str or not default or not on:
        return True
    if not on[0]["kids"]:
        return on[0]["value"] != DISPATCH
    return not all(kid["key"] in EVENTS or kid["key"] == "push" and _branches(kid, default) for kid in on[0]["kids"])


def _number(said: str) -> bool:
    return bool(said) and all(c in DIGITS for c in said)


def _tag(tag: str) -> bool:
    """Whether `tag`, after `factory/`, is a Release's, `v1.2.3`, or a Channel's, `v0-next` or `v0-stable`."""
    major, dash, channel = tag[1:].partition("-")
    parts = tag[1:].split(".")
    return tag[:1] == "v" and (_number(major) and channel in CHANNELS if dash else
                               len(parts) == len(SEMVER) and all(_number(part) for part in parts))


def _file(name: str) -> bool:
    """Whether `name` is a workflow's file name right in the folder, of the characters a port reads one by."""
    return any(name.endswith(end) for end in WORKFLOW_ENDS) and all(c in NAME for c in name)


def _home(uses: str, home) -> str:
    """The file `uses` calls in the home repo `home`, `owner/name`, at a Release's or a Channel's tag, all word for
    word; or "" where it is no such call."""
    owner, slash, name = home.partition("/") if type(home) is str else ("", "", "")
    if not (owner and name and all(c in NAME for c in owner + name)) or type(uses) is not str:
        return ""
    called, at, tag = uses[len(home + "/" + FOLDER):].partition(TAG) if uses.startswith(home + "/" + FOLDER) else ("", "", "")
    return called if at and _file(called) and _tag(tag) else ""


def _jobs(root: dict) -> list:
    named = [kid for kid in root["kids"] if kid["key"] == "jobs"]
    return named[0]["kids"] if named else []


def _calls(roots: dict) -> list:
    """`(path, uses)` for each job of each workflow read that calls another, `path` its own workflow's."""
    return [(path, kid["value"]) for path, root in roots.items() if root is not None
            for job in _jobs(root) for kid in job["kids"] if kid["key"] == "uses"]


def _called(root: dict) -> bool:
    """Whether the workflow's one trigger is `workflow_call`: `on: workflow_call`, or a mapping of it alone."""
    on = [kid for kid in root["kids"] if kid["key"] == "on"]
    return bool(on) and (on[0]["value"] == CALL and not on[0]["kids"] or [kid["key"] for kid in on[0]["kids"]] == [CALL])


def _gated(path: str, roots: dict, listed: list, default, home, seen: tuple) -> bool:
    """Whether no branch but `default` may start the workflow at `path` before a review, and it is on `listed`: its
    triggers `_started` passes, or its one trigger is `workflow_call` and every job in the folder that names it calls
    it, at least one, either by its path here from a workflow itself gated, or at the home repo's Release tag. Any
    other call that names it, another repo's, a branch's, a commit's or a tag of another shape, refuses it. Callers
    are followed `DEPTH` deep; one that comes back to `path` refuses."""
    root = roots.get(path)
    if root is None or not _listed(path, listed) or path in seen or len(seen) == len(DEPTH):
        return False
    if not _called(root):
        return not _started(root, default)
    name = path[len(FOLDER):]
    naming = [(at, uses) for at, uses in _calls(roots) if type(uses) is str and uses.partition("@")[0].endswith("/" + FOLDER + name)]
    return bool(naming) and all(_home(uses, home) == name or uses == LOCAL + name
                                and _gated(at, roots, listed, default, home, seen + (path,)) for at, uses in naming)


def _call(job: dict, roots: dict, home) -> bool:
    """Whether a job of a gated workflow is read as the table says: it calls a workflow of this folder by its path or
    the home repo's at a Release tag, or it runs on GitHub's own runner."""
    uses = [kid for kid in job["kids"] if kid["key"] == "uses"]
    if not uses:
        return _hosted(job)
    value = uses[0]["value"] if not uses[0]["kids"] else None
    return type(value) is str and (bool(_home(value, home)) or value.startswith(LOCAL) and FOLDER + value[len(LOCAL):] in roots)


def _root(text):
    """The workflow's lines as a tree, or None where they are outside the narrow form."""
    lines = _lines(text) if type(text) is str else None
    return _tree(lines) if lines is not None else None


def _listed(name: str, listed: list) -> bool:
    return name in listed or any(entry.endswith("/") and name.startswith(entry) for entry in listed)


def _named(nodes: list) -> bool:
    """Whether `secrets` is named, in any case, by the key or the value of any of `nodes` or of a node under one."""
    left = list(nodes)
    while left:
        node = left.pop()
        if "secrets" in ((node["key"] or "") + " " + node["value"]).casefold():
            return True
        left += node["kids"]
    return False


def _capital(nodes: list) -> bool:
    """Whether a key of `nodes` has a capital: Actions may read a key in any case, so `Permissions:` is never passed over."""
    return any(node["key"] is not None and node["key"] != node["key"].casefold() for node in nodes)


def _quiet(node: dict) -> bool:
    """Whether a `permissions:` node lets the token write nothing: `read-all`, `{}`, or scopes each `read` or `none`."""
    if node["kids"]:
        return all(kid["key"] is not None and kid["value"] in QUIET for kid in node["kids"])
    return node["value"] in QUIET_ALL


def _holds(job: dict, outer: bool, given: list) -> bool:
    """Whether a job holds a secret, as record 0239 says: it names `secrets`, or `outer` says its workflow does outside
    the jobs; it calls another workflow, which this does not read; or its token may write, by its own `permissions:`,
    else its workflow's, `given`, else the repo's default, taken as write until `adapters/settings.py` reads it. A key
    with a capital, at the job or, by `outer`, at the top, is taken to hold one too."""
    own = [kid for kid in job["kids"] if kid["key"] == "permissions"]
    given = own or given
    return outer or _capital(job["kids"]) or _named([job]) or any(kid["key"] == "uses" for kid in job["kids"]) \
        or not given or not _quiet(given[0])


def _read(path, text, listed, narrow: bool, default, roots=None, home=None):
    """`refusal`'s answer, of every job where `narrow` is false, or of each job that holds a secret where it is true;
    a command is read only where `default`, the default branch, alone may start the workflow. Where `narrow` is true,
    `roots` maps each workflow of the commit to its tree, and `home` names the home repo: a workflow `_gated` passes
    holds its secret-holding jobs only to `_call`, and the poller's shim, word for word, passes whole."""
    name = path[len(FOLDER):] if type(path) is str and path.startswith(FOLDER) else ""
    if "/" in name or name in ("", ".", "..") or type(text) is not str or type(listed) is not list \
            or not all(type(entry) is str for entry in listed):
        return UNREADABLE
    lines = _lines(text)
    root = _tree(lines) if lines is not None else None
    named = [kid for kid in root["kids"] if kid["key"] == "jobs"] if root is not None else []
    jobs = named[0] if named and all(kid["key"] is not None for kid in root["kids"]) else None
    if jobs is None or jobs["value"] or not jobs["kids"] \
            or any(job["key"] is None or job["value"] or not job["kids"] for job in jobs["kids"]):
        return UNREADABLE
    # What the workflow says outside its jobs is read once, for every job.
    outside = [kid for kid in root["kids"] if kid["key"] != "jobs"]
    outer = _named(outside) or _capital(root["kids"])
    given = [kid for kid in outside if kid["key"] == "permissions"]
    held = [job for job in jobs["kids"] if not narrow or _holds(job, outer, given)]
    if not held:
        return None
    if narrow and _listed(path, listed) and lines == _lines(SHIM):
        return None if all(_call(job, roots, home) for job in held) else UNREADABLE
    if narrow and _gated(path, roots, listed, default, home, ()):
        return None if all(_call(job, roots, home) for job in held) else UNREADABLE
    top = _keys(root, TOP + ("env", "jobs"))
    if top is None or not _env(top.get("env")):
        return UNREADABLE
    files = [path]
    started = _started(root, default)
    for job in held:
        found = _job(job, started)
        if found is None or found == STARTED:
            return found or UNREADABLE
        files += found
    return None if all(_listed(name, listed) for name in files) else UNLISTED


def refusal(path, text, listed):
    """None where every job of the workflow at `path`, of `text`, takes its settings only from files on `listed`, the
    base's protected list, or the one reason why not."""
    return _read(path, text, listed, False, None)


def refusal_at(files, listed, default, home):
    """None where, in every workflow a commit holds, each job that holds a secret takes its settings only from files on
    `listed`, the base's protected list; or the first reason why not, the workflows taken in their paths' order.
    `files` maps each workflow's path to its text, every one the folder holds, as a port read them whole; `default`
    names the default branch and `home` the home repo, `owner/name`."""
    kinds = type(files) is dict and type(listed) is list and all(type(entry) is str for entry in listed)
    if not kinds or not all(type(path) is str for path in files):
        return UNREADABLE
    roots = {path: _root(files[path]) for path in files}
    for path in sorted(files):
        why = _read(path, files[path], listed, True, default, roots, home)
        if why is not None:
            return why
    return None
