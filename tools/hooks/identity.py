"""PreToolUse on Bash: a commit, a push or a write to GitHub here is made as the Maintainer, or it is refused.

Three identities must be the Maintainer's (§9.12): the commit's author and committer, which come
from git's configuration in each clone, and the account that pushes or writes to GitHub, which comes
from gh. The Maintainer is in `config/hooks.json`; the machine user is the approver in
`config/defaults.json`, which approves and does nothing else (decision 0005). The hook reads what is
configured, so an identity set inside the command is refused, and what it cannot read it refuses.

A program the command gives git to run is one it cannot read, so it is refused whatever git does: an
option that names one (--upload-pack, grep -O, rebase -x and the rest, by any spelling git takes), a
helper set by -c, and GIT_EXEC_PATH set in the command. Only cat and less, by their bare names, pass.
A protocol allowed (protocol.*.allow, GIT_ALLOW_PROTOCOL) or an ext:: URL is refused for every
command, since any may run a transport, by a lazy fetch in a partial clone, and so is any other
remote helper's URL (x::address) given to a command that takes a remote; ssh.variant names no
program and passes. Some things are decided rather than read (decision 0017). A helper that runs a
script (core.pager='sh x.sh'), given by -c or an option, is a program like any other and is
refused: the hook reads words, never a file, and the script may be written in the same command.
Notes and stash make commits on no branch, which are accepted without reading who makes them: no
pull request carries one, only a push takes one out of the clone, and the hook reads every commit a
push sends. A refspec in a variable that an earlier command in the same command set to a plain
value is read as that value; $(git branch --show-current) and its like, where the push runs, as
HEAD; any other variable or command substitution, and a wildcard, it cannot read, and refuses. A
mirror push is read ref by ref, refs/notes and refs/stash among them. A remote held in a variable is
read the same way, or refused. A variable set before a program is set for that program alone; one
set alone, or by export and the like, holds for what follows until unset. This guards against
mistakes; the Stop check and the rulesets are the boundary. Run as `python3 -I` on this file; see
after_edit.py.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))
from tools.hooks import shell  # noqa: E402

DEADLINE = 45   # seconds for the whole check; the settings give the hook 60, and running out refuses
WRITES = {"am", "cherry-pick", "commit", "commit-tree", "filter-branch", "merge", "pull", "push", "rebase", "revert"}
# Known, and not a commit. These run commands of their own, so their text is read for a commit or push.
RUNNERS = {"bisect", "difftool", "mergetool", "submodule"}
# Known, and not themselves a commit or a push: mostly they read, so a write verb in their name or their words is
# only text. The split from the rest of OTHERS is documentary; every command in OTHERS is treated alike. An option
# that makes one of these run a program (--upload-pack, --exec, grep -O) is refused, by HELPER_OPTIONS below; a
# fetch that moves a local branch (git fetch . main:side) commits nothing, and protected.py asks about it.
READS = {"annotate", "archive", "blame", "cat-file", "check-attr", "check-ignore", "check-mailmap",
         "check-ref-format", "cherry", "commit-graph", "count-objects", "describe", "diff", "diff-files", "diff-index",
         "diff-tree", "fetch", "for-each-ref", "fsck", "get-tar-commit-id", "grep", "help", "log", "ls-files",
         "ls-remote", "ls-tree", "merge-base", "merge-tree", "name-rev", "patch-id", "range-diff", "rev-list",
         "rev-parse", "shortlog", "show", "show-branch", "show-index", "show-ref", "status", "var", "verify-commit",
         "verify-pack", "verify-tag", "version", "whatchanged"}
# Known, and not a commit: READS, and these, which change the repo, its index or its working tree. Of them, notes and
# stash make commits, but on no branch: OFF_BRANCH says why they are not read as one.
OTHERS = READS | {"add", "apply", "branch", "bundle", "checkout", "clean", "clone", "config", "format-patch", "gc",
                   "hash-object", "init", "maintenance", "mv", "notes", "prune", "reflog", "remote", "repack", "reset",
                   "restore", "rm", "sparse-checkout", "stash", "switch", "symbolic-ref", "tag", "update-index",
                   "update-ref", "worktree", "write-tree"}
# The commands that make a commit on no branch (refs/notes/*, refs/stash), accepted without reading who makes it
# (decision 0017). This records the decision and drives no code: being in OTHERS is what lets them pass.
OFF_BRANCH = {"notes", "stash"}
GIT_FLAGS = {"-p", "--paginate", "-P", "--no-pager", "--bare", "--no-replace-objects", "--literal-pathspecs",
             "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs", "--no-optional-locks", "--no-lazy-fetch",
             "--no-advice", "--version", "-v", "--help", "-h", "--html-path", "--man-path", "--info-path",
             "--exec-path"}
GIT_VALUED = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
GH_VALUED = {"-R", "--repo", "--hostname"}
PUSH_VALUED = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}
# Programs that print their words and run none of them, so a commit or push in their text is only text.
TEXT_ONLY = {"echo", "printf", "grep", "egrep", "fgrep", "rg", "cat", "head", "tail", "wc", "ls", "less", "sort",
             "uniq", "cut", "tr", "diff", "test", "[", "true", "false"}
SHELLS_AND_SOURCE = shell.SHELLS | {"source", "."}     # without -c, these run a script the hook cannot see
WRITE_TEXT = re.compile(r"\bgit\b[\s\S]*\b(%s)\b|\bgh\b[\s\S]*\b(pr|release|api)\b" % "|".join(sorted(WRITES)))
# Set in the command, each of these changes who git or gh says you are.
ENVIRONMENT = re.compile(r"^(GIT_AUTHOR_\w*|GIT_COMMITTER_\w*|GIT_CONFIG\w*|GIT_DIR|GIT_WORK_TREE|GIT_ASKPASS|"
                         r"GIT_SSH\w*|GH_\w+|GITHUB_\w*TOKEN|EMAIL|HOME|XDG_CONFIG_HOME)=")
GIT_CONFIG_FILE = re.compile(r"(^|/)\.git/config$|\.gitconfig$|(^|/)git/config$")
KEYS = re.compile(r"^(user|author|committer|credential|url|remote|include|includeif|core\.sshcommand|alias|http)\b",
                  re.I)
# Set in the command, each of these names a program git runs, or where it finds one. One list for both hooks:
# protected.py's GIT_HELPER_KEYS is this. Some are in KEYS too, and are refused for that as well.
PROGRAM_KEYS = re.compile(
    r"^(merge\..+\.driver|core\.(pager|editor|fsmonitor|hookspath|attributesfile|gitproxy|sshcommand|askpass|"
    r"alternaterefscommand)|pager\..+|sequence\.editor|interactive\.difffilter|diff\.external|"
    r"diff\..+\.(textconv|command)|filter\..+|gpg\.(.+\.)?program|gpg\.ssh\.defaultkeycommand|"
    r"trailer\..+\.(cmd|command)|tar\..+\.command|(difftool|mergetool|man|browser)\..+\.(cmd|path)|"
    r"submodule\..+\.update|remote\..+\.(vcs|uploadpack|receivepack)|sendemail\.sendmailcmd|init\.templatedir|"
    r"uploadpack\.packobjectshook|protocol\.(.+\.)?allow)$", re.I | re.S)
# protocol.ext.allow lets the ext:: transport run the command its URL names, and any command may run a transport: a
# fetch, or, in a partial clone, a lazy fetch of a missing object by cat-file, log or checkout. ssh.variant names no
# program, only how git calls ssh, and is not refused.
# Configuration that loads code from a place, or names a program git finds: a reader's name is no exemption here
# (core.hooksPath=cat is a directory). protected.py asks of the same.
LOAD_KEYS = re.compile(
    r"^(core\.hookspath|core\.attributesfile|include\.path|includeif\..+\.path|init\.templatedir|"
    r"protocol\.(.+\.)?allow|(difftool|mergetool|man|browser)\..+\.path|remote\..+\.vcs|credential\.(.+\.)?helper)$",
    re.I | re.S)
SWITCHES = re.compile(r"^(pager\..+|core\.fsmonitor)$", re.I)    # of these, a boolean runs nothing
BOOLEANS = {"true", "false", "yes", "no", "on", "off", "1", "0"}
# A helper is a program, and one that runs a script (core.pager='sh x.sh') is a helper like any other: the hook reads
# words, never a file, and the script may be written in the same command. Only these, by their bare names, pass.
PAGERS = {"cat", "less"}    # a bare program git may run, which runs nothing of its own
# Options whose value is a program git runs, and whether it may be the next word (False: only after `=`); options
# that run a program the command does not name, for every command (None) or for these; and short options, by
# command. This hook refuses each one, but a bare name of PAGERS; protected.py asks of the same.
HELPER_OPTIONS = {"--upload-pack": True, "--receive-pack": True, "--exec": True, "--extcmd": True,
                  "--open-files-in-pager": False}
HELPER_ALWAYS = {"--ext-diff": None, "--template": {"clone", "init"}}
HELPER_SHORT = {"grep": {"O": False}, "ls-remote": {"u": True}, "clone": {"u": True}, "difftool": {"x": True},
                "rebase": {"x": True}}
# The short options of these commands that take a value, which ends a bundle: what follows the letter is the value,
# never another option (-Xsubtree=lex, -eOwner, -bfix-ui). Alone, a required one takes the next word; an optional
# one (rebase -S[keyid]) takes only what is attached, and never the next word.
SHORT_VALUED = {"grep": "efABCm", "ls-remote": "ou", "clone": "bjou", "difftool": "tx", "rebase": "CXsx"}
SHORT_OPTIONAL = {"rebase": "S"}
# Set in the command, these say where git finds the programs it runs, or let a transport run one (ext::), for any
# command, since any may run a transport.
PROGRAM_ENVIRONMENT = {"GIT_EXEC_PATH", "GIT_ALLOW_PROTOCOL"}
# A remote helper's URL, <transport>::<address>: git runs git-remote-<transport>, or for ext:: and fd:: the command
# the address names. Each is refused in a word a command that takes a remote is given; ext:: in any word.
REMOTE_HELPER = re.compile(r"^\+?[A-Za-z0-9][A-Za-z0-9+.-]*::")
TAKES_REMOTE = {"archive", "clone", "fetch", "ls-remote", "pull", "push", "remote", "submodule"}
# The options of fetch, pull, clone and ls-remote whose value is the next word when it is not attached, taken by any
# prefix; and their short ones, by command, which end a bundle: a required one takes the next word when it is last,
# an optional one (pull -r[mode], -S[keyid]) only what is attached. protected.py reads a fetch's refspecs by them.
FETCH_VALUED = ("--depth", "--deepen", "--shallow-since", "--shallow-exclude", "--server-option", "--upload-pack",
                "--jobs", "--negotiation-tip", "--filter", "--submodule-prefix", "--strategy", "--strategy-option",
                "--exec")
REMOTE_VALUED = FETCH_VALUED + ("--refmap", "--origin", "--branch", "--reference", "--reference-if-able",
                                "--separate-git-dir", "--config", "--template", "--bundle-uri", "--revision", "--sort")
FETCH_SHORT_VALUED, FETCH_SHORT_OPTIONAL = "ojsX", "rS"
REMOTE_SHORT = {"fetch": (FETCH_SHORT_VALUED, FETCH_SHORT_OPTIONAL), "pull": (FETCH_SHORT_VALUED, FETCH_SHORT_OPTIONAL),
                "clone": ("bjouc", ""), "ls-remote": ("ou", "")}
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")      # a word that sets a variable; protected.py reads it too
VARIABLE = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))")
PLAIN = re.compile(r"^[^\s$`*?\[\]{}'\"\\]*$")       # a value the shell puts in a word as it stands
# Programs whose assignment words set a variable for every command after them, also behind a prefix (command export);
# and those whose assignment words set the environment of the program they run alone: env, sudo, and, before git, the
# wrappers and prefixes that run it (nohup env X=1 git). `unset` ends a variable.
SETTERS = {"export", "declare", "typeset", "local", "readonly"}
RUNS_GIT = shell.WRAPPERS | shell.PREFIXES
# A command substitution that names the branch the shell is on: run where the push runs, it is HEAD.
CURRENT_BRANCH = re.compile(r"^\$\(\s*git\s+(branch\s+--show-current|rev-parse\s+--abbrev-ref\s+HEAD|"
                            r"symbolic-ref\s+((-q|--quiet)\s+)?--short\s+HEAD)\s*\)$")
WILDCARD = re.compile(r"[*?\[]")
TOKENS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
IDENT = re.compile(r"^(.*) <(.*)> \d+ [+-]\d{4}$")
GITHUB = re.compile(r"^https://(?:([^@/]+)@)?github\.com/")
CREDENTIAL = re.compile(r"(?<=://)[^/@\s]+@")
URLISH = re.compile(r"://|^[^/]+@[^/]+:")
HELPER = "gh auth git-credential"
SHOWN = 3   # commits of another identity named in a refusal


class Unreadable(Exception):
    """Something the decision rests on could not be read."""


class Reader:
    """Runs git and gh for one check, all of it within one deadline."""

    def __init__(self, env: dict, seconds: float):
        self.env, self.until = env, time.monotonic() + seconds

    def run(self, program: str, args: list, where) -> str:
        left = self.until - time.monotonic()
        if left <= 0:
            raise Unreadable("the identity check ran out of time before `%s %s`" % (program, args[0]))
        exe = shutil.which(program, path=self.env.get("PATH", os.defpath))
        if exe is None:
            raise Unreadable("%s is not on PATH, so who would commit or push cannot be read" % program)
        try:
            done = subprocess.run([exe] + args, cwd=str(where), env=self.env, capture_output=True, text=True,
                                  timeout=left)
        except subprocess.TimeoutExpired:
            raise Unreadable("`%s %s` did not finish before the identity check's deadline" % (program, args[0]))
        if done.returncode != 0:
            first = (done.stderr.strip().splitlines() or ["exit %d" % done.returncode])[0]
            raise Unreadable("`%s %s` failed in %s: %s" % (program, args[0], where, first))
        return done.stdout


def _join(here, path: str):
    """Where `cd path` or `git -C path` leads from `here`; None when it cannot be told from the words."""
    if here is None or "$" in path or "`" in path or (path.startswith("~") and not re.match(r"~(/|$)", path)):
        return None
    return here / os.path.expanduser(path)


def _gh_kind(words: list) -> str:
    """What a gh command does to GitHub: push (a pull request may push its branch), write, or nothing."""
    if words[:2] == ["pr", "create"]:
        return "push"
    if words[:2] in (["pr", "merge"], ["release", "create"]):
        return "account"
    if words[:1] != ["api"]:
        return ""
    method, fields, i = None, False, 1
    while i < len(words):
        option, given, value = words[i].partition("=")
        if option in ("-X", "--method") or (option.startswith("-X") and len(option) > 2):
            if option.startswith("-X") and len(option) > 2:
                value = option[2:]
            elif not given:
                i += 1
                value = words[i] if i < len(words) else ""
            method = value.upper()
        elif option in ("-f", "-F", "--field", "--raw-field", "--input"):
            fields = True
        i += 1
    method = method or ("POST" if fields else "GET")
    return "account" if method in ("POST", "PUT", "PATCH", "DELETE") else ""


def _calls(commands: list, cwd, text: str) -> tuple:
    """(calls, always, inline). A call is (tool, directory, words after the tool's options, kind).

    `always` refuses whatever the command does: what cannot be read. `inline` refuses only a command
    that commits, pushes or writes: an identity set in the command itself.
    """
    here = pathlib.Path(cwd) if cwd else None
    calls, always, inline, blind = [], [], [], False
    kept = {}       # what earlier commands set for every command after them: a name, and its value or None if unread
    for words, targets in commands:
        inline += [("identity_set_in_command", "%s is set in the command; the hook reads only what is configured"
                    % w.split("=")[0]) for w in words if ENVIRONMENT.match(w)]
        inline += [("identity_set_in_command", "the command touches git's configuration (%s); change it in a command "
                                               "of its own" % w) for w in words + targets if GIT_CONFIG_FILE.search(w)]
        if not words:
            continue
        at = next((i for i, w in enumerate(words) if os.path.basename(w) in ("git", "gh")), None)
        local, given, ended = assigned(words, at)
        for name in ended:
            kept.pop(name, None)
        for name, value in given.items():
            value = expand(value, kept)
            kept[name] = value if PLAIN.match(value) else None
        named = set(kept) | local       # what the command sets in the environment, on git or earlier in the command
        if words[0] in ("cd", "pushd"):
            here = _join(here, words[1]) if len(words) > 1 and words[1] != "-" else None
            continue
        program = os.path.basename(words[0])
        blind = blind or (program in SHELLS_AND_SOURCE and not any(w.startswith("-") and not w.startswith("--")
                                                                   and "c" in w for w in words[1:]))
        if at is None:
            if program not in TEXT_ONLY and WRITE_TEXT.search(" ".join(words)):
                always.append(("command_unreadable", "`%s` looks like a commit or push the hook cannot read as one"
                               % program))
            continue
        # A word is expanded from what earlier commands set: the shell expands it before a prefix's assignment holds.
        tool, rest = os.path.basename(words[at]), [expand(w, kept) for w in words[at + 1:]]
        where, i, settings = here, 0, []
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
            elif option in ("-c", "--config-env"):
                settings.append((option, value))
            elif option in ("--git-dir", "--work-tree"):
                always.append(("identity_set_in_command", "%s points git at a repo the hook does not read" % option))
            elif option == "--exec-path" and given:
                always.append(("command_unreadable", "git is told where to find the programs it runs, which the hook "
                                                     "cannot read"))
            elif option not in GIT_FLAGS:
                always.append(("git_option_unknown", "git %s is an option the hook does not know" % option))
        words = rest[i:]
        if tool == "git":
            sub = words[0] if words else ""
            if sub == "push" and where == here:       # the branch the shell is on, where the push runs
                words = [sub] + ["HEAD" if CURRENT_BRANCH.match(w) else w for w in words[1:]]
            for option, value in settings:
                always += _setting(option, value)
            always += _programs(sub, words[1:])
            if PROGRAM_ENVIRONMENT & named or remote_helper(sub, rest, words[1:]):
                always.append(("command_unreadable", "the command sets where git finds a program it runs, or lets a "
                                                     "transport run one, which the hook cannot read"))
            if sub in TAKES_REMOTE and any(_expands(w) for w in remotes(sub, words[1:])):
                always.append(("command_unreadable", "a remote is held in a variable or a command the hook cannot "
                                                     "read"))
            kind = ("push" if sub == "push" else "commit") if sub in WRITES else ""
            if sub and sub not in WRITES | RUNNERS | OTHERS:
                always.append(("git_command_unknown", "git %s is not a command the hook knows; it may be an alias, "
                                                      "which the hook cannot read" % sub))
            elif sub in RUNNERS and WRITE_TEXT.search(" ".join(words)):
                always.append(("command_unreadable", "git %s runs a command the hook cannot read" % sub))
        else:
            kind = _gh_kind(words)
        calls.append((tool, where, words, kind))
    if blind and WRITE_TEXT.search(text):
        always.append(("command_unreadable", "a shell reads a script the hook cannot see, in a command that names a "
                                             "commit or push"))
    return calls, always, inline


def assigned(words: list, git=None) -> tuple:
    """(local, kept, ended) of a simple command's words, git at index `git` when it runs git: the names they set for
    the program they run alone, the names and values they set for every command after them too, and the names they
    unset.

    Local are the assignments before a program, and those given to env or sudo, or, before git, to a wrapper that
    runs it (command env, nohup env, nice env). Kept are assignments with no program after them, and those given to
    export, declare and the like, behind a prefix too (command export). Any other word is an argument, whatever it
    looks like."""
    at, kept, ended = 0, {}, set()
    while at < len(words) and ASSIGNMENT.match(words[at]):
        at += 1
    pairs = [w.split("=", 1) for w in words[:at]]
    if at == len(words):
        return set(), dict(pairs), ended
    local = {name for name, _ in pairs}
    words = words if git is None else words[:git]       # git's own words set nothing
    while git is None and at < len(words) - 1 and words[at] in shell.PREFIXES:
        at += 1
    if at == len(words):
        return local, kept, ended
    first, args = os.path.basename(words[at]), words[at + 1:]
    if first in SETTERS:
        kept.update(w.split("=", 1) for w in args if ASSIGNMENT.match(w))
    elif first == "unset" and "-f" not in args:
        ended |= {w for w in args if not w.startswith("-")}
    elif first in ("env", "sudo") or (git is not None and first in RUNS_GIT):
        local |= {w.split("=")[0] for w in args if ASSIGNMENT.match(w)}
    return local, kept, ended


def remote_helper(sub: str, words: list, given: list) -> bool:
    """Whether git is given a remote helper's URL: ext:: in any of its `words`, or <transport>::<address> in a word,
    or an option's value, that `given` to a command that takes a remote. A commit message or a pattern is not one."""
    if any("ext::" in w.casefold() for w in words):
        return True
    return sub in TAKES_REMOTE and any(REMOTE_HELPER.match(w.partition("=")[2] if w[:2] == "--" else w) for w in given)


def expand(word: str, kept: dict) -> str:
    """The word with each variable put in that an earlier command set to a plain value; as it is, when one is not."""
    if not _expands(word):
        return word
    out = VARIABLE.sub(lambda m: "\0" if kept.get(m.group(1) or m.group(2)) is None else kept[m.group(1) or m.group(2)],
                       word)
    return word if "\0" in out or _expands(out) else out


def remotes(sub: str, words: list) -> list:
    """The words of git's command `sub` that name a remote: the repository of a push, fetch, pull, clone or ls-remote,
    each word after remote add or set-url and after submodule add, and archive's --remote, by any prefix."""
    if sub == "push":
        return _targets(words)[0][:1]
    if sub in REMOTE_SHORT:
        return operands(sub, words)[:1]
    if sub in ("remote", "submodule"):
        named = operands(sub, words)
        return named[1:] if named[:1] and named[0] in (("add", "set-url") if sub == "remote" else ("add",)) else []
    found = []
    for j, word in enumerate(words):
        option, given, value = word.partition("=")
        if sub == "archive" and word[:2] == "--" and shell.spelt(option, "--remote"):
            found.append(value if given else words[j + 1] if j + 1 < len(words) else "")
    return found


def operands(sub: str, words: list) -> list:
    """The words git's command `sub` is given that are neither an option nor an option's value, read as git reads
    them: a long option of REMOTE_VALUED by any prefix, its value attached or the next word; a bundle of short options
    to its first that takes a value (REMOTE_SHORT)."""
    valued, optional = REMOTE_SHORT.get(sub, ("", ""))
    out, j = [], 0
    while j < len(words):
        word = words[j]
        if word == "--":
            return out + words[j + 1:]
        if word[:2] == "--":
            j += "=" not in word and any(shell.spelt(word, name) for name in REMOTE_VALUED)
        elif word[:1] == "-" and len(word) > 1:
            j += takes_next(word, valued, optional)
        else:
            out.append(word)
        j += 1
    return out


def takes_next(word: str, valued: str, optional: str = "") -> bool:
    """Whether a bundle of short options (-qo, -rmerges) takes the next word as a value. It ends at its first letter
    of `valued` or `optional`, and what follows that letter is its value: only a letter of `valued`, last, takes the
    next word. protected.py reads a fetch's refspecs by it."""
    for at, c in enumerate(word[1:], 1):
        if c in valued:
            return at == len(word) - 1
        if c in optional:
            return False
    return False


def _quoted(text: str) -> str:
    """`text` with each command substitution outside quotes, $(...) or `...`, made one quoted word $(...), as one in
    double quotes is: so that what it gives a command is read as a word that cannot be read, not as words cut off."""
    out, i, quote = [], 0, None
    while i < len(text):
        c = text[i]
        if quote == "'":
            quote = None if c == "'" else quote
        elif c == "\\":
            out.append(text[i:i + 2])
            i += 2
            continue
        elif quote == '"' and text.startswith("$(", i):
            end = _closed(text, i + 2, ")")
            if end is None:
                return text
            out.append(text[i:end + 1])
            i = end + 1
            continue
        elif quote == '"':
            quote = None if c == '"' else quote
        elif c in "'\"":
            quote = c
        elif c == "#" and (i == 0 or text[i - 1] in " \t\n;&|("):
            end = text.find("\n", i)
            end = len(text) if end < 0 else end
            out.append(text[i:end])
            i = end
            continue
        elif c == "`" or text.startswith("$(", i):
            end = _closed(text, i + (1 if c == "`" else 2), c if c == "`" else ")")
            if end is None:
                return text
            inner = text[i + (1 if c == "`" else 2):end]
            out.append("'$(%s)'" % inner if "'" not in inner else '"$(%s)"' % inner)
            i = end + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _closed(text: str, i: int, end: str):
    """Where the substitution whose body starts at i ends: its `)`, or its closing backtick; None if it never does."""
    depth, quote = 0, None
    while i < len(text):
        c = text[i]
        if quote == "'":
            quote = None if c == "'" else quote
        elif c == "\\":
            i += 1
        elif quote == '"' and c == '"':
            quote = None
        elif c in "'\"" and quote is None:
            quote = c
        elif end == ")" and text.startswith("$(", i):
            i = _closed(text, i + 2, ")")
            if i is None:
                return None
        elif quote is None and c == end and (end == "`" or depth == 0):
            return i
        elif quote is None and end == ")" and c in "()":
            depth += 1 if c == "(" else -1
        i += 1
    return None


def _setting(option: str, value: str, keys: bool = True) -> list:
    """Why git's -c or --config-env `value` is refused: what the hook reads from configuration (with `keys`), or a
    program git runs."""
    problems = []
    if keys and KEYS.match(value):
        problems.append(("identity_set_in_command", "git %s %s sets in the command what the hook reads from "
                                                    "configuration" % (option, value.split("=")[0])))
    key, valued, setting = value.partition("=")
    plain = option == "-c" and ((setting in PAGERS and not LOAD_KEYS.match(key)) or (
        SWITCHES.match(key) is not None and (not valued or setting.lower() in BOOLEANS)))
    if (PROGRAM_KEYS.match(key) and not plain) or LOAD_KEYS.match(key):
        problems.append(("command_unreadable", "git %s %s sets a program git runs, which the hook cannot read"
                         % (option, key)))
    return problems


def _programs(sub: str, words: list) -> list:
    """Why the options of git's command `sub` are refused: a program they give git to run, but a bare reader."""
    problems = []
    for kind, value in programs_given(sub, words):
        if kind == "config":
            problems += _setting("-c", value, keys=False)
        elif kind == "always" or value not in PAGERS:
            problems.append(("command_unreadable", "git is given a program to run in the command, which the hook "
                                                   "cannot read"))
    return problems


def programs_given(sub: str, words: list) -> list:
    """What the options of git's command `sub` give it to run, as (kind, value), read as git reads them: a long option
    by any prefix, a short one alone, bundled (-nO./p) or with its value attached. ("program", the program, or None
    when the command does not name it); ("always", None) for an option that runs a program the command does not
    name; ("config", a setting) for clone's -c, which may name one. A bundle ends at its first letter that takes a
    value (SHORT_VALUED): what follows is that value. protected.py reads them too."""
    shorts, valued, optional = HELPER_SHORT.get(sub, {}), SHORT_VALUED.get(sub, ""), SHORT_OPTIONAL.get(sub, "")
    out, j = [], 0
    while j < len(words) and words[j] != "--":
        word, after = words[j], words[j + 1] if j + 1 < len(words) else None
        option, given, value = word.partition("=")
        letter, config = None, False
        if word[:1] == "-" != word[1:2]:
            for at, c in enumerate(word[1:], 1):
                if c in shorts:
                    letter = c
                elif sub == "clone" and c == "c":
                    config = True       # clone's -c, alone, bundled or with its setting attached (-ccore.x=y)
                elif c in valued and at == len(word) - 1:
                    j += 1              # its value is the next word, which is not an option: -e -Ox
                if c in shorts or (sub == "clone" and c == "c") or c in valued or c in optional:
                    break               # an optional value is only what is attached: -S -x ./c
        long = next((o for o in HELPER_OPTIONS if shell.spelt(option, o)), None) if word[:2] == "--" else None
        takes = False
        if letter:          # -Oless, -nO./p: the value is what follows the letter in the bundle
            value = given = word[word.index(letter) + 1:]
            takes = shorts[letter]
        elif long:
            takes = HELPER_OPTIONS[long]
        if letter or long:
            if takes and not given and after is not None:
                j += 1
                given = value = after
            out.append(("program", value if given else None))
        if word[:2] == "--" and any(shell.spelt(option, o) and (subs is None or sub in subs)
                                    for o, subs in HELPER_ALWAYS.items()):
            out.append(("always", None))
        if config or (sub == "clone" and word[:2] == "--" and shell.spelt(option, "--config")):
            attached = word[word.index("c") + 1:] if config else value if given else ""
            out.append(("config", attached or after or ""))
            j += not attached
        j += 1
    return out


def _people() -> tuple:
    who = json.loads((ROOT / "config" / "hooks.json").read_text())["maintainer"]
    machine = json.loads((ROOT / "config" / "defaults.json").read_text())["approver"]
    return who, machine


def _committer(reader: Reader, where, who: dict, machine: str) -> list:
    problems = []
    for kind in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        found = IDENT.match(reader.run("git", ["var", kind], where).strip())
        name, email = found.groups() if found else ("?", "?")
        if (name, email) != (who["name"], who["email"]):
            code = "commit_as_machine_user" if machine.lower() in (name + email).lower() else "commit_identity_not_maintainer"
            problems.append((code, "in %s git would record the %s as %s <%s>, and a commit here is the Maintainer's, "
                                   "%s <%s>. Set user.name and user.email in this clone's git config, in a command of "
                                   "its own" % (where, kind[4:-6].lower(), name, email, who["name"], who["email"])))
    return problems


def _account(reader: Reader, who: dict, machine: str) -> list:
    """The account that pushes or writes: gh's, for github.com, and no token in the environment in its place."""
    for name in TOKENS:
        if reader.env.get(name):
            return [("account_unreadable", "%s is set, so git and gh act as whoever owns that token, which the hook "
                                           "cannot read; unset it" % name)]
    login = reader.run("gh", ["config", "get", "user", "-h", "github.com"], ROOT).strip()
    if not login:
        return [("account_unreadable", "gh names no active account for github.com")]
    if login.lower() == machine.lower():
        return [("account_is_machine_user", "gh's active account is %s, the machine user, which never pushes, merges or "
                                            "opens a pull request here. Run gh auth switch --user %s, in a command of "
                                            "its own" % (login, who["login"]))]
    if login.lower() != who["login"].lower():
        return [("account_not_maintainer", "gh's active account is %s, and a push or a write here is the Maintainer's, "
                                           "%s" % (login, who["login"]))]
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


def _expands(word: str) -> bool:
    return "$" in word or "`" in word


def _remotes(reader: Reader, where, remote, who: dict, machine: str) -> list:
    """Every URL the push may go to is GitHub over HTTPS, naming no account but the Maintainer's."""
    problems = []
    helper = reader.run("git", ["config", "--get-urlmatch", "credential.helper", "https://github.com"], where).strip()
    if not helper.endswith(HELPER):
        problems.append(("account_unreadable", "git in %s does not push to github.com through gh's account; run gh "
                                               "auth setup-git" % where))
    if remote and URLISH.search(remote):
        urls = [remote]
    elif remote:
        urls = reader.run("git", ["remote", "get-url", "--all", "--push", remote], where).split()
    else:
        urls = [url for name in reader.run("git", ["remote"], where).split()
                for url in reader.run("git", ["remote", "get-url", "--all", "--push", name], where).split()]
    for url in urls:
        found, shown = GITHUB.match(url), CREDENTIAL.sub("", url)
        user = (found.group(1) or "").split(":")[0] if found else ""
        if not found:
            problems.append(("account_unreadable", "%s is not GitHub over HTTPS, so the account that would push cannot "
                                                   "be read" % shown))
        elif user and user.lower() == machine.lower():
            problems.append(("account_is_machine_user", "%s pushes as %s, the machine user" % (shown, machine)))
        elif user and user.lower() != who["login"].lower():
            problems.append(("account_not_maintainer", "%s names an account in its URL, and not the Maintainer's"
                             % shown))
    return problems


def _commits(reader: Reader, where, args: list, refspecs: list, who: dict) -> list:
    """Every commit the push would send that no remote has yet is the Maintainer's, as author and as committer. A
    refspec held in a variable or a command, or with a wildcard, the hook cannot read; a mirror sends every ref."""
    sources = []
    for spec in refspecs:
        source = (spec[1:] if spec.startswith("+") else spec).split(":")[0]
        if source.startswith("-"):      # never hand the hook's own git an option from the command
            raise Unreadable("the push names a refspec that starts with '-': %s" % spec)
        if _expands(source):
            raise Unreadable("a refspec of the push is held in a variable or a command the hook cannot read")
        if WILDCARD.search(source):
            raise Unreadable("a refspec of the push has a wildcard, which the hook does not expand")
        if source:
            sources.append(source)
    shas = [reader.run("git", ["rev-parse", "--verify", "--end-of-options", source + "^{commit}"], where).strip()
            for source in sources or ["HEAD"]]
    options = [a.partition("=")[0] for a in args if a[:2] == "--"]
    given = [name for name in ("--mirror", "--all", "--branches", "--tags")
             if any(shell.spelt(option, name) for option in options)]
    pseudo = ["--all"] if "--mirror" in given else ["--branches"] if {"--all", "--branches"} & set(given) else []
    pseudo += ["--tags"] if "--tags" in given else []
    log = reader.run("git", ["log", "--format=%an%x00%ae%x00%cn%x00%ce"] + pseudo +
                     ["--not", "--remotes", "--not", "--end-of-options"] + shas, where)
    mine = [who["name"], who["email"], who["name"], who["email"]]
    others = sorted({line for line in log.splitlines() if line.split("\0") != mine})
    return [("push_carries_another_identity", "the push from %s carries a commit by %s <%s>, committed by %s <%s>; a "
                                              "commit here is the Maintainer's" % ((where,) + tuple((line.split("\0") + ["?"] * 4)[:4])))
            for line in others[:SHOWN]]


def _push(reader: Reader, where, args: list, who: dict, machine: str) -> list:
    """Where the push goes, through gh's account, carrying only the Maintainer's commits."""
    targets, deleting = _targets(args)
    remote, refspecs = (targets[0], targets[1:]) if targets else (None, [])
    if remote and remote.startswith("-"):
        return [("push_commits_unreadable", "the push names a remote that starts with '-'")]
    problems = []
    try:
        problems += _remotes(reader, where, None if remote and _expands(remote) else remote, who, machine)
    except Unreadable as err:
        problems.append(("account_unreadable", str(err)))
    if deleting:
        return problems
    try:
        problems += _commits(reader, where, args, refspecs, who)
    except Unreadable as err:
        problems.append(("push_commits_unreadable", str(err)))
    return problems


def check(payload: dict, env: dict, seconds: float = DEADLINE) -> list:
    """The reasons to refuse this command, as (code, sentence); none when it may run."""
    if payload.get("tool_name") != "Bash":
        return []
    command = payload["tool_input"]["command"]
    try:
        commands = shell.simple_commands(_quoted(shell.without_heredocs(command)))
    except ValueError as err:
        if WRITE_TEXT.search(command):
            return [("command_unreadable", "the command cannot be split into words (%s), so who would commit or push "
                                           "cannot be read. Write the message to a file and use git commit -F" % err)]
        return []
    calls, problems, inline = _calls(commands, payload.get("cwd"), command)
    writes = [c for c in calls if c[3]]
    if writes:
        problems += inline
        for tool, _, words, _ in calls:
            if (tool, words[:1]) in (("git", ["config"]), ("gh", ["auth"])):
                problems.append(("identity_set_in_command", "%s %s changes configuration in the command that writes; "
                                                            "change it in a command of its own" % (tool, words[0])))
        for tool, _, words, _ in writes:
            if tool == "git" and any(w == "--author" or w.startswith("--author=") for w in words):
                problems.append(("identity_set_in_command", "--author names someone other than the configured identity"))
        problems += _verify(writes, env, seconds)
    return list(dict.fromkeys((code, CREDENTIAL.sub("", sentence)) for code, sentence in problems))


def _verify(writes: list, env: dict, seconds: float) -> list:
    """Read who each write would be made as."""
    who, machine = _people()
    reader, problems = Reader(env, seconds), []
    if any(kind in ("push", "account") for _, _, _, kind in writes):
        try:
            problems += _account(reader, who, machine)
        except Unreadable as err:
            problems.append(("account_unreadable", str(err)))
    for tool, where, words, kind in writes:
        if kind == "account":
            continue
        if where is None or not where.is_dir():
            problems.append(("directory_unreadable", "the command commits or pushes in a directory the hook cannot "
                                                     "tell from its words (%s); give it as a plain path" % (where or "?")))
            continue
        try:
            problems += _committer(reader, where, who, machine)
        except Unreadable as err:
            problems.append(("identity_unreadable", str(err)))
        if kind == "push":
            problems += _push(reader, where, words[1:] if tool == "git" else [], who, machine)
    return problems


def main() -> int:
    try:
        problems = check(json.loads(sys.stdin.read()), dict(os.environ))
    except Exception as err:    # what the hook cannot read, it refuses
        problems = [("hook_failed", "the identity hook could not finish (%s: %s), so it refuses"
                     % (type(err).__name__, CREDENTIAL.sub("", str(err))))]
    if not problems:
        return 0
    print("Refused by tools/hooks/identity.py. A commit, a push or a write to GitHub here is the Maintainer's, who "
          "is named in config/hooks.json:", file=sys.stderr)
    for code, sentence in problems:
        print("- %s: %s." % (code, sentence), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
