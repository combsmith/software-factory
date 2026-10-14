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

from tools.hooks import after_edit, before_stop, identity

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
MADE = []   # the one repo every case copies


def git(where: pathlib.Path, *args: str, **extra: str) -> None:
    subprocess.run(["git"] + list(args), cwd=where, env=environment(programs("git"), **extra), check=True,
                   capture_output=True)


def repo(name: str = WHO["name"], email: str = WHO["email"], remote: str = GOOD_REMOTE,
         helper: str = GH_HELPER, pushurls: tuple = ()) -> pathlib.Path:
    """A clone-like repo holding one commit by the Maintainer, configured as the case says."""
    if not MADE:
        MADE.append(folder() / "repo")
        git(SCRATCH.name, "init", "-q", str(MADE[0]))
        (MADE[0] / ".git" / "config").write_text(CONFIG % (WHO["name"], WHO["email"], GH_HELPER, GOOD_REMOTE))
        git(MADE[0], "commit", "-q", "--allow-empty", "-m", "first")
    where = folder() / "repo"
    shutil.copytree(MADE[0], where)
    config = CONFIG % (name, email, helper, remote) + "".join("\tpushurl = %s\n" % url for url in pushurls)
    (where / ".git" / "config").write_text(config)
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
        theirs, committed = repo(), repo()
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
        pushed = repo()
        git(pushed, "update-ref", "refs/remotes/origin/main", "HEAD")
        path = programs("make", "git")
        self.assertEqual(before_stop.respond(*self.stop(False, path, pushed, FAKE_MAKE_EXIT="2")), (0, "", ""))
        (pushed / "new.py").write_text("")
        self.assertEqual(before_stop.respond(*self.stop(False, path, pushed, FAKE_MAKE_EXIT="2"))[0], 2)
        ahead = repo()
        git(ahead, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(ahead, "commit", "-q", "--allow-empty", "-m", "unpushed")
        self.assertEqual(before_stop.respond(*self.stop(False, path, ahead, FAKE_MAKE_EXIT="2"))[0], 2)


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
                                 "before_stop": ("Stop", None), "identity": ("PreToolUse", "Bash")})
        entries = {p.stem for p in HOOKS.glob("*.py") if "\ndef main(" in p.read_text()}
        self.assertEqual(entries, set(wired))
