"""Compare the machine user's live role with `config/machine-user.json`, from answers already read and redacted (issue 89).

`tools/machine_user_drift.sh` reads them through the Maintainer's own login, at a terminal, never in CI: each answer is
written outside the repo, redacted by `tools/redact_trial.py`, the raw answer deleted, and what is left given to this on
stdin, each ended by a NUL, in the order `reads` gives them. With `--reads`, this prints that list of calls for the
script. It prints each difference, one sentence to a line, and exits 1 on any, or prints "no drift" and exits 0. It is no
check: `make verify` reads nothing from GitHub. The script runs it as `python3 -I`.
"""
from __future__ import annotations

import json
import pathlib
import sys

from tools.rulesets_drift import answer

ROOT = pathlib.Path(__file__).resolve().parent.parent


def reads(held: dict) -> list:
    """The calls to read, in order: the user, the org role's teams, the team, then each repo's role and its teams."""
    team = "orgs/%s/teams/%s" % (held["org"], held["code_owner_team"])
    calls = ["users/%s" % held["login"], "orgs/%s/organization-roles/%d/teams" % (held["org"], held["org_role"]["id"]), team]
    for row in held["repos"]:
        calls += ["repos/%s/collaborators/%s/permission" % (row["repo"], held["login"]), "repos/%s/teams" % row["repo"]]
    return calls


def compare(held: dict, answers: list) -> list:
    """Every way what GitHub answered differs from the file. `answers` holds (status, body), in the order of `reads`."""
    calls = reads(held)
    if len(answers) != len(calls):
        return ["%d answers were given for %d reads; read them again" % (len(answers), len(calls))]
    unread = ["%s was answered %s" % (call, status) for call, (status, _) in zip(calls, answers) if status != 200]
    if unread:
        return unread
    bodies = [body for _, body in answers]
    team, problems = held["code_owner_team"], []
    if not isinstance(bodies[0], dict) or bodies[0].get("id") != held["id"]:
        problems.append("%s: config/machine-user.json records id %s and GitHub says otherwise" % (held["login"], held["id"]))
    slugs = [t.get("slug") for t in bodies[1] if isinstance(t, dict)] if isinstance(bodies[1], list) else []
    if team not in slugs:
        problems.append("%s does not hold the org role %s" % (team, held["org_role"]["name"]))
    grants = bodies[2].get("repos_count") if isinstance(bodies[2], dict) else None
    if grants != held["team_repo_grants"]:
        problems.append("%s has %s grants of its own on repos, and config/machine-user.json records %s"
                        % (team, grants, held["team_repo_grants"]))
    for at, row in enumerate(held["repos"]):
        permission, teams = bodies[3 + 2 * at], bodies[4 + 2 * at]
        role = permission.get("role_name") if isinstance(permission, dict) else None
        if role != row["role"]:
            problems.append("%s: %s holds %s, and config/machine-user.json records %s" % (row["repo"], held["login"], role, row["role"]))
        found = [t.get("permission") for t in teams if isinstance(t, dict) and t.get("slug") == team] if isinstance(teams, list) else []
        if found != [row["team_permission"]]:
            problems.append("%s: %s has %s, and config/machine-user.json records %s" % (row["repo"], team, found or "nothing", row["team_permission"]))
    return problems


def main(argv: list, stdin=None) -> int:
    held = json.loads((ROOT / "config" / "machine-user.json").read_text())
    if argv == ["--reads"]:
        print("\n".join(reads(held)))
        return 0
    if argv:
        print("usage: machine_user_drift.py [--reads] < answers, each ended by a NUL", file=sys.stderr)
        return 2
    data = (stdin if stdin is not None else sys.stdin.buffer).read().decode("utf-8", "replace")
    problems = compare(held, [answer(chunk) for chunk in data.split("\0")[:-1]])
    print("\n".join(problems) or "no drift")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
