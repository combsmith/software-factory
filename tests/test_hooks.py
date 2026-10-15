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

from tools.hooks import after_edit, before_stop, identity, protected, rules_changed

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

    def test_a_known_command_that_is_not_a_commit_or_a_push_passes_whatever_its_name_or_its_words_say(self):
        named = {"merge-base", "merge-tree", "rev-parse", "rev-list", "ls-tree", "ls-files", "cat-file", "show", "log",
                 "diff", "for-each-ref", "name-rev", "describe", "archive", "fetch", "commit-graph"}
        self.assertLessEqual(named, identity.READS)
        self.assertFalse(identity.READS & (identity.WRITES | identity.RUNNERS))
        for sub in sorted(identity.READS):
            self.assertEqual(self.codes("git %s HEAD" % sub, folder(), programs()), "", sub)
        for command in ("git merge-tree --write-tree --name-only A B", "git merge-tree A B", "git merge-base A B",
                        "git -C . merge-base --is-ancestor HEAD origin/main", "git rev-parse --verify HEAD",
                        "git rev-list --count A..B", "git ls-tree -r HEAD", "git ls-files -z", "git cat-file -p HEAD",
                        "git show --stat HEAD", "git log --oneline -3", "git diff A B", "git name-rev HEAD",
                        "git for-each-ref --format='%(refname)' refs/heads", "git describe --tags", "git fetch origin",
                        "git archive --format=tar HEAD", "git commit-graph verify",
                        "git commit-graph write --reachable"):
            self.assertEqual(self.codes(command, folder(), programs()), "", command)
        for command in ("git log --grep=commit", "git log --grep commit --grep push -3", "git rev-list --grep=merge A",
                        "git show :/rebase", "git diff commit push", "git ls-files push.py cherry-pick.md",
                        "git for-each-ref refs/heads/rebase", "git log --author=revert"):
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
        for command in ("git ci -m x", "git mt --write-tree A B", "git merge-trees A B", "git commit-graphs write"):
            self.assertIn("git_command_unknown", self.refused(command), command)
        self.assertIn("git_command_unknown", self.refused("xargs -I{} git {} < verbs"))
        self.assertIn("git_option_unknown", self.refused("git --frobnicate commit -m x"))
        for command in ("git submodule foreach git push", "echo 'git push' | sh", "python3 -c 'git push'",
                        "git -c merge.x.driver='git push origin HEAD' merge-tree --write-tree A B",
                        "git -c core.pager='git push origin HEAD:main' log"):
            self.assertIn("command_unreadable", self.refused(command), command)

    def test_a_program_set_in_the_command_for_git_to_run_is_refused(self):
        for command in ("git -c merge.evil.driver=./driver merge-tree --write-tree a b",
                        "GIT_X='git push' git --config-env=pager.log=GIT_X log",
                        "git --config-env=core.pager=GIT_X log", "git --config-env core.pager=GIT_X log",
                        "git -c merge.x.driver='cat %A' merge-tree A B",
                        "git -c core.pager='less -R' log", "git -c core.pager=/bin/cat log", "git -c pager.log=./p log",
                        "git -c core.hooksPath=/tmp/h status", "git -c core.fsmonitor=./m status",
                        "git -c diff.x.textconv=./t log -p", "git -c filter.lfs.smudge=./s status",
                        "git -c gpg.program=./g log --show-signature", "git -c difftool.x.path=./d diff",
                        "git -c protocol.ext.allow=always fetch origin", "git -c core.editor=./e status"):
            self.assertIn("command_unreadable", self.refused(command), command)

    def test_a_configuration_set_in_the_command_that_runs_no_program_passes(self):
        for command in ("git -c core.pager=cat log", "git -c core.pager=less log", "git -c pager.log=false log",
                        "git -c pager.log log", "git -c core.fsmonitor=off status", "git -c color.ui=always log",
                        "git -c pretty.foo='format:git commit %H' log --pretty=foo -1"):
            self.assertEqual(self.codes(command, folder(), programs()), "", command)

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


def a_tree(branch: str = "feature") -> pathlib.Path:
    """A project laid out like this one, a working tree on `branch`, with one worktree under .claude/worktrees/."""
    where = folder()
    git(where, "init", "-q", "-b", branch)       # a real repository: the hook asks git where it stands
    git(where, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "first")
    git(where, "worktree", "add", "-q", "-b", "w", str(where / ".claude" / "worktrees" / "w"))
    for top in (where, where / ".claude" / "worktrees" / "w"):
        for rel in [example(e["path"]) for e in RULES["protected"] if not e["path"].startswith(".git/")] + [
                "docs/notes.md", "lifecycle/issue.json", "kernel/decide.py", "tests/test_hooks.py"]:
            (top / rel).parent.mkdir(parents=True, exist_ok=True)
            (top / rel).write_text("{}\n")
    return where


class Asks(unittest.TestCase):
    """What the hook asks the person: the shared helpers."""

    @classmethod
    def setUpClass(cls):
        cls.project = a_tree()
        cls.env = environment(programs("git"), CLAUDE_PROJECT_DIR=str(cls.project), TMPDIR=str(folder()))

    def env_for(self, project):
        return self.env if project is None else dict(self.env, CLAUDE_PROJECT_DIR=str(project))

    def edit(self, path, tool="Edit", cwd=None, project=None, **check) -> str:
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(cwd or project or self.project),
                   "tool_input": {EDIT_TOOLS[tool]: str(path), "old_string": "a", "new_string": "b"}}
        return " ".join("%s: %s." % found for found in protected.check(payload, self.env_for(project), **check))

    def run_(self, command, cwd=None, project=None, **check) -> str:
        payload = bash(command, cwd or project or self.project)
        return " ".join("%s: %s." % found for found in protected.check(payload, self.env_for(project), **check))

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
        for rel in ("docs/notes.md", "kernel/AGENTS.md", "kernel/__init__.py", "kernel/decide.py", "kernel/derive.py",
                    "kernel/terms.py", "config/apps.json", "config/AGENTS.md",
                    "schemas/facts.schema.json", "tests/test_decide.py", "tests/test_hooks.py", "tools/check_repo.py",
                    "lifecycle.md", "docs/lifecycle/x.md", "tools/hooks.md", ".githubx/y", "config/rubric.md"):
            self.assertEqual(self.edit(self.project / rel), "", rel)
        self.assertEqual(self.edit(folder() / "notes.md"), "")

    def test_a_path_written_another_way_still_asks(self):
        p = a_tree()        # its own, since it adds links to it
        outside = folder()
        (outside / "rules").symlink_to(p / "lifecycle")
        (p / "docs" / "alias.json").symlink_to(p / "config" / "authority.json")
        os.link(p / "lifecycle" / "issue.json", p / "docs" / "hard.json")
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
            self.asked(self.edit(path, cwd=cwd, project=p), "protected_path", path)
        self.asked(self.edit(p / "docs" / "hard.json", project=p), "path_unreadable", "a hard link")

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
                "cat /tmp/x | tee -a config/rubric-pr-review.json", "sed -i '' s/a/b/ config/defaults.json",
                "sed -i.bak s/a/b/ sim/world.py", "sed --in-place s/a/b/ tests/test_simulator.py",
                "sed -n 'w lifecycle/x' docs/notes.md", "mv /tmp/x lifecycle/issue.json",
                "mv lifecycle/issue.json /tmp/x", "cp /tmp/ci.yml .github/workflows/", "cp -r /tmp/stage/. config/",
                "cp /tmp/authority.json config", "cp -t config /tmp/authority.json", "install -m 644 /tmp/x tools/hooks/a.py",
                "git checkout -- lifecycle/", "git checkout HEAD~1 -- .", "git restore --source=HEAD~3 config/authority.json",
                "git checkout main -- '*.json'", "git -C .claude/worktrees/w checkout -- lifecycle",
                "git rm -r config", "rm -rf tools/hooks", "rm -rf ..", "cp -r /tmp/stage/. %s" % p.parent, "rm -rf config",
                "chmod +x tools/hooks/x.py", "touch .claude/settings.local.json", "ln -s /tmp/evil lifecycle/x.json",
                "dd if=/tmp/x of=sim/world.py", "perl -pi -e s/a/b/ tests/test_simulator.py",
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
                "echo x > lifec?cle/a", "echo x > l[i]fecycle/a",
                "git apply /tmp/x.patch", "git stash pop", "tar -xf /tmp/x.tar", "unzip /tmp/x.zip",
                "python3 /tmp/x.py lifecycle/issue.json", 'cp "$X" config/', "git diff --output=lifecycle/x",
                "git log --output lifecycle/x", "perl -e 'open(F, \">lifecycle\\/x\")'",
                "cd config && python3 -c \"open('authority.json', 'w')\"",
                "python3 -c \"open('LIFECYCLE/X.JSON', 'w')\"", "sort -o config/defaults.json /tmp/x",
                "curl -olifecycle/issue.json https://example.com/x", "wget -Olifecycle/x https://example.com/x",
                "gh repo clone combsmith/.github", "cd docs && gh repo clone o/r ../.github/new",
                "python3 -m json.tool /tmp/x config/authority.json", "pytest --junitxml=lifecycle/x tests/",
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
                              ("git --work-tree=/x checkout -- .", "path_unreadable"),
                              ("echo x > {life,x}cycle/a", "path_unreadable"),
                              ("touch {a,b}{c,d}", "path_unreadable"),
                              ("cp /tmp/x lifecycle/{a,b}.json", "path_unreadable")):
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
                "git diff --output=/tmp/x.diff", "pytest tests/", "pytest -q tests/test_simulator.py",
                "python3 -m pytest tests/", "python3 -m unittest discover tests", "sort config/defaults.json",
                "python3 -m json.tool config/authority.json", "cp kernel/decide.py /tmp/x",
                "echo x > kernel/decide.py", "sed -i s/a/b/ kernel/derive.py", "touch docs/{a,b}.md",
                "echo x > docs/{a,b}.md"):
            self.assertEqual(self.run_(command), "", command)

    def test_the_brace_bomb_is_answered_ask_within_the_deadline(self):
        bomb = "echo x > lifecycle/a.json; : '%s'" % ("{a,b}" * 25)
        started = time.monotonic()
        done = hook("protected", bash(bomb, self.project), programs(), CLAUDE_PROJECT_DIR=str(self.project))
        self.assertLess(time.monotonic() - started, protected.DEADLINE)
        self.assertEqual(json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")
        self.asked(self.run_("touch %s" % ("{a,b}" * 25)), "path_unreadable", "a bomb with no redirection")

    def test_a_brace_left_open_is_read_within_the_budget(self):
        started = time.monotonic()
        self.asked(self.run_("rm {" + "a," * 100000), "path_unreadable", "a brace left open, 200 KB long")
        self.assertLess(time.monotonic() - started, protected.DEADLINE)
        started = time.monotonic()
        self.assertEqual(protected._starred("{" + "a," * 100000, lambda: None), "{" + "a," * 100000)
        self.assertLess(time.monotonic() - started, 1)
        for word, starred in (("x{a,b}y{1..9}", "x*y*"), ("{}", "{}"), ("stash@{0}", "stash@{0}"),
                              ("{a,{b,c}}", "*"), ("{a,b", "{a,b"), ("a}b{c,d}", "a}b*")):
            self.assertEqual(protected._starred(word, lambda: None), starred, word)

    def test_a_wildcard_that_would_backtrack_is_read_within_the_budget(self):
        p = a_tree()
        (p / "lifecycle" / ("a" * 250)).write_text("")
        (p / "docs" / "l").symlink_to(p / "lifecycle")     # a way into a protected path that names none
        started = time.monotonic()
        self.asked(self.run_("rm docs/l/*a*a*a*a*c", p, project=p), "protected_path", "a wildcard over a long name")
        self.assertLess(time.monotonic() - started, protected.DEADLINE)
        for pattern, name, matches in (("*a*a*c", "a" * 250, False), ("*a*a*a", "a" * 250, True),
                                       ("*.json", "x.json", True), ("*.json", "x.jsonx", False),
                                       ("[!x]?", "ab", True), ("[!x]?", "xb", False), ("[a-c]x", "Bx", True),
                                       ("?", "", False), ("*", "", True), ("a[", "a[", True)):
            self.assertEqual(protected._glob_match(pattern, name), matches, (pattern, name))

    def test_a_path_with_a_newline_is_still_protected(self):
        for rel in ("lifecycle/x\ny.json", ".github/a\nb.yml"):
            self.asked(self.edit(self.project / rel), "protected_path", rel)
            self.asked(self.run_('touch "%s"' % rel), "protected_path", rel)

    def test_a_parse_over_its_budget_asks(self):
        self.asked(self.run_("ls", seconds=0), "budget_spent", "no time")
        self.asked(self.run_("echo %s" % ("x" * protected.LONGEST)), "budget_spent", "too long")
        self.asked(self.edit("/" + "x" * 5000), "budget_spent", "a path too long")


class MergesAndSettings(Asks):
    """PreToolUse on Bash. A merge, or a write to a ruleset or the repo's settings, makes the hook ask the person."""

    def test_from_the_front_door_a_merge_asks(self):
        done = hook("protected", bash("gh pr merge 5 --admin --squash", self.project), programs(),
                    CLAUDE_PROJECT_DIR=str(self.project))
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        said = json.loads(done.stdout)["hookSpecificOutput"]
        self.assertEqual(said["permissionDecision"], "ask")
        self.assertIn("merge: gh pr merge --admin merges", said["permissionDecisionReason"])
        clean = hook("protected", bash("gh pr view 5", self.project), programs(), CLAUDE_PROJECT_DIR=str(self.project))
        self.assertEqual((clean.returncode, clean.stdout, clean.stderr), (0, "", ""))

    def test_merging_or_adding_to_the_queue_asks(self):
        query = "gh api graphql -f query='mutation%s { %s(input: {pullRequestId: %s}) { clientMutationId } }'"
        for command in (
                "gh pr merge 5 --admin", "gh pr merge --admin --squash 5",
                "gh -R combsmith/software-factory pr merge --admin 5", "gh pr merge -R o/r 5 --admin",
                query % ("($id: ID!)", "mergePullRequest", "$id") + " -f id=x",
                "gh api -X PUT repos/combsmith/software-factory/pulls/5/merge",
                "gh api --method=put /repos/o/r/pulls/5/merge", "gh api -X POST repos/o/r/merges -f base=main -f head=x",
                "bash -c 'gh pr merge --admin 5'", 'echo "$(gh pr merge --admin 5)"',
                "env GH_PAGER= gh pr merge --admin 5", "true && gh pr merge --admin 5",
                "gh api -X POST repos/o/r/git/refs -f ref=refs/heads/x -f sha=y",
                "gh api -X PATCH repos/o/r/git/refs/heads/main -f sha=y", "git push origin HEAD:main", "git push origin main",
                "git push origin +x:refs/heads/main", "git push --mirror", "git push origin --delete main",
                # A repository named in place overrides --repo, as git reads it: these push main.
                "git push --repo=origin origin main", "git push --repo origin origin HEAD:main"):
            self.asked(self.run_(command), "merge", command)
        on_main = a_tree("main")        # with HEAD, a push goes to the branch it is on
        for command in ("git push -u origin HEAD", "git push origin @",
                        'git push origin "$(git branch --show-current)"', "cd docs && git push origin HEAD"):
            self.asked(self.run_(command, on_main), "merge", command)
        self.asked(self.run_("git push origin HEAD", folder()), "merge", "a push from a directory with no branch")
        mutation = "gh api graphql -f query='mutation { %s(input: {}) { clientMutationId } }'"
        contents = "gh api -X %s repos/o/r/contents/docs/x.md -f message=m -f content=x"
        for command in (mutation % "updateRefs", mutation % "updateRef", mutation % "createCommitOnBranch",
                        contents % "PUT", contents % "PUT" + " -f branch=main", contents % "PUT" + " -f branch=refs/heads/main",
                        contents % "DELETE" + " -f sha=s", contents % "PUT" + ' -f branch="$B"',
                        "gh api -X PUT repos/o/r/contents/docs/x.md --input body.json"):
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
                        "gh pr list --search is:merged", "gh --version", "gh pr merge 5 --squash",
                        "gh pr merge --auto 5", "gh -R o/r pr merge 5",
                        "gh api graphql -f query='mutation { enqueuePullRequest(input: {pullRequestId: \"x\"}) { clientMutationId } }'",
                        "gh api graphql -f query='mutation { enablePullRequestAutoMerge(input: {}) { clientMutationId } }'",
                        "gh api graphql -f query='mutation { enqueuePullRequest(input: {pullRequestId: \"x\", jump: true}) { clientMutationId } }'", "git push -u origin HEAD",
                        "gh api -X PUT repos/o/r/contents/docs/x.md -f message=m -f content=x -f branch=feature"):
            self.assertEqual(self.run_(command), "", command)

    def test_github_s_api_is_read_by_its_host(self):
        for command in ("curl -X PUT https://api.github.com/repos/o/r/pulls/5/merge",
                        "curl -X PUT HTTPS://API.GITHUB.COM/repos/o/r/rulesets/1", "curl https://uploads.api.github.com/x",
                        "python3 -c \"requests.put('api.github.com/repos/o/r')\"",
                        "wget --method=PUT https://user@api.github.com:443/repos/o/r"):
            self.asked(self.run_(command), "command_unreadable", command)
        for command in ("curl -X PUT https://api.github.com.evil.example/x", "curl https://notapi.github.com/x",
                        "curl https://example.com/api.github.com.html"):
            self.assertEqual(self.run_(command), "", command)

    def test_a_gitdir_that_is_not_a_git_directory_leaves_the_branch_unreadable(self):
        unread = "the branch a push goes to cannot be read"
        for name in ("main", "feature"):
            where, elsewhere = folder(), folder()
            (elsewhere / "HEAD").write_text("ref: refs/heads/%s\n" % name)
            (where / ".git").write_text("gitdir: %s\n" % elsewhere)
            self.assertIn(unread, self.run_("git push origin HEAD", where), name)
        for gitdir in ("real.git", "repo/.git/worktrees/w"):      # git directories git itself made
            where = folder()
            if gitdir == "real.git":
                git(where, "init", "-q", "--bare", "-b", "feature", gitdir)
            else:
                git(where, "init", "-q", "-b", "main", "repo")
                git(where / "repo", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                    "-m", "first")
                git(where / "repo", "worktree", "add", "-q", "-b", "feature", str(where / "elsewhere"))
                gitdir = os.path.relpath(where / "repo" / ".git" / "worktrees" / "elsewhere", where / "tree")
            (where / "tree").mkdir()
            (where / "tree" / ".git").write_text("gitdir: %s\n" % (gitdir if "/" in gitdir else "../" + gitdir))
            self.assertEqual(self.run_("git push origin HEAD", where / "tree", project=where), "", gitdir)
        self.assertEqual(self.run_("git push origin HEAD", self.project / ".claude" / "worktrees" / "w"), "")

    def test_git_state_is_read_only_inside_the_project(self):
        outside = repo(fresh=True)
        git(outside, "checkout", "-q", "-b", "feature")
        self.assertEqual(self.run_("git push origin HEAD", outside, project=outside), "")
        for command in ("git push origin HEAD", "git push", "git push origin"):
            self.asked(self.run_(command, outside), "merge", command)       # its project is another
        self.asked(self.run_("git push origin HEAD", "/tmp"), "merge", "a push from /tmp")
        root = os.path.realpath(str(self.project))
        self.assertEqual(protected._branch(str(self.project), root), "feature")
        self.assertEqual(protected._branch(str(self.project / "docs"), root), "feature")
        self.assertEqual(protected._branch(str(self.project / ".claude" / "worktrees" / "w"), root), "w")
        self.assertIsNone(protected._branch(str(outside), root))
        self.assertIsNone(protected._branch("/tmp", root))
        self.assertIsNone(protected._git_dir(str(outside / ".git"), root))
        self.assertEqual(protected._git_dir(str(self.project / ".git"), root), os.path.join(root, ".git"))

    def test_git_says_which_branch_a_tree_is_on(self):
        where = repo(fresh=True)
        root = os.path.realpath(str(where))
        git(where, "checkout", "-q", "--detach")
        self.assertEqual(protected._branch(str(where), root), "")       # a detached HEAD is on no branch
        self.assertEqual(self.run_("git push origin HEAD", where, project=where), "")    # git refuses it: no branch
        git(where, "worktree", "add", "-q", "-b", "wt", str(where / ".claude" / "worktrees" / "wt"))
        self.assertEqual(protected._branch(str(where / ".claude" / "worktrees" / "wt"), root), "wt")
        self.assertEqual(self.run_("git push origin HEAD", where / ".claude" / "worktrees" / "wt", project=where), "")
        (where / "fake").mkdir()
        (where / "fake" / "HEAD").write_text("ref: refs/heads/feature\n")
        (where / "sub").mkdir()
        (where / "sub" / ".git").write_text("gitdir: ../fake\n")
        self.assertIsNone(protected._branch(str(where / "sub"), root))
        self.assertIsNone(protected._git_dir(str(where / "sub"), root))
        elsewhere = repo(fresh=True)        # a real git directory, outside the project
        (where / "linked").mkdir()
        (where / "linked" / ".git").write_text("gitdir: %s\n" % (elsewhere / ".git"))
        self.assertIsNone(protected._git_dir(str(where / "linked"), root))
        self.assertIsNone(protected._branch(str(where / "linked"), root))
        self.assertIn("the branch a push goes to cannot be read", self.run_("git push origin HEAD", where / "linked",
                                                                            project=where))
        self.assertIn("the branch a push goes to cannot be read", self.run_("git push origin HEAD", where / "sub",
                                                                            project=where))
        self.assertIsNone(protected._branch("/tmp", root))
        self.assertIn("the branch a push goes to cannot be read", self.run_("git push origin HEAD", "/tmp",
                                                                            project=where))

    def test_nothing_outside_the_project_is_read(self):
        outside = repo(fresh=True)
        git(outside, "checkout", "-q", "-b", "feature")
        # Where a push naming no branch goes is git's configuration's to say, and git is not run outside the project.
        self.assertIn("git's configuration says, which the hook cannot read", self.run_("git push", outside))
        elsewhere = folder()
        (elsewhere / "lifecycle").mkdir()
        os.link(self.project / "docs" / "notes.md", elsewhere / "hard.md")
        for command in ("cp -r .github %s" % elsewhere, "rm -rf %s/*" % elsewhere, "echo x > %s/hard.md" % elsewhere):
            self.assertEqual(self.run_(command), "", command)      # a directory there is not read, nor listed
        p = a_tree()
        (p / "docs" / "fake").mkdir()
        (p / "docs" / "fake" / "HEAD").write_text("ref: refs/heads/feature\n")
        (p / "sub").mkdir()
        (p / "sub" / ".git").write_text("gitdir: ../docs/fake\n")
        self.assertIn("the branch a push goes to cannot be read", self.run_("git push origin HEAD", p / "sub", project=p))

    def test_an_edit_outside_the_project_is_read_by_its_words(self):
        other = folder()
        (other / ".git").mkdir()
        for path in (other / "notes.md", other / "config" / "x.json", pathlib.Path("/tmp/x.txt")):
            self.assertEqual(self.edit(path), "", path)
        for path in (other / "lifecycle" / "x.json", other / "deep" / "tools" / "hooks" / "x.py"):
            self.asked(self.edit(path), "protected_path", path)

    def test_a_temporary_directory_is_known_without_tmpdir(self):
        env = environment(programs("git"), CLAUDE_PROJECT_DIR=str(self.project))
        self.assertNotIn("TMPDIR", env)
        found = protected.check(bash('D=$(mktemp -d) && rm -rf "$D/x"', self.project), env)
        self.assertEqual(found, [])

    def test_a_push_naming_no_branch_asks_unless_where_it_goes_is_read_exactly(self):
        feature, on_main, upstream, refspec, mirror = (repo(fresh=True) for _ in range(5))
        for where in (feature, upstream, refspec):
            git(where, "checkout", "-q", "-b", "feature")
        git(on_main, "checkout", "-q", "-B", "main")
        git(upstream, "config", "push.default", "upstream")
        git(refspec, "config", "remote.origin.push", "HEAD:refs/heads/main")
        git(mirror, "checkout", "-q", "-b", "feature")
        git(mirror, "config", "remote.origin.mirror", "yes")
        for command in ("git push", "git push origin", "git push -u origin HEAD", "git config --get push.default",
                        "git config --list", "git config core.editor vim", "git config push.default",
                        "git config --get-all remote.origin.push main", "git config --get push.default simple",
                        "git branch -a", "git branch --show-current"):
            self.assertEqual(self.run_(command, feature, project=feature), "", command)
        for where in (on_main, upstream, refspec, mirror):
            for command in ("git push", "git push origin", "git push --force-with-lease"):
                self.asked(self.run_(command, where, project=where), "merge", (command, where))
        payload, no_git = bash("git push", feature), environment(programs(), CLAUDE_PROJECT_DIR=str(self.project))
        self.assertIn("merge", " ".join(c for c, _ in protected.check(payload, no_git)))
        for command in ("git -c push.default=upstream push", "git -c push.default=upstream push origin feature",
                        "git branch -u origin/main", "git branch --set-upstream-to=origin/main",
                        "git branch --set-upstream-to origin/main feature", "git config push.default upstream",
                        "git config --global push.default upstream", "git config set push.default upstream",
                        "git config remote.origin.push HEAD:refs/heads/main",
                        "git config --add remote.origin.push HEAD:refs/heads/main",
                        "git config branch.feature.merge refs/heads/main", "git config branch.feature.remote origin",
                        "git config --unset-all remote.origin.push"):
            self.asked(self.run_(command, feature, project=feature), "merge", command)
        self.asked(self.run_("echo '[push] default = upstream' >> .git/config", feature, project=feature), "protected_path",
                   "a write to git's configuration")

    def test_a_write_to_the_base_the_stop_compares_with_asks(self):
        for command in ("git update-ref refs/remotes/origin/main HEAD", "git update-ref --stdin < /tmp/x",
                        "git fetch . +HEAD:refs/remotes/origin/main", "git fetch . HEAD:refs/remotes/origin/main",
                        "git fetch ../other main:refs/remotes/origin/main", "git push . HEAD:refs/remotes/origin/main",
                        "git tag origin/main", "git branch origin/main", "git branch -f origin/main HEAD",
                        "git tag -f refs/remotes/origin/main", "git symbolic-ref refs/remotes/origin/main refs/heads/x"):
            self.asked(self.run_(command), "remote_ref", command)
        for command in ("echo x > .git/refs/remotes/origin/main", "printf x >> .git/packed-refs"):
            self.asked(self.run_(command), "protected_path", command)
        for command in ("git fetch origin", "git fetch origin main", "git fetch origin main:refs/remotes/origin/main",
                        "git tag v1", "git tag -l", "git branch feature-x", "git branch --list 'origin/*'",
                        "git branch -r", "git symbolic-ref HEAD", "git symbolic-ref --short HEAD"):
            self.assertEqual(self.run_(command), "", command)

    def test_the_review_s_plain_spellings_ask(self):
        mutation = "gh api graphql -f query='mutation { %s(input: {}) { clientMutationId } }'"
        for command, code in (
                ("git -c alias.land='push origin HEAD:main' land", "command_unreadable"),
                ("git land", "command_unreadable"), ("git -c alias.st=\'push origin HEAD:main\' status", "command_unreadable"),
                ("gh repo sync combsmith/software-factory --branch main --force", "merge"),
                ("git push origin 'refs/heads/*:refs/heads/*'", "merge"), ("git push origin '+refs/heads/*'", "merge"),
                ("git push origin :", "merge"), (mutation % "deleteRepository", "repo_settings"),
                (mutation % "transferRepository", "repo_settings"), (mutation % "deleteRef", "merge"),
                ("cat <(gh api -X DELETE repos/o/r)", "repo_settings"), ("diff <(git push origin HEAD:main) x", "merge"),
                ("cat <(echo x > lifecycle/a.json)", "protected_path"),
                ("git --git-dir=/x/.git push origin HEAD", "merge"), ("GIT_DIR=/x/.git git push origin HEAD", "merge"),
                ("git remote set-url --push origin https://github.com/x/y.git", "merge"),
                ("git remote add other https://github.com/x/y.git", "merge"), ("git remote rename origin old", "merge"),
                ("curl -X DELETE https://api.github.com./repos/o/r", "command_unreadable"),
                ("git fetch origin +refs/pull/1/head:refs/remotes/origin/main", "remote_ref"),
                ("git fetch origin feature:refs/remotes/origin/main", "remote_ref")):
            self.asked(self.run_(command), code, command)
        for command in ("gh repo deploy-key list", "gh repo autolink list", "gh repo autolink view 1", "git remote -v",
                        "git remote get-url origin", "git remote show origin", "git fetch origin main:refs/remotes/origin/main",
                        "git fetch origin refs/heads/main:refs/remotes/origin/main", "diff <(cat lifecycle/issue.json) docs/notes.md",
                        "git push origin feature:feature", "gh repo clone o/r /tmp/x", "echo '<(not a substitution)'"):
            self.assertEqual(self.run_(command), "", command)

    def test_deleting_a_remote_branch_of_origin_asks(self):
        # It takes away refs/remotes/origin/*, the base a stop compares the branch with.
        for command in ("git branch -r -d origin/main", "git branch -r -D origin/main", "git branch -rd origin/main",
                        "git branch -dr origin/feature", "git branch -Dr origin/main", "git branch --remotes --delete origin/x",
                        "git branch --rem --del origin/main", "git branch -d -r ORIGIN/main",
                        "git -C . branch -r -d origin/main", "setsid git branch -r -D origin/main"):
            self.asked(self.run_(command), "remote_ref", command)
        for command in ("git branch -d feature", "git branch -D origin/main", "git branch -r", "git branch -rv",
                        "git branch -r -d upstream/main", "git branch -r --list 'origin/*'", "git branch --delete x"):
            self.assertEqual(self.run_(command), "", command)

    def test_a_wrapper_that_runs_its_words_is_read_as_one(self):
        for wrapper in ("setsid", "setsid --wait", "setsid -w", "setsid -f -c", "setsid --fork --ctty --wait", "doas",
                        "nice -n 5", "ionice -c3", "chrt -r 1", "taskset 1", "numactl -N 0", "flock /tmp/lock",
                        "gtimeout 5", "unbuffer", "chronic", "script -q /dev/null", "arch -arm64", "xcrun",
                        "sandbox-exec -n no-network", "fakeroot", "unshare -r", "systemd-run --user"):
            for command, code in (("%s git push origin HEAD:main", "merge"), ("%s gh pr merge --admin 5", "merge"),
                                  ("%s git branch -r -d origin/main", "remote_ref")):
                self.asked(self.run_(command % wrapper), code, command % wrapper)
            self.assertEqual(self.run_("%s git push origin feature" % wrapper), "", wrapper)
        self.assertTrue({"setsid", "nice", "timeout", "env", "sudo"} <= protected.WRAPPERS)    # data, not code

    def test_git_given_a_helper_in_the_command_asks(self):
        # A read-only git command runs the program it is given: a pager, an external diff, a monitor.
        for command in ("git -c diff.external=./x.sh diff", "git -c core.pager='sh -c \"echo > lifecycle/a.json\"' log",
                        "git -c core.PAGER=./p log", "git -c pager.log=./p log", "git -c core.fsmonitor=./m status",
                        "git -c core.sshCommand='ssh -o ProxyCommand=x' fetch", "git -c diff.x.textconv=./t log -p",
                        "git -c filter.x.smudge=./s status", "git -c include.path=/tmp/c log",
                        "git -c merge.default=x -c merge.x.driver=./d log", "git -c core.attributesFile=/tmp/a log",
                        "git -c core.hooksPath=/tmp/h status", "git --config-env=core.pager=P log",
                        "git -c protocol.ext.allow=always ls-remote x", "git diff --ext-diff", "git log -p --ext-diff",
                        "git show --ext-diff HEAD", "GIT_EXTERNAL_DIFF=./x git diff", "GIT_PAGER=./p git log",
                        "env PAGER=./p git log", "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.pager GIT_CONFIG_VALUE_0=./p git log",
                        "GIT_CONFIG_PARAMETERS=\"'core.pager'='./p'\" git log", "git grep -O./p x", "git grep -O x",
                        "git grep --open-files-in-pager=./p x", "git fetch --upload-pack=./u .", "git ls-remote -u ./u .",
                        "git ls-remote --upload-pack ./u .", "git push --receive-pack ./r . HEAD:feature",
                        "git difftool -x ./d", "setsid --wait git -c core.pager=./p log", "nice git diff --ext-diff"):
            self.asked(self.run_(command), "command_unreadable", command)
        for command in ("git -c core.pager=cat log", "git -c core.pager='less -R' log", "git -c core.pager= log",
                        "GIT_PAGER=cat git log", "PAGER= git log", "env GIT_PAGER=cat git log", "git --no-pager log",
                        "git diff --no-ext-diff", "git -c color.ui=always log", "git log -- --ext-diff",
                        "git -c core.editor=true status", "git -c diff.external=cat diff", "git grep -n x",
                        "git ls-remote origin", "git fetch origin"):
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
                "gh ruleset create", "gh secret set X", "gh variable delete X", "gh workflow disable verify",
                mutation % "updateRepository", mutation % "createRepositoryRuleset", mutation % "updateBranchProtectionRule"):
            self.asked(self.run_(command), "repo_settings", command)
        for command in ("gh api -X PUT repositories/123/rulesets/1 --input r.json", "gh api -X PATCH repositories/123"):
            self.asked(self.run_(command), "repo_settings", command)
        self.asked(self.run_('gh api -X POST "repos/o/$R/rulesets"'), "command_unreadable", "an endpoint in a variable")

    def test_what_does_not_write_the_repos_settings_is_not_asked_about(self):
        for command in ("gh api repos/o/r", "gh api repos/o/r/rulesets", "gh api -X GET repos/o/r/rulesets -f x=1",
                        "gh repo view", "gh api -X POST repos/o/r/issues/5/comments -f body='rulesets and settings'",
                        "gh api repos/o/r/branches/main/protection", "gh issue create --title 'edit the ruleset'",
                        "gh api -X POST repos/o/r/issues -f title=x", "gh ruleset list", "gh ruleset view 1",
                        "gh ruleset check main", "gh api -X POST repositories/123/issues -f title=x"):
            self.assertEqual(self.run_(command), "", command)

    def test_the_question_shows_no_credential_and_no_command(self):
        for payload in (bash("gh api -X PATCH 'https://someone:hunter2secret@api.github.com/repos/o/r?t=hunter2secret'",
                             self.project),
                        bash("echo hunter2secret > lifecycle/hunter2secret", self.project),
                        bash("curl -u someone:hunter2secret -X PUT https://api.github.com/repos/o/r/pulls/5/merge",
                             self.project),
                        bash("hunter2secret 'never closed", self.project),
                        bash("gh ghp_hunter2secret 5", self.project),
                        bash("gh api -X ghp_hunter2secret repos/o/r/rulesets", self.project),
                        bash("gh api --ghp_hunter2secret=1 -X POST repos/o/r/rulesets", self.project),
                        bash("ghp_hunter2secret lifecycle/x", self.project),
                        bash("git ghp_hunter2secret -- lifecycle/x", self.project),
                        bash("ls | xargs ghp_hunter2secret", self.project),
                        {"tool_name": "Edit", "tool_input": {"file_path": 7}, "cwd": "hunter2secret"}):
            said = protected.respond(payload, self.env)
            self.assertIn('"ask"', said)
            self.assertNotIn("hunter2secret", said)
            self.assertNotIn("someone", said)

    def test_the_git_commands_the_identity_hook_knows_are_known_here(self):
        for command in ("git merge-tree --write-tree A B", "git commit-graph write --reachable"):
            self.assertEqual(self.run_(command), "", command)
        self.asked(self.run_("git mt A B"), "command_unreadable", "an alias")

    def test_git_plumbing_that_reads_is_not_asked_about_for_the_words_it_is_given(self):
        for command in ("git check-ref-format --branch lifecycle/x", "git check-mailmap 'A <a@x>' lifecycle/x",
                        "git verify-pack -v lifecycle/x.idx", "git show-index lifecycle/x.idx",
                        "git patch-id lifecycle/x", "git get-tar-commit-id lifecycle/x",
                        "git merge-tree --write-tree lifecycle/x main", "git merge-tree lifecycle/x main",
                        "git commit-graph verify --object-dir lifecycle/x"):
            self.assertEqual(self.run_(command), "", command)
        self.asked(self.run_("git commit-graph write --object-dir lifecycle/x"), "protected_path", "a write")


class RulesChanged(unittest.TestCase):
    """Stop. Every protected path and Kernel module the branch changes against its merge base is listed for the person."""

    def branch(self) -> pathlib.Path:
        where = repo(fresh=True)
        git(where, "update-ref", "refs/remotes/origin/main", "HEAD")
        return where

    def told(self, where, **given) -> str:
        payload = {"hook_event_name": "Stop", "stop_hook_active": False, "cwd": str(where)}
        code, out, err = rules_changed.respond(payload, environment(programs("git"), CLAUDE_PROJECT_DIR=str(where)),
                                               **given)
        self.assertEqual((code, err), (0, ""))
        return json.loads(out)["systemMessage"] if out else ""

    def write(self, where, rel, text="{}\n"):
        (where / rel).parent.mkdir(parents=True, exist_ok=True)
        (where / rel).write_text(text)

    def test_from_the_front_door_a_committed_change_to_the_lifecycle_is_listed(self):
        where = self.branch()
        self.write(where, "lifecycle/issue.json")
        git(where, "add", "-A")
        git(where, "commit", "-q", "-m", "a rule")
        payload = {"hook_event_name": "Stop", "stop_hook_active": False, "cwd": str(where)}
        done = hook("rules_changed", payload, programs("git"), CLAUDE_PROJECT_DIR=str(where))
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        said = json.loads(done.stdout)["systemMessage"]
        for part in ("lifecycle/issue.json", "the Lifecycle", "the Factory's own rules"):
            self.assertIn(part, said)

    def test_an_edit_made_through_eval_is_listed(self):
        where = self.branch()
        subprocess.run(["/bin/sh", "-c", "mkdir -p lifecycle; eval \"printf x > life\"\"cycle/b.json\""], cwd=where,
                       check=True)
        self.assertIn("lifecycle/b.json", self.told(where))

    def test_the_index_the_working_tree_the_commits_and_the_kernel_are_listed(self):
        where = self.branch()
        self.write(where, "config/authority.json")
        git(where, "add", "-A")
        git(where, "commit", "-q", "-m", "committed")
        self.write(where, ".github/workflows/x.yml")
        git(where, "add", ".github")
        self.write(where, "kernel/decide.py")
        self.write(where, "lifecycle/staged.json")
        git(where, "add", "lifecycle/staged.json")
        (where / "lifecycle" / "staged.json").unlink()      # in the index alone
        said = self.told(where)
        for part in ("config/authority.json", ".github/workflows/x.yml", "kernel/decide.py", "the Kernel",
                     "lifecycle/staged.json"):
            self.assertIn(part, said)

    def test_every_protected_path_changed_is_listed(self):
        where = self.branch()
        for n in range(25):
            self.write(where, "lifecycle/f%02d.json" % n)
        said = self.told(where)
        for n in range(25):
            self.assertIn("lifecycle/f%02d.json" % n, said)
        self.assertNotIn("more", said)

    def test_a_branch_that_changes_no_rule_says_nothing(self):
        where = self.branch()
        self.assertEqual(self.told(where), "")
        self.write(where, "docs/notes.md")
        git(where, "add", "-A")
        git(where, "commit", "-q", "-m", "docs")
        self.assertEqual(self.told(where), "")

    def test_a_base_faked_with_a_tag_or_a_branch_still_lists(self):
        where = self.branch()
        self.write(where, "lifecycle/issue.json")
        git(where, "add", "-A")
        git(where, "commit", "-q", "-m", "a rule")
        git(where, "tag", "origin/main")
        git(where, "branch", "origin/main")
        self.assertIn("lifecycle/issue.json", self.told(where))

    def test_a_replacement_ref_does_not_hide_a_changed_rule(self):
        where = self.branch()
        self.write(where, "lifecycle/issue.json")
        git(where, "add", "-A")
        git(where, "commit", "-q", "-m", "a rule")

        def out(*args):
            return subprocess.run(["git"] + list(args), cwd=where, env=environment(programs("git")), check=True,
                                  capture_output=True, text=True).stdout.strip()
        # The base replaced with a commit whose tree already holds the change: read through it, nothing differs.
        git(where, "replace", "HEAD~1", out("commit-tree", "-m", "base", out("rev-parse", "HEAD^{tree}")))
        self.assertEqual(out("diff", "--name-only", out("merge-base", "HEAD", rules_changed.BASE)), "")
        self.assertIn("lifecycle/issue.json", self.told(where))

    def test_a_name_with_a_newline_or_bytes_that_are_not_utf8_is_listed_escaped(self):
        where = self.branch()
        self.write(where, "lifecycle/x\ny.json")
        blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=where, input=b"{}", check=True,
                              capture_output=True, env=environment(programs("git"))).stdout.strip()
        subprocess.run([b"git", b"update-index", b"--add", b"--cacheinfo", b"100644," + blob + b",lifecycle/\xff.json"],
                       cwd=where, check=True, capture_output=True, env=environment(programs("git")))
        said = self.told(where)
        self.assertIn(repr("lifecycle/x\ny.json"), said)
        self.assertNotIn("x\ny.json", said)
        self.assertIn("lifecycle/\\udcff.json", said)
        self.assertTrue(all(c.isprintable() or c == "\n" for c in said))

    def test_a_check_that_runs_out_of_time_says_so(self):
        self.assertIn("could not be listed", self.told(self.branch(), seconds=0))

    def test_a_branch_whose_base_cannot_be_read_says_so(self):
        where = repo(fresh=True)
        git(where, "remote", "remove", "origin")
        self.assertIn("could not be listed", self.told(where))
        self.assertIn("could not be listed", self.told(folder()))
        code, out, _ = rules_changed.respond({"cwd": 7}, environment(programs("git")))     # whatever goes wrong
        self.assertEqual(code, 0)
        self.assertIn("could not be listed", json.loads(out)["systemMessage"])


class Settings(unittest.TestCase):
    def test_the_hook_that_asks_blocks_when_it_fails_to_answer(self):
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
        found = [h for g in settings["hooks"]["PreToolUse"] for h in g["hooks"] if "protected.py" in h["command"]]
        self.assertEqual([h.get("onFailure") for h in found], ["block"])

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
                                 "protected": ("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit|Bash"),
                                 "rules_changed": ("Stop", None)})
        entries = {p.stem for p in HOOKS.glob("*.py") if "\ndef main(" in p.read_text()}
        self.assertEqual(entries, set(wired))
