"""Rules every workflow obeys, read from its text.

There is no YAML parser here, so a workflow is written in a narrow form that needs none: block
style, even indents, bare keys, one key to a line. Anything outside that form is refused,
which is what stops a rule being dodged by spelling a key another way. The rules allow what is
named and refuse the rest: the events, the commands, the places an expression may stand.

Each rule has at least one counter-example under examples/workflows/invalid/, named for the rule,
that must be rejected for that rule and no other. A rule with no counter-example fails this check.

It also holds the configuration's required Lenses to the workflows that run them (lens_workflows): a Lens whose App is
GitHub Actions names its workflow file and no other Lens names one, and the file it names exists, runs on both
pull_request and merge_group, and has a job whose own `name:`, or whose id where it has none, is the Lens's check,
with no `strategy.matrix` and no `uses:`. Its one job-level `if:` is exactly `always()`, beside a `needs:` that names
every other job in its file, and then it judges them with `tools/needs_passed.py`, the base's: its one checkout is
of the base, never the head. Only `jobs.<id>.name` is read: a workflow's or a step's `name:` names no check run.

The secret scan, the exempt `ci.yml`, reads its rules from the base (scan_problems): `.gitleaks.toml` and
`.gitleaksignore` from a checkout of the base under `base/`, with the head's `.gitleaksignore` deleted first, since
gitleaks also reads the one at the top of what it scans. Its install is held word for word, its version and checksum
free only within their shapes; and every checkout in every workflow is the one CHECKOUT lists.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
RULES = {
    "form": "block style, even indents, bare keys with the colon against them; no tab, flow mapping, anchor "
            "or quoted key",
    "pin": "an action is pinned to a full commit hash with its version beside it; one of the org's own "
           "reusable workflows, to its channel tag; nothing local but a reusable workflow",
    "target": "a workflow runs only on pull_request, merge_group, push, schedule, workflow_dispatch or "
              "workflow_call, and never on pull_request_target",
    "permissions": "permissions are declared at the top and grant nothing that can write; never read-all or write-all; "
                   "and no job is granted security-events: write, with which an upload could stand for CodeQL's verdict",
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
EVENTS = {"pull_request", "merge_group", "push", "schedule", "workflow_dispatch", "workflow_call"}
# The id GitHub gives the App GitHub Actions: it reports every job in every workflow of the repo.
ACTIONS_APP = 15368
# A workflow the org requires as it wrote it. It is exempt from the rules named and from no other,
# and it is held to its text by a hash taken with the pins left out: to change it, change this.
EXEMPT = {
    "ci.yml": (("install",), "d926b2135508f3799b02cfc2741d6017435399f8ec054c3f171dcd79236ba627"),    # the org's secret scan downloads gitleaks
}
MAX_RUN_LINES = 10
ENTRY = re.compile(r"^( *)(- )?([A-Za-z_][\w-]*):(?: (.*))?$")
ITEM = re.compile(r"^( *)- (\S.*)$")
COMMAND = re.compile(r"^(make [\w.-]+|python3 -m [\w.]+)$")
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
# The org's rule for its own reusable workflows: a channel tag, never a branch and never a hash.
CHANNEL = re.compile(r"^combsmith/[\w.-]+/\.github/workflows/[\w.-]+\.ya?ml@[\w.-]+/(v\d+-)?(stable|next)$")
LOCAL = re.compile(r"^\./\.github/workflows/[\w.-]+\.ya?ml$")
VERSION = re.compile(r"^#\s*v\d")
RUNNER = re.compile(r"^[a-z]+-\d+(\.\d+)?(-[a-z0-9]+)*$")
IMAGE = re.compile(r"^[\w./-]+(:[\w.-]+|@sha256:[0-9a-f]{64})$")
WHOLE = re.compile(r"^\$\{\{ [^{}]+ \}\}$")
SECRET = re.compile(r"\bsecrets\b(\.(\w+)|\[\s*['\"](\w+)['\"]\s*\])?")
PERSONAL = re.compile(r"(?:^|_)PAT(?:_|$)", re.I)
PIN = re.compile(r"@[0-9a-f]{40} # v[\w.]+")
# The one actions/checkout every workflow uses, and its version. PIN makes any two pins equal where a text is compared
# word for word, so this is what holds the checkout to a version that has `ref:` and `path:` (decision 0023). A bump of
# actions/checkout changes it here too, so a bot's bump cannot merge on its own.
CHECKOUT = ("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "# v7.0.1")
CHECKOUT_USE = re.compile(r"^actions/checkout[@/]", re.I)
# What a Lens's job that needs others has: the one job-level if: that cannot skip it, the step that judges what it
# needs, and the results that step reads.
ALWAYS = "always()"
JUDGE = "python3 -m tools.needs_passed"
NEEDS = "${{ toJSON(needs) }}"
# The commit a pull request, or a merge-queue entry, is judged against (decision 0023). A judging job checks out this and
# nothing else; the secret scan, which also runs on a push to main, falls back to the commit pushed.
BASE = "${{ github.event.pull_request.base.sha || github.event.merge_group.base_sha }}"
SCAN = "ci.yml"
SCAN_BASE = "${{ github.event.pull_request.base.sha || github.event.merge_group.base_sha || github.sha }}"
# gitleaks 8.30.1 reads the ignore file named by --gitleaks-ignore-path and also the one at the top of --source, so the
# head's is deleted on the line before. Its own log options are kept, and --text added, so a head's .gitattributes cannot
# mark a file binary and hide it; and an inline gitleaks:allow, which the head writes, passes over nothing.
SCAN_RUN = ["rm -f .gitleaksignore",
            "gitleaks detect --source . --config base/.gitleaks.toml --gitleaks-ignore-path base/.gitleaksignore "
            "--ignore-gitleaks-allow --log-opts=\"--full-history --all --diff-filter=tuxdb --text\" "
            "--redact --verbose --exit-code 1"]
SCAN_CHECKOUTS = [{"fetch-depth": "0", "persist-credentials": "false"},
                  {"path": "base", "ref": SCAN_BASE, "persist-credentials": "false"}]
# What the secret scan's workflow and its one job may hold, and what its install may be given.
SCAN_TOP = {"name", "on", "permissions", "jobs"}
SCAN_JOB = {"name", "runs-on", "timeout-minutes", "permissions", "steps"}
# The install's whole block. It reads the version and the checksum from its env, so they alone are free, each held to its
# shape and quoted: the version goes into the URL's path, where curl folds `/../`, and the checksum can only accept what
# a gitleaks release serves. A gitleaks without a flag of SCAN_RUN exits non-zero, so the scan fails closed.
INSTALL_RUN = ['tarball="gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"',
               'url="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${tarball}"',
               "curl -sSfL --proto '=https' --proto-redir '=https' -o /tmp/gitleaks.tar.gz \"${url}\"",
               'echo "${GITLEAKS_CHECKSUM}  /tmp/gitleaks.tar.gz" | sha256sum -c',
               "tar -xzf /tmp/gitleaks.tar.gz -C /tmp gitleaks",
               "sudo mv /tmp/gitleaks /usr/local/bin"]
SCAN_ENV = {"GITLEAKS_VERSION": re.compile(r'"[0-9]+\.[0-9]+\.[0-9]+"'),
            "GITLEAKS_CHECKSUM": re.compile(r'"[0-9a-f]{64}"')}
# The only events a workflow with a judging job runs on: on any other there is no base, and its checkout would be the head.
JUDGED = {"pull_request", "merge_group"}
JOB = re.compile(r"^[A-Za-z_][\w-]*$")


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
    if any(e["path"][-1:] == ["permissions"] and e["key"] == "security-events" and e["value"] == "write"
           for e in entries):
        found.append(("permissions", "a job is granted security-events: write"))

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
            elif CHECKOUT_USE.match(value) and (value, e["comment"]) != CHECKOUT:
                found.append(("pin", "%s %s is not the listed checkout, %s %s" % ((value, e["comment"]) + CHECKOUT)))
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


def _listed(text: str, entry: dict):
    """The values of `entry`: its own, or the items of the block list under it; None where one is not a job's id."""
    if entry["value"]:
        values = [entry["value"]]
    else:
        values = []
        for raw in text.split("\n")[entry["line"]:]:
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            item = ITEM.match(raw.rstrip())
            if item is None or len(item.group(1)) < entry["indent"]:
                break
            values.append(_unquote(item.group(2).partition(" #")[0].strip()))
    return values if values and all(JOB.match(v) for v in values) else None


def _checkout(entry: dict) -> bool:
    return entry["key"] == "uses" and entry["value"].lower().startswith("actions/checkout@")


def _with(entries: list, step: dict) -> dict:
    """{key: value} under the `with:` of the step that `step`, one of its entries, belongs to."""
    return {e["key"]: e["value"] for e in entries
            if e["step"] == step["step"] and e["path"] == step["path"] + ["with"]}


def _steps(entries: list, job: str) -> list:
    """The steps of `job`, in order: for each, {key: entry} of its own keys."""
    steps = {}
    for e in entries:
        if e["path"] == ["jobs", job, "steps"]:
            steps.setdefault(e["step"], {})[e["key"]] = e
    return [steps[number] for number in sorted(steps)]


def _lines(entry) -> list:
    """The command lines of a `run:` entry: its block, or its one line; none for anything else."""
    return (entry["body"] or [entry["value"]]) if entry and entry["key"] == "run" else []


def _block(entry, bad: list):
    """The command lines of a `run:` entry as bash is given them: None where a line of its file cannot be read, which
    read() leaves out of every block, or where its block is not literal, `|`, since `>` folds its lines into one."""
    if bad or (entry and entry["body"] and entry["value"] != "|"):
        return None
    return _lines(entry)


def scan_problems(text: str) -> list:
    """Why the secret scan in `text` could be passed by the head it scans: its rules not read from the base.

    Its one job runs four steps, in this order and nothing else: the head's checkout, with its history; the base's,
    under `base/`, at the base's commit; the install, whose whole block is INSTALL_RUN, given a version and a checksum
    of their shapes; and the scan, whose whole block is SCAN_RUN, telling gitleaks the base's `.gitleaks.toml` and
    `.gitleaksignore` on the line after the head's `.gitleaksignore` is deleted. Nothing sets an environment, a
    directory or a container that the scan could run in instead. Both blocks are literal, and a file with a line
    read() cannot read, which it leaves out of a block, holds neither.
    """
    entries, bad = read(text)
    problems = []
    jobs = [e["key"] for e in entries if e["path"] == ["jobs"]]
    steps = _steps(entries, jobs[0]) if len(jobs) == 1 else []
    if [_with(entries, e) for e in entries if _checkout(e)] != SCAN_CHECKOUTS:
        problems.append("%s does not check out the head and then the base, under base/ at `ref: %s`, and nothing "
                        "else, so the scan's rules may not be the base's" % (SCAN, SCAN_BASE))
    install = steps[2] if len(steps) == 4 else {}
    given = {e["key"] for e in entries if install.get("env") and e["step"] == install["env"]["step"]
             and e["path"] == install["env"]["path"] + ["env"]}
    shaped = (len(jobs) == 1 and len(steps) == 4
              and {e["key"] for e in entries if e["path"] == []} <= SCAN_TOP
              and {e["key"] for e in entries if e["path"] == ["jobs", jobs[0]]} <= SCAN_JOB
              and all(set(step) <= {"name", "uses", "with"} and _checkout(step.get("uses", {"key": ""}))
                      for step in steps[:2])
              and set(install) <= {"name", "env", "run"} and given == ({*SCAN_ENV} if "env" in install else set())
              and set(steps[3]) <= {"name", "run"})
    if not shaped:
        problems.append("%s does not run, in this order and nothing else, the head's checkout, the base's, the "
                        "install and the scan, with no environment, directory or container of its own: a step could "
                        "change base/ or what the scan reads" % SCAN)
    if _block(install.get("run"), bad) != INSTALL_RUN:
        problems.append("%s does not install gitleaks by INSTALL_RUN, word for word, as its third step's whole literal "
                        "block in a file read whole: another install could put another program where the scan runs "
                        "gitleaks" % SCAN)
    lines = text.split("\n")
    for key, shape in SCAN_ENV.items():
        values = [lines[e["line"] - 1].strip()[len(key) + 2:] for e in entries if e["key"] == key and install.get("env")
                  and e["step"] == install["env"]["step"] and e["path"] == install["env"]["path"] + ["env"]]
        if len(values) != 1 or not shape.fullmatch(values[0]):
            problems.append("%s does not give the install %s once, as %s: a value of another shape could change what "
                            "the install fetches" % (SCAN, key, shape.pattern))
    if _block(steps[-1].get("run") if steps else None, bad) != SCAN_RUN:
        problems.append("%s does not run, as its last step's whole literal block in a file read whole, `%s` on the line "
                        "after `%s`: it could read the head's .gitleaks.toml or .gitleaksignore, and a change could "
                        "widen the allowlist it needs"
                        % (SCAN, SCAN_RUN[1], SCAN_RUN[0]))
    return problems


def _judging(text: str, entries: list, job: str, jobs: list) -> list:
    """Why the job `job`, which has `needs:` or shares its file with other jobs, would pass, or never report, when one
    of them did not pass.

    A job it does not need is a check nobody requires. With a plain `needs:` it is skipped when one fails, and GitHub
    passes a required check that is skipped. Under `if: always()` it runs whatever they did, so it must judge them: run
    tools.needs_passed on `needs` given whole, as its one step but a checkout, and need every other job.
    """
    mine = [e for e in entries if e["path"][:2] == ["jobs", job]]
    inside = {e["key"]: e for e in mine if e["path"] == ["jobs", job]}
    whys = []
    if inside.get("if", {}).get("value") != ALWAYS:
        whys.append("it has no job-level if: always(), so it is skipped when one of them fails, and a skipped "
                    "required check passes")
    needs = _listed(text, inside["needs"]) if "needs" in inside else []
    others = [j for j in jobs if j != job]
    if "needs" not in inside:
        whys.append("it has no needs:, so the other jobs in its file, %s, are checks nobody requires"
                    % ", ".join(others))
    elif needs is None:
        whys.append("its needs: cannot be read as a list of jobs")
    elif sorted(set(needs)) != sorted(others):
        whys.append("it needs %s, not every other job in its file, %s: a job it does not need is a check nobody "
                    "requires" % (", ".join(needs), ", ".join(others) or "none"))
    steps = [e for e in mine if e["path"] == ["jobs", job, "steps"]]
    runs = [e for e in steps if e["key"] == "run"]
    # One line, no block: in a block an earlier line can exit first, and `>` folds the lines into one command.
    judged = [e for e in runs if e["value"] == JUDGE and not e["body"]]
    if not judged:
        whys.append("it runs no step `%s`, on a line of its own, to fail it when one of them did not pass" % JUDGE)
    elif any(e["key"] == "if" and e["step"] == j["step"] for e in steps for j in judged):
        whys.append("an if: can skip its step `%s`" % JUDGE)
    if len(runs) > 1 or any(e["key"] == "uses" and not e["value"].startswith("actions/checkout@") for e in steps):
        whys.append("its steps are more than a checkout and `%s`, and another could act for it" % JUDGE)
    events = {e["key"] for e in entries if e["path"] == ["on"]}
    events |= {e["value"] for e in entries if e["path"] == [] and e["key"] == "on" and e["value"]}
    if events - JUDGED:
        whys.append("its workflow runs on %s, where there is no base to check out, so `ref: %s` would come out empty "
                    "and the checkout would be the head's: run it on pull_request and merge_group alone"
                    % (", ".join(sorted(events - JUDGED)), BASE))
    if [_with(entries, c) for c in steps if _checkout(c)] != [{"persist-credentials": "false", "ref": BASE}]:
        whys.append("its one checkout is not of the base alone, `ref: %s` and persist-credentials: false and nothing "
                    "else, so the head's own tools/needs_passed.py could give its verdict" % BASE)
    if [(e["path"], e["value"]) for e in mine if e["key"] == "NEEDS"] != [(["jobs", job, "env"], NEEDS)]:
        whys.append("it does not give NEEDS: %s once, in its own env:, so what it needs cannot be read" % NEEDS)
    return whys


def lens_job_problems(text: str, check: str) -> list:
    """Why a workflow holding `text` would never report the check run `check` on every head and in the merge queue.

    GitHub names a job's check run by the job's own `name:`, or by its id where it has none; a workflow's or a step's
    `name:` names none. A job with a `strategy.matrix` reports under its name and its values, one with a job-level
    `if:` can be skipped, and one that calls a reusable workflow with `uses:` reports under the caller's and the
    callee's names. A workflow that does not run on both pull_request and merge_group reports on no head, or not in
    the queue. Each would leave the Lens waiting for ever. The one `if:` allowed is `always()`, beside `needs:`, which
    cannot skip the job; a job that needs others is held by _judging.
    """
    entries, _ = read(text)
    top = {e["key"]: e for e in entries if e["path"] == []}
    events = {e["key"] for e in entries if e["path"] == ["on"]}
    if top.get("on", {}).get("value"):
        events.add(top["on"]["value"])
    problems = []
    if not {"pull_request", "merge_group"} <= events:
        problems.append("runs on %s, not on both pull_request and merge_group, so its check would not report on every "
                        "head and in the queue" % (", ".join(sorted(events)) or "nothing"))
    jobs = [e["key"] for e in entries if e["path"] == ["jobs"]]
    named = []
    for job in jobs:
        inside = {e["key"]: e for e in entries if e["path"] == ["jobs", job]}
        if inside.get("name", {}).get("value", job) == check:
            named.append((job, inside))
    if not named:
        return problems + ["runs no job named %r: only a job's own name, or its id where it has none, names its check"
                           % check]
    for job, inside in named:
        matrix = [e for e in entries if e["path"] == ["jobs", job, "strategy"] and e["key"] == "matrix"]
        for there, said in ((matrix, "has a strategy.matrix"),
                            ("if" in inside and (inside["if"]["value"] != ALWAYS or "needs" not in inside),
                             "has a job-level if: other than always() beside needs:"),
                            ("uses" in inside, "calls a reusable workflow with uses:")):
            if there:
                problems.append("has the job %s, and it %s, so its check would never report under that name alone"
                                % (job, said))
        if "needs" in inside or len(jobs) > 1:
            problems += ["has the job %s beside other jobs, and %s" % (job, why)
                         for why in _judging(text, entries, job, jobs)]
    return problems


def lens_workflows(root: pathlib.Path) -> list:
    """Each required Lens names the workflow file it is read from exactly where GitHub Actions runs it, and that file
    reports its check on every head and in the merge queue (lens_job_problems).

    The Kernel reads a Lens whose App is GitHub Actions only from the file `config/defaults.json` names for it, and
    reads a Lens no workflow runs only from a check that names none. A Lens of GitHub Actions with no file could be
    passed by any job in the repo; another App's with one would never be read. A file gone, moved, or whose job would
    never report under the Lens's check name, would leave the Lens unreadable or waiting on every pull request.
    """
    config = root / "config" / "defaults.json"
    if not config.is_file():
        return []
    try:
        lenses = json.loads(config.read_text())["required_lenses"]["deterministic"]
    except (OSError, ValueError, KeyError, TypeError) as err:
        return ["config/defaults.json: required_lenses.deterministic cannot be read, so no Lens's workflow file can be "
                "checked: %r" % err]
    if not isinstance(lenses, list) or not all(isinstance(lens, dict) for lens in lenses):
        return ["config/defaults.json: required_lenses.deterministic is not a list of Lenses, so no Lens's workflow "
                "file can be checked"]
    problems = []
    for lens in lenses:
        rel, where = lens.get("workflow"), "config/defaults.json: the Lens %s" % lens.get("lens")
        actions = lens.get("app_id") == ACTIONS_APP and type(lens.get("app_id")) is int
        if actions and not isinstance(rel, str):
            problems.append("%s is run by GitHub Actions and names no workflow file; name the file whose job runs it"
                            % where)
        if not actions and rel is not None:
            problems.append("%s names the workflow file %s, and only GitHub Actions runs one; make it null" % (where, rel))
        if not isinstance(rel, str):
            continue
        path = root / rel
        if not path.is_file():
            problems.append("%s is read from %s, which does not exist" % (where, rel))
            continue
        if not isinstance(lens.get("check"), str):
            problems.append("%s names no check, so its workflow file cannot be read for it" % where)
            continue
        problems += ["%s is read from %s, which %s" % (where, rel, why)
                     for why in lens_job_problems(path.read_text(errors="replace"), lens["check"])]
    return problems


def run(root: pathlib.Path = ROOT) -> list:
    problems = lens_workflows(root)
    live = sorted((root / ".github" / "workflows").glob("*.y*ml"))
    example = root / "examples" / "workflows" / "verify.yml"
    for path in live + sorted((root / "examples" / "workflows").glob("*.y*ml")):
        text = path.read_text(errors="replace")
        spared, held = EXEMPT.get(path.name, ((), None)) if path in live else ((), None)
        if path in live and path.name == SCAN:
            problems += ["%s: %s" % (path.relative_to(root), p) for p in scan_problems(text)]
        if held and hashlib.sha256(PIN.sub("@PIN", text).encode()).hexdigest() != held:
            problems.append("%s is exempt from a rule, so it is held word for word, and it has changed; "
                            "if the change is meant, record its new hash in EXEMPT" % path.relative_to(root))
        for rule, message in lint(text):
            if rule not in spared:
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
