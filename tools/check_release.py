"""The Release's rules beyond a schema (#197's rulings 4 and 6). Run by `make verify`.

The ring file, `release/rings.json`, validates as `rings/1` in `tools/check_examples.py`; what no schema can say is
held here: no repo and Intent family is served by two Channels (decision 0010, on the Factory's side), and both
Channels name one major. A fixture in `release/fixtures/` is what GitHub answered a Release's read or step, and holds
no credential and no header a trial's fixture may not keep, by `tools/check_trials.py`'s own scan; one of a Release's runs,
`release-fixture/1`, says nothing its own exchanges do not show: the run, of `release.yml` and its conclusion, and the
step's inputs and last line as that run's job's log shows them (ruling 9′, as amended on 2026-11-03). The rules that cut and move, `release/cut.py`, and that name a commit's Release,
`release/current.py`, are pure: they import nothing but each other, and name nothing that reads, writes or runs.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re

from tools import check_trials
from tools.check_purity import FORBIDDEN_NAMES

ROOT = pathlib.Path(__file__).resolve().parent.parent
RINGS = "release/rings.json"
FIXTURES = "release/fixtures"
API_REPO = "/repos/combsmith/software-factory"
WORKFLOW = ".github/workflows/release.yml"
# A step's input as GitHub's log of the job shows it, under the step's group: two spaces, the name, and its value.
INPUT = re.compile(r"^  RELEASE_(COMMAND|VERSION|TO|CUT_COMMIT): ?(\S*)$")
PURE = ("release/cut.py", "release/current.py")
# What the rules may import: the future's annotations, and each other, never the CLI that reads files.
ALLOWED_IMPORTS = {"__future__"} | {"release." + pathlib.PurePath(rel).stem for rel in PURE}


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
    """The body of the one read of `call` GitHub answered 200, or None: the read is missing, refused or made twice."""
    found = [e["response"].get("body") for e in exchanges if isinstance(e, dict)
             and isinstance(e.get("request"), dict) and isinstance(e.get("response"), dict)
             and str(e["request"].get("call", "")).split(" ")[:2] == ["GET", call] and e["response"].get("status") == 200]
    return found[0] if len(found) == 1 else None


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
    logs = [_answer(exchanges, "%s/actions/jobs/%s/logs" % (API_REPO, job.get("id"))) for job in
            (jobs if isinstance(jobs, list) else []) if isinstance(job, dict) and job.get("run_id") == run]
    logs = [log for log in logs if isinstance(log, str)]
    if len(logs) != 1:
        return ["items[%d]: the log of run %s's one job is not read once among its exchanges" % (i, run)]
    asked, printed = {}, None
    for line in logs[0].splitlines():
        said = line.partition(" ")[2]
        given = INPUT.match(said)
        if given:
            asked[given.group(1).lower()] = given.group(2)
        elif said.startswith('{"writes": '):
            try:
                printed = json.loads(said)
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
    return problems


if __name__ == "__main__":
    import sys
    found = run()
    for p in found:
        print(p)
    sys.exit(1 if found else 0)
