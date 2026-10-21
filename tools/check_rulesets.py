"""The repo's rulesets agree with the Lenses: each required check is a deterministic Lens's, from that Lens's App.

`config/rulesets.json` records the rulesets as GitHub answered the Maintainer's read of them, and its schema holds
what a ruling fixed (issues 62 and 95). This check holds the values written in two files to each other: a check the
`main` ruleset requires is the `check` of a deterministic Lens in `config/defaults.json`, pinned to that Lens's
`app_id`; `verify`'s check is among them, so GitHub merges nothing the verification check has not passed; and each
tool of the code-scanning rule is the check of a deterministic Lens that no workflow runs. Whether the live rulesets
still say this is `tools/rulesets_drift.sh`'s, run by hand: nothing here reads GitHub.
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRANCH = "main"
VERIFY = "verify"


def run(root: pathlib.Path = ROOT) -> list:
    try:
        return _agree(root)
    except (AttributeError, TypeError) as err:
        return ["config/rulesets.json or config/defaults.json holds a value of the wrong kind, so they cannot be "
                "compared; make each match its schema: %s" % err]


def _agree(root: pathlib.Path) -> list:
    try:
        rulesets = json.loads((root / "config" / "rulesets.json").read_text())["rulesets"]
        lenses = json.loads((root / "config" / "defaults.json").read_text())["required_lenses"]["deterministic"]
        rules = rulesets[BRANCH]["rules"]
    except (OSError, ValueError, KeyError, TypeError) as err:
        return ["config/rulesets.json or config/defaults.json cannot be read as rulesets and Lenses: %s" % err]
    by_check = {lens.get("check"): lens for lens in lenses if isinstance(lens, dict)}
    problems = []
    required = (rules.get("required_status_checks") or {}).get("required_status_checks") or []
    for item in required:
        item = item if isinstance(item, dict) else {}
        check, app = item.get("context"), item.get("integration_id")
        lens = by_check.get(check)
        if lens is None:
            problems.append("config/rulesets.json: the %s ruleset requires the check %r, which no deterministic Lens "
                            "in config/defaults.json reads; name the Lens there or take the check out" % (BRANCH, check))
        elif app != lens.get("app_id"):
            problems.append("config/rulesets.json: the %s ruleset pins the check %r to App %r, and config/defaults.json "
                            "reads Lens %s from App %r; make them agree" % (BRANCH, check, app, lens.get("lens"),
                                                                          lens.get("app_id")))
    named = {item.get("context") for item in required if isinstance(item, dict)}
    if VERIFY not in {by_check[check].get("lens") for check in named if check in by_check}:
        problems.append("config/rulesets.json: the %s ruleset does not require the %s Lens's check, so GitHub could "
                        "merge what it has not passed; require it, pinned to its App" % (BRANCH, VERIFY))
    tools = (rules.get("code_scanning") or {}).get("code_scanning_tools") or []
    for item in tools:
        tool = item.get("tool") if isinstance(item, dict) else None
        lens = by_check.get(tool)
        if lens is None or lens.get("workflow") is not None:
            problems.append("config/rulesets.json: the code-scanning rule names the tool %r, which is no deterministic "
                            "Lens's check that no workflow runs in config/defaults.json; make them agree" % (tool,))
    return problems


if __name__ == "__main__":
    found = run()
    print("\n".join(found) or "rulesets ok")
    raise SystemExit(1 if found else 0)
