"""Compare the machine user's live role with `config/machine-user.json`, from answers already read and redacted (issue 89).

`tools/machine_user_drift.sh` reads them through the Maintainer's own login, at a terminal, never in CI: each answer is
written outside the repo, redacted by `tools/redact_trial.py`, the raw answer deleted, and what is left given to this on
stdin, each ended by a NUL, in the order `reads` gives them. With `--reads`, this prints that list of calls for the
script. It prints each difference, one sentence to a line, and exits 1 on any, or prints "no drift" and exits 0. It is no
check: `make verify` reads nothing from GitHub. The script runs it from the repo's root, as `python3 -m`.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from tools.rulesets_drift import answer

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = 100
# GitHub's temporary private fork of a security advisory: it comes and goes, and is none of the org's active repos.
ADVISORY = re.compile(r"-ghsa(-[a-z0-9]{4}){3}$")


def reads(held: dict) -> list:
    """The calls to read, in order: the user, the org role and its teams, the team and who is in it, the org's repos,
    the user's membership of each team, then each repo's role and its teams."""
    org, login, team = held["org"], held["login"], held["code_owner_team"]
    role, place = "orgs/%s/organization-roles/%d" % (org, held["org_role"]["id"]), "orgs/%s/teams/%s" % (org, team)
    calls = ["users/%s" % login, role, "%s/teams?per_page=%d" % (role, PAGE), place, "%s/members?per_page=%d" % (place, PAGE),
             "orgs/%s/repos?per_page=%d" % (org, PAGE)]
    calls += ["orgs/%s/teams/%s/memberships/%s" % (org, name, login) for name in held["teams"]]
    for row in held["repos"]:
        calls += ["repos/%s/collaborators/%s/permission" % (row["repo"], login), "repos/%s/teams" % row["repo"]]
    return calls


def _listed(body, read: str, key: str, problems: list) -> list:
    """The rows of a list GitHub answered; a whole page may have more after it, and that is said."""
    rows = [r for r in body if isinstance(r, dict) and isinstance(r.get(key), str)] if isinstance(body, list) else []
    if len(rows) >= PAGE:
        problems.append("%s answered a whole page, so more may follow" % read)
    return rows


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
    name = bodies[1].get("name") if isinstance(bodies[1], dict) else None
    if name != held["org_role"]["name"]:
        problems.append("the org role %d is %s, and config/machine-user.json records %s" % (held["org_role"]["id"], name, held["org_role"]["name"]))
    holders = sorted(row["slug"] for row in _listed(bodies[2], calls[2], "slug", problems))
    if holders != sorted(held["org_role"]["teams"]):
        problems.append("the org role %s is held by %s, and config/machine-user.json records %s"
                        % (held["org_role"]["name"], holders, sorted(held["org_role"]["teams"])))
    grants = bodies[3].get("repos_count") if isinstance(bodies[3], dict) else None
    if grants != held["team_repo_grants"]:
        problems.append("%s has %s grants of its own on repos, and config/machine-user.json records %s"
                        % (team, grants, held["team_repo_grants"]))
    owners = sorted(row["login"] for row in _listed(bodies[4], calls[4], "login", problems))
    if owners != sorted(held["code_owners"]):
        problems.append("%s holds %s, and config/machine-user.json records %s" % (team, owners, sorted(held["code_owners"])))
    active = [row["name"] for row in _listed(bodies[5], calls[5], "name", problems)
              if not row.get("archived") and not ADVISORY.search(row["name"])]
    recorded = {row["repo"].split("/")[-1] for row in held["repos"]}
    if recorded - set(active):
        problems.append("%s are recorded and are not active repos of the org" % sorted(recorded - set(active)))
    left_out = len(set(active) - recorded)     # a count: the names are not for this file, or for what it prints
    if left_out != held["repos_left_out"]:
        problems.append("%d active repos are not recorded, and config/machine-user.json leaves out %d" % (left_out, held["repos_left_out"]))
    for at, name in enumerate(held["teams"]):
        body = bodies[6 + at]
        if not isinstance(body, dict) or body.get("state") != "active" or body.get("role") != "member":
            problems.append("%s is not an active plain member of %s" % (held["login"], name))     # a maintainer sets who is in it
    first = 6 + len(held["teams"])
    for at, row in enumerate(held["repos"]):
        permission, teams = bodies[first + 2 * at], bodies[first + 1 + 2 * at]
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
