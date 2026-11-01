"""The repo's rulesets agree with the Lenses: each required check is a deterministic Lens's, from that Lens's App.

`config/rulesets.json` records the rulesets as GitHub answered the Maintainer's read of them, and its schema holds
what a ruling fixed (issues 62 and 95). This check holds the values written in two files to each other: a check the
`main` ruleset requires is the `check` of a deterministic Lens in `config/defaults.json`, pinned to that Lens's
`app_id`; `verify`'s check is among them, so GitHub merges nothing the verification check has not passed; and each
tool of the code-scanning rule is the check of a deterministic Lens that no workflow runs. Whether the live rulesets
still say this is `tools/rulesets_drift.sh`'s, run by hand: nothing here reads GitHub.

The two tag rulesets guard every key, since a shim inherits secrets and its environment's branch policy is met by the
caller's `main` whatever commit the channel names (decision 0113). Each is recorded, active and over its tags; `factory
release tags` lets by the admin role and the release App alone, whose id is `config/apps.json`'s, and no one bypasses
`factory releases are immutable`.

No external Lens's approval counts toward the merge (issue 366): CodeRabbit approves once its threads are resolved, by
whoever resolves them (trials/P-25.json). A `main` ruleset counts an approval when it asks for any number of them, a
code owner's, a required reviewer's, one of the last push, or an extra one for a change no person made. One that does
asks for exactly one, a code owner's, of the last push, with a stale one dismissed on a push, no required reviewer and
no extra one for a change no person made, and `.github/CODEOWNERS` names on every line, a `*` line among them, only the
team through which the machine user is a code owner (issue 198's ruling 2). An App is never a code owner. Whether GitHub
reads each line as written (a team it cannot see makes a line no owner's) is no file's to say.
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRANCH = "main"
VERIFY = "verify"
# The team through which the machine user is a code owner (issue 198's ruling 2).
CODE_OWNER = "@combsmith/org-leads"
CATCH_ALL = "*"     # the one spelling read as every path; another is refused, never guessed at
# The tag rulesets that guard every key (decision 0113), and the rules each must hold.
TAG_RULESETS = {"factory release tags": {"creation", "update", "deletion", "non_fast_forward"},
                "factory releases are immutable": {"update", "deletion", "non_fast_forward"}}
ADMIN_ROLE = 5


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
    review = rules.get("pull_request") or {}
    if review.get("required_approving_review_count", 0) != 0 or review.get("require_code_owner_review") is True \
            or review.get("required_reviewers") or review.get("require_last_push_approval") is True \
            or review.get("require_extra_approval_for_unattributed_changes") is True:
        if review.get("required_approving_review_count") != 1 or review.get("require_code_owner_review") is not True \
                or review.get("require_last_push_approval") is not True \
                or review.get("require_extra_approval_for_unattributed_changes") is not False \
                or review.get("dismiss_stale_reviews_on_push") is not True or review.get("required_reviewers"):
            problems.append("config/rulesets.json: the %s ruleset counts an approval otherwise than as one, a code "
                            "owner's, of the last push, a stale one dismissed, with no required reviewer, so an "
                            "external Lens's approval could count; ask for exactly that" % BRANCH)
        problems += _code_owners(root)
    return problems + _tags(rulesets, root)


def _tags(rulesets: dict, root: pathlib.Path) -> list:
    """What would let a Release tag, and so what every shim calls and every key it hands on, be moved by another."""
    try:
        app_id = json.loads((root / "config" / "apps.json").read_text())["apps"]["release"]["app_id"]
    except (OSError, ValueError, KeyError, TypeError) as err:
        return ["config/apps.json names no release App, so who may write a Release tag cannot be told: %s" % err]
    problems = []
    for name, rules in TAG_RULESETS.items():
        ruleset = rulesets.get(name)
        if not isinstance(ruleset, dict) or ruleset.get("enforcement") != "active" or ruleset.get("target") != "tag" \
                or not set(ruleset.get("rules") or ()) >= rules or not ruleset.get("include"):
            problems.append("config/rulesets.json: the tag ruleset %s is not recorded, active and holding its rules; every "
                            "key's guard is the tag rulesets (decision 0113)" % name)
            continue
        actors = {(a.get("actor_type"), a.get("actor_id")) for a in ruleset.get("bypass_actors") or ()}
        allowed = {("RepositoryRole", ADMIN_ROLE), ("Integration", app_id)} if name == "factory release tags" else set()
        if actors - allowed:
            problems.append("config/rulesets.json: %s lets %s bypass it; only %s may, since it guards every key"
                            % (name, sorted(actors - allowed), sorted(allowed) or "no one"))
    return problems


def _code_owners(root: pathlib.Path) -> list:
    """What lets an approval by anyone but the code owners' team count, in a ruleset that asks for a code owner's."""
    try:
        text = (root / ".github" / "CODEOWNERS").read_text()
    except (OSError, ValueError) as err:
        return [".github/CODEOWNERS cannot be read, so who may approve cannot be told: %s" % err]
    lines = [line.split() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    problems = []
    for words in lines:
        if words[1:] != [CODE_OWNER]:
            problems.append(".github/CODEOWNERS: %s is owned by %s, not by %s alone, so another account's approval "
                            "could count" % (words[0], " ".join(words[1:]) or "no one", CODE_OWNER))
    if not any(words[0] == CATCH_ALL for words in lines):
        problems.append(".github/CODEOWNERS has no line for every path, so a path no code owner holds could merge on "
                        "an external Lens's approval; add `* %s`" % CODE_OWNER)
    return problems


if __name__ == "__main__":
    found = run()
    print("\n".join(found) or "rulesets ok")
    raise SystemExit(1 if found else 0)
