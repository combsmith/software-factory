"""The Release's rules beyond a schema (#197's rulings 4 and 6). Run by `make verify`.

The ring file, `release/rings.json`, validates as `rings/1` in `tools/check_examples.py`; what no schema can say is
held here: no repo and Intent family is served by two Channels (decision 0010, on the Factory's side), and both
Channels name one major. A fixture in `release/fixtures/` is what GitHub answered a Release's read or step, and holds
no credential and no header a trial's fixture may not keep, by `tools/check_trials.py`'s own scan; one of a Release's runs,
`release-fixture/1`, is held to its schema here whatever its name, and says nothing its own exchanges do not show: the
run, of `release.yml` and its conclusion, its one job, and the step's inputs and last line as that job's log shows them,
a log that keeps the step's lines alone (ruling 9′, as amended on 2026-11-03). The rules that cut and move, `release/cut.py`, and that name a commit's Release,
`release/current.py`, are pure: they import nothing but each other, and name nothing that reads, writes or runs.

The decision points, `release/decision-points.json`, validate as `decision-points/1` there too; held here is what no
schema can say (decision 0193): a point is recorded once; what the Maintainer writes of it, `decided`, `day` and `by`,
is written whole or not at all, in the name `config/hooks.json` gives him and no other, on or after the day the
counts were read; the counts are read on the day of the event they stop at, or after; and no share of the merged pull
requests is greater than their count. Whose hand wrote it, no check here can say.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re

from tools import check_trials
from tools.check_purity import FORBIDDEN_NAMES
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
RINGS = "release/rings.json"
FIXTURES = "release/fixtures"
API_REPO = "/repos/combsmith/software-factory"
WORKFLOW = ".github/workflows/release.yml"
# A line of GitHub's log of a job: its time, then what was said. A fixture's log keeps the release step's lines
# alone: its group; its inputs, two spaces, the name and its value; its last line; and how its process exited.
LOG_LINE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z (.*)$")
GROUP = "##[group]Run python3 -m release.move"
INPUT = re.compile(r"^  RELEASE_(COMMAND|VERSION|TO|CUT_COMMIT): ?(\S*)$")
PRINTED = '{"writes": '
EXIT = re.compile(r"^##\[error\]Process completed with exit code [0-9]+\.$")
SCHEMAS = ("release-fixture", "trial")
PURE = ("release/cut.py", "release/current.py")
# What the rules may import: the future's annotations, and each other, never the CLI that reads files.
ALLOWED_IMPORTS = {"__future__"} | {"release." + pathlib.PurePath(rel).stem for rel in PURE}
POINTS = "release/decision-points.json"
HOOKS = "config/hooks.json"
# What the Maintainer writes of a decision point, in his own hand: all three, or none.
DECISION = ("decided", "day", "by")
# What is counted of the pull requests merged before a point's event: each a share of them.
SHARES = ("the_maintainers", "touched_protected")


def ring_problems(value) -> list:
    """What is wrong with a ring file that its schema let through: nothing, or each sentence."""
    problems, served = [], {}
    lines, channels = value.get("serves"), value.get("channels")
    for line in (lines if isinstance(lines, list) else []):
        if not isinstance(line, dict):
            continue
        repo = line.get("repo")
        # GitHub names a repo whatever its case: one repo spelled two ways is one repo (decision 0080).
        key = (repo.casefold() if isinstance(repo, str) else repo, line.get("family"))
        if key in served and served[key] != line.get("channel"):
            problems.append("serves: %s, family %s, is served by two Channels, %s and %s"
                            % (key[0], key[1], served[key], line.get("channel")))
        served.setdefault(key, line.get("channel"))
    tags = [c.get("tag") for c in (channels.values() if isinstance(channels, dict) else []) if isinstance(c, dict)]
    majors = {tag.split("/v", 1)[1].split("-")[0] for tag in tags if isinstance(tag, str) and "/v" in tag}
    if len(majors) > 1:
        problems.append("channels: name majors %s; both Channels are of one major" % ", ".join(sorted(majors)))
    return problems


def maintainer(root: pathlib.Path = ROOT):
    """The login `config/hooks.json` names the Maintainer by, or None: the file is not read, or names none."""
    try:
        named = json.loads((root / HOOKS).read_text())
    except (OSError, ValueError):
        return None
    named = named.get("maintainer") if isinstance(named, dict) else None
    login = named.get("login") if isinstance(named, dict) else None
    return login if isinstance(login, str) and login else None


def _count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def point_problems(value, maintainer) -> list:
    """What is wrong with the decision points that their schema let through: nothing, or each sentence. `maintainer`
    is the login `config/hooks.json` names, or None, and then nobody's decision counts."""
    problems, seen = [], []
    points = value.get("points") if isinstance(value, dict) else None
    for i, point in enumerate(points if isinstance(points, list) else []):
        if not isinstance(point, dict):
            continue
        if point.get("point") in seen:
            problems.append("points[%d]: %s is recorded twice; a decision point is recorded once" % (i, point.get("point")))
        seen.append(point.get("point"))
        shown = point.get("shown") if isinstance(point.get("shown"), dict) else {}
        for share in SHARES:
            if _count(shown.get("merged")) and _count(shown.get(share)) and shown[share] > shown["merged"]:
                problems.append("points[%d]: shown.%s is %d of %d merged; a share is no greater than its whole"
                                % (i, share, shown[share], shown["merged"]))
        read_on, before = shown.get("read_on"), shown.get("before")
        # A day is one text format, in UTC, so days compare as text. What is counted merged before the event, so it
        # is read on the event's day or after.
        if isinstance(read_on, str) and isinstance(before, str) and read_on < before[:10]:
            problems.append("points[%d]: the counts were read on %s, before the event they stop at, %s" % (i, read_on, before))
        written = [point.get(field) is not None for field in DECISION]
        if any(written) and not all(written):
            problems.append("points[%d]: decided, day and by are written together, or none is" % i)
        if not all(written):
            continue
        by, day = point["by"], point["day"]
        # GitHub names a login whatever its case: one login spelled two ways is one account.
        if not (isinstance(by, str) and isinstance(maintainer, str) and by.casefold() == maintainer.casefold()):
            problems.append("points[%d]: decided by %s; only the Maintainer %s names records continue or stop"
                            % (i, by, HOOKS))
        # He decides on what he was shown, never before it.
        if isinstance(day, str) and isinstance(read_on, str) and day < read_on:
            problems.append("points[%d]: decided on %s, before the counts were read on %s" % (i, day, read_on))
    return problems


def _impure(path: pathlib.Path, rel: str) -> list:
    tree = ast.parse(path.read_text(), filename=rel)
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "release":
            mods = ["release." + alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or "."] if node.level == 0 else ["."]
        else:
            mods = []
        for mod in mods:
            if mod not in ALLOWED_IMPORTS:
                problems.append("%s:%d imports %s; the Release's rules import nothing but each other"
                                % (rel, node.lineno, mod))
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            problems.append("%s:%d names %s; the Release's rules read, write and run nothing" % (rel, node.lineno, node.id))
    return problems


def _answer(exchanges, call: str):
    """The body of the one read of `call`, which GitHub answered 200, or None: the read is missing, refused, or made
    twice, whatever the other was answered."""
    found = [e["response"] for e in exchanges if isinstance(e, dict)
             and isinstance(e.get("request"), dict) and isinstance(e.get("response"), dict)
             and str(e["request"].get("call", "")).split(" ")[:2] == ["GET", call]]
    return found[0].get("body") if len(found) == 1 and found[0].get("status") == 200 else None


def _disagrees(item, i: int) -> list:
    """Where an item of `release-fixture/1` says other than its own exchanges: its run, of release.yml and its
    conclusion; the step's inputs and last line, as the log of that run's job shows them (ruling 9′, as amended)."""
    exchanges = item.get("exchanges") if isinstance(item, dict) else None
    if not isinstance(exchanges, list):
        return []
    run = item.get("run")
    found = _answer(exchanges, "%s/actions/runs/%s" % (API_REPO, run))
    if not (isinstance(found, dict) and found.get("id") == run and found.get("path") == WORKFLOW
            and found.get("conclusion") == item.get("conclusion")):
        return ["items[%d]: run %s is not read once among its exchanges, of %s, concluded %s"
                % (i, run, WORKFLOW, item.get("conclusion"))]
    jobs = _answer(exchanges, "%s/actions/runs/%s/jobs" % (API_REPO, run))
    jobs = jobs.get("jobs") if isinstance(jobs, dict) else None
    if not (isinstance(jobs, list) and len(jobs) == 1 and isinstance(jobs[0], dict) and jobs[0].get("run_id") == run):
        return ["items[%d]: run %s's jobs are not read once, as its one job, the release job" % (i, run)]
    log = _answer(exchanges, "%s/actions/jobs/%s/logs" % (API_REPO, jobs[0].get("id")))
    if not isinstance(log, str):
        return ["items[%d]: the log of run %s's job is not read once among its exchanges" % (i, run)]
    said = [LOG_LINE.match(line) for line in log.splitlines()]
    said = [line.group(2) if line else None for line in said]
    # The log keeps the step's lines alone, its group first: a line the trim left in is refused, not passed over.
    if said[:1] != [GROUP] or not all(line == GROUP or INPUT.match(line) or EXIT.match(line)
                                      or line.startswith(PRINTED) for line in said if line is not None) \
            or None in said or said.count(GROUP) != 1:
        return ["items[%d]: run %s's log keeps a line beyond the step's group, its inputs, its last line and its exit"
                % (i, run)]
    asked = {given.group(1).lower(): given.group(2) for given in map(INPUT.match, said) if given}
    printed = [n for n, line in enumerate(said) if line.startswith(PRINTED)]
    # The step's last line is the last it said: nothing follows it but how its process exited.
    if printed and not all(EXIT.match(line) for line in said[printed[-1] + 1:]):
        printed = []
    try:
        printed = json.loads(said[printed[0]]) if len(printed) == 1 else None
    except ValueError:
        printed = None
    problems = []
    if asked != item.get("asked"):
        problems.append("items[%d]: asked is not the step's inputs as run %s's log shows them" % (i, run))
    if printed is None or printed != item.get("printed"):
        problems.append("items[%d]: printed is not the step's last line as run %s's log shows it" % (i, run))
    return problems


def fixture_problems(value, rel: str) -> list:
    """What a Release fixture holds that it must not: a credential anywhere, or a header a trial's fixture drops; and
    for `release-fixture/1`, an item that says other than its own exchanges."""
    problems = ["%s: %s %s" % (rel, where, what) for where, what in check_trials._credentials(value, "")]
    value = value if isinstance(value, dict) else {}
    if value.get("schema") == "release-fixture/1":
        # Every fixture of a Release's runs is held to its schema here, whatever its name: none is passed over.
        schemas = {kind: json.loads((ROOT / "schemas" / ("%s.schema.json" % kind)).read_text()) for kind in SCHEMAS}
        problems += ["%s: %s" % (rel, err) for err in validate(value, schemas["release-fixture"], schemas=schemas)]
    items = value.get("items") if value.get("schema") == "release-fixture/1" else None
    if items is None:
        groups = [("exchanges", value.get("exchanges"))]
    else:
        groups = [("items[%d].exchanges" % i, item.get("exchanges") if isinstance(item, dict) else None)
                  for i, item in enumerate(items if isinstance(items, list) else [])]
        for i, item in enumerate(items if isinstance(items, list) else []):
            problems += ["%s: %s" % (rel, p) for p in _disagrees(item, i)]
    for where, exchanges in groups:
        for i, exchange in enumerate(exchanges if isinstance(exchanges, list) else []):
            for side in ("request", "response"):
                held = (exchange.get(side) or {}).get("headers") if isinstance(exchange, dict) else None
                for name in (held if isinstance(held, dict) else {}):
                    if str(name).lower() not in check_trials.HEADERS:
                        problems.append("%s: %s[%d].%s.headers holds %s, which a fixture does not keep"
                                        % (rel, where, i, side, name))
    if not any(isinstance(exchanges, list) and exchanges for _, exchanges in groups):
        problems.append("%s: holds no exchange" % rel)
    return problems


def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    rings = root / RINGS
    if not rings.is_file():
        return ["%s is missing; both Channels and the ring file exist from the first commit" % RINGS]
    try:
        value = json.loads(rings.read_text())
    except ValueError as err:
        return ["%s is not JSON: %s" % (RINGS, err)]
    if isinstance(value, dict):
        problems += ["%s: %s" % (RINGS, p) for p in ring_problems(value)]
    for path in sorted((root / FIXTURES).glob("*")) if (root / FIXTURES).is_dir() else []:
        rel = path.relative_to(root).as_posix()
        try:
            problems += fixture_problems(json.loads(path.read_text()), rel)
        except ValueError as err:
            problems.append("%s is not JSON: %s" % (rel, err))
    for rel in PURE:
        path = root / rel
        problems += _impure(path, rel) if path.is_file() else ["%s is missing" % rel]
    points = root / POINTS
    if not points.is_file():
        return problems + ["%s is missing; the first decision point is recorded from slice 1's event" % POINTS]
    try:
        problems += ["%s: %s" % (POINTS, p) for p in point_problems(json.loads(points.read_text()), maintainer(root))]
    except ValueError as err:
        problems.append("%s is not JSON: %s" % (POINTS, err))
    return problems


if __name__ == "__main__":
    import sys
    found = run()
    for p in found:
        print(p)
    sys.exit(1 if found else 0)
