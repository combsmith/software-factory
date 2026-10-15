"""The session hooks hold the line whatever the agent was told (§9.12). Each is fed a violation and a clean case.

Each hook is run once from its front door, as `.claude/settings.json` runs it: `python3 -I` on the
script, the event's JSON on stdin. The other cases call the function that front door calls, in this
process, since a Python start for each would make `make fast` slow. Every case has a PATH that holds
only the programs it allows; `make` and `gh` are stand-ins, so no case runs the real checks or reads a
real account.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from tools.hooks import after_edit, before_stop, identity, protected

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOKS = ROOT / "tools" / "hooks"
SCRATCH = tempfile.TemporaryDirectory()     # removed when the run ends
WHO = json.loads((ROOT / "config" / "hooks.json").read_text())["maintainer"]
MACHINE = json.loads((ROOT / "config" / "defaults.json").read_text())["approver"]
HOME = tempfile.mkdtemp(dir=SCRATCH.name)   # no global git configuration
GOOD_REMOTE = "https://github.com/combsmith/software-factory.git"
GH_HELPER = "!gh auth git-credential"
STAND_INS = {
    "gh": 'if [ -n "$FAKE_GH_SLEEP" ]; then exec /bin/sleep "$FAKE_GH_SLEEP"; fi\necho "$FAKE_GH_USER"',
    "make": 'if [ "$1" = "-n" ]; then exit "${FAKE_MAKE_DRY:-0}"; fi\n'
            'echo "make $* in $(pwd -P)"\nexit "${FAKE_MAKE_EXIT:-0}"',
}
PATHS = {}     # made once: a new program's first run is slow on some systems


def folder() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()


def programs(*names: str) -> str:
    """A PATH holding only `names`: git is the real one, make and gh are stand-ins the case steers."""
    if names not in PATHS:
        bin_dir = folder()
        for name in names:
            path = bin_dir / name
            if name == "git":
                path.symlink_to(shutil.which("git"))
                continue
            path.write_text("#!/bin/sh\n%s\n" % STAND_INS[name])
            path.chmod(0o755)
        PATHS[names] = str(bin_dir)
    return PATHS[names]


def environment(path: str, **extra: str) -> dict:
    env = {"PATH": path, "HOME": HOME, "GIT_CONFIG_NOSYSTEM": "1", "FAKE_GH_USER": WHO["login"]}
    env.update(extra)
    return env


def hook(module: str, payload, path: str, **extra: str) -> subprocess.CompletedProcess:
    """Run tools/hooks/<module>.py as the settings run it, from a directory holding a json.py that must not load."""
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    elsewhere = folder()
    (elsewhere / "json.py").write_text("raise SystemExit(7)\n")
    return subprocess.run([sys.executable, "-I", str(HOOKS / (module + ".py"))], cwd=elsewhere, input=stdin,
                          capture_output=True, text=True, env=environment(path, **extra), timeout=60)


CONFIG = """[core]
\trepositoryformatversion = 0
\tbare = false
[user]
\tname = %s
\temail = %s
[credential "https://github.com"]
\thelper = %s
[remote "origin"]
\turl = %s
\tfetch = +refs/heads/*:refs/remotes/origin/*
"""
MADE = []   # the one repo every case clones


def git(where: pathlib.Path, *args: str, **extra: str) -> None:
    subprocess.run(["git"] + list(args), cwd=where, env=environment(programs("git"), **extra), check=True,
                   capture_output=True)


REPOS = {}  # one of each configuration, for the cases that only read it


def repo(name: str = WHO["name"], email: str = WHO["email"], remote: str = GOOD_REMOTE,
         helper: str = GH_HELPER, pushurls: tuple = (), fresh: bool = False) -> pathlib.Path:
    """A clone holding one commit by the Maintainer, configured as the case says. A case that changes it asks for a fresh one."""
    key = (name, email, remote, helper, pushurls)
    if not fresh and key in REPOS:
        return REPOS[key]
    if not MADE:
        MADE.append(folder() / "repo")
        git(SCRATCH.name, "init", "-q", str(MADE[0]))
        (MADE[0] / ".git" / "config").write_text(CONFIG % (WHO["name"], WHO["email"], GH_HELPER, GOOD_REMOTE))
        git(MADE[0], "commit", "-q", "--allow-empty", "-m", "first")
    where = folder() / "repo"
    git(SCRATCH.name, "clone", "-q", str(MADE[0]), str(where))    # its commit is then on a remote already
    config =CONFIG % (name, email, helper, remote) + "".join("\tpushurl = %s\n" % url for url in pushurls)
    (where / ".git" / "config").write_text(config)
    if not fresh:
        REPOS[key] = where
    return where


def bash(command: str, cwd: pathlib.Path) -> dict:
    return {"session_id": "s", "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": command}, "cwd": str(cwd)}


def a_project() -> pathlib.Path:
    """A project directory, with one worktree under .claude/worktrees/."""
    where = folder()
    (where / "kernel").mkdir()
    (where / ".claude" / "worktrees" / "w" / "kernel").mkdir(parents=True)
    return where


class Identity(unittest.TestCase):
    """PreToolUse on Bash. A commit or push as the machine user, or not as the Maintainer, is refused."""

    @classmethod
    def setUpClass(cls):
        cls.here, cls.bad, cls.path = repo(), repo(name="Someone Else", email="someone@example.com"), programs("git", "gh")

    def codes(self, command, cwd=None, path=None, seconds=identity.DEADLINE, **extra) -> str:
        found = identity.check(bash(command, cwd or self.here), environment(path or self.path, **extra), seconds)
        return " ".join("%s: %s." % problem for problem in found)

    def refused(self, command, cwd=None, path=None, **extra) -> str:
        said = self.codes(command, cwd, path, **extra)
        self.assertTrue(said, "%r was let through" % command)
        return said

    def test_from_the_front_door_a_refusal_is_exit_2_and_a_pass_is_silent(self):
        clean = hook("identity", bash("git push", self.here), self.path)
        self.assertEqual((clean.returncode, clean.stdout, clean.stderr), (0, "", ""))
        refused = hook("identity", bash("git push", self.here), self.path, FAKE_GH_USER=MACHINE)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("account_is_machine_user", refused.stderr)
        for unreadable in ("not json", json.dumps({"tool_name": "Bash"})):
            done = hook("identity", unreadable, self.path)
            self.assertEqual(done.returncode, 2, unreadable)
            self.assertIn("hook_failed", done.stderr)

    def test_a_commit_or_a_push_as_the_maintainer_passes(self):
        for command in ('git commit -m "x"', "git push", "git push -u origin HEAD 2>&1 | tail -3",
                        'cd "%s" && git commit -m "$(cat <<\'EOF\'\nit\'s #7, fine\nEOF\n)"' % self.here,
                        "git -C %s commit --amend --no-edit" % self.here, "gh pr create --title x --body y",
                        'git push -u origin "$(git branch --show-current)"', "git push origin $BRANCH",
                        "git push origin +HEAD:refs/heads/x", "git push origin --delete old"):
            self.assertEqual(self.codes(command), "", command)

    def test_a_heredoc_body_is_not_read_as_commands(self):
        for command in ("git commit -F - <<'EOF'\nThen git push later\nEOF",
                        "git commit -F - <<EOF\nIt's done; then git push later\nEOF",
                        "git commit -F - <<-EOF\n\tThen git push later\n\tEOF",
                        "cat > notes.md <<\"EOF\"\nIt's a note: git push later\nEOF\nls",
                        'git commit -m "$(cat <<\'EOF\'\nSay "git push" later\nEOF\n)"'):
            self.assertEqual(self.codes(command, FAKE_GH_USER=MACHINE), "", command)

    def test_a_command_that_commits_and_pushes_nothing_is_not_checked(self):
        for command in ("ls -la", "git status", "git log --oneline -3", "grep -rn 'git push' docs",
                        "gh pr view 7", "git config user.email", "cat <<'EOF'\nDon't\nEOF",
                        "git log --grep 'merge' -3", 'echo "fix the merge later"', "gh api repos/x/y",
                        "gh api -X GET search/issues -f q=x"):
            self.assertEqual(self.codes(command, folder(), programs()), "", command)

    def test_a_commit_identity_that_is_not_the_maintainers_is_refused(self):
        cases = [(self.bad, {}), (repo(email="someone@example.com"), {}), (repo(name="Someone Else"), {}),
                 (self.here, {"GIT_COMMITTER_EMAIL": "someone@example.com"})]
        for where, extra in cases:
            self.assertIn("commit_identity_not_maintainer", self.refused("git commit -m x", where, **extra), extra)
        self.assertIn("committer", self.refused("git commit -m x", GIT_COMMITTER_NAME="Someone Else"))
        said = self.refused("git commit -m x", repo(name=MACHINE, email="1+%s@users.noreply.github.com" % MACHINE))
        self.assertIn("commit_as_machine_user", said)

    def test_every_way_git_makes_a_commit_is_checked(self):
        for verb in ("commit", "commit-tree", "merge", "pull", "rebase", "cherry-pick", "revert", "am"):
            self.assertIn("commit_identity_not_maintainer", self.refused("git %s x" % verb, self.bad), verb)

    def test_an_identity_set_in_the_command_is_refused(self):
        for command in ('git commit --author="Bot <bot@example.com>" -m x', "git -c user.email=b@x commit -m x",
                        "GIT_AUTHOR_EMAIL=b@x git commit -m x", "export GIT_COMMITTER_NAME=Bot; git commit -m x",
                        "env HOME=/tmp git commit -m x", "git config user.email b@x && git commit -m x",
                        "gh auth switch && git push", "GH_TOKEN=abc git push", "git --git-dir=/tmp/x commit -m x",
                        "git -c http.extraHeader=x push", "git -c alias.ci=commit commit -m x",
                        "echo '[user]' >> .git/config && git commit -m x", "tee -a .git/config < x; git commit -m x"):
            self.assertIn("identity_set_in_command", self.refused(command), command)

    def test_what_looks_like_a_commit_or_push_and_was_not_read_as_one_is_refused(self):
        self.assertIn("git_command_unknown", self.refused("git ci -m x"))
        self.assertIn("git_command_unknown", self.refused("xargs -I{} git {} < verbs"))
        self.assertIn("git_option_unknown", self.refused("git --frobnicate commit -m x"))
        for command in ("git submodule foreach git push", "echo 'git push' | sh", "python3 -c 'git push'"):
            self.assertIn("command_unreadable", self.refused(command), command)

    def test_a_push_as_the_machine_user_or_anyone_else_is_refused(self):
        self.assertIn("account_is_machine_user", self.refused("git push", FAKE_GH_USER=MACHINE))
        self.assertIn("account_not_maintainer", self.refused("git push", FAKE_GH_USER="someone-else"))
        self.assertIn("account_is_machine_user", self.refused("gh pr create --fill", FAKE_GH_USER=MACHINE))
        self.assertIn("account_is_machine_user", self.refused("gh -R combsmith/software-factory pr create --fill",
                                                              FAKE_GH_USER=MACHINE))
        url = "https://%s@github.com/combsmith/software-factory.git" % MACHINE
        self.assertIn("account_is_machine_user", self.refused("git push %s HEAD" % url))
        self.assertIn("account_not_maintainer", self.refused("git push https://someone@github.com/x/y.git HEAD"))
        two = repo(pushurls=(GOOD_REMOTE, url))
        for command in ("git push", "git push origin HEAD"):
            self.assertIn("account_is_machine_user", self.refused(command, two), command)

    def test_a_write_to_github_through_gh_is_made_as_the_maintainer(self):
        for command in ("gh pr merge 7 --squash", "gh release create v1", "gh api -X POST repos/x/y/rulesets",
                        "gh api --method=DELETE repos/x/y", "gh api repos/x/y/issues -f title=x",
                        "gh api -XPATCH repos/x/y"):
            self.assertIn("account_is_machine_user", self.refused(command, FAKE_GH_USER=MACHINE), command)
            self.assertEqual(self.codes(command), "", command)

    def test_a_push_whose_account_cannot_be_read_is_refused(self):
        cases = [("git push", None, {"GH_TOKEN": "abc"}), ("git push", None, {"FAKE_GH_USER": ""}),
                 ("git push", repo(remote="git@github.com:combsmith/software-factory.git"), {}),
                 ("git push", repo(helper="osxkeychain"), {}), ("git push nowhere HEAD", None, {})]
        for command, where, extra in cases:
            self.assertIn("account_unreadable", self.refused(command, where, **extra), (command, extra))

    def test_a_credential_is_never_shown(self):
        said = self.refused("git push https://someone:hunter2secret@github.com/x/y.git HEAD")
        self.assertNotIn("hunter2secret", said)
        self.assertNotIn("someone", said)
        said = self.refused("git push", repo(helper="store --file /tmp/hunter2secret"))
        self.assertNotIn("hunter2secret", said)

    def test_a_push_that_carries_another_identity_is_refused(self):
        theirs, committed = repo(fresh=True), repo(fresh=True)
        git(theirs, "commit", "-q", "--allow-empty", "-m", "theirs", "--author", "Someone <s@example.com>")
        git(committed, "commit", "-q", "--allow-empty", "-m", "ours", GIT_COMMITTER_NAME="Someone Else")
        for where in (theirs, committed):
            self.assertIn("push_carries_another_identity", self.refused("git push", where))
        self.assertEqual(self.codes("git commit -m x", theirs), "")

    def test_a_push_names_no_option_to_the_hooks_own_git(self):
        target = folder() / "written-by-the-hook"
        for command in ("git push origin +HEAD '+--format=x' '+--output=%s'" % target,
                        "git push -- origin --output=%s" % target, "git push -- --upload-pack=%s HEAD" % target):
            said = self.refused(command)
            self.assertIn("push_commits_unreadable", said, command)
            self.assertIn("starts with '-'", said, command)
            self.assertFalse(target.exists(), command)
        self.assertIn("push_commits_unreadable", self.refused("git push origin no-such-branch"))

    def test_a_commit_is_checked_where_it_is_made(self):
        bad = self.bad
        for command in ("cd %s && git commit -m x" % bad, "git -C %s commit -m x" % bad,
                        "bash -c 'cd %s && git commit -m x'" % bad, "true; (cd %s; git commit -m x)" % bad,
                        "env A=1 sh -ec 'pushd %s; git commit -m x'" % bad, 'echo "$(cd %s; git commit -m x)"' % bad):
            self.assertIn("commit_identity_not_maintainer", self.refused(command), command)
        self.assertIn("directory_unreadable", self.refused('cd "$SOMEWHERE" && git commit -m x'))

    def test_what_the_hook_cannot_read_is_refused(self):
        self.assertIn("git is not on PATH", self.refused("git commit -m x", path=programs("gh")))
        self.assertIn("gh is not on PATH", self.refused("git push", path=programs("git")))
        self.assertIn("command_unreadable", self.refused('git commit -m "never closed'))

    def test_a_check_that_runs_out_of_time_refuses(self):
        started = time.monotonic()
        said = self.codes("git push", FAKE_GH_SLEEP="5", seconds=0.3)
        self.assertIn("account_unreadable", said)
        self.assertLess(time.monotonic() - started, 3)


class AfterEdit(unittest.TestCase):
    """PostToolUse on an edit. The fast checks run, and a failure is shown to the agent."""

    def edit(self, path, rel="kernel/decide.py", key="file_path", **extra):
        self.project = a_project()
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "cwd": str(self.project),
                   "tool_response": {}, "tool_input": {key: str(self.project / rel)}}
        return payload, environment(path, CLAUDE_PROJECT_DIR=str(self.project), **extra)

    def test_a_failing_fast_check_is_shown_to_the_agent(self):
        payload, env = self.edit(programs("make"))
        done = hook("after_edit", payload, env["PATH"], FAKE_MAKE_EXIT="1", CLAUDE_PROJECT_DIR=str(self.project))
        self.assertEqual(done.returncode, 2)
        self.assertIn("make fast in %s" % self.project, done.stderr)

    def test_passing_fast_checks_say_nothing(self):
        self.assertEqual(after_edit.respond(*self.edit(programs("make"))), (0, "", ""))

    def test_an_edit_in_a_worktree_or_a_notebook_is_checked_there(self):
        code, _, err = after_edit.respond(*self.edit(programs("make"), ".claude/worktrees/w/kernel/x.py",
                                                     FAKE_MAKE_EXIT="1"))
        self.assertEqual(code, 2)
        self.assertIn("make fast in %s" % (self.project / ".claude" / "worktrees" / "w"), err)
        payload, env = self.edit(programs("make"), "kernel/x.ipynb", "notebook_path", FAKE_MAKE_EXIT="1")
        payload["cwd"] = str(folder())      # the notebook, not where the session stands, says where
        code, _, err = after_edit.respond(payload, env)
        self.assertEqual(code, 2)
        self.assertIn("make fast in %s" % self.project, err)

    def test_an_edit_outside_the_project_runs_nothing(self):
        payload, env = self.edit(programs("make"), FAKE_MAKE_EXIT="1")
        payload["tool_input"]["file_path"] = str(folder() / "notes.md")
        self.assertEqual(after_edit.respond(payload, env), (0, "", ""))

    def test_a_branch_with_no_fast_target_tells_the_person_and_does_not_fail(self):
        code, out, err = after_edit.respond(*self.edit(programs("make"), FAKE_MAKE_EXIT="2", FAKE_MAKE_DRY="2"))
        self.assertEqual((code, err), (0, ""))
        self.assertIn("make fast", json.loads(out)["systemMessage"])

    def test_with_no_make_the_agent_is_told_the_checks_did_not_run(self):
        code, _, err = after_edit.respond(*self.edit(programs()))
        self.assertEqual(code, 2)
        self.assertIn("make is not on PATH", err)


class BeforeStop(unittest.TestCase):
    """Stop. A session is sent back once while make verify fails on work it has not pushed."""

    def stop(self, again, path, where=None, **extra):
        self.where = where or a_project()
        payload = {"hook_event_name": "Stop", "stop_hook_active": again, "cwd": str(self.where)}
        return payload, environment(path, CLAUDE_PROJECT_DIR=str(self.where), **extra)

    def test_a_session_does_not_end_while_verify_fails(self):
        payload, env = self.stop(False, programs("make"))
        done = hook("before_stop", payload, env["PATH"], FAKE_MAKE_EXIT="2", CLAUDE_PROJECT_DIR=str(self.where))
        self.assertEqual(done.returncode, 2)
        self.assertIn("make verify in %s" % self.where, done.stderr)
        for coaching in ("say why", "next stop", "ends"):
            self.assertNotIn(coaching, done.stderr)

    def test_a_session_ends_when_verify_passes(self):
        self.assertEqual(before_stop.respond(*self.stop(False, programs("make"))), (0, "", ""))

    def test_a_session_sent_back_once_ends_and_the_person_is_told(self):
        code, out, _ = before_stop.respond(*self.stop(True, programs("make"), FAKE_MAKE_EXIT="2"))
        self.assertEqual(code, 0)
        self.assertIn("make verify in %s" % self.where, json.loads(out)["systemMessage"])

    def test_with_no_make_the_session_is_told_verify_did_not_run(self):
        code, _, err = before_stop.respond(*self.stop(False, programs()))
        self.assertEqual(code, 2)
        self.assertIn("make is not on PATH", err)

    def test_with_nothing_unpushed_verify_is_not_run(self):
        pushed = repo(fresh=True)
        git(pushed, "update-ref", "refs/remotes/origin/main", "HEAD")
        path = programs("make", "git")
        self.assertEqual(before_stop.respond(*self.stop(False, path, pushed, FAKE_MAKE_EXIT="2")), (0, "", ""))
        (pushed / "new.py").write_text("")
        self.assertEqual(before_stop.respond(*self.stop(False, path, pushed, FAKE_MAKE_EXIT="2"))[0], 2)
        ahead = repo(fresh=True)
        git(ahead, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(ahead, "commit", "-q", "--allow-empty", "-m", "unpushed")
        self.assertEqual(before_stop.respond(*self.stop(False, path, ahead, FAKE_MAKE_EXIT="2"))[0], 2)


RULES = json.loads((ROOT / "config" / "hooks.json").read_text())
EDIT_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}


def example(entry: str) -> str:
    """A path the entry protects: a file in it when it is a directory, with * made a name."""
    return entry.replace("*", "x") + ("x.json" if entry.endswith("/") else "")


def a_tree() -> pathlib.Path:
    """A project laid out like this one, a working tree, with one worktree under .claude/worktrees/."""
    where = folder()
    for top in (where, where / ".claude" / "worktrees" / "w"):
        for rel in [example(e["path"]) for e in RULES["protected"]] + ["docs/notes.md", "lifecycle/issue.json"]:
            (top / rel).parent.mkdir(parents=True, exist_ok=True)
            (top / rel).write_text("{}\n")
    (where / ".git").mkdir()
    (where / ".claude" / "worktrees" / "w" / ".git").write_text("gitdir: %s/.git/worktrees/w\n" % where)
    return where


class Asks(unittest.TestCase):
    """What the hook asks the person: the shared helpers."""

    @classmethod
    def setUpClass(cls):
        cls.project = a_tree()
        cls.env = environment(programs(), CLAUDE_PROJECT_DIR=str(cls.project), TMPDIR=str(folder()))

    def edit(self, path, tool="Edit", cwd=None, **check) -> str:
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(cwd or self.project),
                   "tool_input": {EDIT_TOOLS[tool]: str(path), "old_string": "a", "new_string": "b"}}
        return " ".join("%s: %s." % found for found in protected.check(payload, self.env, **check))

    def run_(self, command, cwd=None, **check) -> str:
        return " ".join("%s: %s." % found for found in protected.check(bash(command, cwd or self.project), self.env,
                                                                        **check))

    def asked(self, said, code, case):
        self.assertTrue(said.startswith(code + ":") or (". %s:" % code) in said, "%r was not asked about as %s: %s"
                        % (case, code, said))


class ProtectedPaths(Asks):
    """PreToolUse on an edit or a command. An edit to a protected path makes the hook ask the person."""

    def test_from_the_front_door_an_edit_to_a_protected_path_asks_and_a_clean_one_is_silent(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(self.project),
                   "tool_input": {"file_path": str(self.project / "lifecycle" / "issue.json"), "content": "{}"}}
        done = hook("protected", payload, programs(), CLAUDE_PROJECT_DIR=str(self.project))
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        said = json.loads(done.stdout)["hookSpecificOutput"]
        self.assertEqual((said["hookEventName"], said["permissionDecision"]), ("PreToolUse", "ask"))
        self.assertIn("protected_path: lifecycle/ is the Lifecycle", said["permissionDecisionReason"])
        payload["tool_input"]["file_path"] = str(self.project / "docs" / "notes.md")
        clean = hook("protected", payload, programs(), CLAUDE_PROJECT_DIR=str(self.project))
        self.assertEqual((clean.returncode, clean.stdout, clean.stderr), (0, "", ""))
        for unreadable in ("not json", "[]", json.dumps({"tool_name": "Bash"}),
                           json.dumps({"tool_name": "Edit", "tool_input": "x"})):
            done = hook("protected", unreadable, programs(), CLAUDE_PROJECT_DIR=str(self.project))
            self.assertEqual(done.returncode, 0, unreadable)
            self.assertEqual(json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"], "ask", unreadable)

    def test_every_protected_path_asks_for_every_edit_tool_in_every_tree(self):
        for entry in RULES["protected"]:
            for top in (self.project, self.project / ".claude" / "worktrees" / "w"):
                for tool in EDIT_TOOLS:
                    said = self.edit(top / example(entry["path"]), tool)
                    self.asked(said, "protected_path", (entry["path"], str(top), tool))
                    self.assertIn(entry["is"], said)
        for rel in (".claude/settings.json", ".claude/settings.local.json", "lifecycle/new/deep.json",
                    "tools/hooks/protected.py", "config/rubric-pr-review.json", ".github/workflows/verify.yml"):
            self.asked(self.edit(self.project / rel), "protected_path", rel)

    def test_an_edit_elsewhere_is_not_asked_about(self):
        for rel in ("docs/notes.md", "kernel/AGENTS.md", "kernel/__init__.py", "config/apps.json", "config/AGENTS.md",
                    "schemas/facts.schema.json", "tests/test_decide.py", "tests/test_hooks.py", "tools/check_repo.py",
                    "lifecycle.md", "docs/lifecycle/x.md", "tools/hooks.md", ".githubx/y", "config/rubric.md"):
            self.assertEqual(self.edit(self.project / rel), "", rel)
        self.assertEqual(self.edit(folder() / "notes.md"), "")

    def test_a_path_written_another_way_still_asks(self):
        p = a_tree()        # its own, since it adds links to it
        outside = folder()
        (outside / "rules").symlink_to(p / "lifecycle")
        (p / "docs" / "alias.json").symlink_to(p / "config" / "authority.json")
        os.link(p / "lifecycle" / "issue.json", outside / "hard.json")
        shutil.rmtree(p / "tools" / "hooks")
        (p / "tools" / "hooks").symlink_to(outside)     # a protected directory that leads out of the tree
        for path, cwd in [("%s/./lifecycle/../lifecycle/issue.json" % p, None), ("%s/docs/../lifecycle/x" % p, None),
                          ("%s/LIFECYCLE/ISSUE.JSON" % p, None), ("%s/.GitHub/workflows/ci.yml" % p, None),
                          ("%s/Config/Authority.json" % p, None), ("%s/tools//hooks/x.py" % p, None),
                          ("lifecycle/issue.json", p), ("../lifecycle/issue.json", p / "docs"),
                          ("%s/rules/issue.json" % outside, None), ("%s/docs/alias.json" % p, None),
                          ("%s/.claude/worktrees/w/lifecycle/issue.json" % p, None),
                          ("%s/.claude/worktrees/w/./docs/../.claude/settings.json" % p, None),
                          ("%s/tools/hooks/x.py" % p, None)]:
            self.asked(self.edit(path, cwd=cwd), "protected_path", path)
        self.asked(self.edit(outside / "hard.json"), "path_unreadable", "a hard link")

    def test_a_protected_path_in_any_working_tree_or_in_the_users_settings_asks(self):
        other = folder()
        (other / ".git").mkdir()
        self.asked(self.edit(other / "lifecycle" / "x.json"), "protected_path", "another working tree")
        self.asked(self.edit(pathlib.Path(HOME) / ".claude" / "settings.json"), "protected_path", "the user's settings")
        self.asked(self.edit(self.project / ".claude" / "worktrees" / "new" / "lifecycle" / "x"), "protected_path",
                   "a worktree with no .git yet")

    def test_an_edit_that_names_no_path_asks(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {}}
        self.assertIn("path_unreadable", " ".join(c for c, _ in protected.check(payload, self.env)))
        payload["tool_input"] = {"file_path": "lifecycle/x.json"}      # relative, and no directory to read it from
        self.assertIn("path_unreadable", " ".join(c for c, _ in protected.check(payload, self.env)))

    def test_the_protected_paths_are_data(self):
        data = protected.load()
        data["protected"] = [p for p in data["protected"] if p[0] != "lifecycle/"] + [("docs/", "the documents")]
        self.assertEqual(self.edit(self.project / "lifecycle" / "issue.json", data=data), "")
        self.asked(self.edit(self.project / "docs" / "notes.md", data=data), "protected_path", "docs/ as data")
        self.asked(self.run_("echo x > docs/notes.md", data=data), "protected_path", "docs/ as data")

    def test_a_list_that_cannot_be_read_asks_about_everything(self):
        broken = folder() / "hooks.json"
        for text in ("{", json.dumps({"maintainer": {}}), json.dumps(dict(RULES, protected=[])),
                     json.dumps(dict(RULES, protected=[{"path": "../x", "is": "y"}]))):
            broken.write_text(text)
            self.asked(self.edit(self.project / "docs" / "notes.md", source=broken), "config_unreadable", text)
            self.asked(self.run_("ls", source=broken), "config_unreadable", text)

    def test_a_command_that_writes_a_protected_path_asks(self):
        p, outside = self.project, folder()
        (outside / "rules").symlink_to(p / "lifecycle")
        for command in (
                "echo x > lifecycle/a.json", "echo x >> config/authority.json", "printf x 1> config/rubric-pr-review.json",
                "cat /tmp/x | tee -a kernel/decide.py", "sed -i '' s/a/b/ config/defaults.json",
                "sed -i.bak s/a/b/ sim/world.py", "sed --in-place s/a/b/ tests/test_simulator.py",
                "sed -n 'w lifecycle/x' docs/notes.md", "mv /tmp/x lifecycle/issue.json",
                "mv lifecycle/issue.json /tmp/x", "cp /tmp/ci.yml .github/workflows/", "cp -r /tmp/stage/. config/",
                "cp /tmp/authority.json config", "cp -t config /tmp/authority.json", "install -m 644 /tmp/x tools/hooks/a.py",
                "git checkout -- lifecycle/", "git checkout HEAD~1 -- .", "git restore --source=HEAD~3 config/authority.json",
                "git checkout main -- '*.json'", "git -C .claude/worktrees/w checkout -- lifecycle",
                "git rm -r config", "rm -rf tools/hooks", "rm -rf ..", "cp -r /tmp/stage/. %s" % p.parent, "rm -rf config",
                "chmod +x tools/hooks/x.py", "touch .claude/settings.local.json", "ln -s /tmp/evil lifecycle/x.json",
                "dd if=/tmp/x of=kernel/terms.py", "perl -pi -e s/a/b/ kernel/derive.py",
                "python3 -c \"open('.claude/settings.json', 'w').write('{}')\"",
                "python3 - <<'EOF'\nopen('config/hooks.json', 'w')\nEOF",
                "node -e \"require('fs').writeFileSync('schemas/hooks.schema.json', '')\"",
                "node -e \"require('fs').writeFileSync('tools\\/hooks\\/x.py', '')\"",
                "cd lifecycle && echo x > issue.json", "cd config; tee authority.json < /tmp/x",
                "bash -c 'echo x > lifecycle/a'", "echo x > ./lifecycle/../lifecycle/a", "echo x > LIFECYCLE/A.JSON",
                "echo x > %s/lifecycle/a" % p, "echo x > .claude/worktrees/w/lifecycle/a",
                "echo x > ~/.claude/settings.json", "echo x > $HOME/.claude/settings.json",
                "echo x > %s/rules/a.json" % outside, 'for f in lifecycle/*; do sed -i s/a/b/ "$f"; done',
                "find . -name '*.json' -delete", "find config -exec sed -i s/a/b/ {} +", "git ls-files | xargs sed -i s/a/b/",
                "awk '{print > FILENAME}' config/authority.json", "echo x > {lifecycle,docs}/a",
                "cp /tmp/x lifecycle/{a,b}.json", "echo x > lifec?cle/a", "echo x > l[i]fecycle/a",
                "git apply /tmp/x.patch", "git stash pop", "tar -xf /tmp/x.tar", "unzip /tmp/x.zip",
                "python3 /tmp/x.py lifecycle/issue.json", 'cp "$X" config/', "git diff --output=lifecycle/x",
                "git log --output lifecycle/x", "perl -e 'open(F, \">lifecycle\\/x\")'",
                "cd config && python3 -c \"open('authority.json', 'w')\"", "echo x > {life,x}cycle/a",
                "cp -r /tmp/stage/ config/", "git -C config checkout -- authority.json",
                "gh api -X PUT repos/o/r/contents/.github/workflows/x.yml -f content=x"):
            self.asked(self.run_(command), "protected_path", command)

    def test_a_write_the_hook_cannot_read_asks(self):
        for command, code in (('cd "$SOMEWHERE" && rm -rf x', "path_unreadable"),
                              ('echo x > "$OUT"', "path_unreadable"), ("rm -rf $(git rev-parse --show-toplevel)/x",
                                                                        "path_unreadable"),
                              ('echo "never closed', "command_unreadable"), ("echo x > >(tee y)", "command_unreadable"),
                              ("ls | xargs -n1 rm", "protected_path"), ("cd - && touch x", "path_unreadable"),
                              ("git checkout stash@{0} -- :/", "path_unreadable"),
                              ("git --work-tree=/x checkout -- .", "path_unreadable")):
            self.asked(self.run_(command), code, command)

    def test_a_command_that_reads_a_protected_path_or_writes_elsewhere_is_not_asked_about(self):
        for command in (
                "cat lifecycle/issue.json", "grep -rn x lifecycle config .github", "sed -n 1,5p config/authority.json",
                "jq . config/hooks.json", "git diff lifecycle/", "git log -- .github", "git add .",
                "git add -A && git commit -m 'Touch lifecycle/ and gh pr merge'", "ls -la .github tools/hooks",
                "cp lifecycle/issue.json /tmp/x", "cp -r .github /tmp/gh", "cp docs/notes.md config/",
                "echo x > docs/notes.md", "echo x > docs/new.md 2>&1", "echo x 2>/dev/null >&2", "make verify",
                "SIM_SEEDS=40 make verify", "python3 -m unittest tests.test_hooks", "git checkout -b x origin/main",
                "git switch main", "git pull --ff-only", "git reset --hard origin/main", "git clean -fd",
                "gh pr create --title x --body 'edits .github/ and lifecycle/'", "find . -name '*.json'",
                "find lifecycle -exec grep -l x {} +", "diff <(cat lifecycle/issue.json) docs/notes.md",
                'D=$(mktemp -d) && git archive -o "$D/x.tar" HEAD && tar -xf "$D/x.tar" -C "$D"',
                'D="$(mktemp -d -t x)"; rm -rf "$D"',
                "cat > /tmp/notes.md <<'EOF'\nlifecycle/ and gh pr merge\nEOF", "mkdir -p /tmp/x && cp docs/notes.md /tmp/x/",
                "rm -rf /tmp/scratch", "python3 tools/check_context.py", "echo $HOME", "export PATH=$PATH:/x",
                'echo "$x" > /tmp/y', "git commit -F - <<'EOF'\nChange lifecycle/issue.json\nEOF",
                'for f in docs/*.md; do wc -l "$f"; done', "tar -czf /tmp/x.tgz docs", "cd docs && echo x > notes.md",
                "cat lifecycle/issue.json | python3 -c 'import json, sys; json.load(sys.stdin)'",
                "ls | xargs -n1 wc -l", 'cd "$TMPDIR" && echo x > y', "git push -u origin HEAD",
                "ls | xargs -n 1 wc -l", "python3 tools/hooks/protected.py < /tmp/payload.json",
                "bash -c 'cat lifecycle/issue.json'",
                "python3 -I tests/test_simulator.py", "git merge origin/main -m 'Merge lifecycle/ and config/defaults.json'",
                "git worktree add .claude/worktrees/x -b y origin/main", 'cp "$X" %s/' % folder(),
                "git diff --output=/tmp/x.diff"):
            self.assertEqual(self.run_(command), "", command)


class MergesAndSettings(Asks):
    """PreToolUse on Bash. A merge, or a write to a ruleset or the repo's settings, makes the hook ask the person."""

    def test_from_the_front_door_a_merge_asks(self):
        done = hook("protected", bash("gh pr merge 5 --squash", self.project), programs(),
                    CLAUDE_PROJECT_DIR=str(self.project))
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        said = json.loads(done.stdout)["hookSpecificOutput"]
        self.assertEqual(said["permissionDecision"], "ask")
        self.assertIn("merge: gh pr merge merges a pull request", said["permissionDecisionReason"])
        clean = hook("protected", bash("gh pr view 5", self.project), programs(), CLAUDE_PROJECT_DIR=str(self.project))
        self.assertEqual((clean.returncode, clean.stdout, clean.stderr), (0, "", ""))

    def test_merging_or_adding_to_the_queue_asks(self):
        query = "gh api graphql -f query='mutation%s { %s(input: {pullRequestId: %s}) { clientMutationId } }'"
        for command in (
                "gh pr merge 5 --squash", "gh pr merge --auto 5", "gh -R combsmith/software-factory pr merge 5",
                "gh pr merge -R o/r 5", query % ("", "enqueuePullRequest", '"x"'),
                query % ("($id: ID!)", "mergePullRequest", "$id") + " -f id=x",
                query % ("", "enablePullRequestAutoMerge", '"x"'), "gh api -X PUT repos/combsmith/software-factory/pulls/5/merge",
                "gh api --method=put /repos/o/r/pulls/5/merge", "gh api -X POST repos/o/r/merges -f base=main -f head=x",
                "bash -c 'gh pr merge 5'", 'echo "$(gh pr merge 5)"', "env GH_PAGER= gh pr merge 5",
                "true && gh pr merge 5", "git push origin HEAD:main", "git push origin main",
                "git push origin +x:refs/heads/main", "git push --mirror", "git push origin --delete main"):
            self.asked(self.run_(command), "merge", command)
        for command in ("gh api graphql -F query=@merge.graphql", "gh api graphql --input q.json",
                        "python3 -c \"import subprocess; subprocess.run(['gh', 'pr', 'merge', '5'])\"",
                        "curl -X PUT https://api.github.com/repos/o/r/pulls/5/merge", "gh alias set m 'pr merge'",
                        "gh m 5", "python3 - <<'EOF'\nimport subprocess\nsubprocess.run('gh pr merge 5', shell=True)\nEOF",
                        "gh api graphql -f query=\"$Q\""):
            self.asked(self.run_(command), "command_unreadable", command)

    def test_what_does_not_merge_is_not_asked_about(self):
        for command in ("gh pr view 5", "gh pr create --fill", "gh pr checks 5", "gh pr view 5 --json mergeable",
                        "gh api graphql -f query='query { viewer { login } }'", "gh api repos/o/r/pulls/5/merge",
                        "git push -u origin HEAD", "git push origin feature-main", "git merge origin/main",
                        "git commit -m 'gh pr merge later'", "echo gh pr merge 5", "grep -rn 'pr merge' tools",
                        "gh pr list --search is:merged", "gh --version"):
            self.assertEqual(self.run_(command), "", command)

    def test_a_write_to_a_ruleset_or_the_repos_settings_asks(self):
        mutation = "gh api graphql -f query='mutation { %s(input: {}) { clientMutationId } }'"
        for command in (
                "gh api -X PATCH repos/o/r -f allow_auto_merge=true", "gh api -X DELETE repos/o/r",
                "gh api -X POST repos/{owner}/{repo}/rulesets --input r.json",
                "gh api -X PUT repos/o/r/branches/main/protection --input p.json", "gh api --method DELETE repos/o/r/hooks/1",
                "gh api repos/o/r/environments/prod -X PUT", "gh api -X PUT repos/o/r/actions/permissions -F enabled=true",
                "gh api repos/o/r/rulesets -f name=x", "gh api -XPATCH /repos/o/r/", "gh api -X PATCH https://api.github.com/repos/o/r",
                "gh api -X PUT repos/o/r/./rulesets/../rulesets/1", "gh api -X PATCH REPOS/O/R",
                "gh api -X PUT repos/o/r/%72ulesets/1", "gh api -X PATCH 'repos/o/r?x=1'", "gh api -X PATCH orgs/combsmith -f x=y",
                "gh repo edit --enable-auto-merge", "gh repo edit combsmith/software-factory --default-branch x",
                "gh ruleset list", "gh secret set X", "gh variable delete X", "gh workflow disable verify",
                mutation % "updateRepository", mutation % "createRepositoryRuleset", mutation % "updateBranchProtectionRule"):
            self.asked(self.run_(command), "repo_settings", command)
        self.asked(self.run_('gh api -X POST "repos/o/$R/rulesets"'), "command_unreadable", "an endpoint in a variable")

    def test_what_does_not_write_the_repos_settings_is_not_asked_about(self):
        for command in ("gh api repos/o/r", "gh api repos/o/r/rulesets", "gh api -X GET repos/o/r/rulesets -f x=1",
                        "gh repo view", "gh api -X POST repos/o/r/issues/5/comments -f body='rulesets and settings'",
                        "gh api repos/o/r/branches/main/protection", "gh issue create --title 'edit the ruleset'",
                        "gh api -X POST repos/o/r/issues -f title=x"):
            self.assertEqual(self.run_(command), "", command)

    def test_the_question_shows_no_credential_and_no_command(self):
        for payload in (bash("gh api -X PATCH 'https://someone:hunter2secret@api.github.com/repos/o/r?t=hunter2secret'",
                             self.project),
                        bash("echo hunter2secret > lifecycle/hunter2secret", self.project),
                        bash("curl -u someone:hunter2secret -X PUT https://api.github.com/repos/o/r/pulls/5/merge",
                             self.project),
                        bash("hunter2secret 'never closed", self.project),
                        {"tool_name": "Edit", "tool_input": {"file_path": 7}, "cwd": "hunter2secret"}):
            said = protected.respond(payload, self.env)
            self.assertIn('"ask"', said)
            self.assertNotIn("hunter2secret", said)
            self.assertNotIn("someone", said)


class Settings(unittest.TestCase):
    def test_every_hook_is_wired_to_its_event(self):
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
        wired = {}
        for event, groups in settings["hooks"].items():
            for group in groups:
                for handler in group["hooks"]:
                    found = re.match(r'^python3 -I "\$CLAUDE_PROJECT_DIR/tools/hooks/(\w+)\.py"( \|\| exit 2)?$',
                                     handler["command"])
                    self.assertTrue(found, handler["command"])
                    wired[found.group(1)] = (event, group.get("matcher"))
                    # A hook that cannot start is shown to the agent, never let through. Not on Stop, which would loop.
                    self.assertEqual(bool(found.group(2)), event != "Stop", handler["command"])
        self.assertEqual(wired, {"after_edit": ("PostToolUse", "Edit|Write|MultiEdit|NotebookEdit"),
                                 "before_stop": ("Stop", None), "identity": ("PreToolUse", "Bash"),
                                 "protected": ("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit|Bash")})
        entries = {p.stem for p in HOOKS.glob("*.py") if "\ndef main(" in p.read_text()}
        self.assertEqual(entries, set(wired))
