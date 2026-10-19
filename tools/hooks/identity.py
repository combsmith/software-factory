"""PreToolUse on Bash: a guard that catches a session's honest mistake early, when a commit, a push or a write to
GitHub here would not be the Maintainer's. It is a helper, not a rule enforcer: it reads words, not the identity git
will use, so a spelling built to hide git, gh or `.git` is out of its scope, left to the Stop check, the rulesets and,
until "Identity: every commit a pull request carries is the Maintainer's, checked outside the shell" (issue 204) is
built, the Maintainer's reading of each pull request.

Three identities should be the Maintainer's (§9.12): the commit's author and committer, which come
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
set alone, or by export and the like, holds for what follows until unset. A push that names no
refspec, or no remote, is read from git's configuration, once, by push_configuration, which
protected.py calls too: a mirror, every remote's remote.*.push and push.default, and where a push
that names no remote goes; a push setting given in the command is refused (decision 0024). So is a
git the command may redefine, in a command that commits or pushes: a function or an alias for git,
gh or what runs them, PATH or a dynamic linker's variable set, git named by a path to another file, or git
run under a prefix or a wrapper not on shell.AS_IS (decision 0024; a name given to autoload, functions or
typeset -f is defined, and a shell's attached option value is never read as -c, issue 181); and, in such a
command, a write into git's directory,
by a redirection or a path a program of PATH_WRITERS is given. An alias whose value runs git or gh,
and git given no command by xargs or parallel, are refused always. A loop's word list and a case's
patterns are data (decision 0030). A write is read where and when the shell makes it: after popd or
cd -, in every directory the command has stood in; by a writer that names no output, where it stands;
by a substitution in a case's pattern, where the pattern stands; and through tar's old-style bundle,
an alias for a feeder, a shell, source or eval, and a bracket expression as the shell reads them. A
loop too long to read is one the hook cannot read (decision 0032). A word is read as the shell reads it
(decision 0032's Boundaries, issue 174): a substitution a single quote or a backslash holds is text to git, gh and a
program that prints its words, and read where another program may run it later; a comment is dropped; a $'...'
holding a backslash is refused on sight, since the hook decodes none; a command the hook cannot split, a ( touching a
word among them, is refused whatever it names; an alias is read as its value's text in place of its name; a variable the hook reads, in an
expansion it does not read as plain, may be anything; and wget's -e and tar's --one-top-level name places written.
This guards against mistakes; identity is enforced not here but by issue 204's check, named above. Run as `python3 -I` on
this file; see after_edit.py.
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
# Seconds, of DEADLINE, for reading the command's words. Past them the command is one the hook cannot read, and is
# refused, so that no reading runs on until the settings' timeout, which may let the command through (decision 0032).
READ_SECONDS = 10
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
# git configuration that says where a push goes, or what a push that names no refspec sends: every key push_configuration
# reads, and branch.*.merge. One list for both hooks: given in a command that commits or pushes, this hook refuses it,
# and protected.py asks.
PUSH_KEYS = re.compile(r"^(push\..*|remote\.pushdefault|remote\..*\.(push|mirror)|branch\..*\.(merge|remote|pushremote))$",
                       re.I | re.S)
# What push_configuration reads, in one call: what a push that names no refspec sends, where one that names no remote
# goes, and which remotes are configured.
PUSH_READ = r"^(push\.default|remote\.pushdefault|remote\..+\.(push|mirror|url|pushurl)|branch\..+\.(pushremote|remote))$"
# What a push that names no refspec sends under each push.default git takes: matching, every branch the remote shares;
# the rest, the branch the shell is on (nothing sends none, and is read as HEAD all the same). Any other value refuses.
DEFAULT_SENDS = {None: "HEAD", "simple": "HEAD", "current": "HEAD", "upstream": "HEAD", "tracking": "HEAD",
                 "nothing": "HEAD", "matching": ":"}
TRUE, FALSE = {"true", "yes", "on"}, {"false", "no", "off", ""}
LOCAL = "."     # a remote that is this repository: a push to it writes nothing to GitHub
# Set in the command, each of these names a program git runs, or where it finds one. One list for both hooks:
# protected.py's GIT_HELPER_KEYS is this. Some are in KEYS too, and are refused for that as well. submodule.*.update
# runs a program only when its value is !cmd, and any of these set to nothing runs none: _names_program reads that.
PROGRAM_KEYS = re.compile(
    r"^(merge\..+\.driver|core\.(pager|editor|fsmonitor|hookspath|attributesfile|gitproxy|sshcommand|askpass|"
    r"alternaterefscommand)|pager\..+|sequence\.editor|interactive\.difffilter|diff\.external|"
    r"diff\..+\.(textconv|command)|filter\..+\.(clean|smudge|process)|gpg\.(.+\.)?program|gpg\.ssh\.defaultkeycommand|"
    r"trailer\..+\.(cmd|command)|tar\..+\.command|(difftool|mergetool|man|browser)\..+\.(cmd|path)|"
    r"submodule\..+\.update|remote\..+\.(vcs|uploadpack|receivepack)|sendemail\.sendmailcmd|init\.templatedir|"
    r"uploadpack\.packobjectshook|protocol\.(.+\.)?allow)$", re.I | re.S)
SUBMODULE_UPDATE = re.compile(r"^submodule\..+\.update$", re.I | re.S)
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
VARIABLE_WHOLE = re.compile(r"^\$\{?([A-Za-z_]\w*)\}?$")     # a word that is one variable and nothing else
# shell.environment reads the command's variables fail-closed: only an assignment that runs unconditionally at the
# top level of a plain ;/newline sequence, once, its value a plain word. env and sudo set the environment of the
# program they run; before git, so do the wrappers and prefixes that run it (nohup env X=1 git).
SETS_LOCALLY = {"env", "sudo"}
# A name the command may define so that it runs in place of git or gh: they, and the words that run them as they are.
# $(which git) is read as the git on PATH, so which, type and whence, which say where it is, are among them.
REDEFINABLE = {"git", "gh", "builtin", "which", "type", "whence"} | shell.AS_IS
# The dynamic linker's variables: set anywhere in a command that writes, as PATH is, they may make git or gh run other
# code (issue 181). A closed list; a variable not on it is left alone.
LOADER_VARIABLES = {"LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH",
                    "DYLD_FRAMEWORK_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FALLBACK_FRAMEWORK_PATH"}
# gh's commands that write, as WRITE_TEXT names them, given to a program the hook cannot read.
GH_WRITES = {"pr", "release", "api"}
RUNS_GIT = shell.WRAPPERS | shell.PREFIXES
# Reserved words whose own words are data: a loop's word list, a case's word and its patterns. Only what the body runs
# is read, as a command of its own.
DATA_HEADS = {"for", "select", "case"}
# git's directory, as a path's component: a write into it, in a command that commits or pushes, may change what git
# runs or where a push goes (decision 0030).
GIT_DIRECTORY = ".git"
# The programs that write the paths they are given, as (which operands they write, their options that take the next
# word, their options whose value is a path they write, where they write when their words name no output). "last"
# writes the last operand, the destination; "all" every operand; "first" the first; "none" only an option's value. The
# fourth column is None for a writer whose words always name its output; else (its options of which one must be given,
# or none when it is empty; its options that name where it writes instead): given those, and none of these, and no
# operand it writes, it writes where it stands (decision 0032). Any other program's words are not writes into git's
# directory: find's -path, fd's -E and tree's -I are patterns, and a reader's operand, git's own -F among them, is read.
TARGET = {"-t", "--target-directory"}
PATH_WRITERS = {
    "cp": ("last", {"-S", "--suffix"}, TARGET, None), "mv": ("last", {"-S", "--suffix"}, TARGET, None),
    "ln": ("last", {"-S", "--suffix"}, TARGET, None), "ditto": ("last", set(), set(), None),
    "install": ("last", {"-m", "--mode", "-o", "--owner", "-g", "--group", "-S", "--suffix"}, TARGET, None),
    "rsync": ("last", {"-e", "--rsh", "--exclude", "--include", "--filter", "-f", "--exclude-from", "--include-from",
                       "--files-from", "--rsync-path", "--chmod", "--chown", "-M", "--remote-option", "--password-file",
                       "--compare-dest", "--copy-dest", "--link-dest"},
              {"--backup-dir", "--partial-dir", "-T", "--temp-dir", "--log-file", "--write-batch", "--only-write-batch"},
              None),
    "scp": ("last", {"-c", "-F", "-i", "-J", "-l", "-o", "-P", "-S", "-D", "-X"}, set(), None),
    "tee": ("all", set(), set(), None), "touch": ("all", {"-d", "--date", "-r", "--reference", "-t"}, set(), None),
    "mkdir": ("all", {"-m", "--mode"}, set(), None), "chmod": ("all", {"--reference"}, set(), None),
    "chown": ("all", {"--reference", "--from"}, set(), None), "chgrp": ("all", {"--reference", "--from"}, set(), None),
    "truncate": ("all", {"-s", "--size", "-r", "--reference"}, set(), None),
    "tar": ("none", {"-T", "--files-from", "-X", "--exclude-from", "--exclude", "-b", "--blocking-factor", "-H",
                     "--format", "-I", "--use-compress-program", "-N", "--newer", "-K", "--starting-file", "-L",
                     "--tape-length", "-V", "--label", "-F", "--info-script", "--new-volume-script"},
            {"-C", "--directory", "-f", "--file", "-g", "--listed-incremental"},
            ({"-x", "--extract", "--get"}, {"-C", "--directory"})),
    "curl": ("none", {"-d", "--data", "-H", "--header", "-u", "--user", "-X", "--request", "-F", "--form", "-A",
                      "--user-agent", "-e", "--referer", "-b", "--cookie", "-K", "--config", "-m", "--max-time"},
             {"-o", "--output", "--output-dir", "-D", "--dump-header", "-c", "--cookie-jar", "--trace", "--trace-ascii",
              "--stderr"}, ({"-O", "--remote-name", "--remote-name-all", "-J", "--remote-header-name"}, {"--output-dir"})),
    "wget": ("none", {"-e", "--execute", "-U", "--user-agent", "--header"},
             {"-O", "--output-document", "-P", "--directory-prefix", "-o", "--output-file", "-a", "--append-output"},
             (set(), {"-O", "--output-document", "-P", "--directory-prefix"})),
    "unzip": ("none", {"-x"}, {"-d"}, (set(), {"-d"})),
    "patch": ("first", {"-p", "--strip", "-i", "--input", "-F", "--fuzz", "-r", "--reject-file", "-B", "--prefix",
                        "-D", "--ifdef", "-z", "--suffix", "-V"}, {"-o", "--output", "-d", "--directory"},
              (set(), {"-o", "--output", "-d", "--directory"})),
}
HERE = "."      # where a writer that names no output writes: the directory it stands in
# The writers whose output options given `-` write the standard output, and their options that name a directory, to
# which `-` is a path. To any other program, and as an operand, `-` is a path like any other, which may be a link into
# git's directory.
STDOUT_DASH = {"curl": {"--output-dir"}, "wget": {"-P", "--directory-prefix"}}
# tar by its other names, and its modes: which of its places it writes depends on them (_tar).
TARS = {"tar", "gtar", "bsdtar"}
PATH_WRITERS.update({name: PATH_WRITERS["tar"] for name in TARS})
TAR_EXTRACTS = {"-x", "--extract", "--get"}
TAR_CHANGES = {"-c", "--create", "-r", "--append", "-u", "--update", "-A", "--catenate", "--concatenate", "--delete"}
TAR_READS = {"-t", "--list", "-d", "--diff", "--compare"}
# The suffixes tar's --one-top-level takes off an archive's name for the directory it extracts into.
TAR_SUFFIX = re.compile(r"(?:\.tar(?:\.(?:gz|bz2|xz|lz|lzma|lzo|zst|Z))?|\.(?:tgz|taz|tbz|tbz2|tb2|tz2|txz|tlz|tzst|tzo))$")
# wget's options whose value is a wgetrc command, key=value, the value a place written.
WGET_EXECUTE = {"-e", "--execute"}
# bsdtar's options that take the next word, where GNU tar's, in PATH_WRITERS, differ: its -H, -L and -K take none, and
# its -s takes a pattern. tar is either, by the system it runs on, so both readings are read (_written).
TAR_BSD_VALUED = {"-b", "--block-size", "-I", "-T", "--files-from", "-X", "--exclude-from", "--exclude", "--include",
                  "-s", "--format", "--options", "--newer", "--newer-mtime", "--newer-than", "--newer-mtime-than",
                  "--older", "--older-mtime", "--older-than", "--older-mtime-than", "--strip-components", "--uname",
                  "--gname", "--uid", "--gid", "--passphrase"}
# Programs that write their operands only in place (-i): their options that take the next word, and those whose value
# is the script, so that the first operand is a file and not the script.
IN_PLACE = {"sed": ({"-e", "--expression", "-f", "--file", "-l", "--line-length"}, {"-e", "--expression", "-f", "--file"}),
            "perl": ({"-e", "-E", "-I", "-l", "-0"}, {"-e", "-E"})}
# A brace that expands, {a,b} or {1..9}: the hook reads each word it gives, up to BRACE_MOST of them; past that, a
# range of digits as a digit and any other brace as a wildcard.
# Up to the first comma or `..` no other one is read, so the match cannot backtrack across them (SonarCloud S8786).
BRACE = re.compile(r"\{(?:[^{},.]|\.(?!\.))*(?:,|\.\.)[^{}]*\}")
NUMBERS = re.compile(r"\{-?\d+\.\.-?\d+(?:\.\.-?\d+)?\}")
RANGE = re.compile(r"^(-?\d+|[a-zA-Z])\.\.(-?\d+|[a-zA-Z])(?:\.\.(-?\d+))?$")
BRACE_MOST = 64
LOOP_MOST = 256     # paths a loop variable is read as, at most
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


class Spent(Exception):
    """The budget for reading the command ran out."""


def _budget(seconds: float):
    """A function that raises Spent once `seconds` from now have passed: called as the reading goes."""
    until = time.monotonic() + seconds

    def spend():
        if time.monotonic() > until:
            raise Spent()
    return spend


class Reader:
    """Runs git and gh for one check, all of it within one deadline."""

    def __init__(self, env: dict, seconds: float):
        self.env, self.until = env, time.monotonic() + seconds

    def run(self, program: str, args: list, where, allowed=()) -> str:
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
        if done.returncode not in (0,) + tuple(allowed):
            first = (done.stderr.strip().splitlines() or ["exit %d" % done.returncode])[0]
            raise Unreadable("`%s %s` failed in %s: %s" % (program, args[0], where, first))
        return done.stdout

    def config(self, where, args: list) -> str:
        """What `git config` says in `where`: "" when nothing is set. Raises Unreadable when git cannot say."""
        return self.run("git", ["config"] + args, where, allowed=(1,))


def _join(here, path: str):
    """Where `cd path` or `git -C path` leads from `here`; None when it cannot be told from the words."""
    if here is None or "$" in path or "`" in path or (path.startswith("~") and not re.match(r"~(/|$)", path)):
        return None     # a directory the hook cannot tell stays one, whatever follows (an absolute path among it)
    return here / os.path.expanduser(path)


# What cd is given that goes where cd - goes: the shell's previous directory.
PREVIOUS = {"-", "~-", "$OLDPWD", "${OLDPWD}"}


def _directory(words: list):
    """The directory cd or pushd (words[0]) goes to, past its options: `~` for none, and `.` for an empty one, where
    the shell stays. None where the shell takes it from a stack the hook does not keep (decision 0032): popd, pushd
    with no directory or with +N or -N, and cd - (~-, $OLDPWD) or cd +N."""
    args, options = words[1:], []
    while args and re.fullmatch(r"-[A-Za-z@]+", args[0]):
        options, args = options + [args[0]], args[1:]
    if words[0] in ("pushd", "popd") and any("n" in option for option in options):
        return "."      # -n changes the stack, never the directory

    args = args[1:] if args[:1] == ["--"] else args
    if words[0] == "popd" or (words[0] == "pushd" and not args):
        return None
    if not args:
        return "~"
    if args[0] in PREVIOUS or re.fullmatch(r"[+-]\d+", args[0]):
        return None
    return args[0] or "."


ALIAS_MOST = 256    # aliases read in one command, at most: past it, the command is one the hook cannot read
PLACES_MOST = 64    # directories a command may stand in, at most: past it, where it stands cannot be read


def _unaliased(commands: list, table: dict, seen: frozenset = frozenset(), budget: list = None, spend=None) -> list:
    """`commands`, as shell.commands(marked=True) gives them, with each alias the command defines (`table`, from
    shell.alias_values: name to the text of each value it is given, or None where it is unaliased) read as the shell
    expands it, as text in place of its name where its name stands as the program: the words before the name, the
    value's text, the words after the name and the command's redirections, each word quoted as itself, read again as
    commands (issue 174). So an empty value makes the next word the program, and a value that ends in `;`, `&&` or a
    newline makes what follows a command of its own; an alias for xargs, a shell, source or eval is read as that
    program, and a script it is given as commands of its own (decision 0032). A name given more than one value, or
    unaliased, is read as each, and as itself, wherever it runs: the hook does not order definitions. A value that ends
    in a blank makes the next word an alias too; an alias already read in a command is not read again. Past
    ALIAS_MOST aliases read, it raises Unreadable; a text that cannot be split raises ValueError."""
    budget = [ALIAS_MOST] if budget is None else budget
    out = []
    for words, redirections in commands:
        at, _ = shell.past_prefixes(words or [])
        name = words[at] if words and at is not None and at < len(words) else None
        if name not in table or name in seen:       # a SCOPE mark, too
            out.append((words, redirections))
            continue
        for value in _alias(table, name, budget):
            if value is None:       # where the name is not an alias, it runs as itself
                out.append((words, redirections))
                continue
            tail, read = words[at + 1:], seen | {name}
            while value[-1:] in (" ", "\t") and tail[:1] and tail[0] in table and tail[0] not in read:
                # A value that ends in a blank makes the next word an alias too, in bash and zsh.
                following = _alias(table, tail[0], budget)
                if len(following) > 1 or following[0] is None:
                    raise Unreadable("an alias after one whose value ends in a blank is one the hook cannot place")
                value, tail, read = value + following[0], tail[1:], read | {tail[0]}
            # A here-document's body is data, and is not spliced: the operator alone would wait for one.
            spliced = [shell.requoted(w) for w in words[:at]] + [value] + [shell.requoted(w) for w in tail] + [
                "%s %s" % (operator, shell.requoted(target)) for operator, target in redirections
                if not re.fullmatch(r"<<-?", operator)]
            out += _unaliased(shell.commands(" ".join(spliced), spend, marked=True), table, read, budget, spend)
    return out


def _evaluated(commands: list, spend, table: dict = None) -> list:
    """`commands`, as shell.commands(marked=True) gives them, each followed by what the substitutions a quote held in its
    words run, where a program may run them later: in a command that only assigns (x='$(...)', read by eval or $((x))),
    or given to a program that is not git, gh or one of TEXT_ONLY (trap '$(...)' EXIT). A commit message, a pull
    request's body, grep, echo and printf keep them as text (issue 174). What they run is read with the command's
    aliases (`table`, shell.alias_values) read in it, as _unaliased reads them. Raises ValueError when one cannot be
    split and, its quotes and backslashes taken out, names git or gh, or its aliases cannot be read."""
    out = []
    for words, redirections in commands:
        out.append((words, redirections))
        plain = [shell.unmarked(w) for w in words or []]
        at = _program(plain)
        if not plain or not (all(ASSIGNMENT.match(w) for w in plain) or (
                at is not None and os.path.basename(plain[at]) not in TEXT_ONLY | {"git", "gh"})):
            continue
        for script in [script for word in words for script in shell.held(word)]:
            try:
                read = shell.commands(script, spend, marked=True)
            except ValueError:
                # Most are text a quote holds, sed's code spans among them: one that cannot be split is refused only
                # when, its quotes and backslashes taken out, it names git or gh.
                if shell.GIT_OR_GH.search(re.sub(r"[\\'\"]", "", script)):
                    raise
                continue
            try:
                read = _unaliased(read, table, spend=spend) if table else read
            except Unreadable as err:
                raise ValueError(str(err)) from None
            out += _evaluated(read, spend, table)
    return out


def _alias(table: dict, name: str, budget: list) -> list:
    """The text of each value `name` is given, or None where it is unaliased; each one alias read of the budget."""
    out = []
    for each in table[name]:
        budget[0] -= 1
        if budget[0] < 0:
            raise Unreadable("the command reads more than %d aliases, which the hook does not read" % ALIAS_MOST)
        out.append(each)
    return out


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


def _calls(commands: list, cwd, text: str, env: dict = None, spend=None) -> tuple:
    """(calls, always, inline). A call is (tool, directory, words after the tool's options, kind).

    `commands` are shell.commands's: (words, [(operator, target)]). `always` refuses whatever the command does: what
    cannot be read. `inline` refuses only a command that commits, pushes or writes: an identity set in the command
    itself, or a write into git's directory. `text` is the command as the shell reads it, and `env` the hook's own
    environment, whose PATH names the git and gh it reads. `spend`, called as the reading goes, raises Spent once its
    budget is gone.
    """
    spend = spend or _budget(READ_SECONDS)
    here = pathlib.Path(cwd) if cwd else None
    places, stood = [here], [here]  # where a relative write may land, and every directory the command has stood in
    values, present, branches = shell.environment(text)     # what the command leaves in the environment, fail-closed
    calls, always, inline = [], [], []
    blind = _redefined(text)        # a git the command may redefine is one the hook cannot read (decision 0024)
    if shell.aliased(_quoted(shell.without_heredocs(text)), REDEFINABLE):
        always.append(("command_unreadable", "the command defines an alias whose value runs git, gh or what runs them "
                                             "(decision 0030)"))
    table = {}
    try:
        table = shell.alias_values(_quoted(shell.without_heredocs(text)), spend)
        commands = _unaliased(commands, table, spend=spend)
    except (Unreadable, ValueError) as err:
        always.append(("command_unreadable", "the command's aliases cannot be read (%s)" % err))
    # After the aliases, so that an alias for trap or eval is read as the program it runs.
    commands = _evaluated(commands, spend, table)
    # Each command's words as the shell gives them, and as shell.commands marked them, which only _bare reads.
    commands = [(None, redirections, None) if marked is None else (
        [shell.unmarked(w) for w in marked], [(op, shell.unmarked(t)) for op, t in redirections], marked)
        for marked, redirections in commands]
    scoped = []     # where the command stood when each subshell it is in began
    loops = _loops([c[:2] for c in commands if c[0] is not None], values)
    for raw, redirections, marked in commands:
        spend()
        if raw is None:     # a case pattern's substitution runs in a subshell: a cd in it is its own (shell.SCOPE)
            if (raw, redirections) == shell.SCOPE[0]:
                scoped.append((here, places, stood))
            elif scoped:
                here, places, stood = scoped.pop()
            continue
        # A word is read with what the command set unconditionally put in for each variable it holds.
        words, targets = [expand(w, values) for w in raw], [expand(t, values) for _, t in redirections]
        # A path written is read with what the command set put in, but where a zsh modifier or a subscript follows the
        # variable ($f:r, $f[1]): _git_directory reads those, and ${f%.py}, as a wildcard.
        inline += _git_directory([written(t, values) for op, t in redirections if ">" in op], places, "a redirection",
                                 loops, spend)
        inline += [("identity_set_in_command", "%s is set in the command; the hook reads only what is configured"
                    % w.split("=")[0]) for w in words if ENVIRONMENT.match(w)]
        inline += [("identity_set_in_command", "the command touches git's configuration (%s); change it in a command "
                                               "of its own" % w) for w in words + targets if GIT_CONFIG_FILE.search(w)]
        if not words:
            continue
        if raw[0] in ("cd", "pushd", "popd"):
            target = _directory(words)
            # The hook keeps no stack: where the shell takes the directory from one, the command may stand in any
            # directory it has stood in, and what it writes or commits is read in each (decision 0032).
            places = list(dict.fromkeys(stood if target is None else [_join(place, target) for place in places]))
            stood = list(dict.fromkeys(stood + places))
            if len(stood) > PLACES_MOST:    # cd - then a relative cd doubles them: past the most, the directory is lost
                inline.append(("directory_unreadable", "the command may stand in more directories than the hook reads "
                                                       "(%d); give each a plain path" % PLACES_MOST))
                places = stood = [None]
            here = places[0] if len(places) == 1 else None
            continue
        runs = _program(words)      # past reserved words, prefixes and wrappers: time bash, if sh, nice sh
        at = runs if runs is not None and os.path.basename(words[runs]) in ("git", "gh") else None
        start = runs if runs is not None else 0
        program = os.path.basename(words[start])
        if at is None and program in DATA_HEADS:
            continue        # a loop's word list is data: what its body runs is a command of its own
        inline += _git_directory(_written(program, [written(w, values) for w in raw[start + 1:]]), places, program,
                                 loops, spend)
        local = _local(words, at)
        named = present | local     # the environment git runs with: persisted, and set for it alone
        if local & {"PATH", "path"}:
            blind.append("the command sets PATH, so git or gh may be another program")
        if program in SHELLS_AND_SOURCE and not _given_c(words[start + 1:]):
            blind.append("a shell reads a script the hook cannot see")
        runner = _runner(words, at, here, env or {})
        if runner:
            blind.append(runner)
            if at is None and set(words[1:]) & (WRITES | GH_WRITES):
                always.append(("command_unreadable", "%s, and it is given a commit or a push" % runner))
        if at is None:
            # A substitution is read as a command of its own below; its text is not the wrapper's to read as a push.
            if program not in TEXT_ONLY and WRITE_TEXT.search(" ".join(_bare(expand(w, values)) for w in marked)):
                always.append(("command_unreadable", "`%s` looks like a commit or push the hook cannot read as one"
                               % program))
            continue
        tool, rest, before = os.path.basename(words[at]), words[at + 1:], words[:at]
        wheres, i, settings = places, 0, []
        while i < len(rest) and rest[i].startswith("-"):
            option, given, value = rest[i].partition("=")
            if option in (GIT_VALUED if tool == "git" else GH_VALUED) and not given:
                i += 1
                value = rest[i] if i < len(rest) else ""
            i += 1
            if tool != "git":
                continue
            if option == "-C":
                wheres = list(dict.fromkeys(_join(where, value) for where in wheres))
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
            if sub == "push" and wheres == places:    # the branch the shell is on, where the push runs, is HEAD
                words = [sub] + [_branch_word(w, values, branches) for w in words[1:]]
            for option, value in settings:
                always += _setting(option, value)
                if PUSH_KEYS.match(value.partition("=")[0].strip()):     # read from configuration, never the command
                    inline.append(("identity_set_in_command", "git %s %s sets in the command where a push goes or what "
                                                              "it sends; set it in a command of its own"
                                   % (option, value.partition("=")[0])))
            always += _programs(sub, words[1:])
            if PROGRAM_ENVIRONMENT & named or remote_helper(sub, rest, words[1:]):
                always.append(("command_unreadable", "the command sets where git finds a program it runs, or lets a "
                                                     "transport run one, which the hook cannot read"))
            if sub in TAKES_REMOTE and any(_expands(w) for w in remotes(sub, words[1:])):
                always.append(("command_unreadable", "a remote is held in a variable or a command the hook cannot "
                                                     "read"))
            kind = ("push" if sub == "push" else "commit") if sub in WRITES else ""
            if not sub and set(map(os.path.basename, before)) & shell.FEEDERS:
                always.append(("git_command_unknown", "git is given no command but what xargs or parallel feeds it "
                                                      "from its input, which the hook cannot read"))
            elif sub and sub not in WRITES | RUNNERS | OTHERS:
                always.append(("git_command_unknown", "git %s is not a command the hook knows; it may be an alias, "
                                                      "which the hook cannot read" % sub))
            elif sub in RUNNERS and WRITE_TEXT.search(" ".join(words)):
                always.append(("command_unreadable", "git %s runs a command the hook cannot read" % sub))
        else:
            kind = _gh_kind(words)
        calls += [(tool, where, words, kind) for where in wheres]
    said = " ".join(w for words, _, _ in commands for w in words or [])     # as the shell runs it: g''it push is git push
    if blind and (WRITE_TEXT.search(text) or WRITE_TEXT.search(said) or any(kind for _, _, _, kind in calls)):
        always += [("command_unreadable", "%s, in a command that names a commit or push" % why)
                   for why in dict.fromkeys(blind)]
    return calls, always, inline


def _redefined(text: str) -> list:
    """Why git or gh, as the command runs it, may not be the program on the hook's PATH (decision 0024): the command
    defines a function or an alias (or hashes a path) for git, gh or a word that runs them, in its text or in a script
    it runs; or it sets PATH, anywhere, or for git alone. Each is a reason; none is an empty list."""
    reasons, quoted = [], _quoted(shell.without_heredocs(text))
    if shell.defined(quoted) & REDEFINABLE:
        reasons.append("the command defines a function or an alias for git, gh or what runs them")
    if shell.sets("PATH", quoted) or shell.sets("path", quoted):
        reasons.append("the command sets PATH, so git or gh may be another program")
    if any(shell.sets(name, quoted) for name in sorted(LOADER_VARIABLES)):     # as PATH is: spelt however
        reasons.append("the command sets a dynamic linker's variable, so git or gh may run other code")
    if "*" in shell.touched(text):
        reasons.append("the command writes a variable it names at run time, or evals or sources, which may set PATH")
    return reasons


def _git_directory(paths: list, places: list, given: str, loops: dict, spend=lambda: None) -> list:
    """Why a command that commits or pushes is refused for writing into git's directory (decision 0030): each of
    `paths`, the places a redirection or a program of PATH_WRITERS writes, that has a component naming `.git`, as it is
    written or once resolved against each of `places`, where the hook tracks the command through cd (decision 0032):
    `..` and links taken out, in any case, a wildcard or a brace that may expand to it, and a loop's variable read as
    each word the loop runs over, or, past LOOP_MOST of them, refused. A path the hook cannot expand is left alone, so
    that `git push > "$TMPDIR/log"` passes. A variable the hook reads (`loops`), in an expansion it does not read as
    plain (`${f%.py}`, `${f:-x}`, `${!f}`), may be anything, a leading dot included (issue 174)."""
    found = []
    for written in paths:
        written, wild = _wildcarded(written, loops)     # before a variable is put in, where it stands with an operator
        hits, bound = False, _bound(written, loops)
        if bound is None:
            found.append(("git_directory_written", "%s writes a path through a loop's variable, and the loop runs over "
                                                   "more words than the hook reads (%d), so where it writes cannot be "
                                                   "read; make the write in a command of its own" % (given, LOOP_MOST)))
            continue
        for unbraced in bound:
            if not unbraced or _expands(unbraced):
                continue
            expanded, exact = _braced(unbraced)
            exact = exact and not wild
            for path, here in [(p, h) for p in expanded for h in places]:
                spend()
                path = os.path.expanduser(path)
                seen = [os.path.normpath(path)]
                if here is not None or os.path.isabs(path):
                    joined = os.path.normpath(os.path.join(str(here or ""), path))
                    seen += [joined, os.path.realpath(joined)]
                parts = [part for each in seen for part in each.split(os.sep)]
                hits = hits or any(_names_git(part) if exact else _globbed(part.casefold()) for part in parts)
        if hits:
            found.append(("git_directory_written", "%s writes a path in git's directory, which may change what git "
                                                   "runs or where a push goes; make the write in a command of its own"
                          % given))
    return found


def _names_git(part: str) -> bool:
    """Whether one component of a path, its braces expanded, may name git's directory, in any case: `.git`, or a
    wildcard the shell may expand to it (.gi?, .g*, .gi[t]). A wildcard matches a leading dot only when the dot is
    written, as the shell's does."""
    part = part.casefold()
    return part == GIT_DIRECTORY or bool(re.search(r"[*?\[]", part) and part.startswith(".") and _globbed(part))


def _braced(path: str) -> tuple:
    """(the paths the brace expansions in `path` give, whether they are exact). Past BRACE_MOST, one path in which a
    range of digits stands for a digit, which .git holds none of, and any other brace for a wildcard, which may be
    anything, even a leading dot: not exact."""
    names = _expansions(path)
    if names is not None:
        return names, True
    while NUMBERS.search(path):
        path = NUMBERS.sub("0", path)
    while BRACE.search(path):
        path = BRACE.sub("*", path)
    return [path], False


def _globbed(pattern: str) -> bool:
    """Whether a shell pattern for one name matches `.git`, read in one pass: each place of `.git` the pattern may have
    reached so far, a * taking any number of letters, so that no run of stars backtracks (issue 174). It stops where
    no place is reached: a [ that never closes is a letter .git does not hold, so no later [ is read to the end again
    (quadratic)."""
    reached, i, last = {0}, 0, len(GIT_DIRECTORY)
    while i < len(pattern) and reached:
        c, bracket = pattern[i], _bracket(pattern, i) if pattern[i] == "[" else None
        if c == "*":
            reached = set(range(min(reached), last + 1))
        else:
            one = "." if c == "?" else bracket[0] if bracket is not None else re.escape(c)
            reached = {at + 1 for at in reached if at < last and re.fullmatch(one, GIT_DIRECTORY[at], re.S)}
            i = bracket[1] - 1 if bracket is not None else i
        i += 1
    return last in reached and i >= len(pattern)


# A POSIX class in a bracket expression, as the letters and the dot of `.git` it holds, in any case (decision 0032).
CLASSES = {"alpha": "a-z", "alnum": "a-z", "lower": "a-z", "upper": "a-z", "word": "a-z", "graph": "a-z.",
           "print": "a-z.", "punct": ".", "xdigit": "a-f", "digit": "", "space": "", "blank": "", "cntrl": ""}


def _bracket(pattern: str, i: int):
    """(a regular expression for the bracket expression that starts at pattern[i], the index past it), as the shell
    reads one: `!` or `^` negates it, a `]` first is a letter, a range stays a range (.gi[s-u]), and a POSIX class
    ([:alpha:]) is the letters it holds. One the hook cannot read, an unknown class, an equivalence class or a collating
    symbol, or a range it cannot order, may match anything: `.`. None when it never closes, and `[` is a letter."""
    j = i + 1 + (pattern[i + 1:i + 2] in ("!", "^"))
    negated, items, unread, first = j > i + 1, [], False, j
    while j < len(pattern):
        c = pattern[j]
        if c == "]" and j > first:
            if unread or not "".join(items):
                return "." if unread or negated else "(?!)", j + 1      # (?!) matches nothing
            return "[%s%s]" % ("^" if negated else "", "".join(items)), j + 1
        if c == "[" and pattern[j + 1:j + 2] in (":", "=", "."):
            end = pattern.find(pattern[j + 1] + "]", j + 2)
            if end < 0:
                return None
            name = pattern[j + 2:end]
            unread = unread or pattern[j + 1] != ":" or name not in CLASSES
            items.append(re.escape(CLASSES.get(name, "")).replace("\\-", "-"))
            j = end + 2
        elif pattern[j + 1:j + 2] == "-" and pattern[j + 2:j + 3] not in ("", "]"):
            low, high = c, pattern[j + 2]
            unread = unread or low > high
            items.append("%s-%s" % (re.escape(low), re.escape(high)))
            j += 3
        else:
            items.append(re.escape(c))
            j += 1
    return None


def _expansions(word: str, most: int = None):
    """Each word the brace expansions in `word` give, as bash expands them: {a,b}, nested, and {1..9}, {1..9..2} or
    {a..e}; a brace that is neither is left as it stands. None when they would be more than `most` (BRACE_MOST)."""
    most = BRACE_MOST if most is None else most
    out, todo = [], [word]
    while todo:
        each = todo.pop()
        found = _first_brace(each, most)
        if found is None:
            out.append(each)
        elif found[2] is None:
            return None
        else:
            start, end, alternatives = found
            todo += [each[:start] + alternative + each[end:] for alternative in alternatives]
        if len(out) + len(todo) > most:
            return None
    return out


def _first_brace(word: str, most: int):
    """(where the first brace expansion in `word` starts, where it ends, what it expands to, None when that is more
    than `most`), or None when `word` holds none."""
    start = word.find("{")
    while start >= 0:
        depth, i, commas = 0, start, []
        while i < len(word):
            if word[i] == "\\":
                i += 1
            elif word[i] == "{":
                depth += 1
            elif word[i] == "}":
                depth -= 1
                if not depth:
                    break
            elif word[i] == "," and depth == 1:
                commas.append(i)
            i += 1
        if i >= len(word):
            return None
        body = word[start + 1:i]
        if commas:
            cuts = [start] + commas + [i]
            return start, i + 1, [word[a + 1:b] for a, b in zip(cuts, cuts[1:])]
        ranged = RANGE.match(body)
        if ranged:
            low, high, step = ranged.group(1), ranged.group(2), abs(int(ranged.group(3) or 1)) or 1
            if low.isalpha() != high.isalpha():
                pass
            elif low.isalpha():
                a, b = ord(low), ord(high)
                if abs(b - a) // step + 1 > most:
                    return start, i + 1, None
                return start, i + 1, [chr(c) for c in range(a, b + (1 if b >= a else -1), step if b >= a else -step)]
            else:
                a, b = int(low), int(high)
                if abs(b - a) // step + 1 > most:
                    return start, i + 1, None
                return start, i + 1, [str(n) for n in range(a, b + (1 if b >= a else -1), step if b >= a else -step)]
        start = word.find("{", start + 1)
    return None


def _bound(path: str, loops: dict):
    """`path` with each loop variable it holds put in, as each word its loop runs over: a loop's word list is data to
    read as commands, but its words are what the variable holds in the body. None when they are more than LOOP_MOST:
    a reading the hook would cut short is one it cannot read (decision 0032)."""
    out = [path]
    for name, words in loops.items():
        held, bound = re.compile(r"\$(?:\{%s\}|%s(?!\w))" % (re.escape(name), re.escape(name))), []
        for each in out:
            bound += [held.sub(lambda _, w=word: w, each) for word in words] if held.search(each) else [each]
        if len(bound) > LOOP_MOST:
            return None
        out = bound
    return out


# A variable with zsh's modifier or a subscript after it, unbraced: $f:r, $f:t:r, $f[1,4].
UNBRACED = re.compile(r"\$([A-Za-z_]\w*)(?:(\[)|(?::[A-Za-z&])+)")


def _wildcarded(path: str, names) -> tuple:
    """(`path` with each expansion of a variable of `names` that is not plain, ${f%.py}, ${f:-x}, ${!f}, ${#f} and the
    rest, made a wildcard that may be anything, as a brace past BRACE_MOST is; whether one was). Reading each operator
    is a list without end (issue 174)."""
    out, i, wild = [], 0, False
    while i < len(path):
        bare = UNBRACED.match(path, i)
        if bare and bare.group(1) in names:     # zsh's $f:r and $f[1,4]: its modifiers, or its subscript
            end = path.find("]", bare.end()) + 1 or len(path) if bare.group(2) else bare.end()
            out.append("*")
            wild, i = True, end
            continue
        if not path.startswith("${", i):
            out.append(path[i])
            i += 1
            continue
        end = shell._balanced(path, i + 2, "}")
        body = path[i + 2:end - 1] if path[end - 1:end] == "}" else None
        named = re.match(r"(?:\([^()]*\))*[!#~=^+]*([A-Za-z_]\w*)", body or "")      # zsh's ${(L)f}, ${~f}
        if named and named.group(1) in names and body != named.group(1):
            out.append("*")
            wild = True
        else:
            out.append(path[i:end])
        i = end
    return "".join(out), wild


def _loops(commands: list, values: dict) -> dict:
    """{name: the words a for or select loop over it runs over, the variables the command set put in}, and each
    variable the command set to a plain value, as that value: the variables the hook reads. A loop with no `in` runs
    over the positional parameters, which the hook cannot read."""
    loops = {name: [value] for name, value in values.items()}
    for words, _ in commands:
        rest = words
        while rest and rest[0] in shell.NEUTRAL | shell.CLOSERS | {"if", "while", "until", "{"}:
            rest = rest[1:]
        if rest[:1] in (["for"], ["select"]) and len(rest) > 1:
            listed = rest[3:] if rest[2:3] == ["in"] else ["$@"]
            loops.setdefault(rest[1], []).extend(expand(w, values) for w in listed)
    return loops


def _written(program: str, args: list) -> list:
    """The paths `program`, given `args`, writes: by PATH_WRITERS, an option of its that names one (`-t DIR`,
    `--target-directory=DIR`, `-fFILE`, a bundle ending in one), and dd's of=; by IN_PLACE, sed's and perl's files when
    -i is given. Any other program writes none of its words."""
    if program == "dd":
        return [w[3:] for w in args if w.startswith("of=")]
    if program in IN_PLACE:
        valued, scripts = IN_PLACE[program]
        operands, _, given = _options(args, valued, set())
        if not any(o == "-i" or shell.spelt(o, "--in-place") for o in given):
            return []
        return operands if set(given) & scripts else operands[1:]
    if program not in PATH_WRITERS:
        return []
    which, valued, destinations, stands = PATH_WRITERS[program]
    if program in TARS:     # GNU tar's options and bsdtar's take different words (-H, -s): each reading is read
        written = _tar(args, valued, destinations, stands) + _tar(args, TAR_BSD_VALUED, destinations, stands)
        return list(dict.fromkeys(written))
    operands, named, given = _options(args, valued, destinations)
    if which == "last" and set(given) & TARGET:
        return named        # -t names the destination: every operand is a source
    if program == "wget":       # -e's wgetrc command: what follows its = is a place written, under any key (issue 174)
        named += [value.partition("=")[2].strip() for value in _options(args, valued - WGET_EXECUTE, WGET_EXECUTE)[1]]
    if program in STDOUT_DASH:      # curl -o - and wget -O - write the standard output; --output-dir - is a directory
        directories = _options(args, (valued | destinations) - STDOUT_DASH[program], STDOUT_DASH[program])[1]
        named = [path for path in named if path != "-"] + [path for path in directories if path == "-"]
    written = named + {"last": operands[-1:], "all": operands, "first": operands[:1], "none": []}[which]
    if stands is not None:
        needs, names = stands
        if (not needs or _gave(given, needs)) and not _gave(given, names) and written == named:
            written.append(HERE)        # its words name no output: it writes where it stands
    return written


def _tar(args: list, valued: set, destinations: set, stands: tuple) -> list:
    """The places tar writes, by its mode: -C's directory when it extracts, or where it stands when it extracts with no
    -C; -f's archive when it creates or changes one; and -g's snapshot always. Creating, -C names where it reads, and
    listing or comparing, -f the archive it reads. In a mode the hook does not know, every place it names. A first word
    with no dash, all letters, is read as tar reads it (_old_style)."""
    takes = valued | destinations
    if args and re.fullmatch(r"[A-Za-z]+", args[0]):
        args = _old_style(args, takes)
    given = _options(args, valued, destinations)[2]

    def values(options: set) -> list:
        return _options(args, takes - options, options)[1]
    extracts, changes = _gave(given, TAR_EXTRACTS), _gave(given, TAR_CHANGES)
    if not (extracts or changes or _gave(given, TAR_READS)):
        extracts = changes = True
    directories = values({"-C", "--directory"})
    needs, names = stands
    here = [HERE] if _gave(given, needs) and not _gave(given, names) else []     # it writes where it stands
    archives = [path for path in values({"-f", "--file"}) if path != "-"]      # tar -f - writes the standard output
    # --one-top-level[=DIR], by any prefix getopt takes, is where tar extracts, under -C: DIR, or the archive's name
    # with its suffixes taken off (issue 174).
    tops = [given_value if attached else TAR_SUFFIX.sub("", os.path.basename(archive))
            for option, attached, given_value in (word.partition("=") for word in args if word[:2] == "--")
            if shell.spelt(option, "--one-top-level") for archive in ([None] if attached else archives)]
    tops = [os.path.join(base, top) for base in directories or [""] for top in tops] if extracts else []
    return ((directories if extracts else []) + here + tops + (archives if changes else []) +
            values({"-g", "--listed-incremental"}))


def _gave(given: list, options: set) -> bool:
    """Whether a program was given one of `options`: a long one by any prefix getopt takes."""
    return any(shell.spelt(option, name) for option in given for name in options)


def _old_style(args: list, takes: set) -> list:
    """tar's words with its first, a bundle with no dash, read as tar reads it: each letter an option, and each that
    takes a value takes the next word in turn, so `tar xfC h.tar .git` is `tar -x -f h.tar -C .git`."""
    out, rest = [], list(args[1:])
    for letter in args[0]:
        out.append("-" + letter)
        if "-" + letter in takes and rest:
            out.append(rest.pop(0))
    return out + rest


def _options(args: list, valued: set, destinations: set) -> tuple:
    """(operands, the values of the options of `destinations`, every option given) of a program's words, as getopt
    reads them: a long option by any prefix, its value attached by `=` or the next word; a bundle of short ones, which
    ends at its first that takes a value, what follows it in the bundle, or the next word, being that value; `--`."""
    operands, named, given, i, takes = [], [], [], 0, valued | destinations
    while i < len(args):
        word = args[i]
        if word == "--":
            operands += args[i + 1:]
            break
        if word.startswith("--"):
            option, attached, value = word.partition("=")
            option = next((o for o in sorted(takes) if o.startswith("--") and shell.spelt(option, o)), option)
            given.append(option)
            if option in takes and not attached:
                i += 1
                value = args[i] if i < len(args) else ""
            if option in destinations:
                named.append(value)
        elif word.startswith("-") and word != "-":
            for at, letter in enumerate(word[1:], 1):
                given.append("-" + letter)
                if "-" + letter in takes:
                    value = word[at + 1:]
                    if not value:
                        i += 1
                        value = args[i] if i < len(args) else ""
                    if "-" + letter in destinations:
                        named.append(value)
                    break
        else:
            operands.append(word)
        i += 1
    return operands, named, given


def _given_c(args: list) -> bool:
    """Whether a shell's own options, the words before its first operand, hold -c: alone or bundled before an option
    that takes a value (-lc, -ec, -co). A word past them is the script or its arguments (bash x.sh -c). -o, +o, -O and
    +O take a value: the rest of their bundle where one is attached (-oemacs), else the next word; so do bash's
    --rcfile and --init-file. A value is never read as flags (issue 181)."""
    i = 0
    while i < len(args) and args[i][:1] in ("-", "+") and args[i] not in ("-", "--"):
        word = args[i]
        if word[1:2] == "-":        # a long option: bash's --rcfile and --init-file take the next word, no other does
            i += 2 if word in ("--rcfile", "--init-file") else 1
            continue
        flags = word[1:]
        valued = re.search("[oO]", flags)
        if word[0] == "-" and "c" in (flags[:valued.start()] if valued else flags):
            return True
        i += 2 if valued and valued.end() == len(flags) else 1
    return False


def _program(words: list):
    """The index of the program a simple command runs: past its assignments, prefixes and the wrappers of
    shell.WRAPPED, as shell.py reads them for both hooks. Any other program runs itself, whatever its words say: git
    given to gitleaks is a word. None when it runs none (command -v)."""
    at, _ = shell.past_prefixes(words)
    while at is not None and at < len(words) and os.path.basename(words[at]) in shell.WRAPPED:
        at, _ = shell.past_prefixes(words, shell.past_wrapper(words, at, os.path.basename(words[at]))[0])
    return at if at is not None and at < len(words) else None


def _runner(words: list, at, here, env: dict) -> str:
    """Why what runs the git or gh at index `at` (None: the command runs neither) cannot be read, or "" when it can.

    Past reserved words and assignments, only the prefixes and wrappers of shell.AS_IS may run it: env with assignments
    only, command with no option. A program held in a variable or a command the hook cannot read may be git, and git or
    gh named by a path is read only when it is the file on the hook's PATH. Any other program runs itself: git given to
    it as a word is data."""
    if at is None:
        program = _program(words)
        return ("a program is held in a variable or a command the hook cannot read"
                if program is not None and _expands(words[program]) else "")
    at_, passed = shell.past_prefixes(words)
    while at_ is not None:
        for name, options in passed:
            if name not in shell.RESERVED and (name not in shell.AS_IS or (name == "command" and options)):
                return "git or gh may run under %s, which the hook does not read" % (
                    name if name in shell.PREFIXED else "a prefix")
        if at_ >= len(words):
            return ""
        word = words[at_]
        if at_ == at:
            return "" if "/" not in word or _on_path(word, here, env) else (
                "git or gh is named by a path to another file than the one on the hook's PATH")
        name = os.path.basename(word)
        if name not in shell.AS_IS:     # a wrapper _program stepped past to reach git
            return "git or gh may run under a program the hook does not read as a wrapper"
        if "/" in word and not _on_path(word, here, env):
            return "git or gh runs under a wrapper named by a path to another file than the one on the hook's PATH"
        past, _ = shell.past_wrapper(words, at_, name)
        if name == "env" and not all(ASSIGNMENT.match(w) or w == "--" for w in words[at_ + 1:past]):
            return "git or gh may run under env given more than assignments, which the hook does not read"
        at_, passed = shell.past_prefixes(words, past)
    return ""       # command -v names a program and runs none


def _on_path(word: str, here, env: dict) -> bool:
    """Whether a path names the file the hook's PATH finds by its name: the git or gh the hook reads."""
    found = shutil.which(os.path.basename(word), path=env.get("PATH", os.defpath))
    path = os.path.expanduser(word)
    if not os.path.isabs(path):
        if here is None:
            return False
        path = os.path.join(str(here), path)
    try:
        return found is not None and os.path.samefile(path, found)
    except OSError:
        return False


def _local(words: list, git) -> set:
    """The names this one command sets in the environment of the git or gh at index `git`: assignments before it, and
    those given to env or sudo, or, before git, to a wrapper that runs it (command env, nohup env, nice env). These
    are set for this command alone, so they are read here and not across the command; shell.environment reads the
    rest."""
    if git is None:
        return set()
    names, at = set(), 0
    while at < git and ASSIGNMENT.match(words[at]):
        names.add(words[at].split("=")[0])
        at += 1
    for i in range(at, git):
        first = os.path.basename(words[i])
        if first in SETS_LOCALLY or first in RUNS_GIT or first in shell.PREFIXES:
            names |= {w.split("=")[0] for w in words[i + 1:git] if ASSIGNMENT.match(w)}
            break
        break
    return names


def _bare(word: str) -> str:
    """`word`, as shell.commands(marked=True) gives it, with each substitution the shell runs, $(...) or `...`, taken
    out: its text is read as a command of its own. One a single quote or a backslash holds stays, as text (issue 174)."""
    out, last = [], 0
    for start, end, _ in shell.substitutions(word):
        out.append(word[last:start])
        last = end
    return shell.unmarked("".join(out) + word[last:])


def _branch_word(word: str, values: dict, branches: set) -> str:
    """A push refspec word that names the branch the shell is on, read as HEAD: the current-branch substitution, or a
    variable the command set to it. Otherwise the word, variables it holds put in."""
    whole = VARIABLE_WHOLE.match(word)
    if shell.CURRENT_BRANCH.match(word) or (whole and whole.group(1) in branches):
        return "HEAD"
    return expand(word, values)


def remote_helper(sub: str, words: list, given: list) -> bool:
    """Whether git is given a remote helper's URL: ext:: in any of its `words`, or <transport>::<address> in a word,
    or an option's value, that `given` to a command that takes a remote. A commit message or a pattern is not one."""
    if any("ext::" in w.casefold() for w in words):
        return True
    return sub in TAKES_REMOTE and any(REMOTE_HELPER.match(w.partition("=")[2] if w[:2] == "--" else w) for w in given)


# A variable as `expand` puts it in, but not where zsh's modifier or a subscript follows it.
PLAIN_VARIABLE = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*)(?![\w:\[]))")


def written(word: str, values: dict) -> str:
    """A word a writer is given, with each variable the command set to a plain value put in, as `expand` puts it in,
    but where zsh's modifier or a subscript follows it ($f:r, $f[1,4]): that one _wildcarded reads (issue 174)."""
    return PLAIN_VARIABLE.sub(lambda m: values.get(m.group(1) or m.group(2), m.group(0)), word)


def expand(word: str, values: dict) -> str:
    """The word with each variable the command set to a plain value put in; left as it is where a variable's value
    is not read, so that a word that still expands is treated as one the hook cannot read."""
    if "$" not in word:
        return word
    return VARIABLE.sub(lambda m: values.get(m.group(1) or m.group(2), m.group(0)), word)


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
    out, i, quote, braces = [], 0, None, 0     # braces: where a ${...} that began ends; a # in it begins no comment
    while i < len(text):
        c = text[i]
        if quote is None and text.startswith("${", i) and i >= braces:
            braces = shell._balanced(text, i + 2, "}")
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
            # A script of its own, whose quotes are its own: escaped, as below, so that shlex keeps the word whole.
            out.append("$(%s)" % text[i + 2:end].replace("\\", "\\\\").replace('"', '\\"'))
            i = end + 1
            continue
        elif quote == '"':
            quote = None if c == '"' else quote
        elif text.startswith("$'", i):      # $'...', in which a backslash escapes, \' among them
            end = shell.ansi_end(text, i + 2)
            if end is None:
                return text
            out.append(text[i:end])
            i = end
            continue
        elif c in "'\"":
            quote = c
        elif c == "#" and i >= braces and (i == 0 or text[i - 1] in " \t\n;&|("):
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
            if c == "`":    # in a backtick's script, \`, \$ and \\ are the character: `echo \`git push\`` runs git
                inner = re.sub(r"\\([\\`$])", r"\1", inner)
            # One double-quoted word holding $(inner): inside it shlex reads only \ and ", so escaping those keeps
            # inner's own quotes literal and the word intact, whatever inner holds.
            out.append('"$(%s)"' % inner.replace("\\", "\\\\").replace('"', '\\"'))
            i = end + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _closed(text: str, i: int, end: str):
    """Where the substitution whose body starts at i ends: its `)`, or its closing backtick; None if it never does. A
    `)` in a comment or in a parameter expansion (`${x/)/y}`) does not end it (decision 0032)."""
    depth, quote, start = 0, None, i
    while i < len(text):
        c = text[i]
        if quote == "'":
            quote = None if c == "'" else quote
        elif c == "\\":
            i += 1
        elif quote == '"' and c == '"':
            quote = None
        elif quote is None and text.startswith("$'", i):       # $'...', in which a backslash escapes
            i = shell.ansi_end(text, i + 2)
            if i is None:
                return None
            continue
        elif c in "'\"" and quote is None:
            quote = c
        elif text.startswith("${", i):
            i = shell._balanced(text, i + 2, "}") - 1
            if text[i:i + 1] != "}":
                return None
        elif end == ")" and quote is None and c == "#" and (i == start or text[i - 1] in " \t\n;&|()"):
            i = text.find("\n", i)      # a comment runs to the end of its line
            if i < 0:
                return None
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


def names_program(key: str, valued: bool, value: str) -> bool:
    """Whether a configuration key set to `value` (given at all, `valued`) names a program git runs: a helper key,
    but submodule.*.update only for a !cmd value, and none when it is set to nothing."""
    if not PROGRAM_KEYS.match(key):
        return False
    if valued and value == "":
        return False        # core.askpass= and the like set no program
    if SUBMODULE_UPDATE.match(key):
        return value.startswith("!")        # a built-in checkout/rebase/merge/none runs nothing
    return True


def _setting(option: str, value: str, keys: bool = True) -> list:
    """Why git's -c or --config-env `value` is refused: a variable the hook cannot read, what it reads from
    configuration (with `keys`), or a program git runs."""
    problems = []
    if "$" in value or "`" in value:
        return [("command_unreadable", "git %s is set from a variable or a command the hook cannot read" % option)]
    if keys and KEYS.match(value):
        problems.append(("identity_set_in_command", "git %s %s sets in the command what the hook reads from "
                                                    "configuration" % (option, value.split("=")[0])))
    key, valued, setting = value.partition("=")
    plain = option == "-c" and ((setting in PAGERS and not LOAD_KEYS.match(key)) or (
        SWITCHES.match(key) is not None and (not valued or setting.lower() in BOOLEANS)))
    if (names_program(key, bool(valued), setting) and not plain) or LOAD_KEYS.match(key):
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


def push_configuration(config) -> dict:
    """What git's configuration says of a push that names no refspec, or no remote, read in one call to `config`, which
    runs `git config` with the arguments it is given, as the hook that calls it runs git, and gives what it prints (""
    when nothing is set). git's own answer covers includes, scopes and worktrees. Every remote's keys are read, not only
    those of the remote git would pick:

    {"default": push.default, or None; "refspecs": each remote.*.push; "mirror": whether any remote.*.mirror is true;
     "remotes": the remotes configured, by a url or a pushurl; "pushdefault": each remote.pushDefault; "branches":
     {branch: {"pushremote": [...], "remote": [...]}}, which say where a push that names no remote goes}

    Raises Unreadable when a value is not one git takes."""
    read = {"default": None, "refspecs": [], "mirror": False, "remotes": set(), "pushdefault": [], "branches": {}}
    for entry in config(["-z", "--get-regexp", PUSH_READ]).split("\0"):
        if not entry:
            continue
        key, valued, value = entry.partition("\n")
        section, _, rest = key.partition(".")
        name, _, variable = rest.rpartition(".")
        if not valued and variable != "mirror":
            raise Unreadable("git's configuration sets %s with no value, which git does not take" % key)
        if key == "push.default":
            read["default"] = value     # the last one set is the one git reads
        elif key == "remote.pushdefault":
            read["pushdefault"].append(value)
        elif section == "branch" and variable in ("pushremote", "remote"):
            read["branches"].setdefault(name, {}).setdefault(variable, []).append(value)
        elif variable == "push":
            read["refspecs"].append(value)
        elif variable == "mirror":
            read["mirror"] = read["mirror"] or _boolean(value if valued else None, key)
        else:
            read["remotes"].add(name)
    return read


def _boolean(value, key: str) -> bool:
    """A boolean as git reads it: with no value, true; an integer, true unless zero. Raises Unreadable for any other."""
    if value is None or value.lower() in TRUE:
        return True
    if value.lower() in FALSE:
        return False
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value) != 0
    raise Unreadable("git's configuration sets %s to a value that is not a boolean" % key)


def _destination(read: dict, branch: str) -> str:
    """Where a push that names no remote goes, as git picks it from push_configuration's `read`: the branch's
    pushRemote, then remote.pushDefault, then the branch's remote, then origin; the last of each that is set. `branch`
    is the branch the push is made from, "" when HEAD is detached. "." is this repository. A value that is neither it
    nor a configured remote raises Unreadable."""
    own = read["branches"].get(branch, {}) if branch else {}
    named = next((values[-1] for values in (own.get("pushremote"), read["pushdefault"], own.get("remote")) if values),
                 None)
    if named is not None and named != LOCAL and named not in read["remotes"]:
        raise Unreadable("git's configuration sends a push that names no remote where no configured remote is")
    return "origin" if named is None else named


def _configured(read: dict) -> tuple:
    """(the refspecs a push that names none sends, whether it is a mirror), from push_configuration's `read`: each
    remote.*.push, of every remote, and what push.default sends, since a remote with none follows it. They are read as
    a refspec the command gives is, so one with a wildcard, or a negative one, refuses. A push.default git does not
    take raises Unreadable."""
    if read["default"] not in DEFAULT_SENDS:
        raise Unreadable("push.default is set to a value git does not take, so what the push sends cannot be read")
    return read["refspecs"] + [DEFAULT_SENDS[read["default"]]], read["mirror"]


def _commits(reader: Reader, where, args: list, refspecs: list, who: dict, mirror: bool = False) -> list:
    """Every commit the push would send that no remote has yet is the Maintainer's, as author and as committer. A
    refspec held in a variable or a command, or with a wildcard, the hook cannot read; a mirror sends every ref."""
    sources, matching = [], False
    for spec in refspecs:
        if spec in (":", "+:"):
            matching = True     # a matching refspec pushes every branch the two share: read them all
            continue
        source = (spec[1:] if spec.startswith("+") else spec).split(":")[0]
        if source.startswith("-"):      # never hand the hook's own git an option from the command
            raise Unreadable("the push names a refspec that starts with '-': %s" % spec)
        if source.startswith("^"):
            raise Unreadable("a refspec of the push is a negative one, which the hook does not read")
        if _expands(source):
            raise Unreadable("a refspec of the push is held in a variable or a command the hook cannot read")
        if WILDCARD.search(source):
            raise Unreadable("a refspec of the push has a wildcard, which the hook does not expand")
        if source:
            sources.append(source)
    options = [a.partition("=")[0] for a in args if a[:2] == "--"]
    given = [name for name in ("--mirror", "--all", "--branches", "--tags")
             if any(shell.spelt(option, name) for option in options)] + (["--mirror"] if mirror else [])
    if "--mirror" in given:     # every ref under refs/, refs/stash and refs/notes/* among them
        pseudo = ["--all", "--glob=refs/stash", "--glob=refs/notes/*"]
    else:
        pseudo = ["--branches"] if (matching or {"--all", "--branches"} & set(given)) else []
        pseudo += ["--tags"] if "--tags" in given else []
    shas = [reader.run("git", ["rev-parse", "--verify", "--end-of-options", source + "^{commit}"], where).strip()
            for source in sources or ([] if pseudo else ["HEAD"])]
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
    try:
        # What it sends, and where it goes, git's configuration says when the command does not: read once.
        read = push_configuration(lambda given: reader.config(where, given)) if remote is None or not refspecs else None
        if remote is None:
            branch = reader.run("git", ["symbolic-ref", "--quiet", "--short", "HEAD"], where, allowed=(1,)).strip()
            remote = _destination(read, branch)
    except Unreadable as err:
        return [("push_commits_unreadable", str(err))]
    if remote == LOCAL:
        return []       # this repository: nothing goes to GitHub
    problems = []
    try:
        problems += _remotes(reader, where, None if _expands(remote) else remote, who, machine)
    except Unreadable as err:
        problems.append(("account_unreadable", str(err)))
    if deleting:
        return problems
    try:
        mirror = False
        if not refspecs:
            refspecs, mirror = _configured(read)
        problems += _commits(reader, where, args, refspecs, who, mirror)
    except Unreadable as err:
        problems.append(("push_commits_unreadable", str(err)))
    return problems


def check(payload: dict, env: dict, seconds: float = DEADLINE) -> list:
    """The reasons to refuse this command, as (code, sentence); none when it may run."""
    if payload.get("tool_name") != "Bash":
        return []
    command = payload["tool_input"]["command"]
    # $(which git) and `command -v gh` stand for the git or gh on PATH, which a PATH set in the command would change.
    read = shell.WHICH.sub(lambda m: m.group(1) if os.path.basename(m.group(1)) in ("git", "gh") else m.group(0),
                           command)
    started, spend = time.monotonic(), _budget(min(READ_SECONDS, seconds))
    try:
        commands = shell.commands(_quoted(shell.without_heredocs(read)), spend, scopes=True, marked=True)
        calls, problems, inline = _calls(commands, payload.get("cwd"), read, env, spend)
    except ValueError as err:
        # The command cannot be split into words, so whatever it names, git may be among it under a spelling the hook
        # cannot see (issue 174).
        return [("command_unreadable", "the command cannot be split into words (%s); split it, or put its text in a "
                                       "file" % err)]
    except Spent:
        return [("command_unreadable", "the hook could not read the command within its budget (%d seconds), so it "
                                       "refuses it; split it into shorter commands" % READ_SECONDS)]
    seconds -= time.monotonic() - started
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
