"""Hold each factory environment to `main` alone, from answers already read and redacted (issue 463).

An environment's deployment branches are what keep its keys from another ref's copy of a workflow, and nothing in this repo can
hold that setting: a fixture says only what it was the day it was read. `tools/environments_drift.sh` reads it through the
Maintainer's own login, at a terminal, never in CI: each answer is written outside the repo, redacted by
`tools/redact_trial.py`, the raw answer deleted, and what is left given to this on stdin. With `--names`, stdin is the list, and
this prints the name of each environment to read. Without, stdin is the list and then each one's policies in that order, each
answer ended by a NUL; this prints each difference, one sentence to a line, and exits 1 on any, or prints "no drift" and exits
0. It is no check: `make verify` reads nothing from GitHub. The script runs it from the repo's root, as `python3 -m`.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from adapters.deployments import ENVIRONMENT as RECORDS_ONLY     # a Deployment makes it, it holds no key, and nothing reads a secret there
from tools.rulesets_drift import answer

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = 100     # the script reads one page of this many; a full page may not be all
PLAIN = re.compile(r"[A-Za-z0-9_-]+")
# A job's environment: its value, or, in the mapping's form, the `name:` on the next line. Linear, though SonarCloud reads
# the blanks before the value as overlapping it: an attempt starts only at a line's start, and once past `environment:`
# it ends in `([^\n]*)$`, which matches to the line's end whatever came before, so nothing after the colon fails and
# backtracks. Its input is this repo's own workflow files, read at the Maintainer's terminal.
WORKFLOW = re.compile(r"^[ \t]*environment:[ \t]*(?:#[^\n]*)?(?:\n[ \t]*name:[ \t]*)?([^\n]*)$", re.M)  # NOSONAR
MAIN_ALONE = [("main", "branch")]
OWN_LIST = {"custom_branch_policies": True, "protected_branches": False}


def _environments(value) -> list:
    """Each `environment` a value of a config file names, at any depth."""
    if isinstance(value, dict):
        return [v for k, v in value.items() if k == "environment" and isinstance(v, str)] + _environments(list(value.values()))
    return [name for item in value for name in _environments(item)] if isinstance(value, list) else []


def named(root: pathlib.Path) -> set:
    """Each environment the repo says holds a key: as a workflow's job, a stored credential's, or an App's."""
    found = {_value(name) for path in (root / ".github" / "workflows").glob("*.y*ml") for name in WORKFLOW.findall(path.read_text())}
    for rel in ("credential-ages.json", "apps.json"):
        found.update(_environments(json.loads((root / "config" / rel).read_text())))
    return found


def _value(text: str) -> str:
    """A YAML value as a name: no comment, no quotes. What is left is the name, or what the read will not find."""
    return text.split(" #")[0].strip().strip("\"'")


def _said(value) -> str:
    """A value from GitHub, safe to print: a plain name as it is, and anything else, a control character among it, in repr."""
    return value if isinstance(value, str) and PLAIN.fullmatch(value) else repr(value)


def _rows(listed) -> list:
    rows = listed.get("environments") if isinstance(listed, dict) else None
    return rows if isinstance(rows, list) else []


def names(listed) -> list:
    """The name of each environment to read, in GitHub's order: a plain name, so it is safe in a call, and not the Deployment's."""
    found = [r.get("name") for r in _rows(listed) if isinstance(r, dict) and isinstance(r.get("name"), str)]
    return [name for name in found if PLAIN.fullmatch(name) and name != RECORDS_ONLY]


def compare(listed, policies: dict, wanted: set) -> list:
    """Every way the environments are not `main` alone. `policies` maps a name to its (status, body)."""
    if not isinstance(listed, dict) or not isinstance(listed.get("environments"), list):
        return ["GitHub's list of the repo's environments could not be read; read it again"]
    rows, problems = [r for r in listed["environments"] if isinstance(r, dict)], []
    if listed.get("total_count") != len(rows):
        problems.append("GitHub counts %s environments and gave %d; read it again" % (_said(listed.get("total_count")), len(rows)))
    if len(rows) >= PAGE:
        problems.append("GitHub listed %d environments, a whole page, so more may follow unread" % len(rows))
    seen = {r.get("name") for r in rows if isinstance(r.get("name"), str)}
    for name in sorted(wanted - seen - {RECORDS_ONLY}):
        problems.append("%s is named here for a key, and GitHub has no such environment" % name)
    if RECORDS_ONLY in wanted:
        problems.append("%s records Deployments alone, and is named here for a key; hold it, or take the key away" % RECORDS_ONLY)
    for row in rows:
        name = row.get("name")
        if name == RECORDS_ONLY:
            continue
        if name not in names({"environments": [row]}):
            problems.append("an environment is named %r, which cannot be read into a call" % (name,))
            continue
        if row.get("can_admins_bypass") is not False:
            problems.append("%s: admins can bypass it" % name)
        if row.get("deployment_branch_policy") != OWN_LIST:
            problems.append("%s: its deployment branches are not a list of their own" % name)
        status, body = policies.get(name, (0, None))
        if status != 200 or not isinstance(body, dict) or not isinstance(body.get("branch_policies"), list):
            problems.append("%s: its deployment branches were answered %s" % (name, status))
            continue
        shown = [(p.get("name"), p.get("type")) if isinstance(p, dict) else (None, None) for p in body["branch_policies"]]
        if body.get("total_count") != len(shown):
            problems.append("%s: GitHub counts %s policies and gave %d" % (name, _said(body.get("total_count")), len(shown)))
        if shown != MAIN_ALONE:
            said = ", ".join(_said(n) if t == "branch" else "%s (%s)" % (_said(n), _said(t)) for n, t in shown) or "nothing"
            problems.append("%s: deploys from %s, and not main alone" % (name, said))
    return problems


def main(argv: list, stdin=None) -> int:
    if argv not in ([], ["--names"]):
        print("usage: environments_drift.py [--names] < answers, each ended by a NUL", file=sys.stderr)
        return 2
    data = (stdin if stdin is not None else sys.stdin.buffer).read().decode("utf-8", "replace")
    chunks = [answer(chunk) for chunk in data.split("\0")[:-1]]
    status, listed = chunks[0] if chunks else (0, None)
    listed = listed if status == 200 else None
    if argv:
        print("\n".join(names(listed)))
        return 0
    wanted = names(listed)
    if listed is not None and len(chunks) - 1 != len(wanted):
        print("%d environments were listed and %d answers given; read them again" % (len(wanted), len(chunks) - 1))
        return 1
    problems = compare(listed, dict(zip(wanted, chunks[1:])), named(ROOT))
    print("\n".join(problems) or "no drift")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
