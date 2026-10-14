"""PreToolUse on Bash: a commit or a push here is made as the Maintainer, or it is refused.

Three identities must be the Maintainer's (§9.12): the commit's author and committer, which come
from git's configuration in each clone, and the account that pushes or opens a pull request, which
comes from gh. The Maintainer is in `config/hooks.json`; the machine user is the approver in
`config/defaults.json`, which approves and does nothing else (decision 0005). The hook reads what is
configured, so an identity set inside the command is refused, and what it cannot read it refuses.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

from tools.hooks import shell

ROOT = pathlib.Path(__file__).resolve().parents[2]
WRITES = {"am", "cherry-pick", "commit", "commit-tree", "merge", "pull", "push", "rebase", "revert"}
# What the text of a command that could not be split into words is searched for.
WRITE_TEXT = re.compile(r"\bgit\b[\s\S]*\b(%s)\b|\bgh\b[\s\S]*\bpr\b[\s\S]*\bcreate\b" % "|".join(sorted(WRITES)))
# Set in the command, each of these changes who git or gh says you are.
ENVIRONMENT = re.compile(r"^(GIT_AUTHOR_\w*|GIT_COMMITTER_\w*|GIT_CONFIG\w*|GIT_DIR|GIT_WORK_TREE|GIT_ASKPASS|"
                         r"GIT_SSH\w*|GH_\w+|GITHUB_\w*TOKEN|EMAIL|HOME|XDG_CONFIG_HOME)=")
KEYS = re.compile(r"^(user|author|committer|credential|url|remote|include|includeif|core\.sshcommand)\b", re.I)
TOKENS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
GIT_VALUED = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
GH_VALUED = {"-R", "--repo", "--hostname"}
PUSH_VALUED = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}
IDENT = re.compile(r"^(.*) <(.*)> \d+ [+-]\d{4}$")
GITHUB = re.compile(r"^https://(?:([^@/]+)@)?github\.com/")
HELPER = "gh auth git-credential"
SHOWN = 3   # commits of another identity named in a refusal


class Unreadable(Exception):
    """Something the decision rests on could not be read."""


def _run(program: str, args: list, where, env: dict) -> str:
    exe = shutil.which(program, path=env.get("PATH", os.defpath))
    if exe is None:
        raise Unreadable("%s is not on PATH, so who would commit or push cannot be read" % program)
    done = subprocess.run([exe] + args, cwd=str(where), env=env, capture_output=True, text=True, timeout=20)
    if done.returncode != 0:
        first = (done.stderr.strip().splitlines() or ["exit %d" % done.returncode])[0]
        raise Unreadable("`%s %s` failed in %s: %s" % (program, " ".join(args), where, first))
    return done.stdout


def _join(here, path: str):
    """Where `cd path` or `git -C path` leads from `here`; None when it cannot be told from the words."""
    if here is None or "$" in path or "`" in path or (path.startswith("~") and not re.match(r"~(/|$)", path)):
        return None
    return here / os.path.expanduser(path)


def _calls(commands: list, cwd) -> tuple:
    """(calls, problems): each git or gh call as (tool, directory, words after the tool's own options)."""
    here = pathlib.Path(cwd) if cwd else None
    calls, problems = [], []
    for words in commands:
        problems += [("identity_set_in_command", "%s is set in the command; the hook reads only what is configured"
                      % w.split("=")[0]) for w in words if ENVIRONMENT.match(w)]
        if words[0] in ("cd", "pushd"):
            here = _join(here, words[1]) if len(words) > 1 and words[1] != "-" else None
            continue
        at = next((i for i, w in enumerate(words) if os.path.basename(w) in ("git", "gh")), None)
        if at is None:
            continue
        tool, rest = os.path.basename(words[at]), words[at + 1:]
        where, i = here, 0
        while i < len(rest) and rest[i].startswith("-"):
            option, given, value = rest[i].partition("=")
            if option in (GIT_VALUED if tool == "git" else GH_VALUED) and not given:
                i += 1
                value = rest[i] if i < len(rest) else ""
            i += 1
            if tool != "git":
                continue
            if option == "-C":
                where = _join(where, value)
            elif option in ("-c", "--config-env") and KEYS.match(value):
                problems.append(("identity_set_in_command", "git %s %s sets an identity in the command" % (option, value)))
            elif option in ("--git-dir", "--work-tree"):
                problems.append(("identity_set_in_command", "%s points git at a repo the hook does not read" % option))
        calls.append((tool, where, rest[i:]))
    return calls, problems


def _writes(call) -> bool:
    tool, _, words = call
    return words[:1] and words[0] in WRITES if tool == "git" else words[:2] == ["pr", "create"]


def _people() -> tuple:
    who = json.loads((ROOT / "config" / "hooks.json").read_text())["maintainer"]
    machine = json.loads((ROOT / "config" / "defaults.json").read_text())["approver"]
    return who, machine


def _committer(where, env: dict, who: dict, machine: str) -> list:
    problems = []
    for kind in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        found = IDENT.match(_run("git", ["var", kind], where, env).strip())
        name, email = found.groups() if found else ("?", "?")
        if (name, email) != (who["name"], who["email"]):
            code = "commit_as_machine_user" if machine.lower() in (name + email).lower() else "commit_identity_not_maintainer"
            problems.append((code, "in %s git would record the %s as %s <%s>, and a commit here is the Maintainer's, "
                                   "%s <%s>. Set user.name and user.email in this clone's git config, in a command of "
                                   "its own" % (where, kind[4:-6].lower(), name, email, who["name"], who["email"])))
    return problems


def _account(env: dict, who: dict, machine: str) -> list:
    """The account that pushes: gh's, for github.com, and no token in the environment in its place."""
    for name in TOKENS:
        if env.get(name):
            return [("push_account_unreadable", "%s is set, so git and gh act as whoever owns that token, which the "
                                                "hook cannot read; unset it" % name)]
    login = _run("gh", ["config", "get", "user", "-h", "github.com"], ROOT, env).strip()
    if not login:
        return [("push_account_unreadable", "gh names no active account for github.com")]
    if login.lower() == machine.lower():
        return [("push_as_machine_user", "gh's active account is %s, the machine user, which never pushes or opens a "
                                         "pull request here. Run gh auth switch --user %s, in a command of its own"
                 % (login, who["login"]))]
    if login.lower() != who["login"].lower():
        return [("push_account_not_maintainer", "gh's active account is %s, and a push here is the Maintainer's, %s"
                 % (login, who["login"]))]
    return []


def _targets(args: list) -> tuple:
    """(positional words, deleting) of a push: the remote first, then refspecs."""
    out, repo, i = [], [], 0
    while i < len(args):
        option, given, value = args[i].partition("=")
        if args[i] == "--":
            out += args[i + 1:]
            break
        if option in PUSH_VALUED:
            if not given:
                i += 1
                value = args[i] if i < len(args) else ""
            repo += [value] if option == "--repo" else []
        elif not args[i].startswith("-"):
            out.append(args[i])
        i += 1
    return repo + out, "--delete" in args or "-d" in args


def _push(where, args: list, env: dict, who: dict, machine: str) -> list:
    """Where the push goes, through gh's account, carrying only the Maintainer's commits."""
    problems = []
    helper = _run("git", ["config", "--get-urlmatch", "credential.helper", "https://github.com"], where, env).strip()
    if not helper.endswith(HELPER):
        problems.append(("push_account_unreadable", "git in %s does not push to github.com through gh's account (its "
                                                    "credential helper is %s); run gh auth setup-git" % (where, helper)))
    targets, deleting = _targets(args)
    if any(t.startswith("-") for t in targets):    # never hand the hook's own git an option from the command
        raise Unreadable("the push names a remote or refspec that starts with '-'")
    if targets and re.search(r"://|^[^/]+@[^/]+:", targets[0]):
        urls = [targets[0]]
    elif targets:
        urls = [_run("git", ["remote", "get-url", "--push", targets[0]], where, env).strip()]
    else:
        urls = [_run("git", ["remote", "get-url", "--push", r], where, env).strip()
                for r in _run("git", ["remote"], where, env).split()]
    for url in urls:
        found = GITHUB.match(url)
        user = (found.group(1) or "").split(":")[0] if found else ""
        if not found:
            problems.append(("push_account_unreadable", "%s is not GitHub over HTTPS, so the account that would push "
                                                        "cannot be read" % url))
        elif user and user.lower() == machine.lower():
            problems.append(("push_as_machine_user", "%s pushes as %s, the machine user" % (url, user)))
        elif user and user.lower() != who["login"].lower():
            problems.append(("push_account_not_maintainer", "%s pushes as %s, not as %s" % (url, user, who["login"])))
    if deleting:
        return problems
    revs = ["--branches"] if {"--all", "--mirror", "--branches"} & set(args) else []
    revs += ["--tags"] if "--tags" in args else []
    revs += [spec.lstrip("+").split(":")[0] for spec in targets[1:] if spec.lstrip("+").split(":")[0]]
    log = _run("git", ["log", "--format=%an%x00%ae%x00%cn%x00%ce"] + (revs or ["HEAD"]) + ["--not", "--remotes"],
               where, env)
    others = sorted({line for line in log.splitlines()
                     if line.split("\0") != [who["name"], who["email"], who["name"], who["email"]]})
    for line in others[:SHOWN]:
        an, ae, cn, ce = (line.split("\0") + ["?"] * 4)[:4]
        problems.append(("push_carries_another_identity", "the push from %s carries a commit by %s <%s>, committed by "
                                                          "%s <%s>; a commit here is the Maintainer's" % (where, an, ae, cn, ce)))
    return problems


def check(payload: dict, env: dict) -> list:
    """The reasons to refuse this command, as (code, sentence); none when it may run."""
    if payload.get("tool_name") != "Bash":
        return []
    command = payload["tool_input"]["command"]
    try:
        commands = shell.simple_commands(command)
    except ValueError as err:
        if WRITE_TEXT.search(command):
            return [("command_unreadable", "the command cannot be split into words (%s), so who would commit or push "
                                           "cannot be read. Write the message to a file and use git commit -F" % err)]
        return []
    calls, problems = _calls(commands, payload.get("cwd"))
    writes = [c for c in calls if _writes(c)]
    if not writes:
        return []
    for tool, _, words in calls:
        if (tool, words[:1]) in (("git", ["config"]), ("gh", ["auth"])):
            problems.append(("identity_set_in_command", "%s %s changes configuration in the command that commits or "
                                                        "pushes; change it in a command of its own" % (tool, words[0])))
    for tool, _, words in writes:
        if tool == "git" and any(w == "--author" or w.startswith("--author=") for w in words):
            problems.append(("identity_set_in_command", "--author names someone other than the configured identity"))
    who, machine = _people()
    pushes = [c for c in writes if c[0] == "gh" or c[2][0] == "push"]
    try:
        problems += _account(env, who, machine) if pushes else []
    except Unreadable as err:
        problems.append(("push_account_unreadable", str(err)))
    for tool, where, words in writes:
        if where is None or not where.is_dir():
            problems.append(("directory_unreadable", "the command commits or pushes in a directory the hook cannot "
                                                     "tell from its words (%s); give it as a plain path" % (where or "?")))
            continue
        try:
            problems += _committer(where, env, who, machine)
        except Unreadable as err:
            problems.append(("identity_unreadable", str(err)))
        if (tool, where, words) not in pushes:
            continue
        try:
            problems += _push(where, words[1:] if tool == "git" else [], env, who, machine)
        except Unreadable as err:
            problems.append(("push_account_unreadable", str(err)))
    return list(dict.fromkeys(problems))


def main() -> int:
    try:
        problems = check(json.loads(sys.stdin.read()), dict(os.environ))
    except Exception as err:    # what the hook cannot read, it refuses
        problems = [("hook_failed", "the identity hook could not finish (%s: %s), so it refuses"
                     % (type(err).__name__, err))]
    if not problems:
        return 0
    print("Refused by tools/hooks/identity.py. A commit or a push in this repo is the Maintainer's, who is named "
          "in config/hooks.json:", file=sys.stderr)
    for code, sentence in problems:
        print("- %s: %s." % (code, sentence), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
