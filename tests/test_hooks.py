"""The session hooks hold the line whatever the agent was told (§9.12). Each is fed a violation and a clean case.

Each hook is run once from its front door, as `.claude/settings.json` runs it: the event's JSON on
stdin, from the repo root. The other cases call the function that front door calls, in this process,
since a Python start for each would make `make fast` slow. Every case has a PATH that holds only the
programs it allows; `make` and `gh` are stand-ins, so no case runs the real checks or reads a real account.
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
import unittest

from tools.hooks import after_edit, before_stop, identity

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRATCH = tempfile.TemporaryDirectory()     # removed when the run ends
WHO = json.loads((ROOT / "config" / "hooks.json").read_text())["maintainer"]
MACHINE = json.loads((ROOT / "config" / "defaults.json").read_text())["approver"]
HOME = tempfile.mkdtemp(dir=SCRATCH.name)   # no global git configuration
GOOD_REMOTE = "https://github.com/combsmith/software-factory.git"
GH_HELPER = "!gh auth git-credential"
STAND_INS = {"gh": 'echo "$FAKE_GH_USER"', "make": 'echo "make $* in $(pwd -P)"\nexit "${FAKE_MAKE_EXIT:-0}"'}


def folder() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp(dir=SCRATCH.name)).resolve()


PATHS = {}     # made once: a new program's first run is slow on some systems


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
    """Run tools/hooks/<module>.py as the settings run it, with `payload` on stdin."""
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, "-m", "tools.hooks." + module], cwd=ROOT, input=stdin,
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


def repo(name: str = WHO["name"], email: str = WHO["email"], remote: str = GOOD_REMOTE,
         helper: str = GH_HELPER) -> pathlib.Path:
    """A clone-like repo holding one commit by the Maintainer, configured as the case says."""
    if not MADE:
        MADE.append(folder() / "repo")
        env = environment(programs("git"))
        subprocess.run(["git", "init", "-q", str(MADE[0])], env=env, check=True)
        (MADE[0] / ".git" / "config").write_text(CONFIG % (WHO["name"], WHO["email"], GH_HELPER, GOOD_REMOTE))
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "first"], cwd=MADE[0], env=env, check=True)
    where = folder() / "repo"
    shutil.copytree(MADE[0], where)
    (where / ".git" / "config").write_text(CONFIG % (name, email, helper, remote))
    return where


def bash(command: str, cwd: pathlib.Path) -> dict:
    return {"session_id": "s", "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": command}, "cwd": str(cwd)}


def a_tree() -> pathlib.Path:
    """A copy of the repo, as far as finding where to run make goes."""
    where = folder()
    (where / "tools").mkdir()
    (where / "tools" / "verify.py").write_text("")
    return where


class Identity(unittest.TestCase):
    """PreToolUse on Bash. A commit or push as the machine user, or not as the Maintainer, is refused.

    The cases call `check()` in this process, which is what the front door runs; one case goes
    through the front door to hold the exit codes. A Python start for each case would make
    `make fast` slow.
    """

    @classmethod
    def setUpClass(cls):
        cls.here, cls.path = repo(), programs("git", "gh")

    def codes(self, command, cwd=None, path=None, **extra) -> str:
        found = identity.check(bash(command, cwd or self.here), environment(path or self.path, **extra))
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
        self.assertIn("push_as_machine_user", refused.stderr)
        for unreadable in ("not json", json.dumps({"tool_name": "Bash"})):
            done = hook("identity", unreadable, self.path)
            self.assertEqual(done.returncode, 2, unreadable)
            self.assertIn("hook_failed", done.stderr)

    def test_a_commit_or_a_push_as_the_maintainer_passes(self):
        for command in ('git commit -m "x"', "git push", "git push -u origin HEAD 2>&1 | tail -3",
                        'cd "%s" && git commit -m "$(cat <<\'EOF\'\nit\'s #7, fine\nEOF\n)"' % self.here,
                        "git -C %s commit --amend --no-edit" % self.here, "gh pr create --title x --body y"):
            self.assertEqual(self.codes(command), "", command)

    def test_a_command_that_commits_and_pushes_nothing_is_not_checked(self):
        for command in ("ls -la", "git status", "git log --oneline -3", "grep -rn 'git push' docs",
                        "gh pr view 7", "git config user.email", "cat <<'EOF'\nDon't\nEOF"):
            self.assertEqual(self.codes(command, folder(), programs()), "", command)

    def test_a_commit_identity_that_is_not_the_maintainers_is_refused(self):
        said = self.refused("git commit -m x", repo(name="Someone Else", email="someone@example.com"))
        self.assertIn("commit_identity_not_maintainer", said)
        said = self.refused("git commit -m x", repo(name=MACHINE, email="1+%s@users.noreply.github.com" % MACHINE))
        self.assertIn("commit_as_machine_user", said)

    def test_an_identity_set_in_the_command_is_refused(self):
        for command in ('git commit --author="Bot <bot@example.com>" -m x', "git -c user.email=b@x commit -m x",
                        "GIT_AUTHOR_EMAIL=b@x git commit -m x", "export GIT_COMMITTER_NAME=Bot; git commit -m x",
                        "env HOME=/tmp git commit -m x", "git config user.email b@x && git commit -m x",
                        "gh auth switch && git push", "GH_TOKEN=abc git push", "git --git-dir=/tmp/x commit -m x"):
            self.assertIn("identity_set_in_command", self.refused(command), command)

    def test_a_push_as_the_machine_user_or_anyone_else_is_refused(self):
        self.assertIn("push_as_machine_user", self.refused("git push", FAKE_GH_USER=MACHINE))
        self.assertIn("push_account_not_maintainer", self.refused("git push", FAKE_GH_USER="someone-else"))
        self.assertIn("push_as_machine_user", self.refused("gh pr create --fill", FAKE_GH_USER=MACHINE))
        self.assertIn("push_as_machine_user", self.refused("gh -R combsmith/software-factory pr create --fill",
                                                           FAKE_GH_USER=MACHINE))
        url = "https://%s@github.com/combsmith/software-factory.git" % MACHINE
        self.assertIn("push_as_machine_user", self.refused("git push %s HEAD" % url))

    def test_a_push_whose_account_cannot_be_read_is_refused(self):
        cases = [("git push", None, {"GH_TOKEN": "abc"}), ("git push", None, {"FAKE_GH_USER": ""}),
                 ("git push", repo(remote="git@github.com:combsmith/software-factory.git"), {}),
                 ("git push", repo(helper="osxkeychain"), {}), ("git push nowhere HEAD", None, {}),
                 ("git push -- origin --output=written-by-the-hook", None, {})]
        for command, where, extra in cases:
            self.assertIn("push_account_unreadable", self.refused(command, where, **extra), (command, extra))

    def test_a_push_that_carries_another_authors_commit_is_refused(self):
        here = repo()
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "theirs", "--author", "Someone <s@example.com>"],
                       cwd=here, env=environment(programs("git")), check=True)
        self.assertIn("push_carries_another_identity", self.refused("git push", here))
        self.assertEqual(self.codes("git commit -m x", here), "")

    def test_a_commit_is_checked_where_it_is_made(self):
        bad = repo(name="Someone Else", email="someone@example.com")
        for command in ("cd %s && git commit -m x" % bad, "git -C %s commit -m x" % bad,
                        "bash -c 'cd %s && git commit -m x'" % bad, "true; (cd %s; git commit -m x)" % bad,
                        "env A=1 sh -ec 'pushd %s; git commit -m x'" % bad, "eval cd %s \\; git commit -m x" % bad):
            self.assertIn("commit_identity_not_maintainer", self.refused(command), command)
        self.assertIn("directory_unreadable", self.refused('cd "$SOMEWHERE" && git commit -m x'))

    def test_what_the_hook_cannot_read_is_refused(self):
        self.assertIn("git is not on PATH", self.refused("git commit -m x", path=programs("gh")))
        self.assertIn("gh is not on PATH", self.refused("git push", path=programs("git")))
        self.assertIn("command_unreadable", self.refused('git commit -m "never closed'))


class AfterEdit(unittest.TestCase):
    """PostToolUse on an edit. The fast checks run, and a failure is shown to the agent."""

    def edit(self, path, **extra):
        self.where = a_tree()
        return {"hook_event_name": "PostToolUse", "tool_name": "Edit", "cwd": str(ROOT), "tool_response": {},
                "tool_input": {"file_path": str(self.where / "kernel" / "decide.py")}}, environment(path, **extra)

    def test_a_failing_fast_check_is_shown_to_the_agent(self):
        payload, env = self.edit(programs("make"))
        done = hook("after_edit", payload, env["PATH"], FAKE_MAKE_EXIT="1")
        self.assertEqual(done.returncode, 2)
        self.assertIn("make fast in %s" % self.where, done.stderr)

    def test_passing_fast_checks_say_nothing(self):
        self.assertEqual(after_edit.respond(*self.edit(programs("make"))), (0, "", ""))

    def test_with_no_make_the_agent_is_told_the_checks_did_not_run(self):
        code, _, err = after_edit.respond(*self.edit(programs()))
        self.assertEqual(code, 2)
        self.assertIn("make is not on PATH", err)


class BeforeStop(unittest.TestCase):
    """Stop. A session does not end while make verify fails, and is sent back once, not for ever."""

    def stop(self, again, path, **extra):
        self.where = a_tree()
        payload = {"hook_event_name": "Stop", "stop_hook_active": again, "cwd": str(self.where)}
        return payload, environment(path, **extra)

    def test_a_session_does_not_end_while_verify_fails(self):
        payload, env = self.stop(False, programs("make"))
        done = hook("before_stop", payload, env["PATH"], FAKE_MAKE_EXIT="2")
        self.assertEqual(done.returncode, 2)
        self.assertIn("make verify in %s" % self.where, done.stderr)

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


class Settings(unittest.TestCase):
    def test_every_hook_is_wired_to_its_event(self):
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
        wired = {}
        for event, groups in settings["hooks"].items():
            for group in groups:
                for handler in group["hooks"]:
                    command = handler["command"]
                    self.assertTrue(command.startswith('cd "$CLAUDE_PROJECT_DIR" && python3 -m tools.hooks.'), command)
                    wired[re.search(r"-m tools\.hooks\.(\w+)", command).group(1)] = (event, group.get("matcher"))
                    if event != "Stop":     # a hook that cannot start is shown to the agent, never let through
                        self.assertTrue(command.endswith(" || exit 2"), command)
        self.assertEqual(wired, {"after_edit": ("PostToolUse", "Edit|Write|MultiEdit|NotebookEdit"),
                                 "before_stop": ("Stop", None), "identity": ("PreToolUse", "Bash")})
        entries = {p.stem for p in (ROOT / "tools" / "hooks").glob("*.py") if "\ndef main(" in p.read_text()}
        self.assertEqual(entries, set(wired))
