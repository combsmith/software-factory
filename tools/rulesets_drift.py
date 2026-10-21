"""Compare the Factory repo's live rulesets with `config/rulesets.json`, from answers already read and redacted.

`tools/rulesets_drift.sh` reads them through the Maintainer's own login, at their terminal or a session's, never in
CI: it writes each answer outside the repo, redacts it with `tools/redact_trial.py`, deletes the raw answer, and feeds
what is left to this on stdin, so this opens no path it is given. With `--ids`, stdin is the list, and this prints the
id of each ruleset it names, for the script to read. Without, stdin is the list and then each of those rulesets in that
order, each answer ended by a NUL; this prints each difference, one sentence to a line, and exits 1 on any, or prints
"no drift" and exits 0 when the live rulesets are exactly what the file records. It is no check: `make verify` reads
nothing from GitHub. The script runs it as `python3 -I`, so the scratch directory it runs beside shadows no module.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = 100     # rulesets_drift.sh reads one page of this many; a full page may not be all


def answer(text: str) -> tuple:
    """A redacted answer's status and its body as JSON; a status of 0 and None when it cannot be read."""
    try:
        head, body = text.replace("\r\n", "\n").split("\n\n", 1)
        return int(head.split()[1]), json.loads(body)
    except (ValueError, IndexError):
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
    if len(listed) >= PAGE:
        problems.append("GitHub listed %d rulesets, a whole page, so more may follow unread; read the rest" % len(listed))
    # A ruleset is known by its name and its id together: an org's ruleset may share a repo ruleset's name.
    pairs = [(item.get("name"), item.get("id")) if isinstance(item, dict) else (None, None) for item in listed]
    for name, number in pairs:
        if name not in recorded or recorded[name].get("id") != number:
            problems.append("the live ruleset %r, id %s, is not in config/rulesets.json; record it, or take it off the "
                            "repo" % (name, number))
    for name, want in sorted(recorded.items()):
        if (name, want.get("id")) not in pairs:
            problems.append("config/rulesets.json records the ruleset %r, id %s, and the repo has none of that name "
                            "and id" % (name, want.get("id")))
            continue
        status, body = live.get(want.get("id"), (0, None))
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


def main(argv: list, stdin=None) -> int:
    data = (stdin if stdin is not None else sys.stdin.buffer).read().decode("utf-8", "replace")
    if argv == ["--ids"]:
        status, listed = answer(data)
        print("\n".join(str(i) for i in ids(listed if status == 200 else None)))
        return 0
    if argv:
        print("usage: rulesets_drift.py [--ids] < answers, each ended by a NUL", file=sys.stderr)
        return 2
    recorded = json.loads((ROOT / "config" / "rulesets.json").read_text())["rulesets"]
    chunks = data.split("\0")
    status, listed = answer(chunks[0])
    numbers = ids(listed if status == 200 else None)
    answers = [answer(chunk) for chunk in chunks[1:1 + len(numbers)]]
    problems = [] if len(answers) == len(numbers) else [
        "%d rulesets were listed and %d answers given; read them again" % (len(numbers), len(answers))]
    problems += compare(recorded, listed if status == 200 else None, dict(zip(numbers, answers)))
    print("\n".join(problems) or "no drift")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
