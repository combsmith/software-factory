"""Rules every workflow obeys, read from its text. There is no YAML parser here, and none is needed.

Each rule has a counter-example under examples/workflows/invalid/, named for the
rule, that must be rejected for that rule and no other. A rule with no
counter-example fails this check: a rule nothing has ever tripped is not known to work.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
RULES = {
    "pin": "an action or reusable workflow from outside this repo is pinned to a full commit hash",
    "target": "no workflow runs on pull_request_target",
    "permissions": "permissions are declared at the top, and never write-all",
    "expression": "no expression is written into a run: block; pass it through env:",
    "length": "a run: block is at most ten lines and calls a module",
    "token": "no personal access token is named, and secrets are never inherited",
    "queue": "a workflow that runs on pull_request also runs on merge_group, with no path filter",
    "cron": "no schedule fires at minute 0",
    "timeout": "every job that has steps sets timeout-minutes",
    "runner": "the runner image is named by version, never -latest",
    "install": "nothing is installed or downloaded in a run: block",
    "credentials": "every checkout sets persist-credentials: false",
    "soft": "no step or job continues on error",
    "form": "the file has an on: section and no tab",
}
MAX_RUN_LINES = 10
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
FETCHES = re.compile(r"\b(pip3? install|npm (install|ci)|npx|curl|wget|apt(-get)? install|brew install)\b")
TRIGGERS = ("pull_request_target", "pull_request", "merge_group", "schedule")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _top(lines: list, key: str) -> list:
    """The lines of one top-level section."""
    out, inside = [], False
    for line in lines:
        if line[:1] not in ("", " ", "#"):
            inside = bool(re.match(r'^["\']?%s["\']?\s*:' % key, line))
        if inside:
            out.append(line)
    return out


def _run_blocks(lines: list) -> list:
    """The text of each run: block, as a list of its lines."""
    blocks, i = [], 0
    while i < len(lines):
        m = re.match(r"^(\s*(?:- )?)run:\s*(.*)$", lines[i])
        i += 1
        if not m:
            continue
        depth, rest = len(m.group(1)), m.group(2).strip()
        body = [] if rest[:1] in ("|", ">") or not rest else [rest]
        while i < len(lines) and (not lines[i].strip() or _indent(lines[i]) > depth):
            body.append(lines[i].strip())
            i += 1
        blocks.append([ln for ln in body if ln])
    return blocks


def lint(text: str) -> list:
    """(rule, message) for each rule this workflow breaks."""
    lines = [ln.rstrip("\n") for ln in text.splitlines()]
    code = [ln for ln in lines if not ln.lstrip().startswith("#")]
    found = []
    on = "\n".join(_top(code, "on"))
    if "\t" in text or not on:
        found.append(("form", "no on: section, or a tab"))
    events = {t for t in TRIGGERS if re.search(r"(?<![\w-])%s(?![\w-])" % t, on)}
    if "pull_request_target" in events:
        found.append(("target", "runs on pull_request_target"))
    if "pull_request" in events and ("merge_group" not in events or re.search(r"^\s+paths(-ignore)?:", on, re.M)):
        found.append(("queue", "runs on pull_request without merge_group, or behind a path filter"))
    for line in code:
        m = re.match(r"^\s*-?\s*cron:\s*['\"]?(\S+)", line)
        if m and m.group(1) in ("0", "00", "*/60"):
            found.append(("cron", "a schedule at minute 0"))
        m = re.match(r"^\s*(?:- )?uses:\s*['\"]?([^'\"\s#]+)", line)
        if m and not m.group(1).startswith("./") and not PINNED.match(m.group(1)):
            found.append(("pin", "%s is not pinned to a commit" % m.group(1)))
        m = re.match(r"^\s*runs-on:\s*(.+)$", line)
        if m and "-latest" in m.group(1):
            found.append(("runner", "runs on %s" % m.group(1).strip()))
        if re.search(r"secrets\.\w*PAT\w*", line) or re.match(r"^\s*secrets:\s*inherit\b", line):
            found.append(("token", "names a personal access token, or inherits every secret"))
        if re.match(r"^\s*(?:- )?continue-on-error:\s*(?!false)", line):
            found.append(("soft", "continues on error"))
    perms = _top(code, "permissions")
    if not perms or any("write-all" in ln for ln in code if re.match(r"^\s*permissions:", ln)):
        found.append(("permissions", "no top-level permissions, or write-all"))
    for block in _run_blocks(code):
        if any("${{" in ln for ln in block):
            found.append(("expression", "an expression inside run:"))
        if len(block) > MAX_RUN_LINES:
            found.append(("length", "a run: block of %d lines" % len(block)))
        if any(FETCHES.search(ln) for ln in block):
            found.append(("install", "installs or downloads in run:"))
    jobs, name, body = {}, None, []
    for line in _top(code, "jobs")[1:]:
        if re.match(r"^  [\w-]+:\s*$", line):
            name = line.strip().rstrip(":")
            jobs[name] = []
        elif name:
            jobs[name].append(line)
    for name, body in sorted(jobs.items()):
        if any(re.match(r"^\s+steps:", ln) for ln in body) and not any("timeout-minutes:" in ln for ln in body):
            found.append(("timeout", "job %s has no timeout-minutes" % name))
    checkouts = len(re.findall(r"uses:\s*actions/checkout@", "\n".join(code)))
    if checkouts > len(re.findall(r"persist-credentials:\s*false", "\n".join(code))):
        found.append(("credentials", "a checkout keeps its credentials"))
    return found


def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    live = sorted((root / ".github" / "workflows").glob("*.y*ml"))
    good = sorted((root / "examples" / "workflows").glob("*.y*ml"))
    for path in live + good:
        for rule, message in lint(path.read_text()):
            problems.append("%s: [%s] %s. The rule: %s" % (path.relative_to(root), rule, message, RULES[rule]))
    if not good:
        problems.append("examples/workflows/ holds no workflow that passes")
    real = root / ".github" / "workflows" / "verify.yml"
    if real.exists() and good and real.read_text() != good[0].read_text():
        problems.append("%s is not %s, word for word; change both together"
                        % (real.relative_to(root), good[0].relative_to(root)))
    page = root / "docs" / "standards" / "workflows.md"
    shown = re.search(r"```yaml\n(.*?)```", page.read_text(), re.S) if page.exists() else None
    if shown and good and shown.group(1) != good[0].read_text():
        problems.append("docs/standards/workflows.md: its example is not %s, word for word" % good[0].relative_to(root))
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
