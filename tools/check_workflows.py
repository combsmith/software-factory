"""Rules every workflow obeys, read from its text.

There is no YAML parser here, so a workflow is written in a narrow form that needs none: block
style, even indents, bare keys, one key to a line. Anything outside that form is refused,
which is what stops a rule being dodged by spelling a key another way. The rules allow what is
named and refuse the rest: the events, the commands, the places an expression may stand.

Each rule has at least one counter-example under examples/workflows/invalid/, named for the rule,
that must be rejected for that rule and no other. A rule with no counter-example fails this check.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
RULES = {
    "form": "block style, even indents, bare keys with the colon against them; no tab, flow mapping, anchor "
            "or quoted key",
    "pin": "an action is pinned to a full commit hash with its version beside it; one of the org's own "
           "reusable workflows, to its channel tag; nothing local but a reusable workflow",
    "target": "a workflow runs only on pull_request, merge_group, schedule, workflow_dispatch or "
              "workflow_call, and never on pull_request_target",
    "permissions": "permissions are declared at the top and grant nothing that can write; never read-all or write-all",
    "expression": "an expression stands only as the whole of a value under env:, with: or secrets:, or in if:",
    "length": "a run: block is at most ten lines",
    "install": "a run: line is `make <target>` or `python3 -m <module>` and nothing else, so nothing is "
               "installed, fetched or decided in a workflow",
    "token": "a secret is named one at a time; none is a personal access token, and secrets are never inherited",
    "queue": "a workflow that runs on pull_request also runs on merge_group, and filters neither",
    "cron": "no schedule fires at minute 0, alone or among other minutes",
    "timeout": "every job that has steps sets timeout-minutes, on the job",
    "runner": "the runner and any container image are named by version, never latest",
    "credentials": "every checkout sets persist-credentials: false",
    "soft": "no step or job continues on error",
}
EVENTS = {"pull_request", "merge_group", "schedule", "workflow_dispatch", "workflow_call"}
MAX_RUN_LINES = 10
ENTRY = re.compile(r"^( *)(- )?([A-Za-z_][\w-]*):(?: (.*))?$")
ITEM = re.compile(r"^( *)- (\S.*)$")
COMMAND = re.compile(r"^(make [\w.-]+|python3 -m [\w.]+)$")
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
# The org's rule for its own reusable workflows: a channel tag, never a branch and never a hash.
CHANNEL = re.compile(r"^petry-projects/[\w.-]+/\.github/workflows/[\w.-]+\.ya?ml@[\w.-]+/(v\d+-)?(stable|next)$")
LOCAL = re.compile(r"^\./\.github/workflows/[\w.-]+\.ya?ml$")
VERSION = re.compile(r"^#\s*v\d")
RUNNER = re.compile(r"^[a-z]+-\d+(\.\d+)?(-[a-z0-9]+)*$")
IMAGE = re.compile(r"^[\w./-]+(:[\w.-]+|@sha256:[0-9a-f]{64})$")
WHOLE = re.compile(r"^\$\{\{ [^{}]+ \}\}$")
SECRET = re.compile(r"\bsecrets\b(\.(\w+)|\[\s*['\"](\w+)['\"]\s*\])?")
PERSONAL = re.compile(r"(?:^|_)PAT(?:_|$)", re.I)
PIN = re.compile(r"@[0-9a-f]{40} # v[\w.]+")


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def read(text: str) -> tuple:
    """(entries, numbers of the lines not in the narrow form). An entry is one `key: value` line.

    Its `path` is the keys above it, `step` numbers the list item it belongs to, and `body` holds
    the lines of a block of text under it.
    """
    entries, bad, stack, step, block = [], [], [], 0, None
    for number, raw in enumerate(text.split("\n"), 1):
        if "\t" in raw or "\r" in raw:
            bad.append(number)
            continue
        if block is not None:
            if not raw.strip() or len(raw) - len(raw.lstrip(" ")) > block["indent"]:
                if raw.strip():
                    block["body"].append(raw.strip())
                continue
            block = None
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        found, item = ENTRY.match(line), ITEM.match(line)
        if found is None:
            if item is None or len(item.group(1)) % 2 or item.group(2)[0] in "{[&*!|>'\"" or \
                    re.search(r":(\s|$)", item.group(2)):
                bad.append(number)
            continue
        indent = len(found.group(1)) + (2 if found.group(2) else 0)
        key, rest = found.group(3), (found.group(4) or "").strip()
        value, _, comment = (rest, "", "") if key == "run" else rest.partition(" #")
        value = value.strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if found.group(2):
            step += 1
        entry = {"key": key, "value": _unquote(value), "comment": "#" + comment if comment else "",
                 "indent": indent, "line": number, "path": [k for _, k in stack], "step": step, "body": []}
        if value in ("|", "|-", "|+", ">", ">-", ">+"):
            block = entry
        elif indent % 2 or (value and value[0] in "{[&*!|>" and not (key == "permissions" and value == "{}")):
            bad.append(number)
        entries.append(entry)
        stack.append((indent, key))
    return entries, bad


def lint(text: str) -> list:
    """(rule, message) for each rule this workflow breaks."""
    entries, bad = read(text)
    found = []

    def under(*path):
        return [e for e in entries if e["path"] == list(path)]

    top = {e["key"]: e for e in under()}
    jobs = under("jobs")
    if bad:
        found.append(("form", "line %d is not in the narrow form" % bad[0]))
    elif "on" not in top or not jobs:
        found.append(("form", "no on: section, or no job that can be read"))

    events = {e["key"] for e in under("on")}
    if top.get("on", {}).get("value"):
        events.add(top["on"]["value"])
    if events - EVENTS:
        found.append(("target", "runs on %s" % ", ".join(sorted(events - EVENTS))))
    filtered = [e for e in entries if e["path"][:2] in (["on", "pull_request"], ["on", "merge_group"])]
    if "pull_request" in events and ("merge_group" not in events or filtered):
        found.append(("queue", "runs on pull_request without merge_group, or behind a filter"))

    grant, granted = top.get("permissions"), under("permissions")
    if grant is None or (grant["value"] != "{}" and not granted) or \
            any(e["value"] not in ("read", "none") for e in granted) or \
            any(e["key"] == "permissions" and e["value"] not in ("", "{}") for e in entries):
        found.append(("permissions", "no top-level permissions, one that can write, or read-all or write-all"))

    for e in entries:
        key, value = e["key"], e["value"]
        if key == "cron" and any(part in ("0", "00") or part[:1] == "*" or part[:2] in ("0-", "0/")
                                 for part in (value.split() or [""])[0].split(",")):
            found.append(("cron", "a schedule that fires at minute 0"))
        if key == "uses" and not LOCAL.match(value) and not CHANNEL.match(value):
            if not PINNED.match(value):
                found.append(("pin", "%s is not pinned to a commit" % value))
            elif not VERSION.match(e["comment"]):
                found.append(("pin", "%s has no version beside its hash" % value.split("@")[0]))
        if key == "runs-on" and not RUNNER.match(value):
            found.append(("runner", "runs on '%s'" % value))
        if key in ("image", "container") and (value or key == "image") and \
                (not IMAGE.match(value) or value.endswith(":latest")):
            found.append(("runner", "uses the image '%s'" % value))
        if key == "continue-on-error" and value != "false":
            found.append(("soft", "continues on error"))
        if key == "secrets" and value:
            found.append(("token", "inherits secrets"))
        if key == "shell":
            found.append(("install", "sets its own shell"))
        if key == "run":
            commands = e["body"] if e["body"] else [value]
            if len(commands) > MAX_RUN_LINES:
                found.append(("length", "a run: block of %d lines" % len(commands)))
            if not all(COMMAND.match(c) for c in commands):
                found.append(("install", "runs something other than make or a module of this repo"))
        if key == "uses" and value.lower().startswith("actions/checkout@"):
            if not [x for x in entries if x["step"] == e["step"] and x["key"] == "persist-credentials"
                    and x["value"] == "false" and x["path"][-1:] == ["with"]]:
                found.append(("credentials", "a checkout keeps its credentials"))

    for job in jobs:
        inside = {e["key"]: e for e in under("jobs", job["key"])}
        if "steps" in inside and not inside.get("timeout-minutes", {}).get("value", "").isdigit():
            found.append(("timeout", "job %s has no timeout-minutes" % job["key"]))

    by_line = {e["line"]: e for e in entries}
    for number, raw in enumerate(text.split("\n"), 1):
        e = by_line.get(number)
        if "${{" in raw:
            passed = e is not None and e["key"] != "script" and (
                e["key"] == "if" or (WHOLE.match(e["value"]) and set(e["path"]) & {"env", "with", "secrets"}))
            if not passed:
                found.append(("expression", "line %d writes an expression where it could become a command" % number))
        for use in SECRET.finditer("" if raw.lstrip().startswith("#") else raw.split(" #")[0]):
            name = use.group(2) or use.group(3)
            keyed = e is not None and e["key"] == "secrets" and use.start() == raw.find("secrets")
            if (name is None and not keyed) or (name and PERSONAL.search(name)):
                found.append(("token", "line %d names a personal token, or every secret at once" % number))
    return sorted(set(found))


def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    live = sorted((root / ".github" / "workflows").glob("*.y*ml"))
    example = root / "examples" / "workflows" / "verify.yml"
    for path in live + sorted((root / "examples" / "workflows").glob("*.y*ml")):
        for rule, message in lint(path.read_text(errors="replace")):
            problems.append("%s: [%s] %s. The rule: %s" % (path.relative_to(root), rule, message, RULES[rule]))
    for folder in sorted((root / ".github").glob("actions*")):
        problems.append("%s: a local action is not read by this check; write a reusable workflow"
                        % folder.relative_to(root))
    if not example.exists():
        return problems + ["examples/workflows/verify.yml, the required check's workflow, is missing"]
    wanted = PIN.sub("@PIN", example.read_text())
    real = root / ".github" / "workflows" / "verify.yml"
    if live and not real.exists():
        problems.append(".github/workflows/ holds workflows and not verify.yml, the required check")
    if real.exists() and PIN.sub("@PIN", real.read_text()) != wanted:
        problems.append("%s is not %s, word for word but for the pins; change both together"
                        % (real.relative_to(root), example.relative_to(root)))
    page = root / "docs" / "standards" / "workflows.md"
    shown = re.search(r"```yaml\n(.*?)```", page.read_text(), re.S) if page.exists() else None
    if shown and PIN.sub("@PIN", shown.group(1)) != wanted:
        problems.append("docs/standards/workflows.md: its example is not %s, word for word but for the pins"
                        % example.relative_to(root))
    tripped = set()
    for path in sorted((root / "examples" / "workflows" / "invalid").glob("*.y*ml")):
        want = path.name.split(".")[0]
        got = sorted({rule for rule, _ in lint(path.read_text())})
        tripped.add(want)
        if got != [want]:
            problems.append("invalid/%s: must break the rule '%s' and no other, and breaks %s"
                            % (path.name, want, got or "none"))
    for rule in sorted(set(RULES) - tripped):
        problems.append("the rule '%s' has no counter-example under examples/workflows/invalid/" % rule)
    return problems
