"""Compare the Factory repo's live rulesets with `config/rulesets.json`, from answers already read and redacted.

`tools/rulesets_drift.sh` reads them through the Maintainer's own login, at their terminal or a session's, never in
CI: it writes each answer outside the repo, redacts it with `tools/redact_trial.py`, deletes the raw answer, and runs
this on what is left. `--ids LIST` prints the id of each ruleset the list names, for the script to read. Given the
directory, this prints each difference, one sentence to a line, and exits 1 on any; it prints "no drift" and exits 0
when the live rulesets are exactly what the file records. It is no check: `make verify` reads nothing from GitHub.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def answer(path: pathlib.Path) -> tuple:
    """A redacted answer's status and its body as JSON; a status of 0 and None when it cannot be read."""
    try:
        text = path.read_text()
        head, body = text.replace("\r\n", "\n").split("\n\n", 1)
        return int(head.split()[1]), json.loads(body)
    except (OSError, ValueError, IndexError):
        return 0, None


def shape(ruleset: dict) -> dict:
    """A ruleset as GitHub answers it, in the form config/rulesets.json records it: each rule keyed by its type."""
    ref = (ruleset.get("conditions") or {}).get("ref_name") or {}
    rules, seen = {}, []
    for rule in ruleset.get("rules") or []:
        seen.append(rule.get("type"))
        rules[rule.get("type")] = rule.get("parameters", {})
    if len(seen) != len(set(seen)):
        rules["(a rule type given twice)"] = sorted(t for t in set(seen) if seen.count(t) > 1)
    return {"id": ruleset.get("id"), "target": ruleset.get("target"), "enforcement": ruleset.get("enforcement"),
            "include": ref.get("include"), "exclude": ref.get("exclude"),
            "bypass_actors": ruleset.get("bypass_actors"), "rules": rules}


def ids(listed) -> list:
    """The id of each ruleset in GitHub's list, each a whole number."""
    return [r["id"] for r in listed if isinstance(r, dict) and type(r.get("id")) is int] if isinstance(listed, list) else []


def compare(recorded: dict, listed, live: dict) -> list:
    """Every way the live rulesets differ from the recorded ones. `live` maps an id to its (status, body)."""
    if not isinstance(listed, list):
        return ["GitHub's list of the repo's rulesets could not be read; read it again"]
    problems = []
    names = {}
    for item in listed:
        name = item.get("name") if isinstance(item, dict) else None
        names[name] = item.get("id") if isinstance(item, dict) else None
        if name not in recorded:
            problems.append("the live ruleset %r is not in config/rulesets.json; record it, or take it off the repo" % (name,))
    for name, want in sorted(recorded.items()):
        if name not in names:
            problems.append("config/rulesets.json records the ruleset %r, and the repo has none of that name" % name)
            continue
        status, body = live.get(names[name], (0, None))
        if status != 200 or not isinstance(body, dict):
            problems.append("the ruleset %r was answered %s, not 200; read it again" % (name, status))
            continue
        got = shape(body)
        for key in sorted(set(want) | set(got)):
            if key == "rules":
                for rule in sorted(set(want["rules"]) | set(got["rules"])):
                    if want["rules"].get(rule) != got["rules"].get(rule):
                        problems.append("ruleset %r, rule %s: config/rulesets.json records %s and GitHub says %s" % (
                            name, rule, json.dumps(want["rules"].get(rule), sort_keys=True),
                            json.dumps(got["rules"].get(rule), sort_keys=True)))
            elif want.get(key) != got.get(key):
                problems.append("ruleset %r, %s: config/rulesets.json records %s and GitHub says %s" % (
                    name, key, json.dumps(want.get(key), sort_keys=True), json.dumps(got.get(key), sort_keys=True)))
    return problems


def main(argv: list) -> int:
    if len(argv) == 2 and argv[0] == "--ids":
        status, listed = answer(pathlib.Path(argv[1]))
        print("\n".join(str(i) for i in ids(listed if status == 200 else None)))
        return 0
    if len(argv) != 1:
        print("usage: python3 -m tools.rulesets_drift DIR, or --ids LIST", file=sys.stderr)
        return 2
    folder = pathlib.Path(argv[0])
    recorded = json.loads((ROOT / "config" / "rulesets.json").read_text())["rulesets"]
    status, listed = answer(folder / "list")
    if status != 200:
        listed = None
    live = {i: answer(folder / ("ruleset-%d" % i)) for i in ids(listed)}
    problems = compare(recorded, listed, live)
    print("\n".join(problems) or "no drift")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
